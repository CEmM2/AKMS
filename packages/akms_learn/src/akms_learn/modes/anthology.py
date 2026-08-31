"""Mode 2: node anthology — ordered mini-reader compiled from node sections.

Five sub-tasks (plan §14, L253-L259):
  1. Compile ordered node summaries/full sections into an anthology view.
  2. Respect ``reading_priority`` when present (lower = earlier; missing = +infinity).
  3. Include confidence and status badges in Markdown.
  4. Warn on missing teaching-oriented sections.
  5. Preserve source paths and section line ranges when available.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel

from akms_learn.graph_import import GraphSlice
from akms_learn.models import LearningWarning
from akms_learn.sections import SectionView

__all__ = [
    "TEACHING_SECTIONS",
    "AnthologyEntry",
    "anthology_mode",
]

# ---------------------------------------------------------------------------
# Teaching sections — the four "teaching-oriented" sections for anthology mode.
# Canonical spellings match APPROVED_SECTIONS verbatim; case-insensitive
# matching happens inside sections.py, not here.
# ---------------------------------------------------------------------------

TEACHING_SECTIONS: tuple[str, ...] = (
    "Learning goal",
    "Main path",
    "Implementation",
    "Self-check",
)


# ---------------------------------------------------------------------------
# AnthologyEntry
# ---------------------------------------------------------------------------


class AnthologyEntry(BaseModel):
    """Per-node anthology record built by :func:`anthology_mode`.

    Carries all rendering-relevant data for one node: badges, present teaching
    sections, and provenance (source path + line range).
    """

    node_id: str
    title: str | None = None
    confidence_badge: str
    status_badge: str
    teaching_sections: dict[str, dict[str, Any] | None]
    source_path: str
    line_range: tuple[int, int]


# ---------------------------------------------------------------------------
# anthology_mode
# ---------------------------------------------------------------------------


def anthology_mode(
    graph_slice: GraphSlice,
    ordered_nodes: list[str],
    sections_by_node: dict[str, dict[str, SectionView | None]],
    request: Any = None,
) -> tuple[list[AnthologyEntry], list[LearningWarning]]:
    """Build the node anthology view for Mode 2.

    Parameters
    ----------
    graph_slice:
        Frozen ``GraphSlice`` containing the node dicts.  Each node dict may
        carry ``reading_priority`` (numeric), ``confidence`` (float),
        ``status`` (str), ``title`` (str), and ``source_path`` (str).
    ordered_nodes:
        Sequence of node IDs in the compiler's default ordering.  Used as
        the tie-breaker when two nodes share the same ``reading_priority``.
    sections_by_node:
        Mapping from ``node_id`` to the section dict produced by
        :func:`~akms_learn.sections.extract_sections`.  Values are
        ``dict[str, SectionView | None]``; missing keys are treated as
        ``None``.
    request:
        Unused — reserved for future per-request filtering.  Accepted to
        keep the mode signature forward-compatible.

    Returns
    -------
    entries:
        :class:`AnthologyEntry` list in reading-priority order (lower
        numeric value first, missing = +infinity, ties broken by
        ``ordered_nodes`` position).
    warnings:
        :class:`~akms_learn.models.LearningWarning` list — one
        ``code="missing_teaching_section"`` entry per node × missing
        teaching section.

    Notes
    -----
    * Pure: no input is mutated.
    * Deterministic: same inputs always produce byte-identical output.
    """
    # ------------------------------------------------------------------
    # Step 1: build (node_id, reading_priority, original_index) triples
    # and sort by (reading_priority, original_index) — lower first.
    # ------------------------------------------------------------------
    node_index: dict[str, int] = {nid: i for i, nid in enumerate(ordered_nodes)}

    # Index nodes by node_id for O(1) lookup.
    nodes_by_id: dict[str, dict[str, Any]] = {
        n["node_id"]: n for n in graph_slice.nodes if "node_id" in n
    }

    # Build sort key list — only process node_ids that appear in ordered_nodes.
    # Non-numeric ``reading_priority`` is coerced to +infinity AND surfaces a
    # ``LearningWarning(code="invalid_reading_priority")`` so malformed graph
    # data isn't silently masked.
    sort_keys: list[tuple[float, int, str]] = []
    invalid_priority_records: list[tuple[str, Any]] = []
    for node_id in ordered_nodes:
        node = nodes_by_id.get(node_id, {})
        raw_priority = node.get("reading_priority")
        if raw_priority is None:
            priority: float = math.inf
        else:
            try:
                priority = float(raw_priority)
            except (TypeError, ValueError):
                priority = math.inf
                invalid_priority_records.append((node_id, raw_priority))
        sort_keys.append((priority, node_index[node_id], node_id))

    sort_keys.sort(key=lambda t: (t[0], t[1]))

    # ------------------------------------------------------------------
    # Steps 2-5: for each node in sorted order, build the entry and
    # accumulate warnings.
    # ------------------------------------------------------------------
    entries: list[AnthologyEntry] = []
    warnings: list[LearningWarning] = []

    # Emit invalid-priority warnings up-front (sorted by node_id for
    # deterministic warning ordering across runs).
    for nid, raw_value in sorted(invalid_priority_records, key=lambda t: t[0]):
        warnings.append(
            LearningWarning(
                severity="warning",
                code="invalid_reading_priority",
                source_ref=nid,
                message=(
                    f"Node {nid!r} has non-numeric reading_priority "
                    f"{raw_value!r}; coerced to +infinity (sorts last)."
                ),
            )
        )

    for _priority, _idx, node_id in sort_keys:
        node = nodes_by_id.get(node_id, {})

        # Step 2: gather only teaching sections from sections_by_node.
        node_sections: dict[str, SectionView | None] = sections_by_node.get(node_id, {})
        teaching_section_views: dict[str, SectionView | None] = {
            sec: node_sections.get(sec)  # None if key absent
            for sec in TEACHING_SECTIONS
        }

        # Step 3: build badges.
        raw_conf = node.get("confidence")
        confidence_badge = (
            f"confidence: {raw_conf}" if raw_conf is not None else "confidence: n/a"
        )

        raw_status = node.get("status")
        status_badge = (
            f"status: {raw_status}" if raw_status is not None else "status: n/a"
        )

        # Step 4: emit one warning per missing teaching section.
        for section_name in TEACHING_SECTIONS:
            if teaching_section_views.get(section_name) is None:
                warnings.append(
                    LearningWarning(
                        severity="warning",
                        code="missing_teaching_section",
                        source_ref=node_id,
                        message=(
                            f"Node {node_id!r} missing teaching section {section_name!r}."
                        ),
                    )
                )

        # Step 5: build AnthologyEntry — provenance from first non-None
        # teaching section.
        source_path: str = node.get("source_path", "")
        line_range: tuple[int, int] = (0, 0)
        for sec in TEACHING_SECTIONS:
            sv = teaching_section_views.get(sec)
            if sv is not None:
                line_range = sv.line_range
                break

        # Serialise teaching sections: SectionView → dict | None.
        serialised_sections: dict[str, dict[str, Any] | None] = {
            sec: (sv.model_dump() if sv is not None else None)
            for sec, sv in teaching_section_views.items()
        }

        entries.append(
            AnthologyEntry(
                node_id=node_id,
                title=node.get("title"),
                confidence_badge=confidence_badge,
                status_badge=status_badge,
                teaching_sections=serialised_sections,
                source_path=source_path,
                line_range=line_range,
            )
        )

    return entries, warnings
