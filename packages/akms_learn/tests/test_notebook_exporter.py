"""Tests for notebook.py exporter via nbformat.

Covers all five acceptance criteria:

Output .ipynb passes ``nbformat.validate`` without errors.
Notebook metadata contains ``akms.packet_id``, ``akms.graph_version``,
      ``akms.compiler_version``, ``akms.schema``, plus the
      ``no_execute``/``illustrative_only``/``adapter_executable`` triplet.
Default mode is ``no_execute=True``; exporter never invokes
      nbclient/jupyter/subprocess.
Every Markdown cell carries a provenance footer with
      ``source_node_id``, ``source_path``, and ``line_range``.
When the LSP marks a snippet as unsafe, the exporter emits a Markdown
      cell, not a code cell.

Additional tests:
  - Exporter is registered in KNOWN_EXPORTERS.
  - Exporter raises PreconditionError when the notebook extra is absent.
  - Output file is named ``lesson.ipynb`` and is written to output_dir.
  - Deterministic output: two calls on the same packet produce the same file.
  - Safe snippet emits a code cell.
  - No ``nbclient``/``jupyter``/``subprocess`` in exporter source.
"""

from __future__ import annotations

import importlib.util
import json
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# These tests exercise the optional ``notebook`` extra. Skip-collect the whole
# module when nbformat is absent rather than raising a collection error — keeps
# the full suite runnable in a clean checkout without the extra installed.
# ruff: noqa: E402 — the imports below must follow the importorskip above,
# which is the whole point of skip-collecting this module.
nbformat = pytest.importorskip("nbformat")

