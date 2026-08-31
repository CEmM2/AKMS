"""Full E2E pipeline tests.

Validates the complete INIT → PLAN → TASK_BREAKDOWN → SCAFFOLD → EXECUTE →
REVIEW → FINALIZE → COMPLETE flow using FakeAgent + AutoApproveCheckpointHandler.

Acceptance criteria:
[0] Pipeline with FakeAgent completes all stages through COMPLETE
[1] AutoApproveCheckpointHandler sees all 6 checkpointed stages
[2] PipelineState shows completed=True, current_stage=COMPLETE
[3] FakeAgent memory files created for dispatched tasks
[4] No real LLM calls (FakeAgent is deterministic)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from akms.orchestrator.orchestrator import run_pipeline
from akms.orchestrator.stages import PipelineState, Stage
from akms.schema.models import PropagationConfig
from tests.fakes.checkpoint_handlers import AutoApproveCheckpointHandler
from tests.fakes.fake_agent import FakeAgent

# All stages that must be checkpointed (between INIT and COMPLETE)
_EXPECTED_CHECKPOINTED_STAGES = [
    "PLAN",
    "TASK_BREAKDOWN",
    "SCAFFOLD",
    "EXECUTE",
    "REVIEW",
    "FINALIZE",
]


def _make_repo(tmp_path: Path) -> Path:
    """Create a minimal repo directory structure for E2E pipeline tests."""
    repo = tmp_path / "repo"
    for d in ("graph", "nodes", "checkpoints", "loadouts", "sessions"):
        (repo / "knowledge" / d).mkdir(parents=True)
    return repo


def _run_full_pipeline(tmp_path: Path) -> tuple[Path, AutoApproveCheckpointHandler]:
    """Run the full pipeline with FakeAgent and return (repo, handler)."""
    repo = _make_repo(tmp_path)
    handler = AutoApproveCheckpointHandler()
    asyncio.run(
        run_pipeline(
            repo_root=repo,
            goal="e2e test",
            plan_name="test",
            agent_cls=FakeAgent,
            config=PropagationConfig(),
            checkpoint_handler=handler,
        )
    )
    return repo, handler


class TestFullPipelineE2E:
    """Full E2E pipeline tests.

    Acceptance criteria:
    [0] Pipeline with FakeAgent completes all stages through COMPLETE
    [1] AutoApproveCheckpointHandler sees all 6 checkpointed stages
    [2] PipelineState shows completed=True, current_stage=COMPLETE
    [3] FakeAgent memory files created for dispatched tasks
    [4] No real LLM calls (FakeAgent is deterministic)
    """

    @pytest.mark.e2e
    def test_full_pipeline_reaches_complete(self, tmp_path):
        """Verifies: Pipeline with FakeAgent reaches COMPLETE.
        Acceptance criterion: Pipeline completes all stages through COMPLETE
        Passes when: state.completed is True and state.current_stage == Stage.COMPLETE.
        """
        repo, _ = _run_full_pipeline(tmp_path)

        state = PipelineState.load(repo)
        assert state is not None, "PipelineState should be persisted after run"
        assert state.completed is True, (
            f"state.completed should be True after full pipeline, got {state.completed}"
        )
        assert state.current_stage == Stage.COMPLETE, (
            f"state.current_stage should be COMPLETE, got {state.current_stage}"
        )

    @pytest.mark.e2e
    def test_all_checkpointed_stages_presented(self, tmp_path):
        """Verifies: All 6 checkpointed stages presented to handler.
        Acceptance criterion: PLAN, TASK_BREAKDOWN, SCAFFOLD, EXECUTE, REVIEW, FINALIZE
        Passes when: All 6 stage names appear in handler.checkpoints_seen.
        """
        _, handler = _run_full_pipeline(tmp_path)

        for stage_name in _EXPECTED_CHECKPOINTED_STAGES:
            assert stage_name in handler.checkpoints_seen, (
                f"Stage {stage_name!r} was not presented to checkpoint handler. "
                f"Stages seen: {handler.checkpoints_seen}"
            )

    @pytest.mark.e2e
    def test_fake_agent_memory_files_created(self, tmp_path):
        """Verifies: FakeAgent memory files created for dispatched tasks.
        Acceptance criterion: Memory files exist in knowledge/sessions/
        Passes when: At least one .md file exists in sessions directory.
        """
        repo, _ = _run_full_pipeline(tmp_path)

        sessions_dir = repo / "knowledge" / "sessions"
        md_files = list(sessions_dir.glob("*.md"))
        assert len(md_files) >= 1, (
            f"Expected at least one .md file in {sessions_dir}, found none. "
            f"FakeAgent should write memory files for every dispatched task."
        )

    @pytest.mark.e2e
    def test_pipeline_state_final_state(self, tmp_path):
        """Verifies: PipelineState final state is correct.
        Acceptance criterion: completed=True, current_stage=COMPLETE, current_phase >= 1
        Passes when: All state fields have expected final values.
        """
        repo, _ = _run_full_pipeline(tmp_path)

        state = PipelineState.load(repo)
        assert state is not None, "PipelineState should be persisted after run"
        assert state.completed is True, (
            f"state.completed should be True, got {state.completed}"
        )
        assert state.current_stage == Stage.COMPLETE, (
            f"state.current_stage should be COMPLETE, got {state.current_stage}"
        )
        assert state.current_phase >= 1, (
            f"state.current_phase should be >= 1 after agent execution, "
            f"got {state.current_phase}"
        )
