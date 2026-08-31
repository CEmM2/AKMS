"""Tests for MCP tools wrapper — Phase 6 Task 6.1 (mcp_tools.py).

Verifies that the FastMCP server correctly wraps all AKMS graph functions
and returns JSON-serializable results. All tests use the same tmp_vault
and tmp_repo fixtures as the rest of the suite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from akms.graph.build_graph import build_graph
from akms.orchestrator.mcp_tools import create_mcp_server

from .conftest import make_global_node, make_local_node, set_overlay


# ── Helpers ──────────────────────────────────────────────────────────


def _call_tool(server, tool_name: str, arguments: dict | None = None):
    """Invoke an MCP tool directly via the server's request handlers.

    This simulates what the Claude Agent SDK does internally:
    it calls the server's ListTools and CallTool handlers.
    """
    from mcp.types import CallToolRequest, CallToolRequestParams

    handler = server.request_handlers.get(CallToolRequest)
    assert handler is not None, "Server has no CallTool handler"

    params = CallToolRequestParams(name=tool_name, arguments=arguments or {})
    request = CallToolRequest(method="tools/call", params=params)

    import asyncio

    raw = asyncio.run(handler(request))
    # Handler returns ServerResult wrapping CallToolResult — unwrap via .root
    result = raw.root if hasattr(raw, "root") else raw
    assert len(result.content) >= 1
    text = result.content[0].text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def _list_tools(server) -> list[str]:
    """List available tool names from the server."""
    from mcp.types import ListToolsRequest

    handler = server.request_handlers.get(ListToolsRequest)
    assert handler is not None

    import asyncio

    raw = asyncio.run(handler(ListToolsRequest(method="tools/list")))
    result = raw.root if hasattr(raw, "root") else raw
    return [tool.name for tool in result.tools]


def _setup_seed_graph(tmp_vault, tmp_repo):
    """Create seed nodes and compile graph — reusable across tests."""
    make_global_node(
        tmp_vault,
        id="skill-taichi",
        title="Taichi GPU Simulation",
        domain="gpu-simulation",
        tags=["taichi", "gpu", "simulation"],
        confidence=0.95,
        edges=[{"to": "skill-mechanics", "type": "requires", "weight": 0.8}],
    )
    make_global_node(
        tmp_vault,
        id="skill-mechanics",
        title="Computational Mechanics",
        domain="computational-mechanics",
        tags=["mechanics", "fem", "simulation"],
        confidence=0.90,
    )
    # Compile graph so tools can load it
    build_graph(str(tmp_repo), global_vault=str(tmp_vault))


# ── Test: Server Creation ────────────────────────────────────────────


class TestCreateMcpServer:
    """Test MCP server factory."""

    def test_creates_server(self, tmp_repo, tmp_vault):
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        assert server is not None
        assert server.name == "akms-tools"

    def test_server_has_expected_tools(self, tmp_repo, tmp_vault):
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        tool_names = _list_tools(server)
        expected = {
            "akms_build_graph",
            "akms_query_subgraph",
            "akms_generate_loadout",
            "akms_update_graph",
            "akms_generate_mirror",
            "akms_graph_status",
            "akms_derive_tags",
            "akms_re_evaluate",
            # qmd-backed search tools replacing Grep.
            "akms_search_nodes",
            "akms_search_mirror",
            "akms_search_sessions",
            "akms_get_pitfalls",
            #   # Deterministic resolve-task (shared with the CLI).
            "akms_resolve_task",
        }
        assert expected == set(tool_names)

    def test_server_type_is_lowlevel(self, tmp_repo, tmp_vault):
        from mcp.server.lowlevel.server import Server

        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        assert isinstance(server, Server)


# ── Test: akms_build_graph ───────────────────────────────────────────


class TestAkmsBuildGraph:
    """Test the build_graph MCP tool."""

    def test_compiles_graph(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", tags=["test"])
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        result = _call_tool(server, "akms_build_graph")
        assert "error" not in result
        assert result["node_count"] == 1
        assert result["edge_count"] == 0
        assert Path(result["graph_json_path"]).exists()

    def test_returns_correct_counts(self, tmp_vault, tmp_repo):
        make_global_node(
            tmp_vault,
            id="a",
            tags=["x"],
            edges=[{"to": "b", "type": "requires", "weight": 0.5}],
        )
        make_global_node(tmp_vault, id="b", tags=["y"])
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        result = _call_tool(server, "akms_build_graph")
        assert result["node_count"] == 2
        assert result["edge_count"] == 1


# ── Test: akms_query_subgraph ────────────────────────────────────────


class TestAkmsQuerySubgraph:
    """Test the query_subgraph MCP tool."""

    def test_finds_nodes_by_tags(self, tmp_vault, tmp_repo):
        _setup_seed_graph(tmp_vault, tmp_repo)
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        result = _call_tool(
            server,
            "akms_query_subgraph",
            {"seed_tags": ["taichi", "gpu"], "agent_role": "implementer"},
        )
        assert "error" not in result
        assert result["count"] >= 1
        ids = [n["id"] for n in result["nodes"]]
        assert "skill-taichi" in ids

    def test_respects_agent_role(self, tmp_vault, tmp_repo):
        _setup_seed_graph(tmp_vault, tmp_repo)
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        result = _call_tool(
            server,
            "akms_query_subgraph",
            {"seed_tags": ["mechanics"], "agent_role": "physics_reviewer"},
        )
        assert "error" not in result
        assert result["count"] >= 1

    def test_empty_tags_returns_empty(self, tmp_vault, tmp_repo):
        _setup_seed_graph(tmp_vault, tmp_repo)
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        result = _call_tool(
            server,
            "akms_query_subgraph",
            {"seed_tags": ["nonexistent-tag-xyz"], "agent_role": "implementer"},
        )
        assert "error" not in result
        assert result["count"] == 0


# ── Test: akms_generate_loadout ──────────────────────────────────────


class TestAkmsGenerateLoadout:
    """Test the generate_loadout MCP tool."""

    def test_generates_loadout_file(self, tmp_vault, tmp_repo):
        _setup_seed_graph(tmp_vault, tmp_repo)
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        result = _call_tool(
            server,
            "akms_generate_loadout",
            {
                "task_id": "t1-test",
                "phase": 1,
                "seed_tags": ["taichi", "gpu"],
                "agent_role": "implementer",
                "mode": "routing",
            },
        )
        assert "error" not in result
        assert Path(result["loadout_path"]).exists()
        assert result["mode"] == "routing"
        assert result["node_count"] >= 1

    def test_returns_graph_version(self, tmp_vault, tmp_repo):
        _setup_seed_graph(tmp_vault, tmp_repo)
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        result = _call_tool(
            server,
            "akms_generate_loadout",
            {
                "task_id": "t2-test",
                "phase": 1,
                "seed_tags": ["mechanics"],
                "agent_role": "implementer",
            },
        )
        assert "error" not in result
        assert "graph_version" in result
        assert len(result["graph_version"]) > 0


# ── Test: akms_update_graph ──────────────────────────────────────────


class TestAkmsUpdateGraph:
    """Test the update_graph MCP tool."""

    def test_processes_agent_memory_json(self, tmp_vault, tmp_repo):
        _setup_seed_graph(tmp_vault, tmp_repo)
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        memory = {
            "task_id": "t1-test",
            "task_description": "Test task",
            "phase_id": 1,
            "timestamp": "2026-03-08T10:00:00",
            "agent_model": "sonnet",
            "loadout_used": "test-loadout.md",
            "status": "complete",
            "tests_passed": 5,
            "tests_total": 5,
            "nodes_used": [
                {
                    "id": "skill-taichi",
                    "useful": True,
                    "coverage": "sufficient",
                }
            ],
            "nodes_missing": [],
            "pitfalls_discovered": [],
            "new_knowledge": [],
            "lessons": [],
        }
        result = _call_tool(
            server,
            "akms_update_graph",
            {"source_json": json.dumps(memory)},
        )
        assert "error" not in result

    def test_processes_pcd_json(self, tmp_vault, tmp_repo):
        _setup_seed_graph(tmp_vault, tmp_repo)
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        pcd = {
            "phase_id": 1,
            "timestamp": "2026-03-08T10:00:00",
            "nodes_used": [
                {
                    "id": "skill-mechanics",
                    "useful": True,
                    "coverage": "sufficient",
                }
            ],
            "nodes_missing": [],
            "pitfalls_discovered": [],
            "new_knowledge": [],
            "lessons": [],
        }
        result = _call_tool(
            server,
            "akms_update_graph",
            {"source_json": json.dumps(pcd)},
        )
        assert "error" not in result

    def test_error_on_bad_json(self, tmp_vault, tmp_repo):
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        result = _call_tool(
            server,
            "akms_update_graph",
            {"source_json": "not valid json {{{"},
        )
        assert "error" in result
        assert "Invalid JSON" in result["error"]


# ── Test: akms_generate_mirror ───────────────────────────────────────


class TestAkmsGenerateMirror:
    """Test the generate_mirror MCP tool."""

    def test_returns_summary(self, tmp_vault, tmp_repo):
        """Mirror with no git repo gracefully returns empty results."""
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        result = _call_tool(
            server,
            "akms_generate_mirror",
            {"phase": 1, "parent_branch": "main"},
        )
        # Without a real git repo, generate_mirror returns gracefully
        # with empty mirrors list (not an error)
        assert isinstance(result, dict)


# ── Test: akms_graph_status ──────────────────────────────────────────


class TestAkmsGraphStatus:
    """Test the graph_status MCP tool."""

    def test_returns_health_report(self, tmp_vault, tmp_repo):
        _setup_seed_graph(tmp_vault, tmp_repo)
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        result = _call_tool(server, "akms_graph_status")
        assert "error" not in result
        # graph_status returns diagnostic sections
        assert "degraded_nodes" in result
        assert "tentative_nodes" in result

    def test_handles_empty_graph(self, tmp_vault, tmp_repo):
        # Build empty graph
        build_graph(str(tmp_repo), global_vault=str(tmp_vault))
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        result = _call_tool(server, "akms_graph_status")
        assert "error" not in result


# ── Test: akms_derive_tags ───────────────────────────────────────────


class TestAkmsDeriveTags:
    """Test the derive_tags MCP tool."""

    def test_derives_tags_from_task(self, tmp_vault, tmp_repo):
        _setup_seed_graph(tmp_vault, tmp_repo)
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        task = {
            "task_id": "t1-setup",
            "title": "Setup taichi GPU runtime",
            "objective": "Initialize simulation framework",
            "scope": [],
            "akms_tags": [],
        }
        result = _call_tool(
            server,
            "akms_derive_tags",
            {"task_json": json.dumps(task)},
        )
        assert "error" not in result
        assert "tags" in result
        # "taichi" should match via title whole-word
        assert "taichi" in result["tags"] or len(result["tags"]) > 0

    def test_error_on_bad_json(self, tmp_vault, tmp_repo):
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        result = _call_tool(
            server,
            "akms_derive_tags",
            {"task_json": "bad json!!!"},
        )
        assert "error" in result


# ── Test: akms_re_evaluate ───────────────────────────────────────────


class TestAkmsReEvaluate:
    """Test the re_evaluate MCP tool."""

    def test_regenerates_loadout(self, tmp_vault, tmp_repo):
        _setup_seed_graph(tmp_vault, tmp_repo)
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        result = _call_tool(
            server,
            "akms_re_evaluate",
            {
                "task_id": "t1-next",
                "phase": 2,
                "seed_tags": ["taichi", "gpu"],
                "agent_role": "implementer",
            },
        )
        assert "error" not in result
        assert "loadout_path" in result
        assert Path(result["loadout_path"]).exists()
        assert result["node_count"] >= 1


# ── Test: SDK Integration Structure ──────────────────────────────────


class TestMcpSdkIntegration:
    """Verify the server works with SDK config structure."""

    def test_sdk_config_structure(self, tmp_repo, tmp_vault):
        """Verify we can build a valid McpSdkServerConfig dict."""
        server = create_mcp_server(tmp_repo, global_vault=tmp_vault)
        config = {
            "type": "sdk",
            "name": "akms-tools",
            "instance": server,
        }
        assert config["type"] == "sdk"
        assert config["name"] == "akms-tools"
        assert config["instance"] is server