from akms_learn.capability_gates import PreconditionError
from akms_learn.exporters import KNOWN_EXPORTERS
from akms_learn.exporters.notebook import export
from akms_learn.models import (
    CompilerInfo,
    LearningEdgeView,
    LearningNodeView,
    LearningRequestInfo,
    LearningSourcePacket,
    PacketBody,
    SourceInfo,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_node(
    node_id: str,
    *,
    source_path: str = "toy://node.md",
    line_range: tuple[int, int] = (1, 10),
    included_sections: dict[str, Any] | None = None,
) -> LearningNodeView:
    return LearningNodeView(
        node_id=node_id,
        source_path=source_path,
        line_range=line_range,
        title=f"Node {node_id}",
        included_sections=included_sections or {},
    )


def _make_packet(
    nodes: list[LearningNodeView] | None = None,
    *,
    packet_id: str = "test-packet-p3-1",
    graph_version: str = "v2-test",
    topic: str = "Toy Topic",
    edges: list[LearningEdgeView] | None = None,
) -> LearningSourcePacket:
    """Build a minimal synthetic LSP for exporter tests (no compiler invocation)."""
    if nodes is None:
        # Default: one node with content in every section heading.
        nodes = [
            _make_node(
                "node_a",
                source_path="toy://node_a.md",
                line_range=(1, 20),
                included_sections={
                    "concept": {"content": "A toy concept explanation."},
                    "derivation": {"content": "A toy derivation."},
                    "implementation": {"content": "import math\nx = math.sqrt(2)"},
                    "pitfalls": {"content": "Watch out for rounding."},
                    "assessment": {"content": "Is x correct?"},
                },
            )
        ]
    return LearningSourcePacket(
        packet_id=packet_id,
        created_at="2026-01-01T00:00:00+00:00",
        compiler=CompilerInfo(name="akms-learn", version="1.0"),
        source=SourceInfo(
            graph_hash="abc123",
            graph_path="toy://graph.json",
            graph_version=graph_version,
        ),
        request=LearningRequestInfo(
            topic=topic,
            request_hash="req-hash-001",
        ),
        body=PacketBody(
            nodes=nodes,
            edges=edges or [],
            reading_order=[n.node_id for n in nodes],
        ),
        warnings=[],
    )


@contextmanager
def _gate_open():
    """Patch ``find_spec`` so ``nbformat`` appears installed for gate checks."""
    original = importlib.util.find_spec

    def _patched(name, *args, **kwargs):
        if name == "nbformat":
            return True  # type: ignore[return-value]
        return original(name, *args, **kwargs)

    with patch("importlib.util.find_spec", side_effect=_patched):
        yield


def _run_export(
    packet: LearningSourcePacket,
    output_dir: Path,
) -> list[Path]:
    """Run the notebook exporter with the capability gate forced open."""
    with _gate_open():
        return export(packet, output_dir)


def _load_notebook(path: Path) -> nbformat.NotebookNode:
    """Load and return the notebook node from *path*."""
    return nbformat.read(str(path), as_version=4)


def _all_markdown_cells(nb: nbformat.NotebookNode) -> list[nbformat.NotebookNode]:
    return [c for c in nb.cells if c.cell_type == "markdown"]


def _all_code_cells(nb: nbformat.NotebookNode) -> list[nbformat.NotebookNode]:
    return [c for c in nb.cells if c.cell_type == "code"]


# ---------------------------------------------------------------------------
# Output passes nbformat.validate
# ---------------------------------------------------------------------------


class TestNbformatValidation:
    """Exported .ipynb passes nbformat.validate without errors."""

    @pytest.mark.unit
    def test_output_passes_nbformat_validate(self, tmp_path: Path):
        """The exported notebook is schema-valid according to nbformat."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        assert len(paths) == 1
        nb = _load_notebook(paths[0])
        # nbformat.validate raises if invalid
        nbformat.validate(nb)

    @pytest.mark.unit
    def test_output_file_is_named_lesson_ipynb(self, tmp_path: Path):
        """Output file is named ``lesson.ipynb``."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        assert paths[0].name == "lesson.ipynb"

    @pytest.mark.unit
    def test_output_is_valid_json(self, tmp_path: Path):
        """The .ipynb file is valid JSON."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        raw = paths[0].read_text(encoding="utf-8")
        data = json.loads(raw)
        assert "cells" in data
        assert "metadata" in data
        assert "nbformat" in data

    @pytest.mark.unit
    def test_empty_packet_still_validates(self, tmp_path: Path):
        """Even a packet with no nodes produces a valid notebook."""
        packet = _make_packet(nodes=[])
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])
        nbformat.validate(nb)

    @pytest.mark.unit
    def test_nbformat_version_is_4(self, tmp_path: Path):
        """Notebook uses nbformat version 4."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])
        assert nb.nbformat == 4


# ---------------------------------------------------------------------------
# Notebook metadata completeness
# ---------------------------------------------------------------------------


class TestMetadata:
    """Notebook metadata has all required akms.* fields + execution triplet."""

    @pytest.mark.unit
    def test_akms_packet_id_present(self, tmp_path: Path):
        """``akms.packet_id`` equals the packet's packet_id."""
        packet = _make_packet(packet_id="my-packet-123")
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])
        assert nb.metadata["akms"]["packet_id"] == "my-packet-123"

    @pytest.mark.unit
    def test_akms_graph_version_present(self, tmp_path: Path):
        """``akms.graph_version`` equals the source graph_version."""
        packet = _make_packet(graph_version="v2-gv-test")
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])
        assert nb.metadata["akms"]["graph_version"] == "v2-gv-test"

    @pytest.mark.unit
    def test_akms_compiler_version_present(self, tmp_path: Path):
        """``akms.compiler_version`` matches the compiler info."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])
        assert nb.metadata["akms"]["compiler_version"] == "1.0"

    @pytest.mark.unit
    def test_akms_schema_present(self, tmp_path: Path):
        """``akms.schema`` is ``"v2"``."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])
        assert nb.metadata["akms"]["schema"] == "v2"

    @pytest.mark.unit
    def test_execution_triplet_present(self, tmp_path: Path):
        """Execution triplet keys are present."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])
        execution = nb.metadata["execution"]
        assert "no_execute" in execution
        assert "illustrative_only" in execution
        assert "adapter_executable" in execution

    @pytest.mark.unit
    def test_all_required_akms_fields_present(self, tmp_path: Path):
        """All four akms.* fields are present together."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])
        akms = nb.metadata["akms"]
        assert set(akms.keys()) >= {
            "packet_id",
            "graph_version",
            "compiler_version",
            "schema",
        }


