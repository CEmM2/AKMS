"""`failure-memory hooks` and `refresh if-stale`, in real temporary git repositories.

Every repository uses the built-in mirror provider on a tiny Python tree.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from akms_failure_memory.cli import main
from akms_failure_memory.config import load_project_config
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.hooks import (
    HOOK_NAMES,
    OPT_OUT_ENV,
    hooks_status,
    install_hooks,
    run_hook,
    uninstall_hooks,
)
from akms_failure_memory.locks import ProjectLock
from akms_failure_memory.project import init_project
from akms_failure_memory.refresh import refresh_if_stale, refresh_project

pytestmark = pytest.mark.integration

CONFIG = ".knowledge/failure-memory.toml"
MIRRORS = ".knowledge/code-mirror"
GITIGNORE = (
    ".knowledge/code-mirror/\n"
    ".knowledge/generated/\n"
    ".knowledge/graph/\n"
    ".knowledge/local-nodes/\n"
    ".knowledge/.failure-memory.lock\n"
)


@pytest.fixture(autouse=True)
def _hermetic_git(tmp_path_factory: pytest.TempPathFactory, monkeypatch) -> None:
    """Keep the developer's git config (a global core.hooksPath, say) out."""
    empty = tmp_path_factory.mktemp("gitconfig") / "config"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for name, value in {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.invalid",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv(OPT_OUT_ENV, raising=False)


def git(repo: Path, *arguments: str, **kwargs) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        **kwargs,
    )
    assert completed.returncode == 0, completed.stderr
    return completed


def _source(name: str, value: int) -> str:
    return f'"""{name}."""\n\n\ndef {name}() -> int:\n    """Return {value}."""\n    return {value}\n'


def _lesson(lesson_id: str) -> dict:
    return {
        "id": lesson_id,
        "date_found": "2026-08-11",
        "date_found_precision": "exact",
        "date_fixed": "2026-08-11",
        "date_fixed_precision": "exact",
        "location": {
            "area": "tool",
            "package": "demo",
            "module": "demo.alpha",
            "file": "src/alpha.py",
            "symbol": "alpha",
            "line_hint": f"lesson {lesson_id}",
        },
        "found_by": {"type": "test", "trigger": "tests/test_alpha.py::test_alpha"},
        "symptom": "Observed failure.",
        "root_cause": "Known cause.",
        "fix": "Known fix.",
        "prevention": "tests/test_alpha.py prevents recurrence.",
        "references": {"commit": "abc123", "issue": "", "pr": "", "plan": ""},
        "related": [],
    }


def _add_lesson(repo: Path, lesson_id: str) -> None:
    registry = repo / ".knowledge/lessons.json"
    data = json.loads(registry.read_text(encoding="utf-8"))
    data["lessons"].append(_lesson(lesson_id))
    registry.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _project(tmp_path: Path, name: str = "repo") -> tuple[Path, Path]:
    """A committed project on `main` with alpha, beta and gamma sources."""
    repo = tmp_path / name
    (repo / "src").mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    for index, source in enumerate(("alpha", "beta", "gamma")):
        (repo / "src" / f"{source}.py").write_text(_source(source, index), "utf-8")
    (repo / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    init_project(
        repository_root=repo,
        config_path=CONFIG,
        repository_id="demo-repo",
        node_namespace="demo-failure",
    )
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "initial")
    vault = tmp_path / f"{name}-vault"
    vault.mkdir()
    return repo, vault


def _refreshed(tmp_path: Path, name: str = "repo") -> tuple[Path, Path]:
    repo, vault = _project(tmp_path, name)
    refresh_if_stale(
        config_path=repo / CONFIG, repository_root=repo, global_vault=vault
    )
    return repo, vault


def _installed(tmp_path: Path, name: str = "repo") -> tuple[Path, Path]:
    repo, vault = _refreshed(tmp_path, name)
    install_hooks(repository_root=repo, config_path=repo / CONFIG, global_vault=vault)
    return repo, vault


def _mirror(repo: Path, source: str) -> Path:
    return repo / MIRRORS / "src" / f"{source}.md"


def _hook_lines(completed: subprocess.CompletedProcess[str]) -> list[str]:
    return [line for line in completed.stderr.splitlines() if "failure-memory" in line]


