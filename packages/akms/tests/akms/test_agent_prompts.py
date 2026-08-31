"""Tests for agent prompt wiring: system_prompt_additions + task_instructions_path.

Verifies that fields injected by wave_dispatch (from agent_configs) actually
reach the prompts built by AKMSAgent._build_system_prompt and _build_task_prompt.
Includes an integration test through the real prompt-building path.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from akms.agents.base import AKMSAgent
from akms.schema.models import PropagationConfig


@pytest.fixture
def bare_agent(tmp_path):
    """Create a minimal AKMSAgent for testing prompt builders."""
    repo = tmp_path / "repo"
    repo.mkdir()
    config = PropagationConfig()
    agent = AKMSAgent(config=config, model="test-model", repo_root=repo)
    return agent


class TestSystemPromptAdditions:
    """Verify _build_system_prompt renders system_prompt_additions from task_json."""

    def test_system_prompt_includes_additions(self, bare_agent):
        """system_prompt_additions text should appear in the system prompt."""
        task_json = {
            "task_id": "t1",
            "system_prompt_additions": (
                "You MUST include a 'tasks' key in your AgentMemory frontmatter."
            ),
            "loadout_path": "",
        }
        from akms.agents.base import Loadout
        loadout = Loadout(path="")
        prompt = bare_agent._build_system_prompt(loadout, task_json)

        assert "Role-Specific Instructions" in prompt
        assert "You MUST include a 'tasks' key" in prompt

    def test_system_prompt_without_additions(self, bare_agent):
        """When system_prompt_additions is absent, no extra section appears."""
        task_json = {"task_id": "t1", "loadout_path": ""}
        from akms.agents.base import Loadout
        loadout = Loadout(path="")
        prompt = bare_agent._build_system_prompt(loadout, task_json)

        assert "Role-Specific Instructions" not in prompt


class TestTaskInstructionsPath:
    """Verify _build_task_prompt renders task_instructions_path."""

    def test_task_prompt_includes_instructions_path(self, bare_agent):
        """task_instructions_path should appear in task prompt with read instruction."""
        task_json = {
            "task_id": "t1",
            "task_instructions_path": "/knowledge/task_instructions.md",
            "loadout_path": "",
        }
        prompt = bare_agent._build_task_prompt(task_json)

        assert "Task Instructions" in prompt
        assert "/knowledge/task_instructions.md" in prompt
        assert "Read detailed task decomposition instructions from:" in prompt

    def test_task_prompt_without_instructions_path(self, bare_agent):
        """When task_instructions_path is absent, no extra section appears."""
        task_json = {"task_id": "t1", "loadout_path": ""}
        prompt = bare_agent._build_task_prompt(task_json)

        assert "Task Instructions" not in prompt


class TestPromptIntegration:
    """Integration test: verify prompt wiring through the run_subagent dispatch path.

    Uses a CapturingAgent subclass that records the prompts built by
    _build_system_prompt and _build_task_prompt instead of calling the SDK.
    """

    def test_prompt_fields_reach_agent_via_run_subagent(self, tmp_path):
        """system_prompt_additions and task_instructions_path both appear in
        the prompts built during run_subagent dispatch."""
        import asyncio
        from akms.orchestrator.wave_dispatch import run_subagent

        repo = tmp_path / "repo"
        for d in ("graph", "nodes", "sessions"):
            (repo / "knowledge" / d).mkdir(parents=True)

        captured_system = []
        captured_task = []

        class CapturingAgent(AKMSAgent):
            """Agent that captures prompts instead of calling the SDK."""

            def _build_system_prompt(self, loadout, task_json):
                prompt = super()._build_system_prompt(loadout, task_json)
                captured_system.append(prompt)
                return prompt

            def _build_task_prompt(self, task_json):
                prompt = super()._build_task_prompt(task_json)
                captured_task.append(prompt)
                return prompt

            async def execute(self, task_json, loadout, system_prompt):
                task_prompt = self._build_task_prompt(task_json)
                captured_task.append(task_prompt)

                # Skip actual SDK call — just write a valid memory file
                from akms.schema.models import AgentMemory
                from datetime import datetime
                import yaml

                memory = AgentMemory(
                    task_id=task_json.get("task_id", "t1"),
                    phase_id=0,
                    timestamp=datetime.now(),
                    agent_model="test",
                    loadout_used="",
                    status="complete",
                    tests_passed=1,
                    tests_total=1,
                    task_description="test",
                    completion_notes="done",
                    nodes_used=[],
                )
                out_dir = self.repo_root / "knowledge" / "sessions"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"{memory.task_id}.md"
                out_path.write_text(
                    "---\n"
                    + yaml.dump(memory.model_dump(mode="json"), default_flow_style=False)
                    + "---\n"
                )

        config = PropagationConfig()
        task_json = {
            "task_id": "integration-test",
            "agent_role": "task_decomposer",
            "task_instructions_path": "/path/to/instructions.md",
            "akms_tags": [],
            "akms_schema": "v2",
            "loadout_path": "",
        }

        from unittest.mock import patch
        with patch("akms.orchestrator.wave_dispatch.trace_agent_call") as mock_trace:
            mock_trace.return_value = MagicMock()
            result = asyncio.run(
                run_subagent(task_json, CapturingAgent, config, repo)
            )

        assert result.status == "complete"

        # Verify system_prompt_additions reached the system prompt
        # (injected by run_subagent from agent_configs)
        assert len(captured_system) == 1
        sys_prompt = captured_system[0]
        assert "Role-Specific Instructions" in sys_prompt, (
            "system_prompt_additions from agent_configs should appear in system prompt"
        )
        assert "tasks" in sys_prompt.lower(), (
            "Decomposer role instructions should mention 'tasks' key requirement"
        )

        assert len(captured_task) >= 1, "Task prompt should have been captured at least once"
        task_prompt = captured_task[0]
        assert "/path/to/instructions.md" in task_prompt, (
            "task_instructions_path should appear in task prompt"
        )
