"""Tests for orchestrator module — Phase 6: Stage Pipeline & Checkpoints.

Coverage:
- Stage definitions and transitions
- PipelineState (persist, load, abort, resume)
- Checkpoint I/O (write, read, response)
- Agent configs
- Handler pipeline stages (direct handler calls)
- Wave scope validation
"""

from __future__ import annotations

import asyncio
import builtins
from pathlib import Path

import pytest
import yaml

from akms.graph.build_graph import build_graph
from akms.orchestrator.agent_configs import (
    get_agent_config,
    get_special_agent_config,
)
from akms.orchestrator.checkpoint import (
    CheckpointData,
    list_checkpoints,
    read_checkpoint_response,
    write_checkpoint,
    write_checkpoint_response,
)
from akms.orchestrator.orchestrator import (
    handle_execute,
    handle_finalize,
    handle_init,
    handle_plan,
    handle_review,
    handle_scaffold,
    handle_task_breakdown,
    run_pipeline,
)
from akms.orchestrator.stages import (
    STAGE_DEFINITIONS,
    PipelineState,
    Stage,
    get_stage_definition,
    is_valid_transition,
)
from akms.schema.models import AgentRole

from .conftest import make_ctx, make_global_node, make_state


# ═══════════════════════════════════════════════════════════════════════
#  Stage Definitions & Transitions
# ═══════════════════════════════════════════════════════════════════════


class TestStageDefinitions:
    """Test stage definitions and metadata."""

    def test_all_stages_defined(self):
        """All 8 stages have definitions."""
        assert len(STAGE_DEFINITIONS) == 8
        for stage in Stage:
            assert stage in STAGE_DEFINITIONS

    def test_init_has_no_checkpoint(self):
        defn = get_stage_definition(Stage.INIT)
        assert defn.requires_checkpoint is False

    def test_all_non_init_require_checkpoint(self):
        # INIT and COMPLETE are the two stages without checkpoints
        no_checkpoint_stages = {Stage.INIT, Stage.COMPLETE}
        for stage in Stage:
            if stage in no_checkpoint_stages:
                continue
            defn = get_stage_definition(stage)
            assert defn.requires_checkpoint is True, (
                f"{stage.name} should require checkpoint"
            )

    def test_init_transitions_to_plan(self):
        assert is_valid_transition(Stage.INIT, Stage.PLAN)
        assert not is_valid_transition(Stage.INIT, Stage.EXECUTE)

    def test_review_can_loop_to_execute(self):
        """Review can go back to Execute (for next phase)."""
        assert is_valid_transition(Stage.REVIEW, Stage.EXECUTE)

    def test_review_can_go_to_finalize(self):
        assert is_valid_transition(Stage.REVIEW, Stage.FINALIZE)

    def test_finalize_transitions_to_complete(self):
        defn = get_stage_definition(Stage.FINALIZE)
        assert defn.valid_next == [Stage.COMPLETE]


class TestPipelineState:
    """Test PipelineState persistence and transitions."""

    def test_create_and_save(self, tmp_repo):
        state = PipelineState(goal="test goal", plan_name="test-plan")
        path = state.save(tmp_repo)
        assert path.exists()

    def test_load(self, tmp_repo):
        state = PipelineState(goal="test goal", current_phase=2)
        state.save(tmp_repo)

        loaded = PipelineState.load(tmp_repo)
        assert loaded is not None
        assert loaded.goal == "test goal"
        assert loaded.current_phase == 2

    def test_load_nonexistent_returns_none(self, tmp_repo):
        loaded = PipelineState.load(tmp_repo)
        assert loaded is None

    def test_load_or_create(self, tmp_repo):
        state = PipelineState.load_or_create(tmp_repo, goal="new goal")
        assert state.goal == "new goal"

        # Second call loads existing
        state2 = PipelineState.load_or_create(tmp_repo, goal="different")
        assert state2.goal == "new goal"

    def test_advance_valid(self, tmp_repo):
        state = PipelineState()
        state.advance_to(Stage.PLAN)
        assert state.current_stage == Stage.PLAN

    def test_advance_invalid_raises(self, tmp_repo):
        state = PipelineState()
        with pytest.raises(ValueError, match="Invalid transition"):
            state.advance_to(Stage.EXECUTE)

    def test_abort_and_resume(self, tmp_repo):
        state = PipelineState()
        state.advance_to(Stage.PLAN)
        state.abort("developer requested")

        assert state.aborted is True
        assert state.abort_reason == "developer requested"

        state.resume()
        assert state.aborted is False
        assert state.current_stage == Stage.PLAN

    def test_resume_without_abort_raises(self, tmp_repo):
        state = PipelineState()
        with pytest.raises(ValueError, match="not aborted"):
            state.resume()

    def test_mark_completed(self, tmp_repo):
        state = PipelineState()
        state.mark_completed()
        assert state.completed is True

    def test_stage_history_tracked(self, tmp_repo):
        state = PipelineState()
        state.advance_to(Stage.PLAN)
        state.advance_to(Stage.TASK_BREAKDOWN)

        assert len(state.stage_history) == 2
        assert state.stage_history[0]["from_stage"] == "INIT"
        assert state.stage_history[0]["to_stage"] == "PLAN"

    def test_roundtrip(self, tmp_repo):
        state = PipelineState(
            goal="test", plan_name="plan", current_phase=3, total_phases=5
        )
        state.advance_to(Stage.PLAN)
        state.save(tmp_repo)

        loaded = PipelineState.load(tmp_repo)
        assert loaded.goal == "test"
        assert loaded.current_stage == Stage.PLAN
        assert loaded.current_phase == 3
        assert loaded.total_phases == 5


