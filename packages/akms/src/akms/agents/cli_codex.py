"""AKMS Codex CLI runtime backend (``codex exec``, non-interactive).

Drives a subagent through the Codex CLI binary instead of the OpenAI Agents SDK.
The ``codex`` binary is a **runtime** dependency discovered on PATH (not a pip
dependency), mirroring ``cli_claude``. Only ``execute()`` is overridden; the
Codex agent writes its AgentMemory file per the system prompt, which the sealed
``AKMSAgent.run()`` validates.

Notes / version assumptions (Codex CLI ``codex exec``):
- ``codex exec`` has no dedicated system-prompt flag, so the assembled AKMS system
  prompt (which carries the AgentMemory write contract) is **prepended** to the
  task prompt.
- Headless writes use ``--sandbox workspace-write`` + ``-c approval_policy="never"``
  (codex exec has no --ask-for-approval flag) plus ``--skip-git-repo-check``.
  Tools are Codex's built-in file/shell surface.
- qmd search parity (FR-C05/FR-Q05) is wired **best-effort** via ``-c`` config
  overrides pointing Codex at the AKMS stdio MCP server. This depends on the
  installed Codex version's config schema; if unsupported, Codex still runs with
  its built-in tools and the search tools are simply unavailable.

Select with::

    akms orchestrate ... --backend codex-cli
    # equivalently: --agent akms.agents.cli_codex.AKMSCodexCliAgent
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from akms.agents._cli_common import find_binary, run_cli
from akms.agents.base import AKMSAgent, Loadout


def _codex_mcp_overrides(repo_root: str | Path) -> list[str]:
    """Best-effort ``-c`` config overrides wiring the AKMS stdio MCP server.

    Mirrors ``akms_mcp_config_json`` but in Codex's ``-c key=value`` form (the
    value is parsed as JSON by Codex), so the CLI backend can reach the same
    ``mcp__akms__akms_*`` tools as the SDK backends where the Codex version
    supports MCP servers.
    """
    args = json.dumps(["-m", "akms.orchestrator.mcp_stdio", "--repo-root", str(repo_root)])
    return [
        "-c",
        f"mcp_servers.akms.command={json.dumps(sys.executable)}",
        "-c",
        f"mcp_servers.akms.args={args}",
    ]


class AKMSCodexCliAgent(AKMSAgent):
    """Run the task with ``codex exec`` (Codex CLI, non-interactive).

    Overrides only ``execute()``; ``run()`` remains the sealed protocol owner.
    ``--model`` is passed only when a model is explicitly provided; otherwise
    ``codex`` uses its own configured default.
    """

    def __init__(self, config, repo_root, model=None):
        super().__init__(config, repo_root, model)
        # None → omit --model and let `codex` pick its default (don't inherit
        # the orchestrator's Claude config default as if it were explicit).
        self.explicit_model = model

    def preflight(self) -> str | None:
        """Report backend availability: this agent shells out to ``codex``."""
        import shutil

        if shutil.which("codex") is None:
            return (
                "The 'codex' binary (Codex CLI) is not on PATH. This backend "
                "drives it directly and needs no Python SDK — install the "
                "Codex CLI and ensure 'codex' resolves on PATH."
            )
        return None

    async def execute(
        self,
        task_json: dict,
        loadout: Loadout,
        system_prompt: str,
    ) -> None:
        task_prompt = self._build_task_prompt(task_json)
        # codex exec has no system-prompt flag → prepend it (carries the
        # AgentMemory write contract).
        full_prompt = f"{system_prompt}\n\n---\n\n{task_prompt}"

        cmd = [find_binary("codex"), "exec"]
        if self.explicit_model:
            cmd += ["--model", self.explicit_model]
        cmd += [
            "--cd",
            str(self.repo_root),
            "--sandbox",
            "workspace-write",
            "-c",
            'approval_policy="never"',
            "--skip-git-repo-check",
            *_codex_mcp_overrides(self.repo_root),
            full_prompt,
        ]

        await run_cli(cmd, cwd=self.repo_root)
