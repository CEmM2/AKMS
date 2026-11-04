"""``changes``: git diffs mapped to symbols and their direct callers, on real temp repos."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from akms.repo_wiki.changes import parse_name_status, parse_unified_hunks
from akms.repo_wiki.cli import main

from .test_build_render_graph_summary import copy_fixture

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


@pytest.fixture()
def repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    copy_fixture(FIXTURES / "intel_repo", tmp_path)
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


def changes(repo: Path, capsys: pytest.CaptureFixture[str], *args: str) -> dict:
    assert main(["--repo-root", str(repo), "changes", *args, "--json"]) == 0
    return json.loads(capsys.readouterr().out)


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def by_id(payload: dict) -> dict[str, dict]:
    return {item["id"]: item for item in payload["changed_symbols"]}


def test_clean_tree_reports_nothing(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = changes(repo, capsys)
    assert payload["files"] == [] and payload["changed_symbols"] == []
    assert payload["summary"]["risk"] == "LOW"


def test_modified_function_body_maps_to_symbol_and_callers(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    edit(repo / "pkg" / "core.py", "return value * 2", "return value * 3")
    payload = changes(repo, capsys)
    assert payload["mode"] == "worktree"
    assert [f["path"] for f in payload["files"]] == ["pkg/core.py"]
    assert payload["files"][0]["hunks"] == [
        {"old_start": 6, "old_lines": 1, "new_start": 6, "new_lines": 1}
    ]
    symbols = by_id(payload)
    assert list(symbols) == ["python:pkg/core.py::leaf"]
    leaf = symbols["python:pkg/core.py::leaf"]
    assert leaf["status"] == "modified"
    assert [c["id"] for c in leaf["callers"]["confident"]] == [
        "python:pkg/core.py::Store._write",
        "python:pkg/core.py::middle",
        "python:pkg/service.py::via_module",
        "python:tests/test_core.py::test_leaf",
    ]
    summary = payload["summary"]
    assert summary["changed_symbols"] == 1
    assert summary["affected_callers"] == {"confident": 4, "possible": 0}
    assert summary["risk"] == "MEDIUM"  # 3 non-test direct callers


def test_new_function_is_added_with_no_callers(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with (repo / "pkg" / "core.py").open("a", encoding="utf-8") as handle:
        handle.write("\n\ndef fresh():\n    return leaf(1)\n")
    payload = changes(repo, capsys)
    symbols = by_id(payload)
    assert list(symbols) == ["python:pkg/core.py::fresh"]
    fresh = symbols["python:pkg/core.py::fresh"]
    assert fresh["status"] == "added"
    assert (fresh["start_line"], fresh["end_line"]) == (27, 28)
    assert fresh["callers"] == {"confident": [], "possible": []}
    assert payload["module_level_changes"] == []


def test_deleted_function_keeps_base_lines_and_flags_dangling_callers(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    edit(
        repo / "pkg" / "core.py",
        "def middle(value):\n    return leaf(value) + 1\n\n\n",
        "",
    )
    payload = changes(repo, capsys)
    middle = by_id(payload)["python:pkg/core.py::middle"]
    assert middle["status"] == "deleted"
    assert (middle["start_line"], middle["end_line"]) == (
        9,
        10,
    )  # from the base revision
    confident = middle["callers"]["confident"]
    assert [c["id"] for c in confident] == ["python:pkg/service.py::run"]
    assert confident[0]["edge"]["basis"] == "dangling"
    assert [c["id"] for c in middle["callers"]["possible"]] == [
        "python:other/helpers.py::stray"
    ]
    assert payload["summary"]["dangling_references"] == 1
    assert payload["summary"]["risk"] == "HIGH"


def test_rename_reports_moved_symbols_and_their_old_importers(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git(repo, "mv", "pkg/api.py", "pkg/public_api.py")
    payload = changes(repo, capsys)
    assert payload["files"][0]["status"] == "renamed"
    assert payload["files"][0]["old_path"] == "pkg/api.py"
    moved = by_id(payload)["python:pkg/public_api.py::public_entry"]
    assert moved["status"] == "moved"
    assert moved["old_id"] == "python:pkg/api.py::public_entry"
    assert [c["id"] for c in moved["callers"]["confident"]] == [
        "python:pkg/cli.py::main"
    ]
    assert payload["summary"]["risk"] == "HIGH"


def test_renamed_and_edited_file_marks_touched_symbol_modified(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git(repo, "mv", "pkg/cli.py", "pkg/entry.py")
    edit(repo / "pkg" / "entry.py", "return public_entry(1)", "return public_entry(2)")
    payload = changes(repo, capsys)
    item = by_id(payload)["python:pkg/entry.py::main"]
    assert item["status"] == "modified"
    assert item["old_id"] == "python:pkg/cli.py::main"


def test_staged_mode_sees_only_the_index(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    edit(repo / "pkg" / "core.py", "return value * 2", "return value * 3")
    git(repo, "add", "pkg/core.py")
    edit(
        repo / "pkg" / "service.py", "return middle(value)", "return middle(value) + 0"
    )
    staged = changes(repo, capsys, "--staged")
    assert staged["mode"] == "staged"
    assert list(by_id(staged)) == ["python:pkg/core.py::leaf"]
    worktree = changes(repo, capsys, "--worktree")
    assert sorted(by_id(worktree)) == [
        "python:pkg/core.py::leaf",
        "python:pkg/service.py::run",
    ]


def test_staged_content_differs_from_worktree(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    core = repo / "pkg" / "core.py"
    with core.open("a", encoding="utf-8") as handle:
        handle.write("\n\ndef staged_only():\n    return 1\n")
    git(repo, "add", "pkg/core.py")
    edit(core, "def staged_only():\n    return 1\n", "")
    staged = changes(repo, capsys, "--staged")
    assert "python:pkg/core.py::staged_only" in by_id(staged)


def test_untracked_file_and_base_ref(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "pkg" / "extra.py").write_text(
        "from pkg.core import leaf\n\n\ndef uses_leaf():\n    return leaf(5)\n",
        encoding="utf-8",
    )
    payload = changes(repo, capsys)
    assert payload["files"][0]["status"] == "added"
    assert list(by_id(payload)) == ["python:pkg/extra.py::uses_leaf"]
    assert changes(repo, capsys, "--staged")["changed_symbols"] == []

    git(repo, "add", "pkg/extra.py")
    git(repo, "commit", "-q", "-m", "extra")
    edit(repo / "pkg" / "core.py", "return text.strip()", "return text.strip().lower()")
    since = changes(repo, capsys, "--base", "HEAD~1")
    assert since["mode"] == "base" and since["base"] == "HEAD~1"
    assert sorted(by_id(since)) == [
        "python:pkg/core.py::parse",
        "python:pkg/extra.py::uses_leaf",
    ]
    # Against HEAD, the committed extra.py is outside the diff and missing from the graph.
    assert main(["--repo-root", str(repo), "changes"]) == 3
    capsys.readouterr()
    head = changes(repo, capsys, "--allow-stale")
    assert [f["path"] for f in head["files"]] == ["pkg/core.py"]


def test_new_caller_in_an_edited_file_is_seen_without_a_rebuild(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    edit(repo / "pkg" / "core.py", "return value * 2", "return value * 4")
    edit(repo / "pkg" / "api.py", "return run(value)", "return run(value) + leaf(1)")
    edit(
        repo / "pkg" / "api.py",
        "from pkg.service import run",
        "from pkg.core import leaf\nfrom pkg.service import run",
    )
    payload = changes(repo, capsys)
    leaf = by_id(payload)["python:pkg/core.py::leaf"]
    callers = {c["id"]: c for c in leaf["callers"]["confident"]}
    assert callers["python:pkg/api.py::public_entry"]["changed"] is True
    # Edited callers are part of the change, so they do not count as affected:
    # leaf's 4 other callers plus cli.main, the caller of the edited public_entry.
    assert sorted(by_id(payload)) == [
        "python:pkg/api.py::public_entry",
        "python:pkg/core.py::leaf",
    ]
    assert payload["summary"]["affected_callers"]["confident"] == 5


def test_non_source_and_unparsable_files(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "README.md").write_text("# hi\n", encoding="utf-8")
    edit(repo / "pkg" / "cli.py", "def main(argv=None):", "def main(argv=None:")
    payload = changes(repo, capsys)
    files = {f["path"]: f for f in payload["files"]}
    assert files["README.md"]["symbols_supported"] is False
    assert files["pkg/cli.py"]["parse_error"]
    assert payload["changed_symbols"] == []


def test_files_outside_the_diff_still_make_the_graph_stale(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Commit a change without rebuilding: the graph no longer matches HEAD.
    edit(
        repo / "pkg" / "service.py", "return middle(value)", "return middle(value) * 2"
    )
    git(repo, "commit", "-qam", "service")
    edit(repo / "pkg" / "core.py", "return value * 2", "return value * 3")
    code = main(["--repo-root", str(repo), "changes", "--json"])
    assert code == 3
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "graph_stale"
    assert main(["--repo-root", str(repo), "changes", "--allow-stale"]) == 0
    assert "python:pkg/core.py::leaf" in capsys.readouterr().out


def test_not_a_git_repo_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    copy_fixture(FIXTURES / "intel_repo", tmp_path)
    assert main(["--repo-root", str(tmp_path), "changes", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "git_error"


def test_bad_base_ref_exits_1(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--repo-root", str(repo), "changes", "--base", "no-such-ref"]) == 1
    assert "no-such-ref" in capsys.readouterr().err


def test_changes_json_shape_is_stable(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    edit(repo / "pkg" / "core.py", "return value * 2", "return value * 3")
    payload = changes(repo, capsys)
    assert set(payload) == {
        "schema",
        "mode",
        "base",
        "base_commit",
        "graph",
        "files",
        "changed_symbols",
        "module_level_changes",
        "summary",
    }
    assert payload["schema"] == "repo-wiki/changes/v1"
    assert set(payload["files"][0]) == {
        "path",
        "old_path",
        "status",
        "binary",
        "hunks",
        "symbols_supported",
        "parse_error",
    }
    assert set(payload["changed_symbols"][0]) == {
        "id",
        "old_id",
        "status",
        "kind",
        "name",
        "qualname",
        "path",
        "start_line",
        "end_line",
        "is_test",
        "public_entry",
        "callers",
    }
    caller = payload["changed_symbols"][0]["callers"]["confident"][0]
    assert {"id", "path", "start_line", "end_line", "edge", "changed"} <= set(caller)
    assert set(payload["summary"]) == {
        "files",
        "changed_symbols",
        "by_status",
        "affected_callers",
        "dangling_references",
        "modules_reached",
        "public_entry_points",
        "risk",
        "risk_with_possible",
        "risk_reasons",
    }


def test_text_output_summarizes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    edit(repo / "pkg" / "core.py", "return value * 2", "return value * 3")
    assert main(["--repo-root", str(repo), "changes"]) == 0
    out = capsys.readouterr().out
    assert "modified python:pkg/core.py::leaf" in out
    assert "Summary: 1 changed symbol(s) (1 modified)" in out


# ---------------------------------------------------------------- diff parsing


def test_parse_name_status_handles_renames_and_deletes() -> None:
    raw = b"M\0a.py\0R087\0old.py\0new.py\0D\0gone.py\0A\0fresh.py\0"
    parsed = [(c.status, c.old_path, c.path) for c in parse_name_status(raw)]
    assert parsed == [
        ("modified", "a.py", "a.py"),
        ("renamed", "old.py", "new.py"),
        ("deleted", "gone.py", "gone.py"),
        ("added", None, "fresh.py"),
    ]


def test_parse_unified_hunks_ignores_content_that_looks_like_headers() -> None:
    patch = (
        "diff --git a/x.py b/x.py\n"
        "--- a/x.py\n"
        "+++ b/x.py\n"
        "@@ -3 +3,2 @@ def f():\n"
        "--- not a header\n"
        "+++ also not\n"
        "+new\n"
        "diff --git a/gone.py b/gone.py\n"
        "--- a/gone.py\n"
        "+++ /dev/null\n"
        "@@ -1,4 +0,0 @@\n"
    )
    hunks = parse_unified_hunks(patch)
    assert set(hunks) == {"x.py", "gone.py"}
    first = hunks["x.py"][0][0]
    assert (first.old_start, first.old_lines, first.new_start, first.new_lines) == (
        3,
        1,
        3,
        2,
    )
    gone = hunks["gone.py"][0][0]
    assert (gone.old_lines, gone.new_lines) == (4, 0)
