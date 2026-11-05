"""``flows`` and ``flow`` commands, and the flow sections of ``context``, ``impact``, ``changes``."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from akms.repo_wiki.cli import main

from .test_build_render_graph_summary import copy_fixture

FIXTURES = Path(__file__).resolve().parent / "fixtures"
APP = "python:pkg/app.py::"
CORE = "python:pkg/core.py::"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    copy_fixture(FIXTURES / "flows_repo", tmp_path)
    (tmp_path / ".gitignore").write_text(".repo_wiki/\n", encoding="utf-8")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "test@example.com")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "commit.gpgsign", "false")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "initial")
    assert (
        main(["--repo-root", str(tmp_path), "build", "--no-summaries", "--no-index"])
        == 0
    )
    capsys.readouterr()
    return tmp_path


def run(
    repo: Path, capsys: pytest.CaptureFixture[str], *args: str
) -> tuple[int, dict, str]:
    code = main(["--repo-root", str(repo), *args, "--json"])
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


def text(repo: Path, capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str]:
    code = main(["--repo-root", str(repo), *args])
    return code, capsys.readouterr().out


SUMMARY_KEYS = {
    "id",
    "name",
    "kind",
    "entry",
    "detail",
    "path",
    "start_line",
    "end_line",
    "steps",
    "depth",
    "terminals",
    "truncated",
    "truncated_reasons",
    "heuristic_steps",
    "inferred_steps",
}

# ------------------------------------------------------------------- flows


def test_flows_json_shape(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload, err = run(repo, capsys, "flows")
    assert code == 0 and err == ""
    assert set(payload) == {
        "schema",
        "filters",
        "flows",
        "summary",
        "settings",
        "flows_source",
        "graph",
    }
    assert payload["schema"] == "repo-wiki/flows/v1"
    assert set(payload["flows"][0]) == SUMMARY_KEYS
    assert payload["summary"] == {
        "total": 7,
        "matched": 7,
        "shown": 7,
        "by_kind": {"cli": 2, "console_script": 1, "root": 3, "script": 1},
        "omitted_flows": {},
    }
    assert payload["flows_source"] == {"source": "file", "reason": None}
    assert [f["kind"] for f in payload["flows"]][:2] == ["console_script", "script"]


def test_flows_filters(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, by_kind, _ = run(repo, capsys, "flows", "--kind", "cli")
    assert {f["entry"] for f in by_kind["flows"]} == {APP + "cmd_go", APP + "hello"}
    _, by_entry, _ = run(repo, capsys, "flows", "--entry", "chain")
    assert [f["entry"] for f in by_entry["flows"]] == [CORE + "chain_a"]
    _, glob, _ = run(repo, capsys, "flows", "--entry", "pkg.app.*")
    assert {f["entry"] for f in glob["flows"]} == {APP + "cmd_go", APP + "hello"}
    _, alias, _ = run(repo, capsys, "flows", "--entry", "tool-alias")
    assert [f["name"] for f in alias["flows"]] == ["tool"]
    _, touching, _ = run(repo, capsys, "flows", "--touching", "middle")
    assert {f["entry"]: f["touching_depth"] for f in touching["flows"]} == {
        APP + "main": 1,
        "pkg.app": 2,
        APP + "cmd_go": 3,
    }
    assert touching["filters"]["touching"] == CORE + "middle"
    _, limited, _ = run(repo, capsys, "flows", "--limit", "2")
    assert limited["summary"]["shown"] == 2 and limited["summary"]["matched"] == 7


def test_flows_text_output(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out = text(repo, capsys, "flows")
    assert code == 0
    assert out.startswith("Flows: 7 of 7 (2 cli, 1 console_script, 3 root, 1 script)")
    assert "tool  [console_script; 4 steps; depth 2]" in out


def test_flows_exit_codes(
    repo: Path, tmp_path_factory: pytest.TempPathFactory, capsys
) -> None:
    code, payload, _ = run(repo, capsys, "flows", "--limit", "-1")
    assert code == 2 and payload["error"]["code"] == "usage"
    code, payload, _ = run(repo, capsys, "flows", "--touching", "nothing_here")
    assert code == 4 and payload["error"]["code"] == "unknown_symbol"
    empty = tmp_path_factory.mktemp("empty")
    code, payload, _ = run(empty, capsys, "flows")
    assert code == 3 and payload["error"]["code"] == "graph_missing"
    (repo / "pkg" / "core.py").write_text(
        (repo / "pkg" / "core.py").read_text("utf-8") + "\n\ndef new():\n    pass\n",
        encoding="utf-8",
    )
    code, payload, _ = run(repo, capsys, "flow", "tool")
    assert code == 3 and payload["error"]["code"] == "graph_stale"
    code, payload, _ = run(repo, capsys, "flow", "tool", "--allow-stale")
    assert code == 0 and payload["graph"]["stale"] is True


# -------------------------------------------------------------------- flow


def test_flow_lookup_by_id_name_alias_and_entry_symbol(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, by_name, _ = run(repo, capsys, "flow", "tool")
    flow_id = by_name["flow"]["id"]
    for query in (flow_id, "tool-alias", APP + "main", "pkg.app.main"):
        code, payload, _ = run(repo, capsys, "flow", query)
        assert code == 0 and payload["flow"]["id"] == flow_id, query
    assert payload["schema"] == "repo-wiki/flow/v1"
    flow = payload["flow"]
    assert set(flow) == SUMMARY_KEYS | {"aliases", "cycles", "terminals"}
    assert flow["steps"][1]["path"] == "pkg/app.py"
    assert flow["steps"][1]["kind"] == "function"
    assert flow["aliases"] == ["tool-alias"]


def test_flow_unknown_and_not_an_entry(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload, err = run(repo, capsys, "flow", "no_such_flow")
    assert code == 4 and payload["error"]["code"] == "unknown_flow"
    assert "repo-wiki flows" in err
    code, payload, err = run(repo, capsys, "flow", "leaf")
    assert code == 4 and payload["error"]["code"] == "unknown_flow"
    assert "--touching leaf" in err
    code, payload, _ = run(repo, capsys, "flow", "helper")  # two symbols named helper
    assert code == 4 and payload["error"]["code"] == "ambiguous_symbol"


def test_flow_text_is_a_call_tree_with_cuts_and_cycles(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / ".repo_wiki" / "config.yaml").write_text(
        "flows:\n  max_fanout: 2\n  include_heuristic: true\n", encoding="utf-8"
    )
    code, out = text(repo, capsys, "flow", "cmd_go")
    assert code == 0
    lines = out.splitlines()
    assert lines[0].startswith("Flow pkg.app.cmd_go  [cli; ")
    assert "truncated: fanout" in lines[0]
    assert any(
        line.startswith("    wide  pkg/core.py:") and "3 more not followed" in line
        for line in lines
    )
    middle = next(
        i for i, line in enumerate(lines) if line.strip().startswith("middle")
    )
    assert lines[middle + 1].strip().startswith("leaf")  # children follow their parent
    _, spin = text(repo, capsys, "flow", "spin")
    assert "Cycles: python:pkg/core.py::loop_b -> python:pkg/core.py::loop_a" in spin
    _, stray = text(repo, capsys, "flow", "stray")
    assert "? helper  pkg/helpers_a.py" in stray
    assert "[HEURISTIC name]" in stray


def test_stale_flows_file_is_recomputed_with_a_note(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = repo / ".repo_wiki" / "generated" / "flows.json"
    path.unlink()
    code, payload, err = run(repo, capsys, "flows")
    assert code == 0
    assert payload["flows_source"] == {"source": "computed", "reason": "missing"}
    assert "computed in memory" in err
    assert payload["summary"]["total"] == 7
    assert not path.exists()


# ------------------------------------------------------------- integration


def test_context_lists_the_flows_a_symbol_is_in(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, payload, _ = run(repo, capsys, "context", "middle")
    flows = payload["flows"]
    assert flows["count"] == 3
    assert [f["entry"] for f in flows["flows"]] == [
        APP + "main",
        "pkg.app",
        APP + "cmd_go",
    ]  # shallowest first
    assert flows["flows"][0]["matched"] == [{"id": CORE + "middle", "depth": 1}]
    assert flows["as_entry"] is None
    _, entry, _ = run(repo, capsys, "context", "spin")
    assert entry["flows"]["as_entry"] == entry["flows"]["flows"][0]["id"]
    _, out = text(repo, capsys, "context", "middle")
    assert "Flows through it: 3" in out
    assert "tool  [console_script; 4 steps; depth 2]  at d=1" in out


def test_impact_lists_affected_flows_without_changing_risk(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, payload, _ = run(repo, capsys, "impact", "leaf")
    flows = payload["flows"]
    assert flows["through_target"] == 6
    assert flows["count"] == 6
    assert payload["summary"]["risk"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert "flows" not in payload["summary"]["risk_reasons"][0]
    _, out = text(repo, capsys, "impact", "leaf")
    assert "Affected flows: 6 (6 through the target; not part of the risk)" in out


def test_changes_lists_the_flows_the_diff_touches(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    core = repo / "pkg" / "core.py"
    core.write_text(
        core.read_text("utf-8").replace("return leaf(value) + 1", "return leaf(value)"),
        encoding="utf-8",
    )
    _, payload, _ = run(repo, capsys, "changes")
    assert payload["summary"]["flows_touched"] == 3
    assert {f["entry"] for f in payload["flows"]["flows"]} == {
        APP + "main",
        "pkg.app",
        APP + "cmd_go",
    }
    _, out = text(repo, capsys, "changes")
    assert "Flows touched: 3" in out


def test_disabled_flows_leave_the_other_commands_unchanged(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / ".repo_wiki" / "config.yaml").write_text(
        "flows:\n  enabled: false\n", encoding="utf-8"
    )
    _, payload, _ = run(repo, capsys, "context", "middle")
    assert "flows" not in payload
    _, payload, _ = run(repo, capsys, "impact", "middle")
    assert "flows" not in payload
    code, payload, _ = run(repo, capsys, "flows")
    assert code == 0 and payload["summary"]["total"] == 7  # computed on demand


# ----------------------------------------------------------- changes --refresh


def test_changes_without_refresh_keeps_its_shape(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, payload, _ = run(repo, capsys, "changes")
    assert "flows_before" not in payload and "flows_after" not in payload
    assert "refresh" not in payload
    assert "flows_touched_after" not in payload["summary"]


def test_changes_refresh_reports_flows_before_and_after(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    core = repo / "pkg" / "core.py"
    core.write_text(
        core.read_text("utf-8") + "\n\ndef added():\n    return middle(5)\n",
        encoding="utf-8",
    )
    # Without a refresh the new function is in no flow: the stored graph predates it.
    _, plain, _ = run(repo, capsys, "changes", "--allow-stale")
    assert plain["summary"]["flows_touched"] == 0
    code, payload, _ = run(repo, capsys, "changes", "--refresh")
    assert code == 0
    assert payload["refresh"]["parsed"] == 1 and payload["refresh"]["errors"] == 0
    assert payload["flows_before"]["count"] == 0
    assert [f["entry"] for f in payload["flows_after"]["flows"]] == [CORE + "added"]
    assert payload["flows"] == payload["flows_after"]
    summary = payload["summary"]
    assert (
        summary["flows_touched"],
        summary["flows_touched_before"],
        summary["flows_touched_after"],
        summary["flows_only_before"],
        summary["flows_only_after"],
    ) == (1, 0, 1, 0, 1)
    assert payload["graph"]["stale"] is False  # the refresh made it current
    _, out = text(repo, capsys, "changes", "--refresh")
    assert out.startswith("Refreshed the graph first: 0 file(s) re-parsed")
    assert "Flows touched: 1 in the refreshed graph (before the refresh: 1;" in out


def test_changes_refresh_waits_for_and_reports_a_held_build_lock(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from akms.repo_wiki import refresh
    from akms.repo_wiki.locking import acquire_build_lock

    monkeypatch.setattr(refresh, "REFRESH_WAIT_SECONDS", 0.3)
    lock = acquire_build_lock(repo)
    try:
        code, payload, err = run(repo, capsys, "changes", "--refresh")
        assert code == 1 and payload["error"]["code"] == "build_lock"
        assert "waiting for a running build" in err
        code = main(["--repo-root", str(repo), "build", "--no-summaries", "--no-index"])
        assert code == 1
        assert "another repo-wiki build is running" in capsys.readouterr().err
    finally:
        lock.release()
    assert run(repo, capsys, "changes", "--refresh")[0] == 0
