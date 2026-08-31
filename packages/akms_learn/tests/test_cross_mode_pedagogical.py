"""Capabilities catalog + cross-mode sweep over the pedagogical modes.

Covers:

* Capabilities report lists ``pedagogical_template``, ``derivation_first``,
  ``implementation_first``, ``multi_granularity``.
* Cross-mode sweep covers every pedagogical surface with at least one
  assertion: pedagogical fallback, section extraction line ranges,
  derivation-first ordering, implementation anchor detection, code-link
  warnings, granularity convention selection, bundle manifest mode +
  granularity.
* All four pedagogical modes invoke LSP validation before export.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from akms_learn import (
    LearningRequest,
    compile_learning_source,
)
from akms_learn.graph_import import GraphSlice
from akms_learn.models import LearningSourcePacket
from akms_learn.toy_fixtures import (
    fixture_graph_toy_concept_kit,
    fixture_graph_toy_derivation_gap,
    fixture_graph_toy_executable_bridge,
    fixture_graph_toy_multi_granularity,
)
from akms_learn.plugin import get_plugin

PLAN2_MODE_KEYS: tuple[str, ...] = (
    "pedagogical_template",
    "derivation_first",
    "implementation_first",
    "multi_granularity",
)


def _make_request(
    generation_option: str,
    *,
    exporters: tuple[str, ...] = ("markdown", "bundle"),
    **overrides: Any,
) -> LearningRequest:
    defaults: dict[str, Any] = dict(
        topic="cross-mode sweep",
        goal="Exercise §11 bullets via the public compile pipeline.",
        audience="engineer",
        depth="implementation",
        generation_option=generation_option,
        seed_tags=[],
        exporters=list(exporters),
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


# ---------------------------------------------------------------------------
# Capabilities catalog
# ---------------------------------------------------------------------------


class TestPedagogicalCapabilities:
    """Verifies: capabilities report lists the four pedagogical modes."""

    @pytest.mark.regression
    def test_capabilities_lists_four_new_modes(self) -> None:
        caps = set(get_plugin().capabilities())
        for mode in PLAN2_MODE_KEYS:
            assert mode in caps, (
                f"capabilities() must include {mode!r}; got {sorted(caps)}"
            )

    @pytest.mark.regression
    def test_capabilities_preserves_baseline_strings(self) -> None:
        """Append-only invariant: the original 10 capability strings remain."""
        caps = get_plugin().capabilities()
        for required in (
            "learning_source_packet",
            "deterministic_outline",
            "node_anthology",
            "pitfall_driven",
            "markdown_export",
            "bundle_export",
            "domain_pack_registry",
            "static_domain_pack_descriptors",
            "source_pack_descriptors",
            "code_mirror_provenance",
        ):
            assert required in caps, f"capability {required!r} was removed"


# ---------------------------------------------------------------------------
# Cross-mode sweep
# ---------------------------------------------------------------------------


class TestPedagogicalCrossModeSweep:
    """Verifies: each pedagogical surface has at least one assertion."""

    @pytest.mark.regression
    def test_pedagogical_fallback_when_section_missing(self, tmp_path: Path) -> None:
        """§11 — pedagogical_template falls back when a section is absent.

        The toy_concept_kit fixture intentionally lacks several pedagogical
        slots (e.g. "Worked example", "Exercises"). The export must still
        produce a lesson.md that contains every canonical heading — the
        fallback path is the empty-section placeholder.
        """
        result = compile_learning_source(
            request=_make_request("pedagogical_template"),
            graph_slice=fixture_graph_toy_concept_kit(),
            output_dir=tmp_path,
        )
        content = (tmp_path / "lesson.md").read_text(encoding="utf-8")
        #   # The fallback contract is: heading must be present even when content
        #           # is sparse. This is the pedagogical-fallback canary.
        for heading in ("## Learning goal", "## Worked example", "## Exercises"):
            assert heading in content, (
                f"pedagogical fallback violated: heading {heading!r} missing"
            )
        assert result.packet.body.reading_order, "packet must record reading_order"

    @pytest.mark.regression
    def test_section_extraction_line_ranges_present(self, tmp_path: Path) -> None:
        """§11 — extracted section line ranges flow into the LSP via node line_range."""
        result = compile_learning_source(
            request=_make_request("derivation_first"),
            graph_slice=fixture_graph_toy_derivation_gap(),
            output_dir=tmp_path,
        )
        # Every node view carries its source line range from the slice.
        nodes_with_ranges = [
            n
            for n in result.packet.body.nodes
            if n.line_range and n.line_range != (0, 0)
        ]
        assert nodes_with_ranges, "no node view carried a non-zero line_range"

    @pytest.mark.regression
    def test_derivation_first_orders_heavy_before_light(self, tmp_path: Path) -> None:
        """§11 — derivation_first places ## Derivation before ## Implementation."""
        compile_learning_source(
            request=_make_request("derivation_first"),
            graph_slice=fixture_graph_toy_derivation_gap(),
            output_dir=tmp_path,
        )
        content = (tmp_path / "lesson.md").read_text(encoding="utf-8")
        deriv_idx = content.find("## Derivation")
        impl_idx = content.find("## Implementation")
        assert deriv_idx >= 0 and impl_idx >= 0
        assert deriv_idx < impl_idx, "derivation_first must place ## Derivation first"

    @pytest.mark.regression
    def test_implementation_anchor_detection(self, tmp_path: Path) -> None:
        """§11 — implementation_first detects code-mirror anchors via CodeLinkView."""
        result = compile_learning_source(
            request=_make_request("implementation_first"),
            graph_slice=fixture_graph_toy_executable_bridge(),
            output_dir=tmp_path,
        )
        # The executable-bridge fixture wires an implementation node via an
        # `implements` edge; CodeLinkView entries should populate.
        assert result.packet.body.code_links, (
            "implementation_first must populate body.code_links from `implements` edges"
        )

    @pytest.mark.regression
    def test_code_link_warning_emitted_end_to_end(self, tmp_path: Path) -> None:
        """§11 — code-link missing-source warning fires from the compile pipeline.

        Builds a minimal slice with an ``implements`` edge whose target is a
        ``code_mirror`` node with no usable ``source_path``. The compiler's
        Stage that builds CodeLinkView entries must emit a
        ``code_mirror_missing_source_path`` warning on the result.
        """
        slice_ = GraphSlice(
            nodes=(
                {
                    "node_id": "src_step",
                    "title": "Source Step (toy)",
                    "kind": "core_concept",
                    "domain": "toy_domain",
                    "tags": ["toy"],
                    "status": "established",
                    "source_path": "toy://src/step.md",
                    "line_range": [1, 4],
                    "extracted": {"concept": "# Concept\nA toy concept."},
                },
                {
                    "node_id": "broken_mirror",
                    "title": "Broken Mirror (toy)",
                    "kind": "code_mirror",
                    "domain": "toy_domain",
                    "tags": ["toy", "mirror"],
                    "status": "established",
                    "source_path": "",  # sentinel — triggers the warning
                    "line_range": [0, 0],
                    "extracted": {},
                },
            ),
            edges=(
                {
                    "edge_id": "e_impl",
                    "from": "src_step",
                    "to": "broken_mirror",
                    "type": "implements",
                    "source_path": "toy://edges.md",
                    "line_range": [1, 1],
                },
            ),
            metadata={"graph_version": "toy-broken-mirror-v1"},
        )

        result = compile_learning_source(
            request=_make_request("deterministic_outline"),
            graph_slice=slice_,
            output_dir=tmp_path,
        )
        codes = {w.code for w in result.warnings}
        assert "code_mirror_missing_source_path" in codes, (
            f"expected code_mirror_missing_source_path warning, got {sorted(codes)}"
        )

    @pytest.mark.regression
    def test_granularity_convention_selection(self, tmp_path: Path) -> None:
        """§11 — multi_granularity selects per convention (tags / id-prefix)."""
        result = compile_learning_source(
            request=_make_request("multi_granularity", granularity="overview"),
            graph_slice=fixture_graph_toy_multi_granularity(),
            output_dir=tmp_path,
        )
        # Granularity flows from the request through LearningRequestInfo to the
        # bundle manifest.
        manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["granularity"] == "overview"
        assert result.packet.request.granularity == "overview"

    @pytest.mark.regression
    def test_dict_request_granularity_not_silently_dropped(
        self, tmp_path: Path
    ) -> None:
        """A raw ``dict`` request (the CLI path) must carry ``granularity`` into
        ``multi_granularity_mode``. Before Stage 6 coerced dicts to a
        ``LearningRequest``, ``getattr(dict, "granularity")`` returned ``None``
        and the explicit selection was silently ignored.
        """
        result = compile_learning_source(
            request={
                "topic": "cross-mode sweep",
                "goal": "Exercise §11 bullets via the public compile pipeline.",
                "generation_option": "multi_granularity",
                "granularity": "overview",
                "exporters": ["markdown", "bundle"],
            },
            graph_slice=fixture_graph_toy_multi_granularity(),
            output_dir=tmp_path,
        )
        manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["granularity"] == "overview"
        assert result.packet.request.granularity == "overview"

    @pytest.mark.regression
    def test_dict_request_invalid_granularity_falls_back(self, tmp_path: Path) -> None:
        """An out-of-range ``granularity`` on a dict request must NOT raise on the
        model's ``Literal`` field — it falls back to ``None`` (matching the old
        permissive ``getattr``-on-dict behaviour) and the mode re-derives it.
        """
        result = compile_learning_source(
            request={
                "topic": "cross-mode sweep",
                "goal": "Exercise §11 bullets via the public compile pipeline.",
                "generation_option": "multi_granularity",
                "granularity": "bogus",
                "exporters": ["markdown", "bundle"],
            },
            graph_slice=fixture_graph_toy_multi_granularity(),
            output_dir=tmp_path,
        )
        # No exception raised by the model's Literal field: the invalid value
        # fell back to None on the request (vs. a ValidationError under a naive
        # ``LearningRequest(**dict)``), and the mode re-derived granularity from
        # conventions internally.
        assert result.packet.request.granularity is None

    @pytest.mark.regression
    def test_bundle_manifest_carries_mode_and_granularity(self, tmp_path: Path) -> None:
        """Bundle manifest records mode + granularity."""
        compile_learning_source(
            request=_make_request("multi_granularity", granularity="deep_dive"),
            graph_slice=fixture_graph_toy_multi_granularity(),
            output_dir=tmp_path,
        )
        manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["mode"] == "multi_granularity"
        assert manifest["granularity"] == "deep_dive"


