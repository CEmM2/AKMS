#!/usr/bin/env python3
"""Verify an AKMS setup end to end and report what is actually wired.

    python skills/akms/scripts/check_setup.py [--repo .]

Reports on: the package, the CLI, the MCP entry point, the global vault, the
project layout, the compiled graph, and qmd-backed search.

Deliberately distinguishes "absent" from "broken" from "present but empty",
because those need different fixes — and because an empty result from search is
NOT evidence that no knowledge exists.

Exit codes: 0 = usable, 1 = something required is missing.
"""

from __future__ import annotations

import argparse
import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

OK, WARN, BAD = "ok", "warn", "FAIL"
_MARK = {OK: "  [ok]  ", WARN: "  [warn]", BAD: "  [FAIL]"}

results: list[tuple[str, str]] = []


def report(state: str, msg: str) -> None:
    results.append((state, msg))
    print(f"{_MARK[state]} {msg}")


def check_package() -> bool:
    try:
        import akms  # noqa: F401
    except Exception as exc:
        report(BAD, f"cannot import akms: {type(exc).__name__}: {exc}")
        report(BAD, "  fix: uv pip install akms")
        return False
    try:
        from importlib.metadata import version
        report(OK, f"akms package importable (version {version('akms')})")
    except Exception:
        report(OK, "akms package importable (version unknown)")
    return True


def check_cli() -> None:
    path = shutil.which("akms")
    if path:
        report(OK, f"`akms` CLI on PATH: {path}")
    else:
        report(WARN, "`akms` not on PATH — call it via `uv run akms` / `python -m`")


def check_mcp() -> None:
    path = shutil.which("akms-mcp-stdio")
    if path:
        report(OK, f"`akms-mcp-stdio` on PATH: {path}")
    else:
        report(WARN, "`akms-mcp-stdio` not on PATH — use "
                     "`python -m akms.orchestrator.mcp_stdio --repo-root .`")
    try:
        importlib.import_module("akms.orchestrator.mcp_stdio")
        report(OK, "MCP stdio module importable")
    except Exception as exc:
        report(BAD, f"MCP stdio module import failed: {type(exc).__name__}: {exc}")
        return
    try:
        importlib.import_module("mcp")
        from importlib.metadata import version
        report(OK, f"mcp runtime present (version {version('mcp')}, transitive dep)")
    except Exception:
        report(BAD, "mcp runtime missing — pin `mcp` explicitly if you trimmed deps")


def check_vault() -> None:
    env = os.environ.get("AKMS_GLOBAL_VAULT")
    vault = Path(env).expanduser() if env else Path.home() / ".claude" / "akms" / "nodes"
    src = "AKMS_GLOBAL_VAULT" if env else "default"
    if not vault.exists():
        report(WARN, f"global vault absent at {vault} ({src}) — "
                     "project-local knowledge only, which is a valid setup")
        return
    count = len(list(vault.rglob("*.md")))
    if count == 0:
        report(WARN, f"global vault at {vault} exists but holds no .md nodes")
    else:
        report(OK, f"global vault: {vault} ({count} node file(s), read-only)")


def check_layout(repo: Path) -> None:
    local = repo / "knowledge" / "local-nodes"
    if not local.exists():
        report(WARN, f"{local.relative_to(repo)} missing — run akms_bootstrap.sh")
        return
    nodes = list(local.glob("*.md"))
    if not nodes:
        report(WARN, f"{local.relative_to(repo)} exists but is empty — "
                     "no project knowledge yet; queries will return nothing")
    else:
        report(OK, f"local nodes: {len(nodes)} in {local.relative_to(repo)}")


def check_graph(repo: Path) -> None:
    graph = repo / "knowledge" / "graph" / "graph.json"
    if not graph.exists():
        report(WARN, "graph.json not compiled yet — run `akms status --repo .`")
        return
    try:
        import json
        data = json.loads(graph.read_text())
        n = len(data.get("nodes", []))
        report(OK if n else WARN, f"graph compiled: {n} node(s)")
    except Exception as exc:
        report(BAD, f"graph.json unreadable: {type(exc).__name__}: {exc}")


def check_qmd(repo: Path) -> None:
    """qmd powers the three akms_search_* tools; absence is silent by design."""
    try:
        from akms._resources import seed_qmd_path
        wrapper = seed_qmd_path("run_qmd.sh")
        has_wrapper = wrapper.exists()
    except Exception as exc:
        report(BAD, f"could not resolve run_qmd.sh: {type(exc).__name__}: {exc}")
        return

    binary = shutil.which("qmd")
    if has_wrapper and binary:
        report(OK, f"qmd search wired (wrapper bundled, binary at {binary})")
    elif has_wrapper and not binary:
        report(WARN, "run_qmd.sh is bundled but the `qmd` binary is not on PATH — "
                     "the wrapper falls back to grep-style matching, so results "
                     "will be poorer but not empty")
    else:
        report(BAD, f"run_qmd.sh not found at {wrapper} — akms_search_* will "
                    "return EMPTY LISTS, not errors. An empty search result "
                    "then does NOT mean the knowledge is absent.")


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify an AKMS setup.")
    ap.add_argument("--repo", "-r", default=".", help="Repository root (default: cwd)")
    args = ap.parse_args()
    repo = Path(args.repo).resolve()

    print(f"AKMS setup check — {repo}\n")

    print("package")
    if not check_package():
        print("\nresult: NOT USABLE — install the package first.")
        return 1
    check_cli()

    print("\nmcp")
    check_mcp()

    print("\nknowledge sources")
    check_vault()
    check_layout(repo)
    check_graph(repo)

    print("\nsearch")
    check_qmd(repo)

    fails = [m for s, m in results if s == BAD]
    warns = [m for s, m in results if s == WARN]
    print(f"\n{'-' * 58}")
    print(f"ok: {sum(1 for s, _ in results if s == OK)}   "
          f"warnings: {len(warns)}   failures: {len(fails)}")
    if fails:
        print("\nresult: NOT USABLE")
        return 1
    print("\nresult: usable" + (" (with warnings above)" if warns else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
