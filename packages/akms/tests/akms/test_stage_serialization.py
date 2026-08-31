"""Tests for stage wire serialization and backward-compatible loading."""

import json
from pathlib import Path

import pytest

from akms.orchestrator.stages import (
    PipelineState,
    Stage,
    stage_from_wire,
    stage_to_wire,
)


class TestStageToWire:
    def test_all_stages_lowercase(self):
        for stage in Stage:
            assert stage_to_wire(stage) == stage.name.lower()

    def test_execute(self):
        assert stage_to_wire(Stage.EXECUTE) == "execute"

    def test_init(self):
        assert stage_to_wire(Stage.INIT) == "init"


class TestStageFromWire:
    def test_stage_enum_passthrough(self):
        assert stage_from_wire(Stage.EXECUTE) is Stage.EXECUTE

    def test_int(self):
        assert stage_from_wire(4) is Stage.EXECUTE

    def test_string_int(self):
        assert stage_from_wire("4") is Stage.EXECUTE

    def test_uppercase_name(self):
        assert stage_from_wire("EXECUTE") is Stage.EXECUTE

    def test_lowercase_name(self):
        assert stage_from_wire("execute") is Stage.EXECUTE

    def test_prefixed_name(self):
        assert stage_from_wire("Stage.EXECUTE") is Stage.EXECUTE

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError, match="Invalid stage string"):
            stage_from_wire("nonexistent")

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="Invalid stage type"):
            stage_from_wire(3.14)


class TestPipelineStateRoundtrip:
    def test_save_stores_stage_as_string(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / "knowledge" / "graph").mkdir(parents=True)

        state = PipelineState(current_stage=Stage.EXECUTE, goal="test")
        state.save(repo)

        raw = json.loads(
            (repo / "knowledge" / "graph" / "pipeline_state.json").read_text()
        )
        assert raw["current_stage"] == "execute"  # string on disk, not int

    def test_load_reads_string_format(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / "knowledge" / "graph").mkdir(parents=True)

        state = PipelineState(current_stage=Stage.REVIEW, goal="test")
        state.save(repo)

        loaded = PipelineState.load(repo)
        assert loaded.current_stage is Stage.REVIEW

    def test_backward_compat_loads_old_name_format(self, tmp_path):
        """Old format used Stage.name (uppercase) — still loadable."""
        repo = tmp_path / "repo"
        (repo / "knowledge" / "graph").mkdir(parents=True)

        old_data = {"current_stage": "EXECUTE", "current_phase": 2, "goal": "old"}
        (repo / "knowledge" / "graph" / "pipeline_state.json").write_text(
            json.dumps(old_data)
        )

        loaded = PipelineState.load(repo)
        assert loaded.current_stage is Stage.EXECUTE
        assert loaded.current_phase == 2
