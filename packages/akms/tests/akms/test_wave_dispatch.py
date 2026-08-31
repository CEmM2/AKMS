"""wave_dispatch.py tests -- wave building and parallel dispatch.

Covers: model resolution, topological wave building, scope disjointness
validation, blocked task detection, single agent dispatch, and failure isolation
in wave-parallel dispatch.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from akms.orchestrator.wave_dispatch import (
    TaskResult,
    build_waves,
    dispatch_phase,
    find_blocked_tasks,
    resolve_model_for_tier,
    run_subagent,
    validate_scope_disjointness,
)


class TestResolveModelForTier:
    """
    Tests for resolve_model_for_tier().
    Acceptance criterion: explicit override wins, tier map works (opus/sonnet/haiku),
                          unknown tier falls back to config default.
    """

    @pytest.mark.unit
    def test_explicit_override_wins(self):
        """
        Verifies: When model_override is provided, it takes precedence over tier.
        Passes when: resolve_model_for_tier("haiku", model_override="custom") == "custom"
        """
        result = resolve_model_for_tier("haiku", model_override="custom-model-v1")
        assert result == "custom-model-v1"

    @pytest.mark.unit
    def test_opus_tier_mapping(self):
        """
        Verifies: "opus" tier maps to "claude-opus-4-6".
        Passes when: resolve_model_for_tier("opus") == "claude-opus-4-6"
        """
        assert resolve_model_for_tier("opus") == "claude-opus-4-6"

    @pytest.mark.unit
    def test_sonnet_tier_mapping(self):
        """
        Verifies: "sonnet" tier maps to "claude-sonnet-4-6".
        Passes when: resolve_model_for_tier("sonnet") == "claude-sonnet-4-6"
        """
        assert resolve_model_for_tier("sonnet") == "claude-sonnet-4-6"

    @pytest.mark.unit
    def test_haiku_tier_mapping(self):
        """
        Verifies: "haiku" tier maps to "claude-haiku-4-5".
        Passes when: resolve_model_for_tier("haiku") == "claude-haiku-4-5"
        """
        assert resolve_model_for_tier("haiku") == "claude-haiku-4-5"

    @pytest.mark.unit
    def test_unknown_tier_uses_config_default(self):
        """
        Verifies: Unknown tier with config falls back to config.orchestrator.default_model.
        Passes when: resolve_model_for_tier("unknown", config=mock_config) == config default.
        """
        from akms.schema.models import PropagationConfig

        config = PropagationConfig()
        # default_model is "claude-sonnet-4-6" but we confirm it falls through tier_map
        result = resolve_model_for_tier("unknown_tier", config=config)
        assert result == config.orchestrator.default_model


class TestBuildWaves:
    """
    Tests for build_waves() topological sort.
    Acceptance criterion: no-dep tasks in single wave, linear chain produces N waves,
                          diamond pattern correct, circular deps raise ValueError.
    """

    @pytest.mark.unit
    def test_no_deps_single_wave(self):
        """
        Verifies: Tasks with no dependencies all land in a single wave.
        Passes when: build_waves([{id:a}, {id:b}, {id:c}]) returns 1 wave with 3 tasks.
        """
        tasks = [
            {"task_id": "a"},
            {"task_id": "b"},
            {"task_id": "c"},
        ]
        waves = build_waves(tasks)
        assert len(waves) == 1
        assert len(waves[0]) == 3
        ids = {t["task_id"] for t in waves[0]}
        assert ids == {"a", "b", "c"}

    @pytest.mark.unit
    def test_linear_chain_produces_n_waves(self):
        """
        Verifies: a->b->c chain produces 3 sequential waves.
        Passes when: build_waves returns 3 waves, each with 1 task in correct order.
        """
        tasks = [
            {"task_id": "a"},
            {"task_id": "b", "blocked_by": ["a"]},
            {"task_id": "c", "blocked_by": ["b"]},
        ]
        waves = build_waves(tasks)
        assert len(waves) == 3
        assert waves[0][0]["task_id"] == "a"
        assert waves[1][0]["task_id"] == "b"
        assert waves[2][0]["task_id"] == "c"

    @pytest.mark.unit
    def test_diamond_pattern(self):
        """
        Verifies: root -> {left, right} -> join produces 3 waves with correct grouping.
        Passes when: Wave 0=[root], Wave 1={left, right}, Wave 2=[join].
        """
        tasks = [
            {"task_id": "root"},
            {"task_id": "left", "blocked_by": ["root"]},
            {"task_id": "right", "blocked_by": ["root"]},
            {"task_id": "join", "blocked_by": ["left", "right"]},
        ]
        waves = build_waves(tasks)
        assert len(waves) == 3
        assert waves[0][0]["task_id"] == "root"
        wave1_ids = {t["task_id"] for t in waves[1]}
        assert wave1_ids == {"left", "right"}
        assert waves[2][0]["task_id"] == "join"

    @pytest.mark.unit
    def test_circular_deps_raises_value_error(self):
        """
        Verifies: Circular dependencies raise ValueError.
        Passes when: build_waves with a<->b raises ValueError("Cannot resolve").
        """
        tasks = [
            {"task_id": "a", "blocked_by": ["b"]},
            {"task_id": "b", "blocked_by": ["a"]},
        ]
        with pytest.raises(ValueError, match="Cannot resolve"):
            build_waves(tasks)


class TestValidateScopeDisjointness:
    """
    Tests for validate_scope_disjointness().
    Acceptance criterion: clean scopes pass, overlapping scopes raise ValueError.
    """

    @pytest.mark.unit
    def test_clean_scopes_pass(self):
        """
        Verifies: Non-overlapping file scopes pass without error.
        Passes when: validate_scope_disjointness succeeds for disjoint scopes.
        """
        wave = [
            {"task_id": "t1", "scope": ["src/a.py", "src/b.py"]},
            {"task_id": "t2", "scope": ["src/c.py", "src/d.py"]},
        ]
        # Should not raise
        validate_scope_disjointness(wave)

    @pytest.mark.unit
    def test_overlapping_scopes_raise_value_error(self):
        """
        Verifies: Overlapping file scopes raise ValueError("Scope conflict").
        Passes when: Two tasks claiming same file raise ValueError.
        """
        wave = [
            {"task_id": "t1", "scope": ["src/a.py", "src/shared.py"]},
            {"task_id": "t2", "scope": ["src/b.py", "src/shared.py"]},
        ]
        with pytest.raises(ValueError, match="Scope conflict"):
            validate_scope_disjointness(wave)


class TestFindBlockedTasks:
    """
    Tests for find_blocked_tasks().
    Acceptance criterion: correctly identifies downstream blocked tasks.
    """

    @pytest.mark.unit
    def test_finds_downstream_blocked(self):
        """
        Verifies: Tasks depending on failed tasks are identified.
        Passes when: find_blocked_tasks returns IDs of tasks blocked by failed set.
        """
        remaining_waves = [
            [
                {"task_id": "c", "blocked_by": ["a"]},
                {"task_id": "d", "blocked_by": ["b"]},
            ],
            [
                {"task_id": "e", "blocked_by": ["c"]},
            ],
        ]
        failed_ids = {"a"}
        blocked = find_blocked_tasks(remaining_waves, failed_ids)
        assert "c" in blocked
        # "e" depends on "c", not directly on "a", so it is not in blocked
        # unless we consider transitive — but the function checks direct deps only
        assert "d" not in blocked

    @pytest.mark.unit
    def test_no_blocked_when_unrelated_failure(self):
        """
        Verifies: Tasks not depending on failed tasks are not reported.
        Passes when: find_blocked_tasks returns empty list for unrelated failures.
        """
        remaining_waves = [
            [
                {"task_id": "c", "blocked_by": ["b"]},
                {"task_id": "d", "blocked_by": ["b"]},
            ],
        ]
        failed_ids = {"x"}  # x is not depended on by c or d
        blocked = find_blocked_tasks(remaining_waves, failed_ids)
        assert blocked == []


class TestRunSubagent:
    """
    Tests for run_subagent() single agent dispatch.
    Acceptance criterion: successful dispatch returns TaskResult(status='complete'),
                          failed dispatch returns TaskResult(status='failed').
    """

    @pytest.mark.unit
    def test_successful_dispatch(self, tmp_path):
        """
        Verifies: Successful agent run returns TaskResult with status='complete'.
        Passes when: result.status == 'complete' and result.task_id matches input.
        """
        from akms.schema.models import AgentMemory, PropagationConfig

        config = PropagationConfig()

        # Create a mock agent class whose run() returns a valid AgentMemory
        mock_memory = MagicMock(spec=AgentMemory)
        mock_memory.task_id = "task-1"

        mock_agent_instance = MagicMock()
        mock_agent_instance.run = AsyncMock(return_value=mock_memory)

        mock_agent_cls = MagicMock(return_value=mock_agent_instance)

        task_json = {"task_id": "task-1", "agent_role": "implementer"}

        with patch(
            "akms.orchestrator.wave_dispatch.trace_agent_call"
        ) as mock_trace:
            mock_span = MagicMock()
            mock_trace.return_value = mock_span

            result = asyncio.run(
                run_subagent(task_json, mock_agent_cls, config, tmp_path)
            )

        assert result.status == "complete"
        assert result.task_id == "task-1"
        assert result.error is None
        mock_span.set_attribute.assert_any_call("akms.success", True)
        mock_span.end.assert_called_once()

    @pytest.mark.unit
    def test_failed_dispatch(self, tmp_path):
        """
        Verifies: Agent exception returns TaskResult with status='failed' and error msg.
        Passes when: result.status == 'failed' and result.error contains exception message.
        """
        from akms.schema.models import PropagationConfig

        config = PropagationConfig()

        mock_agent_instance = MagicMock()
        mock_agent_instance.run = AsyncMock(
            side_effect=RuntimeError("agent crashed")
        )

        mock_agent_cls = MagicMock(return_value=mock_agent_instance)

        task_json = {"task_id": "task-2", "agent_role": "implementer"}

        with patch(
            "akms.orchestrator.wave_dispatch.trace_agent_call"
        ) as mock_trace:
            mock_span = MagicMock()
            mock_trace.return_value = mock_span

            result = asyncio.run(
                run_subagent(task_json, mock_agent_cls, config, tmp_path)
            )

        assert result.status == "failed"
        assert result.task_id == "task-2"
        assert "agent crashed" in result.error
        mock_span.set_attribute.assert_any_call("akms.success", False)
        mock_span.end.assert_called_once()


class TestDispatchPhaseFailureIsolation:
    """
    Tests for dispatch_phase() failure isolation via return_exceptions=True.
    Acceptance criterion: one failed task doesn't kill other tasks in the same wave.
    """

    @pytest.mark.unit
    def test_partial_wave_failure(self, tmp_path):
        """
        Verifies: One task failure in a wave doesn't prevent other tasks from completing.
        Passes when: Both tasks reported -- one 'complete', one 'failed'.
        """
        from akms.schema.models import PropagationConfig

        config = PropagationConfig()

        tasks = [
            {"task_id": "ok-task", "scope": ["src/a.py"]},
            {"task_id": "bad-task", "scope": ["src/b.py"]},
        ]

        ok_result = TaskResult(
            task_id="ok-task", status="complete", memory_path="/tmp/ok.md"
        )
        bad_result = TaskResult(
            task_id="bad-task",
            status="failed",
            memory_path="",
            error="boom",
        )

        async def fake_run_subagent(task_json, agent_cls, config, repo_root, model_override=None):
            if task_json["task_id"] == "ok-task":
                return ok_result
            return bad_result

        with patch(
            "akms.orchestrator.wave_dispatch.run_subagent",
            side_effect=fake_run_subagent,
        ), patch(
            "akms.orchestrator.wave_dispatch.build_waves",
            return_value=[tasks],
        ), patch(
            "akms.orchestrator.wave_dispatch.validate_scope_disjointness",
        ):
            results = asyncio.run(
                dispatch_phase(tasks, MagicMock(), config, tmp_path)
            )

        assert len(results) == 2
        statuses = {r.task_id: r.status for r in results}
        assert statuses["ok-task"] == "complete"
        assert statuses["bad-task"] == "failed"
