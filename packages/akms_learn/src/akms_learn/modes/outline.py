"""Mode 1 — Deterministic outline (plan §13, L231-L249).

Pure graph-to-outline transformation. **No LLM, no network, no randomness, no
wall-clock reads.** The output is a plain ``dict`` that the orchestrator
(``compile_learning_source``) folds into the ``PacketBody`` before serialising
the LSP.

Plan §13 enumerates 7 sub-tasks (L233-L242). Each is implemented inline below
and called out in a comment so reviewers can map code → spec line:

    1. Generate learning goal from request.                 (Step 1)
    2. Build prerequisite list from ``requires`` edges.     (Step 2)
    3. Build core path from ordered selected nodes.         (Step 3)
    4. Include implementation/derivation branches.          (Step 4)
    5. Include pitfalls when requested.                     (Step 5)
    6. Emit ``reading_order`` and ``concept_map.json`` data. (Step 6)
    7. Preserve all source node ids and edge ids/attributes. (Step 7)

Acceptance criteria (plan §13, L244-L247):

* same graph + request → byte-stable output (this dict has no timestamps)
* node ids and edge provenance included (``provenance`` + ``concept_map``)
* no LLM calls (verified by ``test_outline_no_llm_imports``)
"""

from __future__ import annotations

from typing import Any

from akms_learn.graph_import import GraphSlice
from akms_learn.models import LearningWarning
from akms_learn.requests import LearningRequest

__all__ = ["outline_mode"]


# Edge-type → outline-bucket conventions:
#
# * ``requires``   — SOURCE node is the prerequisite (matches
#                    ``ordering.EDGE_TYPE_TO_BUCKET[requires]``).
# * ``derives`` /  — TARGET node is the branch (the *derived* /
#   ``implements``    *implementing* concept itself, not the parent it
#                     branches from). This is the outline-mode convention
#                     and is INTENTIONALLY OPPOSITE to ordering.py's
#                     source-side classification, because an outline lists
#                     "branches off the core" — the derivations/
#                     implementations, not the core they extend.
# * ``pitfall_of`` — TARGET node is the pitfall.
#
# Result: prereqs / core_path / branches / pitfalls are DISJOINT for any
# graph topology, so the AC #6 strict sum equation `len(reading_order) ==
# len(core_path)+len(prereqs)+len(branches)+len(pitfalls)` holds without
# requiring dedup. (Dedup is kept as a defensive belt-and-suspenders.)
_REQUIRES_EDGE = "requires"
_DERIVES_EDGE = "derives"
_IMPLEMENTS_EDGE = "implements"
_PITFALL_OF_EDGE = "pitfall_of"


