"""Tests for deterministic resolve-task CLI / service.

Covers:
  - Shared service happy path (loadout + manifest)
  - CLI subprocess pure-JSON stdout
  - Explicit changed-paths sequence validation
  - Invalid inputs fail before artifacts are accepted
  - No LLM / network on the resolve path
  - MCP tool shares the same service contract
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from akms.cli.commands import main
from akms.graph.build_graph import build_graph
from akms.schema.models import AgentRole
from akms.task_context.manifest import load_resolution_manifest
from akms.task_context.resolve_task_service import (
    ResolveTaskError,
    load_changed_paths_manifest,
    resolve_task,
)
from tests.akms.conftest import make_global_node, make_mirror_node


def _write_task(path: Path, **overrides) -> Path:
    task = {
        "task_id": "TSK-001",
        "phase": 1,
        "title": "Resolve required knowledge",
        "objective": "Prove deterministic resolve-task.",
        "scope": ["src/solver.py"],
        "deliverables": ["src/solver.py"],
        "akms_tags": ["solver"],
        "implementation_steps": ["Load routes", "Write loadout"],
        "symbols": [],
    }
    task.update(overrides)
    path.write_text(json.dumps(task, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_routes(path: Path, *, node_id: str = "lesson-solver") -> Path:
    payload = {
        "schema_version": "v1",
        "source_hash": "sha256:fixture-routes",
        "by_path": {
            "src/solver.py": [
                {
                    "node_id": node_id,
                    "reason": "Exact route for solver implementation",
                    "provenance": "tests/fixture",
                }
            ]
        },
        "by_symbol": {},
    }
    if path.suffix in {".yaml", ".yml"}:
        path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _prepare_repo(
    tmp_vault: Path, tmp_repo: Path, *, node_id: str = "lesson-solver"
) -> None:
    make_global_node(
        tmp_vault,
        id=node_id,
        tags=["solver", "failure"],
        domain="computational-mechanics",
        content="# Solver lesson\n\n## Summary\n\nAlways check residuals.\n",
        status="established",
        confidence=0.95,
    )
    make_global_node(
        tmp_vault,
        id="advisory-solver",
        tags=["solver"],
        domain="computational-mechanics",
        content="# Advisory\n\n## Summary\n\nGeneral solver tips.\n",
        status="established",
        confidence=0.9,
    )
    make_mirror_node(
        tmp_repo,
        id="mirror-solver",
        title="Code Mirror: src/solver.py",
        source_file="src/solver.py",
        content_ref="code-mirror/mirror-solver.md",
    )
    build_graph(tmp_repo, global_vault=tmp_vault)


# ═══════════════════════════════════════════════════════════════════════
#  Service unit / integration
# ═══════════════════════════════════════════════════════════════════════


class TestResolveTaskService:
    def test_happy_path_writes_loadout_and_manifest(self, tmp_vault, tmp_repo):
        _prepare_repo(tmp_vault, tmp_repo)
        task_path = _write_task(tmp_repo / "task.json")
        routes_path = _write_routes(tmp_repo / "routes.json")

        result = resolve_task(
            repo_root=tmp_repo,
            task=task_path,
            route_index=routes_path,
            agent_role=AgentRole.IMPLEMENTER,
            mode="routing",
        )

        assert result.status == "ok", result.error
        assert result.fingerprint
        assert result.required_count >= 1
        assert result.loadout_path and Path(result.loadout_path).exists()
        assert result.manifest_path and Path(result.manifest_path).exists()

        loadout = Path(result.loadout_path).read_text(encoding="utf-8")
        assert "## Required Knowledge" in loadout
        assert "Exact route for solver implementation" in loadout
        assert f"resolution_fingerprint: {result.fingerprint}" in loadout or (
            result.fingerprint in loadout
        )

        manifest = load_resolution_manifest(result.manifest_path)
        assert manifest.fingerprint == result.fingerprint
        assert "lesson-solver" in {sel.node_id for sel in manifest.selected_nodes}

    def test_changed_paths_sequence_required(self, tmp_vault, tmp_repo):
        _prepare_repo(tmp_vault, tmp_repo)
        task_path = _write_task(tmp_repo / "task.json")
        routes_path = _write_routes(tmp_repo / "routes.json")

        #   # Bare string must be rejected (canonicalisation rule).
        result = resolve_task(
            repo_root=tmp_repo,
            task=task_path,
            route_index=routes_path,
            changed_paths="src/solver.py",  # type: ignore[arg-type]
        )
        assert result.status == "error"
        assert result.error_code == "invalid_changed_paths"
        assert not list((tmp_repo / "knowledge" / "loadouts").glob("*.md"))

        with pytest.raises(ResolveTaskError, match="sequence"):
            load_changed_paths_manifest("src/only.py")

        ok = resolve_task(
            repo_root=tmp_repo,
            task=task_path,
            route_index=routes_path,
            changed_paths=["src/solver.py"],
        )
        assert ok.status == "ok", ok.error
        assert "src/solver.py" in ok.changed_paths

    def test_invalid_task_json_fails_closed(self, tmp_vault, tmp_repo):
        _prepare_repo(tmp_vault, tmp_repo)
        routes_path = _write_routes(tmp_repo / "routes.json")
        bad = tmp_repo / "bad.json"
        bad.write_text("{not json", encoding="utf-8")

        result = resolve_task(
            repo_root=tmp_repo,
            task=bad,
            route_index=routes_path,
        )
        assert result.status == "error"
        assert result.error_code == "invalid_task_json"
        assert result.loadout_path is None

    def test_missing_required_node_fails_before_write(self, tmp_vault, tmp_repo):
        _prepare_repo(tmp_vault, tmp_repo)
        task_path = _write_task(tmp_repo / "task.json")
        # Route points at a node that is not in the graph.
        routes_path = _write_routes(tmp_repo / "routes.json", node_id="missing-node")

        result = resolve_task(
            repo_root=tmp_repo,
            task=task_path,
            route_index=routes_path,
        )
        assert result.status == "error"
        # Either route validation or required-unavailable — both fail closed.
        assert result.error_code in {
            "required_node_unavailable",
            "resolve_error",
        }
        assert result.error
        assert not list((tmp_repo / "knowledge" / "loadouts").glob("*-loadout.md"))

    def test_no_llm_or_network_on_resolve_path(self, tmp_vault, tmp_repo, monkeypatch):
        _prepare_repo(tmp_vault, tmp_repo)
        task_path = _write_task(tmp_repo / "task.json")
        routes_path = _write_routes(tmp_repo / "routes.json")

        def _boom_llm(*_a, **_k):
            raise AssertionError("call_llm must not be invoked during resolve_task")

        def _boom_urlopen(*_a, **_k):
            raise AssertionError(
                "network urlopen must not be invoked during resolve_task"
            )

        monkeypatch.setattr(
            "akms.orchestrator.llm_router.call_llm",
            _boom_llm,
            raising=False,
        )
        # urllib is the stdlib network surface most likely to appear.
        import urllib.request

        monkeypatch.setattr(urllib.request, "urlopen", _boom_urlopen)

        result = resolve_task(
            repo_root=tmp_repo,
            task=task_path,
            route_index=routes_path,
            agent_role="implementer",
        )
        assert result.status == "ok", result.error


# ═══════════════════════════════════════════════════════════════════════
#  CLI adapter
# ═══════════════════════════════════════════════════════════════════════


class TestResolveTaskCli:
    def test_cli_json_stdout(self, tmp_vault, tmp_repo, capsys):
        _prepare_repo(tmp_vault, tmp_repo)
        task_path = _write_task(tmp_repo / "task.json")
        routes_path = _write_routes(tmp_repo / "routes.yaml")

        code = main(
            [
                "--repo",
                str(tmp_repo),
                "resolve-task",
                "--task-json",
                str(task_path),
                "--routes",
                str(routes_path),
                "--role",
                "implementer",
            ]
        )
        captured = capsys.readouterr()
        assert code == 0, captured.out + captured.err
        # Stdout must be pure JSON (no leading log lines).
        payload = json.loads(captured.out)
        assert payload["status"] == "ok"
        assert payload["fingerprint"]
        assert payload["required_count"] >= 1
        assert Path(payload["loadout_path"]).exists()
        assert Path(payload["manifest_path"]).exists()

    def test_cli_subprocess_integration(self, tmp_vault, tmp_repo):
        _prepare_repo(tmp_vault, tmp_repo)
        task_path = _write_task(tmp_repo / "task.json")
        routes_path = _write_routes(tmp_repo / "routes.json")
        changed = tmp_repo / "changed.json"
        changed.write_text(
            json.dumps(["src/solver.py"]),
            encoding="utf-8",
        )

        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "akms.cli.commands",
                "--repo",
                str(tmp_repo),
                "resolve-task",
                "--task-json",
                str(task_path),
                "--routes",
                str(routes_path),
                "--changed-paths",
                str(changed),
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(tmp_repo),
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout
        # Ensure no human log lines precede JSON.
        stdout = proc.stdout.strip()
        assert stdout.startswith("{"), stdout[:200]
        payload = json.loads(stdout)
        assert payload["status"] == "ok"
        assert "src/solver.py" in payload["changed_paths"]

    def test_cli_rejects_invalid_role_via_argparse(self, tmp_vault, tmp_repo):
        _prepare_repo(tmp_vault, tmp_repo)
        task_path = _write_task(tmp_repo / "task.json")
        routes_path = _write_routes(tmp_repo / "routes.json")
        with pytest.raises(SystemExit):
            main(
                [
                    "--repo",
                    str(tmp_repo),
                    "resolve-task",
                    "--task-json",
                    str(task_path),
                    "--routes",
                    str(routes_path),
                    "--role",
                    "not-a-role",
                ]
            )


# ═══════════════════════════════════════════════════════════════════════
#  MCP contract
# ═══════════════════════════════════════════════════════════════════════


class TestResolveTaskMcp:
    def test_mcp_tool_present_and_matches_service(self, tmp_vault, tmp_repo):
        from akms.orchestrator.mcp_tools import create_mcp_server
        from tests.akms.test_mcp_tools import _call_tool

        _prepare_repo(tmp_vault, tmp_repo)
        task_path = _write_task(tmp_repo / "task.json")
        routes_path = _write_routes(tmp_repo / "routes.json")

        server = create_mcp_server(repo_root=tmp_repo, global_vault=tmp_vault)
        # Tool must be registered.
        from mcp.types import ListToolsRequest
        import asyncio

        list_handler = server.request_handlers.get(ListToolsRequest)
        assert list_handler is not None
        listed = asyncio.run(list_handler(ListToolsRequest()))
        names = {t.name for t in listed.root.tools}
        assert "akms_resolve_task" in names

        result = _call_tool(
            server,
            "akms_resolve_task",
            {
                "task_json_path": str(task_path),
                "routes_path": str(routes_path),
                "agent_role": "implementer",
                "changed_paths": ["src/solver.py"],
            },
        )
        assert result["status"] == "ok", result
        assert result["fingerprint"]
        assert result["required_count"] >= 1
        assert Path(result["loadout_path"]).exists()
