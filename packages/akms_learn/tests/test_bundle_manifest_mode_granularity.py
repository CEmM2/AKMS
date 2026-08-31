"""Bundle manifest mode + granularity fields.

Covers:
  * Bundle manifest contains 'mode' for every export.
  * Bundle manifest contains 'granularity' when set; omits it otherwise.
  * Pre-existing manifest keys survive (additive-only change).
  * MANIFEST_VERSION unchanged (v1).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from akms_learn import LearningRequest, compile_learning_source, fixture_graph
from akms_learn.exporters.bundle import MANIFEST_VERSION


def _make_request(**overrides) -> LearningRequest:
    """Build a minimal LearningRequest that requests the bundle exporter."""
    defaults: dict = dict(
        topic="test topic",
        goal="test goal",
        audience="engineer",
        depth="implementation",
        generation_option="deterministic_outline",
        seed_tags=[],
        exporters=["bundle"],
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


def _read_manifest(output_dir: Path) -> dict:
    return json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))


class TestBundleManifestModeGranularity:
    """Bundle manifest mode + granularity fields."""

    @pytest.mark.integration
    def test_manifest_contains_mode_for_every_export(self, tmp_path: Path) -> None:
        """Verifies: manifest has 'mode' key for every export.

        Checks three different generation_option values to confirm 'mode' is
        always present regardless of which mode was requested.
        """
        for option in ("deterministic_outline", "node_anthology", "pitfall_driven"):
            out_dir = tmp_path / option
            compile_learning_source(
                request=_make_request(generation_option=option),
                graph_slice=fixture_graph(),
                output_dir=out_dir,
            )
            manifest = _read_manifest(out_dir)
            assert "mode" in manifest, (
                f"manifest.json missing 'mode' key for generation_option={option!r}"
            )
            assert manifest["mode"] == option, (
                f"manifest['mode']={manifest['mode']!r} != {option!r}"
            )

    @pytest.mark.integration
    def test_manifest_contains_granularity_when_set(self, tmp_path: Path) -> None:
        """Verifies: manifest contains 'granularity' for multi_granularity request."""
        for gran in ("overview", "standard", "deep_dive"):
            out_dir = tmp_path / gran
            compile_learning_source(
                request=_make_request(
                    generation_option="multi_granularity",
                    granularity=gran,
                ),
                graph_slice=fixture_graph(),
                output_dir=out_dir,
            )
            manifest = _read_manifest(out_dir)
            assert "granularity" in manifest, (
                f"manifest.json missing 'granularity' key for granularity={gran!r}"
            )
            assert manifest["granularity"] == gran, (
                f"manifest['granularity']={manifest['granularity']!r} != {gran!r}"
            )

    @pytest.mark.integration
    def test_manifest_omits_granularity_when_unset(self, tmp_path: Path) -> None:
        """Verifies: manifest omits 'granularity' (not null) for a legacy-mode export."""
        compile_learning_source(
            request=_make_request(generation_option="deterministic_outline"),
            graph_slice=fixture_graph(),
            output_dir=tmp_path,
        )
        manifest = _read_manifest(tmp_path)
        assert "granularity" not in manifest, (
            f"manifest.json must NOT contain 'granularity' when unset, "
            f"got: {manifest.get('granularity')!r}"
        )

    @pytest.mark.integration
    def test_baseline_manifest_byte_identical_across_runs(self, tmp_path: Path) -> None:
        """Verifies: pre-existing keys are byte-identical across two runs.

        The 'mode' key is additive; all pre-existing keys must remain present
        and unchanged in value. Two writes from the same packet must still be
        byte-equal (reproducibility invariant).
        """
        request = _make_request(generation_option="deterministic_outline")
        slice_ = fixture_graph()

        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        compile_learning_source(request=request, graph_slice=slice_, output_dir=dir_a)
        compile_learning_source(request=request, graph_slice=slice_, output_dir=dir_b)

        manifest_a = _read_manifest(dir_a)
        _read_manifest(dir_b)

        # Byte-equality across runs (reproducibility).
        assert (dir_a / "manifest.json").read_bytes() == (
            dir_b / "manifest.json"
        ).read_bytes(), "manifest.json differs across two identical runs"

        # All pre-existing required keys are still present.
        for key in (
            "manifest_version",
            "compiler_name",
            "compiler_version",
            "graph_hash",
            "request_hash",
            "learning_modes_used",
            "artifacts",
            "warnings",
            "unavailable_capabilities",
            "domain_packs",
            "source_packs",
        ):
            assert key in manifest_a, f"pre-existing key missing from manifest: {key!r}"

        # New additive key is also present.
        assert "mode" in manifest_a

    @pytest.mark.integration
    def test_manifest_version_stays_v1(self, tmp_path: Path) -> None:
        """Verifies: MANIFEST_VERSION still equals 'v1'."""
        assert MANIFEST_VERSION == "v1", (
            f"MANIFEST_VERSION must be 'v1', got {MANIFEST_VERSION!r}"
        )

        compile_learning_source(
            request=_make_request(),
            graph_slice=fixture_graph(),
            output_dir=tmp_path,
        )
        manifest = _read_manifest(tmp_path)
        assert manifest["manifest_version"] == "v1", (
            f"manifest.json manifest_version={manifest['manifest_version']!r}, expected 'v1'"
        )