# ---------------------------------------------------------------------------
# All four pedagogical modes validate LSP before export
# ---------------------------------------------------------------------------


def _fixture_for_mode(mode: str):
    """Return a fixture slice appropriate to the requested pedagogical mode."""
    if mode == "pedagogical_template":
        return fixture_graph_toy_concept_kit()
    if mode == "derivation_first":
        return fixture_graph_toy_derivation_gap()
    if mode == "implementation_first":
        return fixture_graph_toy_executable_bridge()
    if mode == "multi_granularity":
        return fixture_graph_toy_multi_granularity()
    raise AssertionError(f"unexpected mode: {mode!r}")


class TestPedagogicalLspValidation:
    """Verifies: every pedagogical mode validates LSP before writing exports."""

    @pytest.mark.regression
    @pytest.mark.parametrize("mode", PLAN2_MODE_KEYS)
    def test_each_mode_produces_lsp_that_revalidates(
        self, mode: str, tmp_path: Path
    ) -> None:
        """Compile, then re-`model_validate` the canonical JSON packet.

        Stage 9 of the compiler runs ``LearningSourcePacket.model_validate``
        on the assembled packet before writing exports. The check below is
        the same call on the round-tripped JSON — if Stage 9 emitted a
        non-validating packet the loader here will raise.
        """
        request_kwargs: dict[str, Any] = {}
        if mode == "multi_granularity":
            request_kwargs["granularity"] = "standard"

        result = compile_learning_source(
            request=_make_request(mode, **request_kwargs),
            graph_slice=_fixture_for_mode(mode),
            output_dir=tmp_path,
        )

        assert result.packet_path is not None
        raw = json.loads(result.packet_path.read_text(encoding="utf-8"))
        revalidated = LearningSourcePacket.model_validate(raw)
        assert revalidated.request.generation_option == mode
