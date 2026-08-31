"""Package-level tests for LSP Pydantic models.

Duplicate-by-design with the core-package test suite — no shared helper
import, so this package stays independently testable.
"""

import pytest
from pydantic import ValidationError

from akms_learn.models import (
    AssessmentView,
    CodeLinkView,
    CompilerInfo,
    LearningEdgeView,
    LearningNodeView,
    LearningRequestInfo,
    LearningSourcePacket,
    LearningWarning,
    PacketBody,
    PitfallView,
    ReferenceView,
    SourceInfo,
)


def _minimal_compiler() -> CompilerInfo:
    return CompilerInfo(name="akms.learn.compile_learning_source", version="0.1.0")


def _minimal_source() -> SourceInfo:
    return SourceInfo(graph_hash="sha256:abc", graph_path=".akms/graph.json")


def _minimal_request() -> LearningRequestInfo:
    return LearningRequestInfo(topic="J2 return mapping", request_hash="sha256:req")


def _minimal_node() -> LearningNodeView:
    return LearningNodeView(
        node_id="radial-return-j2",
        source_path="~/.claude/akms/nodes/plasticity/radial-return-j2.md",
        line_range=(1, 40),
    )


def _minimal_edge() -> LearningEdgeView:
    return LearningEdgeView(
        edge_id="e1",
        source_path=".akms/graph.json",
        line_range=(101, 110),
        **{"from": "yield-function-j2", "to": "radial-return-j2"},
    )


def _minimal_pitfall() -> PitfallView:
    return PitfallView(message="Beware mixing total and incremental strains.")


def _minimal_packet() -> LearningSourcePacket:
    return LearningSourcePacket(
        packet_id="pkt-001",
        created_at="2026-05-18T00:00:00+03:00",
        compiler=_minimal_compiler(),
        source=_minimal_source(),
        request=_minimal_request(),
        body=PacketBody(),
    )


class TestLspModels:
    """Tests for LSP Pydantic models."""

    @pytest.mark.unit
    def test_lsp_models_instantiate(self):
        """Every model constructs with minimal valid data."""
        # 1. LearningWarning
        w = LearningWarning(severity="info", code="X1", message="hello")
        assert w.severity == "info"

        # 2-4. Header blocks
        c = _minimal_compiler()
        s = _minimal_source()
        r = _minimal_request()
        assert (c.version, s.graph_hash, r.topic) == (
            "0.1.0",
            "sha256:abc",
            "J2 return mapping",
        )

        # 5. PacketBody
        body = PacketBody()
        assert body.nodes == [] and body.assessments == []

        # 6-7. View models with required provenance
        n = _minimal_node()
        e = _minimal_edge()
        assert n.node_id == "radial-return-j2"
        assert e.from_node == "yield-function-j2"

        # 8. PitfallView
        p = _minimal_pitfall()
        assert p.severity is None

        # 9. CodeLinkView
        cl = CodeLinkView(node_id="radial-return-j2", source_file="src/materials/j2.py")
        assert cl.symbols == []

        # 10. AssessmentView (stub)
        a = AssessmentView()
        assert a is not None

        # 11. ReferenceView
        ref = ReferenceView(title="Simo & Hughes 1998")
        assert ref.url is None

        # 12. LearningSourcePacket
        pkt = _minimal_packet()
        assert pkt.akms_learning_schema == "learn/v0.1"

    @pytest.mark.unit
    def test_lsp_round_trip(self):
        """Packet -> model_dump -> model_validate produces equal model."""
        pkt = LearningSourcePacket(
            packet_id="pkt-001",
            created_at="2026-05-18T00:00:00+03:00",
            compiler=_minimal_compiler(),
            source=_minimal_source(),
            request=_minimal_request(),
            body=PacketBody(
                nodes=[_minimal_node()],
                edges=[_minimal_edge()],
                pitfalls=[_minimal_pitfall()],
                code_links=[
                    CodeLinkView(
                        node_id="radial-return-j2",
                        source_file="src/materials/j2.py",
                        symbols=["update_stress"],
                    )
                ],
                assessments=[AssessmentView()],
                references=[ReferenceView(title="Simo & Hughes 1998")],
            ),
            warnings=[
                LearningWarning(severity="warning", code="W001", message="check"),
            ],
        )
        dumped = pkt.model_dump(by_alias=True)
        rebuilt = LearningSourcePacket.model_validate(dumped)
        assert rebuilt == pkt

    @pytest.mark.unit
    def test_assessment_view_stub(self):
        """Empty assessments list is valid; arbitrary stub content accepted."""
        # Empty constructor
        a_empty = AssessmentView()
        assert a_empty is not None

        # Arbitrary extra keys accepted
        a_arbitrary = AssessmentView(
            id="q-radial-return-01",
            type="short_answer",
            arbitrary_key="anything",
            extras={"nested": [1, 2, 3]},
        )
        dumped = a_arbitrary.model_dump()
        assert dumped.get("arbitrary_key") == "anything"
        assert dumped.get("id") == "q-radial-return-01"

        # Empty list of assessments is valid inside PacketBody
        body = PacketBody(assessments=[])
        assert body.assessments == []

    @pytest.mark.unit
    def test_provenance_fields_required(self):
        """Node/edge views without provenance fields fail validation."""
        # Missing all provenance on LearningNodeView
        with pytest.raises(ValidationError):
            LearningNodeView()  # type: ignore[call-arg]

        # Missing line_range on LearningNodeView
        with pytest.raises(ValidationError):
            LearningNodeView(  # type: ignore[call-arg]
                node_id="n1",
                source_path="nodes/n1.md",
            )

        # Missing source_path on LearningEdgeView
        with pytest.raises(ValidationError):
            LearningEdgeView(  # type: ignore[call-arg]
                edge_id="e1",
                line_range=(1, 2),
                **{"from": "a", "to": "b"},
            )

        # Missing edge_id on LearningEdgeView
        with pytest.raises(ValidationError):
            LearningEdgeView(  # type: ignore[call-arg]
                source_path="g.json",
                line_range=(1, 2),
                **{"from": "a", "to": "b"},
            )
