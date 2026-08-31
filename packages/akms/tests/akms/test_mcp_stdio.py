"""Tests for the AKMS MCP stdio entrypoint and the build_fastmcp_app refactor.

The stdio entrypoint (``akms.orchestrator.mcp_stdio``) lets external CLI agent
backends reach the same qmd-backed tools. ``create_mcp_server`` must keep its
contract (returns the lowlevel ``Server`` for in-process SDK consumption).
"""

from __future__ import annotations

import asyncio

import pytest

from akms.orchestrator.mcp_tools import build_fastmcp_app, create_mcp_server


@pytest.mark.unit
def test_build_fastmcp_app_returns_fastmcp(tmp_repo):
    from mcp.server.fastmcp import FastMCP

    app = build_fastmcp_app(tmp_repo)
    assert isinstance(app, FastMCP)


@pytest.mark.unit
def test_create_mcp_server_contract_preserved(tmp_repo):
    """create_mcp_server still returns the lowlevel Server (SDK consumption)."""
    server = create_mcp_server(tmp_repo)
    assert server is not None
    assert server.__class__.__name__ == "Server"


@pytest.mark.unit
def test_fastmcp_app_exposes_akms_tools(tmp_repo):
    """The stdio app exposes the full AKMS tool surface, incl. qmd search."""
    app = build_fastmcp_app(tmp_repo)
    tools = asyncio.run(app.list_tools())
    names = {t.name for t in tools}

    # All four qmd-backed search tools must be present for CLI search parity.
    assert {
        "akms_search_nodes",
        "akms_search_mirror",
        "akms_search_sessions",
        "akms_get_pitfalls",
    } <= names
    # Plus the graph tools (12 total today).
    assert len(names) >= 12


@pytest.mark.unit
def test_mcp_stdio_main_requires_repo_root(monkeypatch):
    """The stdio CLI requires --repo-root (argparse errors without it)."""
    import akms.orchestrator.mcp_stdio as mcp_stdio

    monkeypatch.setattr("sys.argv", ["akms-mcp-stdio"])
    with pytest.raises(SystemExit):
        mcp_stdio.main()


@pytest.mark.unit
def test_mcp_stdio_main_serves_built_app(tmp_repo, monkeypatch):
    """main() builds the app for the given repo and serves it over stdio."""
    import akms.orchestrator.mcp_stdio as mcp_stdio

    captured = {}

    class _FakeApp:
        def run(self, transport):
            captured["transport"] = transport

    def fake_build(repo_root, global_vault=None):
        captured["repo_root"] = repo_root
        return _FakeApp()

    monkeypatch.setattr(mcp_stdio, "build_fastmcp_app", fake_build)
    monkeypatch.setattr("sys.argv", ["akms-mcp-stdio", "--repo-root", str(tmp_repo)])

    mcp_stdio.main()

    assert captured["transport"] == "stdio"
    assert str(captured["repo_root"]) == str(tmp_repo)
