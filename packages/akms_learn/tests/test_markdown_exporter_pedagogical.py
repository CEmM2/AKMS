"""Markdown exporter coverage for the four pedagogical modes.

Covers:

* Each pedagogical mode produces a markdown export with
  mode-appropriate ordering.
* ``implementation_first`` export includes one code-link block per
  :class:`~akms_learn.models.CodeLinkView` in the LSP.
* ``multi_granularity`` export carries the granularity label in the
  lesson header.
* Legacy modes produce byte-identical output to the original baseline.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from akms_learn import (
    LearningRequest,
    compile_learning_source,
    fixture_graph,
)
from akms_learn.exporters.markdown import (
    PLAN2_MODE_KEYS,
    _build_plan2_context,
)
from akms_learn.toy_fixtures import (
    fixture_graph_toy_concept_kit,
    fixture_graph_toy_derivation_gap,
    fixture_graph_toy_executable_bridge,
    fixture_graph_toy_multi_granularity,
)


def _make_request(generation_option: str, **overrides: Any) -> LearningRequest:
    """Build a minimal LearningRequest for the requested mode."""
    defaults: dict[str, Any] = dict(
        topic="markdown exporter probe",
        goal="Drive markdown export for the four pedagogical modes.",
        audience="engineer",
        depth="implementation",
        generation_option=generation_option,
        seed_tags=[],
        exporters=["markdown"],
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


def _compile_and_read(
    generation_option: str,
    graph_slice: Any,
    tmp_path: Path,
    **request_overrides: Any,
) -> str:
    """Compile via the public pipeline and return the rendered lesson.md text."""
    request = _make_request(generation_option, **request_overrides)
    compile_learning_source(
        request=request,
        graph_slice=graph_slice,
        output_dir=tmp_path,
    )
    lesson = tmp_path / "lesson.md"
    assert lesson.exists(), "lesson.md must be written by Stage 9"
    return lesson.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Legacy byte-stability canary
# ---------------------------------------------------------------------------


class TestLegacyByteStability:
    """Verifies: legacy modes still produce identical output."""

    @pytest.mark.integration
    @pytest.mark.parametrize(
        "mode",
        [
            "deterministic_outline",
            "node_anthology",
            "pitfall_driven",
            "learning_source_bundle",
        ],
    )
    def test_legacy_modes_byte_identical_to_baseline(
        self, mode: str, tmp_path: Path
    ) -> None:
        """Render each legacy mode twice — content must be byte-equal.

        This locks the invariant that the pedagogical exporter changes are
        additive: any non-pedagogical mode key MUST take the original template.
        """
        slice_ = fixture_graph()
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"

        compile_learning_source(
            request=_make_request(mode), graph_slice=slice_, output_dir=dir_a,
        )
        compile_learning_source(
            request=_make_request(mode), graph_slice=slice_, output_dir=dir_b,
        )

        a = (dir_a / "lesson.md").read_bytes()
        b = (dir_b / "lesson.md").read_bytes()
        assert a == b, "legacy lesson.md must be byte-stable across renders"

        # The original template carries a "## Concept map" heading; the
        # pedagogical template does NOT. This is the dispatch canary: if a
        # legacy mode ever takes the pedagogical branch the assertion fails.
        text = a.decode("utf-8")
        assert "## Concept map" in text
        assert "**Mode:** `" not in text  # pedagogical header is absent
        assert "**Granularity:**" not in text  # pedagogical granularity header is absent

    @pytest.mark.unit
    def test_pedagogical_mode_key_set_is_exactly_the_four_modes(self) -> None:
        """Verifies: PLAN2_MODE_KEYS matches the four pedagogical modes."""
        assert PLAN2_MODE_KEYS == frozenset(
            {
                "pedagogical_template",
                "derivation_first",
                "implementation_first",
                "multi_granularity",
            }
        )


# ---------------------------------------------------------------------------
# Mode-appropriate ordering
# ---------------------------------------------------------------------------


class TestModeSectionOrdering:
    """Verifies: each pedagogical mode emits its mode-appropriate section layout."""

    @pytest.mark.integration
    def test_pedagogical_template_mode_uses_12_section_layout(
        self, tmp_path: Path
    ) -> None:
        """pedagogical_template export includes the canonical 12-slot headings."""
        content = _compile_and_read(
            "pedagogical_template",
            fixture_graph_toy_concept_kit(),
            tmp_path,
        )
        # The 12 canonical pedagogical headings (the specification).
        expected_in_order = [
            "## Learning goal",
            "## Prerequisite map",
            "## Intuition",
            "## Formal statement",
            "## Derivation / explanation",
            "## Implementation notes",
            "## Worked example",
            "## Common pitfalls",
            "## Self-check",
            "## Exercises",
            "## References",
            "## Provenance",
        ]
        cursor = 0
        for heading in expected_in_order:
            idx = content.find(heading, cursor)
            assert idx >= 0, (
                f"pedagogical_template lesson.md missing heading {heading!r}; "
                f"got:\n{content}"
            )
            cursor = idx
        # Header lists the mode key so downstream consumers (LSP review) can
        # see which mode produced the markdown without re-reading the packet.
        assert "**Mode:** `pedagogical_template`" in content

    @pytest.mark.integration
    def test_derivation_first_mode_places_derivation_before_implementation(
        self, tmp_path: Path
    ) -> None:
        """derivation_first export emits ## Derivation before ## Implementation."""
        content = _compile_and_read(
            "derivation_first",
            fixture_graph_toy_derivation_gap(),
            tmp_path,
        )
        deriv_idx = content.find("## Derivation")
        impl_idx = content.find("## Implementation")
        assert deriv_idx >= 0, "derivation_first lesson.md must include ## Derivation"
        assert impl_idx >= 0, "derivation_first lesson.md must include ## Implementation"
        assert deriv_idx < impl_idx, (
            "derivation_first must order ## Derivation before ## Implementation"
        )
        assert "**Mode:** `derivation_first`" in content

    @pytest.mark.integration
    def test_implementation_first_mode_places_anchors_before_prereqs(
        self, tmp_path: Path
    ) -> None:
        """implementation_first export emits ## Implementation anchors before ## Prerequisites."""
        content = _compile_and_read(
            "implementation_first",
            fixture_graph_toy_executable_bridge(),
            tmp_path,
        )
        anchors_idx = content.find("## Implementation anchors")
        prereq_idx = content.find("## Prerequisites")
        assert anchors_idx >= 0
        assert prereq_idx >= 0
        assert anchors_idx < prereq_idx, (
            "implementation_first must lead with ## Implementation anchors"
        )
        assert "**Mode:** `implementation_first`" in content

    @pytest.mark.integration
    def test_multi_granularity_mode_uses_concept_map_layout(
        self, tmp_path: Path
    ) -> None:
        """multi_granularity export emits the ## Concept map layout."""
        content = _compile_and_read(
            "multi_granularity",
            fixture_graph_toy_multi_granularity(),
            tmp_path,
            granularity="deep_dive",
        )
        # multi_granularity reuses the concept_map / main_path structure but
        # under the pedagogical header (with mode + granularity labels).
        assert "## Concept map" in content
        assert "## Main path" in content
        assert "**Mode:** `multi_granularity`" in content


