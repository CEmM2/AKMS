"""Regression tests for four markdown-rendering fixes.

Each test pins one behavior so the fixes can't drift back:

1. ``main_path`` / ``implementation`` / ``derivation`` / ``self_check``
   preserve ``packet.body.reading_order`` instead of being sorted by node id.
2. The Implementation / derivation section emits a blank line between the
   implementation and derivation blocks when both are present.
3. Pitfall list items use the ``indent(2)`` Jinja filter so multi-line
   pitfall messages stay inside their list item.
4. The Provenance section's Node ids and Edge ids bullets render on
   separate lines (``trim_blocks=True`` would otherwise merge them).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from akms_learn.exporters.markdown import _build_context, export
from akms_learn.models import (
    CompilerInfo,
    LearningEdgeView,
    LearningNodeView,
    LearningRequestInfo,
    LearningSourcePacket,
    PacketBody,
    PitfallView,
    SourceInfo,
)


def _node(node_id: str, *, title: str | None = None, **sections) -> LearningNodeView:
    """Build a LearningNodeView with simple section content."""
    included = {
        heading: {"name": heading, "content": content, "source_path": "x.md",
                  "line_range": (1, 1)}
        for heading, content in sections.items()
    }
    return LearningNodeView(
        node_id=node_id,
        source_path="x.md",
        line_range=(1, 1),
        title=title,
        included_sections=included,
    )


def _packet(
    *,
    nodes: list[LearningNodeView],
    edges: list[LearningEdgeView] | None = None,
    pitfalls: list[PitfallView] | None = None,
    reading_order: list[str],
) -> LearningSourcePacket:
    """Build a minimal LearningSourcePacket for context/render tests."""
    body = PacketBody(
        nodes=nodes,
        edges=edges or [],
        pitfalls=pitfalls or [],
        reading_order=reading_order,
    )
    request = LearningRequestInfo(
        topic="t",
        goal="g",
        audience="engineer",
        depth="overview",
        generation_option="deterministic_outline",
        seed_tags=(),
        exporters=("markdown",),
        request_hash="r",
    )
    return LearningSourcePacket(
        packet_id="pkt-test",
        created_at="2026-05-20T00:00:00Z",
        request=request,
        source=SourceInfo(graph_hash="h", graph_path="x.json"),
        compiler=CompilerInfo(name="akms-learn", version="0.0.0"),
        body=body,
    )


class TestReadingOrderPreserved:
    """Fix #1 — sections that iterate over nodes must follow reading_order."""

    @pytest.mark.unit
    def test_main_path_follows_reading_order_not_alphabetical(self) -> None:
        """main_path emits nodes in reading_order, not alphabetic node_id order."""
        # If sorted alphabetically: alpha → beta → gamma.
        # reading_order forces: gamma → alpha → beta.
        nodes = [
            _node("alpha", title="Alpha Concept"),
            _node("beta", title="Beta Concept"),
            _node("gamma", title="Gamma Concept"),
        ]
        packet = _packet(nodes=nodes, reading_order=["gamma", "alpha", "beta"])
        ctx = _build_context(packet)

        assert ctx["main_path"] == ["Gamma Concept", "Alpha Concept", "Beta Concept"], (
            "main_path must follow reading_order; got "
            f"{ctx['main_path']!r}"
        )

    @pytest.mark.unit
    def test_implementation_concatenation_follows_reading_order(self) -> None:
        """Implementation content concatenates in reading_order, not node_id sort."""
        nodes = [
            _node("alpha", Implementation="A_impl"),
            _node("beta", Implementation="B_impl"),
            _node("gamma", Implementation="G_impl"),
        ]
        packet = _packet(nodes=nodes, reading_order=["gamma", "beta", "alpha"])
        ctx = _build_context(packet)

        # Reading-order-driven concatenation produces gamma → beta → alpha.
        assert ctx["implementation"] == "G_impl\n\nB_impl\n\nA_impl", (
            f"implementation order wrong: {ctx['implementation']!r}"
        )

    @pytest.mark.unit
    def test_derivation_concatenation_follows_reading_order(self) -> None:
        nodes = [
            _node("alpha", Derivation="A_deriv"),
            _node("beta", Derivation="B_deriv"),
        ]
        packet = _packet(nodes=nodes, reading_order=["beta", "alpha"])
        ctx = _build_context(packet)

        assert ctx["derivation"] == "B_deriv\n\nA_deriv"

    @pytest.mark.unit
    def test_self_check_concatenation_follows_reading_order(self) -> None:
        nodes = [
            _node("alpha", **{"Self-check": "A_sc"}),
            _node("beta", **{"Self-check": "B_sc"}),
        ]
        packet = _packet(nodes=nodes, reading_order=["beta", "alpha"])
        ctx = _build_context(packet)

        assert ctx["self_check"] == "B_sc\n\nA_sc"

    @pytest.mark.unit
    def test_empty_reading_order_falls_back_to_node_id_sort(self) -> None:
        """Compatibility: when reading_order is empty, fall back to sorted node_id."""
        nodes = [
            _node("beta", title="Beta"),
            _node("alpha", title="Alpha"),
            _node("gamma", title="Gamma"),
        ]
        packet = _packet(nodes=nodes, reading_order=[])
        ctx = _build_context(packet)

        assert ctx["main_path"] == ["Alpha", "Beta", "Gamma"]


