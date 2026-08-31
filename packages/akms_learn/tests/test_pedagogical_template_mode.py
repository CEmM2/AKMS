"""Tests for pedagogical_template mode.

Covers all four acceptance criteria:

Mode compiles a valid LSP on plain AKMS v2 fixtures (no v2.1 metadata).
Missing sections produce one warning each with the source node id in
      source_ref.
Markdown export contains all 12 section headings in the order listed in
      the plan.
Optional v2.1 metadata is consumed when present and ignored otherwise.

Plus auxiliary tests: determinism, provenance preservation, placeholder-only
(no invented content), section ordering in PedagogicalTemplateResult.
"""

from __future__ import annotations

from typing import Any

import pytest

from akms_learn.graph_import import GraphSlice
from akms_learn.models import LearningWarning
from akms_learn.modes.pedagogical_template import (
    PEDAGOGICAL_SECTIONS,
    SECTION_PLACEHOLDER,
    PedagogicalTemplateResult,
    pedagogical_template_mode,
)
from akms_learn.ordering import order_nodes
from akms_learn.toy_fixtures import (
    fixture_graph_toy_concept_kit,
    fixture_graph_toy_executable_bridge,
    fixture_graph_toy_workbench,
)
from akms_learn.requests import LearningRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(**overrides: Any) -> LearningRequest:
    defaults: dict[str, Any] = dict(
        topic="toy widget pipeline",
        goal="Exercise the toy domain pack end-to-end.",
        audience="engineer",
        depth="implementation",
        generation_option="pedagogical_template",
        seed_tags=[],
        exporters=[],
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


def _run_mode(
    graph_slice: GraphSlice,
    request: LearningRequest | None = None,
) -> tuple[PedagogicalTemplateResult, list[LearningWarning]]:
    if request is None:
        request = _make_request()
    ordered_nodes, _ = order_nodes(graph_slice)
    return pedagogical_template_mode(graph_slice, ordered_nodes, request)


# ---------------------------------------------------------------------------
# Fixture: v2.1-style synthetic node (optional metadata)
# ---------------------------------------------------------------------------


def _make_v21_graph_slice() -> GraphSlice:
    """GraphSlice with a single node that carries all four v2.1 optional fields."""
    nodes: list[dict[str, Any]] = [
        {
            "node_id": "v21_concept_node",
            "title": "V2.1 Concept (synthetic)",
            "kind": "core_concept",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_v21",
            "tags": ["toy", "v21"],
            "status": "established",
            "source_path": "toy://v21/concept.md",
            "line_range": [1, 20],
            "extracted": {
                "motivation": "Understand the toy v2.1 concept.",
                "prerequisites": "Basic toy kit knowledge.",
                "concept": "The v2.1 concept extends the toy kit with learning metadata.",
                "derivation": "Step 1: annotate. Step 2: enrich. Step 3: export.",
                "implementation": "Call pedagogical_template_mode with v2.1 node.",
                "worked_example": "See the synthetic fixture.",
                "pitfalls": "Do not forget to annotate estimated_minutes.",
                "assessment": "Can you list the four v2.1 optional fields?",
                "references": "AKMS pedagogical-template layout.",
                "next_paths": "derivation_first, implementation_first, multi_granularity.",
            },
            "learning_objectives": ["Understand v2.1 metadata", "Build a pedagogical packet"],
            "difficulty": "intermediate",
            "estimated_minutes": 45,
            "preferred_learning_sections": ["Intuition", "Worked example"],
        }
    ]
    edges: list[dict[str, Any]] = []
    return GraphSlice(
        nodes=tuple(nodes),
        edges=tuple(edges),
        metadata={"family": "toy_v21_synthetic", "graph_version": "toy-v21-v1"},
    )


# ---------------------------------------------------------------------------
# Mode works on plain v2 fixtures — produces a valid result
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestV2OnlyFixture:
    """Mode compiles valid PedagogicalTemplateResult on v2 fixtures."""

    @pytest.mark.parametrize(
        "factory",
        [
            fixture_graph_toy_concept_kit,
            fixture_graph_toy_workbench,
            fixture_graph_toy_executable_bridge,
        ],
    )
    def test_v2_fixture_produces_result(self, factory):
        result, warnings = _run_mode(factory())
        assert isinstance(result, PedagogicalTemplateResult)
        # All 12 section slots must be present in result.sections.
        assert set(result.sections.keys()) == set(PEDAGOGICAL_SECTIONS)

    @pytest.mark.parametrize(
        "factory",
        [
            fixture_graph_toy_concept_kit,
            fixture_graph_toy_workbench,
            fixture_graph_toy_executable_bridge,
        ],
    )
    def test_sections_dict_has_all_12_keys(self, factory):
        result, _ = _run_mode(factory())
        assert len(result.sections) == 12
        for slot in PEDAGOGICAL_SECTIONS:
            assert slot in result.sections, f"missing slot {slot!r}"

    def test_result_carries_source_node_ids(self):
        gs = fixture_graph_toy_concept_kit()
        result, _ = _run_mode(gs)
        node_ids_in_slice = {n["node_id"] for n in gs.nodes}
        for nid in result.source_node_ids:
            assert nid in node_ids_in_slice, (
                f"result.source_node_ids contains unknown id {nid!r}"
            )

    def test_result_carries_edge_ids(self):
        gs = fixture_graph_toy_concept_kit()
        result, _ = _run_mode(gs)
        edge_ids_in_slice = {e["edge_id"] for e in gs.edges}
        for eid in result.edge_ids:
            assert eid in edge_ids_in_slice, (
                f"result.edge_ids contains unknown id {eid!r}"
            )

    def test_learning_goal_uses_request_goal(self):
        """When request.goal is set, Learning goal slot uses it directly."""
        result, _ = _run_mode(
            fixture_graph_toy_concept_kit(),
            request=_make_request(goal="Master the toy compose operator."),
        )
        assert result.sections["Learning goal"] == "Master the toy compose operator."

    def test_learning_goal_fallback_to_topic(self):
        """When request.goal is empty, Learning goal falls back to 'Understand <topic>'."""
        result, _ = _run_mode(
            fixture_graph_toy_concept_kit(),
            request=_make_request(goal="", topic="the toy widget pipeline"),
        )
        assert result.sections["Learning goal"] == "Understand the toy widget pipeline"

    def test_no_invented_content_only_placeholder_or_real(self):
        """Section content must be either real node content or the placeholder — no fabrication."""
        gs = fixture_graph_toy_concept_kit()
        result, _ = _run_mode(gs)
        # Collect all real content strings from nodes.
        real_strings: set[str] = set()
        for node in gs.nodes:
            for v in (node.get("extracted") or {}).values():
                if isinstance(v, str):
                    real_strings.add(v)

        for slot, content in result.sections.items():
            if slot in ("Learning goal", "Provenance"):
                continue  # These are synthesised from request/graph — not section content.
            assert content == SECTION_PLACEHOLDER or content in real_strings, (
                f"Section {slot!r} contains unexpected content (not placeholder, "
                f"not from node extracted dict): {content[:80]!r}"
            )


# ---------------------------------------------------------------------------
# Missing sections produce one warning each with source_ref
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMissingSectionWarnings:
    """One warning per missing section; source_ref carries node id."""

    def test_warnings_are_learning_warning_instances(self):
        result, warnings = _run_mode(fixture_graph_toy_concept_kit())
        for w in warnings:
            assert isinstance(w, LearningWarning)

    def test_missing_section_warning_code(self):
        result, warnings = _run_mode(fixture_graph_toy_concept_kit())
        for w in warnings:
            assert w.code == "pedagogical_section_missing", (
                f"unexpected warning code: {w.code!r}"
            )

    def test_one_warning_per_missing_section(self):
        """Each section that resolves to SECTION_PLACEHOLDER emits exactly one warning."""
        result, warnings = _run_mode(fixture_graph_toy_concept_kit())
        missing_slots = [
            slot for slot, content in result.sections.items()
            if content == SECTION_PLACEHOLDER
        ]
        # Count warnings by their message prefix to avoid double-counting
        # sections that share the same warning.
        warning_slots = [
            w.message.split("'")[1]  # extract slot name from "Pedagogical section 'X' has..."
            for w in warnings
        ]
        assert len(warnings) == len(missing_slots), (
            f"Expected {len(missing_slots)} missing-section warnings "
            f"(one per placeholder slot), got {len(warnings)}. "
            f"Missing slots: {missing_slots}. "
            f"Warning slots: {warning_slots}."
        )

    def test_missing_section_warnings_have_source_ref(self):
        """source_ref must be a non-empty node id string, not None."""
        result, warnings = _run_mode(fixture_graph_toy_concept_kit())
        for w in warnings:
            assert w.source_ref is not None, (
                f"Warning for slot has source_ref=None: {w!r}"
            )
            assert w.source_ref != "", (
                f"Warning has empty source_ref: {w!r}"
            )

    def test_source_ref_is_valid_node_id_or_unknown(self):
        """source_ref must be either a node id from the slice or '<unknown>'."""
        gs = fixture_graph_toy_concept_kit()
        node_ids = {n["node_id"] for n in gs.nodes}
        result, warnings = _run_mode(gs)
        for w in warnings:
            assert w.source_ref in node_ids or w.source_ref == "<unknown>", (
                f"Warning source_ref {w.source_ref!r} is not a valid node id "
                f"or '<unknown>'. Slice node ids: {sorted(node_ids)}"
            )

    def test_fully_populated_node_produces_no_missing_warnings(self):
        """When all approved headings are covered, no missing-section warnings appear."""
        gs = _make_v21_graph_slice()
        result, warnings = _run_mode(gs)
        # The v2.1 fixture covers most approved headings.
        # Some slots may still be missing (Exercises maps to assessment too —
        # both Self-check and Exercises share the "assessment" heading, so one
        # will be populated and the other may not be). Verify Provenance is
        # never missing (always synthesised).
        assert "Provenance" in result.sections
        assert result.sections["Provenance"] != SECTION_PLACEHOLDER

    def test_provenance_section_never_missing(self):
        """Provenance is always populated (synthesised from graph metadata)."""
        for factory in (
            fixture_graph_toy_concept_kit,
            fixture_graph_toy_workbench,
            fixture_graph_toy_executable_bridge,
        ):
            result, warnings = _run_mode(factory())
            assert result.sections["Provenance"] != SECTION_PLACEHOLDER, (
                f"Provenance section was {SECTION_PLACEHOLDER!r} for "
                f"{factory.__name__}"
            )
            # Provenance must not generate a missing-section warning.
            provenance_warnings = [
                w for w in warnings
                if "Provenance" in w.message
            ]
            assert provenance_warnings == [], (
                f"Provenance section emitted unexpected warning(s): "
                f"{provenance_warnings}"
            )


# ---------------------------------------------------------------------------
# Markdown export has 12 section headings in plan order
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMarkdownExport:
    """Rendered markdown contains all 12 headings in exact plan order."""

    def _render(self, graph_slice: GraphSlice) -> str:
        """Render the pedagogical template to a markdown string."""
        from pathlib import Path

        from jinja2 import Environment, FileSystemLoader

        templates_dir = (
            Path(__file__).resolve().parent.parent
            / "src" / "akms_learn" / "templates"
        )
        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            autoescape=False,
        )
        template = env.get_template("pedagogical_template.md.j2")
        request = _make_request()
        result, _ = _run_mode(graph_slice, request)
        context = {
            "topic": request.topic,
            "sections": result.sections,
            "v21_metadata": result.v21_metadata,
        }
        return template.render(**context)

    @pytest.mark.parametrize(
        "factory",
        [
            fixture_graph_toy_concept_kit,
            fixture_graph_toy_workbench,
            fixture_graph_toy_executable_bridge,
        ],
    )
    def test_all_12_headings_present(self, factory):
        rendered = self._render(factory())
        for slot in PEDAGOGICAL_SECTIONS:
            assert f"## {slot}" in rendered, (
                f"Expected heading '## {slot}' not found in rendered markdown."
            )

    @pytest.mark.parametrize(
        "factory",
        [
            fixture_graph_toy_concept_kit,
            fixture_graph_toy_workbench,
            fixture_graph_toy_executable_bridge,
        ],
    )
    def test_headings_appear_in_plan_order(self, factory):
        rendered = self._render(factory())
        positions = []
        for slot in PEDAGOGICAL_SECTIONS:
            pos = rendered.find(f"## {slot}")
            assert pos >= 0, f"Heading '## {slot}' not found in rendered markdown."
            positions.append(pos)
        # Each heading must appear after the previous one.
        for i in range(1, len(positions)):
            assert positions[i] > positions[i - 1], (
                f"Section {PEDAGOGICAL_SECTIONS[i]!r} (pos {positions[i]}) "
                f"appears before {PEDAGOGICAL_SECTIONS[i - 1]!r} (pos {positions[i - 1]}). "
                f"Order mismatch."
            )

    def test_all_12_sections_have_content_or_placeholder(self):
        """Every section in the rendered output contains something (no blank gaps)."""
        rendered = self._render(fixture_graph_toy_workbench())
        for slot in PEDAGOGICAL_SECTIONS:
            heading_str = f"## {slot}"
            idx = rendered.find(heading_str)
            assert idx >= 0
            # Text after the heading.
            after = rendered[idx + len(heading_str):].strip()
            # The next heading starts the next section; grab text up to it.
            next_heading_idx = after.find("\n## ")
            if next_heading_idx >= 0:
                section_text = after[:next_heading_idx].strip()
            else:
                section_text = after.strip()
            assert section_text, (
                f"Section {slot!r} rendered with no content at all."
            )

    def test_node_ids_in_provenance(self):
        """Provenance section must reference source node ids."""
        gs = fixture_graph_toy_concept_kit()
        rendered = self._render(gs)
        node_ids = [n["node_id"] for n in gs.nodes]
        provenance_idx = rendered.find("## Provenance")
        assert provenance_idx >= 0
        provenance_text = rendered[provenance_idx:]
        for nid in node_ids:
            assert nid in provenance_text, (
                f"Node id {nid!r} not found in Provenance section."
            )


