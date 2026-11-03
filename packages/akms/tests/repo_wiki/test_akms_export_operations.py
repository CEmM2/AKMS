"""Export locking, path and git selection, and deterministic timestamps."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from akms.repo_wiki.cli import main
from akms.repo_wiki.export import export_akms
from akms.repo_wiki.export.akms import resolve_generated_at
from akms.repo_wiki.locking import (
    LockError,
    LockOwnership,
    RepoLocalLock,
    _pid_reuse,
    output_lock_path,
)

FIXED_TS = "2026-03-07T12:00:00+00:00"
SRC_ROOT = Path(__file__).resolve().parents[2] / "src"


def _write(repo: Path, rel: str, body: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _git(
    repo: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _init_git_repo(repo: Path) -> None:
    _git(repo, "init")
    _git(repo, "config", "user.email", "repo2md-tests@example.invalid")
    _git(repo, "config", "user.name", "repo2md tests")
    _write(repo, "pkg/a.py", "A = 1\n")
    _write(repo, "pkg/b.py", "B = 1\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")


@pytest.mark.integration
def test_two_process_lock_exclusion(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo, "pkg/value.py", "VALUE = 1\n")
    output = repo / "akms-out"

    holder = RepoLocalLock(
        repo, purpose="export-akms", lock_file=output_lock_path(output)
    )
    holder.acquire()
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join(
            [str(SRC_ROOT), env["PYTHONPATH"]]
            if env.get("PYTHONPATH")
            else [str(SRC_ROOT)]
        )
        child = subprocess.run(
            [
                sys.executable,
                "-c",
                textwrap.dedent(
                    f"""
                    from pathlib import Path
                    from akms.repo_wiki.export import export_akms
                    try:
                        export_akms(
                            repo_root=Path({str(repo)!r}),
                            output_root=Path({str(output)!r}),
                            phase=1,
                            generated_at={FIXED_TS!r},
                            acquire_lock=True,
                        )
                    except Exception as exc:
                        print(type(exc).__name__ + ":" + str(exc))
                        raise SystemExit(3)
                    raise SystemExit(0)
                    """
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
        assert child.returncode == 3
        assert "LockError" in child.stdout or "LockError" in child.stderr
        # Sibling lock must not create the output mirror tree.
        assert not output.exists() or not list(output.rglob("*.md"))
    finally:
        holder.release()

    # After release, export succeeds.
    result = export_akms(
        repo_root=repo,
        output_root=output,
        phase=1,
        generated_at=FIXED_TS,
        acquire_lock=True,
    )
    assert result.errors == []
    assert result.written


@pytest.mark.integration
def test_stale_lock_is_reclaimed_with_diagnostics(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    output = repo / "akms-out"
    _write(repo, "pkg/value.py", "VALUE = 1\n")
    path = output_lock_path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Synthetic dead-owner lock (unlikely PID).
    path.write_text(
        json.dumps(
            {
                "pid": 2**22,
                "hostname": __import__("socket").gethostname(),
                "user": "ghost",
                "acquired_at": "2000-01-01T00:00:00+00:00",
                "lock_name": "export-akms",
                "purpose": "export-akms",
                "process_started_at": "never",
                "cmdline_fingerprint": "repo-wiki export-akms",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    lock = RepoLocalLock(repo, stale_seconds=0, lock_file=path, purpose="export-akms")
    ownership = lock.acquire()
    assert ownership.pid == os.getpid()
    assert (lock.reclaim_reason or "").startswith("reclaiming")
    lock.release()
    assert not path.exists()


@pytest.mark.integration
def test_force_lock_refuses_live_holder(tmp_path: Path):
    """--force-lock must not steal from a live matching owner (no concurrent writers)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    output = repo / "out"
    holder = RepoLocalLock(
        repo, purpose="export-akms", lock_file=output_lock_path(output)
    )
    holder.acquire()
    try:
        with pytest.raises(LockError, match="live writer|still running"):
            RepoLocalLock(
                repo, purpose="export-akms", lock_file=output_lock_path(output)
            ).acquire()
        with pytest.raises(
            LockError, match="refuses to steal|live writer|still running"
        ):
            RepoLocalLock(
                repo,
                purpose="export-akms",
                lock_file=output_lock_path(output),
                force=True,
            ).acquire()
        assert output_lock_path(output).is_file()
    finally:
        holder.release()


