"""Tests for ExtractedSection + the node-level section extractor.

Covers:

* ExtractedSection exposes the seven fields and extraction_method
  is a Literal of the four allowed values.
* Approved headings are recognised exactly (case-sensitive pass).
* Differently-cased headings are recognised via the
  case_insensitive fallback.
* Nodes without a matching heading fall back to fallback_summary
  or excerpt deterministically (no random tiebreaks).
* extract_sections propagates source_node_id, source_path and
  line_range from the source node.
"""

from __future__ import annotations

import typing
from pathlib import Path

import pytest

from akms_learn.toy_fixtures import (
    fixture_graph_toy_concept_kit,
    fixture_graph_toy_workbench,
)
from akms_learn.section_extraction import (
    APPROVED_HEADINGS,
    EXCERPT_MAX_CHARS,
    ExtractedSection,
    ExtractionMethod,
    extract_sections_from_node,
    extract_sections_from_nodes,
)


# ---------------------------------------------------------------------------
# model surface
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_extracted_section_has_seven_fields():
    """Dataclass surface."""
    section = ExtractedSection(
        name="motivation",
        normalized_name="motivation",
        content="why",
        source_node_id="n1",
        source_path=Path("x.md"),
        line_range=(1, 5),
        extraction_method="exact",
    )
    # All seven fields are accessible.
    assert section.name == "motivation"
    assert section.normalized_name == "motivation"
    assert section.content == "why"
    assert section.source_node_id == "n1"
    assert section.source_path == Path("x.md")
    assert section.line_range == (1, 5)
    assert section.extraction_method == "exact"


@pytest.mark.unit
def test_extraction_method_literal_has_four_values():
    """Extraction_method is a Literal of exactly four values."""
    args = typing.get_args(ExtractionMethod)
    assert set(args) == {
        "exact",
        "case_insensitive",
        "fallback_summary",
        "excerpt",
    }


@pytest.mark.unit
def test_extracted_section_is_frozen():
    """Dataclass is frozen so sections are hashable / immutable."""
    section = ExtractedSection(
        name="x",
        normalized_name="motivation",
        content="c",
        source_node_id="n",
        source_path=None,
        line_range=None,
        extraction_method="exact",
    )
    with pytest.raises(Exception):
        section.content = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# exact heading match
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_exact_heading_match_returns_exact():
    """A heading equal to an approved heading yields 'exact'."""
    node = {
        "node_id": "n_exact",
        "source_path": "/tmp/n.md",
        "line_range": [10, 20],
        "extracted": {
            "motivation": "Because it matters.",
            "concept": "The big idea.",
        },
    }
    sections = extract_sections_from_node(node)
    assert {s.normalized_name for s in sections} == {"motivation", "concept"}
    assert all(s.extraction_method == "exact" for s in sections)
    # Canonical ordering: motivation comes before concept in APPROVED_HEADINGS.
    assert sections[0].normalized_name == "motivation"
    assert sections[1].normalized_name == "concept"


# ---------------------------------------------------------------------------
# case-insensitive fallback
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_case_insensitive_heading_match_returns_case_insensitive():
    """'Motivation' / 'CONCEPT' match via case-insensitive tier."""
    node = {
        "node_id": "n_ci",
        "source_path": "/tmp/n.md",
        "line_range": [1, 2],
        "extracted": {
            "Motivation": "Capitalised.",
            "CONCEPT": "Shouting.",
        },
    }
    sections = extract_sections_from_node(node)
    methods = {s.normalized_name: s.extraction_method for s in sections}
    assert methods == {
        "motivation": "case_insensitive",
        "concept": "case_insensitive",
    }
    # Original heading text preserved in `name`; normalized name is canonical.
    name_map = {s.normalized_name: s.name for s in sections}
    assert name_map["motivation"] == "Motivation"
    assert name_map["concept"] == "CONCEPT"


@pytest.mark.unit
def test_exact_beats_case_insensitive_when_both_present():
    """Exact wins when both an exact and CI heading collide."""
    node = {
        "node_id": "n_both",
        "extracted": {
            "concept": "lowercase exact",
            "Concept": "capitalised CI",
        },
    }
    sections = extract_sections_from_node(node)
    # Exactly one canonical 'concept' record, sourced from the exact match.
    concept_records = [s for s in sections if s.normalized_name == "concept"]
    assert len(concept_records) == 1
    assert concept_records[0].extraction_method == "exact"
    assert concept_records[0].content == "lowercase exact"


# ---------------------------------------------------------------------------
# fallback ladder
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_match_with_summary_falls_back_to_summary():
    """No approved heading + summary present → fallback_summary."""
    node = {
        "node_id": "n_sum",
        "source_path": "/tmp/n.md",
        "line_range": [1, 4],
        "summary": "Two-sentence overview.",
        "extracted": {"Notes": "irrelevant heading"},
    }
    sections = extract_sections_from_node(node)
    assert len(sections) == 1
    s = sections[0]
    assert s.extraction_method == "fallback_summary"
    assert s.normalized_name == "summary"
    assert s.content == "Two-sentence overview."


@pytest.mark.unit
def test_no_match_no_summary_falls_back_to_excerpt():
    """No approved heading + no summary → excerpt of body."""
    body = "x" * (EXCERPT_MAX_CHARS + 200)
    node = {
        "node_id": "n_exc",
        "source_path": "/tmp/n.md",
        "line_range": [1, 50],
        "body": body,
        "extracted": {"Notes": "skipped"},
    }
    sections = extract_sections_from_node(node)
    assert len(sections) == 1
    s = sections[0]
    assert s.extraction_method == "excerpt"
    assert s.normalized_name == "excerpt"
    assert s.content == body[:EXCERPT_MAX_CHARS]
    assert len(s.content) == EXCERPT_MAX_CHARS


