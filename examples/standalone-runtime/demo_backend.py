"""A deterministic, offline backend for the embedded AKMS runtime.

``DemoAgent`` subclasses :class:`akms.agents.base.AKMSAgent` — the documented
extension seam — and shows the two methods a custom backend implements:

* ``preflight()``: cheap availability probe, run before any file is written.
  Return ``None`` when the backend can run, or a human-readable reason string
  when it cannot.
* ``execute()``: do the work for one task and write a schema-valid
  ``AgentMemory`` file to ``knowledge/sessions/{task_id}.md``. The sealed
  ``run()`` wrapper owns the protocol lifecycle around it.

No network, no credentials, no LLM: every task "succeeds" with a canned
result, so the full pipeline can be observed end to end.
"""

from __future__ import annotations

from datetime import datetime

import yaml

from akms.agents.base import AKMSAgent
from akms.schema.models import AgentMemory


class DemoAgent(AKMSAgent):
    """Offline stand-in for a real coding-agent backend."""

    def preflight(self) -> str | None:
        return None  # always available: this backend needs no binary or SDK

    async def execute(self, task_json: dict, loadout, system_prompt: str) -> None:
        task_id = task_json.get("task_id", task_json.get("id", "unknown"))
        memory = AgentMemory(
            task_id=task_id,
            phase_id=task_json.get("phase_id", task_json.get("phase", 0)),
            timestamp=datetime.now(),
            agent_model="demo-offline",
            loadout_used=task_json.get("loadout_path", ""),
            status="complete",
            tests_passed=1,
            tests_total=1,
            task_description=task_json.get("task_description", "demo task"),
            completion_notes="DemoAgent completed offline",
            nodes_used=task_json.get("akms_tags", []),
        )
        data = memory.model_dump(mode="json")
        # A task_decomposer must emit a `tasks` list for the breakdown stage.
        if task_json.get("agent_role") == "task_decomposer":
            data["tasks"] = [
                {
                    "task_id": f"{task_id}-t1",
                    "phase": 1,
                    "title": "Demo task",
                    "objective": "Single placeholder work item",
                    "blocked_by": [],
                    "scope": [],
                    "akms_tags": [],
                    "akms_schema": "v2",
                }
            ]
        out = self._expected_memory_path(task_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            "---\n"
            + yaml.dump(data, default_flow_style=False, sort_keys=False)
            + "---\n"
            + f"# DemoAgent output for {task_id}\n"
        )