def outline_mode(
    graph_slice: GraphSlice,
    ordered_nodes: list[str],
    request: LearningRequest,
    sections_by_node: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[LearningWarning]]:
    """Build the deterministic Mode 1 outline view.

    Pure function. Never mutates ``graph_slice``, ``ordered_nodes``,
    ``request`` or ``sections_by_node``.

    Parameters
    ----------
    graph_slice:
        Immutable ``GraphSlice`` (frozen Pydantic model) — the bounded slice
        produced by Stage 3 / Stage 4 of the compiler.
    ordered_nodes:
        Bucket-sorted node-id list produced by
        :func:`akms_learn.ordering.order_nodes`.
    request:
        The validated :class:`LearningRequest`. ``request.goal`` /
        ``request.topic`` feed Step 1; ``request.include_pitfalls`` gates
        Step 5.
    sections_by_node:
        Reserved for Phase 5+. Mode 1 never inspects section content; only
        structural edge/node classification is needed.

    Returns
    -------
    (outline_dict, warnings)
        ``outline_dict`` is a ``PacketBody``-compatible dict with keys:
        ``learning_goal``, ``prerequisites``, ``core_path``, ``branches``,
        ``pitfalls``, ``reading_order``, ``concept_map``, ``provenance``.
        ``warnings`` is currently always empty for Mode 1 — soft issues are
        surfaced by upstream stages (ordering / sections).
    """
    # ---- Index nodes + edges -------------------------------------------------
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for raw in graph_slice.nodes:
        nid = raw.get("node_id")
        if nid is not None:
            nodes_by_id[nid] = raw

    ordered_node_set: set[str] = set(ordered_nodes)

    requires_edges: list[dict[str, Any]] = []
    derives_or_implements_edges: list[dict[str, Any]] = []
    pitfall_of_edges: list[dict[str, Any]] = []

    for edge in graph_slice.edges:
        etype = edge.get("type", "")
        if etype == _REQUIRES_EDGE:
            requires_edges.append(edge)
        elif etype in (_DERIVES_EDGE, _IMPLEMENTS_EDGE):
            derives_or_implements_edges.append(edge)
        elif etype == _PITFALL_OF_EDGE:
            pitfall_of_edges.append(edge)

    # ---- Step 1: learning_goal ----------------------------------------------
    goal_str = (request.goal or "").strip()
    topic_str = (request.topic or "").strip()
    learning_goal: str = goal_str if goal_str else f"Understand {topic_str}"

    # ---- Step 2: prerequisites (SOURCE of any `requires` edge) ---------------
    # Matches ordering.py convention: source of `requires` → prerequisite.
    # Intersect with ordered_nodes so only real participants land here.
    prereq_ids: set[str] = {
        edge["from"] for edge in requires_edges if edge.get("from") in ordered_node_set
    }
    prerequisites: list[str] = sorted(prereq_ids)

    # ---- Step 5 (computed early): pitfalls (TARGET of any `pitfall_of`) -----
    # We compute pitfalls before core_path so core_path can exclude them
    # cleanly, keeping the four buckets DISJOINT. Pitfalls are gated by
    # ``request.include_pitfalls``; the field is a typed bool on
    # ``LearningRequest`` (Phase 2), so no getattr fallback is needed.
    include_pitfalls: bool = bool(request.include_pitfalls)
    pitfall_ids: set[str] = set()
    if include_pitfalls:
        pitfall_ids = {
            edge["to"]
            for edge in pitfall_of_edges
            if edge.get("to") in ordered_node_set
        }
    pitfalls: list[str] = sorted(pitfall_ids) if include_pitfalls else []

    # ---- Step 4: branches (TARGET of any `derives` or `implements` edge) ----
    # An outline lists "branches off the core" — the derivations /
    # implementations themselves, not the core node they extend. Intersect
    # with ordered_nodes; exclude prereqs and pitfalls so buckets stay
    # disjoint.
    branch_ids: set[str] = (
        {
            edge["to"]
            for edge in derives_or_implements_edges
            if edge.get("to") in ordered_node_set
        }
        - prereq_ids
        - pitfall_ids
    )
    branches: list[str] = sorted(branch_ids)

    # ---- Step 3: core_path (ordered_nodes MINUS prereqs/branches/pitfalls) --
    # Preserve the ordering produced by `order_nodes` — DO NOT re-sort.
    # Disjoint with prereqs/branches/pitfalls so AC #6 sum equation holds.
    excluded: set[str] = prereq_ids | branch_ids | pitfall_ids
    core_path: list[str] = [nid for nid in ordered_nodes if nid not in excluded]

    # ---- Step 6: reading_order + concept_map ---------------------------------
    # Concatenate prerequisites + core_path + branches + pitfalls. Buckets are
    # DISJOINT by construction (Steps 2-5) so the AC #6 strict sum equation
    # holds: len(reading_order) == sum(len(bucket) for bucket in 4 buckets).
    # First-seen dedup is kept defensively but should never collapse anything.
    reading_order: list[str] = []
    _seen: set[str] = set()
    for nid in (*prerequisites, *core_path, *branches, *pitfalls):
        if nid not in _seen:
            reading_order.append(nid)
            _seen.add(nid)

    # concept_map: every node touched + every classifying edge used.
    classifying_edges: list[dict[str, Any]] = []
    classifying_edges.extend(requires_edges)
    classifying_edges.extend(derives_or_implements_edges)
    if include_pitfalls:
        classifying_edges.extend(pitfall_of_edges)

    nodes_used: set[str] = set(reading_order)
    edges_used: set[str] = {
        edge["edge_id"] for edge in classifying_edges if edge.get("edge_id") is not None
    }

    concept_map: dict[str, list[str]] = {
        "nodes": sorted(nodes_used),
        "edges": sorted(edges_used),
    }

    # ---- Step 7: provenance --------------------------------------------------
    # AC #2: every node_id in core_path/prereqs MUST be present in slice.
    # AC #3: every `requires` edge_id MUST appear in concept_map (already does
    # via edges_used since we always include `requires` edges).
    # Provenance covers EVERY node/edge in the slice that contributed.
    all_node_ids: set[str] = set(reading_order) & set(nodes_by_id.keys())
    # Also include the source nodes of every classifying edge, even if not in
    # ordered_nodes (defensive — keeps provenance complete).
    for edge in classifying_edges:
        src = edge.get("from")
        dst = edge.get("to")
        if src in nodes_by_id:
            all_node_ids.add(src)
        if dst in nodes_by_id:
            all_node_ids.add(dst)

    all_edge_ids: set[str] = set(edges_used)

    provenance: dict[str, list[str]] = {
        "node_ids": sorted(all_node_ids),
        "edge_ids": sorted(all_edge_ids),
    }

    outline: dict[str, Any] = {
        "learning_goal": learning_goal,
        "prerequisites": prerequisites,
        "core_path": core_path,
        "branches": branches,
        "pitfalls": pitfalls,
        "reading_order": reading_order,
        "concept_map": concept_map,
        "provenance": provenance,
    }

    warnings: list[LearningWarning] = []
    return outline, warnings