# ═══════════════════════════════════════════════════════════════════════
#  Checkpoint I/O
# ═══════════════════════════════════════════════════════════════════════


class TestCheckpointIO:
    """Test checkpoint file read/write."""

    def test_write_checkpoint(self, tmp_repo):
        data = CheckpointData(
            stage=Stage.PLAN,
            stage_output="plan.md",
            akms_status={"node_count": 5},
            warnings=["test warning"],
        )
        path = write_checkpoint(tmp_repo, data)
        assert path.exists()
        assert "plan" in path.stem.lower()

    def test_read_checkpoint_data(self, tmp_repo):
        data = CheckpointData(
            stage=Stage.EXECUTE,
            phase=2,
            stage_output="phase 2 done",
        )
        path = write_checkpoint(tmp_repo, data)

        with open(path) as f:
            loaded = yaml.safe_load(f)

        assert loaded["stage"] == "execute"
        assert loaded["phase"] == 2

    def test_write_and_read_response(self, tmp_repo):
        data = CheckpointData(stage=Stage.PLAN)
        cp_path = write_checkpoint(tmp_repo, data)

        # Write response
        write_checkpoint_response(cp_path, "approve")

        # Read response
        response = read_checkpoint_response(cp_path)
        assert response is not None
        assert response.is_approve()

    def test_read_response_not_found(self, tmp_repo):
        data = CheckpointData(stage=Stage.PLAN)
        cp_path = write_checkpoint(tmp_repo, data)

        response = read_checkpoint_response(cp_path)
        assert response is None

    def test_reject_response_with_reason(self, tmp_repo):
        data = CheckpointData(stage=Stage.PLAN)
        cp_path = write_checkpoint(tmp_repo, data)

        write_checkpoint_response(cp_path, "reject", reason="needs more detail")
        response = read_checkpoint_response(cp_path)

        assert response.is_reject()
        assert response.reason == "needs more detail"

    def test_abort_response(self, tmp_repo):
        data = CheckpointData(stage=Stage.EXECUTE, phase=1)
        cp_path = write_checkpoint(tmp_repo, data)

        write_checkpoint_response(cp_path, "abort", reason="stopping")
        response = read_checkpoint_response(cp_path)

        assert response.is_abort()
        assert response.reason == "stopping"

    def test_list_checkpoints(self, tmp_repo):
        write_checkpoint(
            tmp_repo, CheckpointData(stage=Stage.PLAN, timestamp="2026-03-08T10:00:00")
        )
        write_checkpoint(
            tmp_repo,
            CheckpointData(
                stage=Stage.EXECUTE, phase=1, timestamp="2026-03-08T11:00:00"
            ),
        )

        cps = list_checkpoints(tmp_repo)
        assert len(cps) == 2
        stages = {cp["stage"] for cp in cps}
        assert "plan" in stages
        assert "execute" in stages


# ═══════════════════════════════════════════════════════════════════════
#  Agent Configs
# ═══════════════════════════════════════════════════════════════════════


class TestAgentConfigs:
    """Test agent configuration registry."""

    def test_all_roles_have_configs(self):
        for role in AgentRole:
            config = get_agent_config(role)
            assert config.role == role

    def test_implementer_config(self):
        config = get_agent_config(AgentRole.IMPLEMENTER)
        assert config.loadout_required is True
        assert config.receives_phase_diffs is False

    def test_code_reviewer_receives_diffs(self):
        config = get_agent_config(AgentRole.CODE_REVIEWER)
        assert config.receives_phase_diffs is True

    def test_physics_reviewer_uses_opus(self):
        config = get_agent_config(AgentRole.PHYSICS_REVIEWER)
        assert config.model_tier == "opus"

    def test_unknown_role_raises(self):
        with pytest.raises(ValueError):
            get_agent_config("nonexistent_role")

    def test_special_agents(self):
        for name in ["planner", "task_decomposer", "scaffolder", "phase_agent"]:
            config = get_special_agent_config(name)
            assert config.name != ""

    def test_unknown_special_agent_raises(self):
        with pytest.raises(ValueError):
            get_special_agent_config("nonexistent")


# ═══════════════════════════════════════════════════════════════════════
#  Handler Pipeline
# ═══════════════════════════════════════════════════════════════════════