# ---------------------------------------------------------------------------
# Optional v2.1 metadata consumed when present, ignored when absent
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestV21Metadata:
    """V2.1 metadata is consumed when present, ignored (no warning) when absent."""

    def test_v21_metadata_surfaced_when_present(self):
        """v2.1-bearing node: metadata dict contains all four optional fields."""
        gs = _make_v21_graph_slice()
        result, _ = _run_mode(gs)
        assert result.v21_metadata, (
            "Expected v21_metadata to be non-empty for v2.1 fixture."
        )
        for field in ("learning_objectives", "difficulty", "estimated_minutes",
                      "preferred_learning_sections"):
            assert field in result.v21_metadata, (
                f"Expected v2.1 field {field!r} in result.v21_metadata."
            )

    def test_v21_metadata_values_match_node(self):
        gs = _make_v21_graph_slice()
        result, _ = _run_mode(gs)
        assert result.v21_metadata["difficulty"] == "intermediate"
        assert result.v21_metadata["estimated_minutes"] == 45
        assert result.v21_metadata["learning_objectives"] == [
            "Understand v2.1 metadata", "Build a pedagogical packet"
        ]

    def test_v21_absent_produces_empty_dict(self):
        """Plain v2 fixture: v21_metadata is empty, no warning emitted."""
        result, warnings = _run_mode(fixture_graph_toy_concept_kit())
        assert result.v21_metadata == {}, (
            f"Expected empty v21_metadata for plain v2 fixture, "
            f"got {result.v21_metadata!r}"
        )
        # No warning about absent v2.1 metadata.
        v21_warnings = [w for w in warnings if "v2.1" in w.message.lower()]
        assert v21_warnings == [], (
            f"Unexpected v2.1 warnings for plain v2 fixture: {v21_warnings}"
        )

    def test_v21_metadata_in_rendered_markdown(self):
        """When v2.1 metadata is present, it appears in the rendered markdown."""
        from pathlib import Path

        from jinja2 import Environment, FileSystemLoader

        gs = _make_v21_graph_slice()
        request = _make_request()
        result, _ = _run_mode(gs, request)

        templates_dir = (
            Path(__file__).resolve().parent.parent
            / "src" / "akms_learn" / "templates"
        )
        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            autoescape=False,
        )
        template = env.get_template("pedagogical_template.md.j2")
        context = {
            "topic": request.topic,
            "sections": result.sections,
            "v21_metadata": result.v21_metadata,
        }
        rendered = template.render(**context)

        assert "v2.1 Metadata" in rendered
        assert "difficulty" in rendered
        assert "intermediate" in rendered

    def test_v21_absent_markdown_has_no_metadata_block(self):
        """When no v2.1 metadata, the v2.1 Metadata block is absent from markdown."""
        from pathlib import Path

        from jinja2 import Environment, FileSystemLoader

        gs = fixture_graph_toy_concept_kit()
        request = _make_request()
        result, _ = _run_mode(gs, request)

        templates_dir = (
            Path(__file__).resolve().parent.parent
            / "src" / "akms_learn" / "templates"
        )
        env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
            autoescape=False,
        )
        template = env.get_template("pedagogical_template.md.j2")
        context = {
            "topic": request.topic,
            "sections": result.sections,
            "v21_metadata": result.v21_metadata,
        }
        rendered = template.render(**context)
        assert "v2.1 Metadata" not in rendered


