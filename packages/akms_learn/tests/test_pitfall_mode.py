"""Package-level tests for Mode 8 pitfall-driven.

Covers all 5 ACs:
  AC1 – pitfall edges produce PitfallView entries
  AC2 – four structured fields (symptom/cause/correction/diagnostics) surfaced
  AC3 – corrective_concepts contains node_ids reachable via requires/adjacent
  AC4 – thin/missing structured content emits LearningWarning(code='thin_pitfall_content')
  AC5 – determinism: same inputs → same PitfallView list order
"""

from __future__ import annotations

import pytest

from akms_learn.graph_import import GraphSlice, fixture_graph
from akms_learn.models import LearningWarning, PitfallView
from akms_learn.modes.pitfall import PITFALL_EDGE_TYPES, STRUCTURED_FIELDS, pitfall_mode
from akms_learn.sections import SectionView


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------


def _make_slice(nodes: list[dict], edges: list[dict]) -> GraphSlice:
    return GraphSlice(nodes=tuple(nodes), edges=tuple(edges), metadata={})


def _section_view(content: str, source_path: str = "test.md") -> SectionView:
    return SectionView(
        name="Pitfalls",
        content=content,
        source_path=source_path,
        line_range=(1, content.count("\n") + 1),
    )


def _parse_message(message: str) -> dict[str, str]:
    """Parse the encoded message string back into a key→value dict."""
    result: dict[str, str] = {}
    for line in message.splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            result[k.strip()] = v.strip()
        elif line.endswith(":"):
            result[line[:-1].strip()] = ""
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPitfallMode:
    """Tests for Mode 8 pitfall-driven.

    AC covered: 1, 2, 3, 4, 5.
    """

    @pytest.mark.integration
    def test_pitfall_edges_detected(self):
        """AC1 – Each pitfall_of edge in the fixture produces a PitfallView."""
        gs = fixture_graph()
        pitfall_count = sum(1 for e in gs.edges if e.get("type") in PITFALL_EDGE_TYPES)
        assert pitfall_count >= 1, "fixture_graph must have at least 1 pitfall_of edge"

        views, _warnings = pitfall_mode(gs, sections_by_node={})

        assert len(views) >= 1
        assert all(isinstance(v, PitfallView) for v in views)
        assert len(views) == pitfall_count

    @pytest.mark.integration
    def test_pitfall_view_four_fields(self):
        """AC2 – PitfallView message encodes all four structured fields."""
        pitfall_node = {
            "node_id": "pitfall_zero_det",
            "title": "Zero Determinant Pitfall",
            "source_path": "nodes/pitfall_zero_det.md",
        }
        corrective_node = {
            "node_id": "fix_conditioning",
            "title": "Conditioning Fix",
        }
        gs = _make_slice(
            nodes=[pitfall_node, corrective_node],
            edges=[
                {
                    "edge_id": "e_pf1",
                    "from": "ctx_node",
                    "to": "pitfall_zero_det",
                    "type": "pitfall_of",
                }
            ],
        )
        pitfalls_content = (
            "### Symptom\nA\n### Cause\nB\n### Correction\nC\n### Diagnostics\nD"
        )
        sections_by_node = {
            "pitfall_zero_det": {
                "Pitfalls": _section_view(pitfalls_content),
            }
        }

        views, warnings = pitfall_mode(gs, sections_by_node=sections_by_node)

        assert len(views) == 1
        v = views[0]
        parsed = _parse_message(v.message)

        assert parsed.get("symptom") == "A"
        assert parsed.get("cause") == "B"
        assert parsed.get("correction") == "C"
        assert parsed.get("diagnostics") == "D"
        # No thin-content warning when all fields present
        assert not any(w.code == "thin_pitfall_content" for w in warnings)

    @pytest.mark.integration
    def test_pitfall_corrective_concepts_linked(self):
        """AC3 – corrective_concepts in message contains node_ids reachable via requires."""
        pitfall_node = {"node_id": "pitfall_target", "title": "Bad Pitfall"}
        corrective_node = {"node_id": "corrective_node", "title": "Fix It"}
        gs = _make_slice(
            nodes=[pitfall_node, corrective_node],
            edges=[
                {
                    "edge_id": "e_pitfall_edge",
                    "from": "source_ctx",
                    "to": "pitfall_target",
                    "type": "pitfall_of",
                },
                {
                    "edge_id": "e_corrective",
                    "from": "pitfall_target",
                    "to": "corrective_node",
                    "type": "requires",
                },
            ],
        )

        views, _warnings = pitfall_mode(gs, sections_by_node={})

        assert len(views) == 1
        parsed = _parse_message(views[0].message)
        corrective_ids = [
            c for c in parsed.get("corrective_concepts", "").split(",") if c
        ]
        assert "corrective_node" in corrective_ids

    @pytest.mark.integration
    def test_pitfall_thin_content_warning(self):
        """AC4 – Empty structured fields emit LearningWarning(code='thin_pitfall_content')."""
        pitfall_node = {"node_id": "pitfall_empty", "title": "Empty Pitfall"}
        gs = _make_slice(
            nodes=[pitfall_node],
            edges=[
                {
                    "edge_id": "e_thin",
                    "from": "ctx",
                    "to": "pitfall_empty",
                    "type": "pitfall_of",
                }
            ],
        )
        # sections_by_node is empty → no Pitfalls section found
        views, warnings = pitfall_mode(gs, sections_by_node={})

        thin_warnings = [w for w in warnings if w.code == "thin_pitfall_content"]
        assert len(thin_warnings) == 1
        assert thin_warnings[0].source_ref == "pitfall_empty"
        assert isinstance(thin_warnings[0], LearningWarning)

    @pytest.mark.integration
    def test_pitfall_thin_content_warning_one_missing_field(self):
        """AC4 – A single missing field (Diagnostics empty) still emits thin_pitfall_content."""
        pitfall_node = {
            "node_id": "pitfall_partial",
            "title": "Partial Pitfall",
            "source_path": "nodes/pitfall_partial.md",
        }
        gs = _make_slice(
            nodes=[pitfall_node],
            edges=[
                {
                    "edge_id": "e_partial",
                    "from": "ctx",
                    "to": "pitfall_partial",
                    "type": "pitfall_of",
                }
            ],
        )
        # Three fields populated, Diagnostics intentionally empty.
        pitfalls_content = (
            "### Symptom\nSymptom text\n"
            "### Cause\nCause text\n"
            "### Correction\nCorrection text\n"
            "### Diagnostics\n"
        )
        sections_by_node = {
            "pitfall_partial": {
                "Pitfalls": _section_view(pitfalls_content),
            }
        }

        views, warnings = pitfall_mode(gs, sections_by_node=sections_by_node)

        thin_warnings = [w for w in warnings if w.code == "thin_pitfall_content"]
        assert len(thin_warnings) == 1, (
            "Exactly one warning per pitfall edge with any missing field"
        )
        assert thin_warnings[0].source_ref == "pitfall_partial"
        assert "diagnostics" in thin_warnings[0].message

    @pytest.mark.integration
    def test_pitfall_mode_deterministic(self):
        """AC5 – Same graph_slice → identical PitfallView list on two calls."""
        gs = fixture_graph()

        views1, warnings1 = pitfall_mode(gs, sections_by_node={})
        views2, warnings2 = pitfall_mode(gs, sections_by_node={})

        # PitfallView is a Pydantic model; compare via model_dump for equality
        dumps1 = [v.model_dump() for v in views1]
        dumps2 = [v.model_dump() for v in views2]
        assert dumps1 == dumps2

        warns1 = [w.model_dump() for w in warnings1]
        warns2 = [w.model_dump() for w in warnings2]
        assert warns1 == warns2