@pytest.mark.integration
def test_force_lock_reclaims_dead_owner(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    output = repo / "out"
    path = output_lock_path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "pid": 2**22,
                "hostname": __import__("socket").gethostname(),
                "user": "ghost",
                "acquired_at": "2000-01-01T00:00:00+00:00",
                "lock_name": "export-akms",
                "purpose": "export-akms",
                "process_started_at": "Mon Jan  1 00:00:00 2000",
                "cmdline_fingerprint": "repo-wiki export-akms --phase 1",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    forced = RepoLocalLock(repo, force=True, purpose="export-akms", lock_file=path)
    ownership = forced.acquire()
    assert ownership.pid == os.getpid()
    forced.release()


@pytest.mark.integration
def test_shared_external_output_serializes_across_repo_roots(tmp_path: Path):
    """Two different repo roots targeting the same external output cannot both write."""
    shared_out = tmp_path / "shared-mirror"
    repo_a = tmp_path / "repo_a"
    repo_b = tmp_path / "repo_b"
    repo_a.mkdir()
    repo_b.mkdir()
    _write(repo_a, "a.py", "A = 1\n")
    _write(repo_b, "b.py", "B = 1\n")

    holder = RepoLocalLock(
        repo_a, purpose="export-akms", lock_file=output_lock_path(shared_out)
    )
    holder.acquire()
    try:
        with pytest.raises(LockError, match="export lock is held|live writer"):
            export_akms(
                repo_root=repo_b,
                output_root=shared_out,
                phase=1,
                generated_at=FIXED_TS,
                acquire_lock=True,
            )
    finally:
        holder.release()

    result = export_akms(
        repo_root=repo_b,
        output_root=shared_out,
        phase=1,
        generated_at=FIXED_TS,
        acquire_lock=True,
    )
    assert result.errors == []
    assert result.written
    # Sibling lock is derived from the resolved absolute output path.
    assert output_lock_path(shared_out) == output_lock_path(shared_out.resolve())
    assert output_lock_path(shared_out).parent == shared_out.resolve().parent


@pytest.mark.unit
def test_pid_reuse_start_time_mismatch_is_stale():
    ownership = LockOwnership(
        pid=os.getpid(),
        hostname=__import__("socket").gethostname(),
        user="tester",
        acquired_at="2000-01-01T00:00:00+00:00",
        lock_name="export-akms",
        purpose="export-akms",
        process_started_at="Mon Jan  1 00:00:00 2000",
        cmdline_fingerprint="repo-wiki export-akms",
    )
    reused, reason = _pid_reuse(
        ownership,
        current_started="Tue Feb  2 00:00:00 2020",
        current_cmd="/usr/bin/unrelated-daemon",
    )
    assert reused is True
    assert "PID reuse" in reason


@pytest.mark.unit
def test_pid_reuse_cmdline_fingerprint_mismatch_without_start():
    ownership = LockOwnership(
        pid=12345,
        hostname="host",
        user="tester",
        acquired_at="2000-01-01T00:00:00+00:00",
        lock_name="export-akms",
        purpose="export-akms",
        process_started_at=None,
        cmdline_fingerprint="repo-wiki export-akms --phase 1",
    )
    reused, reason = _pid_reuse(
        ownership,
        current_started=None,
        current_cmd="/usr/sbin/cron",
    )
    assert reused is True
    assert "fingerprint" in reason


@pytest.mark.unit
def test_matching_start_time_not_reuse_even_if_cmdline_differs():
    ownership = LockOwnership(
        pid=os.getpid(),
        hostname="host",
        user="tester",
        acquired_at="2000-01-01T00:00:00+00:00",
        lock_name="export-akms",
        purpose="export-akms",
        process_started_at="Mon Aug 10 12:00:00 2026",
        cmdline_fingerprint="pytest tests/test_akms_export_operations.py",
    )
    reused, _ = _pid_reuse(
        ownership,
        current_started="Mon Aug 10 12:00:00 2026",
        current_cmd="python -m pytest something_else",
    )
    assert reused is False


@pytest.mark.integration
def test_live_pid_wrong_fingerprint_reclaimed_as_stale(tmp_path: Path):
    """Alive PID with exporter cmdline recorded but unrelated live process → reclaim."""
    repo = tmp_path / "repo"
    repo.mkdir()
    path = output_lock_path(repo / "out")
    path.parent.mkdir(parents=True, exist_ok=True)
    # Use this test process PID (alive) but claim it was export-akms with a
    # fabricated start token so fingerprint marks reuse.
    path.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "hostname": __import__("socket").gethostname(),
                "user": "ghost",
                "acquired_at": "2000-01-01T00:00:00+00:00",
                "lock_name": "export-akms",
                "purpose": "export-akms",
                "process_started_at": "Mon Jan  1 00:00:00 1990",
                "cmdline_fingerprint": "repo-wiki export-akms --full",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    # Without force: auto-reclaim as PID reuse (start-time mismatch).
    lock = RepoLocalLock(repo, purpose="export-akms", lock_file=path)
    ownership = lock.acquire()
    assert ownership.pid == os.getpid()
    assert "stale" in (lock.reclaim_reason or "") or "PID reuse" in (
        lock.reclaim_reason or ""
    )
    lock.release()


@pytest.mark.unit
def test_source_date_epoch_is_deterministic_and_never_wall_clock(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    with pytest.raises(ValueError, match="SOURCE_DATE_EPOCH"):
        resolve_generated_at(None, environ={})

    resolved = resolve_generated_at(None, environ={"SOURCE_DATE_EPOCH": "0"})
    assert resolved == "1970-01-01T00:00:00+00:00"

    explicit = resolve_generated_at(FIXED_TS, environ={"SOURCE_DATE_EPOCH": "0"})
    assert explicit == FIXED_TS

    with pytest.raises(ValueError, match="integer"):
        resolve_generated_at(None, environ={"SOURCE_DATE_EPOCH": "not-int"})


@pytest.mark.integration
def test_cli_accepts_source_date_epoch_without_generated_at(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
):
    (tmp_path / "value.py").write_text("VALUE = 1\n", encoding="utf-8")
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1717200000")
    code = main(
        [
            "--repo-root",
            str(tmp_path),
            "export-akms",
            "--output",
            "out",
            "--phase",
            "1",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["generated_at"] == "2024-06-01T00:00:00+00:00"
    assert payload["selection"]["mode"] == "full"
    assert payload["selected"][0]["source_path"] == "value.py"
    assert payload["selected"][0]["source_hash"].startswith("sha256:")


@pytest.mark.integration
def test_path_selection_exports_only_requested_sources(tmp_path: Path):
    _write(tmp_path, "pkg/a.py", "A = 1\n")
    _write(tmp_path, "pkg/b.py", "B = 1\n")
    out = tmp_path / "mirror"
    result = export_akms(
        repo_root=tmp_path,
        output_root=out,
        phase=1,
        generated_at=FIXED_TS,
        source_paths=["pkg/a.py"],
        acquire_lock=True,
    )
    assert result.errors == []
    assert [item.source_path for item in result.written] == ["pkg/a.py"]
    assert result.selection["mode"] == "paths"
    assert result.selection["requested_paths"] == ["pkg/a.py"]
    assert [item.source_path for item in result.selected] == ["pkg/a.py"]
    assert (out / ".knowledge/code-mirror/pkg/a.md").is_file()
    assert not (out / ".knowledge/code-mirror/pkg/b.md").exists()


@pytest.mark.integration
def test_path_selection_refuses_prune(tmp_path: Path):
    _write(tmp_path, "pkg/a.py", "A = 1\n")
    result = export_akms(
        repo_root=tmp_path,
        output_root=tmp_path / "mirror",
        phase=1,
        generated_at=FIXED_TS,
        source_paths=["pkg/a.py"],
        prune=True,
    )
    assert result.errors
    assert result.errors[0].stage == "validation"
    assert "prune" in result.errors[0].message


@pytest.mark.integration
def test_git_selection_clean_and_dirty(tmp_path: Path):
    repo = tmp_path / "gitrepo"
    repo.mkdir()
    _init_git_repo(repo)
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()

    # Clean worktree, no changes since base → empty selection (no errors).
    clean = export_akms(
        repo_root=repo,
        output_root=repo / "mirror-clean",
        phase=1,
        generated_at=FIXED_TS,
        git_base=base,
    )
    assert clean.errors == []
    assert clean.selection["mode"] == "git_diff"
    assert clean.selection["dirty_worktree"] is False
    assert clean.written == []
    assert clean.selected == []

    _write(repo, "pkg/a.py", "A = 2\n")
    dirty = export_akms(
        repo_root=repo,
        output_root=repo / "mirror-dirty",
        phase=1,
        generated_at=FIXED_TS,
        git_base=base,
    )
    assert dirty.errors == []
    assert dirty.selection["dirty_worktree"] is True
    assert [item.source_path for item in dirty.written] == ["pkg/a.py"]
    assert dirty.selected[0].source_hash.startswith("sha256:")


@pytest.mark.integration
def test_git_two_ref_selection_refuses_dirty_worktree(tmp_path: Path):
    repo = tmp_path / "gitrepo"
    repo.mkdir()
    _init_git_repo(repo)
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _write(repo, "pkg/a.py", "A = 2\n")
    _git(repo, "add", "pkg/a.py")
    _git(repo, "commit", "-m", "change")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _write(repo, "pkg/a.py", "A = 3\n")  # dirty

    result = export_akms(
        repo_root=repo,
        output_root=repo / "mirror",
        phase=1,
        generated_at=FIXED_TS,
        git_base=base,
        git_head=head,
    )
    assert result.errors
    assert result.errors[0].stage == "selection"
    assert "dirty worktree" in result.errors[0].message


@pytest.mark.integration
def test_missing_git_ref_is_reported_explicitly(tmp_path: Path):
    repo = tmp_path / "gitrepo"
    repo.mkdir()
    _init_git_repo(repo)
    result = export_akms(
        repo_root=repo,
        output_root=repo / "mirror",
        phase=1,
        generated_at=FIXED_TS,
        git_base="definitely-missing-ref-xyz",
    )
    assert result.errors
    assert result.errors[0].stage == "selection"
    assert "missing or invalid git ref" in result.errors[0].message


@pytest.mark.integration
def test_cli_path_and_json_selection_metadata(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    _write(tmp_path, "pkg/a.py", "A = 1\n")
    _write(tmp_path, "pkg/b.py", "B = 1\n")
    code = main(
        [
            "--repo-root",
            str(tmp_path),
            "export-akms",
            "--output",
            "out",
            "--phase",
            "1",
            "--generated-at",
            FIXED_TS,
            "--path",
            "pkg/b.py",
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["selection"]["mode"] == "paths"
    assert payload["selected"] == [
        {
            "language": "python",
            "source_hash": payload["selected"][0]["source_hash"],
            "source_path": "pkg/b.py",
        }
    ]
    assert [item["source_path"] for item in payload["written"]] == ["pkg/b.py"]


@pytest.mark.integration
def test_git_diff_ignores_non_source_paths_and_exports_code(tmp_path: Path):
    repo = tmp_path / "gitrepo"
    repo.mkdir()
    _init_git_repo(repo)
    _write(repo, "LICENSE", "mit\n")
    _write(repo, "data.json", "{}\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "non-source baseline")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()

    _write(repo, "LICENSE", "mit2\n")
    _write(repo, "data.json", '{"a": 1}\n')
    _write(repo, "pkg/a.py", "A = 2\n")

    result = export_akms(
        repo_root=repo,
        output_root=repo / "mirror",
        phase=1,
        generated_at=FIXED_TS,
        git_base=base,
    )
    assert result.errors == []
    assert result.selection["mode"] == "git_diff"
    assert set(result.selection["requested_paths"]) == {
        "LICENSE",
        "data.json",
        "pkg/a.py",
    }
    assert [item.source_path for item in result.written] == ["pkg/a.py"]
    assert [item.source_path for item in result.selected] == ["pkg/a.py"]


@pytest.mark.integration
def test_explicit_path_still_fails_for_ineligible_source(tmp_path: Path):
    _write(tmp_path, "pkg/a.py", "A = 1\n")
    _write(tmp_path, "LICENSE", "mit\n")
    result = export_akms(
        repo_root=tmp_path,
        output_root=tmp_path / "mirror",
        phase=1,
        generated_at=FIXED_TS,
        source_paths=["LICENSE", "pkg/a.py"],
    )
    assert result.errors
    assert result.errors[0].stage == "selection"
    assert result.errors[0].source_path == "LICENSE"
    assert result.written == []


@pytest.mark.integration
def test_git_diff_handles_non_ascii_paths_despite_quotepath(tmp_path: Path):
    repo = tmp_path / "gitrepo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "repo2md-tests@example.invalid")
    _git(repo, "config", "user.name", "repo2md tests")
    _git(repo, "config", "core.quotepath", "true")
    non_ascii = "src/café.py"
    _write(repo, non_ascii, "VALUE = 1\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial non-ascii")
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _write(repo, non_ascii, "VALUE = 2\n")

    # Default git quoting would emit C-escaped names; exporter must still select.
    quoted = _git(repo, "diff", "--name-only", "--diff-filter=ACMR", base).stdout
    assert "\\" in quoted or quoted.strip().startswith('"')

    result = export_akms(
        repo_root=repo,
        output_root=repo / "mirror",
        phase=1,
        generated_at=FIXED_TS,
        git_base=base,
    )
    assert result.errors == []
    assert [item.source_path for item in result.written] == [non_ascii]
    assert result.selection["requested_paths"] == [non_ascii]


@pytest.mark.integration
def test_unreadable_lock_reclaimed_after_short_grace(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    path = output_lock_path(repo / "out")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")  # corrupt / empty

    # Fresh unreadable lock: still within the short grace window.
    with pytest.raises(LockError, match="unreadable or corrupt lock"):
        RepoLocalLock(
            repo, stale_seconds=6 * 60 * 60, lock_file=path, purpose="export-akms"
        ).acquire()

    # Force may reclaim unreadable locks inside the grace window.
    forced = RepoLocalLock(
        repo,
        stale_seconds=6 * 60 * 60,
        lock_file=path,
        purpose="export-akms",
        force=True,
    )
    ownership = forced.acquire()
    assert ownership.pid == os.getpid()
    forced.release()

    path.write_bytes(b"")
    # Past unreadable grace (5s): reclaimed even though full stale window is hours.
    aged = time.time() - 10
    os.utime(path, (aged, aged))
    lock = RepoLocalLock(
        repo, stale_seconds=6 * 60 * 60, lock_file=path, purpose="export-akms"
    )
    ownership = lock.acquire()
    assert ownership.pid == os.getpid()
    assert "unreadable" in (lock.reclaim_reason or "")
    lock.release()


def _git_repo_with_mirrors(tmp_path: Path) -> tuple[Path, str]:
    """A committed repo whose pkg/a.py and pkg/b.py already have mirrors."""

    repo = tmp_path / "gitrepo"
    repo.mkdir()
    _init_git_repo(repo)
    full = export_akms(repo_root=repo, output_root=repo, phase=1, generated_at=FIXED_TS)
    assert full.errors == []
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "mirrors")
    return repo, _git(repo, "rev-parse", "HEAD").stdout.strip()


def _mirror(repo: Path, stem: str) -> Path:
    return repo / ".knowledge" / "code-mirror" / "pkg" / f"{stem}.md"


@pytest.mark.integration
def test_git_diff_exports_untracked_sources(tmp_path: Path):
    repo, base = _git_repo_with_mirrors(tmp_path)
    _write(repo, "pkg/new.py", "NEW = 1\n")

    result = export_akms(
        repo_root=repo, output_root=repo, phase=1, generated_at=FIXED_TS, git_base=base
    )

    assert result.errors == []
    assert [item.source_path for item in result.written] == ["pkg/new.py"]
    assert _mirror(repo, "new").is_file()
    # The exporter's own lock file is not a selected source.
    assert all(".lock" not in path for path in result.selection["requested_paths"])


@pytest.mark.integration
def test_git_diff_ignores_untracked_files_git_ignores(tmp_path: Path):
    repo, base = _git_repo_with_mirrors(tmp_path)
    _write(repo, ".gitignore", "scratch.py\n")
    _write(repo, "scratch.py", "SCRATCH = 1\n")

    result = export_akms(
        repo_root=repo, output_root=repo, phase=1, generated_at=FIXED_TS, git_base=base
    )

    assert "scratch.py" not in result.selection["requested_paths"]
    assert [item.source_path for item in result.written] == []


@pytest.mark.integration
def test_git_diff_removes_mirrors_of_deleted_sources(tmp_path: Path):
    repo, base = _git_repo_with_mirrors(tmp_path)
    (repo / "pkg" / "b.py").unlink()

    result = export_akms(
        repo_root=repo, output_root=repo, phase=1, generated_at=FIXED_TS, git_base=base
    )

    assert result.errors == []
    assert [item.source_path for item in result.removed] == ["pkg/b.py"]
    assert not _mirror(repo, "b").exists()
    assert _mirror(repo, "a").is_file()


@pytest.mark.integration
def test_git_diff_replaces_the_mirror_of_a_renamed_source(tmp_path: Path):
    repo, base = _git_repo_with_mirrors(tmp_path)
    _git(repo, "mv", "pkg/b.py", "pkg/c.py")

    result = export_akms(
        repo_root=repo, output_root=repo, phase=1, generated_at=FIXED_TS, git_base=base
    )

    assert result.errors == []
    assert [item.source_path for item in result.written] == ["pkg/c.py"]
    assert [item.source_path for item in result.removed] == ["pkg/b.py"]
    assert not _mirror(repo, "b").exists()
    assert _mirror(repo, "c").is_file()


@pytest.mark.integration
def test_git_diff_keeps_mirrors_it_does_not_own(tmp_path: Path):
    repo, base = _git_repo_with_mirrors(tmp_path)
    _mirror(repo, "b").write_text("hand-written notes\n", encoding="utf-8")
    (repo / "pkg" / "b.py").unlink()

    result = export_akms(
        repo_root=repo, output_root=repo, phase=1, generated_at=FIXED_TS, git_base=base
    )

    assert result.removed == []
    assert _mirror(repo, "b").read_text(encoding="utf-8") == "hand-written notes\n"


@pytest.mark.integration
def test_explicit_path_of_a_deleted_source_removes_its_mirror(tmp_path: Path):
    repo, _ = _git_repo_with_mirrors(tmp_path)
    (repo / "pkg" / "b.py").unlink()

    result = export_akms(
        repo_root=repo,
        output_root=repo,
        phase=1,
        generated_at=FIXED_TS,
        source_paths=["pkg/a.py", "pkg/b.py"],
    )

    assert result.errors == []
    assert [item.source_path for item in result.written] == ["pkg/a.py"]
    assert [item.source_path for item in result.removed] == ["pkg/b.py"]
    assert not _mirror(repo, "b").exists()


@pytest.mark.integration
def test_explicit_path_that_never_existed_is_still_an_error(tmp_path: Path):
    repo, _ = _git_repo_with_mirrors(tmp_path)

    result = export_akms(
        repo_root=repo,
        output_root=repo,
        phase=1,
        generated_at=FIXED_TS,
        source_paths=["pkg/typo.py"],
    )

    assert [(e.source_path, e.stage) for e in result.errors] == [
        ("pkg/typo.py", "selection")
    ]
    assert result.removed == []


def _repo_with_unparsable_source(tmp_path: Path) -> Path:
    """pkg/a.py and pkg/b.py are mirrored; pkg/b.py then stops parsing."""

    repo, _ = _git_repo_with_mirrors(tmp_path)
    _write(repo, "pkg/b.py", "def broken(:\n")
    _write(repo, "pkg/c.py", "C = 1\n")
    return repo


@pytest.mark.integration
def test_unparsable_source_is_skipped_and_the_rest_exported(tmp_path: Path):
    repo = _repo_with_unparsable_source(tmp_path)

    result = export_akms(
        repo_root=repo, output_root=repo, phase=1, generated_at=FIXED_TS
    )

    assert result.errors == []
    assert [item.source_path for item in result.written] == ["pkg/a.py", "pkg/c.py"]
    assert [(s.source_path, s.reason) for s in result.skipped] == [
        ("pkg/b.py", "parse_error")
    ]
    assert _mirror(repo, "c").is_file()
    # The record shape is part of the frozen export contract.
    assert set(result.skipped[0].to_dict()) == {
        "source_path",
        "language",
        "source_hash",
        "reason",
    }


@pytest.mark.integration
def test_unparsable_source_keeps_its_existing_mirror(tmp_path: Path):
    repo = _repo_with_unparsable_source(tmp_path)
    before = _mirror(repo, "b").read_bytes()

    result = export_akms(
        repo_root=repo,
        output_root=repo,
        phase=1,
        generated_at=FIXED_TS,
        source_paths=["pkg/b.py"],
    )

    assert result.errors == []
    assert result.written == []
    assert result.removed == []
    assert _mirror(repo, "b").read_bytes() == before


@pytest.mark.integration
def test_prune_does_not_remove_the_mirror_of_an_unparsable_source(tmp_path: Path):
    repo = _repo_with_unparsable_source(tmp_path)
    stale = _mirror(repo, "gone")
    stale.write_text(_mirror(repo, "a").read_text(encoding="utf-8"), encoding="utf-8")
    (repo / "pkg" / "a.py").unlink()

    result = export_akms(
        repo_root=repo, output_root=repo, phase=1, generated_at=FIXED_TS, prune=True
    )

    assert result.errors == []
    # a.py's mirror is stale and removed; b.py (unparsable) keeps its mirror.
    assert [item.source_path for item in result.removed] == ["pkg/a.py"]
    assert _mirror(repo, "b").is_file()
    assert _mirror(repo, "c").is_file()


@pytest.mark.integration
def test_strict_parse_restores_all_or_nothing(tmp_path: Path):
    repo = _repo_with_unparsable_source(tmp_path)
    before = _mirror(repo, "b").read_bytes()

    result = export_akms(
        repo_root=repo,
        output_root=repo,
        phase=1,
        generated_at=FIXED_TS,
        prune=True,
        strict_parse=True,
    )

    assert [(e.source_path, e.stage) for e in result.errors] == [("pkg/b.py", "parse")]
    assert result.written == []
    assert result.removed == []
    assert result.skipped == []
    assert not _mirror(repo, "c").exists()
    assert _mirror(repo, "b").read_bytes() == before


@pytest.mark.integration
def test_missing_extractor_output_is_skipped_unless_strict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from akms.repo_wiki import export as export_package
    from akms.repo_wiki.extract.registry import ExtractionResult

    repo = _repo_with_unparsable_source(tmp_path)
    (repo / "pkg" / "b.py").write_text("B = 2\n", encoding="utf-8")
    real = export_package.extract_files

    def drop_b(sources, config):
        extraction = real(sources, config)
        modules = {
            path: module
            for path, module in extraction.parsed_modules.items()
            if path != "pkg/b.py"
        }
        return ExtractionResult(
            parsed_modules=modules,
            notes=extraction.notes,
            handled_languages=extraction.handled_languages,
        )

    monkeypatch.setattr(export_package, "extract_files", drop_b)

    lenient = export_akms(
        repo_root=repo, output_root=repo, phase=1, generated_at=FIXED_TS
    )
    assert lenient.errors == []
    assert [(s.source_path, s.reason) for s in lenient.skipped] == [
        ("pkg/b.py", "parse_error")
    ]

    strict = export_akms(
        repo_root=repo,
        output_root=repo,
        phase=1,
        generated_at=FIXED_TS,
        strict_parse=True,
    )
    assert [(e.source_path, e.stage) for e in strict.errors] == [("pkg/b.py", "parse")]
    assert strict.written == []


@pytest.mark.integration
def test_decode_error_still_fails_the_export_by_default(tmp_path: Path):
    repo = _repo_with_unparsable_source(tmp_path)
    (repo / "pkg" / "d.py").write_bytes(b"VALUE = '\xff'\n")

    result = export_akms(
        repo_root=repo, output_root=repo, phase=1, generated_at=FIXED_TS
    )

    assert [(e.source_path, e.stage) for e in result.errors] == [("pkg/d.py", "decode")]
    assert result.written == []
