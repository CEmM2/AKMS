"""Mode: pedagogical_template — mini-textbook layout.

Generates a 12-section mini-textbook structure from an AKMS v2 GraphSlice.
The 12 sections in canonical order:

    1. Learning goal
    2. Prerequisite map
    3. Intuition
    4. Formal statement
    5. Derivation / explanation
    6. Implementation notes
    7. Worked example
    8. Common pitfalls
    9. Self-check
    10. Exercises
    11. References
    12. Provenance

Design decisions
----------------
* **No v2.1 metadata required** — works on plain AKMS v2 nodes using the
  node-level section extractor (:func:`~akms_learn.section_extraction.extract_sections_from_node`).
* **Missing sections → warnings, not invention** — every section that cannot
  be populated from source nodes emits exactly one
  ``LearningWarning(code="pedagogical_section_missing")`` with the
  ``source_ref`` set to the primary source node id for that section slot.
  Placeholder text ``"[No content available]"`` is used instead.
* **Optional v2.1 metadata** — if any node carries one or more of the fields
  ``learning_objectives``, ``difficulty``, ``estimated_minutes``,
  ``preferred_learning_sections`` those values are surfaced in the returned
  dict under ``v21_metadata``.  Their absence never triggers a warning.
* **Ordering** — ``pedagogical_template`` strategy in the ordering registry
  currently delegates to :func:`~akms_learn.ordering.order_nodes`.
  This mode therefore relies on the incoming ``ordered_nodes`` list
  and does all layout work here rather than overriding node order —
  the "keep all layout work in the mode compiler" design branch.
* **Pure function** — never mutates inputs; deterministic on the same inputs.
* **Imports at module top** — no mid-module imports.

Slot → approved-heading map
---------------------------
AKMS v2 publishes 10 approved section headings (see
:data:`~akms_learn.section_extraction.APPROVED_HEADINGS`). The pedagogical
template needs 12 slots, so two of the heading names are reused as the
fallback source for the slots that have no v2 analogue:

* ``concept`` feeds both **Intuition** and **Formal statement**.
* ``assessment`` feeds both **Self-check** and **Exercises**.

This is deliberate. v2.1 will introduce dedicated headings (``intuition``,
``formal_statement``, ``self_check``, ``exercises``) and the duplication
goes away. Until then the mapping below preserves the 12-slot layout
without inventing content. When a node carries the same heading content
the two slots fed by it will render identical text; that is reported by
``pedagogical_section_missing`` only when the heading itself is absent
from every ordered node.

Warning codes
-------------
``pedagogical_section_missing``
    Emitted once per section slot that has no populated content.
    ``source_ref`` is the primary source node id (first node in
    ``ordered_nodes``, or ``"<unknown>"`` if the slice is empty).
"""

from __future__ import annotations

from typing import Any, Optional

from akms_learn.graph_import import GraphSlice
from akms_learn.models import LearningWarning
from akms_learn.requests import LearningRequest
from akms_learn.section_extraction import (
    ExtractedSection,
    extract_sections_from_node,
)

__all__ = [
    "PEDAGOGICAL_SECTIONS",
    "SECTION_PLACEHOLDER",
    "PedagogicalTemplateResult",
    "pedagogical_template_mode",
]

# ---------------------------------------------------------------------------
# 12-section canonical order — immutable.
# DO NOT reorder; downstream template rendering depends on this exact sequence.
# ---------------------------------------------------------------------------

PEDAGOGICAL_SECTIONS: tuple[str, ...] = (
    "Learning goal",
    "Prerequisite map",
    "Intuition",
    "Formal statement",
    "Derivation / explanation",
    "Implementation notes",
    "Worked example",
    "Common pitfalls",
    "Self-check",
    "Exercises",
    "References",
    "Provenance",
)

# Placeholder inserted into sections that have no source content.
SECTION_PLACEHOLDER: str = "[No content available]"

# ---------------------------------------------------------------------------
# Mapping: pedagogical section name → approved_heading names to search.
# Each entry is a tuple of approved headings (and common aliases) to try, in
# priority order.  The extractor returns ExtractedSection with
# ``normalized_name`` drawn from APPROVED_HEADINGS; we match on both the
# normalized name and common spelling variants so fixture-level data is found.
# ---------------------------------------------------------------------------

