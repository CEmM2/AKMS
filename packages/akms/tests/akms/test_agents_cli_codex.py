"""Tests for AKMSCodexCliAgent (the `codex exec` backend).

No real `codex` binary is invoked: ``run_cli`` / ``find_binary`` are
monkeypatched. The fake ``run_cli`` writes a valid AgentMemory so the sealed
``AKMSAgent.run()`` lifecycle can validate it. These assert argv construction
(flags + prepended system prompt + MCP overrides), not live Codex behavior.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import frontmatter
import pytest

from akms.agents import cli_codex
from akms.agents.cli_codex import AKMSCodexCliAgent, _codex_mcp_overrides
from akms.schema.models import PropagationConfig, TaskStatus


def _write_valid_agent_memory(repo_root: Path, task_id: str = "task-1") -> Path:
    sessions_dir = repo_root / "knowledge" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    output_path = sessions_dir / f"{task_id}.md"
    memory_dict = {
        "task_id": task_id,
        "task_description": "Test task",
        "phase_id": 1,
        "timestamp": datetime.now().isoformat(),
        "agent_model": "gpt-5-codex",
        "loadout_used": "",
        "status": "complete",
        "commit": "abc123",
        "tests_passed": 1,
        "tests_total": 1,
        "completion_notes": "All done",
        "nodes_used": [],
        "nodes_missing": [],
        "lessons": {"worked": [], "failed": []},
        "pitfalls_discovered": [],
        "new_knowledge": [],
        "akms_schema": "v2",
    }
    post = frontmatter.Post(content="\n## Notes\n\nok\n", **memory_dict)
    with open(output_path, "wb") as f:
        frontmatter.dump(post, f)
    return output_path


def _task_json(task_id: str = "task-1", tools: list[str] | None = None) -> dict:
    tj = {"task_id": task_id, "phase": 1, "title": "Test task", "loadout_path": ""}
    if tools is not None:
        tj["tools"] = tools
    return tj


@pytest.mark.unit
def test_execute_builds_codex_exec_command(tmp_repo, monkeypatch):
    captured: dict = {}

    async def fake_run_cli(cmd, cwd):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        _write_valid_agent_memory(Path(cwd), "task-1")

    monkeypatch.setattr(cli_codex, "find_binary", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(cli_codex, "run_cli", fake_run_cli)

    agent = AKMSCodexCliAgent(
        config=PropagationConfig(), repo_root=tmp_repo, model="gpt-5-codex"
    )
    memory = asyncio.run(agent.run(_task_json()))

    assert memory.status == TaskStatus.COMPLETE

    cmd = captured["cmd"]
    assert cmd[0] == "/usr/bin/codex"
    assert cmd[1] == "exec"
    assert "--model" in cmd and "gpt-5-codex" in cmd
    assert "--cd" in cmd and str(tmp_repo) in cmd
    assert "--sandbox" in cmd and "workspace-write" in cmd
    # codex exec has no --ask-for-approval flag; approvals set via -c config.
    assert "--ask-for-approval" not in cmd
    assert any(a == 'approval_policy="never"' for a in cmd)
    assert "--skip-git-repo-check" in cmd
    assert Path(captured["cwd"]) == Path(tmp_repo)

    full_prompt = cmd[-1]
    assert "AgentMemory" in full_prompt or "agent memory" in full_prompt.lower()
    assert "---" in full_prompt

    # Best-effort MCP wiring via -c overrides.
    assert "-c" in cmd
    joined = " ".join(cmd)
    assert "mcp_servers.akms.command=" in joined
    assert "akms.orchestrator.mcp_stdio" in joined


@pytest.mark.unit
def test_omits_model_when_not_given(tmp_repo, monkeypatch):
    captured: dict = {}

    async def fake_run_cli(cmd, cwd):
        captured["cmd"] = cmd
        _write_valid_agent_memory(Path(cwd), "task-1")

    monkeypatch.setattr(cli_codex, "find_binary", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(cli_codex, "run_cli", fake_run_cli)

    # No explicit model → codex uses its own default; --model omitted.
    agent = AKMSCodexCliAgent(config=PropagationConfig(), repo_root=tmp_repo)
    asyncio.run(agent.run(_task_json()))
    assert "--model" not in captured["cmd"]


@pytest.mark.unit
def test_run_cli_failure_maps_to_failed_memory(tmp_repo, monkeypatch):
    async def boom(cmd, cwd):
        raise RuntimeError("agent CLI 'codex' exited with code 1: nope")

    monkeypatch.setattr(cli_codex, "find_binary", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(cli_codex, "run_cli", boom)

    agent = AKMSCodexCliAgent(config=PropagationConfig(), repo_root=tmp_repo)
    memory = asyncio.run(agent.run(_task_json()))

    assert memory.status == TaskStatus.FAILED
    assert "codex" in memory.completion_notes.lower()


@pytest.mark.unit
def test_codex_mcp_overrides_are_parseable(tmp_path):
    overrides = _codex_mcp_overrides(tmp_path)
    # Pairs of ("-c", "key=value"); values after '=' must be valid JSON.
    assert overrides[0] == "-c" and overrides[2] == "-c"
    for kv in (overrides[1], overrides[3]):
        key, _, value = kv.partition("=")
        json.loads(value)  # raises if not valid JSON
    assert "mcp_servers.akms.command" in overrides[1]
    args_value = json.loads(overrides[3].split("=", 1)[1])
    assert args_value[:2] == ["-m", "akms.orchestrator.mcp_stdio"]
    assert args_value[-1] == str(tmp_path)


@pytest.mark.unit
def test_backend_resolves_codex_cli():
    from akms.cli.commands import BACKENDS, _import_agent_class

    cls = _import_agent_class(BACKENDS["codex-cli"])
    assert cls is AKMSCodexCliAgent