def _state(repo: Path) -> Path:
    raw = git(
        repo, "rev-parse", "--git-path", "akms-failure-memory/refresh-state.json"
    ).stdout.strip()
    return repo / raw


# ── install / uninstall / status ──────────────────────────────────────────


def test_install_is_idempotent_and_status_reports_it(tmp_path: Path) -> None:
    repo, vault = _refreshed(tmp_path)
    assert hooks_status(repository_root=repo)["installed"] == "none"

    first = install_hooks(
        repository_root=repo, config_path=repo / CONFIG, global_vault=vault
    )

    hooks_dir = repo / ".git" / "hooks"
    assert first["hooks"] == {name: "created" for name in HOOK_NAMES}
    contents = {name: (hooks_dir / name).read_bytes() for name in HOOK_NAMES}
    for name, content in contents.items():
        assert content.startswith(b"#!/bin/sh\n")
        assert f'hooks run {name} "$@"'.encode() in content
        assert os.access(hooks_dir / name, os.X_OK)
    assert first["git_config"] == {
        "globalVault": vault.resolve().as_posix(),
        "root": ".",
        "config": CONFIG,
    }

    # The vault is remembered: a second install needs no --global-vault.
    second = install_hooks(repository_root=repo, config_path=repo / CONFIG)

    assert second["hooks"] == {name: "unchanged" for name in HOOK_NAMES}
    assert {name: (hooks_dir / name).read_bytes() for name in HOOK_NAMES} == contents
    status = hooks_status(repository_root=repo)
    assert status["installed"] == "all"
    assert all(entry["current"] for entry in status["hooks"].values())
    assert status["git_config"]["globalVault"] == vault.resolve().as_posix()
    # Nothing was written to the vault, and no tracked file changed.
    assert list(vault.iterdir()) == []
    assert git(repo, "status", "--porcelain").stdout == ""


def test_install_requires_a_vault_the_first_time(tmp_path: Path) -> None:
    repo, _vault = _project(tmp_path)

    with pytest.raises(FailureMemoryError) as error:
        install_hooks(repository_root=repo, config_path=repo / CONFIG)

    assert error.value.code == "global_vault_required"
    assert not (repo / ".git/hooks/post-checkout").exists()


def test_uninstall_removes_only_what_install_added(tmp_path: Path) -> None:
    repo, _vault = _installed(tmp_path)
    hooks_dir = repo / ".git" / "hooks"
    # A line the user added to a hook install created survives uninstall.
    with (hooks_dir / "post-merge").open("a", encoding="utf-8") as stream:
        stream.write("echo mine\n")

    result = uninstall_hooks(repository_root=repo)

    assert result["hooks"] == {
        "post-checkout": "deleted",
        "post-merge": "removed",
        "post-rewrite": "deleted",
    }
    assert not (hooks_dir / "post-checkout").exists()
    assert (hooks_dir / "post-merge").read_text(encoding="utf-8") == (
        "#!/bin/sh\necho mine\n"
    )
    assert sorted(result["git_config_removed"]) == [
        "akms-failure-memory.config",
        "akms-failure-memory.globalVault",
        "akms-failure-memory.root",
    ]
    assert hooks_status(repository_root=repo)["installed"] == "none"
    assert uninstall_hooks(repository_root=repo)["hooks"]["post-checkout"] == "absent"


def test_existing_hook_keeps_running_and_is_restored_exactly(tmp_path: Path) -> None:
    repo, vault = _refreshed(tmp_path)
    hook = repo / ".git" / "hooks" / "post-merge"
    original = (
        "#!/usr/bin/env bash\n"
        "# the user's own hook\n"
        'echo "user hook $1" >> "$(git rev-parse --git-dir)/user-hook.log"\n'
        "exit 0\n"
    )
    hook.write_text(original, encoding="utf-8")
    hook.chmod(0o750)

    result = install_hooks(
        repository_root=repo, config_path=repo / CONFIG, global_vault=vault
    )

    assert result["hooks"]["post-merge"] == "inserted"
    text = hook.read_text(encoding="utf-8")
    # The block sits right after the shebang, so the user's `exit 0` cannot skip it.
    assert text.startswith("#!/usr/bin/env bash\n# >>> akms-failure-memory hook >>>")
    assert text.endswith("# the user's own hook\n" + original.split("\n", 2)[2])
    assert hook.stat().st_mode & 0o777 == 0o750

    git(repo, "checkout", "-q", "-b", "topic")
    (repo / "src/alpha.py").write_text(_source("alpha", 7), encoding="utf-8")
    git(repo, "commit", "-q", "-am", "alpha 7")
    git(repo, "checkout", "-q", "main")
    before = _mirror(repo, "alpha").read_text(encoding="utf-8")
    merged = git(repo, "merge", "-q", "topic")

    assert (repo / ".git/user-hook.log").read_text(encoding="utf-8") == "user hook 0\n"
    assert any("1 mirror(s) refreshed" in line for line in _hook_lines(merged))
    assert _mirror(repo, "alpha").read_text(encoding="utf-8") != before

    uninstall_hooks(repository_root=repo)

    assert hook.read_text(encoding="utf-8") == original
    assert hook.stat().st_mode & 0o777 == 0o750


