"""Mode 8 — Pitfall-driven learning source (plan §15, L265-L271).

Plan §15 enumerates 5 sub-tasks implemented below:

    1. Detect pitfall edges in selected graph/slice.            (Step 1)
    2. Build failure-mode sections: symptom, cause,             (Step 2)
       correction, diagnostics.
    3. Link each pitfall to source node ids and session refs    (Step 3)
       when available.
    4. Include corrective concepts through ``requires`` or      (Step 4)
       adjacent edges.
    5. Add warnings when pitfall edges lack enough              (Step 5)
       explanatory content.

**PitfallView field shape decision**
``PitfallView`` (models.py) carries six fields: ``pitfall_id``,
``source_node_id``, ``source_path``, ``line_range``, ``message``,
``severity``.  It has NO explicit slots for the four structured fields
(symptom/cause/correction/diagnostics) or for ``corrective_concepts``.
Since ``ConfigDict()`` without ``extra="allow"`` silently drops unknown
kwargs, we pack all derived data into ``message`` as a deterministic
newline-delimited string of the form::

    symptom: <text>
    cause: <text>
    correction: <text>
    diagnostics: <text>
    corrective_concepts: <id1>,<id2>,...
    session_refs: <ref1>,<ref2>,...

Tests should inspect ``message`` lines to verify structured content.
``pitfall_id`` carries the originating ``edge_id``.
``source_node_id`` carries the TARGET node id (the node being warned about).
``source_path`` carries the target node's ``source_path`` attribute.

**Determinism contract**: output order equals the deterministic edge sort
``(edge_id, from_node, to_node)``.  All iterables are sorted before use.
No uuid/random/datetime.now() calls anywhere in this module.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from akms_learn.graph_import import GraphSlice
from akms_learn.models import LearningWarning, PitfallView

__all__ = [
    "PITFALL_EDGE_TYPES",
    "STRUCTURED_FIELDS",
    "pitfall_mode",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PITFALL_EDGE_TYPES: frozenset[str] = frozenset({"pitfall_of", "pitfall"})

STRUCTURED_FIELDS: tuple[str, ...] = ("symptom", "cause", "correction", "diagnostics")

# Regex patterns for inline label styles: ``**Symptom:**`` or ``- Symptom:``
_INLINE_BOLD_RE = re.compile(
    r"\*\*(?P<key>Symptom|Cause|Correction|Diagnostics):\*\*\s*(?P<val>[^\n*]+)",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(
    r"^[ \t]*-[ \t]+(?P<key>Symptom|Cause|Correction|Diagnostics):[ \t]*(?P<val>.+)$",
    re.IGNORECASE | re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_pitfalls_section(content: str) -> dict[str, str]:
    """Parse structured sub-fields from a node's ``Pitfalls`` section content.

    Recognises three label styles (permissive, case-insensitive):

    * ``### Symptom`` ATX heading → content until next ``###`` heading.
    * ``**Symptom:**`` inline bold label → content on the same line.
    * ``- Symptom: ...`` bullet item.

    Returns a dict with exactly the four canonical keys in lower-case
    (``symptom``, ``cause``, ``correction``, ``diagnostics``).
    Missing sub-fields default to empty string ``""``.

    Never raises.  Malformed content is treated as empty.
    """
    result: dict[str, str] = {k: "" for k in STRUCTURED_FIELDS}

    # ---- Pass 1: ATX sub-headings (### Symptom … ### Cause …) ----------------
    # Split on any ### (or deeper) heading line, case-insensitive.
    heading_split_re = re.compile(r"^[ \t]{0,3}#{3,}[ \t]+(.+?)[ \t]*$", re.MULTILINE)
    parts = heading_split_re.split(content)
    # parts alternates: [pre-content, heading1, content1, heading2, content2, …]
    # index 0 = content before first heading; 1 = heading1; 2 = content1; etc.
    if len(parts) > 1:
        i = 1
        while i < len(parts) - 1:
            key_candidate = parts[i].strip().lower()
            section_body = parts[i + 1].strip() if i + 1 < len(parts) else ""
            if key_candidate in result:
                result[key_candidate] = section_body
            i += 2

    # ---- Pass 2: inline ``**Symptom:**`` bold labels (fill still-empty keys) --
    for m in _INLINE_BOLD_RE.finditer(content):
        key = m.group("key").lower()
        val = m.group("val").strip()
        if key in result and not result[key]:
            result[key] = val

    # ---- Pass 3: ``- Symptom: …`` bullet items (fill still-empty keys) --------
    for m in _BULLET_RE.finditer(content):
        key = m.group("key").lower()
        val = m.group("val").strip()
        if key in result and not result[key]:
            result[key] = val

    return result


def _build_message(
    structured: dict[str, str],
    corrective_concepts: list[str],
    session_refs: list[str],
) -> str:
    """Encode structured fields + lists into the ``PitfallView.message`` string.

    Format is newline-delimited ``key: value`` pairs, deterministic.
    """
    lines: list[str] = []
    for field in STRUCTURED_FIELDS:
        lines.append(f"{field}: {structured.get(field, '')}")
    lines.append(f"corrective_concepts: {','.join(corrective_concepts)}")
    lines.append(f"session_refs: {','.join(str(r) for r in session_refs)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def pitfall_mode(
    graph_slice: GraphSlice,
    sections_by_node: dict[str, Any],
    request: Optional[Any] = None,
) -> tuple[list[PitfallView], list[LearningWarning]]:
    """Build the Mode 8 pitfall-driven view.

    Pure function — never mutates inputs.

    Parameters
    ----------
    graph_slice:
        Immutable ``GraphSlice`` produced by the compiler pipeline.
    sections_by_node:
        Mapping ``node_id -> {section_name -> SectionView | None}``.
        Pass an empty dict when section extraction has not been performed.
    request:
        Optional ``LearningRequest``; reserved for future gate filtering.
        Not used in Phase 4.

    Returns
    -------
    (pitfall_views, warnings)
        ``pitfall_views`` is sorted by ``(edge_id, from_node, to_node)``
        for determinism.
        ``warnings`` contains one ``LearningWarning(code='thin_pitfall_content')``
        per pitfall edge where ANY of the four structured fields is empty.
    """
    # ---- Index nodes by id ---------------------------------------------------
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for raw in graph_slice.nodes:
        nid = raw.get("node_id") or raw.get("id")
        if nid is not None:
            nodes_by_id[nid] = raw

    # ---- Step 1: Collect pitfall edges, sort deterministically ---------------
    pitfall_edges: list[dict[str, Any]] = [
        edge
        for edge in graph_slice.edges
        if edge.get("type") in PITFALL_EDGE_TYPES
    ]
    pitfall_edges.sort(
        key=lambda e: (
            e.get("edge_id", ""),
            e.get("from", ""),
            e.get("to", ""),
        )
    )

    pitfall_views: list[PitfallView] = []
    warnings: list[LearningWarning] = []

    for edge in pitfall_edges:
        edge_id: str = edge.get("edge_id", "")
        target_node_id: str = edge.get("to", "")
        # source_node_id == the pitfall node (the "to" end of the edge, kind=pitfall).
        source_node_id: str = target_node_id

        target_node: dict[str, Any] = nodes_by_id.get(target_node_id, {})

        # ---- Step 2: Parse Pitfalls section for structured fields ------------
        pitfalls_section = (
            sections_by_node.get(target_node_id, {}) or {}
        ).get("Pitfalls")

        structured: dict[str, str] = {k: "" for k in STRUCTURED_FIELDS}
        if pitfalls_section is not None:
            raw_content: str = ""
            # SectionView carries .content; plain dicts carry "content" key.
            if hasattr(pitfalls_section, "content"):
                raw_content = pitfalls_section.content or ""
            elif isinstance(pitfalls_section, dict):
                raw_content = pitfalls_section.get("content", "")
            structured = _parse_pitfalls_section(raw_content)

        # Thin-content warning: fire when ANY of the four structured fields is empty.
        missing_fields = [f for f in STRUCTURED_FIELDS if not structured[f]]
        if missing_fields:
            warnings.append(
                LearningWarning(
                    severity="warning",
                    code="thin_pitfall_content",
                    source_ref=target_node_id,
                    message=(
                        f"Pitfall node {target_node_id!r} missing structured fields: "
                        f"{sorted(missing_fields)!r}."
                    ),
                )
            )

        # ---- Step 3: Source path + session refs ------------------------------
        node_source_path: str = target_node.get("source_path", "")
        session_refs: list[str] = sorted(
            str(r) for r in (target_node.get("session_refs") or [])
        )

        # ---- Step 4: Corrective concepts (outgoing requires/adjacent edges) --
        corrective_concepts: list[str] = sorted(
            e["to"]
            for e in graph_slice.edges
            if e.get("from") == target_node_id
            and e.get("type") in {"requires", "adjacent"}
            and e.get("to") is not None
        )

        # ---- Step 5: Build PitfallView ---------------------------------------
        message = _build_message(structured, corrective_concepts, session_refs)

        pitfall_views.append(
            PitfallView(
                pitfall_id=edge_id,
                source_node_id=source_node_id,
                source_path=node_source_path or None,
                message=message,
                severity="warning",
            )
        )

    return pitfall_views, warnings
