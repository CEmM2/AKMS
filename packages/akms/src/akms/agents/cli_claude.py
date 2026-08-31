"""AKMS Claude Code CLI runtime backend (``claude -p``, headless).

Drives a subagent through the Claude Code CLI binary instead of the Claude
Agent SDK. The ``claude`` binary is a **runtime** dependency discovered on PATH
(not a pip dependency), so this backend works on machines that have Claude Code
installed but not ``claude-agent-sdk`` (e.g. CI boxes). It preserves the sealed
AKMS protocol: only ``execute()`` is overridden, and the headless agent writes
its AgentMemory file per the system prompt, which ``AKMSAgent.run()`` validates.

Search parity (FR-C05/FR-Q05): the qmd-backed ``mcp__akms__akms_*`` tools are
wired via ``claude --mcp-config`` pointing at ``akms.orchestrator.mcp_stdio``.

Select with::

    akms orchestrate ... --backend claude-cli
    # equivalently: --agent akms.agents.cli_claude.AKMSClaudeCliAgent
"""

from __future__ import annotations

from akms.agents._cli_common import akms_mcp_config_json, find_binary, run_cli
from akms.agents.base import AKMSAgent, Loadout


class AKMSClaudeCliAgent(AKMSAgent):
    """Run the task with ``claude -p`` (Claude Code headless).

    Overrides only ``execute()``; ``run()`` remains the sealed protocol owner.
    ``--model`` is passed only when a model is explicitly provided; otherwise the
    ``claude`` CLI uses its own configured default.
    """

    def __init__(self, config, repo_root, model=None):
        super().__init__(config, repo_root, model)
        # None → omit --model and let `claude` pick its default (don't inherit
        # the orchestrator's Claude config default as if it were explicit).
        self.explicit_model = model

    def preflight(self) -> str | None:
        """Report backend availability: this agent shells out to ``claude``."""
        import shutil

        if shutil.which("claude") is None:
            return (
                "The 'claude' binary (Claude Code CLI) is not on PATH. This backend "
                "drives it directly and needs no Python SDK — install the "
                "Claude Code CLI and ensure 'claude' resolves on PATH."
            )
        return None

    async def execute(
        self,
        task_json: dict,
        loadout: Loadout,
        system_prompt: str,
    ) -> None:
        tools = self._resolve_allowed_tools(task_json)
        prompt = self._build_task_prompt(task_json)

        cmd = [
            find_binary("claude"),
            "-p",
            prompt,
            "--append-system-prompt",
            system_prompt,
            "--permission-mode",
            "acceptEdits",
        ]
        if self.explicit_model:
            cmd += ["--model", self.explicit_model]
        cmd += ["--mcp-config", akms_mcp_config_json(self.repo_root)]
        if tools:
            cmd += ["--allowedTools", *tools]

        await run_cli(cmd, cwd=self.repo_root)
