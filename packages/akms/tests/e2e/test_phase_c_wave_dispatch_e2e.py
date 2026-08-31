"""Phase C E2E: wave dispatch with FakeAgent through full dispatch_phase.

End-to-end test verifying the complete wave dispatch pipeline with a 4-task
diamond dependency pattern using FakeAgent for deterministic agent execution.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from akms.orchestrator.wave_dispatch import build_waves, dispatch_phase
from tests.fakes.fake_agent import FakeAgent


class TestWaveDispatchE2E:
    """
    E2E wave dispatch with FakeAgent.
    Acceptance criterion: 4-task diamond pattern with FakeAgent -- all 4 complete,
                          correct wave ordering, memory files exist.
    """

    @pytest.mark.e2e
    def test_four_task_diamond_dispatch(self, tmp_path):
        """
        Verifies: Full dispatch_phase with 4-task diamond dependency pattern
                  using FakeAgent produces correct wave ordering, all tasks complete,
                  and memory files are persisted.
        Acceptance criterion: E2E: 4-task diamond with FakeAgent through full
                              dispatch_phase
        Passes when:
          - build_waves produces 3 waves: [root], [left, right], [join]
          - dispatch_phase returns 4 results, all status='complete'
          - Memory files exist at repo_root/knowledge/sessions/{task_id}.md
        """
        from akms.schema.models import PropagationConfig

        config = PropagationConfig()

        tasks = [
            {
                "task_id": "root",
                "agent_role": "implementer",
                "scope": ["src/root.py"],
                "phase": 1,
                "task_description": "Root task",
            },
            {
                "task_id": "left",
                "agent_role": "implementer",
                "blocked_by": ["root"],
                "scope": ["src/left.py"],
                "phase": 1,
                "task_description": "Left task",
            },
            {
                "task_id": "right",
                "agent_role": "implementer",
                "blocked_by": ["root"],
                "scope": ["src/right.py"],
                "phase": 1,
                "task_description": "Right task",
            },
            {
                "task_id": "join",
                "agent_role": "implementer",
                "blocked_by": ["left", "right"],
                "scope": ["src/join.py"],
                "phase": 1,
                "task_description": "Join task",
            },
        ]

        # Verify wave structure
        waves = build_waves(tasks)
        assert len(waves) == 3
        assert waves[0][0]["task_id"] == "root"
        wave1_ids = {t["task_id"] for t in waves[1]}
        assert wave1_ids == {"left", "right"}
        assert waves[2][0]["task_id"] == "join"

        # Patch trace_agent_call to avoid OTel span issues
        with patch("akms.orchestrator.wave_dispatch.trace_agent_call") as mock_trace:
            from unittest.mock import MagicMock

            mock_span = MagicMock()
            mock_trace.return_value = mock_span

            results = asyncio.run(
                dispatch_phase(
                    tasks,
                    FakeAgent,
                    config,
                    tmp_path,
                )
            )

        # All 4 tasks should complete
        assert len(results) == 4
        for r in results:
            assert r.status == "complete", (
                f"Task {r.task_id} status={r.status}, error={r.error}"
            )

        # Verify memory files exist
        for task in tasks:
            tid = task["task_id"]
            memory_path = tmp_path / "knowledge" / "sessions" / f"{tid}.md"
            assert memory_path.exists(), f"Memory file missing for {tid}"
