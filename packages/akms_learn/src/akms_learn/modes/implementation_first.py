"""Mode: implementation_first — teach from implementation anchors backward into prerequisites.

Behaviour
---------
Detect implementation anchors (``implements`` edge endpoints + ``code_mirror``
nodes) and build a backward prerequisite path from each anchor by walking
``requires`` edges in reverse. The alphabetic-max-target cycle-break
rule (from :func:`~akms_learn.ordering._topo_sort_with_cycle_break`) is reused
to keep the result deterministic on cyclic requires-subgraphs.

Each implementation anchor edge produces one :class:`CodeLinkView` (using the
same shared collector pathway). The resulting view list is returned on
the result struct as ``code_references``.

Policy
------
Two render policies are supported:

* ``code_first``  — open with code anchors, then prereq concepts.
* ``concept_first`` (default) — open with concept prereqs, then code anchors.

Policy travels on :class:`~akms_learn.requests.LearningRequest.policy`. The
policy value never enters the AKMS graph; it lives on the LSP / mode result
only (Phase 2 context §"Key Principles" item 3).

Warning codes
-------------
``implementation_anchor_missing_source``
    Emitted once per implementation-anchor node whose ``source_path`` is
    missing or set to a sentinel (``"unknown" | "none" | "null" | ""``).
    ``source_ref`` is the offending anchor node id. The compiler still
    produces a valid LSP — the warning is informational.

``cycle_broken``
    Re-emitted unchanged from the underlying topological sort when a cycle
    is detected in the requires-edge subgraph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

import networkx as nx

from akms_learn._code_links import (
    MISSING_SOURCE_PATH_SENTINELS,
    build_code_links,
    is_missing_source_path,
)
from akms_learn.graph_import import GraphSlice
from akms_learn.models import CodeLinkView, LearningWarning
from akms_learn.ordering import _topo_sort_with_cycle_break, order_nodes
from akms_learn.requests import LearningRequest

__all__ = [
    "ImplementationFirstResult",
    "implementation_first_mode",
    "implementation_first_strategy",
    "ImplementationFirstPolicy",
    "DEFAULT_POLICY",
    "IMPLEMENTATION_ANCHOR_MISSING_SOURCE_CODE",
    "MISSING_SOURCE_PATH_SENTINELS",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ImplementationFirstPolicy = Literal["code_first", "concept_first"]

DEFAULT_POLICY: ImplementationFirstPolicy = "concept_first"
"""Default policy when ``request.policy`` is None or unrecognised."""

IMPLEMENTATION_ANCHOR_MISSING_SOURCE_CODE: str = "implementation_anchor_missing_source"
"""Stable warning code for an anchor lacking a usable ``source_path``."""


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ImplementationFirstResult:
    """Structured result from :func:`implementation_first_mode`.

    Attributes
    ----------
    ordered_nodes:
        Final node id list in implementation_first learning order. Section
        order depends on the resolved policy: under ``code_first`` the
        implementation-anchor section appears first, then concept prereqs;
        under ``concept_first`` the order is reversed.
    code_section:
        The sub-list of ``ordered_nodes`` corresponding to implementation
        anchors (the "code" section).
    concept_section:
        The sub-list of ``ordered_nodes`` corresponding to the backward
        prerequisite path (the "concept" section).
    code_references:
        One :class:`CodeLinkView` per ``implements`` edge in the slice,
        produced via the same collector pathway as
        :func:`akms_learn.compiler._build_code_links`. May be empty.
    policy:
        The resolved policy that produced the section order
        (``"code_first"`` or ``"concept_first"``). LSP-only — never written
        to the AKMS graph.
    source_node_ids:
        Sorted list of all node ids that contributed to the result.
    edge_ids:
        Sorted list of all edge ids present in the graph slice.
    warnings:
        List of :class:`~akms_learn.models.LearningWarning` instances.
        Includes ``implementation_anchor_missing_source`` and
        ``cycle_broken`` entries.
    """

    ordered_nodes: list[str]
    code_section: list[str]
    concept_section: list[str]
    code_references: list[CodeLinkView]
    policy: ImplementationFirstPolicy
    source_node_ids: list[str]
    edge_ids: list[str]
    warnings: list[LearningWarning] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _resolve_policy(raw: Optional[str]) -> ImplementationFirstPolicy:
    """Normalise the request's policy value to a known literal.

    ``None`` and unrecognised values both fall back to
    :data:`DEFAULT_POLICY` (``"concept_first"``). Comparison is case-
    insensitive and whitespace-tolerant.
    """
    if raw is None:
        return DEFAULT_POLICY
    norm = str(raw).strip().lower()
    if norm == "code_first":
        return "code_first"
    if norm == "concept_first":
        return "concept_first"
    return DEFAULT_POLICY


def _index_nodes(graph_slice: GraphSlice) -> dict[str, dict[str, Any]]:
    """Index nodes by ``node_id`` (shallow copies — never mutate slice)."""
    by_id: dict[str, dict[str, Any]] = {}
    for raw in graph_slice.nodes:
        nid = raw.get("node_id") or raw.get("id")
        if nid is not None:
            by_id[nid] = dict(raw)
    return by_id


def _find_implementation_anchors(
    graph_slice: GraphSlice,
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    """Return implementation-anchor node ids in deterministic (sorted) order.

    An "implementation anchor" is any node that is either:

    * the *target* of an ``implements`` edge in the slice, OR
    * a node whose ``kind == "code_mirror"``.

    The two sets are unioned and returned sorted alphabetically for
    determinism (the backward walk and warning emission will sort again).
    """
    anchors: set[str] = set()

    for edge in graph_slice.edges:
        if edge.get("type") != "implements":
            continue
        dst = edge.get("to")
        if dst is not None and dst in nodes_by_id:
            anchors.add(str(dst))

    for nid, node in nodes_by_id.items():
        if node.get("kind") == "code_mirror":
            anchors.add(nid)

    return sorted(anchors)


def _build_reverse_requires_subgraph(
    node_ids: list[str],
    graph_slice: GraphSlice,
) -> nx.DiGraph:
    """Build the *reverse* ``requires``-edge subgraph over *node_ids*.

    A ``requires`` edge ``A -> B`` (A requires B) becomes ``B -> A`` in the
    reverse subgraph, so a topological walk from a sink yields the
    prerequisite chain leading *up to* that sink — exactly the "backward
    walk from the implementation anchor" the plan calls for.
    """
    id_set = set(node_ids)
    g: nx.DiGraph = nx.DiGraph()
    g.add_nodes_from(node_ids)
    for edge in graph_slice.edges:
        if edge.get("type") != "requires":
            continue
        src = edge.get("from")
        dst = edge.get("to")
        if src in id_set and dst in id_set:
            # Reverse direction: dst -> src so prereq targets come first.
            g.add_edge(dst, src)
    return g


def _walk_backward_prereqs(
    anchors: list[str],
    graph_slice: GraphSlice,
    nodes_by_id: dict[str, dict[str, Any]],
) -> tuple[list[str], list[LearningWarning]]:
    """Build the prereq-first concept section from the implementation anchors.

    Starting from each anchor, follow ``requires`` edges in reverse (i.e.
    ``A requires B`` means B is a prerequisite of A — visit B first). Returns
    the deduped, topologically-ordered list of prereq node ids (does NOT
    include the anchors themselves).

    Cycles in the ``requires`` subgraph are broken via the
    alphabetic-max-target rule, with ``cycle_broken`` warnings forwarded.
    """
    if not anchors:
        return [], []

    # Index the reverse-requires graph over ALL nodes in the slice so we
    # can reach prereqs of prereqs.
    all_ids = list(nodes_by_id.keys())
    reverse_g = _build_reverse_requires_subgraph(all_ids, graph_slice)

    # Collect every node reachable from any anchor in the reverse graph
    # (these are the prereqs, transitively).
    reachable: set[str] = set()
    for anchor in anchors:
        if anchor not in reverse_g:
            continue
        # nx.descendants returns nodes reachable from `anchor` excluding itself.
        reachable.update(nx.descendants(reverse_g, anchor))

    # Anchors themselves are reported in code_section, not concept_section.
    prereq_ids = sorted(reachable - set(anchors))

    if not prereq_ids:
        return [], []

    # Topologically sort the prereqs respecting the reverse-requires order.
    induced = reverse_g.subgraph(prereq_ids).copy()
    ordered, warnings = _topo_sort_with_cycle_break(induced)
    return ordered, warnings


def _order_anchors(
    anchors: list[str],
    graph_slice: GraphSlice,
) -> tuple[list[str], list[LearningWarning]]:
    """Order anchor nodes deterministically respecting their requires edges."""
    if not anchors:
        return [], []
    id_set = set(anchors)
    g: nx.DiGraph = nx.DiGraph()
    g.add_nodes_from(sorted(anchors))
    for edge in graph_slice.edges:
        if edge.get("type") != "requires":
            continue
        src = edge.get("from")
        dst = edge.get("to")
        if src in id_set and dst in id_set:
            g.add_edge(src, dst)
    return _topo_sort_with_cycle_break(g)


def _build_code_references(
    graph_slice: GraphSlice,
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[CodeLinkView]:
    """Build one :class:`CodeLinkView` per ``implements`` edge in the slice.

    Delegates to :func:`akms_learn._code_links.build_code_links` with no
    missing-mirror callback — this mode emits the parallel
    ``implementation_anchor_missing_source`` warning via
    :func:`_emit_anchor_missing_source_warnings` instead. The shared
    helper applies :func:`coerce_line_range` to ``line_range`` values,
    so this code path tolerates malformed ranges (previously a raw
    ``int(...)`` cast in the local copy).
    """
    return build_code_links(
        graph_slice.edges,
        nodes_by_id,
        on_missing_mirror_source=None,
    )


def _emit_anchor_missing_source_warnings(
    anchors: list[str],
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[LearningWarning]:
    """Emit one warning per anchor whose ``source_path`` is missing/sentinel."""
    warnings: list[LearningWarning] = []
    seen: set[str] = set()
    for anchor_id in anchors:
        if anchor_id in seen:
            continue
        node = nodes_by_id.get(anchor_id) or {}
        if is_missing_source_path(node.get("source_path")):
            warnings.append(
                LearningWarning(
                    severity="warning",
                    code=IMPLEMENTATION_ANCHOR_MISSING_SOURCE_CODE,
                    source_ref=anchor_id,
                    message=(
                        f"Implementation anchor {anchor_id!r} has no usable "
                        f"source path (missing or set to a sentinel value "
                        f"such as 'unknown'); code-reference rendering will "
                        f"fall back to the node id."
                    ),
                )
            )
            seen.add(anchor_id)
    return warnings


# ---------------------------------------------------------------------------
# Public ordering strategy (registered in ordering.py)
# ---------------------------------------------------------------------------


def implementation_first_strategy(
    graph_slice: GraphSlice,
) -> tuple[list[str], list[LearningWarning]]:
    """Ordering strategy for the ``implementation_first`` mode.

    Produces a default-policy (``concept_first``) ordering — concept prereqs
    first, then implementation anchors, then any remaining nodes (in the
    authoritative default order from :func:`order_nodes`). The full
    :func:`implementation_first_mode` is the supported API for the rich
    result (code_references, policy-aware section split, anchor warnings).

    Determinism: anchor discovery sorts; the reverse-requires topo sort uses
    the alphabetic-max cycle-break.
    """
    nodes_by_id = _index_nodes(graph_slice)
    anchors = _find_implementation_anchors(graph_slice, nodes_by_id)

    concept_ordered, concept_w = _walk_backward_prereqs(
        anchors, graph_slice, nodes_by_id
    )
    anchor_ordered, anchor_w = _order_anchors(anchors, graph_slice)

    placed: set[str] = set(concept_ordered) | set(anchor_ordered)
    default_ordered, default_w = order_nodes(graph_slice)
    leftover = [nid for nid in default_ordered if nid not in placed]

    # Default policy at the strategy level is concept_first.
    ordered = concept_ordered + anchor_ordered + leftover

    warnings: list[LearningWarning] = []
    warnings.extend(concept_w)
    warnings.extend(anchor_w)
    # Only forward cycle warnings from the default ordering — anchor /
    # prereq partitions have already accounted for the slice's requires
    # edges, so default-order cycle warnings would be duplicates. Filter
    # by code to avoid re-emitting.
    for w in default_w:
        if w.code != "cycle_broken":
            warnings.append(w)

    return ordered, warnings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def implementation_first_mode(
    graph_slice: GraphSlice,
    request: LearningRequest,
) -> tuple[ImplementationFirstResult, list[LearningWarning]]:
    """Build the implementation_first mode view.

    Pure function — never mutates ``graph_slice`` or ``request``.

    Parameters
    ----------
    graph_slice:
        Immutable :class:`~akms_learn.graph_import.GraphSlice` from the
        compiler pipeline.
    request:
        The validated :class:`~akms_learn.requests.LearningRequest`. Reads
        ``request.policy`` (Optional). ``None`` and unrecognised values
        normalise to :data:`DEFAULT_POLICY` (``"concept_first"``).

    Returns
    -------
    (result, warnings)
        ``result`` is an :class:`ImplementationFirstResult` containing the
        ordered nodes, section split, code references, and resolved policy.
        ``warnings`` is the same list as ``result.warnings``.
    """
    nodes_by_id = _index_nodes(graph_slice)
    policy = _resolve_policy(getattr(request, "policy", None))

    # Discover anchors first — the warning + code-reference paths need them.
    anchors = _find_implementation_anchors(graph_slice, nodes_by_id)

    # Backward prereq walk produces the concept section.
    concept_ordered, concept_warnings = _walk_backward_prereqs(
        anchors, graph_slice, nodes_by_id
    )

    # Anchors form the code section, ordered respecting requires edges
    # between anchors (rare but possible).
    anchor_ordered, anchor_warnings = _order_anchors(anchors, graph_slice)

    # Any nodes not placed by the prereq walk or anchor set fall through
    # in the authoritative default order — this preserves provenance for
    # nodes that are neither anchors nor prerequisites of anchors.
    placed: set[str] = set(concept_ordered) | set(anchor_ordered)
    default_ordered, default_warnings = order_nodes(graph_slice)
    leftover = [nid for nid in default_ordered if nid not in placed]

    # Compose final ordering per policy.
    if policy == "code_first":
        ordered_nodes = anchor_ordered + concept_ordered + leftover
    else:
        ordered_nodes = concept_ordered + anchor_ordered + leftover

    # Build the per-edge CodeLinkView list.
    code_references = _build_code_references(graph_slice, nodes_by_id)

    # Emit anchor-missing-source warnings.
    anchor_missing_warnings = _emit_anchor_missing_source_warnings(anchors, nodes_by_id)

    all_warnings: list[LearningWarning] = []
    all_warnings.extend(concept_warnings)
    all_warnings.extend(anchor_warnings)
    # Forward only non-cycle warnings from the default ordering (anchor +
    # prereq partitions own the requires-cycle reporting).
    for w in default_warnings:
        if w.code != "cycle_broken":
            all_warnings.append(w)
    all_warnings.extend(anchor_missing_warnings)

    source_node_ids = sorted(nid for nid in ordered_nodes if nid in nodes_by_id)
    edge_ids = sorted(
        str(e.get("edge_id", "")) for e in graph_slice.edges if e.get("edge_id")
    )

    result = ImplementationFirstResult(
        ordered_nodes=ordered_nodes,
        code_section=list(anchor_ordered),
        concept_section=list(concept_ordered),
        code_references=code_references,
        policy=policy,
        source_node_ids=source_node_ids,
        edge_ids=edge_ids,
        warnings=all_warnings,
    )
    return result, all_warnings
