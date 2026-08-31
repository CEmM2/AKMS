"""Markdown exporter for Learning Source Packets.

Exporter Protocol conformance
-----------------------------
This module exposes a top-level :func:`export` function matching the
``Exporter`` callable protocol declared in
:mod:`akms_learn.exporters`:

.. code-block:: python

    def export(
        packet: LearningSourcePacket,
        output_dir: Path,
        /,
    ) -> list[Path]: ...

The compiler dispatches this function from Stage 9 of
:func:`akms_learn.compiler.compile_learning_source` when ``"markdown"`` is
in ``request.exporters``.  Callers MUST NOT invoke this module's functions
directly — use :func:`~akms_learn.compiler.compile_learning_source` with
``exporters=["markdown"]`` instead.

Design invariants
-----------------
* **Pure** — no network, no LLM, no global state mutations.
* **Deterministic** — identical inputs produce byte-equal ``lesson.md``
  outputs. All iterables are sorted before rendering.
* **No ``datetime.now()``, no ``uuid``, no ``random``** — the template
  context contains no per-call entropy.
* **No ``from akms import …``** — one-way import rule enforced.
* Empty sections render with an explicit ``_no content_`` marker; they are
  never silently omitted.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, FileSystemLoader

from akms_learn._code_links import is_missing_source_path

if TYPE_CHECKING:
    from akms_learn.models import LearningSourcePacket

__all__ = ["export", "_build_context", "PLAN2_MODE_KEYS"]

# Directory that contains ``markdown_default.md.j2`` and
# ``markdown_expanded.md.j2``.
_TEMPLATES_DIR: Path = Path(__file__).resolve().parent.parent / "templates"
_TEMPLATE_NAME = "markdown_default.md.j2"
_TEMPLATE_EXPANDED = "markdown_expanded.md.j2"

# Mode keys that dispatch to the pedagogical (12-slot) markdown layout.
# Mode keys outside this set keep the original template — that is what
# guarantees legacy outputs stay byte-identical to the original baseline.
PLAN2_MODE_KEYS: frozenset[str] = frozenset(
    {
        "pedagogical_template",
        "derivation_first",
        "implementation_first",
        "multi_granularity",
    }
)

# Edge types that classify the *source* node into a learning bucket.
# Mirrors ``EDGE_TYPE_TO_BUCKET`` in ``ordering.py`` (no import — one-way rule).
_EDGE_TYPE_PREREQ = "requires"
_EDGE_TYPE_PITFALL = "pitfall_of"

# Node kind strings that map to the prerequisite / pitfall buckets.
_PREREQ_KINDS = frozenset({"prerequisite"})
_PITFALL_KINDS = frozenset({"pitfall"})


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _node_display(node: Any) -> str:
    """Return title if present, else node_id."""
    title = getattr(node, "title", None)
    if title:
        return str(title)
    return str(node.node_id)


def _extract_section_content(sections: dict[str, Any], heading: str) -> str:
    """Extract the ``content`` text from a serialised SectionView dict.

    The compiler serialises ``SectionView`` instances via ``model_dump()``
    before storing them in ``LearningNodeView.included_sections``.  The result
    is a dict with keys ``name``, ``content``, ``source_path``, ``line_range``.
    """
    if not sections:
        return ""
    entry = sections.get(heading)
    if entry is None:
        return ""
    if isinstance(entry, dict):
        return str(entry.get("content") or "")
    # SectionView instance (in tests that bypass serialisation)
    content = getattr(entry, "content", None)
    return str(content) if content else ""


def _classify_nodes(packet: "LearningSourcePacket") -> tuple[set[str], set[str]]:
    """Return (prereq_ids, pitfall_ids) sets from packet nodes + edges.

    Classification priority:
    1. ``node.provenance`` dict ``kind`` field (set by the compiler when the
       raw graph dict carries ``kind`` in its ``provenance`` entry).
    2. ``node.included_sections`` metadata ``kind`` key.
    3. Edge-based: source node of a ``requires`` edge → prerequisite;
       source node of a ``pitfall_of`` edge → pitfall.
    4. No-match → not in either set.

    The ``extracted`` field is intentionally NOT consulted here because
    :func:`~akms_learn.compiler._build_node_view` only populates it from
    ``node.get("extracted")``, which is absent in the standard fixture graph
    (where ``kind`` lives at the raw-dict top level).  The provenance dict is
    also empty for fixture nodes, so we fall through to edge-based detection,
    which is robust for all graph shapes.
    """
    nodes = packet.body.nodes
    edges = packet.body.edges

    prereq_ids: set[str] = set()
    pitfall_ids: set[str] = set()

    # Edge-based classification (primary for standard fixture graphs)
    for edge in edges:
        etype = getattr(edge, "type", None) or ""
        if etype == _EDGE_TYPE_PREREQ:
            from_node = getattr(edge, "from_node", None) or ""
            if from_node:
                # The *source* of a ``requires`` edge is a prerequisite node
                # (it is required *before* the target).
                prereq_ids.add(from_node)
        elif etype == _EDGE_TYPE_PITFALL:
            to_node = getattr(edge, "to_node", None) or ""
            if to_node:
                # The *target* of a ``pitfall_of`` edge is the pitfall node.
                pitfall_ids.add(to_node)

    # Also use PitfallView node_ids from packet.body.pitfalls — but only for
    # *dedicated* pitfall nodes. Those carry ``pitfall_id == source_node_id``;
    # section-derived pitfalls (``pitfall_id == "<nid>::pitfall::N"``) come from
    # ordinary content nodes that must stay in the main path, so they never
    # classify their source node as a pitfall.
    for pv in packet.body.pitfalls:
        snid = getattr(pv, "source_node_id", None)
        pid = getattr(pv, "pitfall_id", None)
        if snid and pid and str(snid) == str(pid):
            pitfall_ids.add(str(snid))
        elif pid and not snid:
            pitfall_ids.add(str(pid))

    # Node-kind-based override (for packets assembled with explicit kind field)
    for node in nodes:
        provenance = getattr(node, "provenance", {}) or {}
        kind = provenance.get("kind") or ""
        if not kind:
            sections = getattr(node, "included_sections", {}) or {}
            kind = sections.get("kind") or ""
        if kind in _PREREQ_KINDS:
            prereq_ids.add(node.node_id)
        elif kind in _PITFALL_KINDS:
            pitfall_ids.add(node.node_id)

    return prereq_ids, pitfall_ids


# ---------------------------------------------------------------------------
# Pedagogical-layout helpers (mode-aware ordering, code-link rendering,
# granularity)
# ---------------------------------------------------------------------------


def _mode_key(packet: "LearningSourcePacket") -> str:
    """Return the lower-cased mode key from the LSP request block.

    The compiler normalises ``generation_option`` to a trimmed, lower-cased
    string, but defensive normalisation is cheap and means the exporter is
    robust to packets assembled by hand in tests.
    """
    raw = getattr(packet.request, "generation_option", None) or ""
    return str(raw).strip().lower()


def _granularity_label(packet: "LearningSourcePacket") -> str:
    """Return the LSP-recorded granularity label, or ``""`` when unset."""
    value = getattr(packet.request, "granularity", None)
    return str(value) if value else ""


def _format_line_range(line_range: Any) -> str:
    """Render a CodeLinkView line_range pair as ``"start-end"`` or ``"unknown"``.

    Mirrors :func:`akms_learn._code_links.coerce_line_range` semantics — any
    ``(start, end)`` tuple of ints is informative *except* the sentinel
    ``(0, 0)``, which (along with malformed inputs) collapses to
    ``"unknown"``.
    """
    if isinstance(line_range, (list, tuple)) and len(line_range) == 2:
        try:
            start = int(line_range[0])
            end = int(line_range[1])
        except (TypeError, ValueError):
            return "unknown"
        if (start, end) == (0, 0):
            return "unknown"
        return f"{start}-{end}"
    return "unknown"


def _render_code_link(view: Any) -> dict[str, str]:
    """Build the template-facing dict for one :class:`CodeLinkView`.

    The :func:`build_code_links` collector populates ``file_path`` /
    ``line_range`` with ``None`` when the implementation target has a
    sentinel/missing ``source_path``. We mirror that by falling back to
    ``"unknown"`` so the rendered block still produces a fenced reference
    block with literal ``source_path:`` / ``line_range:`` keys (one
    block per CodeLinkView, regardless of source completeness).
    """
    file_path = getattr(view, "file_path", None)
    if file_path is None or is_missing_source_path(file_path):
        file_path = "unknown"
    line_range = getattr(view, "line_range", None)
    label = (
        getattr(view, "target", None)
        or getattr(view, "node_id", None)
        or str(file_path)
    )
    return {
        "label": str(label),
        "source_path": str(file_path),
        "line_range": _format_line_range(line_range),
    }


def _warning_codes_sorted(packet: "LearningSourcePacket") -> list[str]:
    """Return the unique, sorted warning-code list from the packet."""
    codes: set[str] = set()
    for warning in packet.warnings or []:
        code = getattr(warning, "code", None)
        if code:
            codes.add(str(code))
    return sorted(codes)


def _ordered_nodes_from_packet(packet: "LearningSourcePacket") -> list[Any]:
    """Return packet nodes ordered by ``packet.body.reading_order``.

    Nodes listed in ``reading_order`` come first in that order; any nodes
    not covered by ``reading_order`` (older packets / malformed input) are
    appended sorted by ``node_id`` so the result is deterministic.

    Shared between :func:`_build_context` and :func:`_build_plan2_context`
    so both templates see identical ordering for the same
    packet (single source of truth — fixing a future ordering bug only
    needs one edit).
    """
    nodes = packet.body.nodes
    node_by_id: dict[str, Any] = {n.node_id: n for n in nodes}
    reading_order = list(packet.body.reading_order or [])
    seen: set[str] = set(reading_order)
    fallback_tail = sorted(n.node_id for n in nodes if n.node_id not in seen)
    ordered_node_ids: list[str] = reading_order + fallback_tail
    return [node_by_id[nid] for nid in ordered_node_ids if nid in node_by_id]


def _build_plan2_context(packet: "LearningSourcePacket") -> dict[str, Any]:
    """Build the Jinja2 context for the pedagogical markdown template.

    Reuses the base context (so all the deterministic ordering
    + sorting work is shared) and layers pedagogical fields on top:

    * ``mode_key`` — dispatch key for the template ``{% if %}`` branches.
    * ``granularity_label`` — surfaced from
      :attr:`LearningRequestInfo.granularity`.
    * ``code_links`` — one rendered dict per CodeLinkView on the packet;
      an empty list yields the template's ``_no content_``
      placeholder.
    * ``warning_codes`` — unique, sorted warning codes from the packet.
    * ``intuition`` / ``formal_statement`` / ``worked_example`` /
      ``exercises`` — section content for the 12-slot pedagogical layout,
      sourced from the existing per-node serialised section dicts.
    """
    base = _build_context(packet)

    ordered_nodes = _ordered_nodes_from_packet(packet)

    # Pedagogical-section content (Intuition / Formal statement /
    # Worked example / Exercises). These slot names match the headings the
    # compiler's section extractor records in ``LearningNodeView.included_sections``.
    pedagogical_slots: dict[str, str] = {
        "intuition": "",
        "formal_statement": "",
        "worked_example": "",
        "exercises": "",
    }
    # `formal_statement` deliberately does NOT inherit the "Concept" fallback
    # that `intuition` uses — otherwise a fixture lacking a distinct "Formal
    # statement" heading would render the Concept content into both slots.
    _slot_to_headings: dict[str, tuple[str, ...]] = {
        "intuition": ("Intuition", "Concept", "concept"),
        "formal_statement": ("Formal statement", "formal_statement"),
        "worked_example": ("Worked example", "worked_example"),
        "exercises": ("Exercises", "Assessment", "assessment"),
    }
    for slot, headings in _slot_to_headings.items():
        for node in ordered_nodes:
            sections = node.included_sections or {}
            for heading in headings:
                content = _extract_section_content(sections, heading)
                if content:
                    pedagogical_slots[slot] = content.strip()
                    break
            if pedagogical_slots[slot]:
                break

    code_links_raw = list(packet.body.code_links or [])
    code_links = [_render_code_link(v) for v in code_links_raw]

    base.update(
        {
            "mode_key": _mode_key(packet),
            "granularity_label": _granularity_label(packet),
            "code_links": code_links,
            "warning_codes": _warning_codes_sorted(packet),
            **pedagogical_slots,
        }
    )
    return base


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


def _build_context(packet: "LearningSourcePacket") -> dict[str, Any]:
    """Build the Jinja2 template context dict from *packet*.

    All list values are deterministically sorted so that re-running the
    renderer on the same packet always produces byte-equal output.

    Parameters
    ----------
    packet:
        A fully-assembled :class:`~akms_learn.models.LearningSourcePacket`.

    Returns
    -------
    dict
        Flat context dict consumed by ``markdown_default.md.j2``.
    """
    nodes = packet.body.nodes
    edges = packet.body.edges

    # ------------------------------------------------------------------
    # topic
    # ------------------------------------------------------------------
    topic: str = str(packet.request.topic) if packet.request.topic else "<unknown topic>"

    # ------------------------------------------------------------------
    # learning_goal — from request.goal if non-empty
    # ------------------------------------------------------------------
    learning_goal: str | None = packet.request.goal if packet.request.goal else None

    # ------------------------------------------------------------------
    # Classify nodes into prereq / pitfall buckets
    # ------------------------------------------------------------------
    prereq_ids, pitfall_ids = _classify_nodes(packet)

    # prerequisites — sorted list of display strings for prereq nodes
    prerequisites: list[str] = sorted(
        _node_display(node)
        for node in nodes
        if node.node_id in prereq_ids
    )

    # concept_map — sorted list of all node_ids in the packet
    concept_map: list[str] = sorted(node.node_id for node in nodes)

    # Preserve the compiler-computed reading_order for main_path,
    # implementation, and derivation so the generated lesson follows the
    # intended pedagogical flow instead of an alphabetical accident.
    # Falls back to node_id-sorted iteration when reading_order is empty.
    ordered_nodes = _ordered_nodes_from_packet(packet)

    # main_path — display strings in reading_order for nodes NOT in
    # prereq or pitfall buckets.
    main_path: list[str] = [
        _node_display(node)
        for node in ordered_nodes
        if node.node_id not in prereq_ids and node.node_id not in pitfall_ids
    ]

    # ------------------------------------------------------------------
    # implementation / derivation — concatenate section content by reading_order
    # ------------------------------------------------------------------
    impl_parts: list[str] = []
    deriv_parts: list[str] = []

    for node in ordered_nodes:
        sections = node.included_sections or {}
        impl_content = _extract_section_content(sections, "Implementation")
        deriv_content = _extract_section_content(sections, "Derivation")
        if impl_content:
            impl_parts.append(impl_content.strip())
        if deriv_content:
            deriv_parts.append(deriv_content.strip())

    implementation: str = "\n\n".join(impl_parts) if impl_parts else ""
    derivation: str = "\n\n".join(deriv_parts) if deriv_parts else ""

    # ------------------------------------------------------------------
    # pitfalls — sorted list of pitfall display strings from PitfallView
    # ------------------------------------------------------------------
    pitfall_views = packet.body.pitfalls or []
    pitfalls: list[str] = sorted(
        str(pv.message or pv.pitfall_id or "")
        for pv in pitfall_views
        if pv.message or pv.pitfall_id
    )

    # ------------------------------------------------------------------
    # self_check — concatenate Self-check section content from nodes
    # ------------------------------------------------------------------
    self_check_parts: list[str] = []
    for node in ordered_nodes:
        content = _extract_section_content(node.included_sections or {}, "Self-check")
        if content:
            self_check_parts.append(content.strip())
    self_check: str = "\n\n".join(self_check_parts) if self_check_parts else ""

    # ------------------------------------------------------------------
    # references — sorted list from packet.body.references
    # ------------------------------------------------------------------
    ref_views = packet.body.references or []
    references: list[str] = sorted(
        str(rv.title or rv.citation or rv.url or rv.reference_id or "")
        for rv in ref_views
        if rv.title or rv.citation or rv.url or rv.reference_id
    )

    # ------------------------------------------------------------------
    # Provenance
    # ------------------------------------------------------------------
    graph_hash: str = packet.source.graph_hash or ""
    request_hash: str = packet.request.request_hash or ""
    node_ids: list[str] = sorted(node.node_id for node in nodes)
    edge_ids: list[str] = sorted(edge.edge_id for edge in edges)

    return {
        "topic": topic,
        "learning_goal": learning_goal,
        "prerequisites": prerequisites,
        "concept_map": concept_map,
        "main_path": main_path,
        "implementation": implementation,
        "derivation": derivation,
        "pitfalls": pitfalls,
        "self_check": self_check,
        "references": references,
        "graph_hash": graph_hash,
        "request_hash": request_hash,
        "node_ids": node_ids,
        "edge_ids": edge_ids,
    }


# ---------------------------------------------------------------------------
# Exporter Protocol entry point
# ---------------------------------------------------------------------------


def export(
    packet: "LearningSourcePacket",
    output_dir: Path,
    /,
) -> list[Path]:
    """Write a ``lesson.md`` file to *output_dir* and return its path.

    This function is the Exporter Protocol entry point; the compiler's Stage 9
    dispatches it automatically when ``"markdown"`` appears in
    ``request.exporters``.

    Parameters
    ----------
    packet:
        The fully-validated :class:`~akms_learn.models.LearningSourcePacket`
        produced by :func:`~akms_learn.compiler.compile_learning_source`.
    output_dir:
        Target directory.  Created on demand if it does not exist.

    Returns
    -------
    list[Path]
        A one-element list containing the absolute path to ``lesson.md``.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        autoescape=False,
    )

    # Pedagogical dispatch: route the pedagogical mode keys through the
    # 12-slot template + context. Every other mode key keeps the original
    # template + context for byte-identical backward compatibility.
    mode_key = _mode_key(packet)
    if mode_key in PLAN2_MODE_KEYS:
        template = env.get_template(_TEMPLATE_EXPANDED)
        context = _build_plan2_context(packet)
    else:
        template = env.get_template(_TEMPLATE_NAME)
        context = _build_context(packet)
    rendered = template.render(**context)

    lesson_path = out_dir / "lesson.md"
    lesson_path.write_text(rendered, encoding="utf-8")
    return [lesson_path]
