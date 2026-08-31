"""Schema-valid FakeAgent for deterministic E2E tests.

Emits v2-compliant AgentMemory objects — NOT raw markdown stubs.
This ensures E2E tests that flow into update_graph.py don't crash
on schema validation.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from akms.schema.models import AgentMemory


class FakeAgent:
    """Deterministic test agent that emits schema-valid AgentMemory."""

    def __init__(self, config: Any, model: str, repo_root: Path):
        self.config = config
        self.model = model
        self.repo_root = repo_root

    async def run(self, task_json: dict) -> AgentMemory:
        task_id = task_json.get("task_id", "unknown")
        phase_id = task_json.get("phase_id", task_json.get("phase", 0))

        memory = AgentMemory(
            task_id=task_id,
            phase_id=phase_id,
            timestamp=datetime.now(),
            agent_model=self.model,
            loadout_used=task_json.get("loadout_path", ""),
            status="complete",
            tests_passed=1,
            tests_total=1,
            task_description=task_json.get("task_description", "FakeAgent task"),
            completion_notes="FakeAgent completed successfully",
            nodes_used=task_json.get("akms_tags", []),
            # akms_schema defaults to "v2" from the model
        )

        # Persist to standard location
        out_dir = self.repo_root / "knowledge" / "sessions"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{task_id}.md"

        # Write as YAML frontmatter + body (matches real agent output format)
        frontmatter_data = memory.model_dump(mode="json")

        # Role-specific frontmatter extensions
        agent_role = task_json.get("agent_role", "implementer")
        if agent_role == "task_decomposer":
            frontmatter_data["tasks"] = [
                {
                    "task_id": f"{task_id}-t1",
                    "phase": 1,
                    "title": "FakeAgent decomposed task",
                    "objective": "Placeholder task from FakeAgent decomposer",
                    "blocked_by": [],
                    "scope": [],
                    "akms_tags": [],
                    "akms_schema": "v2",
                }
            ]

        import yaml
        out_path.write_text(
            "---\n"
            + yaml.dump(frontmatter_data, default_flow_style=False, sort_keys=False)
            + "---\n"
            + f"# FakeAgent Output: {task_id}\n"
        )

        return memory