_SECTION_TO_HEADINGS: dict[str, tuple[str, ...]] = {
    "Learning goal": ("motivation",),
    "Prerequisite map": ("prerequisites",),
    "Intuition": ("concept",),
    "Formal statement": ("concept", "derivation"),
    "Derivation / explanation": ("derivation",),
    "Implementation notes": ("implementation",),
    "Worked example": ("worked_example",),
    "Common pitfalls": ("pitfalls",),
    "Self-check": ("assessment",),
    "Exercises": ("assessment",),
    "References": ("references",),
    "Provenance": (),  # always built from graph provenance
}

# Optional v2.1 metadata field names (consumed if present, ignored otherwise).
_V21_OPTIONAL_FIELDS: tuple[str, ...] = (
    "learning_objectives",
    "difficulty",
    "estimated_minutes",
    "preferred_learning_sections",
)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class PedagogicalTemplateResult:
    """Structured result from :func:`pedagogical_template_mode`.

    Attributes
    ----------
    sections:
        Ordered dict mapping each of the 12 pedagogical section names to
        their populated content string (may be ``SECTION_PLACEHOLDER``).
    source_node_ids:
        Sorted list of all node ids that contributed content to the packet.
    edge_ids:
        Sorted list of all edge ids present in the graph slice.
    v21_metadata:
        Dict of optional v2.1 metadata fields collected from nodes; empty
        when no node carries any v2.1 field.
    warnings:
        List of :class:`~akms_learn.models.LearningWarning` instances.
    """

    __slots__ = ("sections", "source_node_ids", "edge_ids", "v21_metadata", "warnings")

    def __init__(
        self,
        sections: dict[str, str],
        source_node_ids: list[str],
        edge_ids: list[str],
        v21_metadata: dict[str, Any],
        warnings: list[LearningWarning],
    ) -> None:
        self.sections = sections
        self.source_node_ids = source_node_ids
        self.edge_ids = edge_ids
        self.v21_metadata = v21_metadata
        self.warnings = warnings


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _collect_sections_by_node(
    ordered_nodes: list[str],
    nodes_by_id: dict[str, dict[str, Any]],
) -> dict[str, list[ExtractedSection]]:
    """Extract sections for every ordered node, in order."""
    result: dict[str, list[ExtractedSection]] = {}
    for nid in ordered_nodes:
        node = nodes_by_id.get(nid)
        if node is None:
            continue
        result[nid] = extract_sections_from_node(node)
    return result


def _find_content_for_slot(
    slot: str,
    ordered_nodes: list[str],
    sections_by_node: dict[str, list[ExtractedSection]],
) -> tuple[str, Optional[str]]:
    """Return (content, source_node_id) for a pedagogical section slot.

    Searches nodes in ``ordered_nodes`` order.  Returns the content from the
    first node that carries a matching approved heading, or
    ``(SECTION_PLACEHOLDER, None)`` if nothing matches.

    ``Provenance`` is handled separately (never populated here).
    """
    if slot == "Provenance":
        # Provenance is built from graph metadata, not node content.
        return SECTION_PLACEHOLDER, None

    target_headings = _SECTION_TO_HEADINGS.get(slot, ())
    if not target_headings:
        return SECTION_PLACEHOLDER, None

    # Walk nodes in ordering order, pick first hit.
    for nid in ordered_nodes:
        extracted_list = sections_by_node.get(nid, [])
        for section in extracted_list:
            if section.normalized_name in target_headings:
                return section.content, nid

    return SECTION_PLACEHOLDER, None


