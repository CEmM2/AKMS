"""Phase D2 E2E: run_pipeline in graph-only mode.

AutoApproveCheckpointHandler + dry-run pipeline E2E.
Acceptance criteria covered:
- AutoApproveCheckpointHandler records all checkpoint stage names
- AbortThenApproveHandler aborts first call, approves subsequent
- run_pipeline in graph-only mode reaches COMPLETE state
- run_pipeline abort+resume cycle completes successfully
"""

from __future__ import annotations

import asyncio

import pytest

from akms.orchestrator.orchestrator import run_pipeline
from akms.orchestrator.stages import PipelineState, Stage

from tests.fakes.checkpoint_handlers import AutoApproveCheckpointHandler


class TestRunPipelineDry:
    @pytest.mark.e2e
    def test_graph_only_reaches_complete(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / "knowledge" / "graph").mkdir(parents=True)
        (repo / "knowledge" / "nodes").mkdir(parents=True)
        (repo / "knowledge" / "checkpoints").mkdir(parents=True)

        handler = AutoApproveCheckpointHandler()

        asyncio.run(run_pipeline(
            repo_root=repo,
            goal="dry run",
            plan_name="test",
            agent_cls=None,
            checkpoint_handler=handler,
        ))

        state = PipelineState.load(repo)
        assert state.completed is True
        assert state.current_stage == Stage.COMPLETE
        assert "PLAN" in handler.checkpoints_seen

    @pytest.mark.e2e
    def test_abort_and_resume(self, tmp_path):
        repo = tmp_path / "repo"
        (repo / "knowledge" / "graph").mkdir(parents=True)
        (repo / "knowledge" / "nodes").mkdir(parents=True)

        from tests.fakes.checkpoint_handlers import AbortThenApproveHandler

        handler = AbortThenApproveHandler()
        asyncio.run(run_pipeline(
            repo_root=repo, goal="test", plan_name="test",
            agent_cls=None, checkpoint_handler=handler,
        ))

        state = PipelineState.load(repo)
        assert state.aborted is True

        handler2 = AutoApproveCheckpointHandler()
        asyncio.run(run_pipeline(
            repo_root=repo, resume=True,
            agent_cls=None, checkpoint_handler=handler2,
        ))

        state = PipelineState.load(repo)
        assert state.completed is True