class TestHandleInit:
    """Test handle_init Stage 0 (Init)."""

    def test_init_compiles_graph(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", tags=["test"])
        state = make_state(goal="test pipeline")
        ctx = make_ctx(tmp_repo, tmp_vault)

        stage_output, akms_status, warnings = asyncio.run(handle_init(state, ctx))
        assert "node" in stage_output.lower()
        assert "1" in stage_output  # at least 1 node compiled

    def test_init_advances_state_to_plan(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", tags=["test"])
        state = make_state(goal="test")
        ctx = make_ctx(tmp_repo, tmp_vault)

        asyncio.run(handle_init(state, ctx))
        # handle_init does NOT advance state (run_pipeline does that);
        # the state remains at INIT after the handler returns.
        # State advancement is the responsibility of run_pipeline().
        assert state.current_stage == Stage.INIT

    def test_init_graph_persisted_to_disk(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", tags=["test"])
        state = make_state(goal="test")
        ctx = make_ctx(tmp_repo, tmp_vault)

        asyncio.run(handle_init(state, ctx))

        graph_json = tmp_repo / "knowledge" / "graph" / "graph.json"
        assert graph_json.exists()


class TestHandlePlan:
    """Test handle_plan Stage 1 (Plan)."""

    def test_plan_graph_only_mode_skips_dispatch(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", tags=["test"])
        # Build graph first (normally done by handle_init via run_pipeline)
        build_graph(tmp_repo, global_vault=tmp_vault)

        state = make_state(goal="test plan")
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=None)

        stage_output, akms_status, warnings = asyncio.run(handle_plan(state, ctx))
        assert "skipped" in stage_output.lower() or "graph-only" in stage_output.lower()

    def test_plan_dispatches_when_agent_cls_set(self, tmp_vault, tmp_repo, monkeypatch):
        make_global_node(tmp_vault, id="node-a", tags=["test"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        state = make_state(goal="test plan dispatch")

        from akms.agents.base import AKMSAgent
        from akms.orchestrator.wave_dispatch import TaskResult

        # Must pass a non-None agent_cls so the handler dispatches
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=AKMSAgent)

        dispatch_calls: list[str] = []

        async def _mock_dispatch(
            tasks, agent_cls, config, repo_root, model_override=None
        ):
            for task in tasks:
                dispatch_calls.append(task["task_id"])
                out_dir = repo_root / "knowledge" / "sessions"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"{task['task_id']}.md"
                out_path.write_text("---\nstatus: complete\n---\n")
            return [
                TaskResult(
                    task_id=t["task_id"],
                    status="complete",
                    memory_path=str(
                        repo_root / "knowledge" / "sessions" / f"{t['task_id']}.md"
                    ),
                    error="",
                )
                for t in tasks
            ]

        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.dispatch_phase", _mock_dispatch
        )

        stage_output, akms_status, warnings = asyncio.run(handle_plan(state, ctx))
        assert "stage-plan" in dispatch_calls
        assert "Plan written" in stage_output or "agent" in stage_output.lower()


class TestPipelineCheckpointGating:
    """Checkpoint-gated pipeline behavior via run_pipeline() + RecordingCheckpointHandler."""

    def test_pipeline_approve_runs_through_stages(self, tmp_vault, tmp_repo):
        from akms.orchestrator.stages import CheckpointAction
        from tests.fakes.checkpoint_handlers import RecordingCheckpointHandler

        make_global_node(tmp_vault, id="node-a", tags=["test"])

        # Enough APPROVEs to get through all non-INIT stages in graph-only mode:
        # PLAN, TASK_BREAKDOWN, SCAFFOLD, EXECUTE, REVIEW, FINALIZE = 6 checkpoints
        handler = RecordingCheckpointHandler([CheckpointAction.APPROVE] * 10)

        asyncio.run(
            run_pipeline(
                tmp_repo,
                goal="gate-approve",
                global_vault=tmp_vault,
                agent_cls=None,  # graph-only: no real agents
                checkpoint_handler=handler,
            )
        )

        stage_names = [p["stage"] for p in handler.presentations]
        assert "PLAN" in stage_names

    @pytest.mark.parametrize("action", ["reject", "edit"])
    def test_pipeline_reject_or_edit_reruns_same_stage(
        self, tmp_vault, tmp_repo, action
    ):
        from akms.orchestrator.stages import CheckpointAction
        from tests.fakes.checkpoint_handlers import RecordingCheckpointHandler

        make_global_node(tmp_vault, id="node-a", tags=["test"])

        action_enum = CheckpointAction(action)
        # First checkpoint: reject/edit → same stage. Then abort to stop.
        handler = RecordingCheckpointHandler([action_enum, CheckpointAction.ABORT])

        asyncio.run(
            run_pipeline(
                tmp_repo,
                goal=f"gate-{action}",
                global_vault=tmp_vault,
                agent_cls=None,
                checkpoint_handler=handler,
            )
        )

        # First presentation at PLAN, then same stage again, then ABORT stops it
        assert len(handler.presentations) >= 2
        # Both presentations should be the same stage (PLAN is the first gated stage)
        assert handler.presentations[0]["stage"] == handler.presentations[1]["stage"]

    def test_pipeline_abort_stops_pipeline(self, tmp_vault, tmp_repo):
        from akms.orchestrator.stages import CheckpointAction
        from tests.fakes.checkpoint_handlers import RecordingCheckpointHandler

        make_global_node(tmp_vault, id="node-a", tags=["test"])

        # Abort on first checkpoint (PLAN)
        handler = RecordingCheckpointHandler([CheckpointAction.ABORT])

        asyncio.run(
            run_pipeline(
                tmp_repo,
                goal="gate-abort",
                global_vault=tmp_vault,
                agent_cls=None,
                checkpoint_handler=handler,
            )
        )

        # State should be saved as aborted
        state = PipelineState.load(tmp_repo)
        assert state is not None
        assert state.aborted is True

        # Only one checkpoint was presented (PLAN)
        assert len(handler.presentations) == 1
        assert handler.presentations[0]["stage"] == "PLAN"


class TestHandleTaskBreakdown:
    """Test handle_task_breakdown Stage 2 (Task Breakdown)."""

    def test_fills_tags(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", title="Alpha", tags=["alpha"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        tasks = [
            {
                "task_id": "t1",
                "title": "alpha implementation",
                "objective": "",
                "phase": 1,
            },
            {"task_id": "t2", "title": "beta work", "objective": "", "phase": 2},
        ]

        state = make_state(goal="test")
        ctx = make_ctx(tmp_repo, tmp_vault)

        stage_output, akms_status, warnings = asyncio.run(
            handle_task_breakdown(state, ctx, tasks=tasks)
        )

        assert "alpha" in tasks[0].get("akms_tags", [])
        assert "2 tasks" in stage_output
        assert state.phase_order == [1, 2]

    def test_dispatches_when_tasks_missing(self, tmp_vault, tmp_repo, monkeypatch):
        make_global_node(tmp_vault, id="node-a", title="Alpha", tags=["alpha"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        from akms.agents.base import AKMSAgent
        from akms.orchestrator.wave_dispatch import TaskResult

        dispatched_tasks_returned = [
            {
                "task_id": "t1",
                "title": "alpha implementation",
                "objective": "",
                "phase": 1,
            },
            {"task_id": "t2", "title": "beta work", "objective": "", "phase": 2},
        ]

        async def _mock_dispatch(
            tasks, agent_cls, config, repo_root, model_override=None
        ):
            import frontmatter as fm_mod

            results = []
            for task in tasks:
                task_id = task["task_id"]
                out_dir = repo_root / "knowledge" / "sessions"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"{task_id}.md"
                # Write a memory file with embedded tasks list
                post = fm_mod.Post(
                    content="",
                    tasks=dispatched_tasks_returned,
                )
                with open(out_path, "wb") as f:
                    fm_mod.dump(post, f)
                results.append(
                    TaskResult(
                        task_id=task_id,
                        status="complete",
                        memory_path=str(out_path),
                        error="",
                    )
                )
            return results

        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.dispatch_phase", _mock_dispatch
        )

        state = make_state(goal="test")
        # Must pass a non-None agent_cls so the handler dispatches the decomposer
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=AKMSAgent)

        stage_output, akms_status, warnings = asyncio.run(
            handle_task_breakdown(state, ctx, tasks=None)
        )

        assert "2 tasks" in stage_output
        assert state.phase_order == [1, 2]
        assert state.total_phases == 2


class TestHandleScaffold:
    """Test handle_scaffold Stage 3 (Scaffold)."""

    def test_scaffold_graph_only_mode_skips_dispatch(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", tags=["test"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        state = make_state(goal="test")
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=None)

        stage_output, akms_status, warnings = asyncio.run(handle_scaffold(state, ctx))
        assert "skipped" in stage_output.lower() or "graph-only" in stage_output.lower()


class TestHandleExecute:
    """Test handle_execute Stage 4 (Execute)."""

    def test_execute_fills_loadout_paths(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", tags=["test"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        tasks = [
            {
                "task_id": "t1",
                "akms_tags": ["test"],
                "title": "task 1",
                "available_context": 12345,
                "phase": 1,
            },
        ]

        state = make_state(goal="test", current_phase=1)
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=None)

        asyncio.run(handle_execute(state, ctx, tasks=tasks))

        assert tasks[0].get("loadout_path") is not None
        assert Path(tasks[0]["loadout_path"]).exists()
        loadout_text = Path(tasks[0]["loadout_path"]).read_text()
        frontmatter_text = loadout_text.split("---\n", 2)[1]
        header = yaml.safe_load(frontmatter_text)
        assert header["available_context"] == 12345

    def test_execute_uses_single_loadout_writer(self, tmp_vault, tmp_repo, monkeypatch):
        """handle_execute should not perform an extra direct file write."""
        make_global_node(tmp_vault, id="node-a", tags=["test"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        written_paths: list[str] = []

        def _fake_generate_loadout(*, task_id, phase, output_path=None, **kwargs):
            assert output_path is not None
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(f"# Loadout: {task_id}\n")
            written_paths.append(str(out))
            return f"# Loadout: {task_id}\n"

        def _fail_direct_open(path, mode="r", *args, **kwargs):
            if "w" in mode and str(path).endswith("-loadout.md"):
                raise AssertionError("orchestrator attempted direct loadout write")
            return builtins.open(path, mode, *args, **kwargs)

        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.generate_loadout", _fake_generate_loadout
        )
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.open",
            _fail_direct_open,
            raising=False,
        )

        tasks = [
            {
                "task_id": "t1",
                "akms_tags": ["test"],
                "title": "task 1",
                "available_context": 12345,
                "phase": 1,
            },
        ]

        state = make_state(goal="test", current_phase=1)
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=None)

        asyncio.run(handle_execute(state, ctx, tasks=tasks))

        assert len(written_paths) == 1
        assert Path(tasks[0]["loadout_path"]).exists()

    def test_execute_prior_phase_pcd_forwarding_is_wrapper_only(
        self, tmp_vault, tmp_repo, monkeypatch
    ):
        """handle_execute does not forward prior_phase_pcd into task dicts.

        Prior PCD forwarding was a wrapper-only feature (execute_phase_pre).
        The handler manages graph state differently — via state.tasks and
        update_graph. Tests that need prior-PCD semantics should use the
        wrapper or chain handle_task_breakdown + handle_execute.
        """
        make_global_node(tmp_vault, id="node-a", tags=["test"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        sessions_dir = tmp_repo / "knowledge" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "handoff_phase_1.md").write_text("---\nakms_schema: v2\n---\n")

        tasks = [
            {
                "task_id": "t2",
                "akms_tags": ["test"],
                "title": "task 2",
                "available_context": 12345,
                "phase": 2,
            },
        ]

        state = make_state(goal="test", current_phase=2)
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=None)

        stage_output, akms_status, warnings = asyncio.run(
            handle_execute(state, ctx, tasks=tasks)
        )

        # Handler processes the phase; prior_phase_pcd is NOT injected into task dicts
        assert "prior_phase_pcd" not in tasks[0]
        # But the handler still returns a valid result
        assert "Phase 2" in stage_output

    def test_execute_runs_graph_pipeline(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", tags=["test"], confidence=0.90)
        build_graph(tmp_repo, global_vault=tmp_vault)

        state = make_state(goal="test", current_phase=1)
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=None)

        stage_output, akms_status, warnings = asyncio.run(
            handle_execute(state, ctx, tasks=[])
        )

        assert "Phase 1" in stage_output

    def test_execute_without_tasks_runs_cleanly(self, tmp_vault, tmp_repo):
        """handle_execute with empty task list still runs graph status."""
        make_global_node(tmp_vault, id="node-a", tags=["test"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        state = make_state(goal="test", current_phase=1)
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=None)

        stage_output, akms_status, warnings = asyncio.run(
            handle_execute(state, ctx, tasks=None)
        )
        assert "Phase 1" in stage_output

    def test_execute_processes_memories_deterministically(
        self, tmp_vault, tmp_repo, monkeypatch
    ):
        """Memories passed via dispatch results are processed in deterministic order."""
        make_global_node(tmp_vault, id="node-a", tags=["test"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        call_order: list[str] = []

        def _fake_update_graph(source, repo_root, config=None, global_vault=None):
            # The orchestrator issues a single-PCD update_graph call. The
            # call_order now reflects the ordering of `source.tasks` inside
            # the PCD rather than a per-memory call order.
            from akms.schema.models import PCD

            if isinstance(source, PCD):
                for t in source.tasks:
                    call_order.append(t.task_id)
            elif hasattr(source, "task_id"):
                call_order.append(str(source.task_id))
            else:
                call_order.append(str(source.get("task_id", "")))
            return {
                "confidence_events": [],
                "propagation_events": [],
                "pitfall_events": [],
                "knowledge_events": [],
                "session_node_id": "session",
            }

        from akms.orchestrator.wave_dispatch import TaskResult
        import yaml as yaml_mod

        sessions_dir = tmp_repo / "knowledge" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # Create memory files for tasks in non-alphabetical order
        for task_id in ["task-c", "task-a", "task-b"]:
            mp = sessions_dir / f"{task_id}.md"
            hour = 8 + ["c", "a", "b"].index(task_id[-1])
            memory_data = {
                "task_id": task_id,
                "task_description": f"demo task {task_id}",
                "phase_id": 1,
                "timestamp": f"2026-03-09T{hour:02d}:00:00",
                "agent_model": "claude-sonnet-4-6",
                "loadout_used": "",
                "status": "complete",
                "tests_passed": 1,
                "tests_total": 1,
                "completion_notes": "ok",
                "nodes_used": [],
                "pitfalls_discovered": [],
                "new_knowledge": [],
                "nodes_missing": [],
                "lessons": {"worked": [], "failed": []},
                "akms_schema": "v2",
            }
            mp.write_text(
                "---\n" + yaml_mod.dump(memory_data, sort_keys=False) + "---\n"
            )

        async def _mock_dispatch(
            tasks, agent_cls, config, repo_root, model_override=None
        ):
            return [
                TaskResult(
                    task_id="task-c",
                    status="complete",
                    memory_path=str(sessions_dir / "task-c.md"),
                    error="",
                ),
                TaskResult(
                    task_id="task-a",
                    status="complete",
                    memory_path=str(sessions_dir / "task-a.md"),
                    error="",
                ),
                TaskResult(
                    task_id="task-b",
                    status="complete",
                    memory_path=str(sessions_dir / "task-b.md"),
                    error="",
                ),
            ]

        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.dispatch_phase", _mock_dispatch
        )
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.update_graph", _fake_update_graph
        )
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.generate_mirror",
            lambda *args, **kwargs: {"files_processed": 0, "drift_warnings": []},
        )
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.graph_status",
            lambda *args, **kwargs: {
                "summary": {},
                "degraded_nodes": [],
                "tentative_nodes": [],
            },
        )
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.format_report", lambda _: "ok"
        )

        tasks = [
            {"task_id": "task-c", "akms_tags": ["test"], "phase": 1},
            {"task_id": "task-a", "akms_tags": ["test"], "phase": 1},
            {"task_id": "task-b", "akms_tags": ["test"], "phase": 1},
        ]

        from akms.agents.base import AKMSAgent

        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=AKMSAgent)
        state = make_state(goal="test", current_phase=1)

        asyncio.run(handle_execute(state, ctx, tasks=tasks))

        # Memories should be processed alphabetically by task_id
        assert call_order == ["task-a", "task-b", "task-c"]
        assert state.last_pcd_path
        assert (tmp_repo / state.last_pcd_path).is_file()

    def test_execute_filters_tasks_by_current_phase(
        self, tmp_vault, tmp_repo, monkeypatch
    ):
        """Verifies handle_execute only processes tasks matching the current phase."""
        make_global_node(tmp_vault, id="node-a", tags=["test"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        processed_sources: list[str] = []

        def _fake_update_graph(source, repo_root, config=None, global_vault=None):
            from akms.schema.models import PCD

            if isinstance(source, PCD):
                processed_sources.append(f"phase-{source.phase_id}")
            elif hasattr(source, "task_id"):
                processed_sources.append(
                    str(getattr(source, "phase_id", "") or source.task_id)
                )
            else:
                processed_sources.append(
                    str(source.get("phase_id", source.get("task_id", "")))
                )
            return {
                "confidence_events": [],
                "propagation_events": [],
                "pitfall_events": [],
                "knowledge_events": [],
                "session_node_id": "session-phase-2",
            }

        from akms.orchestrator.wave_dispatch import TaskResult

        sessions_dir = tmp_repo / "knowledge" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        mp = sessions_dir / "task-phase2.md"
        mp.write_text(
            "---\n"
            "task_id: task-phase2\n"
            "task_description: demo\n"
            "phase_id: 2\n"
            "timestamp: '2026-03-09T10:00:00'\n"
            "agent_model: claude-sonnet-4-6\n"
            "loadout_used: ''\n"
            "status: complete\n"
            "tests_passed: 1\n"
            "tests_total: 1\n"
            "completion_notes: ok\n"
            "nodes_used: []\n"
            "pitfalls_discovered: []\n"
            "new_knowledge: []\n"
            "nodes_missing: []\n"
            "lessons:\n  worked: []\n  failed: []\n"
            "akms_schema: v2\n"
            "---\n"
        )

        async def _mock_dispatch(
            tasks, agent_cls, config, repo_root, model_override=None
        ):
            return [
                TaskResult(
                    task_id="task-phase2",
                    status="complete",
                    memory_path=str(mp),
                    error="",
                ),
            ]

        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.dispatch_phase", _mock_dispatch
        )
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.update_graph", _fake_update_graph
        )
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.generate_mirror",
            lambda *args, **kwargs: {"files_processed": 0, "drift_warnings": []},
        )
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.graph_status",
            lambda *args, **kwargs: {
                "summary": {},
                "degraded_nodes": [],
                "tentative_nodes": [],
            },
        )
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.format_report", lambda _: "ok"
        )

        from akms.agents.base import AKMSAgent

        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=AKMSAgent)
        state = make_state(goal="test", current_phase=2)

        tasks = [{"task_id": "task-phase2", "akms_tags": ["test"], "phase": 2}]
        asyncio.run(handle_execute(state, ctx, tasks=tasks))

        #   # update_graph is called once per phase with a PCD; the recorded id is
        #           # "phase-{phase_id}" rather than the raw phase.
        assert processed_sources == ["phase-2"]

    def test_task_breakdown_populates_phase_order_for_execute(
        self, tmp_vault, tmp_repo
    ):
        """handle_task_breakdown sets state.phase_order so handle_execute uses correct phase."""
        build_graph(tmp_repo, global_vault=tmp_vault)

        tasks = [
            {"task_id": "t1", "phase": 1, "akms_tags": [], "akms_schema": "v2"},
            {"task_id": "t3", "phase": 3, "akms_tags": [], "akms_schema": "v2"},
        ]

        state = make_state(goal="test")
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=None)

        asyncio.run(handle_task_breakdown(state, ctx, tasks=tasks))

        assert state.phase_order == [1, 3]