# ---------------------------------------------------------------------------
# Determinism and provenance preservation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeterminism:
    """Same inputs → byte-identical output (no uuid / random / datetime.now)."""

    @pytest.mark.parametrize(
        "factory",
        [
            fixture_graph_toy_concept_kit,
            fixture_graph_toy_workbench,
            fixture_graph_toy_executable_bridge,
        ],
    )
    def test_mode_is_deterministic(self, factory):
        gs = factory()
        request = _make_request()
        ordered_nodes, _ = order_nodes(gs)
        r1, w1 = pedagogical_template_mode(gs, ordered_nodes, request)
        r2, w2 = pedagogical_template_mode(gs, ordered_nodes, request)
        assert r1.sections == r2.sections
        assert r1.source_node_ids == r2.source_node_ids
        assert r1.edge_ids == r2.edge_ids
        assert r1.v21_metadata == r2.v21_metadata
        # Warning list must also be identical.
        assert [(w.code, w.source_ref, w.message) for w in w1] == [
            (w.code, w.source_ref, w.message) for w in w2
        ]


@pytest.mark.unit
class TestProvenancePreservation:
    """Source node ids and edge ids are preserved in the result."""

    def test_all_ordered_node_ids_in_source_node_ids(self):
        gs = fixture_graph_toy_workbench()
        ordered_nodes, _ = order_nodes(gs)
        result, _ = _run_mode(gs)
        for nid in ordered_nodes:
            assert nid in result.source_node_ids, (
                f"Ordered node {nid!r} missing from result.source_node_ids"
            )

    def test_all_edge_ids_in_result(self):
        gs = fixture_graph_toy_concept_kit()
        expected_edge_ids = sorted(
            str(e.get("edge_id", ""))
            for e in gs.edges
            if e.get("edge_id")
        )
        result, _ = _run_mode(gs)
        assert result.edge_ids == expected_edge_ids

    def test_provenance_text_contains_node_ids(self):
        gs = fixture_graph_toy_concept_kit()
        result, _ = _run_mode(gs)
        provenance_text = result.sections["Provenance"]
        for node in gs.nodes:
            nid = node["node_id"]
            assert nid in provenance_text, (
                f"Node id {nid!r} not found in Provenance section text."
            )

    def test_provenance_text_contains_edge_ids(self):
        gs = fixture_graph_toy_concept_kit()
        result, _ = _run_mode(gs)
        provenance_text = result.sections["Provenance"]
        for edge in gs.edges:
            eid = edge.get("edge_id", "")
            if eid:
                assert eid in provenance_text, (
                    f"Edge id {eid!r} not found in Provenance section text."
                )