class TestImplementationDerivationSeparator:
    """Fix #2 — a blank line must appear between implementation and derivation."""

    @pytest.mark.unit
    def test_blank_line_between_implementation_and_derivation(self, tmp_path: Path) -> None:
        """When both blocks render, they are separated by a blank line."""
        nodes = [_node("n1", Implementation="IMPL_BLOCK", Derivation="DERIV_BLOCK")]
        packet = _packet(nodes=nodes, reading_order=["n1"])

        export(packet, tmp_path)
        rendered = (tmp_path / "lesson.md").read_text(encoding="utf-8")

        # The two blocks must not be adjacent on the same line.
        assert "IMPL_BLOCKDERIV_BLOCK" not in rendered
        assert "IMPL_BLOCK\nDERIV_BLOCK" not in rendered
        # Either an explicit blank line OR a blank line between them is required.
        assert "IMPL_BLOCK\n\nDERIV_BLOCK" in rendered, (
            "Implementation and derivation must be separated by a blank line"
        )


class TestMultiLinePitfallIndent:
    """Fix #3 — multi-line pitfall messages stay inside their bullet via indent(2)."""

    @pytest.mark.unit
    def test_multi_line_pitfall_continuation_is_indented(self, tmp_path: Path) -> None:
        """Subsequent lines of a multi-line pitfall start with two spaces."""
        # A multi-line pitfall message — without indent(2) the second line
        # would land at column 0 and break list rendering.
        pitfalls = [
            PitfallView(
                pitfall_id="p1",
                source_node_id="n1",
                message="First line of pitfall\nSecond line continuation",
                severity="warning",
            ),
        ]
        nodes = [_node("n1")]
        packet = _packet(nodes=nodes, pitfalls=pitfalls, reading_order=["n1"])

        export(packet, tmp_path)
        rendered = (tmp_path / "lesson.md").read_text(encoding="utf-8")

        # The continuation line MUST be indented (two spaces) so markdown
        # parsers keep it inside the list item.
        assert "- First line of pitfall\n  Second line continuation" in rendered, (
            "Multi-line pitfall continuation must be indented by 2 spaces. "
            f"Got:\n{rendered}"
        )


class TestProvenanceNodeEdgeLinesSeparate:
    """Fix #4 — Node ids and Edge ids must render on distinct lines."""

    @pytest.mark.unit
    def test_node_ids_and_edge_ids_render_on_separate_lines(self, tmp_path: Path) -> None:
        """A blank line (or at minimum a newline) separates the two bullets."""
        nodes = [_node("n1")]
        edges = [
            LearningEdgeView(
                edge_id="e1",
                source_path="x.md",
                line_range=(1, 1),
                **{"from": "n1", "to": "n1"},
            ),
        ]
        packet = _packet(nodes=nodes, edges=edges, reading_order=["n1"])

        export(packet, tmp_path)
        rendered = (tmp_path / "lesson.md").read_text(encoding="utf-8")

        # The merged-line failure mode was: "Node ids ...` `e1` `- **Edge ids:**".
        # Both bullets must start on their own line beginning with "- **".
        assert "- **Node ids:**" in rendered
        assert "- **Edge ids:**" in rendered
        # And the Edge ids bullet must not appear glued onto the Node ids line.
        node_line = next(
            line for line in rendered.splitlines() if "**Node ids:**" in line
        )
        assert "**Edge ids:**" not in node_line, (
            "Node ids and Edge ids bullets must render on separate lines. "
            f"Found merged line: {node_line!r}"
        )
