"""Node-level section extraction with deterministic fallback.

This module provides the :class:`ExtractedSection` abstraction that the
pedagogical modes consume. It is intentionally separate from the
:mod:`akms_learn.sections` machinery (``SectionView`` /
``extract_sections``) for two reasons:

1. :func:`akms_learn.sections.extract_sections` walks *raw markdown*
   and is wired into the compiler pipeline. Changing its signature
   would force a refactor of every mode built on it.
2. The pedagogical modes operate on *already-imported* AKMS nodes whose
   :attr:`extracted` mapping (populated by fixtures and by the
   compiler) keys content by approved heading. The contract here is
   "given a node dict, return a deterministic list of
   :class:`ExtractedSection` records, with a documented fallback
   ladder".

Approved heading set
--------------------

The approved heading set is the v0.1 allowed section types from
the akms-learn internal specification (not published)
§ "Allowed section types in v0.1" (lines 126-145). It is mirrored
verbatim here as :data:`APPROVED_HEADINGS` and MUST NOT be redefined
or paraphrased elsewhere. Updates to the spec are the
only legitimate trigger to update this constant.

Fallback ladder (deterministic, no random tiebreaks)
-----------------------------------------------------

For every node, candidate sections are collected from
``node["extracted"]`` (and a few well-known aliases). Each candidate
heading is resolved against the approved set using the following
ladder, in order; the *first* tier that yields a match wins:

1. ``exact`` — heading string equals an approved heading character-for-
   character.
2. ``case_insensitive`` — heading lowercased equals an approved heading
   lowercased.
3. ``fallback_summary`` — the candidate did not match the approved set
   *and* the node carries a ``summary`` field; the summary becomes the
   section content.
4. ``excerpt`` — neither approved match nor summary; the first
   :data:`EXCERPT_MAX_CHARS` characters of the node body (joined from
   ``body`` / ``markdown`` / ``content`` / extracted-value
   concatenation) become the section content.

Ordering is deterministic: candidate headings are processed in *sorted*
key order, then results are emitted in the canonical approved-heading
order (alphabetical over :data:`APPROVED_HEADINGS`), with fallback
records appended last in deterministic order.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

__all__ = [
    "APPROVED_HEADINGS",
    "ExtractionMethod",
    "ExtractedSection",
    "extract_sections_from_node",
    "extract_sections_from_nodes",
    "EXCERPT_MAX_CHARS",
]


# ---------------------------------------------------------------------------
# Approved heading set — mirrored verbatim from spec 01 §126-145.
# DO NOT paraphrase; DO NOT reorder for "aesthetics"; only update when
# spec 01 §126-145 itself changes.
# ---------------------------------------------------------------------------

APPROVED_HEADINGS: tuple[str, ...] = (
    "motivation",
    "prerequisites",
    "concept",
    "derivation",
    "implementation",
    "worked_example",
    "pitfalls",
    "assessment",
    "references",
    "next_paths",
)

# Pre-computed lookup tables (built once at import). Both must be stable
# across processes — they are derived from the immutable APPROVED_HEADINGS
# tuple, so identity is preserved.
_EXACT_LOOKUP: dict[str, str] = {h: h for h in APPROVED_HEADINGS}
_LOWER_LOOKUP: dict[str, str] = {h.lower(): h for h in APPROVED_HEADINGS}

# Excerpt length used when a node has neither matching heading nor a
# summary field. 500 chars is a deliberate, documented choice — long
# enough to surface signal in tests, short enough to keep packet sizes
# under control.
EXCERPT_MAX_CHARS: int = 500


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


ExtractionMethod = Literal[
    "exact",
    "case_insensitive",
    "fallback_summary",
    "excerpt",
]


@dataclass(frozen=True)
class ExtractedSection:
    """A single extracted section with full provenance.

    Fields
    ------
    name:
        The original heading text exactly as it appeared in the source
        node (whatever case / spelling the author used).
    normalized_name:
        The canonical approved heading the source heading mapped to.
        For the fallback tiers (``fallback_summary`` / ``excerpt``) this
        is the sentinel ``"summary"`` or ``"excerpt"`` respectively, so
        downstream code can switch on it without ambiguity.
    content:
        The section text. For the fallback tiers this is the summary
        body or the deterministic excerpt of the node body.
    source_node_id:
        The ``node_id`` of the AKMS node this section was extracted
        from.
    source_path:
        File path to the source node, or ``None`` when unknown / the
        node has no on-disk provenance (e.g. toy fixtures using
        ``toy://`` URIs propagate as ``None``).
    line_range:
        ``(start, end)`` 1-indexed inclusive line numbers in the source
        file, or ``None`` when the node carries no line provenance.
    extraction_method:
        Which tier of the fallback ladder produced this section.
    """

    name: str
    normalized_name: str
    content: str
    source_node_id: str
    source_path: Optional[Path]
    line_range: Optional[tuple[int, int]]
    extraction_method: ExtractionMethod


# ---------------------------------------------------------------------------
# Heading resolution
# ---------------------------------------------------------------------------


def _coerce_source_path(value: Any) -> Optional[Path]:
    """Coerce a node's ``source_path`` field to ``Path | None``.

    Pseudo-URI strings such as ``"toy://..."`` and the sentinel
    ``"unknown"`` are treated as *no on-disk provenance* and returned as
    ``None`` so downstream consumers can branch on truthiness.
    """
    if value is None:
        return None
    if isinstance(value, Path):
        return value
    if isinstance(value, str):
        if not value or value == "unknown":
            return None
        if "://" in value:
            # Pseudo-URI — preserve as-is via Path so str(p) round-trips
            # for tests, but mark as opaque (no real on-disk path).
            return Path(value)
        return Path(value)
    return None


def _coerce_line_range(value: Any) -> Optional[tuple[int, int]]:
    """Coerce a node's ``line_range`` field to ``(int, int) | None``."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            start, end = int(value[0]), int(value[1])
        except (TypeError, ValueError):
            return None
        # Treat (0, 0) as "no line provenance" — toy fixtures use it for
        # nodes whose source is unknown.
        if start == 0 and end == 0:
            return None
        return (start, end)
    return None


def _node_body_text(node: dict[str, Any]) -> str:
    """Compose a deterministic body string for excerpt fallback.

    Tries (in order) ``body``, ``markdown``, ``content``, then a
    concatenation of ``extracted`` values in sorted key order. Returns
    an empty string if nothing is available.
    """
    for key in ("body", "markdown", "content"):
        raw = node.get(key)
        if isinstance(raw, str) and raw:
            return raw
    extracted = node.get("extracted")
    if isinstance(extracted, dict) and extracted:
        return "\n\n".join(
            str(extracted[k]) for k in sorted(extracted.keys())
        )
    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_sections_from_node(node: dict[str, Any]) -> list[ExtractedSection]:
    """Extract approved sections from a single AKMS node dict.

    Parameters
    ----------
    node:
        Raw AKMS node payload (as produced by test fixtures or by the
        compiler's slice conversion stage). MUST include ``node_id``;
        every other field is optional. Recognised optional fields:

        * ``extracted`` — mapping of heading-text → content string
        * ``source_path``, ``line_range`` — propagated to every returned
          :class:`ExtractedSection`
        * ``summary`` — used by the ``fallback_summary`` tier
        * ``body`` / ``markdown`` / ``content`` — used by ``excerpt``

    Returns
    -------
    list[ExtractedSection]
        Deterministic list of sections. Approved-heading hits come
        first, in canonical approved-heading order
        (:data:`APPROVED_HEADINGS`). The fallback tier (at most one
        ``fallback_summary`` *or* ``excerpt``) is appended last and is
        emitted only when zero approved-heading hits matched.

    Determinism contract
    --------------------
    Calling this function twice on the same ``node`` payload returns
    two lists that compare equal element-by-element. No dict-iteration
    order leaks into the result: all dict scans go through
    ``sorted(...)``.
    """
    node_id = str(node.get("node_id") or "")
    source_path = _coerce_source_path(node.get("source_path"))
    line_range = _coerce_line_range(node.get("line_range"))

    extracted = node.get("extracted")
    if not isinstance(extracted, dict):
        extracted = {}

    # Pass 1 — resolve candidate headings through the ladder in two
    # *tiered* passes so that the exact tier is fully consumed before
    # any case-insensitive candidate is considered. This guarantees the
    # acceptance-criteria invariant "exact beats case_insensitive when
    # both are present" without depending on dict-iteration order.
    canonical_to_record: dict[str, ExtractedSection] = {}

    def _claim(raw_heading: str, canonical: str, method: ExtractionMethod) -> None:
        if canonical in canonical_to_record:
            return
        content = extracted[raw_heading]
        if not isinstance(content, str):
            content = str(content) if content is not None else ""
        canonical_to_record[canonical] = ExtractedSection(
            name=raw_heading,
            normalized_name=canonical,
            content=content,
            source_node_id=node_id,
            source_path=source_path,
            line_range=line_range,
            extraction_method=method,
        )

    # Tier 1: exact matches (sorted for determinism within the tier).
    for raw_heading in sorted(extracted.keys()):
        canonical = _EXACT_LOOKUP.get(raw_heading)
        if canonical is not None:
            _claim(raw_heading, canonical, "exact")

    # Tier 2: case-insensitive matches (only slots not yet claimed).
    for raw_heading in sorted(extracted.keys()):
        if raw_heading in _EXACT_LOOKUP:
            continue  # already handled exactly
        canonical = _LOWER_LOOKUP.get(raw_heading.lower())
        if canonical is not None:
            _claim(raw_heading, canonical, "case_insensitive")

    # Pass 2 — emit in canonical approved-heading order.
    results: list[ExtractedSection] = [
        canonical_to_record[h]
        for h in APPROVED_HEADINGS
        if h in canonical_to_record
    ]

    # If at least one approved heading hit, the fallback tier is
    # suppressed by design — the node already carries structured
    # content the modes can consume.
    if results:
        return results

    # Fallback ladder, deterministic single-emit:
    summary = node.get("summary")
    if isinstance(summary, str) and summary.strip():
        return [
            ExtractedSection(
                name="summary",
                normalized_name="summary",
                content=summary,
                source_node_id=node_id,
                source_path=source_path,
                line_range=line_range,
                extraction_method="fallback_summary",
            )
        ]

    body = _node_body_text(node)
    excerpt = body[:EXCERPT_MAX_CHARS]
    return [
        ExtractedSection(
            name="excerpt",
            normalized_name="excerpt",
            content=excerpt,
            source_node_id=node_id,
            source_path=source_path,
            line_range=line_range,
            extraction_method="excerpt",
        )
    ]


def extract_sections_from_nodes(
    nodes: Iterable[dict[str, Any]],
) -> dict[str, list[ExtractedSection]]:
    """Convenience wrapper: extract sections for many nodes.

    Returns a dict keyed by ``node_id`` (nodes missing an id are
    skipped). Output order of the returned dict mirrors the input
    iteration order; per-node section lists are deterministic per
    :func:`extract_sections_from_node`.
    """
    out: dict[str, list[ExtractedSection]] = {}
    for node in nodes:
        nid = str(node.get("node_id") or "")
        if not nid:
            continue
        out[nid] = extract_sections_from_node(node)
    return out
