"""akms.orchestrator.qmd_shell — shared qmd subprocess helper.

Single implementation of the ``bash seed/qmd/run_qmd.sh <subcmd> <query>``
shell-out, used by both the MCP server (``mcp_tools.create_mcp_server``)
and the Codex function-tool registry (``agents/base_codex.py``).

Previously each caller had its own closure copy of this logic. Factoring
it out is what lets the Codex agent offer parity with the Claude agent's
MCP-backed search surface (PR#18 C2 / PR18-T2).
"""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
from pathlib import Path

from akms._resources import seed_qmd_path

logger = logging.getLogger(__name__)


def run_qmd(
    subcmd: str,
    query: str,
    *,
    repo_root: str | Path,
    timeout: float = 30.0,
) -> list[dict]:
    """Invoke ``run_qmd.sh <subcmd> <query>`` and return parsed hits.

    The wrapper prints either qmd's JSON-per-line output (when the binary
    is installed and the collection exists) or a grep file-path list as
    fallback. Both shapes collapse to a uniform list of
    ``{"path": str, "line": int, "snippet": str}`` dicts sorted by
    ``(path, line)`` for deterministic downstream consumption.

    Returns an empty list (never raises) when:
      - ``run_qmd.sh`` can't be located on disk
      - the subprocess invocation itself fails / times out

    Logs are emitted so failures remain observable.
    """
    repo = Path(repo_root)

    # Prefer a repo-local copy of the wrapper; fall back to the bundled
    # package-root copy. The helper never raises on missing files — the
    # caller gets an empty list.
    wrapper = seed_qmd_path(
        "run_qmd.sh",
        repo_root_candidates=[
            repo.parent / "Packages" / "AKMS",
            repo / "Packages" / "AKMS",
            repo.parents[0] if len(repo.parents) > 0 else repo,
            repo,
        ],
    )
    if not wrapper.exists():
        logger.warning("run_qmd.sh not found at %s — returning empty list", wrapper)
        return []

    cmd = ["bash", str(wrapper), subcmd, query]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except Exception as exc:
        logger.warning("run_qmd.sh %s failed: %s", shlex.join(cmd), exc)
        return []

    hits: list[dict] = []
    for line in (proc.stdout or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Skip the wrapper's prose headers / fallback notices.
        if stripped.startswith("===") or stripped.startswith("("):
            continue
        # qmd JSON rows (one-per-line): best-effort parse.
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                entry = json.loads(stripped)
                hits.append({
                    "path": str(entry.get("path", "")),
                    "line": int(entry.get("line", 0) or 0),
                    "snippet": str(entry.get("snippet", entry.get("content", ""))),
                })
                continue
            except Exception:
                pass
        # Grep-style file path (no line / snippet info).
        if "/" in stripped and "." in stripped:
            hits.append({"path": stripped, "line": 0, "snippet": ""})

    hits.sort(key=lambda h: (h["path"], h["line"]))
    return hits
