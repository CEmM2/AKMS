"""Tests for Packet validation and warning accumulation.

Covers:

1. Valid packet passes ``validate_packet`` with empty or warning-only return.
2. Packet missing ``request_hash`` raises ``PacketValidationError``.
3. Edge referencing absent node_id raises ``PacketValidationError``.
4. ``WarningAccumulator`` preserves insertion order and dedups
   ``(code, source_ref)`` pairs.
5. Soft issue (missing teaching section) becomes ``LearningWarning``, not
   exception (covered via ``emit_missing_section_warning`` helper).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

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
from akms_learn.validation import PacketValidationError, validate_packet
from akms_learn.warnings import (
    WarningAccumulator,
    emit_missing_section_warning,
)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _make_packet(
    *,
    request_hash: str = "deadbeef",
    graph_hash: str = "cafebabe",
    nodes: list[LearningNodeView] | None = None,
    edges: list[LearningEdgeView] | None = None,
) -> LearningSourcePacket:
    """Build a minimal valid LSP for test scenarios."""
    if nodes is None:
        nodes = [
            LearningNodeView(
                node_id="n1",
                source_path="nodes/n1.md",
                line_range=(1, 10),
            ),
            LearningNodeView(
                node_id="n2",
                source_path="nodes/n2.md",
                line_range=(1, 10),
            ),
        ]
    if edges is None:
        edges = [
            LearningEdgeView(
                edge_id="e1",
                source_path="edges/e1.md",
                line_range=(1, 5),
                **{"from": "n1", "to": "n2"},
            )
        ]
    return LearningSourcePacket(
        packet_id="pkt-test",
        created_at="2026-05-18T00:00:00Z",
        compiler=CompilerInfo(name="akms-learn", version="0.1"),
        source=SourceInfo(
            graph_hash=graph_hash,
            graph_path="/tmp/graph.json",
        ),
        request=LearningRequestInfo(
            topic="test-topic",
            request_hash=request_hash,
        ),
        body=PacketBody(nodes=nodes, edges=edges),
    )


# ---------------------------------------------------------------------------
# AC #1 — valid packet passes
# ---------------------------------------------------------------------------


class TestValidatePacket:
    @pytest.mark.unit
    def test_validate_packet_valid(self) -> None:
        """A minimal well-formed packet validates and returns a list."""
        packet = _make_packet()
        result = validate_packet(packet)
        assert isinstance(result, list)
        # All items, if any, are LearningWarning (no errors raised).
        assert all(isinstance(w, LearningWarning) for w in result)

    # AC #2 — missing hash raises
    @pytest.mark.unit
    def test_validate_packet_missing_hash(self) -> None:
        """Packet with empty request_hash raises PacketValidationError."""
        packet = _make_packet(request_hash="")
        with pytest.raises(PacketValidationError) as excinfo:
            validate_packet(packet)
        assert "request_hash" in str(excinfo.value)

    @pytest.mark.unit
    def test_validate_packet_missing_graph_hash(self) -> None:
        """Packet with empty graph_hash raises PacketValidationError."""
        packet = _make_packet(graph_hash="")
        with pytest.raises(PacketValidationError) as excinfo:
            validate_packet(packet)
        assert "graph_hash" in str(excinfo.value)

    # AC #3 — dangling edge raises
    @pytest.mark.unit
    def test_validate_packet_dangling_edge(self) -> None:
        """Edge referencing an unknown node_id raises PacketValidationError."""
        nodes = [
            LearningNodeView(
                node_id="n1",
                source_path="nodes/n1.md",
                line_range=(1, 10),
            )
        ]
        edges = [
            LearningEdgeView(
                edge_id="e1",
                source_path="edges/e1.md",
                line_range=(1, 5),
                **{"from": "n1", "to": "ghost"},
            )
        ]
        packet = _make_packet(nodes=nodes, edges=edges)
        with pytest.raises(PacketValidationError) as excinfo:
            validate_packet(packet)
        assert "ghost" in str(excinfo.value)


# ---------------------------------------------------------------------------
# AC #4 — warning accumulator behavior
# ---------------------------------------------------------------------------


class TestWarningAccumulator:
    @pytest.mark.unit
    def test_warning_accumulator_order_preserved(self) -> None:
        """Three distinct (code, source_ref) warnings preserve insertion order."""
        acc = WarningAccumulator()
        w_a = LearningWarning(
            severity="warning", code="A", message="a", source_ref="x"
        )
        w_b = LearningWarning(
            severity="warning", code="B", message="b", source_ref="y"
        )
        w_c = LearningWarning(
            severity="info", code="C", message="c", source_ref="z"
        )
        acc.append(w_a)
        acc.append(w_b)
        acc.append(w_c)
        out = acc.finalize()
        assert [w.code for w in out] == ["A", "B", "C"]
        # finalize is idempotent / safe to call repeatedly
        assert acc.finalize() == out

    @pytest.mark.unit
    def test_warning_accumulator_dedup(self) -> None:
        """Same (code, source_ref) is deduped; first wins; order preserved."""
        acc = WarningAccumulator()
        w_first = LearningWarning(
            severity="warning", code="dup", message="first", source_ref="ref"
        )
        w_second = LearningWarning(
            severity="warning",
            code="dup",
            message="second-should-be-dropped",
            source_ref="ref",
        )
        w_other = LearningWarning(
            severity="warning", code="other", message="o", source_ref="ref"
        )
        acc.append(w_first)
        acc.append(w_second)
        acc.append(w_other)
        out = acc.finalize()
        assert len(out) == 2
        assert out[0].message == "first"
        assert out[1].code == "other"
        assert len(acc) == 2
        assert list(acc) == out

    # AC #5 / bonus — emit_missing_section_warning helper
    @pytest.mark.unit
    def test_emit_missing_section_warning(self) -> None:
        """Helper returns a soft LearningWarning carrying node_id+section."""
        w = emit_missing_section_warning("node-42", "prerequisites")
        assert isinstance(w, LearningWarning)
        assert w.severity == "warning"
        assert w.message
        # Either reflects the identifiers in message or source_ref.
        assert "node-42" in w.message or "node-42" in (w.source_ref or "")
        assert "prerequisites" in w.message or "prerequisites" in (
            w.source_ref or ""
        )

    @pytest.mark.unit
    def test_warning_model_is_frozen(self) -> None:
        """Defensive: LearningWarning is frozen — Pydantic prevents mutation."""
        w = LearningWarning(severity="warning", code="c", message="m")
        with pytest.raises(ValidationError):
            w.code = "other"  # type: ignore[misc]
