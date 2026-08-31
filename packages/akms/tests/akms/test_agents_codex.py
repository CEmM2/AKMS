"""Tests for AKMSAgent base class and AKMSCodexAgent adapter.

Tests verify the revised spec contract:
- ``run()`` is sealed (cannot be overridden)
- ``execute()`` returns None; the agent writes AgentMemory to disk
- ``run()`` reads and validates AgentMemory post-execution
- Missing AgentMemory → ``_write_failed_memory()`` produces status: failed
- Malformed AgentMemory → ``SchemaValidationError``
"""

from __future__ import annotations

import asyncio
import builtins
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace

import frontmatter
import pytest

from akms.agents.base import AKMSAgent, Loadout
from akms.agents.base_codex import (
    AKMSCodexAgent,
    _tool_bash,
    _tool_edit,
    _tool_glob,
    _tool_multi_edit,
    _tool_read,
    _tool_write,
)
from akms.schema.errors import SchemaValidationError
from akms.schema.models import PropagationConfig, TaskStatus


# ── Helpers ──────────────────────────────────────────────────────────


def _write_valid_agent_memory(repo_root: Path, task_id: str = "task-1") -> Path:
    """Write a valid AgentMemory file that an agent would produce."""
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
        "tests_passed": 2,
        "tests_total": 2,
        "completion_notes": "All done",
        "nodes_used": [],
        "nodes_missing": [],
        "lessons": {"worked": [], "failed": []},
        "pitfalls_discovered": [],
        "new_knowledge": [],
        "akms_schema": "v2",
    }
    post = frontmatter.Post(
        content="\n## Task Notes\n\nEverything went well.\n",
        **memory_dict,
    )
    with open(output_path, "wb") as f:
        frontmatter.dump(post, f)
    return output_path


def _make_task_json(task_id: str = "task-1", phase: int = 1) -> dict:
    return {
        "task_id": task_id,
        "phase": phase,
        "title": "Test task",
        "loadout_path": "",
    }


# ── AKMSAgent sealed protocol tests ─────────────────────────────────


def test_run_is_sealed():
    """Subclass overriding run() raises TypeError at class definition time."""
    with pytest.raises(TypeError, match="must not override AKMSAgent.run"):

        class BadAgent(AKMSAgent):
            async def run(self, task_json: dict):
                pass


def test_execute_is_overridable():
    """Subclass can override execute() without error."""

    class GoodAgent(AKMSAgent):
        async def execute(self, task_json, loadout, system_prompt):
            pass  # Valid override

    assert issubclass(GoodAgent, AKMSAgent)


def test_run_reads_valid_agent_memory(tmp_repo: Path):
    """run() reads and validates AgentMemory written by the agent."""

    class MockAgent(AKMSAgent):
        async def execute(self, task_json, loadout, system_prompt):
            # Simulate agent writing AgentMemory
            _write_valid_agent_memory(self.repo_root, task_json["task_id"])

    agent = MockAgent(config=PropagationConfig(), repo_root=tmp_repo)
    memory = asyncio.run(agent.run(_make_task_json()))

    assert memory.task_id == "task-1"
    assert memory.status == TaskStatus.COMPLETE
    assert memory.tests_passed == 2
    assert memory.commit == "abc123"


def test_run_writes_failed_memory_when_execute_raises(tmp_repo: Path):
    """execute() raising → run() writes status: failed AgentMemory."""

    class ExplodingAgent(AKMSAgent):
        async def execute(self, task_json, loadout, system_prompt):
            raise RuntimeError("boom")

    agent = ExplodingAgent(config=PropagationConfig(), repo_root=tmp_repo)
    memory = asyncio.run(agent.run(_make_task_json()))

    assert memory.status == TaskStatus.FAILED
    assert "RuntimeError: boom" in memory.completion_notes
    assert (tmp_repo / "knowledge" / "sessions" / "task-1.md").exists()


def test_run_writes_failed_memory_when_no_file(tmp_repo: Path):
    """Agent not writing AgentMemory → run() writes status: failed."""

    class SilentAgent(AKMSAgent):
        async def execute(self, task_json, loadout, system_prompt):
            pass  # Deliberately does not write AgentMemory

    agent = SilentAgent(config=PropagationConfig(), repo_root=tmp_repo)
    memory = asyncio.run(agent.run(_make_task_json()))

    assert memory.status == TaskStatus.FAILED
    assert "did not write AgentMemory" in memory.completion_notes


