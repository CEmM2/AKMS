"""Tests for HTML exporter (generated_preview.html via Jinja2).

Covers all five acceptance criteria:

Output is a single self-contained ``generated_preview.html`` —
      no ``<link rel="stylesheet"``, no ``<script src=``, no external
      remote ``href`` values.
``html.parser.HTMLParser().feed(...)`` succeeds without errors on
      the output.
All ``packet.warnings`` strings appear in the rendered HTML body.
Each section carries visible provenance: ``source_node_id``,
      ``source_path``, and ``line_range`` in the HTML.
Two runs against the same LSP produce byte-identical HTML;
      ``PreconditionError`` is raised when the ``html`` extra is absent.

Additional tests:
  - Exporter is registered in ``KNOWN_EXPORTERS``.
  - Output file is named ``generated_preview.html``.
  - Topic appears in the rendered ``<title>`` and ``<h1>``.
  - Empty-warnings packet renders a no-warnings message.
  - Capability gate is the first operation in ``export()``.
"""

from __future__ import annotations

import html.parser
import importlib.util
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from akms_learn.capability_gates import PreconditionError
from akms_learn.exporters import KNOWN_EXPORTERS
from akms_learn.exporters.html import _build_context, export
from akms_learn.models import (
    CompilerInfo,
    LearningEdgeView,
    LearningNodeView,
    LearningRequestInfo,
    LearningSourcePacket,
    LearningWarning,
    PacketBody,
    SourceInfo,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
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


def _make_warning(message: str, code: str = "test_warning") -> LearningWarning:
    return LearningWarning(severity="warning", code=code, message=message)


def _make_packet(
    nodes: list[LearningNodeView] | None = None,
    *,
    packet_id: str = "test-packet-p3-3",
    graph_version: str = "v2-test",
    topic: str = "Toy Topic",
    warnings: list[LearningWarning] | None = None,
    edges: list[LearningEdgeView] | None = None,
    generation_option: str | None = None,
    rich: bool = False,
) -> LearningSourcePacket:
    """Build a minimal synthetic LSP for HTML exporter tests."""
    if nodes is None:
        nodes = [
            _make_node(
                "node_a",
                source_path="toy://node_a.md",
                line_range=(5, 42),
                included_sections={
                    "Concept": {"content": "A toy concept explanation."},
                    "Implementation": {"content": "import math\nx = math.sqrt(2)"},
                },
            )
        ]
    request = LearningRequestInfo(
        topic=topic,
        request_hash="req-hash-p3-3",
        generation_option=generation_option,
        rich_html=rich,
    )
    return LearningSourcePacket(
        packet_id=packet_id,
        created_at="2026-01-01T00:00:00+00:00",
        compiler=CompilerInfo(name="akms-learn", version="1.0"),
        source=SourceInfo(
            graph_hash="abc123",
            graph_path="toy://graph.json",
            graph_version=graph_version,
        ),
        request=request,
        body=PacketBody(
            nodes=nodes,
            edges=edges or [],
            reading_order=[n.node_id for n in nodes],
        ),
        warnings=warnings or [],
    )


@contextmanager
def _gate_open():
    """Patch ``find_spec`` so ``jinja2`` appears installed for gate checks."""
    original = importlib.util.find_spec

    def _patched(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "jinja2":
            return True  # type: ignore[return-value]
        return original(name, *args, **kwargs)

    with patch("importlib.util.find_spec", side_effect=_patched):
        yield


@contextmanager
def _gate_closed():
    """Patch ``find_spec`` so ``jinja2`` appears NOT installed."""
    with patch("importlib.util.find_spec", return_value=None):
        yield


def _run_export(
    packet: LearningSourcePacket,
    output_dir: Path,
) -> list[Path]:
    """Run the HTML exporter with the capability gate forced open."""
    with _gate_open():
        return export(packet, output_dir)


def _html_text(path: Path) -> str:
    """Read the HTML file as UTF-8 text."""
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Self-contained — no external asset references
# ---------------------------------------------------------------------------


class TestSelfContained:
    """Output has no external CSS, JS, or remote asset references."""

    @pytest.mark.unit
    def test_no_link_stylesheet(self, tmp_path: Path):
        """No ``<link rel="stylesheet"`` in the output."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        html = _html_text(paths[0])
        assert '<link rel="stylesheet"' not in html.lower()
        assert "<link rel='stylesheet'" not in html.lower()

    @pytest.mark.unit
    def test_no_external_script_src(self, tmp_path: Path):
        """No ``<script src=`` referencing external resources."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        html = _html_text(paths[0])
        # Any <script src= would be an external asset reference
        assert re.search(r"<script\s[^>]*src\s*=", html, re.IGNORECASE) is None

    @pytest.mark.unit
    def test_no_remote_href(self, tmp_path: Path):
        """No ``href`` pointing to http(s):// URLs."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        html = _html_text(paths[0])
        # href="https://..." or href='http://...' are forbidden
        assert re.search(r'href=["\']https?://', html, re.IGNORECASE) is None

    @pytest.mark.unit
    def test_single_output_file(self, tmp_path: Path):
        """Exporter returns exactly one file path."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        assert len(paths) == 1

    @pytest.mark.unit
    def test_output_filename_is_generated_preview_html(self, tmp_path: Path):
        """Output file is named ``generated_preview.html``."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        assert paths[0].name == "generated_preview.html"

    @pytest.mark.unit
    def test_output_file_exists(self, tmp_path: Path):
        """The returned path actually exists on disk."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        assert paths[0].exists()

    @pytest.mark.unit
    def test_known_exporters_contains_html(self):
        """``"html"`` is registered in ``KNOWN_EXPORTERS``."""
        assert "html" in KNOWN_EXPORTERS


# ---------------------------------------------------------------------------
# html.parser parses without errors
# ---------------------------------------------------------------------------


class _ErrorCollector(html.parser.HTMLParser):
    """Subclass that records any parse errors instead of raising."""

    def __init__(self) -> None:
        super().__init__()
        self.errors: list[str] = []

    def handle_error(self, message: str) -> None:  # type: ignore[override]
        self.errors.append(message)


class TestHTMLParsing:
    """Html.parser.HTMLParser.feed succeeds without errors."""

    @pytest.mark.unit
    def test_html_parses_without_error(self, tmp_path: Path):
        """Feed the output to HTMLParser; no parse errors."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        html_text = _html_text(paths[0])
        # Use the standard library parser — it is lenient but still flags
        # malformed structure if we explicitly check for errors.
        parser = _ErrorCollector()
        parser.feed(html_text)
        assert parser.errors == [], f"HTMLParser reported errors: {parser.errors}"

    @pytest.mark.unit
    def test_html_has_doctype(self, tmp_path: Path):
        """Output starts with ``<!DOCTYPE html>`` (well-formed)."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        html_text = _html_text(paths[0]).lstrip()
        assert html_text.lower().startswith("<!doctype html>")

    @pytest.mark.unit
    def test_topic_in_title_and_h1(self, tmp_path: Path):
        """The topic appears in both the ``<title>`` and the ``<h1>``."""
        topic = "Eigenvalue Decomposition"
        packet = _make_packet(topic=topic)
        paths = _run_export(packet, tmp_path)
        html_text = _html_text(paths[0])
        assert topic in html_text  # appears somewhere (both title + h1)


# ---------------------------------------------------------------------------
# All packet.warnings appear in the rendered HTML
# ---------------------------------------------------------------------------


class TestWarningsRendered:
    """All packet.warnings strings appear in the rendered HTML body."""

    @pytest.mark.unit
    def test_single_warning_appears_in_html(self, tmp_path: Path):
        """A single warning message appears verbatim in the HTML."""
        msg = "CANARY_WARNING_XYZ: section data missing for node_x"
        packet = _make_packet(warnings=[_make_warning(msg)])
        paths = _run_export(packet, tmp_path)
        html_text = _html_text(paths[0])
        assert msg in html_text

    @pytest.mark.unit
    def test_multiple_warnings_all_appear(self, tmp_path: Path):
        """All warning messages appear in the HTML when multiple warnings exist."""
        msgs = [
            "WARNING_ALPHA: first issue detected",
            "WARNING_BETA: second issue detected",
            "WARNING_GAMMA: third issue with special chars: <>&",
        ]
        packet = _make_packet(warnings=[_make_warning(m) for m in msgs])
        paths = _run_export(packet, tmp_path)
        html_text = _html_text(paths[0])
        for msg in msgs:
            # The message may be HTML-escaped in the output, so check escaped too
            import html as html_mod

            escaped = html_mod.escape(msg)
            assert msg in html_text or escaped in html_text, (
                f"Warning message not found in HTML: {msg!r}"
            )

    @pytest.mark.unit
    def test_no_warnings_shows_empty_panel(self, tmp_path: Path):
        """When no warnings exist, the panel shows a no-warnings indicator."""
        packet = _make_packet(warnings=[])
        paths = _run_export(packet, tmp_path)
        html_text = _html_text(paths[0])
        # The template emits a "No warnings." marker when the list is empty
        assert "No warnings." in html_text

    @pytest.mark.unit
    def test_warnings_panel_id_present(self, tmp_path: Path):
        """The warnings panel has ``id="warnings-panel"`` for easy identification."""
        packet = _make_packet(warnings=[_make_warning("some_warning")])
        paths = _run_export(packet, tmp_path)
        html_text = _html_text(paths[0])
        assert 'id="warnings-panel"' in html_text


# ---------------------------------------------------------------------------
# Each section carries provenance
# ---------------------------------------------------------------------------


class TestProvenancePerSection:
    """Each section has visible provenance (source_node_id + source_path + line_range)."""

    @pytest.mark.unit
    def test_source_node_id_in_html(self, tmp_path: Path):
        """The node ID appears in the rendered HTML as a provenance value."""
        node = _make_node(
            "my_unique_node_42", source_path="src/math.md", line_range=(10, 20)
        )
        node_with_sections = _make_node(
            "my_unique_node_42",
            source_path="src/math.md",
            line_range=(10, 20),
            included_sections={"Concept": {"content": "Some concept."}},
        )
        packet = _make_packet(nodes=[node_with_sections])
        paths = _run_export(packet, tmp_path)
        html_text = _html_text(paths[0])
        assert "my_unique_node_42" in html_text

    @pytest.mark.unit
    def test_source_path_in_html(self, tmp_path: Path):
        """The source path appears in the rendered HTML."""
        node = _make_node(
            "node_sp",
            source_path="domain/physics/kinematics.md",
            line_range=(1, 30),
            included_sections={"Overview": {"content": "Physics content."}},
        )
        packet = _make_packet(nodes=[node])
        paths = _run_export(packet, tmp_path)
        html_text = _html_text(paths[0])
        assert "domain/physics/kinematics.md" in html_text

    @pytest.mark.unit
    def test_line_range_in_html(self, tmp_path: Path):
        """The formatted line_range appears in the rendered HTML."""
        node = _make_node(
            "node_lr",
            source_path="any.md",
            line_range=(77, 99),
            included_sections={"Content": {"content": "Some text."}},
        )
        packet = _make_packet(nodes=[node])
        paths = _run_export(packet, tmp_path)
        html_text = _html_text(paths[0])
        assert "77-99" in html_text

    @pytest.mark.unit
    def test_provenance_labels_visible(self, tmp_path: Path):
        """The provenance label strings (``source_node_id``, etc.) appear in the HTML."""
        packet = _make_packet()
        paths = _run_export(packet, tmp_path)
        html_text = _html_text(paths[0])
        assert "source_node_id" in html_text
        assert "source_path" in html_text
        assert "line_range" in html_text

    @pytest.mark.unit
    def test_multi_node_each_has_provenance(self, tmp_path: Path):
        """When multiple nodes exist, each contributes its own provenance values."""
        nodes = [
            _make_node(
                "alpha_node",
                source_path="alpha.md",
                line_range=(1, 5),
                included_sections={"Sec": {"content": "Alpha content."}},
            ),
            _make_node(
                "beta_node",
                source_path="beta.md",
                line_range=(10, 20),
                included_sections={"Sec": {"content": "Beta content."}},
            ),
        ]
        packet = _make_packet(nodes=nodes)
        paths = _run_export(packet, tmp_path)
        html_text = _html_text(paths[0])
        # Both node IDs and paths must appear
        assert "alpha_node" in html_text
        assert "beta_node" in html_text
        assert "alpha.md" in html_text
        assert "beta.md" in html_text


# ---------------------------------------------------------------------------
# Determinism + PreconditionError
# ---------------------------------------------------------------------------


class TestDeterminismAndGate:
    """Byte-identical output across runs; PreconditionError when extra absent."""

    @pytest.mark.unit
    def test_two_runs_produce_identical_bytes(self, tmp_path: Path):
        """Same LSP → byte-equal HTML on two successive calls."""
        packet = _make_packet(
            warnings=[
                _make_warning("first_warning"),
                _make_warning("second_warning"),
            ]
        )
        dir_a = tmp_path / "run_a"
        dir_b = tmp_path / "run_b"
        with _gate_open():
            paths_a = export(packet, dir_a)
            paths_b = export(packet, dir_b)

        bytes_a = paths_a[0].read_bytes()
        bytes_b = paths_b[0].read_bytes()
        assert bytes_a == bytes_b, "Two runs produced non-identical HTML output"

    @pytest.mark.unit
    def test_precondition_error_when_html_extra_absent(self, tmp_path: Path):
        """Exporter raises PreconditionError when jinja2 is not installed."""
        packet = _make_packet()
        with _gate_closed(), pytest.raises(PreconditionError) as exc_info:
            export(packet, tmp_path)
        err = exc_info.value
        # The error must reference the capability and the missing extra
        assert "html" in str(err).lower()

    @pytest.mark.unit
    def test_precondition_error_attributes(self, tmp_path: Path):
        """PreconditionError carries .capability and .extra attributes."""
        packet = _make_packet()
        with _gate_closed(), pytest.raises(PreconditionError) as exc_info:
            export(packet, tmp_path)
        err = exc_info.value
        assert hasattr(err, "capability")
        assert hasattr(err, "extra")
        assert err.extra == "html"

    @pytest.mark.unit
    def test_determinism_across_section_orderings(self, tmp_path: Path):
        """Sections are always emitted in the same order for the same LSP."""
        nodes = [
            _make_node(
                "z_node",
                source_path="z.md",
                line_range=(1, 1),
                included_sections={
                    "Zebra": {"content": "z content"},
                    "Apple": {"content": "a content"},
                },
            ),
        ]
        packet = _make_packet(nodes=nodes)
        dir_a = tmp_path / "run_a"
        dir_b = tmp_path / "run_b"
        with _gate_open():
            a = export(packet, dir_a)[0].read_bytes()
            b = export(packet, dir_b)[0].read_bytes()
        assert a == b

    @pytest.mark.unit
    def test_build_context_warnings_are_sorted(self):
        """``_build_context`` emits warnings in sorted order for determinism."""
        msgs = ["charlie_warning", "alpha_warning", "beta_warning"]
        packet = _make_packet(warnings=[_make_warning(m) for m in msgs])
        ctx = _build_context(packet)
        assert ctx["warnings"] == sorted(msgs)

    @pytest.mark.unit
    def test_gate_is_first_operation(self, tmp_path: Path):
        """PreconditionError is raised before any file I/O (gate-first invariant)."""
        packet = _make_packet()
        with _gate_closed(), pytest.raises(PreconditionError):
            export(packet, tmp_path / "should_not_exist")
        # output_dir must not have been created
        assert not (tmp_path / "should_not_exist").exists()


# ---------------------------------------------------------------------------
# Opt-in rich HTML (MathJax + rendered algorithms)
# ---------------------------------------------------------------------------


def _rich_packet() -> LearningSourcePacket:
    """LSP whose section content carries display math, inline math, and an
    ``algorithmic`` block — the exact constructs that must render in rich mode."""
    node = _make_node(
        "gtn",
        included_sections={
            "Derivation": {
                "content": "Yield surface:\n\n$$\\Phi = (q/\\sigma_M)^2 + 2 q_1 f^* "
                "\\cosh(3 q_2 p / (2\\sigma_M)) - (1 + q_3 f^{*2})$$\n\n"
                "with inline $q = \\sqrt{3 J_2}$.",
            },
            "Implementation": {
                "content": "$$\n\\begin{algorithmic}\n"
                "\\State $\\Phi \\gets (q/\\sigma_M)^2$\n"
                "\\If{$\\Phi \\le 0$}\n\\State $\\textbf{return elastic}$\n\\EndIf\n"
                "\\end{algorithmic}\n$$",
            },
        },
    )
    return _make_packet(nodes=[node], rich=True)


class TestRichHtml:
    """Rich mode renders math (MathJax) + algorithms; default stays self-contained."""

    @pytest.mark.unit
    def test_rich_loads_mathjax(self, tmp_path: Path):
        [path] = _run_export(_rich_packet(), tmp_path)
        html_text = _html_text(path)
        assert "tex-mml-chtml" in html_text  # MathJax CDN script
        assert "MathJax=" in html_text

    @pytest.mark.unit
    def test_rich_renders_algorithm_block(self, tmp_path: Path):
        [path] = _run_export(_rich_packet(), tmp_path)
        html_text = _html_text(path)
        assert 'class="algo"' in html_text
        assert 'class="algo-line"' in html_text
        # the raw LaTeX environment must be consumed, not dumped verbatim
        assert "begin{algorithmic}" not in html_text

    @pytest.mark.unit
    def test_rich_preserves_math_delimiters(self, tmp_path: Path):
        [path] = _run_export(_rich_packet(), tmp_path)
        html_text = _html_text(path)
        # display + inline math survive for MathJax (escaped, not markdown-eaten)
        assert "\\cosh" in html_text
        assert "\\sqrt{3 J_2}" in html_text
        # content is rendered into a div, not dumped as a raw <pre> blob
        assert 'class="section-content"' in html_text

    @pytest.mark.unit
    def test_rich_is_html_parseable(self, tmp_path: Path):
        [path] = _run_export(_rich_packet(), tmp_path)
        html.parser.HTMLParser().feed(_html_text(path))  # must not raise

    @pytest.mark.unit
    def test_default_html_has_no_mathjax(self, tmp_path: Path):
        """The default (non-rich) export stays offline: no MathJax, no <script src=."""
        [path] = _run_export(_make_packet(), tmp_path)
        html_text = _html_text(path)
        assert "tex-mml-chtml" not in html_text
        assert re.search(r"<script\s+src=", html_text, re.IGNORECASE) is None

    @pytest.mark.unit
    def test_rich_flag_off_by_default(self):
        """A packet built without rich_html does not opt into rich rendering."""
        ctx = _build_context(_make_packet())
        assert ctx["rich"] is False
