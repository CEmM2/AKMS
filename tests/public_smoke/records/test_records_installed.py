"""Public smoke test: ``akms-records`` from built wheels, alone and with ``[akms]``.

Each test skips itself in the environment it is not for, so the same file runs
in the environment with only ``akms-records`` and in the one with its extra.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

BIN = Path(sys.executable).parent
HAS_AKMS = importlib.util.find_spec("akms") is not None
DECISION = {
    "schema_ref": "decision/v1",
    "payload": {"decision": "Keep the coarse mesh", "rationale": "within budget"},
    "review_state": "user_confirmed",
    "tags": ["mesh"],
}
LESSON = {
    "id": "L001",
    "date_found": "2026-08-01",
    "date_found_precision": "exact",
    "date_fixed": "2026-08-02",
    "date_fixed_precision": "exact",
    "location": {
        "area": "src",
        "package": "p",
        "module": "m",
        "file": "src/m.py",
        "symbol": "",
        "line_hint": "",
    },
    "found_by": {"type": "test", "trigger": "t"},
    "symptom": "It failed.",
    "root_cause": "Cause.",
    "fix": "Fix.",
    "prevention": "Prevent.",
    "references": {"commit": "", "issue": "", "pr": "", "plan": ""},
    "related": [],
}


def records(*args: str, env: dict[str, str] | None = None, cwd: Path | None = None):
    return subprocess.run(
        [str(BIN / "akms-records"), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
    )


def ok(done: subprocess.CompletedProcess[str]) -> dict:
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def add_record(tmp_path: Path, repo: Path, base: tuple[str, ...]) -> str:
    ok(records("schema", "register", "--template", "decision", *base))
    document = tmp_path / "decision.json"
    document.write_text(json.dumps(DECISION), encoding="utf-8")
    return ok(records("add", "--file", str(document), *base))["record_id"]


def test_failure_memory_import_and_wake_need_no_other_package(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "lessons.json").write_text(
        json.dumps({"schema_version": 1, "_field_spec": {}, "lessons": [LESSON]}),
        encoding="utf-8",
    )
    config = repo / "project.toml"
    config.write_text(
        'schema_version = "failure-memory-project/v1"\nrepository_id = "demo"\n'
        '[paths]\nregistry = "lessons.json"\n'
        '[validation]\nregistry_schema_version = 1\nid_pattern = "^L[0-9]+$"\n',
        encoding="utf-8",
    )
    base = ("--scope", "project:example", "--repo", str(repo))
    created = ok(records("import", *base, "--from-failure-memory", str(config)))
    assert [row["lesson"] for row in created["created"]] == ["L001"]
    again = ok(records("import", *base, "--from-failure-memory", str(config)))
    assert again["created"] == [] and again["unchanged"] == ["L001"]
    wake = ok(
        records(
            "wake",
            "--agent",
            "scout",
            "--task",
            "failed",
            "--budget-tokens",
            "400",
            "--scope",
            "project:example",
            "--repo",
            str(repo),
        )
    )
    assert wake["report"]["excluded"]["imported"]["count"] == 1
    assert wake["budget"]["used"] <= 400


@pytest.mark.skipif(HAS_AKMS, reason="this environment has akms")
def test_promote_without_the_extra_names_it(tmp_path):
    assert importlib.util.find_spec("akms_failure_memory") is None
    repo = tmp_path / "repo"
    repo.mkdir()
    base = ("--scope", "project:example", "--repo", str(repo))
    record_id = add_record(tmp_path, repo, base)
    done = records("promote", record_id, *base, "--review", "approved")
    assert done.returncode == 2
    assert "error[akms_unavailable]" in done.stderr
    assert "akms-records[akms]" in done.stderr


@pytest.mark.skipif(not HAS_AKMS, reason="this environment has no akms")
def test_promote_with_the_extra_on_both_paths(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(vault))
    repo = tmp_path / "repo"
    repo.mkdir()
    base = ("--scope", "project:example", "--repo", str(repo))
    record_id = add_record(tmp_path, repo, base)
    result = ok(records("promote", record_id, *base, "--review", "approved"))
    assert result["action"] == "created"
    assert result["node"] == {
        "source": "agent",
        "status": "tentative",
        "confidence": 0.5,
    }
    again = ok(records("promote", record_id, *base, "--review", "approved"))
    assert again["action"] == "already_promoted"
    policy = (
        "schema",
        "policy",
        "set",
        "decision",
        *base,
        "--source",
        "human",
        "--status",
        "established",
        "--confidence",
        "0.8",
        "--yes",
    )
    ok(records(*policy))
    document = tmp_path / "second.json"
    second = {**DECISION, "payload": {"decision": "A second", "rationale": "other"}}
    document.write_text(json.dumps(second), encoding="utf-8")
    other = ok(records("add", "--file", str(document), *base))["record_id"]
    refused = records("promote", other, *base, "--review", "approved")
    assert refused.returncode == 2
    assert "error[confirmation_required]" in refused.stderr
    human = ok(records("promote", other, *base, "--review", "approved", "--yes"))
    assert human["path"] == "human-policy"
    assert human["confirmation"] == "yes"
    assert human["node"]["status"] == "established"
    assert list(vault.iterdir()) == []
    from akms.graph.build_graph import load_graph

    graph = load_graph(repo / ".knowledge" / "graph" / "graph.json")
    assert {record_id, other} <= set(graph.nodes)
    wake = ok(
        records(
            "wake",
            "--agent",
            "scout",
            "--task",
            "mesh",
            "--budget-tokens",
            "400",
            "--scope",
            "project:example",
            "--repo",
            str(repo),
        )
    )
    assert sorted(wake["report"]["excluded"]["promoted"]["ids"]) == sorted(
        [record_id, other]
    )