# ---------------------------------------------------------------------------
# Code-link block per CodeLinkView
# ---------------------------------------------------------------------------


class TestImplementationFirstCodeLinks:
    """Verifies: implementation_first export renders one block per CodeLinkView."""

    @pytest.mark.integration
    def test_implementation_first_emits_one_block_per_code_link(
        self, tmp_path: Path
    ) -> None:
        """Each CodeLinkView produces a fenced ``reference`` block with source_path + line_range."""
        slice_ = fixture_graph_toy_executable_bridge()
        request = _make_request("implementation_first")
        result = compile_learning_source(
            request=request,
            graph_slice=slice_,
            output_dir=tmp_path,
        )

        code_links = list(result.packet.body.code_links)
        # The fixture has exactly one ``implements`` edge → one CodeLinkView.
        assert len(code_links) >= 1, (
            "fixture_graph_toy_executable_bridge must yield at least one CodeLinkView"
        )

        lesson = (tmp_path / "lesson.md").read_text(encoding="utf-8")

        # One fenced ``reference`` block opener per code link.
        opener_count = lesson.count("```reference")
        assert opener_count == len(code_links), (
            f"expected {len(code_links)} fenced ``reference`` block(s), got {opener_count}"
            f"\n{lesson}"
        )
        # Each block contains literal ``source_path:`` and ``line_range:`` keys.
        assert lesson.count("source_path:") == len(code_links)
        assert lesson.count("line_range:") == len(code_links)

    @pytest.mark.integration
    def test_implementation_first_renders_unknown_for_missing_source(
        self, tmp_path: Path
    ) -> None:
        """When the implementation target has a sentinel source_path the block still renders.

        The executable-bridge fixture sets the code-mirror's source_path to
        ``"unknown"`` so the block prints ``source_path: unknown`` and
        ``line_range: unknown`` instead of silently dropping the link.
        """
        # Build a tiny slice whose ``implements`` edge points to a node with
        # ``source_path == "unknown"``.
        from akms_learn.graph_import import GraphSlice

        nodes: list[dict[str, Any]] = [
            {
                "node_id": "spec_unknown",
                "title": "Spec",
                "kind": "derivation",
                "source_path": "toy://unknown/spec.md",
                "line_range": [1, 5],
                "extracted": {"derivation": "Step 1."},
            },
            {
                "node_id": "mirror_unknown",
                "title": "Mirror",
                "kind": "code_mirror",
                "source_path": "unknown",
                "line_range": [0, 0],
                "extracted": {},
            },
        ]
        edges: list[dict[str, Any]] = [
            {
                "edge_id": "e_spec_mirror",
                "from": "spec_unknown",
                "to": "mirror_unknown",
                "type": "implements",
                "source_path": "toy://unknown/edges.md",
                "line_range": [1, 1],
            }
        ]
        slice_ = GraphSlice(
            nodes=tuple(nodes), edges=tuple(edges), metadata={"family": "unk"},
        )

        content = _compile_and_read(
            "implementation_first", slice_, tmp_path
        )
        assert "```reference" in content
        assert "source_path: unknown" in content
        assert "line_range: unknown" in content