def test_new_hooks_are_owner_only_and_existing_modes_are_kept(tmp_path: Path) -> None:
    repo, vault = _refreshed(tmp_path)
    hooks_dir = repo / ".git" / "hooks"
    shared = hooks_dir / "post-merge"
    shared.write_text("#!/bin/sh\necho team\n", encoding="utf-8")
    shared.chmod(0o755)

    install_hooks(repository_root=repo, config_path=repo / CONFIG, global_vault=vault)

    for name in HOOK_NAMES:
        expected = 0o755 if name == "post-merge" else 0o700
        assert (hooks_dir / name).stat().st_mode & 0o777 == expected, name

    uninstall_hooks(repository_root=repo)

    assert shared.read_text(encoding="utf-8") == "#!/bin/sh\necho team\n"
    assert shared.stat().st_mode & 0o777 == 0o755


def test_hooks_it_cannot_compose_with_are_refused_untouched(tmp_path: Path) -> None:
    repo, vault = _refreshed(tmp_path)
    hooks_dir = repo / ".git" / "hooks"
    python_hook = hooks_dir / "post-rewrite"
    python_hook.write_text("#!/usr/bin/env python3\nprint('hi')\n", encoding="utf-8")
    python_hook.chmod(0o755)

    with pytest.raises(FailureMemoryError) as error:
        install_hooks(
            repository_root=repo, config_path=repo / CONFIG, global_vault=vault
        )

    assert error.value.code == "hook_unsupported"
    assert (
        python_hook.read_text(encoding="utf-8")
        == "#!/usr/bin/env python3\nprint('hi')\n"
    )
    # Nothing is half-installed: the other hooks were not created either.
    assert not (hooks_dir / "post-checkout").exists()
    assert not (hooks_dir / "post-merge").exists()

    python_hook.write_text("#!/bin/sh\necho disabled\n", encoding="utf-8")
    python_hook.chmod(0o644)
    with pytest.raises(FailureMemoryError) as error:
        install_hooks(
            repository_root=repo, config_path=repo / CONFIG, global_vault=vault
        )
    assert error.value.code == "hook_disabled"


def test_core_hooks_path_shared_hooks_and_worktrees(tmp_path: Path) -> None:
    repo, vault = _refreshed(tmp_path)
    shared = tmp_path / "shared-hooks"
    git(repo, "config", "core.hooksPath", str(shared))

    result = install_hooks(
        repository_root=repo, config_path=repo / CONFIG, global_vault=vault
    )

    assert Path(result["hooks_dir"]) == shared.absolute()
    assert sorted(path.name for path in shared.iterdir()) == sorted(HOOK_NAMES)
    assert not (repo / ".git/hooks/post-checkout").exists()
    assert hooks_status(repository_root=repo)["core_hooks_path"] == str(shared)

    # A linked worktree runs the same hooks and keeps its own refresh state.
    git(repo, "branch", "side")
    worktree = tmp_path / "side-worktree"
    git(repo, "worktree", "add", "-q", str(worktree), "side")
    assert hooks_status(repository_root=worktree)["installed"] == "all"
    assert _state(worktree) != _state(repo)

    # Another repository sharing the hooks directory never asked for them:
    # the hooks stay silent there and change nothing.
    other, _ = _project(tmp_path, "other")
    git(other, "config", "core.hooksPath", str(shared))
    git(other, "branch", "topic")
    switched = git(other, "checkout", "-q", "topic")
    assert _hook_lines(switched) == []
    assert not (other / MIRRORS).exists()


