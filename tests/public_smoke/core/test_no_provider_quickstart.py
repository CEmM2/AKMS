"""Public smoke test: the no-provider quickstart against the installed package.

Mirrors the README quickstart a new user runs after ``pip install akms``:
build a small vault, compile the graph, inspect health, query a projection,
generate a loadout, and feed evidence back — all offline, with no API key,
no provider SDK, and no pre-existing configuration.

The test intentionally shells out to the ``akms`` console script (not the
Python API) wherever the quickstart does, so a broken entry point or a
missing runtime dependency fails here the way it would fail for a user.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

BIN = Path(sys.executable).parent


def _write_vault(tmp: Path) -> Path:
    vault = tmp / "vault" / "nodes"
    vault.mkdir(parents=True)
    for node_id, edges in [
        ("smoke-a", [{"to": "smoke-b", "type": "requires", "weight": 0.8}]),
        ("smoke-b", []),
    ]:
        (vault / f"{node_id}.md").write_text(
            "\n".join(
                [
                    "---",
                    "akms_schema: v2",
                    f"id: {node_id}",
                    f"title: Smoke {node_id}",
                    "domain: smoke-domain",
                    "tags:",
                    "- smoke",
                    "status: established",
                    "confidence: 0.9",
                    "source: human",
                    "edges:" if edges else "edges: []",
                    *[
                        f"- to: {e['to']}\n  type: {e['type']}\n  weight: {e['weight']}"
                        for e in edges
                    ],
                    "---",
                    "",
                    f"Content for {node_id}.",
                ]
            )
        )
    return vault


def _write_repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    for sub in ["graph", "local-nodes", "sessions", "loadouts", "code-mirror", "qmd"]:
        (repo / "knowledge" / sub).mkdir(parents=True)
    (repo / "knowledge" / "graph" / "local_state.yaml").write_text(
        "akms_schema: v2\nnodes: {}\n"
    )
    return repo


def _cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(BIN / "akms"), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        timeout=120,
    )


@pytest.mark.e2e
def test_no_provider_quickstart(tmp_path):
    vault = _write_vault(tmp_path)
    repo = _write_repo(tmp_path)

    # 1. Compile the graph (Python API — there is no `akms build` CLI).
    build = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from akms.graph.build_graph import build_graph; "
            f"build_graph({str(repo)!r}, global_vault={str(vault)!r})",
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert build.returncode == 0, build.stderr
    graph_file = repo / "knowledge" / "graph" / "graph.json"
    assert graph_file.exists(), "build_graph did not write knowledge/graph/graph.json"

    # 2. Health report.
    status = _cli(["status"], cwd=repo)
    assert status.returncode == 0, status.stderr
    assert "Nodes in graph: 2" in status.stdout

    # 3. Projection query by seed tag.
    query = _cli(["query", "smoke"], cwd=repo)
    assert query.returncode == 0, query.stderr
    assert "smoke-a" in query.stdout and "smoke-b" in query.stdout

    # 4. Loadout generation.
    loadout = _cli(
        ["loadout", "smoke-task", "--phase", "1", "--tags", "smoke"],
        cwd=repo,
    )
    assert loadout.returncode == 0, loadout.stderr
    loadouts = list((repo / "knowledge" / "loadouts").glob("*"))
    assert loadouts, "loadout command produced no loadout file"

    # 5. Evidence round-trip (Python API), then confirm the overlay mutated.
    evidence = {
        "task_id": "smoke-task",
        "nodes_used": [{"id": "smoke-a", "useful": True, "coverage": "sufficient"}],
        "nodes_missing": [],
        "lessons": {},
        "pitfalls_discovered": [],
        "new_knowledge": [],
    }
    ingest = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json, sys; from akms.graph.update_graph import update_graph; "
            f"summary = update_graph(json.loads(sys.argv[1]), {str(repo)!r}, "
            f"global_vault={str(vault)!r}); "
            "print(json.dumps({'events': len(summary['confidence_events'])}))",
            json.dumps(evidence),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert ingest.returncode == 0, ingest.stderr
    assert json.loads(ingest.stdout.strip().splitlines()[-1])["events"] >= 1


@pytest.mark.e2e
def test_cli_entry_point_works_without_extras(tmp_path):
    """`akms --help` succeeds on the minimal install (no provider SDKs)."""
    result = subprocess.run(
        [str(BIN / "akms"), "--help"], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0
    assert "AKMS" in result.stdout
