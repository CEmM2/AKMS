"""Package-level tests for Mode 12 bundle exporter.

AC covered: 1, 2, 3, 4, 5.

The tests drive :func:`akms_learn.compile_learning_source` with
``exporters=["bundle"]`` and inspect the resulting bundle directory.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from akms_learn import (
    LearningRequest,
    compile_learning_source,
    fixture_graph,
)


def _make_request(**overrides) -> LearningRequest:
    """Build a minimal ``LearningRequest`` that requests the bundle exporter."""
    defaults: dict = dict(
        topic="j² return mapping",
        goal="Understand the j² return-mapping algorithm",
        audience="engineer",
        depth="implementation",
        generation_option="deterministic_outline",
        seed_tags=[],
        exporters=["bundle"],
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


_EXPECTED_ARTIFACT_NAMES: tuple[str, ...] = (
    "concept_map.json",
    "learning_source_packet.yaml",
    "lesson.md",
    "manifest.json",
    "provenance.json",
    "warnings.json",
)


class TestBundleExporter:
    """Tests for Mode 12 bundle exporter.

    AC covered: 1, 2, 3, 4, 5.
    """

    @pytest.mark.integration
    def test_bundle_writes_all_artifacts(self, tmp_path: Path) -> None:
        """All 7 artifacts (LSP yaml, manifest, lesson, concept_map, provenance, warnings) + exports/ + assets/ present."""
        request = _make_request()
        compile_learning_source(
            request=request,
            graph_slice=fixture_graph(),
            output_dir=tmp_path,
        )

        for name in _EXPECTED_ARTIFACT_NAMES:
            assert (tmp_path / name).is_file(), f"Missing artifact: {name}"

        # exports/ + assets/ directories present, each with a .gitkeep sentinel.
        assert (tmp_path / "exports").is_dir()
        assert (tmp_path / "assets").is_dir()
        assert (tmp_path / "exports" / ".gitkeep").is_file()
        assert (tmp_path / "assets" / ".gitkeep").is_file()

    @pytest.mark.integration
    def test_bundle_manifest_required_fields(self, tmp_path: Path) -> None:
        """manifest.json includes compiler_version + graph_hash + request_hash + learning_modes_used + artifact list."""
        request = _make_request()
        compile_learning_source(
            request=request,
            graph_slice=fixture_graph(),
            output_dir=tmp_path,
        )

        manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

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
        ):
            assert key in manifest, f"manifest.json missing key: {key}"

        assert isinstance(manifest["graph_hash"], str)
        assert manifest["graph_hash"], "graph_hash must be non-empty"
        assert isinstance(manifest["request_hash"], str)
        assert manifest["request_hash"], "request_hash must be non-empty"
        # Artifact list is sorted alphabetically.
        assert manifest["artifacts"] == sorted(manifest["artifacts"])
        # Every named artifact is listed.
        for name in _EXPECTED_ARTIFACT_NAMES:
            assert name in manifest["artifacts"]

    @pytest.mark.integration
    def test_bundle_reproducible_byte_equal(self, tmp_path: Path) -> None:
        """Two writes from the same packet produce byte-equal files per artifact (timestamps stripped)."""
        request = _make_request()
        slice_ = fixture_graph()

        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        compile_learning_source(request=request, graph_slice=slice_, output_dir=dir_a)
        compile_learning_source(request=request, graph_slice=slice_, output_dir=dir_b)

        # Files without timestamps — compare bytes directly.
        for name in (
            "concept_map.json",
            "manifest.json",
            "provenance.json",
            "warnings.json",
        ):
            bytes_a = (dir_a / name).read_bytes()
            bytes_b = (dir_b / name).read_bytes()
            assert bytes_a == bytes_b, f"{name} differs across runs"

        # LSP YAML carries ``created_at`` inside the packet header — strip it
        # before comparing.
        yaml_a = yaml.safe_load(
            (dir_a / "learning_source_packet.yaml").read_text(encoding="utf-8")
        )
        yaml_b = yaml.safe_load(
            (dir_b / "learning_source_packet.yaml").read_text(encoding="utf-8")
        )
        yaml_a.pop("created_at", None)
        yaml_b.pop("created_at", None)
        assert yaml_a == yaml_b

    @pytest.mark.integration
    def test_bundle_warnings_propagated(self, tmp_path: Path) -> None:
        """warnings.json matches the LearningWarning list on packet.warnings.

        Uses a ``seed_tags`` filter that excludes every fixture node so
        Stage 8 ``validate_packet`` emits an ``empty_nodes`` /
        ``empty_edges`` warning before Stage 9 runs the bundle exporter.
        This guarantees the bundle exporter sees a non-empty
        ``packet.warnings`` when it writes ``warnings.json``.
        """
        request = _make_request(seed_tags=["__no_such_tag__"])
        result = compile_learning_source(
            request=request,
            graph_slice=fixture_graph(),
            output_dir=tmp_path,
        )

        persisted = json.loads((tmp_path / "warnings.json").read_text(encoding="utf-8"))
        assert isinstance(persisted, list)
        assert persisted, "warnings.json must contain at least one entry"

        persisted_codes = {w.get("code") for w in persisted}
        packet_codes = {w.code for w in result.packet.warnings}
        assert persisted_codes == packet_codes