def test_tracked_hook_is_refused(tmp_path: Path) -> None:
    repo, vault = _refreshed(tmp_path)
    hooks_dir = repo / "githooks"
    hooks_dir.mkdir()
    (hooks_dir / "post-merge").write_text("#!/bin/sh\necho team\n", encoding="utf-8")
    (hooks_dir / "post-merge").chmod(0o755)
    git(repo, "add", "githooks")
    git(repo, "commit", "-q", "-m", "team hooks")
    git(repo, "config", "core.hooksPath", "githooks")

    with pytest.raises(FailureMemoryError) as error:
        install_hooks(
            repository_root=repo, config_path=repo / CONFIG, global_vault=vault
        )

    assert error.value.code == "hook_tracked"
    assert git(repo, "status", "--porcelain").stdout == ""


def test_cli_surface(tmp_path: Path, capsys) -> None:
    repo, vault = _refreshed(tmp_path)

    assert (
        main(["hooks", "install", "--repo", str(repo), "--global-vault", str(vault)])
        == 0
    )
    installed = json.loads(capsys.readouterr().out)
    assert installed["hooks"] == {name: "created" for name in HOOK_NAMES}
    assert main(["hooks", "status", "--repo", str(repo)]) == 0
    assert json.loads(capsys.readouterr().out)["installed"] == "all"
    assert main(["hooks", "uninstall", "--repo", str(repo)]) == 0
    assert json.loads(capsys.readouterr().out)["action"] == "uninstall"

    # `hooks run` outside any repository still exits 0, with one line.
    outside = tmp_path / "not-a-repo"
    outside.mkdir()
    previous = Path.cwd()
    os.chdir(outside)
    try:
        assert main(["hooks", "run", "post-merge", "0"]) == 0
    finally:
        os.chdir(previous)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.strip().splitlines()) == 1
    assert "not_a_git_repository" in captured.err

    assert (
        main(
            [
                "refresh",
                "if-stale",
                "--repo",
                str(repo),
                "--global-vault",
                str(vault),
                "--generated-at",
                "2026-01-01T00:00:00Z",
            ]
        )
        == 2
    )
    assert "error[usage]" in capsys.readouterr().err


# ── hooks run: never blocks git ───────────────────────────────────────────


def test_hook_exits_zero_and_warns_once_on_a_broken_config(tmp_path: Path) -> None:
    repo, _vault = _installed(tmp_path)
    git(repo, "branch", "topic")
    (repo / CONFIG).write_text("this is = = not toml\n", encoding="utf-8")

    switched = git(repo, "checkout", "-q", "topic")

    lines = _hook_lines(switched)
    assert len(lines) == 1
    assert lines[0].startswith("failure-memory hook: skipped (")
    assert git(repo, "branch", "--show-current").stdout.strip() == "topic"


def test_hook_exits_zero_when_its_python_is_gone(tmp_path: Path) -> None:
    repo, _vault = _installed(tmp_path)
    hook = repo / ".git/hooks/post-checkout"
    hook.write_text(
        hook.read_text(encoding="utf-8").replace(
            Path(sys.executable).absolute().as_posix(), "/nonexistent/python"
        ),
        encoding="utf-8",
    )
    git(repo, "branch", "topic")

    switched = git(repo, "checkout", "-q", "topic")

    assert _hook_lines(switched) == [
        "failure-memory hook: skipped, its Python is gone; "
        "re-run failure-memory hooks install"
    ]


def test_opt_out_environment_variable(tmp_path: Path) -> None:
    repo, _vault = _installed(tmp_path)
    git(repo, "checkout", "-q", "-b", "topic")
    (repo / "src/alpha.py").write_text(_source("alpha", 9), encoding="utf-8")
    git(repo, "commit", "-q", "-am", "alpha 9")
    before = _mirror(repo, "alpha").read_bytes()
    environment = {**os.environ, OPT_OUT_ENV: "0"}

    switched = git(repo, "checkout", "-q", "main", env=environment)
    git(repo, "checkout", "-q", "topic", env=environment)

    assert _hook_lines(switched) == []
    assert _mirror(repo, "alpha").read_bytes() == before
    stream = io.StringIO()
    os.environ[OPT_OUT_ENV] = "0"
    try:
        assert run_hook("post-merge", ["0"], cwd=repo, stream=stream) == 0
    finally:
        del os.environ[OPT_OUT_ENV]
    assert stream.getvalue() == ""


