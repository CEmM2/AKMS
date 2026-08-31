"""Tests for notebook_source compiler mode.

Covers all five acceptance criteria:

Compiler registered under mode key ``notebook_source``.
LSP produced contains the six section kinds in canonical deterministic order.
Code candidates failing the safe-code classifier are emitted as explanatory cells.
Each emitted cell payload carries ``provenance.source_node_id``, ``source_path``,
      ``line_range``.
Compiler never executes code (canary: no subprocess/exec/eval/%run/nbclient in source).

Additional tests:
  - Safe candidate (pure stdlib whitelist) is emitted as a code cell.
  - ``no_execute`` metadata defaults to ``True``.
  - Compiler raises ``PreconditionError`` when the ``notebook`` extra is absent.
  - All six sections are present even when source nodes have no content.
  - Deterministic output: second call produces identical result.
"""

from __future__ import annotations

import importlib.util
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from akms_learn.capability_gates import PreconditionError
from akms_learn.graph_import import GraphSlice
from akms_learn.modes.notebook_source import (
    NOTEBOOK_SECTIONS,
    SECTION_PLACEHOLDER,
    NotebookSourceResult,
    _classify_code_safety,
    notebook_source_mode,
)
from akms_learn.ordering import get_strategy, list_strategies, order_nodes
from akms_learn.toy_fixtures import (
    fixture_graph_toy_concept_kit,
    fixture_graph_toy_executable_bridge,
    fixture_graph_toy_workbench,
)
from akms_learn.plugin import get_plugin
from akms_learn.requests import LearningRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(**overrides: Any) -> LearningRequest:
    defaults: dict[str, Any] = dict(
        topic="toy widget pipeline",
        goal="Understand the toy notebook source mode end-to-end.",
        audience="engineer",
        depth="implementation",
        generation_option="notebook_source",
        seed_tags=[],
        exporters=[],
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


@contextmanager
def _gate_open():
    """Context manager that patches ``find_spec`` so nbformat appears installed.

    This is the standard way to test ``notebook_source_mode`` in environments
    where the ``notebook`` extra is not installed.  The patch is scoped to the
    context so it does not bleed into other tests.
    """
    original = importlib.util.find_spec

    def _patched(name, *args, **kwargs):
        if name == "nbformat":
            # Return a truthy sentinel; the actual spec object is never used
            # beyond the None-check in probe_optional_extras.
            return True  # type: ignore[return-value]
        return original(name, *args, **kwargs)

    with patch("importlib.util.find_spec", side_effect=_patched):
        yield


def _run_mode(
    graph_slice: GraphSlice,
    request: LearningRequest | None = None,
    packet_id: str = "test-packet-001",
    graph_version: str = "v2-test",
) -> tuple[NotebookSourceResult, list]:
    """Run notebook_source_mode with capability gate open and default request."""
    if request is None:
        request = _make_request()
    ordered_nodes, _ = order_nodes(graph_slice)
    with _gate_open():
        return notebook_source_mode(
            graph_slice,
            ordered_nodes,
            request,
            packet_id=packet_id,
            graph_version=graph_version,
        )


def _make_graph_with_safe_code() -> GraphSlice:
    """Graph slice with a node whose implementation section is safe Python."""
    safe_snippet = "import math\nresult = math.sqrt(4.0)\n"
    nodes: list[dict[str, Any]] = [
        {
            "node_id": "safe_node",
            "title": "Safe Node",
            "kind": "implementation",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_a",
            "tags": ["toy"],
            "status": "established",
            "source_path": "toy://safe/node.md",
            "line_range": [1, 10],
            "extracted": {
                "implementation": safe_snippet,
                "concept": "A simple safe concept.",
            },
        }
    ]
    return GraphSlice(nodes=tuple(nodes), edges=(), metadata={})


def _make_graph_with_unsafe_code() -> GraphSlice:
    """Graph slice with a node whose implementation section uses network IO."""
    unsafe_snippet = (
        "import requests\ndata = requests.get('http://example.com').json()\n"
    )
    nodes: list[dict[str, Any]] = [
        {
            "node_id": "unsafe_node",
            "title": "Unsafe Node",
            "kind": "implementation",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_b",
            "tags": ["toy"],
            "status": "established",
            "source_path": "toy://unsafe/node.md",
            "line_range": [1, 5],
            "extracted": {
                "implementation": unsafe_snippet,
                "concept": "A concept with unsafe code.",
            },
        }
    ]
    return GraphSlice(nodes=tuple(nodes), edges=(), metadata={})


def _make_graph_with_subprocess_code() -> GraphSlice:
    """Graph slice with subprocess import (immediately unsafe)."""
    unsafe_snippet = "import subprocess\nsubprocess.run(['ls'])\n"
    nodes: list[dict[str, Any]] = [
        {
            "node_id": "subprocess_node",
            "title": "Subprocess Node",
            "kind": "implementation",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_c",
            "tags": ["toy"],
            "status": "established",
            "source_path": "toy://subprocess/node.md",
            "line_range": [1, 3],
            "extracted": {
                "implementation": unsafe_snippet,
            },
        }
    ]
    return GraphSlice(nodes=tuple(nodes), edges=(), metadata={})


# ---------------------------------------------------------------------------
# Mode registered under key "notebook_source"
# ---------------------------------------------------------------------------


class TestRegistration:
    """Compiler registered under mode key ``notebook_source``."""

    @pytest.mark.unit
    def test_strategy_registry_contains_notebook_source(self):
        """``notebook_source`` appears in list_strategies()."""
        assert "notebook_source" in list_strategies()

    @pytest.mark.unit
    def test_get_strategy_notebook_source_does_not_raise(self):
        """``get_strategy("notebook_source")`` returns a callable without error."""
        strategy = get_strategy("notebook_source")
        assert callable(strategy)

    @pytest.mark.unit
    def test_plugin_capabilities_include_notebook_source(self):
        """Plugin.capabilities() lists ``notebook_source``."""
        plugin = get_plugin()
        assert "notebook_source" in plugin.capabilities()


# ---------------------------------------------------------------------------
# Six section kinds in canonical deterministic order
# ---------------------------------------------------------------------------


class TestSixSections:
    """LSP contains the six section kinds in canonical order."""

    @pytest.mark.unit
    def test_six_sections_present_toy_concept_kit(self):
        """All six section keys are present in the result."""
        gs = fixture_graph_toy_concept_kit()
        result, _ = _run_mode(gs)
        assert list(result.sections.keys()) == list(NOTEBOOK_SECTIONS)

    @pytest.mark.unit
    def test_six_sections_present_toy_workbench(self):
        """All six section keys present on the workbench fixture."""
        gs = fixture_graph_toy_workbench()
        result, _ = _run_mode(gs)
        assert list(result.sections.keys()) == list(NOTEBOOK_SECTIONS)

    @pytest.mark.unit
    def test_six_sections_present_toy_executable_bridge(self):
        """All six section keys present on the executable bridge fixture."""
        gs = fixture_graph_toy_executable_bridge()
        result, _ = _run_mode(gs)
        assert list(result.sections.keys()) == list(NOTEBOOK_SECTIONS)

    @pytest.mark.unit
    def test_section_order_is_canonical(self):
        """Section order matches NOTEBOOK_SECTIONS exactly."""
        gs = fixture_graph_toy_concept_kit()
        result, _ = _run_mode(gs)
        assert tuple(result.sections.keys()) == NOTEBOOK_SECTIONS

    @pytest.mark.unit
    def test_each_section_has_at_least_one_cell(self):
        """Every section has a non-empty list of cell payloads."""
        gs = fixture_graph_toy_concept_kit()
        result, _ = _run_mode(gs)
        for slot in NOTEBOOK_SECTIONS:
            assert len(result.sections[slot]) >= 1, f"Section {slot!r} has no cells"

    @pytest.mark.unit
    def test_deterministic_second_call(self):
        """Two calls on the same input produce identical sections."""
        gs = fixture_graph_toy_concept_kit()
        result1, _ = _run_mode(gs, packet_id="pid", graph_version="gv")
        result2, _ = _run_mode(gs, packet_id="pid", graph_version="gv")
        assert result1.sections == result2.sections


# ---------------------------------------------------------------------------
# Unsafe code → explanatory cell; safe code → code cell
# ---------------------------------------------------------------------------


class TestSafeCodeClassifier:
    """Safe → code cell; unsafe/unknown → explanatory cell."""

    @pytest.mark.unit
    def test_safe_stdlib_emits_code_cell(self):
        """Node with pure stdlib implementation emits a code cell."""
        gs = _make_graph_with_safe_code()
        result, _ = _run_mode(gs)
        impl_cells = result.sections["minimal implementation"]
        assert any(c["cell_type"] == "code" for c in impl_cells), (
            f"Expected a code cell in 'minimal implementation', got: {impl_cells}"
        )

    @pytest.mark.unit
    def test_unsafe_network_emits_explanatory_cell(self):
        """Node with requests import emits an explanatory cell."""
        gs = _make_graph_with_unsafe_code()
        result, _ = _run_mode(gs)
        impl_cells = result.sections["minimal implementation"]
        assert all(c["cell_type"] == "markdown" for c in impl_cells), (
            f"Expected only explanatory (markdown) cells, got: {impl_cells}"
        )

    @pytest.mark.unit
    def test_unsafe_subprocess_emits_explanatory_cell(self):
        """Node with subprocess import emits an explanatory cell."""
        gs = _make_graph_with_subprocess_code()
        result, _ = _run_mode(gs)
        impl_cells = result.sections["minimal implementation"]
        assert all(c["cell_type"] == "markdown" for c in impl_cells)

    @pytest.mark.unit
    def test_unsafe_code_degradation_warning_emitted(self):
        """A ``notebook_unsafe_code_degraded`` warning is emitted."""
        gs = _make_graph_with_unsafe_code()
        result, warnings = _run_mode(gs)
        codes = [w.code for w in warnings]
        assert "notebook_unsafe_code_degraded" in codes

    @pytest.mark.unit
    def test_unsafe_code_rendered_as_fenced_block(self):
        """Degraded snippets render inside a fenced code block."""
        gs = _make_graph_with_unsafe_code()
        result, _ = _run_mode(gs)
        impl_cells = result.sections["minimal implementation"]
        for cell in impl_cells:
            if cell["cell_type"] == "markdown":
                assert "```" in cell["source"], (
                    "Degraded code snippet should be wrapped in a fenced block"
                )

    @pytest.mark.unit
    def test_safe_node_no_degradation_warning(self):
        """Safe code produces no degradation warning."""
        gs = _make_graph_with_safe_code()
        result, warnings = _run_mode(gs)
        codes = [w.code for w in warnings]
        assert "notebook_unsafe_code_degraded" not in codes


# ---------------------------------------------------------------------------
# _classify_code_safety unit tests
# ---------------------------------------------------------------------------


class TestClassifyCodeSafety:
    """Unit tests for :func:`_classify_code_safety`."""

    @pytest.mark.unit
    def test_safe_math_import(self):
        assert _classify_code_safety("import math\nx = math.pi") == "safe"

    @pytest.mark.unit
    def test_safe_statistics_import(self):
        assert (
            _classify_code_safety("import statistics\nm = statistics.mean([1,2,3])")
            == "safe"
        )

    @pytest.mark.unit
    def test_safe_multiple_whitelist_imports(self):
        snippet = "import math\nimport functools\nfrom collections import namedtuple"
        assert _classify_code_safety(snippet) == "safe"

    @pytest.mark.unit
    def test_unsafe_requests_import(self):
        assert _classify_code_safety("import requests") == "unsafe"

    @pytest.mark.unit
    def test_unsafe_os_import(self):
        assert _classify_code_safety("import os\nos.remove('file')") == "unsafe"

    @pytest.mark.unit
    def test_unsafe_subprocess_import(self):
        assert _classify_code_safety("import subprocess") == "unsafe"

    @pytest.mark.unit
    def test_unsafe_urllib_import(self):
        assert _classify_code_safety("from urllib import request") == "unsafe"

    @pytest.mark.unit
    def test_unsafe_socket_import(self):
        assert _classify_code_safety("import socket") == "unsafe"

    @pytest.mark.unit
    def test_unsafe_shutil_import(self):
        assert _classify_code_safety("import shutil") == "unsafe"

    @pytest.mark.unit
    def test_unsafe_sys_import(self):
        assert _classify_code_safety("import sys") == "unsafe"

    @pytest.mark.unit
    def test_unsafe_open_call(self):
        assert _classify_code_safety("f = open('file.txt')") == "unsafe"

    @pytest.mark.unit
    def test_unsafe_exec_call(self):
        assert _classify_code_safety("exec('print(1)')") == "unsafe"

    @pytest.mark.unit
    def test_unsafe_eval_call(self):
        assert _classify_code_safety("eval('1+1')") == "unsafe"

    @pytest.mark.unit
    def test_unsafe_compile_call(self):
        assert _classify_code_safety("compile('pass', '', 'exec')") == "unsafe"

    @pytest.mark.unit
    def test_unsafe_dunder_import(self):
        assert _classify_code_safety("__import__('os')") == "unsafe"

    @pytest.mark.unit
    def test_unknown_nonwhitelist_import(self):
        # numpy is not in the whitelist → unknown (over-degrade)
        assert _classify_code_safety("import numpy as np") == "unknown"

    @pytest.mark.unit
    def test_unsafe_multi_import_line_catches_trailing_unsafe(self):
        # `import math, os` — `os` is unsafe; the whole snippet must be unsafe.
        # The raw-text regex misses the second module, but the
        # module-name-granular check catches it.
        assert _classify_code_safety("import math, os") == "unsafe"

    @pytest.mark.unit
    def test_unsafe_multi_import_line_catches_leading_unsafe(self):
        # Symmetric: `import os, math` — leading unsafe still labelled unsafe.
        assert _classify_code_safety("import os, math") == "unsafe"

    @pytest.mark.unit
    def test_unsafe_multi_import_line_with_alias(self):
        # `import math as m, os as o` — alias forms must still extract `os`.
        assert _classify_code_safety("import math as m, os as o") == "unsafe"

    @pytest.mark.unit
    def test_unknown_empty_snippet(self):
        assert _classify_code_safety("") == "unknown"

    @pytest.mark.unit
    def test_unknown_whitespace_only(self):
        assert _classify_code_safety("   \n   ") == "unknown"

    @pytest.mark.unit
    def test_safe_no_imports(self):
        # Pure arithmetic without any import → safe
        assert _classify_code_safety("x = 1 + 2\ny = x * 3") == "safe"

    # -- Dotted from-import cases ---------------------------------------------

    @pytest.mark.unit
    def test_unknown_dotted_sklearn_preprocessing(self):
        # sklearn is not in the whitelist → unknown (must NOT leak through as safe)
        assert (
            _classify_code_safety("from sklearn.preprocessing import StandardScaler")
            == "unknown"
        )

    @pytest.mark.unit
    def test_unknown_dotted_numpy_linalg(self):
        # numpy is not in the whitelist → unknown
        assert _classify_code_safety("from numpy.linalg import inv") == "unknown"

    @pytest.mark.unit
    def test_unsafe_dotted_urllib(self):
        # urllib is in the unsafe set → unsafe
        assert _classify_code_safety("from urllib import request") == "unsafe"

    @pytest.mark.unit
    def test_safe_dotted_collections_abc(self):
        # collections is in the whitelist → safe
        assert _classify_code_safety("from collections.abc import Mapping") == "safe"

    @pytest.mark.unit
    def test_safe_dotted_math(self):
        # math is in the whitelist → safe
        assert _classify_code_safety("from math import sqrt") == "safe"

    @pytest.mark.unit
    def test_unknown_star_import_regex_gated(self):
        # Star-import detected via regex before no-imports early-return
        assert _classify_code_safety("from itertools import *") == "unknown"

    @pytest.mark.unit
    def test_safe_star_import_check_not_fooled_by_docstring(self):
        # A comment/prose mentioning "import *" should not block safe classification
        # (regex gates on the actual import statement pattern, not substring).
        snippet = '# do not use "import *"\nimport math\nx = math.pi'
        assert _classify_code_safety(snippet) == "safe"


# ---------------------------------------------------------------------------
# Provenance on every cell
# ---------------------------------------------------------------------------


class TestProvenance:
    """Every cell payload carries full provenance."""

    @pytest.mark.unit
    def test_provenance_keys_on_all_cells(self):
        """Every cell in every section has source_node_id, source_path, line_range."""
        gs = fixture_graph_toy_concept_kit()
        result, _ = _run_mode(gs)
        for slot, cells in result.sections.items():
            for i, cell in enumerate(cells):
                prov = cell.get("provenance")
                assert prov is not None, (
                    f"Cell {i} in section {slot!r} missing 'provenance'"
                )
                assert "source_node_id" in prov, (
                    f"Cell {i} in section {slot!r} missing provenance.source_node_id"
                )
                assert "source_path" in prov, (
                    f"Cell {i} in section {slot!r} missing provenance.source_path"
                )
                assert "line_range" in prov, (
                    f"Cell {i} in section {slot!r} missing provenance.line_range"
                )

    @pytest.mark.unit
    def test_provenance_source_node_id_nonempty(self):
        """source_node_id is a non-empty string."""
        gs = fixture_graph_toy_concept_kit()
        result, _ = _run_mode(gs)
        for slot, cells in result.sections.items():
            for cell in cells:
                nid = cell["provenance"]["source_node_id"]
                assert isinstance(nid, str) and nid, (
                    f"section {slot!r}: source_node_id is empty"
                )

    @pytest.mark.unit
    def test_provenance_source_path_nonempty(self):
        """source_path is a non-empty string."""
        gs = fixture_graph_toy_concept_kit()
        result, _ = _run_mode(gs)
        for slot, cells in result.sections.items():
            for cell in cells:
                sp = cell["provenance"]["source_path"]
                assert isinstance(sp, str) and sp, (
                    f"section {slot!r}: source_path is empty"
                )

    @pytest.mark.unit
    def test_provenance_on_safe_code_cell(self):
        """Code cells (safe path) also carry full provenance."""
        gs = _make_graph_with_safe_code()
        result, _ = _run_mode(gs)
        for cell in result.sections["minimal implementation"]:
            if cell["cell_type"] == "code":
                prov = cell["provenance"]
                assert "source_node_id" in prov
                assert "source_path" in prov
                assert "line_range" in prov

    @pytest.mark.unit
    def test_provenance_on_explanatory_cell(self):
        """Explanatory/markdown cells carry full provenance."""
        gs = _make_graph_with_unsafe_code()
        result, _ = _run_mode(gs)
        for slot, cells in result.sections.items():
            for cell in cells:
                if cell["cell_type"] == "markdown":
                    prov = cell["provenance"]
                    assert "source_node_id" in prov
                    assert "source_path" in prov
                    assert "line_range" in prov


# ---------------------------------------------------------------------------
# Canary — no execution calls in compiler source
# ---------------------------------------------------------------------------


class TestNoExecution:
    """Compiler source must not contain execution-related calls/imports.

    Canary strategy: grep *non-comment, non-docstring* lines for patterns that
    would constitute actual code execution.  The module docstring legitimately
    mentions these terms when describing what must NOT be done; we strip
    triple-quoted strings and ``#``-comment lines before scanning so that
    explanatory text does not trigger a false positive.
    """

    @staticmethod
    def _non_docstring_source() -> str:
        """Return notebook_source.py with triple-quoted strings stripped."""
        src_path = (
            Path(__file__).parent.parent
            / "src"
            / "akms_learn"
            / "modes"
            / "notebook_source.py"
        )
        raw = src_path.read_text()
        # Strip triple-quoted strings (docstrings / multiline strings).
        stripped = re.sub(r'""".*?"""', '""""""', raw, flags=re.DOTALL)
        stripped = re.sub(r"'''.*?'''", "''''''", stripped, flags=re.DOTALL)
        # Also drop comment lines.
        lines = [ln for ln in stripped.splitlines() if not ln.lstrip().startswith("#")]
        return "\n".join(lines)

    @pytest.mark.unit
    def test_no_nbclient_import_in_source(self):
        """Source file does not import nbclient."""
        code = self._non_docstring_source()
        assert "import nbclient" not in code, (
            "Canary: 'import nbclient' found in notebook_source.py"
        )
        assert "nbclient." not in code, (
            "Canary: 'nbclient.' call found in notebook_source.py"
        )

    @pytest.mark.unit
    def test_no_jupyter_import_in_source(self):
        """Source file does not import jupyter packages."""
        code = self._non_docstring_source()
        assert "import jupyter" not in code, (
            "Canary: 'import jupyter' found in notebook_source.py"
        )

    @pytest.mark.unit
    def test_no_subprocess_import_in_source(self):
        """Source file does not import subprocess."""
        code = self._non_docstring_source()
        assert "import subprocess" not in code, (
            "Canary: 'import subprocess' found in notebook_source.py"
        )

    @pytest.mark.unit
    def test_no_exec_call_in_source(self):
        """Source file does not contain exec(."""
        code = self._non_docstring_source()
        assert "exec(" not in code, "Canary: 'exec(' found in notebook_source.py"

    @pytest.mark.unit
    def test_no_eval_call_in_source(self):
        """Source file does not contain eval(."""
        code = self._non_docstring_source()
        assert "eval(" not in code, "Canary: 'eval(' found in notebook_source.py"

    @pytest.mark.unit
    def test_no_percent_run_in_source(self):
        """Source file does not contain %run magic."""
        code = self._non_docstring_source()
        assert "%run" not in code, "Canary: '%run' found in notebook_source.py"


# ---------------------------------------------------------------------------
# no_execute default
# ---------------------------------------------------------------------------


class TestNoExecuteDefault:
    """``no_execute`` metadata defaults to ``True``."""

    @pytest.mark.unit
    def test_no_execute_is_true(self):
        """notebook_metadata.execution_mode.no_execute is True by default."""
        gs = fixture_graph_toy_concept_kit()
        result, _ = _run_mode(gs)
        assert result.notebook_metadata["execution_mode"]["no_execute"] is True

    @pytest.mark.unit
    def test_illustrative_only_is_false(self):
        """illustrative_only defaults to False."""
        gs = fixture_graph_toy_concept_kit()
        result, _ = _run_mode(gs)
        assert result.notebook_metadata["execution_mode"]["illustrative_only"] is False

    @pytest.mark.unit
    def test_adapter_executable_is_false(self):
        """adapter_executable defaults to False."""
        gs = fixture_graph_toy_concept_kit()
        result, _ = _run_mode(gs)
        assert result.notebook_metadata["execution_mode"]["adapter_executable"] is False

    @pytest.mark.unit
    def test_akms_metadata_keys_present(self):
        """akms block has packet_id, graph_version, compiler_version, schema."""
        gs = fixture_graph_toy_concept_kit()
        result, _ = _run_mode(gs, packet_id="p123", graph_version="v2-gv")
        akms = result.notebook_metadata["akms"]
        assert akms["packet_id"] == "p123"
        assert akms["graph_version"] == "v2-gv"
        assert akms["compiler_version"] == "1.0"
        assert akms["schema"] == "v2"


# ---------------------------------------------------------------------------
# PreconditionError when notebook extra absent
# ---------------------------------------------------------------------------


class TestPreconditionError:
    """Compiler raises PreconditionError when the notebook extra is absent."""

    @pytest.mark.unit
    def test_raises_precondition_error_when_nbformat_absent(self):
        """PreconditionError raised when importlib.util.find_spec('nbformat') returns None."""
        gs = fixture_graph_toy_concept_kit()
        request = _make_request()
        ordered_nodes, _ = order_nodes(gs)

        import importlib.util

        original_find_spec = importlib.util.find_spec

        def _find_spec_mock(name, *args, **kwargs):
            if name == "nbformat":
                return None
            return original_find_spec(name, *args, **kwargs)

        with patch("importlib.util.find_spec", side_effect=_find_spec_mock):
            with pytest.raises(PreconditionError) as exc_info:
                notebook_source_mode(gs, ordered_nodes, request)

        assert exc_info.value.capability == "notebook_source"
        assert exc_info.value.extra == "notebook"

    @pytest.mark.unit
    def test_precondition_error_message_names_capability_and_extra(self):
        """Error message includes both the capability and the missing extra."""
        gs = fixture_graph_toy_concept_kit()
        request = _make_request()
        ordered_nodes, _ = order_nodes(gs)

        import importlib.util

        original_find_spec = importlib.util.find_spec

        def _find_spec_mock(name, *args, **kwargs):
            if name == "nbformat":
                return None
            return original_find_spec(name, *args, **kwargs)

        with patch("importlib.util.find_spec", side_effect=_find_spec_mock):
            with pytest.raises(PreconditionError) as exc_info:
                notebook_source_mode(gs, ordered_nodes, request)

        msg = str(exc_info.value)
        assert "notebook_source" in msg
        assert "notebook" in msg


# ---------------------------------------------------------------------------
# Notebook metadata provenance
# ---------------------------------------------------------------------------


class TestNotebookMetadata:
    """Notebook metadata block is present and well-formed."""

    @pytest.mark.unit
    def test_source_node_ids_sorted(self):
        """source_node_ids list is sorted."""
        gs = fixture_graph_toy_concept_kit()
        result, _ = _run_mode(gs)
        assert result.source_node_ids == sorted(result.source_node_ids)

    @pytest.mark.unit
    def test_edge_ids_sorted(self):
        """edge_ids list is sorted."""
        gs = fixture_graph_toy_concept_kit()
        result, _ = _run_mode(gs)
        assert result.edge_ids == sorted(result.edge_ids)

    @pytest.mark.unit
    def test_missing_section_emits_warning(self):
        """When a slot has no matching content, a notebook_section_missing warning is emitted."""
        # An empty graph has no content — every slot should warn.
        gs = GraphSlice(
            nodes=(
                {
                    "node_id": "empty_node",
                    "title": "Empty",
                    "kind": "core_concept",
                    "domain": "toy",
                    "subdomain": "toy_sub",
                    "tags": [],
                    "status": "established",
                    "source_path": "toy://empty.md",
                    "extracted": {},
                },
            ),
            edges=(),
            metadata={},
        )
        result, warnings = _run_mode(gs)
        codes = [w.code for w in warnings]
        assert "notebook_section_missing" in codes
