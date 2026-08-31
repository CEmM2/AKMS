"""Notebook exporter for Learning Source Packets (notebook_source mode).

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
:func:`akms_learn.compiler.compile_learning_source` when ``"notebook"`` is in
``request.exporters``.  Callers MUST NOT invoke this function directly — use
:func:`~akms_learn.compiler.compile_learning_source` with
``exporters=["notebook"]`` instead.

Design invariants
-----------------
* **Capability-gated** — requires the ``notebook`` extra (``nbformat``).
  :func:`~akms_learn.capability_gates.require_capability` is called at the
  top of :func:`export`; a missing extra raises
  :class:`~akms_learn.capability_gates.PreconditionError`.
* **No execution** — this module MUST NOT import or call ``nbclient``,
  ``jupyter``, ``subprocess``, ``exec``, ``eval``, or ``%run`` under any code
  path.  ``no_execute=True`` is the default; the exporter never runs cells.
* **Pure** — no network, no LLM, no global state mutations.
* **Deterministic** — identical inputs produce byte-equal ``.ipynb`` outputs
  (same packet → same file, modulo packet timestamp).  All dict/list
  iterations are sorted before rendering.
* **nbformat validation** — :func:`nbformat.validate` is called on the
  assembled notebook before writing.  Any validation failure raises
  :class:`~akms_learn.validation.PacketValidationError`.
* **Safety classification** — reuses
  :func:`~akms_learn.modes.notebook_source._classify_code_safety`
  to decide whether a snippet becomes a code cell (``"safe"``) or a Markdown
  cell with fenced content (``"unknown"``/``"unsafe"``).  Prefer over-degrade.
* **Provenance footer** — every Markdown cell ends with a fenced provenance
  block containing ``source_node_id``, ``source_path``, and ``line_range``.

Notebook metadata layout
---------------------------------
``nb.metadata`` carries::

    {
        "akms": {
            "packet_id":        <str>,
            "graph_version":    <str>,
            "compiler_version": <str>,
            "schema":           <str>,
        },
        "execution": {
            "no_execute":         True,   # default — exporter never runs cells
            "illustrative_only":  False,
            "adapter_executable": False,
        },
        "kernelspec": {
            "display_name": "Python 3",
            "language":     "python",
            "name":         "python3",
        },
        "language_info": {"name": "python"},
    }

Six-section canonical order (from NOTEBOOK_SECTIONS in notebook_source.py)
---------------------------------------------------------------------------
1. ``explanation``           — concept / motivation prose
2. ``equations``             — formal derivation text
3. ``minimal implementation``— code cell if safe, Markdown fenced block if not
4. ``diagnostics``           — pitfalls / common mistakes
5. ``verification``          — self-check prompts
6. ``exercises``             — practice problems
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any

import nbformat

from akms_learn.capability_gates import require_capability
from akms_learn.modes.notebook_source import (
    NOTEBOOK_SECTIONS,
    SECTION_PLACEHOLDER,
    _classify_code_safety,
)
from akms_learn.modes.notebook_source import (
    _SECTION_TO_HEADINGS as _SECTION_TO_HEADINGS,
)
from akms_learn.validation import PacketValidationError

if TYPE_CHECKING:
    from akms_learn.models import LearningSourcePacket

__all__ = ["export"]

# The section→heading map is imported (not duplicated) from
# ``notebook_source`` so the exporter cannot drift from the compiler stage
# that assembles ``included_sections``. See the import above.


# ---------------------------------------------------------------------------
# Provenance helpers
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


def _provenance_footer(
    source_node_id: str,
    source_path: str,
    line_range: Any,
) -> str:
    """Return the fenced provenance block appended to every Markdown cell."""
    lr = _format_line_range(line_range)
    return (
        "\n\n---\n"
        "```provenance\n"
        f"source_node_id: {source_node_id}\n"
        f"source_path: {source_path}\n"
        f"line_range: {lr}\n"
        "```"
    )


# ---------------------------------------------------------------------------
# Section content extraction from LearningNodeView.included_sections
# ---------------------------------------------------------------------------


def _extract_section_content(
    included_sections: dict[str, Any],
    heading: str,
) -> str:
    """Return the content string for *heading* from a serialised sections dict.

    ``included_sections`` values are serialised ``SectionView`` dicts
    (carrying a ``"content"`` key) or raw strings — the two shapes the
    compiler ever emits. Any other type is treated as no content.
    """
    entry = included_sections.get(heading)
    if isinstance(entry, dict):
        return str(entry.get("content") or "")
    if isinstance(entry, str):
        return entry
    return ""


def _find_slot_content(
    slot: str,
    nodes: list[Any],
) -> tuple[str, str, str, Any]:
    """Find content for *slot* across all nodes (reading-order preserved).

    Returns ``(content, source_node_id, source_path, line_range)``.
    Falls back to ``(SECTION_PLACEHOLDER, first_node_id, "unknown", None)``
    when no node carries matching heading content.
    """
    headings = _SECTION_TO_HEADINGS.get(slot, ())
    primary_node_id = str(nodes[0].node_id) if nodes else "<unknown>"

    for node in nodes:
        sections = getattr(node, "included_sections", {}) or {}
        for heading in headings:
            content = _extract_section_content(sections, heading)
            if content.strip():
                return (
                    content.strip(),
                    str(node.node_id),
                    str(getattr(node, "source_path", "<unknown>") or "<unknown>"),
                    getattr(node, "line_range", None),
                )

    # Fallback: first node's id as provenance anchor
    first_node = nodes[0] if nodes else None
    first_path = (
        str(getattr(first_node, "source_path", "<unknown>") or "<unknown>")
        if first_node
        else "<unknown>"
    )
    first_lr = getattr(first_node, "line_range", None) if first_node else None
    return SECTION_PLACEHOLDER, primary_node_id, first_path, first_lr


# ---------------------------------------------------------------------------
# Cell builders
# ---------------------------------------------------------------------------


def _stable_cell_id(source: str, index: int, prefix: str = "c") -> str:
    """Return a deterministic, unique cell ID for *index* + *source*.

    nbformat 4.5+ requires cells to carry a unique ``id`` (1-64 chars,
    ``[a-zA-Z0-9_-]``).  We include the cell *index* in the digest input so
    cells with identical source content (e.g. multiple SECTION_PLACEHOLDER
    cells) still get distinct, stable IDs.
    """
    material = f"{index}:{source}"
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


class _CellBuilder:
    """Stateful helper that assigns stable sequential IDs to emitted cells."""

    def __init__(self) -> None:
        self._index: int = 0

    def markdown(self, source: str) -> nbformat.NotebookNode:
        """Return an nbformat v4 Markdown cell with a deterministic id."""
        cell = nbformat.v4.new_markdown_cell(source=source)
        cell["id"] = _stable_cell_id(source, self._index, "md")
        self._index += 1
        return cell

    def code(self, source: str) -> nbformat.NotebookNode:
        """Return an nbformat v4 code cell with no outputs and a deterministic id."""
        cell = nbformat.v4.new_code_cell(source=source)
        cell["outputs"] = []
        cell["execution_count"] = None
        cell["id"] = _stable_cell_id(source, self._index, "co")
        self._index += 1
        return cell


# ---------------------------------------------------------------------------
# Notebook assembly helpers
# ---------------------------------------------------------------------------


def _build_section_cells(
    nodes: list[Any],
    builder: _CellBuilder,
) -> list[nbformat.NotebookNode]:
    """Build an ordered list of nbformat cells from the packet nodes.

    For each of the six canonical notebook sections:

    * Find content from the first matching node (reading order).
    * For ``minimal implementation``: apply safety classification.
      - ``safe``            → code cell
      - ``unknown``/``unsafe`` → Markdown cell with fenced code + note
    * For all other slots → Markdown cell.
    * Append a provenance footer to every Markdown cell.
    * Emit a section-heading Markdown cell before the content cell.
    """
    cells: list[nbformat.NotebookNode] = []

    for slot in NOTEBOOK_SECTIONS:
        content, node_id, src_path, line_range = _find_slot_content(slot, nodes)
        footer = _provenance_footer(node_id, src_path, line_range)

        # Section heading cell (Markdown, carries provenance for the heading too)
        heading_source = f"## {slot.title()}{footer}"
        cells.append(builder.markdown(heading_source))

        # Content cell
        if slot == "minimal implementation" and content != SECTION_PLACEHOLDER:
            safety = _classify_code_safety(content)
            if safety == "safe":
                cells.append(builder.code(content))
            else:
                # Degrade: fenced block + explanatory note
                degraded = (
                    f"> **Note:** This snippet was classified as `{safety}` "
                    f"and is shown for illustration only — it is NOT executable.\n\n"
                    f"```python\n{content}\n```"
                    f"{footer}"
                )
                cells.append(builder.markdown(degraded))
        else:
            # Markdown content + provenance footer
            md_source = f"{content}{footer}"
            cells.append(builder.markdown(md_source))

    return cells


def _build_notebook_metadata(packet: "LearningSourcePacket") -> dict[str, Any]:
    """Build the ``nb.metadata`` dict for the exported notebook.

    Keys:
    * ``akms.packet_id``
    * ``akms.graph_version``
    * ``akms.compiler_version``
    * ``akms.schema``
    * ``execution.no_execute`` / ``execution.illustrative_only`` /
      ``execution.adapter_executable``
    """
    graph_version = getattr(packet.source, "graph_version", None) or ""
    compiler_version = getattr(packet.compiler, "version", "") or ""

    return {
        "akms": {
            "packet_id": str(packet.packet_id),
            "graph_version": str(graph_version),
            "compiler_version": str(compiler_version),
            "schema": "v2",
        },
        "execution": {
            "no_execute": True,
            "illustrative_only": False,
            "adapter_executable": False,
        },
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
        },
    }


# ---------------------------------------------------------------------------
# Exporter Protocol entry point
# ---------------------------------------------------------------------------


def export(
    packet: "LearningSourcePacket",
    output_dir: Path,
    /,
) -> list[Path]:
    """Write a ``.ipynb`` notebook to *output_dir* and return its path.

    This function is the Exporter Protocol entry point; the compiler's Stage 9
    dispatches it automatically when ``"notebook"`` appears in
    ``request.exporters``.

    The emitted notebook:

    * Is validated by :func:`nbformat.validate` before writing — any
      validation failure raises :class:`~akms_learn.validation.PacketValidationError`.
    * Has ``no_execute=True`` in notebook-level metadata.
    * Contains one section heading + one content cell per canonical notebook
      section, drawn from the LSP's node ``included_sections`` (provenance
      footer on every Markdown cell; unsafe snippets → Markdown cells).
    * Never invokes ``nbclient``, ``jupyter``, ``subprocess``, ``exec``,
      or ``eval``.

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
        A one-element list containing the absolute path to the ``.ipynb`` file.

    Raises
    ------
    PreconditionError
        When the ``notebook`` extra (``nbformat``) is not installed.
    PacketValidationError
        When the assembled notebook fails :func:`nbformat.validate`.
    """
    # ------------------------------------------------------------------
    # Capability gate — first operation.
    # ------------------------------------------------------------------
    require_capability("notebook_export")

    # ------------------------------------------------------------------
    # Build notebook.
    # ------------------------------------------------------------------
    nb = nbformat.v4.new_notebook()

    # Notebook-level metadata.
    nb.metadata.update(_build_notebook_metadata(packet))

    # Single builder tracks cell index across all cells for deterministic IDs.
    builder = _CellBuilder()

    # Title cell. Its provenance anchors to the packet itself rather than any
    # single node, so it uses the reserved sentinel node id ``<packet>`` —
    # angle-bracketed so it can never collide with a real node_id.
    topic = str(packet.request.topic) if packet.request.topic else "<unknown topic>"
    title_footer = _provenance_footer(
        source_node_id="<packet>",
        source_path=str(packet.source.graph_path or "<unknown>"),
        line_range=None,
    )
    nb.cells.append(builder.markdown(f"# {topic}{title_footer}"))

    # Determine node reading order (reading_order list → node_id order).
    node_by_id: dict[str, Any] = {n.node_id: n for n in packet.body.nodes}
    reading_order = list(packet.body.reading_order or [])
    seen: set[str] = set(reading_order)
    fallback_tail = sorted(
        n.node_id for n in packet.body.nodes if n.node_id not in seen
    )
    ordered_node_ids = reading_order + fallback_tail
    ordered_nodes = [node_by_id[nid] for nid in ordered_node_ids if nid in node_by_id]

    # Section cells.
    if ordered_nodes:
        section_cells = _build_section_cells(ordered_nodes, builder)
        nb.cells.extend(section_cells)

    # ------------------------------------------------------------------
    # Validate before writing.
    # ------------------------------------------------------------------
    try:
        nbformat.validate(nb)
    except nbformat.ValidationError as exc:
        raise PacketValidationError([f"nbformat validation failed: {exc}"]) from exc

    # ------------------------------------------------------------------
    # Write to disk.
    # ------------------------------------------------------------------
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    notebook_path = out_dir / "lesson.ipynb"
    notebook_path.write_text(
        nbformat.writes(nb),
        encoding="utf-8",
    )

    return [notebook_path]
