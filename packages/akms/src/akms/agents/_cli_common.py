"""Shared helpers for CLI-based AKMS agent backends (``claude -p``, ``codex exec``).

External CLI binaries are **runtime** dependencies discovered on PATH at call
time — never import-time — mirroring the ``nlm`` CLI convention used in
``akms-nodes-gen``. A missing binary surfaces as a clear ``RuntimeError`` from
inside ``execute()``, which ``AKMSAgent.run()`` maps to a ``status: failed``
AgentMemory. The agent process itself writes its AgentMemory file per the system
prompt; these helpers never parse stdout for the result.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def find_binary(name: str) -> str:
    """Return the absolute path to an executable, or raise a clear error."""
    path = shutil.which(name)
    if not path:
        raise RuntimeError(
            f"The '{name}' CLI was not found on PATH. Install it (and ensure "
            f"'{name}' is runnable), or select a different --backend."
        )
    return path


def akms_mcp_config_json(repo_root: str | Path) -> str:
    """Build the ``claude --mcp-config`` JSON wiring the AKMS stdio MCP server.

    Spawns ``python -m akms.orchestrator.mcp_stdio --repo-root <root>`` so the
    headless agent gets the same ``mcp__akms__akms_*`` tools as the SDK backend.
    """
    return json.dumps(
        {
            "mcpServers": {
                "akms": {
                    "command": sys.executable,
                    "args": [
                        "-m",
                        "akms.orchestrator.mcp_stdio",
                        "--repo-root",
                        str(repo_root),
                    ],
                }
            }
        }
    )


async def run_cli(cmd: list[str], cwd: str | Path) -> None:
    """Run an external agent CLI to completion in ``cwd``.

    Streams stderr to the logger and raises ``RuntimeError`` on a non-zero exit.
    The agent writes AgentMemory to disk itself; this does not parse stdout.
    """
    logger.info("Running agent CLI: %s (cwd=%s)", cmd[0], cwd)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await proc.communicate()
    err_text = stderr.decode("utf-8", "replace").strip() if stderr else ""
    if err_text:
        logger.debug("%s stderr: %s", cmd[0], err_text)
    if proc.returncode != 0:
        raise RuntimeError(
            f"agent CLI '{cmd[0]}' exited with code {proc.returncode}: {err_text}"
        )