@pytest.mark.unit
def test_no_match_no_summary_no_body_returns_empty_excerpt():
    """Nothing to extract → single empty excerpt record (no crash)."""
    node = {"node_id": "n_empty"}
    sections = extract_sections_from_node(node)
    assert len(sections) == 1
    assert sections[0].extraction_method == "excerpt"
    assert sections[0].content == ""


@pytest.mark.unit
def test_approved_hit_suppresses_fallback_even_if_summary_present():
    """Fallback ladder is only consulted when zero approved hits."""
    node = {
        "node_id": "n_mix",
        "summary": "should NOT be emitted",
        "extracted": {"motivation": "real content"},
    }
    sections = extract_sections_from_node(node)
    methods = [s.extraction_method for s in sections]
    assert methods == ["exact"]
    assert all(s.normalized_name != "summary" for s in sections)


# ---------------------------------------------------------------------------
# provenance propagation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_source_metadata_propagation_real_path():
    """Source_node_id, source_path, line_range propagate."""
    node = {
        "node_id": "n_prov",
        "source_path": "/abs/path/to/node.md",
        "line_range": [12, 34],
        "extracted": {"derivation": "..."},
    }
    sections = extract_sections_from_node(node)
    assert len(sections) == 1
    s = sections[0]
    assert s.source_node_id == "n_prov"
    assert s.source_path == Path("/abs/path/to/node.md")
    assert s.line_range == (12, 34)


@pytest.mark.unit
def test_source_metadata_propagation_unknown_path_becomes_none():
    """'unknown' sentinel propagates as None for source_path."""
    node = {
        "node_id": "n_unknown",
        "source_path": "unknown",
        "line_range": [0, 0],
        "extracted": {"implementation": "code"},
    }
    sections = extract_sections_from_node(node)
    assert len(sections) == 1
    s = sections[0]
    assert s.source_node_id == "n_unknown"
    assert s.source_path is None
    assert s.line_range is None


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ordering_deterministic_across_two_runs():
    """(determinism) Same input → identical output across runs."""
    # Construct via dict literal so insertion order varies in spirit;
    # determinism comes from the extractor's sorted iteration.
    node = {
        "node_id": "n_det",
        "source_path": "/tmp/det.md",
        "line_range": [1, 100],
        "extracted": {
            "references": "see paper",
            "motivation": "why",
            "Concept": "case-insensitive hit",
            "derivation": "math",
        },
    }
    first = extract_sections_from_node(node)
    second = extract_sections_from_node(node)
    assert first == second
    # Canonical order across APPROVED_HEADINGS.
    assert [s.normalized_name for s in first] == [
        "motivation",
        "concept",
        "derivation",
        "references",
    ]


@pytest.mark.unit
def test_fixture_workbench_yields_only_approved_sections():
    """Toy workbench fixture's 'Derivation' heading hits the CI tier."""
    slice_ = fixture_graph_toy_workbench()
    node = next(n for n in slice_.nodes if n["node_id"] == "workbench_example")
    sections = extract_sections_from_node(dict(node))
    # The legacy heading vocabulary ("Learning goal", "Self-check", ...) does
    # NOT overlap the approved heading set EXCEPT for 'derivation' and
    # 'prerequisites', which match via the case-insensitive tier.
    methods = {s.normalized_name: s.extraction_method for s in sections}
    assert "prerequisites" in methods
    assert "derivation" in methods
    assert methods["prerequisites"] == "case_insensitive"
    assert methods["derivation"] == "case_insensitive"


@pytest.mark.unit
def test_fixture_concept_kit_falls_back_for_non_approved_headings():
    """Toy concept_kit uses 'Concept map' — not in approved set; falls back."""
    slice_ = fixture_graph_toy_concept_kit()
    for raw_node in slice_.nodes:
        node = dict(raw_node)
        sections = extract_sections_from_node(node)
        # 'Concept map' is not an approved heading → triggers excerpt fallback.
        assert len(sections) == 1
        assert sections[0].extraction_method in {
            "fallback_summary",
            "excerpt",
        }


@pytest.mark.unit
def test_extract_sections_from_nodes_batch():
    """The batch helper returns a dict keyed by node_id, preserving order."""
    nodes = [
        {"node_id": "a", "extracted": {"motivation": "a-mot"}},
        {"node_id": "b", "extracted": {"concept": "b-con"}},
    ]
    out = extract_sections_from_nodes(nodes)
    assert list(out.keys()) == ["a", "b"]
    assert out["a"][0].normalized_name == "motivation"
    assert out["b"][0].normalized_name == "concept"


@pytest.mark.unit
def test_approved_headings_match_spec_01_verbatim():
    """Spec mirror canary: APPROVED_HEADINGS must equal spec 01 §126-145."""
    # If this assertion fails, the spec was updated without bumping this
    # constant (or vice versa). Re-read spec 01 §126-145 before changing.
    assert APPROVED_HEADINGS == (
        "motivation",
        "prerequisites",
        "concept",
        "derivation",
        "implementation",
        "worked_example",
        "pitfalls",
        "assessment",
        "references",
        "next_paths",
    )