def test_run_raises_on_malformed_memory(tmp_repo: Path):
    """Malformed AgentMemory file → SchemaValidationError."""

    class BadWriterAgent(AKMSAgent):
        async def execute(self, task_json, loadout, system_prompt):
            # Write an AgentMemory with missing required fields
            sessions_dir = self.repo_root / "knowledge" / "sessions"
            sessions_dir.mkdir(parents=True, exist_ok=True)
            path = sessions_dir / f"{task_json['task_id']}.md"
            post = frontmatter.Post(
                content="bad memory",
                **{"task_id": task_json["task_id"]},  # missing required fields
            )
            with open(path, "wb") as f:
                frontmatter.dump(post, f)

    agent = BadWriterAgent(config=PropagationConfig(), repo_root=tmp_repo)
    with pytest.raises(SchemaValidationError):
        asyncio.run(agent.run(_make_task_json()))


def test_execute_receives_system_prompt_with_memory_instructions(tmp_repo: Path):
    """execute() receives a system prompt containing AgentMemory write instructions."""
    captured = {}

    class CapturingAgent(AKMSAgent):
        async def execute(self, task_json, loadout, system_prompt):
            captured["system_prompt"] = system_prompt
            # Write valid memory so run() doesn't fail
            _write_valid_agent_memory(self.repo_root, task_json["task_id"])

    agent = CapturingAgent(config=PropagationConfig(), repo_root=tmp_repo)
    asyncio.run(agent.run(_make_task_json()))

    assert "AgentMemory Write Instructions" in captured["system_prompt"]
    assert "task-1" in captured["system_prompt"]


def test_init_signature(tmp_repo: Path):
    """AKMSAgent.__init__ accepts config, repo_root, model."""
    agent = AKMSAgent(
        config=PropagationConfig(),
        repo_root=tmp_repo,
        model="claude-opus-4-6",
    )
    assert agent.model == "claude-opus-4-6"
    assert agent.repo_root == tmp_repo


def test_default_model_from_config(tmp_repo: Path):
    """When model=None, falls back to config.orchestrator.default_model."""
    agent = AKMSAgent(config=PropagationConfig(), repo_root=tmp_repo)
    assert agent.model == "claude-sonnet-4-6"


# ── AKMSCodexAgent tests ────────────────────────────────────────────


class _FakeRunResult:
    def __init__(self, final_output: str):
        self.final_output = final_output


class _FakeAgent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeRunner:
    @staticmethod
    def run_sync(agent, input: str, max_turns: int = 25):
        _ = (agent, input, max_turns)
        return _FakeRunResult("Agent completed task.")

    @staticmethod
    async def run(agent, input: str, max_turns: int = 25):
        _ = (agent, input, max_turns)
        return _FakeRunResult("Agent completed task.")


def _install_fake_agents(monkeypatch: pytest.MonkeyPatch):
    fake_mod = ModuleType("agents")

    def function_tool(*args, **kwargs):
        _ = (args, kwargs)

        def _decorator(fn):
            return fn

        return _decorator

    fake_mod.Agent = _FakeAgent
    fake_mod.Runner = _FakeRunner
    fake_mod.function_tool = function_tool
    monkeypatch.setitem(sys.modules, "agents", fake_mod)


def test_codex_agent_is_subclass():
    assert issubclass(AKMSCodexAgent, AKMSAgent)


def test_codex_import_error_message(monkeypatch: pytest.MonkeyPatch, tmp_repo: Path):
    real_import = builtins.__import__

    def _raising_import(name, *args, **kwargs):
        if name == "agents":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _raising_import)

    agent = AKMSCodexAgent(config=PropagationConfig(), repo_root=tmp_repo)
    with pytest.raises(ImportError, match="openai-agents"):
        asyncio.run(agent.execute(_make_task_json(), Loadout(path=""), "sys prompt"))


def test_protocol_failure_mapping_when_execute_raises(tmp_repo: Path):
    """Codex agent raising → run() writes status: failed AgentMemory."""

    class ExplodingCodexAgent(AKMSCodexAgent):
        async def execute(self, task_json, loadout, system_prompt):
            raise RuntimeError("boom")

    agent = ExplodingCodexAgent(config=PropagationConfig(), repo_root=tmp_repo)
    memory = asyncio.run(agent.run({"task_id": "task-1", "phase": 1}))

    assert memory.status == TaskStatus.FAILED
    assert "RuntimeError: boom" in memory.completion_notes
    assert (tmp_repo / "knowledge" / "sessions" / "task-1.md").exists()