def test_busy_lock_warns_and_skips(tmp_path: Path) -> None:
    repo, _vault = _installed(tmp_path)
    git(repo, "checkout", "-q", "-b", "topic")
    (repo / "src/alpha.py").write_text(_source("alpha", 5), encoding="utf-8")
    git(repo, "commit", "-q", "-am", "alpha 5")
    before = _mirror(repo, "alpha").read_bytes()
    config = load_project_config(repo / CONFIG)
    held, release = threading.Event(), threading.Event()

    def holder() -> None:
        with ProjectLock(config.resolve(repo, "lock")):
            held.set()
            release.wait(30)

    thread = threading.Thread(target=holder)
    thread.start()
    held.wait(30)
    try:
        stream = io.StringIO()
        head = git(repo, "rev-parse", "HEAD").stdout.strip()
        assert (
            run_hook("post-checkout", [head, head, "1"], cwd=repo, stream=stream) == 0
        )
    finally:
        release.set()
        thread.join()

    assert stream.getvalue().startswith(
        "failure-memory hook: skipped, another failure-memory command holds"
    )
    assert _mirror(repo, "alpha").read_bytes() == before


# ── what a refresh does ───────────────────────────────────────────────────


def test_lessons_recompile_only_when_the_registry_changed(tmp_path: Path) -> None:
    repo, vault = _project(tmp_path)
    first = refresh_if_stale(
        config_path=repo / CONFIG, repository_root=repo, global_vault=vault
    )
    assert first["stages"]["lessons"]["status"] == "recompiled"  # nothing compiled yet
    again = refresh_if_stale(
        config_path=repo / CONFIG, repository_root=repo, global_vault=vault
    )
    assert again["stages"]["lessons"]["status"] == "current"
    assert again["stages"]["graph"]["status"] == "current"

    install_hooks(repository_root=repo, config_path=repo / CONFIG, global_vault=vault)
    routes = repo / ".knowledge/generated/failure_routes.json"
    git(repo, "checkout", "-q", "-b", "lesson")
    _add_lesson(repo, "L001")
    git(repo, "commit", "-q", "-am", "record L001")
    node = (
        repo / ".knowledge/local-nodes/generated/failure-lessons/demo-failure-l001.md"
    )
    assert not node.exists()

    # Back to main: the registry did not change, so nothing is recompiled.
    routes_before = routes.stat().st_mtime_ns
    switched = git(repo, "checkout", "-q", "main")
    assert not any("lessons recompiled" in line for line in _hook_lines(switched))
    assert routes.stat().st_mtime_ns == routes_before

    # Onto the branch that records L001: its digest differs, so it compiles.
    switched = git(repo, "checkout", "-q", "lesson")
    assert any("lessons recompiled" in line for line in _hook_lines(switched))
    assert node.is_file()
    assert "demo-failure-l001" in routes.read_text(encoding="utf-8")

    # And back: the node goes away with the lesson.
    switched = git(repo, "checkout", "-q", "main")
    assert any("lessons recompiled" in line for line in _hook_lines(switched))
    assert not node.exists()


def test_checkout_refreshes_only_the_sources_that_changed(tmp_path: Path) -> None:
    repo, vault = _refreshed(tmp_path)
    main_head = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "checkout", "-q", "-b", "topic")
    (repo / "src/alpha.py").write_text(_source("alpha", 10), encoding="utf-8")
    (repo / "src/delta.py").write_text(_source("delta", 3), encoding="utf-8")
    git(repo, "rm", "-q", "src/gamma.py")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change alpha, add delta, drop gamma")
    beta = _mirror(repo, "beta").read_bytes()

    result = refresh_if_stale(
        config_path=repo / CONFIG,
        repository_root=repo,
        global_vault=vault,
        since=main_head,
    )

    mirror = result["stages"]["mirror"]
    assert mirror["selection"] == "changed"
    assert mirror["bases"] == [main_head]
    assert (mirror["written"], mirror["removed"]) == (2, 1)
    assert "return 10" in _mirror(repo, "alpha").read_text(encoding="utf-8")
    assert _mirror(repo, "delta").is_file()
    assert not _mirror(repo, "gamma").exists()
    assert _mirror(repo, "beta").read_bytes() == beta  # untouched
    assert result["stages"]["graph"]["status"] == "rebuilt"

    # Nothing changed since: no export, no graph rebuild.
    idle = refresh_if_stale(
        config_path=repo / CONFIG, repository_root=repo, global_vault=vault
    )
    assert idle["stages"]["mirror"]["status"] == "current"
    assert idle["stages"]["graph"]["status"] == "current"

    # The same through the installed hook, going back to main.
    install_hooks(repository_root=repo, config_path=repo / CONFIG, global_vault=vault)
    switched = git(repo, "checkout", "-q", "main")
    assert _hook_lines(switched)[0].startswith(
        "failure-memory: 2 mirror(s) refreshed, 1 removed; graph rebuilt ["
    )
    assert _mirror(repo, "gamma").is_file()
    assert not _mirror(repo, "delta").exists()
    assert _mirror(repo, "beta").read_bytes() == beta

    # A file checkout (`git checkout <ref> -- <path>`) is not a branch switch.
    restored = git(repo, "checkout", "topic", "--", "src/alpha.py")
    assert _hook_lines(restored) == []