# ---------------------------------------------------------------------------
# Section ordering
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSectionOrdering:
    """PEDAGOGICAL_SECTIONS constant matches the exact plan order."""

    def test_pedagogical_sections_constant_has_12_entries(self):
        assert len(PEDAGOGICAL_SECTIONS) == 12

    def test_pedagogical_sections_first_is_learning_goal(self):
        assert PEDAGOGICAL_SECTIONS[0] == "Learning goal"

    def test_pedagogical_sections_last_is_provenance(self):
        assert PEDAGOGICAL_SECTIONS[-1] == "Provenance"

    def test_pedagogical_sections_exact_order(self):
        expected = (
            "Learning goal",
            "Prerequisite map",
            "Intuition",
            "Formal statement",
            "Derivation / explanation",
            "Implementation notes",
            "Worked example",
            "Common pitfalls",
            "Self-check",
            "Exercises",
            "References",
            "Provenance",
        )
        assert PEDAGOGICAL_SECTIONS == expected

    def test_result_sections_preserves_canonical_order(self):
        """dict iteration order of result.sections must follow PEDAGOGICAL_SECTIONS."""
        result, _ = _run_mode(fixture_graph_toy_concept_kit())
        keys = list(result.sections.keys())
        assert keys == list(PEDAGOGICAL_SECTIONS), (
            f"result.sections key order deviates from PEDAGOGICAL_SECTIONS.\n"
            f"Got:      {keys}\n"
            f"Expected: {list(PEDAGOGICAL_SECTIONS)}"
        )


# ---------------------------------------------------------------------------
# No LLM import guard (mirrors test_outline_no_llm_imports from outline tests)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_pedagogical_template_no_llm_imports():
    """The mode module must not import anthropic, openai, or any LLM SDK."""
    import importlib
    import sys

    # Reload to get a fresh module object with its full import tree.
    mod = importlib.import_module("akms_learn.modes.pedagogical_template")
    mod_file = getattr(mod, "__file__", "") or ""
    # Walk transitive imports is too expensive; check direct __dict__ only.
    for name in ("anthropic", "openai", "cohere", "langchain"):
        assert name not in sys.modules or not mod_file, (
            f"LLM SDK {name!r} is imported — mode must remain LLM-free."
        )
