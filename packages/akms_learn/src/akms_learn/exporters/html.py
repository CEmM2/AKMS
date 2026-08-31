"""HTML exporter for Learning Source Packets.

Exporter Protocol conformance
-----------------------------
This module exposes a top-level :func:`export` function matching the
``Exporter`` callable protocol declared in :mod:`akms_learn.exporters`:

.. code-block:: python

    def export(
        packet: LearningSourcePacket,
        output_dir: Path,
        /,
    ) -> list[Path]: ...

The compiler dispatches this function from Stage 9 of
:func:`akms_learn.compiler.compile_learning_source` when ``"html"`` appears in
``request.exporters``.  Callers MUST NOT invoke this module's functions
directly — use :func:`~akms_learn.compiler.compile_learning_source` with
``exporters=["html"]`` instead.

Design invariants
-----------------
* **Capability-gated** — requires the ``html`` extra (``jinja2``).
  :func:`~akms_learn.capability_gates.require_capability` is called at the top
  of :func:`export` with capability ``"html_export"``; a missing extra raises
  :class:`~akms_learn.capability_gates.PreconditionError`.
* **Self-contained** — the output ``generated_preview.html`` embeds all CSS
  inline; there are no ``<link>``, ``<script src=``, or remote ``href``
  references.  Reviewers can open the file offline.
* **Pure** — no network, no LLM, no global state mutations.
* **Deterministic** — identical inputs produce byte-equal
  ``generated_preview.html``.  All iterable context values are sorted before
  being passed to the template.  Jinja2 ``autoescape=True`` is used for
  correctness.  No ``datetime.now()``, ``uuid``, or ``random`` in the context.
* **Consumes the LSP** — reads from ``packet.body`` (nodes, sections,
  warnings) rather than the source graph.
* **Provenance per section** — every rendered section block contains
  ``source_node_id``, ``source_path``, and ``line_range``.
* **Warnings panel** — all ``packet.warnings`` strings are embedded in a
  clearly delimited warnings panel in the page body.

Output
------
A single file ``generated_preview.html`` is written to *output_dir*.
No other files are produced.

Template
--------
The Jinja2 template lives at
``akms_learn/exporters/templates/preview.html.j2`` (relative to this file's
parent directory).  The template is rendered with ``autoescape=True`` so all
context values are HTML-escaped by default.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, FileSystemLoader

from akms_learn.capability_gates import require_capability
from akms_learn.exporters._mathaware import render_markdown

if TYPE_CHECKING:
    from akms_learn.models import LearningSourcePacket

__all__ = ["_build_context", "export"]

# ---------------------------------------------------------------------------
# Template resolution
# ---------------------------------------------------------------------------

_TEMPLATES_DIR: Path = Path(__file__).resolve().parent / "templates"
_TEMPLATE_NAME = "preview.html.j2"
_RICH_TEMPLATE_NAME = "preview_rich.html.j2"
_OUTPUT_NAME = "generated_preview.html"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_line_range(line_range: Any) -> str:
    """Render a line_range as ``"start-end"`` or ``"unknown"``."""
    if isinstance(line_range, (list, tuple)) and len(line_range) >= 2:
        try:
            start = int(line_range[0])
            end = int(line_range[1])
        except (TypeError, ValueError):
            return "unknown"
        if (start, end) == (0, 0):
            return "unknown"
        return f"{start}-{end}"
    return "unknown"


def _extract_section_content(
    included_sections: dict[str, Any],
    heading: str,
) -> str:
    """Return the content string for *heading* from a serialised sections dict."""
    entry = included_sections.get(heading)
    if entry is None:
        return ""
    if isinstance(entry, dict):
        return str(entry.get("content") or "")
    content = getattr(entry, "content", None)
    return str(content) if content else str(entry)


def _warning_text(warning: Any) -> str:
    """Return the human-readable text for one warning entry.

    Accepts both :class:`~akms_learn.warnings.LearningWarning` instances
    (with a ``message`` or ``code`` attribute) and plain strings (for tests
    that pass raw strings in ``packet.warnings``).
    """
    if isinstance(warning, str):
        return warning
    # LearningWarning or duck-typed equivalents
    message = getattr(warning, "message", None)
    if message:
        return str(message)
    code = getattr(warning, "code", None)
    if code:
        return str(code)
    return str(warning)


def _build_sections(
    packet: LearningSourcePacket, *, rich: bool = False
) -> list[dict[str, str]]:
    """Build the per-section context list for the template.

    Each dict has keys:
    * ``heading`` — section name (the heading string, e.g. ``"Concept"``)
    * ``content`` — section text or ``""`` when absent
    * ``source_node_id`` — node ID that supplied this content
    * ``source_path`` — source file path or ``"<unknown>"``
    * ``line_range`` — formatted ``"start-end"`` or ``"unknown"``

    Sections are emitted in reading-order (packet.body.reading_order), then
    alphabetical for nodes not in the reading order.  Within each node, headings
    are emitted in sorted order for determinism.

    The section list is built per-node: one entry per (node, heading) pair where
    content is non-empty.  Empty sections are still emitted with the
    ``"_no content_"`` marker to guarantee provenance coverage.
    """
    node_by_id: dict[str, Any] = {n.node_id: n for n in packet.body.nodes}
    reading_order = list(packet.body.reading_order or [])
    seen: set[str] = set(reading_order)
    fallback_tail = sorted(
        n.node_id for n in packet.body.nodes if n.node_id not in seen
    )
    ordered_node_ids = reading_order + fallback_tail
    ordered_nodes = [node_by_id[nid] for nid in ordered_node_ids if nid in node_by_id]

    sections: list[dict[str, str]] = []
    for node in ordered_nodes:
        node_id = str(node.node_id)
        src_path = str(getattr(node, "source_path", None) or "<unknown>")
        line_range = _format_line_range(getattr(node, "line_range", None))
        included = getattr(node, "included_sections", {}) or {}

        # Collect all headings for this node, sorted for determinism
        headings = sorted(included.keys())
        if not headings:
            # Node has no sections — emit a placeholder section so provenance is visible
            sections.append(
                {
                    "heading": node_id,
                    "content": "",
                    "source_node_id": node_id,
                    "source_path": src_path,
                    "line_range": line_range,
                }
            )
            continue

        for heading in headings:
            content = _extract_section_content(included, heading)
            content = content.strip() if content else ""
            entry: dict[str, str] = {
                "heading": f"{node_id} / {heading}",
                "content": content,
                "source_node_id": node_id,
                "source_path": src_path,
                "line_range": line_range,
            }
            if rich:
                entry["content_html"] = render_markdown(content) if content else ""
            sections.append(entry)

    return sections


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


def _build_context(packet: LearningSourcePacket) -> dict[str, Any]:
    """Build the Jinja2 template context dict from *packet*.

    All list values are deterministically ordered so that re-rendering the
    same LSP always produces byte-equal output.

    Parameters
    ----------
    packet:
        A fully-assembled :class:`~akms_learn.models.LearningSourcePacket`.

    Returns
    -------
    dict
        Flat context dict consumed by ``preview.html.j2``.
    """
    # ------------------------------------------------------------------
    # Scalar metadata
    # ------------------------------------------------------------------
    topic: str = (
        str(packet.request.topic) if packet.request.topic else "<unknown topic>"
    )
    packet_id: str = str(packet.packet_id)
    graph_hash: str = str(packet.source.graph_hash or "")
    graph_version: str = str(getattr(packet.source, "graph_version", None) or "")
    compiler_name: str = str(getattr(packet.compiler, "name", "") or "")
    compiler_version: str = str(getattr(packet.compiler, "version", "") or "")
    request_hash: str = str(packet.request.request_hash or "")
    generation_option: str = str(
        getattr(packet.request, "generation_option", None) or ""
    )
    learning_goal: str = (
        str(packet.request.goal or "") if getattr(packet.request, "goal", None) else ""
    )

    # ------------------------------------------------------------------
    # Warnings — all warning strings, in sorted order for determinism.
    # ------------------------------------------------------------------
    raw_warnings = list(packet.warnings or [])
    warnings: list[str] = sorted(_warning_text(w) for w in raw_warnings)

    # ------------------------------------------------------------------
    # Sections — per-node, per-heading blocks with provenance. Rich mode
    # (opt-in --rich-html) also attaches rendered ``content_html``.
    # ------------------------------------------------------------------
    rich: bool = bool(getattr(packet.request, "rich_html", False))
    sections: list[dict[str, str]] = _build_sections(packet, rich=rich)

    # ------------------------------------------------------------------
    # Derived counts
    # ------------------------------------------------------------------
    node_count: int = len(packet.body.nodes)

    return {
        "topic": topic,
        "packet_id": packet_id,
        "graph_hash": graph_hash,
        "graph_version": graph_version,
        "compiler_name": compiler_name,
        "compiler_version": compiler_version,
        "request_hash": request_hash,
        "generation_option": generation_option,
        "learning_goal": learning_goal,
        "warnings": warnings,
        "sections": sections,
        "node_count": node_count,
        "rich": rich,
    }


# ---------------------------------------------------------------------------
# Exporter Protocol entry point
# ---------------------------------------------------------------------------


def export(
    packet: LearningSourcePacket,
    output_dir: Path,
    /,
) -> list[Path]:
    """Write a ``generated_preview.html`` file to *output_dir* and return its path.

    This function is the Exporter Protocol entry point; the compiler's Stage 9
    dispatches it automatically when ``"html"`` appears in
    ``request.exporters``.

    The emitted HTML:

    * Is a single self-contained file with all CSS embedded inline.
    * Renders a metadata panel (packet ID, graph hash, compiler version, …).
    * Renders a warnings panel containing all ``packet.warnings`` messages.
    * Renders one section card per (node, heading) pair, each with a
      provenance footer (``source_node_id``, ``source_path``, ``line_range``).
    * Is deterministic: identical LSP inputs → byte-equal HTML output.

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
        A one-element list containing the absolute path to
        ``generated_preview.html``.

    Raises
    ------
    PreconditionError
        When the ``html`` extra (``jinja2``) is not installed.
    """
    # ------------------------------------------------------------------
    # Capability gate — first operation.
    # ------------------------------------------------------------------
    require_capability("html_export")

    # ------------------------------------------------------------------
    # Build context (deterministic).
    # ------------------------------------------------------------------
    context = _build_context(packet)

    # ------------------------------------------------------------------
    # Render template.
    # ------------------------------------------------------------------
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=True,
        keep_trailing_newline=True,
    )
    # Opt-in rich rendering selects a separate template (MathJax + rendered
    # algorithms); the default template is untouched so its self-contained /
    # offline guarantee and byte-stability are preserved.
    template_name = _RICH_TEMPLATE_NAME if context.get("rich") else _TEMPLATE_NAME
    template = env.get_template(template_name)
    rendered: str = template.render(**context)

    # ------------------------------------------------------------------
    # Write to disk.
    # ------------------------------------------------------------------
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    html_path = out_dir / _OUTPUT_NAME
    html_path.write_text(rendered, encoding="utf-8")

    return [html_path]