def test_full_refresh_when_there_is_no_base_and_it_says_why(tmp_path: Path) -> None:
    repo, vault = _project(tmp_path)

    first = refresh_if_stale(
        config_path=repo / CONFIG, repository_root=repo, global_vault=vault
    )
    assert first["stages"]["mirror"]["selection"] == "full"
    assert first["stages"]["mirror"]["reason"] == "there are no code mirrors yet"

    _state(repo).unlink()
    second = refresh_if_stale(
        config_path=repo / CONFIG, repository_root=repo, global_vault=vault
    )
    assert second["stages"]["mirror"]["selection"] == "full"
    assert "no base commit" in second["stages"]["mirror"]["reason"]

    (repo / ".gitignore").write_text(GITIGNORE + "src/beta.py\n", encoding="utf-8")
    third = refresh_if_stale(
        config_path=repo / CONFIG, repository_root=repo, global_vault=vault
    )
    assert third["stages"]["mirror"]["selection"] == "full"
    assert ".gitignore" in third["stages"]["mirror"]["reason"]
    assert not _mirror(repo, "beta").exists()  # the full refresh pruned it


def test_rebase_refreshes_once_after_the_rewrite(tmp_path: Path) -> None:
    repo, _vault = _installed(tmp_path)
    git(repo, "checkout", "-q", "-b", "topic")
    for value in (20, 21, 22):
        (repo / "src/alpha.py").write_text(_source("alpha", value), encoding="utf-8")
        git(repo, "commit", "-q", "-am", f"alpha {value}")
    git(repo, "checkout", "-q", "main")
    (repo / "src/beta.py").write_text(_source("beta", 30), encoding="utf-8")
    git(repo, "commit", "-q", "-am", "beta 30")
    git(repo, "checkout", "-q", "topic")

    rebased = git(repo, "rebase", "main")

    # post-checkout at the start of the rebase is skipped and the per-commit
    # steps run no hook; post-rewrite refreshes once, at the end.
    lines = _hook_lines(rebased)
    assert len(lines) == 1, rebased.stderr
    # alpha's commits were rewritten (new commit times) and beta came from main.
    assert lines[0].startswith("failure-memory: 2 mirror(s) refreshed")
    assert "return 30" in _mirror(repo, "beta").read_text(encoding="utf-8")
    assert "return 22" in _mirror(repo, "alpha").read_text(encoding="utf-8")

    from akms.graph.mirror_freshness import stale_mirrors

    assert stale_mirrors(repo) == []

    # An amend refreshes what the amended commit touches.
    (repo / "src/gamma.py").write_text(_source("gamma", 40), encoding="utf-8")
    amended = git(repo, "commit", "-q", "-a", "--amend", "--no-edit")
    assert any("mirror(s) refreshed" in line for line in _hook_lines(amended))
    assert "return 40" in _mirror(repo, "gamma").read_text(encoding="utf-8")
    assert stale_mirrors(repo) == []


def test_hooks_wait_while_a_rebase_is_in_progress(tmp_path: Path) -> None:
    repo, _vault = _installed(tmp_path)
    state_before = _state(repo).read_bytes()
    (repo / ".git/rebase-merge").mkdir()
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    stream = io.StringIO()

    assert run_hook("post-checkout", [head, head, "1"], cwd=repo, stream=stream) == 0
    assert run_hook("post-rewrite", ["amend"], cwd=repo, stream=stream) == 0

    assert stream.getvalue() == ""
    assert _state(repo).read_bytes() == state_before


