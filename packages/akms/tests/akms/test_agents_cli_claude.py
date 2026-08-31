"""Tests for AKMSClaudeCliAgent (the `claude -p` headless backend), the shared
CLI helpers, and the --backend selector wiring.

No real `claude` binary is invoked: ``run_cli`` / ``find_binary`` are
monkeypatched. The fake ``run_cli`` writes a valid AgentMemory so the sealed
``AKMSAgent.run()`` lifecycle can validate it — mirroring the Codex backend
test pattern.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path

import frontmatter
import pytest

from akms.agents import cli_claude
from akms.agents._cli_common import akms_mcp_config_json, find_binary
from akms.agents.cli_claude import AKMSClaudeCliAgent
from akms.schema.models import PropagationConfig, TaskStatus


# ── Helpers ──────────────────────────────────────────────────────────


def _write_valid_agent_memory(repo_root: Path, task_id: str = "task-1") -> Path:
    sessions_dir = repo_root / "knowledge" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    output_path = sessions_dir / f"{task_id}.md"
    memory_dict = {
        "task_id": task_id,
        "task_description": "Test task",
        "phase_id": 1,
        "timestamp": datetime.now().isoformat(),
        "agent_model": "claude-sonnet-4-6",
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


# ── Backend: command construction + protocol ─────────────────────────


@pytest.mark.unit
def test_execute_builds_claude_cli_command(tmp_repo, monkeypatch):
    captured: dict = {}

    async def fake_run_cli(cmd, cwd):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        _write_valid_agent_memory(Path(cwd), "task-1")

    monkeypatch.setattr(cli_claude, "find_binary", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(cli_claude, "run_cli", fake_run_cli)

    agent = AKMSClaudeCliAgent(
        config=PropagationConfig(), repo_root=tmp_repo, model="claude-sonnet-4-6"
    )
    memory = asyncio.run(agent.run(_task_json(tools=["file_edit", "search"])))

    assert memory.status == TaskStatus.COMPLETE

    cmd = captured["cmd"]
    assert cmd[0] == "/usr/bin/claude"
    assert "-p" in cmd
    assert "--append-system-prompt" in cmd
    assert "--permission-mode" in cmd and "acceptEdits" in cmd
    assert "--model" in cmd and "claude-sonnet-4-6" in cmd
    assert Path(captured["cwd"]) == Path(tmp_repo)

    # Resolved allowed-tools incl. qmd search parity (FR-C05/FR-Q05).
    assert "--allowedTools" in cmd
    assert "Write" in cmd and "Edit" in cmd
    assert "mcp__akms__akms_search_nodes" in cmd

    # --mcp-config wires the AKMS stdio server for this repo.
    cfg = json.loads(cmd[cmd.index("--mcp-config") + 1])
    args = cfg["mcpServers"]["akms"]["args"]
    assert "akms.orchestrator.mcp_stdio" in args
    assert str(tmp_repo) in args


@pytest.mark.unit
def test_omits_model_when_not_given(tmp_repo, monkeypatch):
    captured: dict = {}

    async def fake_run_cli(cmd, cwd):
        captured["cmd"] = cmd
        _write_valid_agent_memory(Path(cwd), "task-1")

    monkeypatch.setattr(cli_claude, "find_binary", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(cli_claude, "run_cli", fake_run_cli)

    # No explicit model → claude uses its own default; --model omitted.
    agent = AKMSClaudeCliAgent(config=PropagationConfig(), repo_root=tmp_repo)
    asyncio.run(agent.run(_task_json()))
    assert "--model" not in captured["cmd"]


@pytest.mark.unit
def test_run_cli_failure_maps_to_failed_memory(tmp_repo, monkeypatch):
    async def boom(cmd, cwd):
        raise RuntimeError("agent CLI 'claude' exited with code 2: nope")

    monkeypatch.setattr(cli_claude, "find_binary", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(cli_claude, "run_cli", boom)

    agent = AKMSClaudeCliAgent(config=PropagationConfig(), repo_root=tmp_repo)
    memory = asyncio.run(agent.run(_task_json()))

    assert memory.status == TaskStatus.FAILED
    assert "claude" in memory.completion_notes.lower()


@pytest.mark.unit
def test_missing_binary_maps_to_failed_memory(tmp_repo, monkeypatch):
    def missing(name):
        raise RuntimeError(f"The '{name}' CLI was not found on PATH.")

    monkeypatch.setattr(cli_claude, "find_binary", missing)

    agent = AKMSClaudeCliAgent(config=PropagationConfig(), repo_root=tmp_repo)
    memory = asyncio.run(agent.run(_task_json()))

    assert memory.status == TaskStatus.FAILED


# ── Shared CLI helpers ───────────────────────────────────────────────


@pytest.mark.unit
def test_find_binary_missing_raises():
    with pytest.raises(RuntimeError, match="not found on PATH"):
        find_binary("definitely-not-a-real-binary-akms-xyz")


@pytest.mark.unit
def test_akms_mcp_config_json_wires_stdio(tmp_path):
    cfg = json.loads(akms_mcp_config_json(tmp_path))
    akms = cfg["mcpServers"]["akms"]
    assert akms["args"][:3] == ["-m", "akms.orchestrator.mcp_stdio", "--repo-root"]
    assert akms["args"][-1] == str(tmp_path)


# ── --backend selector wiring ────────────────────────────────────────


@pytest.mark.unit
def test_backends_map_resolves_claude_cli():
    from akms.cli.commands import BACKENDS, _import_agent_class

    cls = _import_agent_class(BACKENDS["claude-cli"])
    assert cls is AKMSClaudeCliAgent


@pytest.mark.unit
def test_all_backends_resolve_to_agent_subclasses():
    from akms.agents.base import AKMSAgent
    from akms.cli.commands import BACKENDS, _import_agent_class

    for name, path in BACKENDS.items():
        cls = _import_agent_class(path)
        assert issubclass(cls, AKMSAgent), name
