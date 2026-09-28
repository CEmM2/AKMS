"""Stdio entrypoint for the AKMS MCP tool server.

Lets external CLI agent backends (e.g. ``claude --mcp-config``) reach the same
qmd-backed ``mcp__akms__akms_*`` search/graph tools that the in-process SDK
server exposes, preserving the FR-C05/FR-Q05 search surface for CLI runtimes.

Run::

    python -m akms.orchestrator.mcp_stdio --repo-root <path> [--global-vault <path>]
"""

from __future__ import annotations

import argparse
import sys


# The console script is installed with the core package, but the server needs
# the `mcp` extra. Only a missing `mcp` is turned into an install hint; any
# other import failure is a real bug and propagates.
try:
    from akms.orchestrator.mcp_tools import build_fastmcp_app
except ModuleNotFoundError as exc:
    if (exc.name or "").split(".")[0] != "mcp":
        raise
    build_fastmcp_app = None


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="akms-mcp-stdio",
        description="Serve the AKMS MCP graph/search tools over stdio.",
    )
    parser.add_argument("--repo-root", required=True, help="Repository root path")
    parser.add_argument(
        "--global-vault", default=None, help="Override global vault path"
    )
    args = parser.parse_args()

    if build_fastmcp_app is None:
        sys.exit(
            "akms-mcp-stdio needs the MCP server dependencies. "
            'Install them with: pip install "akms[mcp]"'
        )
    app = build_fastmcp_app(args.repo_root, args.global_vault)
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