def test_refresh_rejects_misplaced_options(tmp_path: Path) -> None:
    repo, vault = _project(tmp_path)

    with pytest.raises(FailureMemoryError) as error:
        refresh_project(
            action="if-stale",
            config_path=repo / CONFIG,
            repository_root=repo,
            global_vault=vault,
            generated_at="2026-01-01T00:00:00Z",
        )
    assert error.value.code == "usage"

    with pytest.raises(FailureMemoryError) as error:
        refresh_project(
            action="status",
            config_path=repo / CONFIG,
            repository_root=repo,
            global_vault=vault,
            since="HEAD",
        )
    assert error.value.code == "usage"


def test_if_stale_stamps_the_current_time(tmp_path: Path) -> None:
    from datetime import datetime, timedelta, timezone

    repo, vault = _project(tmp_path)
    before = datetime.now(timezone.utc).replace(microsecond=0)

    result = refresh_if_stale(
        config_path=repo / CONFIG, repository_root=repo, global_vault=vault
    )

    stamped = datetime.fromisoformat(result["generated_at"])
    assert stamped.tzinfo is not None and stamped.utcoffset() == timedelta(0)
    assert before <= stamped <= datetime.now(timezone.utc)
    assert f'generated_at: "{result["generated_at"]}"' in _mirror(
        repo, "alpha"
    ).read_text(encoding="utf-8")


def test_a_failed_run_is_caught_up_by_the_next(tmp_path: Path, monkeypatch) -> None:
    import akms_failure_memory.refresh as refresh

    repo, vault = _refreshed(tmp_path)
    graph = load_project_config(repo / CONFIG).resolve(repo, "graph")
    real_mirror, real_graph = refresh._mirror, refresh._graph

    def broken(*_args, **_kwargs):
        raise FailureMemoryError("simulated failure", code="mirror_failure")

    # The lessons recompile, then the mirror export fails: the graph now lags
    # the lessons, and the next run must rebuild it although nothing is stale.
    _add_lesson(repo, "L001")
    (repo / "src/alpha.py").write_text(_source("alpha", 50), encoding="utf-8")
    monkeypatch.setattr(refresh, "_mirror", broken)
    with pytest.raises(FailureMemoryError):
        refresh_if_stale(
            config_path=repo / CONFIG, repository_root=repo, global_vault=vault
        )
    monkeypatch.setattr(refresh, "_mirror", real_mirror)
    graph_before = graph.read_bytes()

    caught_up = refresh_if_stale(
        config_path=repo / CONFIG, repository_root=repo, global_vault=vault
    )

    assert caught_up["stages"]["lessons"]["status"] == "current"
    assert caught_up["stages"]["mirror"]["written"] == 1  # alpha, still pending
    assert caught_up["stages"]["graph"]["status"] == "rebuilt"
    assert b"demo-failure-l001" in graph.read_bytes() != graph_before

    # A failed graph build alone is retried too. (Committed first: a dirty
    # source differs from every base, so it is re-exported on every run.)
    git(repo, "commit", "-q", "-am", "L001 and alpha 50")
    refresh_if_stale(
        config_path=repo / CONFIG, repository_root=repo, global_vault=vault
    )
    _add_lesson(repo, "L002")
    git(repo, "commit", "-q", "-am", "L002")
    monkeypatch.setattr(refresh, "_graph", broken)
    with pytest.raises(FailureMemoryError):
        refresh_if_stale(
            config_path=repo / CONFIG, repository_root=repo, global_vault=vault
        )
    monkeypatch.setattr(refresh, "_graph", real_graph)

    retried = refresh_if_stale(
        config_path=repo / CONFIG, repository_root=repo, global_vault=vault
    )

    assert retried["stages"]["lessons"]["status"] == "current"
    assert retried["stages"]["mirror"]["status"] == "current"
    assert retried["stages"]["graph"]["status"] == "rebuilt"
    assert b"demo-failure-l002" in graph.read_bytes()
    idle = refresh_if_stale(
        config_path=repo / CONFIG, repository_root=repo, global_vault=vault
    )
    assert idle["stages"]["graph"]["status"] == "current"
