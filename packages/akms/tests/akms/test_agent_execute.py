"""Tests for AKMSAgent.execute — SDK wiring.

PR18-T1: `ClaudeAgentOptions` must register the AKMS MCP server so the
MCP-backed search tools (`mcp__akms__akms_search_*`) that
`TOOL_NAME_MAP` resolves to are actually reachable by the agent. Without
this wiring the logical `search` / `search_mirror` tools would expand
into tool names that `claude-agent-sdk` cannot dispatch.
"""

from __future__ import annotations

import asyncio
import types


from akms.agents.base import AKMSAgent, Loadout
from akms.schema.models import PropagationConfig


class _StubAgent(AKMSAgent):
    """Minimal AKMSAgent subclass that inherits the default execute path."""


def _make_loadout() -> Loadout:
    return Loadout(path="", task_id="t-1", phase=1)


def _stub_claude_agent_sdk(captured: dict):
    """Build a fake ``claude_agent_sdk`` module that records
    ``ClaudeAgentOptions`` kwargs and drives a single ``ResultMessage``."""

    class FakeOptions:
        def __init__(self, **kwargs):
            captured["options_kwargs"] = kwargs
            for k, v in kwargs.items():
                setattr(self, k, v)

    class FakeResultMessage:
        def __init__(self, *, is_error: bool, result: str):
            self.is_error = is_error
            self.result = result

    async def fake_query(*, prompt, options):
        captured["prompt"] = prompt
        captured["options"] = options
        yield FakeResultMessage(is_error=False, result="ok")

    mod = types.ModuleType("claude_agent_sdk")
    mod.ClaudeAgentOptions = FakeOptions
    mod.ResultMessage = FakeResultMessage
    mod.query = fake_query
    return mod


class TestExecuteMcpRegistration:
    def test_mcp_server_registered_on_claude_agent_options(
        self,
        tmp_path,
        monkeypatch,
    ):
        """Default `execute` must register the AKMS MCP server so the tools
        in `TOOL_NAME_MAP['search']` / `['search_mirror']` are reachable."""
        # Build a minimal repo root (create_mcp_server only needs it to
        # exist + optionally have propagation_config.yaml).
        repo = tmp_path / "repo"
        (repo / "knowledge" / "graph").mkdir(parents=True)

        agent = _StubAgent(
            config=PropagationConfig(),
            repo_root=repo,
            model="claude-sonnet-4-6",
        )

        captured: dict = {}
        fake_sdk = _stub_claude_agent_sdk(captured)
        monkeypatch.setitem(__import__("sys").modules, "claude_agent_sdk", fake_sdk)

        task_json = {
            "task_id": "t-1",
            "title": "search task",
            "objective": "search",
            "task_description": "",
            "phase_id": 1,
            "tools": ["search"],  # expands to mcp__akms__akms_search_* names
            "akms_schema": "v2",
        }

        asyncio.run(agent.execute(task_json, _make_loadout(), system_prompt="sys"))

        assert "options_kwargs" in captured, (
            "execute() did not build ClaudeAgentOptions"
        )
        opts = captured["options_kwargs"]
        assert "mcp_servers" in opts, (
            "ClaudeAgentOptions was constructed without mcp_servers — the "
            "agent cannot dispatch mcp__akms__* tools (PR#18 C1)."
        )
        servers = opts["mcp_servers"]
        assert "akms" in servers, "akms MCP server not registered under key 'akms'"
        entry = servers["akms"]
        assert entry.get("type") == "sdk"
        assert entry.get("instance") is not None, "akms server instance missing"

        # Sanity: allowed_tools contains at least one mcp__akms__ entry so the
        # registration has concrete consumers (otherwise the test passes
        # vacuously).
        assert any(
            isinstance(t, str) and t.startswith("mcp__akms__")
            for t in opts.get("allowed_tools", [])
        ), (
            "No mcp__akms__* tool made it into allowed_tools — MCP wiring "
            "covers a surface that isn't used."
        )