# ---------------------------------------------------------------------------
# Default no_execute=True; no execution path
# ---------------------------------------------------------------------------


class TestNoExecuteDefault:
    """No_execute=True by default; exporter never invokes nbclient/jupyter."""

    @pytest.mark.unit
    def test_no_execute_is_true_by_default(self, tmp_path: Path):
        """``execution.no_execute`` is True in the emitted notebook."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])
        assert nb.metadata["execution"]["no_execute"] is True

    @pytest.mark.unit
    def test_illustrative_only_is_false_by_default(self, tmp_path: Path):
        """``execution.illustrative_only`` defaults to False."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])
        assert nb.metadata["execution"]["illustrative_only"] is False

    @pytest.mark.unit
    def test_adapter_executable_is_false_by_default(self, tmp_path: Path):
        """``execution.adapter_executable`` defaults to False."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])
        assert nb.metadata["execution"]["adapter_executable"] is False

    @pytest.mark.unit
    def test_no_executed_outputs_in_code_cells(self, tmp_path: Path):
        """Code cells have no executed outputs (outputs=[])."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])
        for cell in _all_code_cells(nb):
            assert cell.outputs == [], (
                f"Code cell has unexpected outputs: {cell.outputs}"
            )

    @pytest.mark.unit
    def test_no_execution_count_in_code_cells(self, tmp_path: Path):
        """Code cells have ``execution_count=None``."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])
        for cell in _all_code_cells(nb):
            assert cell.execution_count is None

    @staticmethod
    def _non_comment_source() -> str:
        """Return notebook.py with docstrings and comments stripped."""
        src = (
            Path(__file__).parent.parent
            / "src"
            / "akms_learn"
            / "exporters"
            / "notebook.py"
        )
        raw = src.read_text()
        stripped = re.sub(r'""".*?"""', '""""""', raw, flags=re.DOTALL)
        stripped = re.sub(r"'''.*?'''", "''''''", stripped, flags=re.DOTALL)
        lines = [ln for ln in stripped.splitlines() if not ln.lstrip().startswith("#")]
        return "\n".join(lines)

    @pytest.mark.unit
    def test_no_nbclient_in_source(self):
        """Exporter source does not reference nbclient."""
        code = self._non_comment_source()
        assert "nbclient" not in code

    @pytest.mark.unit
    def test_no_jupyter_import_in_source(self):
        """Exporter source does not import jupyter."""
        code = self._non_comment_source()
        assert "import jupyter" not in code

    @pytest.mark.unit
    def test_no_subprocess_in_source(self):
        """Exporter source does not import subprocess."""
        code = self._non_comment_source()
        assert "import subprocess" not in code

    @pytest.mark.unit
    def test_no_exec_call_in_source(self):
        """Exporter source does not contain exec(."""
        code = self._non_comment_source()
        assert "exec(" not in code

    @pytest.mark.unit
    def test_no_eval_call_in_source(self):
        """Exporter source does not contain eval(."""
        code = self._non_comment_source()
        assert "eval(" not in code


# ---------------------------------------------------------------------------
# Provenance footer on every Markdown cell
# ---------------------------------------------------------------------------


class TestProvenanceFooter:
    """Every Markdown cell carries a provenance footer."""

    @pytest.mark.unit
    def test_all_markdown_cells_have_provenance_block(self, tmp_path: Path):
        """Every Markdown cell contains a fenced provenance block."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])
        md_cells = _all_markdown_cells(nb)
        assert md_cells, "Expected at least one Markdown cell"
        for cell in md_cells:
            assert "```provenance" in cell.source, (
                f"Markdown cell missing provenance block:\n{cell.source!r}"
            )

    @pytest.mark.unit
    def test_provenance_contains_source_node_id(self, tmp_path: Path):
        """Provenance blocks contain ``source_node_id``."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])
        for cell in _all_markdown_cells(nb):
            assert "source_node_id:" in cell.source, (
                f"Markdown cell missing source_node_id in provenance:\n{cell.source!r}"
            )

    @pytest.mark.unit
    def test_provenance_contains_source_path(self, tmp_path: Path):
        """Provenance blocks contain ``source_path``."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])
        for cell in _all_markdown_cells(nb):
            assert "source_path:" in cell.source, (
                f"Markdown cell missing source_path in provenance:\n{cell.source!r}"
            )

    @pytest.mark.unit
    def test_provenance_contains_line_range(self, tmp_path: Path):
        """Provenance blocks contain ``line_range``."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])
        for cell in _all_markdown_cells(nb):
            assert "line_range:" in cell.source, (
                f"Markdown cell missing line_range in provenance:\n{cell.source!r}"
            )

    @pytest.mark.unit
    def test_provenance_node_id_matches_packet_node(self, tmp_path: Path):
        """The source_node_id in provenance is a node from the packet (or <packet>)."""
        packet = _make_packet()
        node_ids = {n.node_id for n in packet.body.nodes} | {"<packet>"}
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])
        prov_re = re.compile(r"source_node_id:\s*(\S+)")
        for cell in _all_markdown_cells(nb):
            for match in prov_re.finditer(cell.source):
                found_id = match.group(1).strip()
                assert found_id in node_ids, (
                    f"Provenance source_node_id {found_id!r} not in packet nodes {node_ids}"
                )


# ---------------------------------------------------------------------------
# Unsafe snippet → Markdown cell, not code cell
# ---------------------------------------------------------------------------


class TestUnsafeSnippetDegradation:
    """Unsafe LSP snippet is emitted as Markdown, not a code cell."""

    @pytest.mark.unit
    def test_unsafe_snippet_is_markdown_not_code(self, tmp_path: Path):
        """Node with unsafe implementation → no code cell for that snippet."""
        unsafe_snippet = (
            "import requests\ndata = requests.get('http://example.com').json()"
        )
        node = _make_node(
            "unsafe_node",
            source_path="toy://unsafe.md",
            line_range=(1, 5),
            included_sections={
                "implementation": {"content": unsafe_snippet},
            },
        )
        packet = _make_packet(nodes=[node])
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])

        # The unsafe snippet should not appear in a code cell
        for cell in _all_code_cells(nb):
            assert "requests.get" not in cell.source, (
                "Unsafe snippet appeared in a code cell"
            )

    @pytest.mark.unit
    def test_unsafe_snippet_appears_in_markdown_as_fenced(self, tmp_path: Path):
        """The unsafe snippet is wrapped in a fenced code block in Markdown."""
        unsafe_snippet = "import subprocess\nsubprocess.run(['ls'])"
        node = _make_node(
            "subprocess_node",
            included_sections={
                "implementation": {"content": unsafe_snippet},
            },
        )
        packet = _make_packet(nodes=[node])
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])

        found_in_md = any(
            "subprocess.run" in cell.source for cell in _all_markdown_cells(nb)
        )
        assert found_in_md, "Unsafe snippet not found in any Markdown cell"

    @pytest.mark.unit
    def test_unsafe_snippet_degradation_includes_note(self, tmp_path: Path):
        """Degraded Markdown cell includes an explanatory note."""
        unsafe_snippet = "import os\nos.remove('file')"
        node = _make_node(
            "os_node",
            included_sections={
                "implementation": {"content": unsafe_snippet},
            },
        )
        packet = _make_packet(nodes=[node])
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])

        # Look for any cell containing both the snippet and a note keyword
        degraded_cells = [
            cell for cell in _all_markdown_cells(nb) if "os.remove" in cell.source
        ]
        assert degraded_cells, "Degraded cell not found"
        note_found = any(
            "Note" in cell.source or "not executable" in cell.source.lower()
            for cell in degraded_cells
        )
        assert note_found, "Degraded cell has no explanatory note"

    @pytest.mark.unit
    def test_safe_snippet_becomes_code_cell(self, tmp_path: Path):
        """Node with safe stdlib implementation → code cell."""
        safe_snippet = "import math\nx = math.sqrt(4.0)"
        node = _make_node(
            "safe_node",
            included_sections={
                "implementation": {"content": safe_snippet},
            },
        )
        packet = _make_packet(nodes=[node])
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])

        code_cells = _all_code_cells(nb)
        assert any("math.sqrt" in cell.source for cell in code_cells), (
            "Safe snippet not found in any code cell"
        )

    @pytest.mark.unit
    def test_unknown_snippet_is_markdown_not_code(self, tmp_path: Path):
        """Unknown-safety snippet (e.g. numpy) is not in a code cell."""
        unknown_snippet = "import numpy as np\narr = np.array([1, 2, 3])"
        node = _make_node(
            "numpy_node",
            included_sections={
                "implementation": {"content": unknown_snippet},
            },
        )
        packet = _make_packet(nodes=[node])
        paths = _run_export(packet, tmp_path)
        nb = _load_notebook(paths[0])

        for cell in _all_code_cells(nb):
            assert "numpy" not in cell.source, (
                "Unknown (numpy) snippet found in a code cell"
            )


# ---------------------------------------------------------------------------
# Capability gate
# ---------------------------------------------------------------------------


class TestCapabilityGate:
    """Exporter raises PreconditionError when notebook extra is absent."""

    @pytest.mark.unit
    def test_raises_precondition_error_when_nbformat_absent(self, tmp_path: Path):
        """PreconditionError raised when importlib.util.find_spec('nbformat') → None."""
        packet = _make_packet()
        original = importlib.util.find_spec

        def _mock(name, *args, **kwargs):
            if name == "nbformat":
                return None
            return original(name, *args, **kwargs)

        with patch("importlib.util.find_spec", side_effect=_mock):
            with pytest.raises(PreconditionError) as exc_info:
                export(packet, tmp_path)

        assert exc_info.value.capability == "notebook_export"
        assert exc_info.value.extra == "notebook"

    @pytest.mark.unit
    def test_precondition_error_message_names_extra(self, tmp_path: Path):
        """Error message mentions capability and missing extra."""
        packet = _make_packet()
        original = importlib.util.find_spec

        def _mock(name, *args, **kwargs):
            if name == "nbformat":
                return None
            return original(name, *args, **kwargs)

        with patch("importlib.util.find_spec", side_effect=_mock):
            with pytest.raises(PreconditionError) as exc_info:
                export(packet, tmp_path)

        msg = str(exc_info.value)
        assert "notebook" in msg


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    """Exporter is registered in KNOWN_EXPORTERS."""

    @pytest.mark.unit
    def test_notebook_in_known_exporters(self):
        """``"notebook"`` is a member of KNOWN_EXPORTERS."""
        assert "notebook" in KNOWN_EXPORTERS

    @pytest.mark.unit
    def test_notebook_module_importable(self):
        """The notebook exporter module can be imported without error."""
        import importlib

        mod = importlib.import_module("akms_learn.exporters.notebook")
        assert hasattr(mod, "export")
        assert callable(mod.export)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Two exports of the same packet produce byte-equal files."""

    @pytest.mark.unit
    def test_deterministic_output(self, tmp_path: Path):
        """Second export call produces the same .ipynb bytes."""
        packet = _make_packet()
        out1 = tmp_path / "run1"
        out2 = tmp_path / "run2"
        paths1 = _run_export(packet, out1)
        paths2 = _run_export(packet, out2)
        assert paths1[0].read_bytes() == paths2[0].read_bytes()