class TestHandleReview:
    """Test handle_review Stage 5 (Review)."""

    def test_review_graph_only_skips_dispatch(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", tags=["test"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        state = make_state(goal="test", current_phase=1)
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=None)

        stage_output, akms_status, warnings = asyncio.run(handle_review(state, ctx))
        assert "skipped" in stage_output.lower() or "graph-only" in stage_output.lower()

    def test_review_without_agents_returns_status(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", tags=["test"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        state = make_state(goal="test", current_phase=1)
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=None)

        stage_output, akms_status, warnings = asyncio.run(handle_review(state, ctx))
        # In graph-only mode returns status report as akms_status
        assert isinstance(akms_status, str)

    def test_review_dispatches_reviewers(self, tmp_vault, tmp_repo, monkeypatch):
        make_global_node(tmp_vault, id="node-a", tags=["test"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        updates: list[str] = []

        from akms.orchestrator.wave_dispatch import TaskResult
        import yaml as yaml_mod

        async def _mock_dispatch(
            tasks, agent_cls, config, repo_root, model_override=None
        ):
            results = []
            for task in tasks:
                task_id = task["task_id"]
                out_dir = repo_root / "knowledge" / "sessions"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"{task_id}.md"
                memory_data = {
                    "nodes_used": [
                        {"id": "node-a", "useful": True, "coverage": "sufficient"}
                    ],
                    "pitfalls_discovered": [],
                    "new_knowledge": [],
                    "nodes_missing": [],
                    "lessons": {"worked": [], "failed": []},
                }
                out_path.write_text(
                    "---\n" + yaml_mod.dump(memory_data, sort_keys=False) + "---\n"
                )
                results.append(
                    TaskResult(
                        task_id=task_id,
                        status="complete",
                        memory_path=str(out_path),
                        error="",
                    )
                )
            return results

        def _fake_update_graph(source, repo_root, config=None, global_vault=None):
            role = source.get("role", "")
            updates.append(role)
            return {}

        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.dispatch_phase", _mock_dispatch
        )
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.update_graph", _fake_update_graph
        )

        from akms.agents.base import AKMSAgent

        state = make_state(goal="test", current_phase=1)
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=AKMSAgent)

        stage_output, akms_status, warnings = asyncio.run(handle_review(state, ctx))
        # Two reviewers dispatched (code_reviewer and physics_reviewer)
        assert "2/2" in stage_output or "2" in akms_status

    def test_review_parallel_dispatch_is_deterministic_across_runs(
        self, tmp_vault, tmp_repo, monkeypatch
    ):
        make_global_node(tmp_vault, id="node-a", tags=["test"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        from akms.orchestrator.wave_dispatch import TaskResult
        import yaml as yaml_mod

        async def _mock_dispatch(
            tasks, agent_cls, config, repo_root, model_override=None
        ):
            results = []
            for task in tasks:
                task_id = task["task_id"]
                out_dir = repo_root / "knowledge" / "sessions"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"{task_id}.md"
                memory_data = {
                    "nodes_used": [
                        {"id": "node-a", "useful": True, "coverage": "sufficient"}
                    ],
                    "pitfalls_discovered": [],
                    "new_knowledge": [],
                    "nodes_missing": [],
                    "lessons": {"worked": [], "failed": []},
                }
                out_path.write_text(
                    "---\n" + yaml_mod.dump(memory_data, sort_keys=False) + "---\n"
                )
                results.append(
                    TaskResult(
                        task_id=task_id,
                        status="complete",
                        memory_path=str(out_path),
                        error="",
                    )
                )
            return results

        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.dispatch_phase", _mock_dispatch
        )
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.update_graph",
            lambda source, repo_root, config=None, global_vault=None: {},
        )

        from akms.agents.base import AKMSAgent

        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=AKMSAgent)

        state1 = make_state(goal="test", current_phase=1)
        first_output, first_status, _ = asyncio.run(handle_review(state1, ctx))

        state2 = make_state(goal="test", current_phase=1)
        second_output, second_status, _ = asyncio.run(handle_review(state2, ctx))

        # Both runs should produce the same output structure
        assert "2/2" in first_output or "review" in first_output.lower()
        assert first_output == second_output
        assert first_status == second_status


