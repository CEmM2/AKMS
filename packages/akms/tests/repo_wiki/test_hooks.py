"""Opt-in git hooks: install/uninstall/status, composition, skip logic and the worker.

Git runs here with an empty global configuration so a developer's own ``core.hooksPath``
or hooks cannot leak in. The failure-memory hook block (PR #62) is reproduced by a fixture
with the same format and placement rules, because ``akms`` must not import that package.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from akms.repo_wiki.cli import main
from akms.repo_wiki.hooks import (
    HOOK_NAMES,
    install_hooks,
    render_block,
    should_refresh,
    uninstall_hooks,
)

from .test_build_render_graph_summary import copy_fixture

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PYTHON = Path(sys.executable).absolute().as_posix()


@pytest.fixture(autouse=True)
def clean_git(tmp_path_factory: pytest.TempPathFactory, monkeypatch) -> None:
    empty = tmp_path_factory.mktemp("gitconfig") / "config"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_EDITOR", "true")
    monkeypatch.delenv("AKMS_REPO_WIKI_HOOKS", raising=False)
    monkeypatch.setenv("AKMS_REPO_WIKI_HOOKS_SYNC", "1")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture()
def repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    copy_fixture(FIXTURES / "flows_repo", tmp_path)
    (tmp_path / ".gitignore").write_text(".repo_wiki/\n", encoding="utf-8")
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "commit.gpgsign", "false")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "initial")
    assert (
        main(["--repo-root", str(tmp_path), "build", "--no-summaries", "--no-index"])
        == 0
    )
    capsys.readouterr()
    return tmp_path


def hooks_dir(repo: Path) -> Path:
    return repo / ".git" / "hooks"


def triggers(repo: Path) -> list[str]:
    log = repo / ".repo_wiki" / "hooks" / "build.log"
    if not log.exists():
        return []
    return [
        line.split(" trigger ", 1)[1]
        for line in log.read_text("utf-8").splitlines()
        if " trigger " in line
    ]


def commit_change(repo: Path, message: str, name: str = "pkg/loose.py") -> None:
    path = repo / name
    path.write_text(path.read_text("utf-8") + f"# {message}\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


# ------------------------------------------------- failure-memory block fixture

FM_BEGIN = "# >>> akms-failure-memory hook >>>"
FM_END = "# <<< akms-failure-memory hook <<<"
FM_CREATED = "# akms-failure-memory created this file."


def fm_block(hook: str, python: str, *, created: bool) -> str:
    """The block ``failure-memory hooks install`` writes (PR #62), byte for byte."""
    try:  # Use the real renderer when it is installed.
        from akms_failure_memory.hooks import render_block as real  # type: ignore

        return real(hook, python, created=created)
    except ImportError:
        pass
    quoted = "'" + python.replace("'", "'\"'\"'") + "'"
    lines = [
        FM_BEGIN,
        "# Added by `failure-memory hooks install`; `failure-memory hooks uninstall`",
        "# removes it. It refreshes stale failure-memory outputs and never fails",
        "# the git command. Set AKMS_FAILURE_MEMORY_HOOKS=0 to skip it.",
        *([FM_CREATED] if created else []),
        'if [ "${AKMS_FAILURE_MEMORY_HOOKS:-1}" != "0" ]; then',
        f"  if [ -x {quoted} ]; then",
        f'    {quoted} -m akms_failure_memory.cli hooks run {hook} "$@" </dev/null || true',
        "  else",
        "    echo 'failure-memory hook: skipped, its Python is gone; "
        "re-run failure-memory hooks install' >&2",
        "  fi",
        "fi",
        FM_END,
    ]
    return "\n".join(lines) + "\n"


def fm_install(directory: Path, python: str) -> None:
    """Failure-memory's placement rules: create with its marker, else insert after #!."""
    for hook in HOOK_NAMES:
        path = directory / hook
        if not path.exists():
            path.write_text("#!/bin/sh\n" + fm_block(hook, python, created=True))
            os.chmod(path, 0o700)
            continue
        text = path.read_text("utf-8")
        first, _, rest = text.partition("\n")
        mode = stat.S_IMODE(path.stat().st_mode)
        path.write_text(first + "\n" + fm_block(hook, python, created=False) + rest)
        os.chmod(path, mode)


def fm_uninstall(directory: Path) -> None:
    for hook in HOOK_NAMES:
        path = directory / hook
        text = path.read_text("utf-8")
        start = text.index(FM_BEGIN)
        end = text.index(FM_END) + len(FM_END) + 1
        created = FM_CREATED in text[start:end]
        rest = text[:start] + text[end:]
        if created and rest == "#!/bin/sh\n":
            path.unlink()
        else:
            mode = stat.S_IMODE(path.stat().st_mode)
            path.write_text(rest)
            os.chmod(path, mode)


def fake_fm_python(tmp_path: Path) -> str:
    """An executable standing in for failure-memory's Python: records each call."""
    script = tmp_path / "fm-python"
    record = tmp_path / "fm-calls.txt"
    script.write_text(f'#!/bin/sh\necho "$5" >> {record}\n', encoding="utf-8")
    os.chmod(script, 0o755)
    return script.as_posix()


# ------------------------------------------------------- install and status


def test_install_creates_owner_only_hooks_and_records_the_root(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--repo-root", str(repo), "hooks", "install", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["hooks"] == dict.fromkeys(HOOK_NAMES, "created")
    for hook in HOOK_NAMES:
        path = hooks_dir(repo) / hook
        assert stat.S_IMODE(path.stat().st_mode) == 0o700
        assert path.read_text("utf-8") == "#!/bin/sh\n" + render_block(
            hook, PYTHON, created=True
        )
    assert git(repo, "config", "--get", "akms-repo-wiki.root").strip() == "."
    assert install_hooks(repo)["hooks"] == dict.fromkeys(HOOK_NAMES, "unchanged")
    assert main(["--repo-root", str(repo), "hooks", "status", "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["installed"] == "all"
    assert all(entry["current"] for entry in status["hooks"].values())
    assert main(["--repo-root", str(repo), "hooks", "uninstall"]) == 0
    assert not any((hooks_dir(repo) / hook).exists() for hook in HOOK_NAMES)
    assert (
        subprocess.run(
            ["git", "-C", str(repo), "config", "--get", "akms-repo-wiki.root"],
            capture_output=True,
        ).returncode
        == 1
    )


def test_existing_shell_hook_keeps_its_content_and_mode(repo: Path) -> None:
    path = hooks_dir(repo) / "post-commit"
    original = "#!/usr/bin/env bash\nset -e\necho mine\nexit 0\n"
    path.write_text(original, encoding="utf-8")
    os.chmod(path, 0o750)
    assert install_hooks(repo)["hooks"]["post-commit"] == "inserted"
    text = path.read_text("utf-8")
    assert text.startswith("#!/usr/bin/env bash\n# >>> akms-repo-wiki hook >>>")
    assert text.endswith("echo mine\nexit 0\n")
    assert stat.S_IMODE(path.stat().st_mode) == 0o750
    assert uninstall_hooks(repo)["hooks"]["post-commit"] == "removed"
    assert path.read_text("utf-8") == original


@pytest.mark.parametrize(
    ("setup", "code"),
    [
        ("symlink", "hook_unsupported"),
        ("python", "hook_unsupported"),
        ("not_executable", "hook_disabled"),
        ("damaged", "hook_block_damaged"),
    ],
)
def test_unsafe_hooks_are_refused(
    repo: Path, capsys: pytest.CaptureFixture[str], setup: str, code: str
) -> None:
    path = hooks_dir(repo) / "post-merge"
    if setup == "symlink":
        target = repo / "elsewhere.sh"
        target.write_text("#!/bin/sh\n", encoding="utf-8")
        path.symlink_to(target)
    elif setup == "python":
        path.write_text("#!/usr/bin/env python3\nprint(1)\n", encoding="utf-8")
        os.chmod(path, 0o755)
    elif setup == "not_executable":
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        os.chmod(path, 0o644)
    else:
        path.write_text("#!/bin/sh\n# >>> akms-repo-wiki hook >>>\n", encoding="utf-8")
        os.chmod(path, 0o755)
    before = {h: (hooks_dir(repo) / h).exists() for h in HOOK_NAMES}
    assert main(["--repo-root", str(repo), "hooks", "install", "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == code
    # Nothing was written: the check runs for every hook before any write.
    assert {h: (hooks_dir(repo) / h).exists() for h in HOOK_NAMES} == before


def test_tracked_hooks_are_refused(repo: Path) -> None:
    (repo / "githooks").mkdir()
    tracked = repo / "githooks" / "post-commit"
    tracked.write_text("#!/bin/sh\n", encoding="utf-8")
    os.chmod(tracked, 0o755)
    git(repo, "add", "githooks/post-commit")
    git(repo, "commit", "-q", "-m", "hooks")
    git(repo, "config", "core.hooksPath", "githooks")
    from akms.repo_wiki.hooks import HookError

    with pytest.raises(HookError) as excinfo:
        install_hooks(repo)
    assert excinfo.value.code == "hook_tracked"


# ------------------------------------------- coexistence with failure-memory


@pytest.mark.parametrize("order", ["failure_memory_first", "repo_wiki_first"])
def test_both_tools_compose_and_remove_independently(
    repo: Path, tmp_path_factory: pytest.TempPathFactory, order: str
) -> None:
    scratch = tmp_path_factory.mktemp("fm")
    fm_python = fake_fm_python(scratch)
    directory = hooks_dir(repo)
    if order == "failure_memory_first":
        fm_install(directory, fm_python)
        install_hooks(repo)
    else:
        install_hooks(repo)
        fm_install(directory, fm_python)
    for hook in HOOK_NAMES:
        text = (directory / hook).read_text("utf-8")
        assert text.count(FM_BEGIN) == 1 and text.count("# >>> akms-repo-wiki") == 1
        assert stat.S_IMODE((directory / hook).stat().st_mode) == 0o700
    # Both blocks run on a commit.
    commit_change(repo, "both")
    assert (scratch / "fm-calls.txt").read_text("utf-8").split() == ["post-commit"]
    assert triggers(repo) == ["post-commit: commit"]

    # Removing one tool leaves the other's file byte-identical to a solo install.
    snapshot = {h: (directory / h).read_text("utf-8") for h in HOOK_NAMES}
    uninstall_hooks(repo)
    for hook in HOOK_NAMES:
        text = (directory / hook).read_text("utf-8")
        assert "akms-repo-wiki" not in text
        assert (
            fm_block(hook, fm_python, created=order == "failure_memory_first") in text
        )
    install_hooks(repo)
    fm_uninstall(directory)
    for hook in HOOK_NAMES:
        text = (directory / hook).read_text("utf-8")
        assert FM_BEGIN not in text
        # Reinstalled into an existing file, so it is an inserted block now.
        assert render_block(hook, PYTHON, created=False) in text
    del snapshot
    uninstall_hooks(repo)
    # Whatever is left is at most an empty shell hook, which git runs as a no-op.
    for hook in HOOK_NAMES:
        path = directory / hook
        assert not path.exists() or path.read_text("utf-8") == "#!/bin/sh\n"


# ------------------------------------------------------------- skip logic


def test_skip_logic_follows_git_commands(repo: Path) -> None:
    install_hooks(repo)
    commit_change(repo, "one")
    assert triggers(repo) == ["post-commit: commit"]
    git(repo, "commit", "-q", "--amend", "-m", "one, amended")
    assert triggers(repo)[1:] == ["post-rewrite: amend"]
    (repo / "pkg" / "loose.py").write_text("changed\n", encoding="utf-8")
    git(repo, "checkout", "--", "pkg/loose.py")  # a file checkout
    git(repo, "checkout", "-q", "-b", "side")  # HEAD does not move
    assert len(triggers(repo)) == 2
    for n in range(3):
        commit_change(repo, f"side {n}", name="pkg/helpers_a.py")
    git(repo, "checkout", "-q", "main")
    assert triggers(repo)[-1] == "post-checkout: branch checkout"
    count = len(triggers(repo))
    commit_change(repo, "main moves on", name="pkg/helpers_b.py")
    git(repo, "checkout", "-q", "side")
    git(repo, "rebase", "-q", "main")
    assert triggers(repo)[count + 2 :] == ["post-rewrite: rebase finished"]
    count = len(triggers(repo))
    git(repo, "checkout", "-q", "main")
    git(repo, "cherry-pick", "main..side")  # three picks
    assert triggers(repo)[count:] == [
        "post-checkout: branch checkout",
        "post-commit: commit",
    ]
    count = len(triggers(repo))
    git(repo, "checkout", "-q", "-b", "merge-me", "HEAD~1")
    commit_change(repo, "to merge", name="pkg/core.py")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-edit", "merge-me")
    assert triggers(repo)[count:] == [
        "post-checkout: branch checkout",
        "post-commit: commit",
        "post-checkout: branch checkout",
        "post-merge: merge",
    ]


def test_bisect_and_opt_out_skip_everything(repo: Path, monkeypatch) -> None:
    install_hooks(repo)
    for n in range(3):
        commit_change(repo, f"c{n}")
    count = len(triggers(repo))
    git(repo, "bisect", "start", "HEAD", "HEAD~3")
    git(repo, "bisect", "good")
    git(repo, "bisect", "reset")
    # Even the reset's checkout runs while BISECT_START exists; the graph was never
    # rebuilt during the bisect, so it still matches the branch it returns to.
    assert triggers(repo)[count:] == []
    monkeypatch.setenv("AKMS_REPO_WIKI_HOOKS", "0")
    count = len(triggers(repo))
    commit_change(repo, "quiet")
    assert len(triggers(repo)) == count


def test_should_refresh_reads_git_state_files(tmp_path: Path) -> None:
    git_dir = tmp_path
    assert should_refresh(git_dir, "post-commit", []) == (True, "commit")
    (git_dir / "logs").mkdir()
    (git_dir / "logs" / "HEAD").write_text(
        "a b T <t> 1 +0000\tcommit (amend): x\n", encoding="utf-8"
    )
    assert should_refresh(git_dir, "post-commit", [])[0] is False
    (git_dir / "logs" / "HEAD").write_text("a b T <t> 1 +0000\tcommit: y\n")
    (git_dir / "sequencer").mkdir()
    (git_dir / "sequencer" / "todo").write_text("pick a x\npick b y\n")
    assert should_refresh(git_dir, "post-commit", [])[0] is False
    (git_dir / "sequencer" / "todo").write_text("pick b y\n")
    assert should_refresh(git_dir, "post-commit", [])[0] is True
    assert should_refresh(git_dir, "post-checkout", ["a", "b", "0"])[0] is False
    assert should_refresh(git_dir, "post-checkout", ["a", "a", "1"])[0] is False
    assert should_refresh(git_dir, "post-checkout", ["a", "b", "1"])[0] is True
    (git_dir / "rebase-merge").mkdir()
    assert should_refresh(git_dir, "post-checkout", ["a", "b", "1"])[0] is False
    assert should_refresh(git_dir, "post-rewrite", ["amend"])[0] is False
    assert should_refresh(git_dir, "post-rewrite", ["rebase"])[0] is True
    (git_dir / "BISECT_START").write_text("main\n")
    assert should_refresh(git_dir, "post-merge", ["0"]) == (False, "bisect in progress")


def test_hooks_do_nothing_where_not_installed(
    repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """A shared core.hooksPath runs the block in repositories that never opted in."""
    install_hooks(repo)
    git(repo, "config", "--unset", "akms-repo-wiki.root")
    commit_change(repo, "no root recorded")
    assert triggers(repo) == []
    outside = tmp_path_factory.mktemp("not-git")
    result = subprocess.run(
        [sys.executable, "-m", "akms.repo_wiki.hooks", "run", "post-commit"],
        cwd=outside,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "repo-wiki hook: skipped" in result.stderr


# ----------------------------------------------------------------- worker


def test_sync_refresh_keeps_graph_and_flows_current(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    install_hooks(repo)
    core = repo / "pkg" / "core.py"
    core.write_text(core.read_text("utf-8") + "\n\ndef fresh():\n    return leaf(1)\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "add fresh")
    log = (repo / ".repo_wiki" / "hooks" / "build.log").read_text("utf-8")
    assert '"parsed": 1' in log
    assert main(["--repo-root", str(repo), "flow", "fresh", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["flows_source"]["source"] == "file"


def test_detached_worker_finishes_in_the_background(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AKMS_REPO_WIKI_HOOKS_SYNC")
    install_hooks(repo)
    started = time.monotonic()
    commit_change(repo, "background")
    elapsed = time.monotonic() - started
    log = repo / ".repo_wiki" / "hooks" / "build.log"
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if log.exists() and "refreshed:" in log.read_text("utf-8"):
            break
        time.sleep(0.1)
    assert "refreshed:" in log.read_text("utf-8")
    assert not (repo / ".repo_wiki" / "hooks" / "pending").exists()
    assert elapsed < 10  # the commit did not wait for the build