# ── Tool tests (unchanged — these test the Codex tool shims) ────────


def test_tool_read_edit_glob_bash(tmp_repo: Path):
    (tmp_repo / "a.txt").write_text("hello world\n", encoding="utf-8")
    (tmp_repo / "b.py").write_text("print('hello world')\n", encoding="utf-8")

    assert "hello world" in _tool_read(tmp_repo, "a.txt")
    assert _tool_edit(tmp_repo, "a.txt", "hello world", "bye world").startswith("OK:")
    assert "bye world" in (tmp_repo / "a.txt").read_text(encoding="utf-8")

    glob_out = _tool_glob(tmp_repo, "*.txt")
    assert "a.txt" in glob_out

    # The grep runtime tool is deliberately gone; qmd-backed
    # MCP tools are the sanctioned replacement (see akms_search_nodes,
    # akms_search_mirror).

    assert _tool_bash(tmp_repo, "pwd").strip() == str(tmp_repo.resolve())


def test_tool_write(tmp_repo: Path):
    result = _tool_write(tmp_repo, "new_file.txt", "content here")
    assert result.startswith("OK:")
    assert (tmp_repo / "new_file.txt").read_text(encoding="utf-8") == "content here"


def test_tool_failures_are_structured(tmp_repo: Path):
    assert _tool_read(tmp_repo, "missing.txt").startswith("ERROR:")
    assert _tool_edit(tmp_repo, "missing.txt", "x", "y").startswith("ERROR:")
    assert _tool_bash(tmp_repo, "exit 2").startswith("ERROR:")


def test_tool_repo_root_scope_enforced(tmp_repo: Path):
    outside = tmp_repo.parent / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    result = _tool_read(tmp_repo, str(outside))
    assert result.startswith("ERROR:")
    assert "outside repository root" in result


def test_tool_multi_edit_happy_path(tmp_repo: Path):
    """3-line file with 2 edits applied; 1 line unchanged."""
    target = tmp_repo / "sample.txt"
    target.write_text("line one\nline two\nline three\n", encoding="utf-8")

    edits = [
        {"old_text": "line one", "new_text": "LINE ONE"},
        {"old_text": "line three", "new_text": "LINE THREE"},
    ]
    result = _tool_multi_edit(tmp_repo, "sample.txt", edits)

    assert result.startswith("OK:")
    content = target.read_text(encoding="utf-8")
    assert "LINE ONE" in content
    assert "line two" in content  # unchanged
    assert "LINE THREE" in content


def test_tool_multi_edit_empty_old_text(tmp_repo: Path):
    """Empty old_text returns ERROR without modifying the file."""
    target = tmp_repo / "sample.txt"
    target.write_text("original content\n", encoding="utf-8")

    result = _tool_multi_edit(
        tmp_repo, "sample.txt", [{"old_text": "", "new_text": "x"}]
    )

    assert result.startswith("ERROR:")
    assert target.read_text(encoding="utf-8") == "original content\n"


def test_tool_multi_edit_not_found(tmp_repo: Path):
    """old_text not present in file returns ERROR without modifying the file."""
    target = tmp_repo / "sample.txt"
    target.write_text("hello world\n", encoding="utf-8")

    result = _tool_multi_edit(
        tmp_repo, "sample.txt", [{"old_text": "no such text", "new_text": "x"}]
    )

    assert result.startswith("ERROR:")
    assert target.read_text(encoding="utf-8") == "hello world\n"


def test_tool_multi_edit_multiple_matches(tmp_repo: Path):
    """old_text appearing more than once returns ERROR without modifying the file."""
    target = tmp_repo / "sample.txt"
    target.write_text("dup\ndup\n", encoding="utf-8")

    result = _tool_multi_edit(
        tmp_repo, "sample.txt", [{"old_text": "dup", "new_text": "unique"}]
    )

    assert result.startswith("ERROR:")
    assert target.read_text(encoding="utf-8") == "dup\ndup\n"


# ── PR18-T2: Codex function-tool parity with the MCP search surface ──