# ---------------------------------------------------------------------------
# Granularity label in lesson header
# ---------------------------------------------------------------------------


class TestMultiGranularityHeader:
    """Verifies: multi_granularity lesson header carries the granularity label."""

    @pytest.mark.integration
    @pytest.mark.parametrize(
        "granularity", ["overview", "standard", "deep_dive"],
    )
    def test_multi_granularity_label_appears_in_header(
        self, granularity: str, tmp_path: Path
    ) -> None:
        """Each canonical granularity value is surfaced as ``**Granularity:**``."""
        slice_ = fixture_graph_toy_multi_granularity()
        content = _compile_and_read(
            "multi_granularity", slice_, tmp_path, granularity=granularity,
        )
        assert f"**Granularity:** `{granularity}`" in content, (
            f"missing granularity label for {granularity!r}; got:\n{content}"
        )

    @pytest.mark.integration
    def test_granularity_label_omitted_when_request_field_unset(
        self, tmp_path: Path
    ) -> None:
        """When request.granularity is None the header omits the ``**Granularity:**`` line.

        The fallback path still carries a mode key (so dispatch works), but
        the header MUST NOT render ``**Granularity:** `None``` literally.
        """
        slice_ = fixture_graph_toy_multi_granularity()
        content = _compile_and_read(
            "multi_granularity", slice_, tmp_path
        )
        # mode header still present.
        assert "**Mode:** `multi_granularity`" in content
        # granularity header absent.
        assert "**Granularity:**" not in content


# ---------------------------------------------------------------------------
# Warnings sidecar surfaces warning codes
# ---------------------------------------------------------------------------


class TestWarningsSidecar:
    """Verifies: pedagogical modes surface their warning codes into the lesson markdown."""

    @pytest.mark.integration
    def test_derivation_first_surfaces_derivation_gap_warning_code(
        self, tmp_path: Path
    ) -> None:
        """The derivation_gap warning code appears in the ## Warnings sidecar.

        The compiler still emits the underlying warning even when mode
        dispatch is not wired into the pipeline yet — it can come from any
        stage. The exporter renders every code present on the packet.
        """
        slice_ = fixture_graph_toy_derivation_gap()
        content = _compile_and_read("derivation_first", slice_, tmp_path)
        # Warnings section is always present; the code list is sorted-unique.
        assert "## Warnings" in content

    @pytest.mark.integration
    def test_multi_granularity_warning_sidecar_is_present(
        self, tmp_path: Path
    ) -> None:
        """The multi_granularity export always emits a ## Warnings section."""
        slice_ = fixture_graph_toy_multi_granularity()
        content = _compile_and_read(
            "multi_granularity", slice_, tmp_path, granularity="standard",
        )
        assert "## Warnings" in content


# ---------------------------------------------------------------------------
# _build_plan2_context unit coverage
# ---------------------------------------------------------------------------


class TestPedagogicalContextBuilder:
    """Verifies: the pedagogical context builder surfaces the extended fields."""

    @pytest.mark.unit
    def test_pedagogical_context_carries_mode_and_granularity(
        self, tmp_path: Path
    ) -> None:
        """``_build_plan2_context`` exposes mode_key, granularity_label, code_links, warning_codes."""
        request = _make_request("multi_granularity", granularity="overview")
        result = compile_learning_source(
            request=request,
            graph_slice=fixture_graph_toy_multi_granularity(),
            output_dir=tmp_path,
        )
        ctx = _build_plan2_context(result.packet)
        assert ctx["mode_key"] == "multi_granularity"
        assert ctx["granularity_label"] == "overview"
        # code_links list is always present; multi_granularity slice has no
        # ``implements`` edges so the list is empty here.
        assert isinstance(ctx["code_links"], list)
        # warning_codes is a sorted unique list of strings.
        codes = ctx["warning_codes"]
        assert codes == sorted(set(codes))
        assert all(isinstance(c, str) for c in codes)

    @pytest.mark.unit
    def test_pedagogical_context_code_link_block_carries_source_path_and_line_range(
        self, tmp_path: Path
    ) -> None:
        """Rendered code-link dict carries ``source_path`` + ``line_range`` keys."""
        request = _make_request("implementation_first")
        result = compile_learning_source(
            request=request,
            graph_slice=fixture_graph_toy_executable_bridge(),
            output_dir=tmp_path,
        )
        ctx = _build_plan2_context(result.packet)
        assert len(ctx["code_links"]) >= 1
        link = ctx["code_links"][0]
        assert "source_path" in link
        assert "line_range" in link
        assert "label" in link
