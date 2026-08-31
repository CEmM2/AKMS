"""Mode: notebook_source — six-section notebook compiler.

Generates a notebook-oriented Learning Source Packet shaped for export as a
Jupyter notebook.  The lesson body contains exactly **six** sections in
canonical deterministic order:

    1. explanation          — Markdown prose from concept / motivation / summary
    2. equations            — Formal derivation / definition text
    3. minimal implementation — Code or explanatory cells (safe-code classified)
    4. diagnostics          — Pitfall / common-mistake notes
    5. verification         — Self-check / assessment prompts
    6. exercises            — Practice problems

Design decisions
----------------
* **Capability-gated** — the mode requires the ``notebook`` extra
  (``nbformat``) to be importable.  ``require_capability("notebook_source")``
  is called at the top of :func:`notebook_source_mode`; a missing extra raises
  :class:`~akms_learn.capability_gates.PreconditionError`.
* **No execution at compile time** — this module MUST NOT import or call
  ``nbclient``, ``jupyter``, ``subprocess``, ``exec``, ``eval``, or ``%run``
  under any code path.  A canary test enforces this at source-byte level.
* **Safe-code classifier** — :func:`_classify_code_safety` applies a tight
  allowlist of safe stdlib modules.  Unknown or IO/network code degrades to an
  explanatory cell that renders the snippet as fenced text.  Prefer
  false-negatives (over-degrade) over false-positives.
* **Provenance on every cell** — every cell payload (both Markdown-kind and
  code-kind) carries ``provenance = {source_node_id, source_path, line_range}``.
* **Deterministic output** — all dict/set iteration is sorted; no timestamps in
  generated cell payloads.
* **Notebook metadata block** — the returned LSP carries an
  ``akms_notebook_metadata`` key under ``lesson_body`` with:
  ``akms.packet_id``, ``akms.graph_version``, ``akms.compiler_version``,
  ``akms.schema`` plus the execution-mode triplet
  ``no_execute=True`` (default), ``illustrative_only=False``,
  ``adapter_executable=False``.
* **No .ipynb file emission** — notebook file export is owned by the
  notebook exporter.  This
  compiler only produces the LSP shape; it never writes any file.
* **Imports at module top** — no mid-module imports.
* **Pure function** — never mutates ``graph_slice``, ``ordered_nodes``, or
  ``request``.

Slot → approved-heading map
---------------------------
The six notebook sections are mapped to AKMS v2 approved headings:

* ``explanation``            — "concept", "motivation", fallback: summary/body
* ``equations``              — "derivation"
* ``minimal implementation`` — "implementation", "worked_example"
* ``diagnostics``            — "pitfalls"
* ``verification``           — "assessment"
* ``exercises``              — "assessment" (secondary, distinct from verification)

When a heading appears in both ``verification`` and ``exercises`` slots, the
same content is used for both (identical to the pedagogical_template pattern
for dual-slot headings).  A ``notebook_section_missing`` warning is emitted
once per missing slot.

Warning codes
-------------
``notebook_section_missing``
    Emitted once per missing section slot; ``source_ref`` is the primary
    source node id.
``notebook_unsafe_code_degraded``
    Emitted when a code candidate is classified ``unsafe`` or ``unknown`` and
    is emitted as an explanatory cell instead of a code cell.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from akms_learn.capability_gates import require_capability
from akms_learn.graph_import import GraphSlice
from akms_learn.models import LearningWarning
from akms_learn.requests import LearningRequest
from akms_learn.section_extraction import (
    ExtractedSection,
    extract_sections_from_node,
)

__all__ = [
    "NOTEBOOK_SECTIONS",
    "SECTION_PLACEHOLDER",
    "NotebookSourceResult",
    "notebook_source_mode",
    "_classify_code_safety",
]

# ---------------------------------------------------------------------------
# Six-section canonical order — immutable.
# DO NOT reorder; the notebook exporter depends on this exact sequence.
# ---------------------------------------------------------------------------

NOTEBOOK_SECTIONS: tuple[str, ...] = (
    "explanation",
    "equations",
    "minimal implementation",
    "diagnostics",
    "verification",
    "exercises",
)

# Placeholder text for missing sections (consistent with pedagogical_template).
SECTION_PLACEHOLDER: str = "[No content available]"

# Compiler version string embedded in notebook metadata.
_COMPILER_VERSION: str = "1.0"

# AKMS schema version embedded in notebook metadata.
_AKMS_SCHEMA: str = "v2"

# ---------------------------------------------------------------------------
# Safe-code classifier: allowed stdlib modules.
# ---------------------------------------------------------------------------
#
# Only modules whose canonical names appear in this set may be imported in
# code that is classified as ``"safe"``.  Anything else → ``"unsafe"`` or
# ``"unknown"``.  The set is kept deliberately small; prefer false-negatives
# (over-degrade to explanatory cells) over false-positives (emit unsafe code
# as runnable cells).

_SAFE_STDLIB_MODULES: frozenset[str] = frozenset(
    {
        "math",
        "statistics",
        "collections",
        "itertools",
        "functools",
        "dataclasses",
        "typing",
    }
)

# Pattern matching *any* import statement so we can extract module names.
# Group 1: "import foo, bar" form.
# Group 2: "from foo.bar import ..." form — captures dotted module paths.
_IMPORT_RE = re.compile(
    r"^\s*(?:import\s+([\w,\s]+)|from\s+([\w.]+)\s+import\s+)", re.MULTILINE
)

# Detects "from X import *" — must be checked before the no-imports early-return.
_STAR_IMPORT_RE = re.compile(r"^\s*from\s+[\w.]+\s+import\s+\*", re.MULTILINE)

# Top-level package names whose presence in an import statement classifies the
# snippet as ``"unsafe"``. Comparison is module-name-granular (see Step 2 below)
# so multi-import lines like ``import math, os`` are caught reliably.
_UNSAFE_MODULES: frozenset[str] = frozenset(
    {
        "os",
        "subprocess",
        "requests",
        "urllib",
        "socket",
        "shutil",
        "sys",
    }
)

# Regex form kept for the raw-text fast path (Step 1) — catches snippets where
# Step 2's module-name extraction would have run anyway, plus the dotted-from
# case where an attribute access against an unsafe module isn't an import.
_UNSAFE_IMPORT_RE = re.compile(
    r"\bfrom\s+(?:os|subprocess|requests|urllib|socket|shutil|sys)\b"
    r"|"
    r"\bimport\s+(?:os|subprocess|requests|urllib|socket|shutil|sys)\b",
    re.MULTILINE,
)
_UNSAFE_CALL_RE = re.compile(
    r"open\s*\(|exec\s*\(|eval\s*\(|compile\s*\(|__import__\s*\(",
    re.MULTILINE,
)

# ---------------------------------------------------------------------------
# Mapping: notebook section name → approved headings to search (priority order)
# ---------------------------------------------------------------------------

_SECTION_TO_HEADINGS: dict[str, tuple[str, ...]] = {
    "explanation": ("concept", "motivation"),
    "equations": ("derivation",),
    "minimal implementation": ("implementation", "worked_example"),
    "diagnostics": ("pitfalls",),
    "verification": ("assessment",),
    "exercises": ("assessment",),
}


# ---------------------------------------------------------------------------
# Safe-code classifier
# ---------------------------------------------------------------------------


def _classify_code_safety(
    snippet: str,
) -> Literal["safe", "unsafe", "unknown"]:
    """Classify a code snippet as ``"safe"``, ``"unsafe"``, or ``"unknown"``.

    Classification rules (in priority order):

    1. Any match of ``_UNSAFE_IMPORT_RE`` or ``_UNSAFE_CALL_RE`` → ``"unsafe"``.
    2. All ``import`` statements name only modules in ``_SAFE_STDLIB_MODULES``
       **and** no ``import *`` appears → ``"safe"``.
    3. Otherwise → ``"unknown"`` (over-degrade).

    Parameters
    ----------
    snippet:
        Raw Python source code to classify.

    Returns
    -------
    Literal["safe", "unsafe", "unknown"]
    """
    if not snippet or not snippet.strip():
        return "unknown"

    # Step 0 — star-import check BEFORE any early-return; gated on regex so it
    # does not mis-trigger on docstrings that mention "import *" in prose.
    if _STAR_IMPORT_RE.search(snippet):
        return "unknown"

    # Step 1 — immediate unsafe patterns (module-level and call-level).
    if _UNSAFE_IMPORT_RE.search(snippet):
        return "unsafe"
    if _UNSAFE_CALL_RE.search(snippet):
        return "unsafe"

    # Step 2 — collect all imported top-level package names.
    imported_modules: list[str] = []
    for match in _IMPORT_RE.finditer(snippet):
        # Group 1: "import foo, bar" form — names may be dotted ("import os.path")
        if match.group(1):
            for raw in match.group(1).split(","):
                name = raw.strip().split()[0]  # "foo as f" → "foo"
                if name:
                    # Take the top-level component of a dotted name.
                    imported_modules.append(name.split(".")[0])
        # Group 2: "from foo.bar import ..." form — may be a dotted path.
        if match.group(2):
            dotted = match.group(2).strip()
            # Take the top-level package (everything before the first ".").
            imported_modules.append(dotted.split(".")[0])

    if not imported_modules:
        # No imports at all — safe (unsafe calls already excluded in Step 1).
        return "safe"

    # Step 3a — any module-name match against the unsafe set is ``unsafe``.
    # Catches multi-import lines like ``import math, os`` that the raw-text
    # regex in Step 1 cannot label reliably.
    if any(mod in _UNSAFE_MODULES for mod in imported_modules):
        return "unsafe"

    # Step 3b — every top-level module must be in the whitelist.
    # If a module is not in the whitelist AND not in the unsafe set, it is
    # unknown third-party code: prefer false-negative (over-degrade).
    if all(mod in _SAFE_STDLIB_MODULES for mod in imported_modules):
        return "safe"

    return "unknown"


# ---------------------------------------------------------------------------
# Cell payload builders
# ---------------------------------------------------------------------------


def _make_code_cell(
    source: str,
    source_node_id: str,
    source_path: str,
    line_range: tuple[int, int] | None,
) -> dict[str, Any]:
    """Build a code-cell payload for a safe snippet."""
    return {
        "cell_type": "code",
        "source": source,
        "provenance": {
            "source_node_id": source_node_id,
            "source_path": source_path,
            "line_range": line_range,
        },
    }


def _make_explanatory_cell(
    content: str,
    source_node_id: str,
    source_path: str,
    line_range: tuple[int, int] | None,
    *,
    fenced_as_code: bool = False,
) -> dict[str, Any]:
    """Build an explanatory (Markdown) cell payload.

    When *fenced_as_code* is ``True``, the content is wrapped in a fenced
    code block so degraded snippets render with syntax highlighting while
    remaining non-executable.
    """
    if fenced_as_code:
        body = f"```python\n{content}\n```"
    else:
        body = content
    return {
        "cell_type": "markdown",
        "source": body,
        "provenance": {
            "source_node_id": source_node_id,
            "source_path": source_path,
            "line_range": line_range,
        },
    }


# ---------------------------------------------------------------------------
# Section-level helpers
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
    nodes_by_id: dict[str, dict[str, Any]],
) -> tuple[str, str | None]:
    """Return (content, source_node_id) for a notebook section slot.

    Searches nodes in ``ordered_nodes`` order.  Returns the content from the
    first node that carries a matching approved heading, or
    ``(SECTION_PLACEHOLDER, None)`` if nothing matches.
    """
    target_headings = _SECTION_TO_HEADINGS.get(slot, ())
    if not target_headings:
        return SECTION_PLACEHOLDER, None

    for nid in ordered_nodes:
        extracted_list = sections_by_node.get(nid, [])
        for section in extracted_list:
            if section.normalized_name in target_headings:
                return section.content, nid

    # Fallback: check node body/summary for content-rich nodes.
    for nid in ordered_nodes:
        node = nodes_by_id.get(nid) or {}
        body = node.get("body") or node.get("markdown") or node.get("summary") or ""
        if body.strip():
            return body.strip(), nid

    return SECTION_PLACEHOLDER, None


def _node_source_path(node: dict[str, Any]) -> str:
    """Return the source_path of *node*, with a safe fallback."""
    return str(node.get("source_path") or "<unknown>")


def _node_line_range(node: dict[str, Any]) -> tuple[int, int] | None:
    """Return the line_range of *node* as (start, end), or ``None``."""
    lr = node.get("line_range")
    if isinstance(lr, (list, tuple)) and len(lr) >= 2:
        try:
            return (int(lr[0]), int(lr[1]))
        except (TypeError, ValueError):
            pass
    return None


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class NotebookSourceResult:
    """Structured result from :func:`notebook_source_mode`.

    Attributes
    ----------
    sections:
        Ordered dict mapping each of the six notebook section names to a list
        of cell payloads.  Each cell payload is a dict with at least
        ``cell_type``, ``source``, and ``provenance`` keys.
    notebook_metadata:
        Dict with ``akms.*`` provenance keys plus the execution-mode triplet.
    source_node_ids:
        Sorted list of all node ids that contributed content to the packet.
    edge_ids:
        Sorted list of all edge ids present in the graph slice.
    warnings:
        List of :class:`~akms_learn.models.LearningWarning` instances.
    """

    __slots__ = (
        "sections",
        "notebook_metadata",
        "source_node_ids",
        "edge_ids",
        "warnings",
    )

    def __init__(
        self,
        sections: dict[str, list[dict[str, Any]]],
        notebook_metadata: dict[str, Any],
        source_node_ids: list[str],
        edge_ids: list[str],
        warnings: list[LearningWarning],
    ) -> None:
        self.sections = sections
        self.notebook_metadata = notebook_metadata
        self.source_node_ids = source_node_ids
        self.edge_ids = edge_ids
        self.warnings = warnings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def notebook_source_mode(
    graph_slice: GraphSlice,
    ordered_nodes: list[str],
    request: LearningRequest,
    *,
    packet_id: str = "",
    graph_version: str = "",
) -> tuple["NotebookSourceResult", list[LearningWarning]]:
    """Build the notebook_source mode view.

    Requires the ``notebook`` extra (``nbformat``) to be installed.  If the
    extra is absent, :class:`~akms_learn.capability_gates.PreconditionError`
    is raised before any computation is done.

    Pure function — never mutates ``graph_slice``, ``ordered_nodes``, or
    ``request``.

    Parameters
    ----------
    graph_slice:
        Immutable :class:`~akms_learn.graph_import.GraphSlice` from the
        compiler pipeline.
    ordered_nodes:
        Node id list in learning order.
    request:
        The validated :class:`~akms_learn.requests.LearningRequest`.
    packet_id:
        Packet identifier from the compiler; embedded in notebook metadata.
    graph_version:
        Graph version string; embedded in notebook metadata.

    Returns
    -------
    (result, warnings)
        ``result`` is a :class:`NotebookSourceResult`.
        ``warnings`` is a list of :class:`~akms_learn.models.LearningWarning`
        (same list as ``result.warnings``).

    Raises
    ------
    PreconditionError
        When the ``notebook`` extra is not installed.
    """
    # ------------------------------------------------------------------
    # Capability gate — must be the very first operation.
    # ------------------------------------------------------------------
    require_capability("notebook_source")

    # ------------------------------------------------------------------
    # Index nodes by id (read-only copies).
    # ------------------------------------------------------------------
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for raw in graph_slice.nodes:
        nid = raw.get("node_id")
        if nid is not None:
            nodes_by_id[nid] = dict(raw)

    primary_source_ref: str = ordered_nodes[0] if ordered_nodes else "<unknown>"

    # ------------------------------------------------------------------
    # Extract sections from every node.
    # ------------------------------------------------------------------
    extracted_by_node = _collect_sections_by_node(ordered_nodes, nodes_by_id)

    # ------------------------------------------------------------------
    # Build each of the six notebook section slots.
    # ------------------------------------------------------------------
    section_cells: dict[str, list[dict[str, Any]]] = {}
    warnings: list[LearningWarning] = []

    for slot in NOTEBOOK_SECTIONS:
        content, source_nid = _find_content_for_slot(
            slot, ordered_nodes, extracted_by_node, nodes_by_id
        )

        if content == SECTION_PLACEHOLDER or not content.strip():
            warnings.append(
                LearningWarning(
                    severity="warning",
                    code="notebook_section_missing",
                    source_ref=source_nid or primary_source_ref,
                    message=(
                        f"Notebook section {slot!r} has no content from "
                        f"source nodes; placeholder inserted."
                    ),
                )
            )
            node = nodes_by_id.get(source_nid or primary_source_ref) or {}
            cells = [
                _make_explanatory_cell(
                    SECTION_PLACEHOLDER,
                    source_node_id=source_nid or primary_source_ref,
                    source_path=_node_source_path(node),
                    line_range=_node_line_range(node),
                )
            ]
            section_cells[slot] = cells
            continue

        # Determine the contributing node for provenance.
        node = nodes_by_id.get(source_nid or "") or {}
        src_path = _node_source_path(node)
        line_range = _node_line_range(node)
        node_id_for_prov = source_nid or primary_source_ref

        # For the ``minimal implementation`` slot, attempt safe-code
        # classification.  Other slots are always explanatory Markdown.
        if slot == "minimal implementation":
            safety = _classify_code_safety(content)
            if safety == "safe":
                cells = [
                    _make_code_cell(
                        source=content,
                        source_node_id=node_id_for_prov,
                        source_path=src_path,
                        line_range=line_range,
                    )
                ]
            else:
                # Degrade: emit explanatory cell, emit warning.
                warnings.append(
                    LearningWarning(
                        severity="warning",
                        code="notebook_unsafe_code_degraded",
                        source_ref=node_id_for_prov,
                        message=(
                            f"Code candidate for slot {slot!r} classified "
                            f"as {safety!r}; degrading to explanatory cell."
                        ),
                    )
                )
                cells = [
                    _make_explanatory_cell(
                        content=content,
                        source_node_id=node_id_for_prov,
                        source_path=src_path,
                        line_range=line_range,
                        fenced_as_code=True,
                    )
                ]
        else:
            cells = [
                _make_explanatory_cell(
                    content=content,
                    source_node_id=node_id_for_prov,
                    source_path=src_path,
                    line_range=line_range,
                )
            ]

        section_cells[slot] = cells

    # ------------------------------------------------------------------
    # Build notebook metadata block.
    # ------------------------------------------------------------------
    notebook_metadata: dict[str, Any] = {
        "akms": {
            "packet_id": packet_id,
            "graph_version": graph_version,
            "compiler_version": _COMPILER_VERSION,
            "schema": _AKMS_SCHEMA,
        },
        "execution_mode": {
            "no_execute": True,
            "illustrative_only": False,
            "adapter_executable": False,
        },
    }

    # ------------------------------------------------------------------
    # Provenance lists (deterministic — sorted).
    # ------------------------------------------------------------------
    source_node_ids = sorted(nid for nid in ordered_nodes if nid in nodes_by_id)
    edge_ids = sorted(
        str(e.get("edge_id", "")) for e in graph_slice.edges if e.get("edge_id")
    )

    result = NotebookSourceResult(
        sections=section_cells,
        notebook_metadata=notebook_metadata,
        source_node_ids=source_node_ids,
        edge_ids=edge_ids,
        warnings=warnings,
    )
    return result, warnings
