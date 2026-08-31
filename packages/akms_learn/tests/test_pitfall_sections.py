"""Tests for section-based pitfalls (the Nodes_Vault "Known Pitfalls" shape).

AKMS authors pitfalls two ways: as dedicated ``kind == 'pitfall'`` nodes, or as
a ``Pitfalls`` section inside a content node. The compiler now surfaces BOTH
into ``packet.body.pitfalls`` so the lesson Pitfalls section populates, while
the markdown exporter keeps section-pitfall *content nodes* in the main path.
"""

from __future__ import annotations

from typing import Any

import pytest

from akms_learn.compiler import _split_pitfall_paragraphs, compile_learning_source
from akms_learn.exporters.markdown import _classify_nodes
from akms_learn.graph_import import GraphSlice
from akms_learn.requests import LearningRequest


def _request(**overrides: Any) -> LearningRequest:
    defaults: dict[str, Any] = dict(
        topic="pitfalls",
        goal="exercise section-based pitfalls",
        audience="engineer",
        depth="implementation",
        generation_option="default",
        seed_tags=[],
        exporters=[],
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


def _node(node_id: str, markdown: str, *, kind: str | None = None) -> dict[str, Any]:
    node: dict[str, Any] = {
        "node_id": node_id,
        "title": f"Node {node_id}",
        "domain": "toy",
        "tags": [],
        "status": "established",
        "source_path": f"toy://{node_id}.md",
        "line_range": [1, 20],
        "markdown": markdown,
    }
    if kind is not None:
        node["kind"] = kind
    return node


_PITFALLS_MD = (
    "## Implementation\nthe code\n\n"
    "## Pitfalls\n"
    "**First gotcha:** do not foo the bar.\n\n"
    "**Second gotcha:** always baz before qux.\n"
)


class TestSplitPitfallParagraphs:
    @pytest.mark.unit
    def test_splits_on_blank_lines(self):
        out = _split_pitfall_paragraphs("**A:** one.\n\n**B:** two.")
        assert out == ["**A:** one.", "**B:** two."]

    @pytest.mark.unit
    def test_collapses_internal_whitespace(self):
        out = _split_pitfall_paragraphs("line one\n   line two")
        assert out == ["line one line two"]

    @pytest.mark.unit
    def test_single_paragraph_yields_one_entry(self):
        assert _split_pitfall_paragraphs("just one pitfall") == ["just one pitfall"]

    @pytest.mark.unit
    def test_empty_yields_nothing(self):
        assert _split_pitfall_paragraphs("\n\n   \n") == []


class TestSectionPitfallsPopulateBody:
    @pytest.mark.unit
    def test_pitfalls_section_becomes_pitfall_views(self):
        graph = GraphSlice(nodes=(_node("alpha", _PITFALLS_MD),), edges=(), metadata={})
        result = compile_learning_source(request=_request(), graph_slice=graph)
        pitfalls = result.packet.body.pitfalls
        messages = [pv.message for pv in pitfalls]
        assert "**First gotcha:** do not foo the bar." in messages
        assert "**Second gotcha:** always baz before qux." in messages
        # Section-derived entries carry "<nid>::pitfall::N" ids anchored to the node.
        assert all(pv.source_node_id == "alpha" for pv in pitfalls)
        assert all(pv.pitfall_id.startswith("alpha::pitfall::") for pv in pitfalls)

    @pytest.mark.unit
    def test_content_node_with_pitfalls_stays_in_reading_order(self):
        """Regression: a content node carrying a Pitfalls section must NOT be
        excluded from the main path the way a dedicated pitfall node is."""
        graph = GraphSlice(nodes=(_node("alpha", _PITFALLS_MD),), edges=(), metadata={})
        result = compile_learning_source(request=_request(), graph_slice=graph)
        packet = result.packet
        assert "alpha" in packet.body.reading_order
        _prereq_ids, pitfall_ids = _classify_nodes(packet)
        assert "alpha" not in pitfall_ids, "section-pitfall source node must stay in the main path"

    @pytest.mark.unit
    def test_node_without_pitfalls_section_contributes_none(self):
        graph = GraphSlice(
            nodes=(_node("alpha", "## Implementation\njust code\n"),), edges=(), metadata={}
        )
        result = compile_learning_source(request=_request(), graph_slice=graph)
        assert result.packet.body.pitfalls == []


class TestDedicatedPitfallNodeStillWorks:
    @pytest.mark.unit
    def test_kind_pitfall_node_rolls_up_and_is_classified(self):
        node = _node("pf", "## Concept\na pitfall node\n", kind="pitfall")
        graph = GraphSlice(nodes=(node,), edges=(), metadata={})
        result = compile_learning_source(request=_request(), graph_slice=graph)
        pitfalls = result.packet.body.pitfalls
        assert len(pitfalls) == 1
        # Node-based pitfall: pitfall_id == source_node_id == node id.
        assert pitfalls[0].pitfall_id == "pf"
        assert pitfalls[0].source_node_id == "pf"
        _prereq_ids, pitfall_ids = _classify_nodes(result.packet)
        assert "pf" in pitfall_ids
