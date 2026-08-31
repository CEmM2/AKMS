"""Stage handlers raise StageFailedError when their agent produces nothing usable."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from akms.orchestrator.orchestrator import (
    PipelineContext,
    StageFailedError,
    handle_plan,
)
from akms.orchestrator.stages import PipelineState, Stage
from akms.schema.models import PropagationConfig


class _FailedResult:
    status = "failed"
    task_id = "stage-plan"
    memory_path = None


def _ctx(tmp_path) -> PipelineContext:
    class AnyAgent:  # never dispatched: dispatch_phase is patched
        def __init__(self, *a, **k): ...

    return PipelineContext(
        repo_root=tmp_path,
        global_vault=None,
        config=PropagationConfig(),
        agent_cls=AnyAgent,
        model=None,
        spec_path="",
    )


@pytest.mark.unit
def test_plan_agent_failure_raises(tmp_path, monkeypatch):
    for sub in ["graph", "local-nodes", "sessions", "loadouts", "code-mirror", "qmd"]:
        (tmp_path / "knowledge" / sub).mkdir(parents=True)
    (tmp_path / "knowledge" / "graph" / "local_state.yaml").write_text(
        "akms_schema: v2\nnodes: {}\n"
    )
    state = PipelineState(goal="g", plan_name="p")
    state.current_stage = Stage.PLAN

    with patch(
        "akms.orchestrator.orchestrator.dispatch_phase",
        new=AsyncMock(return_value=[_FailedResult()]),
    ):
        with pytest.raises(StageFailedError, match="PLAN stage failed"):
            asyncio.run(handle_plan(state, _ctx(tmp_path)))
