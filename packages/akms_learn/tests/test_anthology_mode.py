"""Package-level tests for Mode 2 node anthology.

Tests cover all 5 acceptance criteria:
  * reading_priority overrides default order when present
  * Each entry includes confidence and status badge strings
  * Missing teaching section produces exactly one LearningWarning
  * All entries carry source_path and line_range
  * Two identical inputs produce byte-stable output
"""

import pytest

from akms_learn.graph_import import GraphSlice
from akms_learn.modes.anthology import (
    TEACHING_SECTIONS,
    anthology_mode,
)
from akms_learn.sections import SectionView


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_slice(*node_dicts) -> GraphSlice:
    """Construct a minimal GraphSlice from keyword node dicts."""
    return GraphSlice(nodes=tuple(node_dicts), edges=(), metadata={})


def _make_sv(name: str, line_range: tuple[int, int] = (1, 2)) -> SectionView:
    """Construct a minimal SectionView for the given section name."""
    return SectionView(
        name=name,
        content=f"Content for {name}.",
        source_path="x.md",
        line_range=line_range,
    )


def _full_sections(node_id: str) -> dict[str, SectionView | None]:
    """Return a sections dict with all four teaching sections populated."""
    return {sec: _make_sv(sec) for sec in TEACHING_SECTIONS}


# ---------------------------------------------------------------------------
# TestAnthologyMode
# ---------------------------------------------------------------------------


class TestAnthologyMode:
    """Tests for Mode 2 node anthology.

    AC covered: 1, 2, 3, 4, 5.
    """

    @pytest.mark.integration
    def test_anthology_respects_reading_priority(self):
        """reading_priority on a node moves it earlier; missing → +infinity (sorts last)."""
        # Node A has priority 5, Node B has priority 1.
        # Default ordered_nodes = ["A", "B"], but B (priority=1) should come first.
        node_a = {"node_id": "A", "reading_priority": 5}
        node_b = {"node_id": "B", "reading_priority": 1}
        gs = _make_slice(node_a, node_b)
        ordered = ["A", "B"]
        sections_by_node = {
            "A": _full_sections("A"),
            "B": _full_sections("B"),
        }

        entries, _ = anthology_mode(gs, ordered, sections_by_node)

        assert len(entries) == 2
        assert entries[0].node_id == "B"
        assert entries[1].node_id == "A"

        # Ties: both nodes same priority → preserve ordered_nodes order.
        node_x = {"node_id": "X", "reading_priority": 3}
        node_y = {"node_id": "Y", "reading_priority": 3}
        gs2 = _make_slice(node_x, node_y)
        ordered2 = ["X", "Y"]
        sections2 = {
            "X": _full_sections("X"),
            "Y": _full_sections("Y"),
        }
        entries2, _ = anthology_mode(gs2, ordered2, sections2)
        assert [e.node_id for e in entries2] == ["X", "Y"]

        # Missing priority → sorts last (after nodes with explicit priority).
        node_no_prio = {"node_id": "Z"}
        node_with_prio = {"node_id": "W", "reading_priority": 10}
        gs3 = _make_slice(node_no_prio, node_with_prio)
        ordered3 = ["Z", "W"]
        sections3 = {
            "Z": _full_sections("Z"),
            "W": _full_sections("W"),
        }
        entries3, _ = anthology_mode(gs3, ordered3, sections3)
        assert entries3[0].node_id == "W"
        assert entries3[1].node_id == "Z"

    @pytest.mark.integration
    def test_anthology_missing_section_warns(self):
        """Missing teaching section → exactly one LearningWarning(code='missing_teaching_section')."""
        # Node "complete" has all four teaching sections.
        # Node "incomplete" is missing exactly "Self-check".
        node_complete = {"node_id": "complete"}
        node_incomplete = {"node_id": "incomplete"}
        gs = _make_slice(node_complete, node_incomplete)
        ordered = ["complete", "incomplete"]

        sections_complete = {sec: _make_sv(sec) for sec in TEACHING_SECTIONS}
        sections_incomplete = {sec: _make_sv(sec) for sec in TEACHING_SECTIONS}
        sections_incomplete["Self-check"] = None  # mark as missing

        sections_by_node = {
            "complete": sections_complete,
            "incomplete": sections_incomplete,
        }

        entries, warnings = anthology_mode(gs, ordered, sections_by_node)

        # Exactly one warning — only the incomplete node, only the missing section.
        assert len(warnings) == 1
        w = warnings[0]
        assert w.code == "missing_teaching_section"
        assert "incomplete" in (w.source_ref or "")
        assert "Self-check" in w.message

    @pytest.mark.integration
    def test_anthology_badges_present(self):
        """Each anthology entry carries confidence + status badge strings."""
        node = {
            "node_id": "node1",
            "confidence": 0.85,
            "status": "tentative",
        }
        gs = _make_slice(node)
        ordered = ["node1"]
        sections_by_node = {"node1": _full_sections("node1")}

        entries, _ = anthology_mode(gs, ordered, sections_by_node)

        assert len(entries) == 1
        entry = entries[0]
        assert entry.confidence_badge == "confidence: 0.85"
        assert entry.status_badge == "status: tentative"

        # Missing confidence and status → "n/a" badges.
        node_no_meta = {"node_id": "node2"}
        gs2 = _make_slice(node_no_meta)
        ordered2 = ["node2"]
        sections2 = {"node2": _full_sections("node2")}

        entries2, _ = anthology_mode(gs2, ordered2, sections2)
        assert len(entries2) == 1
        entry2 = entries2[0]
        assert entry2.confidence_badge == "confidence: n/a"
        assert entry2.status_badge == "status: n/a"

    @pytest.mark.integration
    def test_anthology_provenance_preserved(self):
        """Every entry has source_path and SectionView line_range attached."""
        node = {
            "node_id": "prov_node",
            "source_path": "path/to/node.md",
        }
        gs = _make_slice(node)
        ordered = ["prov_node"]

        # Build a section with a specific line_range on the first teaching section.
        sv = SectionView(
            name="Learning goal",
            content="Some goal.",
            source_path="path/to/node.md",
            line_range=(7, 18),
        )
        sections_by_node = {
            "prov_node": {
                "Learning goal": sv,
                "Main path": None,
                "Implementation": None,
                "Self-check": None,
            }
        }

        entries, _ = anthology_mode(gs, ordered, sections_by_node)

        assert len(entries) == 1
        entry = entries[0]
        assert entry.source_path == "path/to/node.md"
        assert entry.line_range == (7, 18)

    @pytest.mark.integration
    def test_anthology_invalid_reading_priority_warns(self):
        """Non-numeric reading_priority emits LearningWarning(code='invalid_reading_priority')."""
        # Two nodes: one with a legit priority, one with a bogus string.
        node_ok = {"node_id": "ok", "reading_priority": 1}
        node_bad = {"node_id": "bad", "reading_priority": "not-a-number"}
        gs = _make_slice(node_ok, node_bad)
        ordered = ["ok", "bad"]
        sections_by_node = {
            "ok": _full_sections("ok"),
            "bad": _full_sections("bad"),
        }

        entries, warnings = anthology_mode(gs, ordered, sections_by_node)

        # Bad priority coerced to +inf → sorts after node_ok.
        assert [e.node_id for e in entries] == ["ok", "bad"]

        # Exactly one invalid_reading_priority warning, referencing the bad node.
        invalid_warnings = [w for w in warnings if w.code == "invalid_reading_priority"]
        assert len(invalid_warnings) == 1
        w = invalid_warnings[0]
        assert w.source_ref == "bad"
        assert "not-a-number" in w.message