def _collect_v21_metadata(
    ordered_nodes: list[str],
    nodes_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Collect optional v2.1 metadata from nodes, merging across all nodes.

    Later nodes overwrite earlier ones for duplicate keys, but in practice
    a well-formed graph carries these fields on at most one node.
    Returns an empty dict when no v2.1 fields are present anywhere.
    """
    collected: dict[str, Any] = {}
    for nid in ordered_nodes:
        node = nodes_by_id.get(nid) or {}
        for field in _V21_OPTIONAL_FIELDS:
            value = node.get(field)
            if value is not None:
                collected[field] = value
    return collected


def _build_provenance_text(
    ordered_nodes: list[str],
    graph_slice: GraphSlice,
) -> str:
    """Build the Provenance section text from node ids and edge ids."""
    node_ids_str = ", ".join(ordered_nodes) if ordered_nodes else "(none)"
    edge_ids = sorted(
        str(e.get("edge_id", "")) for e in graph_slice.edges if e.get("edge_id")
    )
    edge_ids_str = ", ".join(edge_ids) if edge_ids else "(none)"
    return f"Node ids: {node_ids_str}\nEdge ids: {edge_ids_str}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def pedagogical_template_mode(
    graph_slice: GraphSlice,
    ordered_nodes: list[str],
    request: LearningRequest,
) -> tuple["PedagogicalTemplateResult", list[LearningWarning]]:
    """Build the pedagogical_template mode view.

    Pure function — never mutates ``graph_slice``, ``ordered_nodes``, or
    ``request``.

    Parameters
    ----------
    graph_slice:
        Immutable :class:`~akms_learn.graph_import.GraphSlice` from the
        compiler pipeline.
    ordered_nodes:
        Node id list in learning order (from
        :func:`~akms_learn.ordering.order_nodes` or the pedagogical_template
        strategy).
    request:
        The validated :class:`~akms_learn.requests.LearningRequest`.
        ``request.goal`` and ``request.topic`` contribute to the Learning
        goal slot when no node-level motivation section is available.

    Returns
    -------
    (result, warnings)
        ``result`` is a :class:`PedagogicalTemplateResult`.
        ``warnings`` is a list of :class:`~akms_learn.models.LearningWarning`
        (same list as ``result.warnings`` — provided at top level for
        compatibility with the mode-dispatcher pattern).
    """
    # ------------------------------------------------------------------
    # Index nodes by id (read-only copies).
    # ------------------------------------------------------------------
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for raw in graph_slice.nodes:
        nid = raw.get("node_id")
        if nid is not None:
            nodes_by_id[nid] = dict(raw)  # shallow copy — no mutation to slice

    # Primary source ref for warnings: first ordered node, or "<unknown>".
    primary_source_ref: str = ordered_nodes[0] if ordered_nodes else "<unknown>"

    # ------------------------------------------------------------------
    # Extract approved sections from every node in ordered_nodes.
    # ------------------------------------------------------------------
    extracted_by_node = _collect_sections_by_node(ordered_nodes, nodes_by_id)

    # ------------------------------------------------------------------
    # Build each of the 12 pedagogical section slots.
    # ------------------------------------------------------------------
    section_contents: dict[str, str] = {}
    warnings: list[LearningWarning] = []

    for slot in PEDAGOGICAL_SECTIONS:
        if slot == "Provenance":
            # Provenance is always built from graph metadata — never missing.
            section_contents[slot] = _build_provenance_text(ordered_nodes, graph_slice)
            continue

        # Special case: Learning goal — prefer request.goal / topic fallback
        # before section extractor so the request intent is always honoured.
        if slot == "Learning goal":
            goal_str = (getattr(request, "goal", "") or "").strip()
            topic_str = (getattr(request, "topic", "") or "").strip()
            if goal_str:
                section_contents[slot] = goal_str
                continue
            if topic_str:
                section_contents[slot] = f"Understand {topic_str}"
                continue
            # Fall through to section extractor below.

        content, source_nid = _find_content_for_slot(
            slot, ordered_nodes, extracted_by_node
        )

        if content == SECTION_PLACEHOLDER:
            # Emit one warning per missing section.
            warnings.append(
                LearningWarning(
                    severity="warning",
                    code="pedagogical_section_missing",
                    source_ref=source_nid or primary_source_ref,
                    message=(
                        f"Pedagogical section {slot!r} has no content from "
                        f"source nodes; placeholder inserted."
                    ),
                )
            )

        section_contents[slot] = content

    # ------------------------------------------------------------------
    # Collect optional v2.1 metadata (consumed if present, silent if absent).
    # ------------------------------------------------------------------
    v21_metadata = _collect_v21_metadata(ordered_nodes, nodes_by_id)

    # ------------------------------------------------------------------
    # Provenance lists.
    # ------------------------------------------------------------------
    source_node_ids = sorted(nid for nid in ordered_nodes if nid in nodes_by_id)
    edge_ids = sorted(
        str(e.get("edge_id", "")) for e in graph_slice.edges if e.get("edge_id")
    )

    result = PedagogicalTemplateResult(
        sections=section_contents,
        source_node_ids=source_node_ids,
        edge_ids=edge_ids,
        v21_metadata=v21_metadata,
        warnings=warnings,
    )

    return result, warnings