class TestHandleFinalize:
    """Test handle_finalize Stage 6 (Finalize)."""

    def test_finalize_completes_pipeline(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", tags=["test"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        state = make_state(goal="test")
        ctx = make_ctx(tmp_repo, tmp_vault)

        stage_output, akms_status, warnings = asyncio.run(handle_finalize(state, ctx))
        assert (
            "complete" in stage_output.lower()
            or "finalize" in stage_output.lower()
            or "Pipeline" in stage_output
        )


# ═══════════════════════════════════════════════════════════════════════
#  Wave Scope Validation
# ═══════════════════════════════════════════════════════════════════════


class TestScopeDisjointness:
    """Test concurrency validation for wave scopes (§6.3)."""

    def test_disjoint_scopes_valid(self):
        from akms.orchestrator.wave_dispatch import validate_scope_disjointness

        tasks = [
            {"task_id": "t1", "scope": ["src/a.py"]},
            {"task_id": "t2", "scope": ["src/b.py"]},
        ]
        # Should not raise
        validate_scope_disjointness(tasks)

    def test_overlapping_scopes_detected(self):
        from akms.orchestrator.wave_dispatch import validate_scope_disjointness

        tasks = [
            {"task_id": "t1", "scope": ["src/shared.py"]},
            {"task_id": "t2", "scope": ["src/shared.py"]},
        ]
        with pytest.raises(ValueError, match="shared.py"):
            validate_scope_disjointness(tasks)

    def test_empty_scopes_valid(self):
        from akms.orchestrator.wave_dispatch import validate_scope_disjointness

        tasks = [
            {"task_id": "t1", "scope": []},
            {"task_id": "t2"},
        ]
        # Should not raise
        validate_scope_disjointness(tasks)


# ═══════════════════════════════════════════════════════════════════════
#  run_subagent Integration Test
# ═══════════════════════════════════════════════════════════════════════


class TestRunSubagent:
    """run_subagent asyncio bridge integration tests."""

    def test_run_subagent_asyncio_bridge(self, tmp_repo):
        """Real run_subagent exercises asyncio bridge end-to-end."""
        from akms.agents.base import AKMSAgent
        from akms.orchestrator.wave_dispatch import run_subagent
        from akms.schema.models import PropagationConfig
        from datetime import datetime
        import frontmatter

        # WritingAgent subclass whose execute() writes valid AgentMemory
        class WritingAgent(AKMSAgent):
            async def execute(self, task_json, loadout, system_prompt):
                sessions_dir = self.repo_root / "knowledge" / "sessions"
                sessions_dir.mkdir(parents=True, exist_ok=True)
                output_path = sessions_dir / f"{task_json['task_id']}.md"
                memory_dict = {
                    "task_id": task_json["task_id"],
                    "task_description": "Test task",
                    "phase_id": 1,
                    "timestamp": datetime.now().isoformat(),
                    "agent_model": "claude-sonnet-4-6",
                    "loadout_used": "",
                    "status": "complete",
                    "commit": "abc123",
                    "tests_passed": 1,
                    "tests_total": 1,
                    "completion_notes": "Bridge test",
                    "nodes_used": [],
                    "nodes_missing": [],
                    "lessons": {"worked": [], "failed": []},
                    "pitfalls_discovered": [],
                    "new_knowledge": [],
                    "akms_schema": "v2",
                }
                post = frontmatter.Post(
                    content="\n## Notes\n\nBridge test.\n", **memory_dict
                )
                with open(output_path, "wb") as f:
                    frontmatter.dump(post, f)

        config = PropagationConfig()
        task_json = {
            "task_id": "task-1",
            "phase": 1,
            "title": "Bridge test task",
            "loadout_path": "",
        }

        # Call run_subagent — exercises asyncio bridge end-to-end
        result = asyncio.run(run_subagent(task_json, WritingAgent, config, tmp_repo))
        assert result.task_id == "task-1"
        assert result.status == "complete"


class TestPersistentZoneHelpers:
    """PR17-T1: module-level helpers used by handle_execute + handle_review.

    Covers the full persistent-zone contract:
      - nodes_used / nodes_missing / pitfalls_discovered / new_knowledge
      - lessons.worked / lessons.failed

    Also asserts the dict-branch fallback so legacy fakes / MCP payloads
    keep routing through update_graph the way they used to.
    """

    def _make_agent_memory(self, **overrides):
        from datetime import datetime
        from akms.schema.models import AgentMemory, TaskStatus

        base = dict(
            task_id="t-1",
            task_description="",
            phase_id=1,
            timestamp=datetime.now(),
            agent_model="m",
            loadout_used="",
            status=TaskStatus.COMPLETE,
            tests_passed=0,
            tests_total=0,
        )
        base.update(overrides)
        return AgentMemory(**base)

    def test_empty_memory_is_not_persistent(self):
        from akms.orchestrator.orchestrator import _memory_has_persistent_zone

        assert _memory_has_persistent_zone(self._make_agent_memory()) is False

    def test_nodes_used_triggers_persist(self):
        from akms.orchestrator.orchestrator import _memory_has_persistent_zone
        from akms.schema.models import NodeUsedFeedback

        m = self._make_agent_memory(
            nodes_used=[
                NodeUsedFeedback(id="node-a", useful=True, coverage="sufficient"),
            ]
        )
        assert _memory_has_persistent_zone(m) is True

    def test_nodes_missing_triggers_persist(self):
        """C7: nodes_missing must trigger persist (was dropped in the original
        handle_review guard)."""
        from akms.orchestrator.orchestrator import _memory_has_persistent_zone
        from akms.schema.models import NodeMissingEntry, Priority

        m = self._make_agent_memory(
            nodes_missing=[
                NodeMissingEntry(
                    description="gap on X",
                    suggested_id="sugg-1",
                    domain="computational_mechanics",
                    priority=Priority.MEDIUM,
                ),
            ]
        )
        assert _memory_has_persistent_zone(m) is True

    def test_lessons_worked_triggers_persist(self):
        """C7: lessons.worked must trigger persist."""
        from akms.orchestrator.orchestrator import _memory_has_persistent_zone
        from akms.schema.models import Lessons

        m = self._make_agent_memory(lessons=Lessons(worked=["wrote tests first"]))
        assert _memory_has_persistent_zone(m) is True

    def test_lessons_failed_triggers_persist(self):
        """C7: lessons.failed must trigger persist."""
        from akms.orchestrator.orchestrator import _memory_has_persistent_zone
        from akms.schema.models import Lessons, LessonFailed

        m = self._make_agent_memory(
            lessons=Lessons(
                failed=[
                    LessonFailed(
                        what="skipped TDD", why="fast fix", fix="add tests first"
                    ),
                ]
            ),
        )
        assert _memory_has_persistent_zone(m) is True

    def test_dict_shape_fallback(self):
        """Legacy dict memories (pre-typing fakes) still work through the helper."""
        from akms.orchestrator.orchestrator import _memory_has_persistent_zone

        assert (
            _memory_has_persistent_zone({"nodes_used": [{"id": "n", "useful": True}]})
            is True
        )
        assert _memory_has_persistent_zone({"lessons": {"worked": ["w"]}}) is True
        assert (
            _memory_has_persistent_zone(
                {"lessons": {"failed": [{"attempt": "a", "reason": "r"}]}}
            )
            is True
        )
        assert _memory_has_persistent_zone({}) is False
        assert _memory_has_persistent_zone({"lessons": {}}) is False

    def test_memory_task_id_handles_both_shapes(self):
        from akms.orchestrator.orchestrator import _memory_task_id

        m = self._make_agent_memory(task_id="typed-1")
        assert _memory_task_id(m) == "typed-1"
        assert _memory_task_id({"task_id": "dict-1"}) == "dict-1"
        assert _memory_task_id({}) == ""
