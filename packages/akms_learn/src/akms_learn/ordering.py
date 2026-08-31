"""Deterministic learning-order computation over a GraphSlice.

**Bucket sequence** (plan §12):
    prerequisites → core concepts → derivations → implementations →
    pitfalls → exercises → next paths

**Cycle-break rule**:
    When a bucket's induced subgraph contains a cycle, each cycle is resolved
    by removing exactly one edge: the edge whose *target* node_id sorts
    lexicographically last (alphabetic-max target).  The edge to the
    alphabetically-largest target node is removed first; if there are still
    cycles after removing that edge, the process is repeated until the subgraph
    is acyclic.  Each removal emits a ``LearningWarning(code="cycle_broken",
    severity="warning")``.

**Purity guarantee**:
    ``order_nodes`` never mutates ``graph_slice`` or any of its contained
    dicts.  It builds a fresh ``networkx.DiGraph`` and works entirely on
    copies.

**Node-kind → bucket mapping**:
    Explicit ``node["kind"]`` takes priority when it matches one of:
        ``prerequisite``  → ``"prerequisites"``
        ``core_concept``  → ``"core concepts"``
        ``derivation``    → ``"derivations"``
        ``implementation`` → ``"implementations"``
        ``pitfall``       → ``"pitfalls"``
        ``exercise``      → ``"exercises"``
        ``next_path``     → ``"next paths"``

    If ``kind`` is absent or unrecognised, the bucket is inferred from incident
    edge types (the *source* node of a classifying edge lands in the matching
    bucket; see ``EDGE_TYPE_TO_BUCKET``).  Nodes that cannot be classified
    fall into ``"core concepts"``.

**Edge-type → bucket for source-node classification**:
    ``requires``    → source goes to ``"prerequisites"``
    ``derives``     → source goes to ``"derivations"``
    ``implements``  → source goes to ``"implementations"``
    ``pitfall_of``  → source goes to ``"pitfalls"``
    ``exercise_for``→ source goes to ``"exercises"``
    ``next_path``   → source goes to ``"next paths"``
"""

from __future__ import annotations

from typing import Any, Callable

import networkx as nx

from akms_learn.graph_import import GraphSlice
from akms_learn.models import LearningWarning

