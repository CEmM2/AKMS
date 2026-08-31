"""Section extraction with provenance fallback for AKMS node markdown.

Recognises the 9 approved teaching-oriented headings defined in plan1 §17
(L294–L304) and the Phase 3 context summary.  Matching is **case-insensitive
and depth-agnostic** (``## Pitfalls`` and ``### Pitfalls`` are equivalent).

Public API
----------
APPROVED_SECTIONS   tuple[str, ...] — canonical 9 headings in canonical order.
SectionView         Pydantic v2 model carrying extracted content + provenance.
parse_markdown_headings  Low-level ATX heading scanner (skips fenced blocks).
extract_sections    Main extractor: markdown → (sections_dict, warnings).
merge_sections_into_node_view  Helper to attach sections to a LearningNodeView.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from akms_learn.models import LearningWarning
from akms_learn.warnings import emit_missing_section_warning

__all__ = [
    "APPROVED_SECTIONS",
    "SectionView",
    "parse_markdown_headings",
    "extract_sections",
    "merge_sections_into_node_view",
]

#   # ---------------------------------------------------------------------------
#   # Approved headings — canonical names, canonical order. Case-insensitive
#   # matching is applied at runtime; the values here are the canonical (stored)
#   # keys.
#   # ---------------------------------------------------------------------------

APPROVED_SECTIONS: tuple[str, ...] = (
    "Learning goal",
    "Prerequisites",
    "Concept map",
    "Main path",
    "Implementation",
    "Derivation",
    "Pitfalls",
    "Self-check",
    "References",
)

# Pre-compute a lower-cased lookup for O(1) case-insensitive matching.
# (Implementation and Derivation are two independent canonical headings — no
# aliasing happens here.)
_LOWER_TO_CANONICAL: dict[str, str] = {s.lower(): s for s in APPROVED_SECTIONS}

# Leading section enumerator ("1. ", "2) ") stripped before matching, so authoring
# templates that number their headings (e.g. the Nodes_Vault template's
# "## 3. Algorithmic Implementation") still resolve to a canonical section.
_ENUM_PREFIX_RE = re.compile(r"^\s*\d+[.)]\s*")

# Synonym aliases (lowercase, post enumerator-strip) → canonical APPROVED_SECTIONS
# name. Lets common author phrasings match without renaming every node. Consulted
# only AFTER the exact _LOWER_TO_CANONICAL lookup, so canonical spellings win.
# "Core Concept" and "Mathematical Formulation" both fold into Derivation (the
# lesson's "Implementation / derivation / explanation" body); when both are present
# their content is concatenated in document order (see extract_sections).
_ALIAS_TO_CANONICAL: dict[str, str] = {
    "core concept": "Derivation",
    "mathematical formulation": "Derivation",
    "algorithmic implementation": "Implementation",
    "known pitfalls": "Pitfalls",
}


def _match_canonical(heading_text: str) -> Optional[str]:
    """Resolve a raw heading to a canonical APPROVED_SECTIONS name, or None.

    Resolution order (first hit wins): exact case-insensitive match → the same
    after stripping a leading enumerator → the synonym alias table.
    """
    key = heading_text.strip().lower()
    canonical = _LOWER_TO_CANONICAL.get(key)
    if canonical is not None:
        return canonical
    stripped = _ENUM_PREFIX_RE.sub("", key)
    canonical = _LOWER_TO_CANONICAL.get(stripped)
    if canonical is not None:
        return canonical
    return _ALIAS_TO_CANONICAL.get(stripped)


# ATX heading pattern: optional leading whitespace (≤3 spaces), one or more #,
# at least one space, then the heading text.
_ATX_RE = re.compile(r"^[ \t]{0,3}(#{1,6})[ \t]+(.+?)[ \t]*(?:#+[ \t]*)?$")


# ---------------------------------------------------------------------------
# SectionView
# ---------------------------------------------------------------------------


class SectionView(BaseModel):
    """Extracted section with full source provenance.

    ``line_range`` is a ``(start, end)`` tuple of **1-indexed, inclusive** line
    numbers into ``source_path``.  ``content`` is the raw markdown text between
    the heading line (exclusive) and the next heading (exclusive), with a
    trailing newline stripped via ``rstrip("\\n")``.
    """

    model_config = ConfigDict()

    name: str
    content: str
    source_path: str
    line_range: tuple[int, int]


# ---------------------------------------------------------------------------
# parse_markdown_headings
# ---------------------------------------------------------------------------


def parse_markdown_headings(text: str) -> list[tuple[int, str, int]]:
    """Return ATX headings from *text*, skipping content inside fenced blocks.

    Returns a list of ``(level, heading_text, start_line_1indexed)`` tuples in
    document order.  ``heading_text`` is the stripped text after the ``#``
    markers (trailing closer markers removed by the regex).

    Fenced code blocks are detected by counting unescaped triple-backtick
    (````` ``` `````) fence opens/closes.  A heading inside a fence is silently
    skipped.
    """
    results: list[tuple[int, str, int]] = []
    in_fence = False

    for lineno_0, line in enumerate(text.splitlines()):
        lineno_1 = lineno_0 + 1  # convert to 1-indexed

        # Detect fence open/close (triple backtick at start of line).
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue

        if in_fence:
            continue

        m = _ATX_RE.match(line)
        if m:
            level = len(m.group(1))
            heading_text = m.group(2).strip()
            results.append((level, heading_text, lineno_1))

    return results


# ---------------------------------------------------------------------------
# extract_sections
# ---------------------------------------------------------------------------


def extract_sections(
    node_markdown: str,
    source_path: str,
    node_id: Optional[str] = None,
) -> tuple[dict[str, Any], list[LearningWarning]]:
    """Extract approved teaching sections from *node_markdown*.

    Parameters
    ----------
    node_markdown:
        Raw markdown content of an AKMS node file.  Not mutated.
    source_path:
        Path to the source file (used for ``SectionView.source_path`` and
        ``LearningWarning.source_ref``).
    node_id:
        Optional node identifier for warning messages.  Defaults to
        ``"<unknown>"`` when not supplied.

    Returns
    -------
    sections_dict:
        * **Normal path** — every key in ``APPROVED_SECTIONS`` is present.
          Value is a :class:`SectionView` if the heading was found, ``None``
          otherwise.
        * **Fallback path** — when zero approved headings matched the input,
          the dict has exactly one key ``"body"`` whose value is a
          :class:`SectionView` wrapping the whole document.
    warnings:
        List of :class:`~akms_learn.models.LearningWarning` instances.  One
        ``code="missing_section"`` warning per absent approved heading on the
        normal path.  One ``code="section_fallback_body"`` warning on the
        fallback path.
    """
    _node_id = node_id or "<unknown>"
    lines = node_markdown.splitlines()
    total_lines = max(len(lines), 1)

    # ------------------------------------------------------------------
    # 1. Parse all ATX headings in the document.
    # ------------------------------------------------------------------
    all_headings = parse_markdown_headings(node_markdown)

    # ------------------------------------------------------------------
    # 2. Filter to approved headings only, preserving document order.
    #    Matching: strip() + lower() against _LOWER_TO_CANONICAL.
    # ------------------------------------------------------------------
    approved_hits: list[tuple[str, int]] = []
    for _level, heading_text, start_line in all_headings:
        canonical = _match_canonical(heading_text)
        if canonical is not None:
            approved_hits.append((canonical, start_line))

    # ------------------------------------------------------------------
    # 3. Fallback: zero approved headings matched.
    # ------------------------------------------------------------------
    if not approved_hits:
        fallback_view = SectionView(
            name="body",
            content=node_markdown,
            source_path=source_path,
            line_range=(1, total_lines),
        )
        fallback_warning = LearningWarning(
            severity="warning",
            code="section_fallback_body",
            source_ref=source_path,
            message=(
                "No approved headings found; emitted whole-document body section."
            ),
        )
        return {"body": fallback_view}, [fallback_warning]

    # ------------------------------------------------------------------
    # 4. Slice content between consecutive approved headings.
    #    Heading line itself is excluded; content starts on the next line.
    #    Last section runs to EOF.
    # ------------------------------------------------------------------
    sections_found: dict[str, SectionView] = {}

    for idx, (canonical, start_line) in enumerate(approved_hits):
        # Content begins on the line after the heading.
        content_start = start_line + 1  # 1-indexed line of first content line

        # Content ends just before the next heading (or EOF).
        if idx + 1 < len(approved_hits):
            next_heading_line = approved_hits[idx + 1][1]
            content_end = next_heading_line - 1  # inclusive
        else:
            content_end = total_lines

        # Slice 0-indexed lines: content_start-1 .. content_end (exclusive).
        content_lines = lines[content_start - 1 : content_end]
        content = "\n".join(content_lines).rstrip("\n")

        # Guard: if content_start > content_end the heading is immediately
        # followed by the next heading with no content lines in between.
        if content_start > content_end:
            content = ""
            line_range = (start_line, start_line)
        else:
            line_range = (content_start, content_end)

        # When several source headings map to one canonical (e.g. Core Concept +
        # Mathematical Formulation → Derivation), concatenate their content in
        # document order and widen the line_range to span all contributors.
        existing = sections_found.get(canonical)
        if existing is None:
            sections_found[canonical] = SectionView(
                name=canonical,
                content=content,
                source_path=source_path,
                line_range=line_range,
            )
        elif content:
            merged = f"{existing.content}\n\n{content}" if existing.content else content
            sections_found[canonical] = SectionView(
                name=canonical,
                content=merged,
                source_path=source_path,
                line_range=(existing.line_range[0], line_range[1]),
            )

    # ------------------------------------------------------------------
    # 5. Build result dict; emit missing-section warnings.
    # ------------------------------------------------------------------
    result: dict[str, Any] = {}
    warnings: list[LearningWarning] = []

    for section_name in APPROVED_SECTIONS:
        view = sections_found.get(section_name)
        if view is None:
            result[section_name] = None
            warnings.append(emit_missing_section_warning(_node_id, section_name))
        else:
            result[section_name] = view

    return result, warnings


# ---------------------------------------------------------------------------
# merge_sections_into_node_view
# ---------------------------------------------------------------------------


def merge_sections_into_node_view(
    node_view: Any,
    sections_dict: dict[str, Any],
) -> dict[str, Any]:
    """Attach *sections_dict* to *node_view*'s ``included_sections`` field.

    :class:`~akms_learn.models.LearningNodeView` exposes the dict-shaped
    ``included_sections`` field (not ``sections`` — that name belongs to a
    different model and a different shape). When *node_view* has that
    attribute we set it to a serialised version of *sections_dict*:
    ``{k: v.model_dump() if v else None for k, v in sections_dict.items()}``.

    Returns the serialised dict regardless, so Phase 3.4 can attach it to
    the packet body without depending on this helper having a side-effect.
    """
    serialised: dict[str, Any] = {
        k: v.model_dump() if v is not None else None for k, v in sections_dict.items()
    }
    if hasattr(node_view, "included_sections"):
        node_view.included_sections = serialised
    return serialised
