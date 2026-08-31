"""Compose uncapped exact task requirements with ordinary advisory queries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

import networkx as nx

from akms.graph.query_subgraph import query_subgraph
from akms.schema.models import (
    LOADABLE_STATUSES,
    AgentRole,
    NodeStatus,
    PropagationConfig,
)
from akms.task_context.resolve import ResolvedSeeds


class SelectionClass(str, Enum):
    """Why a node was selected, in deterministic precedence order."""

    REQUIRED = "required"
    COACTIVATED = "coactivated"
    ADVISORY = "advisory"


_SELECTION_ORDER = {
    SelectionClass.REQUIRED: 0,
    SelectionClass.COACTIVATED: 1,
    SelectionClass.ADVISORY: 2,
}


@dataclass(frozen=True)
class NodeSelection:
    """One selected graph node with its class, data, and audit reasons."""

    node_id: str
    selection_class: SelectionClass
    node_data: dict[str, Any]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        node_id = str(self.node_id).strip()
        if not node_id:
            raise ValueError("Selected node_id must not be empty")
        reasons = tuple(
            sorted({reason for item in self.reasons if (reason := str(item).strip())})
        )
        if not reasons:
            raise ValueError(f"Selected node '{node_id}' requires at least one reason")
        object.__setattr__(self, "node_id", node_id)
        object.__setattr__(
            self,
            "selection_class",
            SelectionClass(self.selection_class),
        )
        object.__setattr__(self, "node_data", dict(self.node_data))
        object.__setattr__(self, "reasons", reasons)


@dataclass(frozen=True)
class TaskKnowledgeQueryResult:
    """Canonical required, coactivated, then advisory node selections."""

    selections: tuple[NodeSelection, ...]

    def __post_init__(self) -> None:
        selections = tuple(self.selections)
        node_ids = [selection.node_id for selection in selections]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Task query selections must contain unique node IDs")
        class_order = [
            _SELECTION_ORDER[selection.selection_class] for selection in selections
        ]
        if class_order != sorted(class_order):
            raise ValueError(
                "Task query selections must be ordered required, "
                "coactivated, then advisory"
            )
        object.__setattr__(self, "selections", selections)

    @property
    def node_ids(self) -> tuple[str, ...]:
        return tuple(selection.node_id for selection in self.selections)

    def node_ids_for(self, selection_class: SelectionClass) -> tuple[str, ...]:
        return tuple(
            selection.node_id
            for selection in self.selections
            if selection.selection_class is selection_class
        )

    @property
    def required_node_ids(self) -> tuple[str, ...]:
        return self.node_ids_for(SelectionClass.REQUIRED)

    @property
    def coactivated_node_ids(self) -> tuple[str, ...]:
        return self.node_ids_for(SelectionClass.COACTIVATED)

    @property
    def advisory_node_ids(self) -> tuple[str, ...]:
        return self.node_ids_for(SelectionClass.ADVISORY)


class RequiredNodeUnavailableError(ValueError):
    """Raised before advisory querying when exact requirements cannot load."""

    def __init__(self, issues: Mapping[str, str]):
        if not issues:
            raise ValueError("RequiredNodeUnavailableError requires issues")
        self.issues = {
            str(node_id): str(reason) for node_id, reason in sorted(issues.items())
        }
        self.node_ids = tuple(self.issues)
        detail = "; ".join(
            f"{node_id}: {reason}" for node_id, reason in self.issues.items()
        )
        super().__init__(f"Required task nodes are unavailable: {detail}")


def _status_value(node_data: Mapping[str, Any]) -> str | None:
    status = node_data.get("status")
    if isinstance(status, NodeStatus):
        return status.value
    return str(status) if status is not None else None


def _unloadable_reason(node_data: Mapping[str, Any]) -> str | None:
    if str(node_data.get("domain", "")) == "session":
        return "session nodes are not loadable"
    status = _status_value(node_data)
    loadable_values = {item.value for item in LOADABLE_STATUSES}
    if status not in loadable_values:
        return f"status {status!r} is not loadable"
    return None


def _required_issues(
    graph: nx.DiGraph,
    required_node_ids: tuple[str, ...],
) -> dict[str, str]:
    issues: dict[str, str] = {}
    for node_id in required_node_ids:
        if node_id not in graph:
            issues[node_id] = "missing from graph"
            continue
        reason = _unloadable_reason(graph.nodes[node_id])
        if reason is not None:
            issues[node_id] = reason
    return issues


def _load_with_targets(
    graph: nx.DiGraph,
    source_ids: tuple[str, ...],
    required_ids: frozenset[str],
) -> dict[str, set[str]]:
    reasons: dict[str, set[str]] = {}
    for source_id in source_ids:
        hints = graph.nodes[source_id].get("load_with", ()) or ()
        if isinstance(hints, str):
            hints = (hints,)
        source_class = "required" if source_id in required_ids else "advisory"
        for raw_target in hints:
            target = str(raw_target)
            if target in required_ids or target not in graph:
                continue
            if _unloadable_reason(graph.nodes[target]) is not None:
                continue
            reasons.setdefault(target, set()).add(
                f"load_with from {source_class} node '{source_id}'"
            )
    return reasons


def query_task_knowledge(
    graph: nx.DiGraph,
    seeds: ResolvedSeeds,
    agent_role: AgentRole | str,
    *,
    config: PropagationConfig | None = None,
    max_depth: int = 2,
) -> TaskKnowledgeQueryResult:
    """Compose exact requirements with the unchanged advisory query path.

    Required nodes are validated and inserted independently of ordinary role,
    status, confidence, ranking, and loadout-cap filters. One-hop ``load_with``
    targets are classified separately as coactivated. Remaining ordinary
    ``query_subgraph`` results retain their existing order and node data.
    """

    if not isinstance(seeds, ResolvedSeeds):
        raise TypeError("seeds must be ResolvedSeeds")

    required_node_ids = seeds.all_exact_node_ids
    issues = _required_issues(graph, required_node_ids)
    if issues:
        raise RequiredNodeUnavailableError(issues)

    ordinary = query_subgraph(
        graph,
        list(seeds.advisory_tags),
        agent_role,
        config=config,
        max_depth=max_depth,
    )
    ordinary_base_ids = tuple(
        node_id for node_id, node_data in ordinary if not node_data.get("_coactivated")
    )
    required_set = frozenset(required_node_ids)
    coactivation_reasons = _load_with_targets(
        graph,
        required_node_ids + ordinary_base_ids,
        required_set,
    )
    coactivated_node_ids = tuple(sorted(coactivation_reasons))
    coactivated_set = frozenset(coactivated_node_ids)

    selections: list[NodeSelection] = []
    for node_id in required_node_ids:
        node_data = dict(graph.nodes[node_id])
        node_data.pop("_coactivated", None)
        selections.append(
            NodeSelection(
                node_id=node_id,
                selection_class=SelectionClass.REQUIRED,
                node_data=node_data,
                reasons=seeds.reasons[node_id],
            )
        )

    for node_id in coactivated_node_ids:
        node_data = dict(graph.nodes[node_id])
        node_data["_coactivated"] = True
        selections.append(
            NodeSelection(
                node_id=node_id,
                selection_class=SelectionClass.COACTIVATED,
                node_data=node_data,
                reasons=tuple(coactivation_reasons[node_id]),
            )
        )

    advisory_reason = (
        "advisory tag query: " + ", ".join(seeds.advisory_tags)
        if seeds.advisory_tags
        else "advisory tag query: empty"
    )
    for node_id, node_data in ordinary:
        if node_id in required_set or node_id in coactivated_set:
            continue
        selections.append(
            NodeSelection(
                node_id=node_id,
                selection_class=SelectionClass.ADVISORY,
                node_data=node_data,
                reasons=(advisory_reason,),
            )
        )

    return TaskKnowledgeQueryResult(selections=tuple(selections))
