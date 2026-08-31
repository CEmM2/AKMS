"""Tests for composed required, coactivated, and advisory task queries."""

from __future__ import annotations

import networkx as nx
import pytest

from akms.graph.query_subgraph import query_subgraph
from akms.schema.models import AgentRole, NodeStatus, PropagationConfig
from akms.task_context.query import (
    RequiredNodeUnavailableError,
    SelectionClass,
    query_task_knowledge,
)
from akms.task_context.resolve import ResolvedSeeds


def _add_node(
    graph: nx.DiGraph,
    node_id: str,
    *,
    tags: tuple[str, ...] = (),
    status: str | NodeStatus = NodeStatus.ESTABLISHED,
    confidence: float = 0.9,
    domain: str = "test",
    load_with: tuple[str, ...] = (),
) -> None:
    graph.add_node(
        node_id,
        title=node_id,
        tags=list(tags),
        status=status,
        confidence=confidence,
        domain=domain,
        load_with=list(load_with),
    )


def _resolved(
    *,
    required: tuple[str, ...] = (),
    advisory_tags: tuple[str, ...] = (),
) -> ResolvedSeeds:
    return ResolvedSeeds(
        advisory_tags=advisory_tags,
        required_route_node_ids=required,
        reasons={
            node_id: (f"exact fixture route for '{node_id}'",) for node_id in required
        },
    )


@pytest.mark.unit
def test_required_nodes_bypass_loadout_cap():
    graph = nx.DiGraph()
    required = tuple(f"required-{index}" for index in range(4))
    for node_id in required:
        _add_node(graph, node_id, confidence=0.0)
    _add_node(graph, "advisory", tags=("topic",), confidence=1.0)

    config = PropagationConfig()
    config.loadout.max_nodes_per_loadout = 1
    config.loadout.min_confidence_threshold = 0.95

    result = query_task_knowledge(
        graph,
        _resolved(required=required, advisory_tags=("topic",)),
        AgentRole.IMPLEMENTER,
        config=config,
    )

    assert result.required_node_ids == required
    assert result.advisory_node_ids == ("advisory",)
    assert len(result.required_node_ids) > config.loadout.max_nodes_per_loadout
    assert all(
        selection.selection_class is SelectionClass.REQUIRED
        for selection in result.selections[: len(required)]
    )


@pytest.mark.unit
def test_advisory_filters_and_cap_preserved_in_composed_query():
    graph = nx.DiGraph()
    _add_node(
        graph,
        "preferred",
        tags=("topic",),
        confidence=0.9,
        domain="computational-mechanics",
    )
    _add_node(
        graph,
        "low-confidence",
        tags=("topic",),
        confidence=0.1,
        domain="computational-mechanics",
    )
    _add_node(
        graph,
        "draft",
        tags=("topic",),
        status=NodeStatus.DRAFT,
        confidence=1.0,
        domain="computational-mechanics",
    )
    _add_node(
        graph,
        "role-excluded",
        tags=("topic",),
        confidence=1.0,
        domain="code-mirror",
    )

    config = PropagationConfig()
    config.loadout.max_nodes_per_loadout = 1
    config.loadout.min_confidence_threshold = 0.3
    role = AgentRole.PHYSICS_REVIEWER

    ordinary = query_subgraph(graph, ["topic"], role, config=config)
    composed = query_task_knowledge(
        graph,
        _resolved(advisory_tags=("topic",)),
        role,
        config=config,
    )

    assert composed.advisory_node_ids == tuple(node_id for node_id, _ in ordinary)
    assert composed.advisory_node_ids == ("preferred",)
    assert tuple(selection.node_data for selection in composed.selections) == tuple(
        node_data for _, node_data in ordinary
    )


@pytest.mark.unit
def test_load_with_nodes_classified_coactivated_not_required():
    graph = nx.DiGraph()
    _add_node(
        graph,
        "required",
        load_with=("companion",),
    )
    _add_node(graph, "companion", tags=("topic",))

    result = query_task_knowledge(
        graph,
        _resolved(required=("required",), advisory_tags=("topic",)),
        AgentRole.IMPLEMENTER,
    )

    assert result.required_node_ids == ("required",)
    assert result.coactivated_node_ids == ("companion",)
    assert result.advisory_node_ids == ()
    companion = result.selections[1]
    assert companion.selection_class is SelectionClass.COACTIVATED
    assert companion.node_data["_coactivated"] is True
    assert companion.reasons == ("load_with from required node 'required'",)


@pytest.mark.unit
def test_missing_or_unloadable_required_nodes_fail_closed():
    graph = nx.DiGraph()
    _add_node(graph, "draft", status=NodeStatus.DRAFT)
    _add_node(graph, "session", domain="session")

    with pytest.raises(RequiredNodeUnavailableError) as exc_info:
        query_task_knowledge(
            graph,
            _resolved(required=("missing", "draft", "session")),
            AgentRole.IMPLEMENTER,
        )

    assert exc_info.value.node_ids == ("draft", "missing", "session")
    assert "missing from graph" in str(exc_info.value)
    assert "status 'draft' is not loadable" in str(exc_info.value)
    assert "session nodes are not loadable" in str(exc_info.value)


@pytest.mark.unit
def test_selection_order_is_required_then_coactivated_then_advisory():
    graph = nx.DiGraph()
    _add_node(graph, "required-b", load_with=("coactivated-b",))
    _add_node(graph, "required-a", load_with=("coactivated-a",))
    _add_node(graph, "coactivated-a", tags=("topic",), confidence=1.0)
    _add_node(graph, "coactivated-b", tags=("topic",), confidence=1.0)
    _add_node(graph, "advisory-a", tags=("topic",), confidence=0.9)
    _add_node(graph, "advisory-b", tags=("topic",), confidence=0.8)

    result = query_task_knowledge(
        graph,
        _resolved(
            required=("required-b", "required-a"),
            advisory_tags=("topic",),
        ),
        AgentRole.IMPLEMENTER,
    )

    assert result.node_ids == (
        "required-a",
        "required-b",
        "coactivated-a",
        "coactivated-b",
        "advisory-a",
        "advisory-b",
    )
    assert tuple(selection.selection_class for selection in result.selections) == (
        SelectionClass.REQUIRED,
        SelectionClass.REQUIRED,
        SelectionClass.COACTIVATED,
        SelectionClass.COACTIVATED,
        SelectionClass.ADVISORY,
        SelectionClass.ADVISORY,
    )


@pytest.mark.unit
def test_required_and_coactivated_reasons_are_sorted_and_deduplicated():
    graph = nx.DiGraph()
    _add_node(graph, "required-a", load_with=("companion",))
    _add_node(graph, "required-b", load_with=("companion",))
    _add_node(graph, "companion")
    seeds = ResolvedSeeds(
        required_route_node_ids=("required-b", "required-a"),
        reasons={
            "required-a": ("z-reason", "a-reason", "a-reason"),
            "required-b": ("b-reason",),
        },
    )

    result = query_task_knowledge(
        graph,
        seeds,
        AgentRole.IMPLEMENTER,
    )

    assert result.selections[0].reasons == ("a-reason", "z-reason")
    assert result.selections[2].reasons == (
        "load_with from required node 'required-a'",
        "load_with from required node 'required-b'",
    )