class TestCodexMcpSearchParity:
    """The Codex runtime must expose the same mcp__akms__akms_search_* tools
    as function tools so `resolve_runtime_tools(['search'])` names aren't
    silently filtered out by the `n in _registry` gate in
    ``_codex_sdk_execute``."""

    def test_search_nodes_delegates_to_run_qmd(self, tmp_repo: Path, monkeypatch):
        from akms.agents.base_codex import _tool_search_nodes

        captured = {}

        def fake_run_qmd(subcmd, query, *, repo_root, timeout=30.0):
            captured["subcmd"] = subcmd
            captured["query"] = query
            captured["repo_root"] = Path(repo_root)
            return [
                {"path": "knowledge/local-nodes/alpha.md", "line": 12, "snippet": "hit"}
            ]

        monkeypatch.setattr("akms.orchestrator.qmd_shell.run_qmd", fake_run_qmd)

        hits = _tool_search_nodes(tmp_repo, "alpha", limit=5)
        assert captured == {
            "subcmd": "search_nodes",
            "query": "alpha",
            "repo_root": tmp_repo,
        }
        assert hits == [
            {"path": "knowledge/local-nodes/alpha.md", "line": 12, "snippet": "hit"}
        ]

    def test_search_limit_is_applied(self, tmp_repo: Path, monkeypatch):
        from akms.agents.base_codex import _tool_search_sessions

        def fake_run_qmd(subcmd, query, *, repo_root, timeout=30.0):
            return [{"path": f"p{i}", "line": i, "snippet": ""} for i in range(10)]

        monkeypatch.setattr("akms.orchestrator.qmd_shell.run_qmd", fake_run_qmd)
        hits = _tool_search_sessions(tmp_repo, "q", limit=3)
        assert len(hits) == 3

    def test_mcp_search_names_in_registry(self, tmp_repo: Path, monkeypatch):
        """All four mcp__akms__* names must land in `_registry` so
        `resolve_runtime_tools(['search','search_mirror'])` selections
        aren't dropped in the filter at the top of ``_codex_sdk_execute``."""
        import akms.agents.base_codex as bc

        # Stub openai-agents so importing it inside _codex_sdk_execute works
        # regardless of whether the optional dep is present.
        fake_agents = sys.modules.get("agents")
        if fake_agents is None:
            fake = ModuleType("agents")
            captured_tools: list[str] = []

            def function_tool(name_override=None, **_):
                def deco(fn):
                    captured_tools.append(name_override or fn.__name__)
                    return fn

                return deco

            class _Agent:
                def __init__(self, **_kwargs):
                    pass

            class _Runner:
                @staticmethod
                async def run(*_a, **_kw):
                    class _R:
                        final_output = None

                    return _R()

            fake.function_tool = function_tool
            fake.Agent = _Agent
            fake.Runner = _Runner
            monkeypatch.setitem(sys.modules, "agents", fake)

        # Inspect the registry keys through the executor's tool selection:
        # `resolve_runtime_tools(['search'])` must resolve to names the
        # codex registry recognizes.
        from akms.orchestrator.agent_configs import TOOL_NAME_MAP

        expected = set(TOOL_NAME_MAP["search"]) | set(TOOL_NAME_MAP["search_mirror"])
        # All four expected mcp__akms__ names are registered as Codex tools.
        assert expected <= {
            "mcp__akms__akms_search_nodes",
            "mcp__akms__akms_search_sessions",
            "mcp__akms__akms_search_mirror",
            "mcp__akms__akms_get_pitfalls",
        }, "TOOL_NAME_MAP now expects a search tool Codex does not expose"

    def test_get_pitfalls_reads_overlay_directly(self, tmp_repo: Path):
        import yaml as _yaml
        from akms.agents.base_codex import _tool_get_pitfalls

        overlay = {
            "akms_schema": "v2",
            "local_edges": [
                {
                    "from": "node-a",
                    "to": "session-1",
                    "type": "pitfall",
                    "weight": 0.7,
                    "note": "first",
                    "source_id": "task-1",
                },
                {
                    "from": "node-b",
                    "to": "session-2",
                    "type": "pitfall",
                    "weight": 0.3,
                    "note": "second",
                    "source_id": "task-2",
                },
                {
                    "from": "node-a",
                    "to": "session-3",
                    "type": "requires",
                    "weight": 1.0,
                    "note": "not-a-pitfall",
                },
            ],
        }
        (tmp_repo / "knowledge" / "graph").mkdir(parents=True, exist_ok=True)
        (tmp_repo / "knowledge" / "graph" / "local_state.yaml").write_text(
            _yaml.dump(overlay)
        )

        hits = _tool_get_pitfalls(tmp_repo, ["node-a"])
        assert len(hits) == 1
        assert hits[0]["from"] == "node-a"
        assert hits[0]["source_id"] == "task-1"

        # Non-matching node filter returns empty list (not an error).
        assert _tool_get_pitfalls(tmp_repo, ["node-z"]) == []
