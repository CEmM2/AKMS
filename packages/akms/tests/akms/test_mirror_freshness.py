"""Git-based code-mirror staleness for ``akms status``."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

from akms.graph.graph_status import format_report, graph_status
from akms.graph.mirror_freshness import check_mirror_freshness, stale_mirrors
from akms.repo_wiki.export import export_akms

GENERATED = "2026-01-01T00:00:00+00:00"
LATER = "2026-02-01T00:00:00+00:00"
REFRESHED = "2026-03-01T00:00:00+00:00"


def _git(repo: Path, *args: str, date: str = "2025-12-01T00:00:00+00:00") -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": date,
        "GIT_COMMITTER_DATE": date,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, env=env
    )


def _write(repo: Path, rel: str, text: str) -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _export(repo: Path, generated_at: str, *, output: Path | None = None) -> None:
    result = export_akms(
        repo_root=repo,
        output_root=output or repo,
        phase=1,
        generated_at=generated_at,
        knowledge_dir=".knowledge",
    )
    assert result.errors == []


def _set_mtime(path: Path, iso: str) -> None:
    stamp = datetime.fromisoformat(iso).timestamp()
    os.utime(path, (stamp, stamp))


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo, "pkg/a.py", "A = 1\n")
    _write(repo, "pkg/b.py", "B = 1\n")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    _export(repo, GENERATED)
    return repo


def _reasons(repo: Path) -> dict[str, str]:
    return {m["source_file"]: m["reason"] for m in stale_mirrors(repo)}


def test_fresh_mirrors_are_not_reported(repo: Path):
    assert stale_mirrors(repo) == []


def test_a_commit_after_generation_makes_the_mirror_stale(repo: Path):
    _write(repo, "pkg/a.py", "A = 2\n")
    _git(repo, "commit", "-qam", "change a", date=LATER)

    [record] = stale_mirrors(repo)

    assert record["source_file"] == "pkg/a.py"
    assert record["reason"] == "committed_after"
    assert record["changed_at"].startswith("2026-02-01")
    assert record["generated_at"].startswith("2026-01-01")


def test_refreshing_clears_it(repo: Path):
    _write(repo, "pkg/a.py", "A = 2\n")
    _git(repo, "commit", "-qam", "change a", date=LATER)

    _export(repo, REFRESHED)

    assert stale_mirrors(repo) == []


def test_an_uncommitted_edit_after_generation_makes_it_stale(repo: Path):
    _set_mtime(_write(repo, "pkg/b.py", "B = 2\n"), LATER)

    assert _reasons(repo) == {"pkg/b.py": "modified_after"}


def test_an_uncommitted_edit_before_generation_does_not(repo: Path):
    _set_mtime(_write(repo, "pkg/b.py", "B = 2\n"), "2025-12-15T00:00:00+00:00")

    assert stale_mirrors(repo) == []


def test_a_deleted_source_is_reported(repo: Path):
    (repo / "pkg" / "b.py").unlink()

    assert _reasons(repo) == {"pkg/b.py": "source_missing"}


def test_a_renamed_source_counts_as_missing_not_dirty(repo: Path):
    _git(repo, "mv", "pkg/b.py", "pkg/c.py")

    assert _reasons(repo) == {"pkg/b.py": "source_missing"}


def test_nothing_is_reported_outside_git(tmp_path: Path):
    _write(tmp_path, "pkg/a.py", "A = 1\n")
    _export(tmp_path, GENERATED)
    _set_mtime(tmp_path / "pkg" / "a.py", LATER)

    assert stale_mirrors(tmp_path) == []
    result = check_mirror_freshness(tmp_path)
    assert (result["checked"], result["skipped"]) == (False, "not a git repository")


def test_a_clean_check_says_it_ran(repo: Path):
    result = check_mirror_freshness(repo)

    assert result == {"mirrors": 2, "checked": True, "skipped": None, "stale": []}


def test_knowledge_below_the_repository_resolves_sources_from_the_top(tmp_path: Path):
    repo = tmp_path / "repo"
    _write(repo, "src/x.py", "X = 1\n")
    (repo / "dev").mkdir()
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "base")
    _export(repo, GENERATED, output=repo / "dev")
    _write(repo, "src/x.py", "X = 2\n")
    _git(repo, "commit", "-qam", "change x", date=LATER)

    assert _reasons(repo / "dev") == {"src/x.py": "committed_after"}


def test_status_report_lists_stale_mirrors(repo: Path, tmp_path: Path):
    _write(repo, "pkg/a.py", "A = 2\n")
    _git(repo, "commit", "-qam", "change a", date=LATER)
    vault = tmp_path / "vault"
    vault.mkdir()

    report = graph_status(repo, global_vault=vault)
    text = format_report(report)

    assert [m["source_file"] for m in report["stale_mirrors"]] == ["pkg/a.py"]
    assert "## Stale Code Mirrors: 1" in text
    assert "pkg/a.py: mirror 2026-01-01" in text

    _export(repo, REFRESHED)
    report = graph_status(repo, global_vault=vault)
    assert report["stale_mirrors"] == []
    assert report["mirror_freshness"] == {
        "mirrors": 2,
        "checked": True,
        "skipped": None,
    }
    text = format_report(report)
    assert "## Stale Code Mirrors: 0\n  All 2 code mirrors are current." in text


def test_status_says_the_check_was_skipped_outside_git(tmp_path: Path):
    repo = tmp_path / "plain"
    _write(repo, "pkg/a.py", "A = 1\n")
    _export(repo, GENERATED)
    vault = tmp_path / "vault"
    vault.mkdir()

    report = graph_status(repo, global_vault=vault)
    text = format_report(report)

    assert report["stale_mirrors"] == []
    assert report["mirror_freshness"] == {
        "mirrors": 1,
        "checked": False,
        "skipped": "not a git repository",
    }
    assert "## Stale Code Mirrors: not checked" in text
    assert "Skipped (not a git repository)" in text
    assert "## Stale Code Mirrors: 0" not in text


def test_status_has_no_mirror_section_without_mirrors(tmp_path: Path):
    repo = tmp_path / "bare"
    (repo / ".knowledge").mkdir(parents=True)
    _git(repo, "init", "-q")
    vault = tmp_path / "vault"
    vault.mkdir()

    report = graph_status(repo, global_vault=vault)

    assert report["mirror_freshness"]["mirrors"] == 0
    assert "Stale Code Mirrors" not in format_report(report)


def test_a_report_without_freshness_keeps_the_old_layout():
    # A report dict from before mirror_freshness existed still formats.
    assert "Stale Code Mirrors" not in format_report({"stale_mirrors": []})


def test_a_failing_git_query_is_not_reported_clean(repo: Path, monkeypatch):
    from akms.graph import mirror_freshness

    real = mirror_freshness._git

    def failing_log(top: Path, *arguments: str) -> bytes | None:
        return None if arguments[0] == "log" else real(top, *arguments)

    monkeypatch.setattr(mirror_freshness, "_git", failing_log)
    result = check_mirror_freshness(repo)

    assert result["checked"] is False
    assert result["skipped"] == "git failed"
    assert result["stale"] == []


def test_reads_mirror_files_not_a_cached_graph(repo: Path, tmp_path: Path):
    vault = tmp_path / "vault"
    vault.mkdir()
    graph_status(repo, global_vault=vault)  # compiles and caches graph.json
    _write(repo, "pkg/a.py", "A = 2\n")
    _git(repo, "commit", "-qam", "change a", date=LATER)
    _export(repo, REFRESHED)  # refreshed, graph.json not rebuilt

    assert graph_status(repo, global_vault=vault)["stale_mirrors"] == []


def test_generated_at_is_compared_as_an_aware_time(repo: Path):
    # Mirror timestamps are UTC; a commit in another zone compares correctly.
    _write(repo, "pkg/a.py", "A = 2\n")
    _git(repo, "commit", "-qam", "change a", date="2026-01-01T01:30:00+02:00")

    assert stale_mirrors(repo) == []
