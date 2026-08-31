"""Mode: derivation_first — assumptions → definitions → equations → derivation before prose/implementation.

Ordering contract
-----------------
Derivation-heavy nodes (those carrying ``derivation``, ``prerequisites``, or
``concept`` sections, or equation-heavy content markers) are placed **before**
nodes that carry only implementation/worked-example content.

Within each partition the ``requires``-edge topology is respected via a
topological sort.  Cycles are broken by the alphabetic-max-target rule
(reused from :func:`~akms_learn.ordering._topo_sort_with_cycle_break`).

Node role classification (LSP-only — never written to the AKMS graph)
-----------------------------------------------------------------------
Each node receives a ``role_in_lesson`` value stored in a
:class:`NodeLessonRoleView` sidecar struct on the result.  The five roles:

``assumption``
    Node carries a ``prerequisites`` section.

``definition``
    Node carries a ``concept`` section but NOT a ``derivation`` section.

``derivation_step``
    Node carries a ``derivation`` section.

``result``
    Node carries a ``worked_example`` or ``assessment`` section but none of
    the above derivation-first indicators.

``gap``
    Node is a ``requires``-edge neighbour of a ``derivation_step`` node (i.e.
    it is a *target* of a ``requires`` edge whose source is a
    ``derivation_step``) but itself lacks a ``derivation`` section.  A gap
    represents a broken derivation chain — the derivation depends on a step
    that has no recorded derivation.

Derivation-gap warnings
-----------------------
``derivation_gap``
    Emitted once per ``gap``-role node.  ``source_ref`` is the offending
    node id so the graph author can locate and fill the missing section.

Warning codes
-------------
``derivation_gap``
    Derivation chain is broken: a node that a derivation step requires lacks
    its own ``derivation`` section.  ``source_ref`` = offending node id.

``cycle_broken``
    Re-emitted (unchanged) from the underlying topological sort when a cycle
    is detected in the requires-edge subgraph.  Uses the
    alphabetic-max-target rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import networkx as nx

from akms_learn.graph_import import GraphSlice
from akms_learn.models import LearningWarning
from akms_learn.ordering import _topo_sort_with_cycle_break
from akms_learn.requests import LearningRequest
from akms_learn.section_extraction import (
    ExtractedSection,
    extract_sections_from_node,
)

__all__ = [
    "NodeLessonRoleView",
    "DerivationFirstResult",
    "derivation_first_mode",
    "derivation_first_strategy",
    "DERIVATION_HEAVY_HEADINGS",
    "IMPLEMENTATION_HEADINGS",
    "DERIVATION_GAP_CODE",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Approved headings that signal derivation-heavy content (plan §7, L151).
# Equation-heavy content is inferred from the presence of these headings too,
# since the approved heading set does not have a separate "equations" heading.
DERIVATION_HEAVY_HEADINGS: frozenset[str] = frozenset(
    {"derivation", "prerequisites", "concept"}
)

# Approved headings that signal implementation-only content.
IMPLEMENTATION_HEADINGS: frozenset[str] = frozenset(
    {"implementation", "worked_example"}
)

# Stable warning code for derivation-gap warnings.
DERIVATION_GAP_CODE: str = "derivation_gap"

# Role type (LSP-internal only — never touches the AKMS graph).
NodeRole = Literal["assumption", "definition", "derivation_step", "result", "gap"]


# ---------------------------------------------------------------------------
# Sidecar struct: node role view (LSP-only)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NodeLessonRoleView:
    """Sidecar view carrying the derivation-first role of a single node.

    This struct is **LSP-only** — it is produced during mode execution and
    returned on :class:`DerivationFirstResult`.  It is NEVER written into the
    AKMS v2 graph or any persisted graph file.

    Fields
    ------
    node_id:
        The AKMS node id this view describes.
    role_in_lesson:
        One of ``assumption | definition | derivation_step | result | gap``.
    """

    node_id: str
    role_in_lesson: NodeRole


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class DerivationFirstResult:
    """Structured result from :func:`derivation_first_mode`.

    Attributes
    ----------
    ordered_nodes:
        Node id list in derivation-first learning order:
        derivation-heavy nodes before implementation-heavy nodes,
        respecting ``requires`` edges within each partition.
    role_views:
        One :class:`NodeLessonRoleView` per node in ``ordered_nodes``,
        in the same order.  The ``role_in_lesson`` field is LSP-only and
        absent from any persisted AKMS graph file.
    source_node_ids:
        Sorted list of all node ids that contributed to the result.
    edge_ids:
        Sorted list of all edge ids present in the graph slice.
    warnings:
        List of :class:`~akms_learn.models.LearningWarning` instances.
        Includes ``derivation_gap`` and ``cycle_broken`` entries.
    """

    __slots__ = (
        "ordered_nodes",
        "role_views",
        "source_node_ids",
        "edge_ids",
        "warnings",
    )

    def __init__(
        self,
        ordered_nodes: list[str],
        role_views: list[NodeLessonRoleView],
        source_node_ids: list[str],
        edge_ids: list[str],
        warnings: list[LearningWarning],
    ) -> None:
        self.ordered_nodes = ordered_nodes
        self.role_views = role_views
        self.source_node_ids = source_node_ids
        self.edge_ids = edge_ids
        self.warnings = warnings


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _collect_node_headings(
    node_id: str,
    nodes_by_id: dict[str, dict[str, Any]],
) -> frozenset[str]:
    """Return the set of approved normalized headings present in a node."""
    node = nodes_by_id.get(node_id)
    if node is None:
        return frozenset()
    sections: list[ExtractedSection] = extract_sections_from_node(node)
    return frozenset(s.normalized_name for s in sections)


def _classify_role(
    node_id: str,
    headings: frozenset[str],
    gap_node_ids: frozenset[str],
) -> NodeRole:
    """Assign a :data:`NodeRole` to a node.

    Priority order:
    1. ``gap`` — if the node is in the pre-computed gap set.
    2. ``derivation_step`` — has a ``derivation`` heading.
    3. ``assumption`` — has ``prerequisites`` but no ``derivation``.
    4. ``definition`` — has ``concept`` but no ``derivation``.
    5. ``result`` — has ``worked_example`` or ``assessment``.
    6. Default → ``result`` (catch-all).
    """
    if node_id in gap_node_ids:
        return "gap"
    if "derivation" in headings:
        return "derivation_step"
    if "prerequisites" in headings:
        return "assumption"
    if "concept" in headings:
        return "definition"
    return "result"


def _is_derivation_heavy(headings: frozenset[str]) -> bool:
    """Return True when the node has at least one derivation-heavy heading."""
    return bool(headings & DERIVATION_HEAVY_HEADINGS)


def _build_requires_subgraph(
    node_ids: list[str],
    graph_slice: GraphSlice,
) -> nx.DiGraph:
    """Build a directed ``requires``-edge subgraph over *node_ids*."""
    id_set = set(node_ids)
    g: nx.DiGraph = nx.DiGraph()
    g.add_nodes_from(node_ids)
    for edge in graph_slice.edges:
        etype = edge.get("type", "")
        if etype != "requires":
            continue
        src = edge.get("from")
        dst = edge.get("to")
        if src in id_set and dst in id_set:
            g.add_edge(src, dst)
    return g


def _order_partition(
    node_ids: list[str],
    graph_slice: GraphSlice,
) -> tuple[list[str], list[LearningWarning]]:
    """Return a deterministic order for *node_ids* respecting ``requires`` edges.

    Uses :func:`~akms_learn.ordering._topo_sort_with_cycle_break` (the
    alphabetic-max cycle-break) on the ``requires``-edge induced subgraph.
    """
    if not node_ids:
        return [], []
    subgraph = _build_requires_subgraph(node_ids, graph_slice)
    return _topo_sort_with_cycle_break(subgraph)


def _partition_and_order(
    graph_slice: GraphSlice,
) -> tuple[
    list[str],
    list[LearningWarning],
    dict[str, dict[str, Any]],
    dict[str, frozenset[str]],
]:
    """Shared partition + topo-sort kernel for the strategy and mode.

    Indexes nodes by id, collects approved headings per node, partitions
    into derivation-heavy vs implementation-only, then topo-sorts each
    partition with the alphabetic-max cycle-break. Returns the
    ordered node list plus the intermediate maps the mode function needs
    for role classification and gap detection (the strategy discards
    them via `_, _ = ...` unpacking).

    Extracted to remove duplicated scaffolding between
    :func:`derivation_first_strategy` and :func:`derivation_first_mode`.
    """
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for raw in graph_slice.nodes:
        nid = raw.get("node_id")
        if nid is not None:
            nodes_by_id[nid] = dict(raw)

    all_node_ids = list(nodes_by_id.keys())

    headings_by_id: dict[str, frozenset[str]] = {
        nid: _collect_node_headings(nid, nodes_by_id) for nid in all_node_ids
    }

    heavy: list[str] = []
    light: list[str] = []
    for nid in all_node_ids:
        if _is_derivation_heavy(headings_by_id[nid]):
            heavy.append(nid)
        else:
            light.append(nid)

    heavy_sorted = sorted(heavy)
    light_sorted = sorted(light)

    warnings: list[LearningWarning] = []
    heavy_ordered, w1 = _order_partition(heavy_sorted, graph_slice)
    warnings.extend(w1)
    light_ordered, w2 = _order_partition(light_sorted, graph_slice)
    warnings.extend(w2)

    return heavy_ordered + light_ordered, warnings, nodes_by_id, headings_by_id


def _find_gap_nodes(
    headings_by_id: dict[str, frozenset[str]],
    graph_slice: GraphSlice,
) -> frozenset[str]:
    """Identify nodes that are derivation-chain gaps.

    A node N is a gap when ALL of these hold:
    1. N is the *target* of a ``requires`` edge whose source S is a
       ``derivation_step`` node (S has a ``derivation`` heading).
    2. N itself lacks a ``derivation`` heading.

    Rationale: if a derivation step *requires* N, the reader needs N's
    derivation to follow the chain.  If N has no derivation, the chain is
    broken.
    """
    # Build the set of derivation_step node ids.
    derivation_step_ids: frozenset[str] = frozenset(
        nid for nid, h in headings_by_id.items() if "derivation" in h
    )

    gap_ids: set[str] = set()
    for edge in graph_slice.edges:
        if edge.get("type") != "requires":
            continue
        src = edge.get("from")
        dst = edge.get("to")
        if src is None or dst is None:
            continue
        # src is a derivation_step AND dst is in our node set AND dst lacks derivation.
        if src in derivation_step_ids and dst in headings_by_id:
            dst_headings = headings_by_id[dst]
            if "derivation" not in dst_headings:
                gap_ids.add(dst)

    return frozenset(gap_ids)


# ---------------------------------------------------------------------------
# Public ordering strategy (registered in ordering.py)
# ---------------------------------------------------------------------------


def derivation_first_strategy(
    graph_slice: GraphSlice,
) -> tuple[list[str], list[LearningWarning]]:
    """Ordering strategy for the ``derivation_first`` mode.

    Reorders the graph nodes so that derivation-heavy nodes (those with
    ``derivation``, ``prerequisites``, or ``concept`` sections) precede
    implementation-heavy nodes.  Within each partition the ``requires``-edge
    topology is respected with the alphabetic-max cycle-break.

    This is the function registered in the strategy registry for the
    ``derivation_first`` mode key.  Mode callers should use
    :func:`derivation_first_mode` for the full result including role views
    and gap warnings.

    Parameters
    ----------
    graph_slice:
        Immutable :class:`~akms_learn.graph_import.GraphSlice`.

    Returns
    -------
    (ordered_node_ids, warnings)
    """
    ordered, warnings, _nodes_by_id, _headings_by_id = _partition_and_order(graph_slice)
    return ordered, warnings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def derivation_first_mode(
    graph_slice: GraphSlice,
    request: LearningRequest,
) -> tuple[DerivationFirstResult, list[LearningWarning]]:
    """Build the derivation_first mode view.

    Pure function — never mutates ``graph_slice`` or ``request``.

    Parameters
    ----------
    graph_slice:
        Immutable :class:`~akms_learn.graph_import.GraphSlice` from the
        compiler pipeline.
    request:
        The validated :class:`~akms_learn.requests.LearningRequest`.

    Returns
    -------
    (result, warnings)
        ``result`` is a :class:`DerivationFirstResult`.  The
        ``role_views`` attribute contains the LSP-only role assignments —
        these are NEVER written to any AKMS graph file.
        ``warnings`` is the same list as ``result.warnings``, provided at
        the top level for compatibility with the mode-dispatcher pattern.
    """
    # ------------------------------------------------------------------
    # Shared partition + topo-sort kernel (also used by the strategy).
    # Returns the partitioned + ordered node list along with the indexed
    # maps the mode function needs for role classification + gap lookup.
    # ------------------------------------------------------------------
    ordered_nodes, all_warnings, nodes_by_id, headings_by_id = _partition_and_order(
        graph_slice
    )

    # ------------------------------------------------------------------
    # Identify gap nodes (derivation-chain gaps).
    # ------------------------------------------------------------------
    gap_node_ids = _find_gap_nodes(headings_by_id, graph_slice)

    # ------------------------------------------------------------------
    # Classify roles (role_in_lesson stays on the sidecar, never the graph).
    # ------------------------------------------------------------------
    role_views: list[NodeLessonRoleView] = []
    for nid in ordered_nodes:
        role = _classify_role(nid, headings_by_id.get(nid, frozenset()), gap_node_ids)
        role_views.append(NodeLessonRoleView(node_id=nid, role_in_lesson=role))

    # ------------------------------------------------------------------
    # Emit derivation_gap warnings.
    # ------------------------------------------------------------------
    for nid in sorted(gap_node_ids):  # sorted for deterministic warning order
        all_warnings.append(
            LearningWarning(
                severity="warning",
                code=DERIVATION_GAP_CODE,
                source_ref=nid,
                message=(
                    f"Derivation chain gap: node {nid!r} is required by a "
                    f"derivation_step node but lacks a 'derivation' section. "
                    f"Add a derivation section to close the gap."
                ),
            )
        )

    # ------------------------------------------------------------------
    # Provenance lists.
    # ------------------------------------------------------------------
    source_node_ids = sorted(nid for nid in ordered_nodes if nid in nodes_by_id)
    edge_ids = sorted(
        str(e.get("edge_id", "")) for e in graph_slice.edges if e.get("edge_id")
    )

    result = DerivationFirstResult(
        ordered_nodes=ordered_nodes,
        role_views=role_views,
        source_node_ids=source_node_ids,
        edge_ids=edge_ids,
        warnings=all_warnings,
    )

    return result, all_warnings