__all__ = [
    "LEARNING_BUCKETS",
    "EDGE_TYPE_TO_BUCKET",
    "order_nodes",
    "OrderingStrategy",
    "STRATEGY_KEYS",
    "get_strategy",
    "list_strategies",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LEARNING_BUCKETS: tuple[str, ...] = (
    "prerequisites",
    "core concepts",
    "derivations",
    "implementations",
    "pitfalls",
    "exercises",
    "next paths",
)

# Maps edge *type* → bucket the SOURCE node of that edge belongs to.
EDGE_TYPE_TO_BUCKET: dict[str, str] = {
    "requires": "prerequisites",
    "derives": "derivations",
    "implements": "implementations",
    "pitfall_of": "pitfalls",
    "exercise_for": "exercises",
    "next_path": "next paths",
}

# Maps explicit node["kind"] values → bucket name.
_KIND_TO_BUCKET: dict[str, str] = {
    "prerequisite": "prerequisites",
    "core_concept": "core concepts",
    "derivation": "derivations",
    "implementation": "implementations",
    "pitfall": "pitfalls",
    "exercise": "exercises",
    "next_path": "next paths",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_digraph(
    nodes: tuple[dict[str, Any], ...],
    edges: tuple[dict[str, Any], ...],
) -> nx.DiGraph:
    """Build a ``networkx.DiGraph`` from raw node/edge dicts (read-only).

    Nodes are keyed by their ``node_id`` (preferred) or ``id`` field.
    Edges must have ``from``, ``to``, and ``type`` keys.
    """
    g: nx.DiGraph = nx.DiGraph()
    for node in nodes:
        nid = node.get("node_id") or node.get("id")
        if nid is None:
            continue
        g.add_node(nid, **{k: v for k, v in node.items() if k not in ("node_id", "id")})
    for edge in edges:
        src = edge.get("from")
        dst = edge.get("to")
        etype = edge.get("type", "")
        if src is None or dst is None:
            continue
        g.add_edge(src, dst, type=etype)
    return g


def _classify_nodes(
    graph: nx.DiGraph,
    nodes: tuple[dict[str, Any], ...],
) -> dict[str, str]:
    """Return a mapping ``{node_id: bucket_name}`` for all nodes.

    Priority:
    1. Explicit ``node["kind"]`` if it maps to a known bucket.
    2. Outgoing edge type that maps to a bucket (first match in edge iteration).
    3. Default → ``"core concepts"``.
    """
    classification: dict[str, str] = {}

    # Index raw node dicts by their id for quick lookup.
    raw_by_id: dict[str, dict[str, Any]] = {}
    for node in nodes:
        nid = node.get("node_id") or node.get("id")
        if nid is not None:
            raw_by_id[nid] = node

    for nid in graph.nodes:
        raw = raw_by_id.get(nid, {})
        kind = raw.get("kind", "")
        if kind in _KIND_TO_BUCKET:
            classification[nid] = _KIND_TO_BUCKET[kind]
            continue

        # Infer from outgoing edges.
        bucket: str | None = None
        for _, _dst, data in graph.out_edges(nid, data=True):
            etype = data.get("type", "")
            if etype in EDGE_TYPE_TO_BUCKET:
                bucket = EDGE_TYPE_TO_BUCKET[etype]
                break

        classification[nid] = bucket if bucket is not None else "core concepts"

    return classification


def _topo_sort_with_cycle_break(
    subgraph: nx.DiGraph,
) -> tuple[list[str], list[LearningWarning]]:
    """Return a deterministic topological order for *subgraph*, breaking cycles.

    Cycle-break rule: for each cycle detected, remove the edge whose *target*
    node_id is lexicographically largest (alphabetic-max target).  Emit a
    ``LearningWarning(code="cycle_broken")`` for every removed edge.

    Parameters
    ----------
    subgraph:
        A (potentially cyclic) ``networkx.DiGraph`` that is a copy — may be
        mutated by this function.

    Returns
    -------
    (ordered_ids, warnings)
    """
    warnings: list[LearningWarning] = []

    while True:
        try:
            ordered = list(nx.lexicographical_topological_sort(subgraph))
            return ordered, warnings
        except nx.NetworkXUnfeasible:
            cycles = list(nx.simple_cycles(subgraph))
            if not cycles:
                # Should not happen, but guard defensively.
                break

            # Collect candidate edges to remove: one per cycle.
            # For each cycle, the edge to remove is the one whose target has
            # the lexicographically largest node_id (alphabetic-max target rule).
            edges_to_remove: set[tuple[str, str]] = set()
            for cycle in cycles:
                # Reconstruct cycle edges: (cycle[i], cycle[i+1 mod len])
                cycle_edges = [
                    (cycle[i], cycle[(i + 1) % len(cycle)]) for i in range(len(cycle))
                ]
                # Pick the edge whose target is alphabetically last.
                edge_to_cut = max(cycle_edges, key=lambda e: e[1])
                edges_to_remove.add(edge_to_cut)

            for src, dst in sorted(edges_to_remove):
                if subgraph.has_edge(src, dst):
                    subgraph.remove_edge(src, dst)
                    warnings.append(
                        LearningWarning(
                            code="cycle_broken",
                            severity="warning",
                            source_ref=f"{src}->{dst}",
                            message=(
                                f"Cycle broken: removed edge {src!r} → {dst!r} "
                                f"(alphabetic-max target rule)."
                            ),
                        )
                    )

    # Fallback: if we somehow exit the while-loop, return sorted nodes.
    return sorted(subgraph.nodes), warnings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def order_nodes(
    graph_slice: GraphSlice,
) -> tuple[list[str], list[LearningWarning]]:
    """Produce the default learning order for *graph_slice*.

    Applies the 7-bucket sequence defined in ``LEARNING_BUCKETS`` and uses
    ``networkx.lexicographical_topological_sort`` within each bucket for
    determinism.  Cycles are broken by the alphabetic-max-target rule; each
    broken edge is recorded as a ``LearningWarning(code="cycle_broken")``.

    Parameters
    ----------
    graph_slice:
        An immutable ``GraphSlice`` instance.  This function is **pure** —
        *graph_slice* and its contents are never mutated.

    Returns
    -------
    (ordered_node_ids, warnings)
        ``ordered_node_ids`` is the flat list of node ids in learning order.
        ``warnings`` contains one entry per removed cycle edge (may be empty).
    """
    # Build full graph from immutable slice data (no mutations to graph_slice).
    full_graph = _build_digraph(graph_slice.nodes, graph_slice.edges)

    # Classify every node into a bucket.
    classification = _classify_nodes(full_graph, graph_slice.nodes)

    all_warnings: list[LearningWarning] = []
    ordered_ids: list[str] = []
    assigned: set[str] = set()  # Dedup: first qualifying bucket wins.

    for bucket in LEARNING_BUCKETS:
        # Collect node ids that belong to this bucket and haven't been assigned yet.
        bucket_nodes = [
            nid
            for nid, b in classification.items()
            if b == bucket and nid not in assigned
        ]
        if not bucket_nodes:
            continue

        # Build the induced subgraph for topological ordering.
        # Use a *copy* so we don't mutate the original graph object.
        induced = full_graph.subgraph(bucket_nodes).copy()

        ordered_bucket, warnings = _topo_sort_with_cycle_break(induced)
        all_warnings.extend(warnings)

        for nid in ordered_bucket:
            if nid not in assigned:
                ordered_ids.append(nid)
                assigned.add(nid)

    return ordered_ids, all_warnings


OrderingStrategy = Callable[[GraphSlice], tuple[list[str], list[LearningWarning]]]
"""Callable contract for a mode-specific ordering strategy.

A strategy receives the same :class:`GraphSlice` the compiler would pass to
:func:`order_nodes` and returns ``(ordered_node_ids, warnings)``. Strategies
MUST be pure (no mutation of the input slice) and deterministic (same input
bytes ⇒ same output bytes across runs).

Override contract:
    Mode strategies receive the authoritative default ordering implicitly by
    delegating to :func:`order_nodes`; they may then reorder explicitly. They
    MUST NOT silently replace the default ordering with an unrelated sequence.
"""


def _default_strategy(
    graph_slice: GraphSlice,
) -> tuple[list[str], list[LearningWarning]]:
    """Authoritative default ordering — direct delegate to :func:`order_nodes`."""
    return order_nodes(graph_slice)


def _pedagogical_template_strategy(
    graph_slice: GraphSlice,
) -> tuple[list[str], list[LearningWarning]]:
    """Stub strategy for ``pedagogical_template`` mode.

    Currently identical to :func:`order_nodes`. Override contract: the
    pedagogical intuition → motivation → derivation → algorithm → pitfalls
    template is imposed at section-assembly time, composing on top of the
    default ordering rather than replacing it.
    """
    return order_nodes(graph_slice)


def _derivation_first_strategy(
    graph_slice: GraphSlice,
) -> tuple[list[str], list[LearningWarning]]:
    """Live ``derivation_first`` ordering strategy.

    Override contract: delegates to
    :func:`~akms_learn.modes.derivation_first.derivation_first_strategy`, which
    partitions nodes into derivation-heavy (derivation/prerequisites/concept
    sections) before implementation-heavy nodes, respecting ``requires`` edges
    within each partition.  The default alphabetic-max cycle-break is preserved.
    This strategy now diverges from the default ordering by design.
    """
    from akms_learn.modes.derivation_first import derivation_first_strategy

    return derivation_first_strategy(graph_slice)


def _implementation_first_strategy(
    graph_slice: GraphSlice,
) -> tuple[list[str], list[LearningWarning]]:
    """Live ``implementation_first`` ordering strategy.

    Override contract: delegates to
    :func:`~akms_learn.modes.implementation_first.implementation_first_strategy`,
    which discovers implementation anchors (``implements``-edge targets +
    ``code_mirror`` nodes), walks backward along ``requires`` edges to build
    the concept-prereq section, then emits anchors and any remaining nodes
    (in authoritative default order). Default-policy ordering is
    ``concept_first``; the full :func:`implementation_first_mode` honours
    ``request.policy`` to switch to ``code_first``.
    """
    from akms_learn.modes.implementation_first import implementation_first_strategy

    return implementation_first_strategy(graph_slice)


def _pitfall_driven_strategy(
    graph_slice: GraphSlice,
) -> tuple[list[str], list[LearningWarning]]:
    """``pitfall_driven`` mode — the original default-ordering strategy.

    The canary tests in ``tests/test_ordering.py`` are the authority for
    this strategy's behaviour and must remain byte-stably green. The
    default 7-bucket order from :data:`LEARNING_BUCKETS` already places
    the pitfalls bucket last among the informational buckets; no override
    is layered on top.
    """
    return order_nodes(graph_slice)


def _multi_granularity_strategy(
    graph_slice: GraphSlice,
) -> tuple[list[str], list[LearningWarning]]:
    """Live ``multi_granularity`` ordering strategy.

    Override contract: delegates to
    :func:`~akms_learn.modes.multi_granularity.multi_granularity_strategy`,
    which returns the default-ordered node list unchanged at the strategy
    level (the strategy has no request object, so it cannot apply the
    granularity filter). The full :func:`multi_granularity_mode` reads
    ``request.granularity`` and the convention signals to produce the
    filtered overview / standard / deep_dive variant.
    """
    from akms_learn.modes.multi_granularity import multi_granularity_strategy

    return multi_granularity_strategy(graph_slice)


def _notebook_source_strategy(
    graph_slice: GraphSlice,
) -> tuple[list[str], list[LearningWarning]]:
    """``notebook_source`` ordering strategy.

    Uses the default authoritative node ordering.  The six-section notebook
    layout is imposed at cell-assembly time in
    :func:`~akms_learn.modes.notebook_source.notebook_source_mode`, not at
    the strategy level.  Mirrors the ``pedagogical_template`` pattern: a
    single thin wrapper that calls :func:`order_nodes` directly without an
    intermediate mode-file delegate.
    """
    return order_nodes(graph_slice)


def _adaptive_path_strategy(
    graph_slice: GraphSlice,
) -> tuple[list[str], list[LearningWarning]]:
    """``adaptive_path`` ordering strategy.

    Uses the default authoritative node ordering.  The prerequisite-skip logic
    and learner-profile filtering are applied at compile time in
    :func:`~akms_learn.modes.adaptive_path.adaptive_path_mode`, not at the
    strategy level.  Mirrors the ``notebook_source`` pattern: a single thin
    wrapper that calls :func:`order_nodes` directly without an intermediate
    mode-file delegate.
    """
    return order_nodes(graph_slice)


def _assessment_first_strategy(
    graph_slice: GraphSlice,
) -> tuple[list[str], list[LearningWarning]]:
    """``assessment_first`` ordering strategy.

    Uses the default authoritative node ordering.  Assessment-item generation
    and the four-kind partitioning are applied at compile time in
    :func:`~akms_learn.modes.assessment_first.assessment_first_mode`, not at
    the strategy level.  Mirrors the ``notebook_source`` and ``adaptive_path``
    pattern: a single thin wrapper that calls :func:`order_nodes` directly
    without an intermediate mode-file delegate.
    """
    return order_nodes(graph_slice)


def _llm_expanded_strategy(
    graph_slice: GraphSlice,
) -> tuple[list[str], list[LearningWarning]]:
    """``llm_expanded`` ordering strategy.

    Uses the default authoritative node ordering.  The deterministic-LSP
    capture, source-locked citation validation, and optional LLM expansion
    happen at compile time in
    :func:`~akms_learn.modes.llm_expanded.llm_expanded_mode`, not at the
    strategy level.  Mirrors the ``notebook_source`` / ``adaptive_path`` /
    ``assessment_first`` pattern: a single thin wrapper that calls
    :func:`order_nodes` directly without an intermediate mode-file delegate.
    """
    return order_nodes(graph_slice)


# Registry keyed by mode string. Declared after the strategy functions so the
# callables are defined when the dict is materialised. The key order here is
# fixed for deterministic iteration via :func:`list_strategies`.
_STRATEGY_REGISTRY: dict[str, OrderingStrategy] = {
    "default": _default_strategy,
    "pedagogical_template": _pedagogical_template_strategy,
    "derivation_first": _derivation_first_strategy,
    "implementation_first": _implementation_first_strategy,
    "pitfall_driven": _pitfall_driven_strategy,
    "multi_granularity": _multi_granularity_strategy,
    "notebook_source": _notebook_source_strategy,
    "adaptive_path": _adaptive_path_strategy,
    "assessment_first": _assessment_first_strategy,
    "llm_expanded": _llm_expanded_strategy,
}

STRATEGY_KEYS: tuple[str, ...] = tuple(_STRATEGY_REGISTRY.keys())
"""The registered mode keys, in registry declaration order."""


def get_strategy(mode: str) -> OrderingStrategy:
    """Look up an ordering strategy by mode key.

    Parameters
    ----------
    mode:
        One of the keys in :data:`STRATEGY_KEYS`.

    Returns
    -------
    OrderingStrategy
        The callable registered for *mode*.

    Raises
    ------
    ValueError
        If *mode* is not a registered key. The message lists the available
        keys (sorted) so callers can recover. No silent fallback to
        ``"default"`` ever occurs — mode overrides must be explicit so a
        typo never silently compiles with the wrong ordering.
    """
    if mode not in _STRATEGY_REGISTRY:
        available = ", ".join(sorted(_STRATEGY_REGISTRY.keys()))
        raise ValueError(
            f"Unknown ordering strategy {mode!r}. "
            f"Registered strategies: [{available}]. "
            f"No silent fallback to 'default' is permitted."
        )
    return _STRATEGY_REGISTRY[mode]


def list_strategies() -> tuple[str, ...]:
    """Return the registered strategy keys in declaration order."""
    return STRATEGY_KEYS
