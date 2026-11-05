"""Opt-in git hooks that keep the symbol graph and ``flows.json`` fresh.

``repo-wiki hooks install`` adds one marked block to each of the ``post-checkout``,
``post-commit``, ``post-merge`` and ``post-rewrite`` hooks in the directory git runs hooks
from (``git rev-parse --git-path hooks``, so ``core.hooksPath`` and linked worktrees are
respected). Nothing is installed until that command is run.

The block runs ``python -m akms.repo_wiki.hooks run <hook> "$@"``, which decides in a few
milliseconds whether this git command should refresh the graph (see :func:`should_refresh`)
and, if so, records a pending refresh and starts a detached worker. The git command never
waits for the build and never fails because of it. The worker runs the incremental build
(``build --changed-only --no-summaries --no-index``) under the build lock and keeps going
while refreshes are pending, so a burst of git commands costs one or two builds, not one per
command. Its output goes to ``.repo_wiki/hooks/build.log``.

Composition follows the failure-memory hooks: a missing hook is created (mode 0700) holding
only the block; an existing POSIX shell hook gets the block right after its ``#!`` line;
everything outside the markers is kept byte for byte; symlinked, non-shell, non-executable
and tracked hooks are refused. Each tool has its own markers, so either can be installed or
removed without touching the other's block. The repo-wiki root is recorded in the
repository's git config (``akms-repo-wiki.root``), never in a tracked file.

Set ``AKMS_REPO_WIKI_HOOKS=0`` to skip the hooks for one command or a whole shell.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from akms.repo_wiki.errors import RepoWikiError

HOOK_NAMES = ("post-checkout", "post-commit", "post-merge", "post-rewrite")
OPT_OUT_ENV = "AKMS_REPO_WIKI_HOOKS"
#: Run the worker in the hook's own process instead of detached (tests, debugging).
SYNC_ENV = "AKMS_REPO_WIKI_HOOKS_SYNC"
GIT_CONFIG_KEY = "akms-repo-wiki.root"
STATE_DIR = ".repo_wiki/hooks"
LOG_NAME = "build.log"
PENDING_NAME = "pending"
WORKER_LOCK_NAME = "repo-wiki-hooks-worker"
#: The log is rotated to ``build.log.1`` when it grows past this many bytes.
LOG_LIMIT = 512 * 1024
_BEGIN = "# >>> akms-repo-wiki hook >>>"
_END = "# <<< akms-repo-wiki hook <<<"
_CREATED = "# akms-repo-wiki created this file."
_SHEBANG = "#!/bin/sh\n"
_SHELLS = frozenset({"sh", "bash", "dash", "ash", "ksh", "mksh", "zsh"})
_NEW_HOOK_MODE = 0o700
#: Git variables that pin a repository location; a detached worker must not inherit
#: them (a hook can see a temporary index that is gone by the time the build runs).
_GIT_LOCATION_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_PREFIX",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_QUARANTINE_PATH",
)


class HookError(RepoWikiError):
    """A hook cannot be installed or removed safely; ``code`` names the reason."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


# ----------------------------------------------------------------- git plumbing


def _git(cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(cwd), *arguments],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HookError(f"git is unavailable: {exc}", "git") from exc


def _toplevel(path: Path) -> Path:
    completed = _git(path, "rev-parse", "--show-toplevel")
    if completed.returncode != 0 or not completed.stdout.strip():
        raise HookError(f"{path} is not inside a git worktree", "not_a_git_repository")
    return Path(completed.stdout.strip()).resolve()


def _git_path(top: Path, name: str) -> Path | None:
    raw = _git(top, "rev-parse", "--git-path", name).stdout.strip()
    if not raw:
        return None
    return Path(raw) if Path(raw).is_absolute() else top / raw


def hooks_directory(top: Path) -> Path:
    """The directory git runs hooks from (honours ``core.hooksPath``)."""
    path = _git_path(top, "hooks")
    if path is None:
        raise HookError("git did not report a hooks directory", "git")
    return path.absolute()


def _recorded_root(top: Path) -> str | None:
    completed = _git(top, "config", "--get", GIT_CONFIG_KEY)
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _is_tracked(top: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(top)
    except ValueError:
        return False
    completed = _git(top, "ls-files", "--error-unmatch", "--", str(path.resolve()))
    return completed.returncode == 0


# ------------------------------------------------------------ when to refresh


def _locate(path: Path) -> tuple[Path, Path]:
    """``(worktree top, this worktree's git directory)`` in one git call."""
    completed = _git(path, "rev-parse", "--show-toplevel", "--absolute-git-dir")
    lines = completed.stdout.strip().splitlines()
    if completed.returncode != 0 or len(lines) != 2:
        raise HookError(f"{path} is not inside a git worktree", "not_a_git_repository")
    return Path(lines[0]).resolve(), Path(lines[1])


def _last_reflog_action(git_dir: Path) -> str:
    """The message of HEAD's newest reflog entry (``commit (amend): ...``), or ``""``."""
    try:
        with (git_dir / "logs" / "HEAD").open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - 4096))
            tail = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    lines = [line for line in tail.splitlines() if line.strip()]
    return lines[-1].split("\t", 1)[1] if lines and "\t" in lines[-1] else ""


def _rebasing(git_dir: Path) -> bool:
    """A rebase (either backend) or a ``git am`` is in progress."""
    return (git_dir / "rebase-merge").is_dir() or (git_dir / "rebase-apply").is_dir()


def _sequence_has_more(git_dir: Path) -> bool:
    """A multi-commit cherry-pick or revert still has commands after this one."""
    try:
        todo = (git_dir / "sequencer" / "todo").read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return False
    remaining = [
        line for line in todo.splitlines() if line.strip() and not line.startswith("#")
    ]
    return len(remaining) > 1


def should_refresh(git_dir: Path, hook: str, arguments: list[str]) -> tuple[bool, str]:
    """``(refresh?, reason)`` for one hook invocation: at most one refresh per git command.

    Reads only files in *git_dir* (no git subprocess), so it costs well under a
    millisecond. The cases follow git's measured hook order (git 2.54):

    * every hook is skipped while ``git bisect`` runs (each step would rebuild);
    * ``post-checkout`` only for a branch checkout that moved ``HEAD`` (flag ``1``, old and
      new commit differ), and not the checkout a rebase starts with;
    * ``post-commit`` not for the commits a rebase or ``git am`` makes (``post-rewrite``
      follows once), not for an amend (``post-rewrite amend`` follows), and not for all but
      the last commit of a multi-commit cherry-pick or revert (``sequencer/todo`` still
      lists more than the current command);
    * ``post-merge`` always (``git merge``, ``git pull``);
    * ``post-rewrite rebase`` always (once, at the end of the rebase); ``post-rewrite
      amend`` unless a rebase is paused (its own ``post-rewrite`` follows).
    """
    if (git_dir / "BISECT_START").exists():
        return False, "bisect in progress"
    if hook == "post-checkout":
        if len(arguments) < 3 or arguments[2] != "1":
            return False, "file checkout"
        if arguments[0] == arguments[1]:
            return False, "HEAD did not move"
        if _rebasing(git_dir):
            return False, "checkout inside a rebase"
        return True, "branch checkout"
    if hook == "post-commit":
        if _rebasing(git_dir):
            return False, "commit inside a rebase or am"
        if _last_reflog_action(git_dir).startswith("commit (amend)"):
            return False, "amend (post-rewrite follows)"
        if _sequence_has_more(git_dir):
            return False, "cherry-pick/revert sequence continues"
        return True, "commit"
    if hook == "post-merge":
        return True, "merge"
    if hook == "post-rewrite":
        kind = arguments[0] if arguments else ""
        if kind == "rebase":
            return True, "rebase finished"
        if _rebasing(git_dir):
            return False, "amend inside a rebase"
        return True, "amend"
    return False, "unknown hook"


# ------------------------------------------------------------------ the block


def _sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _python() -> str:
    # Not resolved: a virtual environment's interpreter is often a symlink to the base
    # one, which does not see the environment's packages.
    return Path(sys.executable).absolute().as_posix()


def render_block(hook: str, python: str, *, created: bool) -> str:
    quoted = _sh_quote(python)
    lines = [
        _BEGIN,
        "# Added by `repo-wiki hooks install`; `repo-wiki hooks uninstall` removes it.",
        "# It starts a background refresh of the repo-wiki symbol graph and never",
        f"# fails or waits for it. Set {OPT_OUT_ENV}=0 to skip it.",
        *([_CREATED] if created else []),
        f'if [ "${{{OPT_OUT_ENV}:-1}}" != "0" ]; then',
        f"  if [ -x {quoted} ]; then",
        f'    {quoted} -m akms.repo_wiki.hooks run {hook} "$@" </dev/null || true',
        "  else",
        "    echo 'repo-wiki hook: skipped, its Python is gone; "
        "re-run repo-wiki hooks install' >&2",
        "  fi",
        "fi",
        _END,
    ]
    return "\n".join(lines) + "\n"


def _find_block(text: str, path: Path) -> tuple[int, int] | None:
    """Character span of the managed block (end exclusive), or None."""
    begins = [
        m.start() for m in re.finditer(rf"^{re.escape(_BEGIN)}[ \t]*\r?$", text, re.M)
    ]
    ends = [m.end() for m in re.finditer(rf"^{re.escape(_END)}[ \t]*\r?$", text, re.M)]
    if not begins and not ends:
        return None
    if len(begins) != 1 or len(ends) != 1 or ends[0] < begins[0]:
        raise HookError(
            f"{path} has damaged akms-repo-wiki markers; fix them by hand",
            "hook_block_damaged",
        )
    end = ends[0]
    if text.startswith("\n", end):
        end += 1
    elif text.startswith("\r\n", end):
        end += 2
    return begins[0], end


def _shell_shebang(first_line: str) -> bool:
    if not first_line.startswith("#!"):
        return False
    words = first_line[2:].strip().split()
    if not words:
        return False
    program = PurePosixPath(words[0]).name
    if program == "env":
        program = next((word for word in words[1:] if not word.startswith("-")), "")
    return PurePosixPath(program).name in _SHELLS


def _read_hook(path: Path, hook: str) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HookError(
            f"{path} is not a text file; call `python -m akms.repo_wiki.hooks run "
            f'{hook} "$@"` from it by hand',
            "hook_unsupported",
        ) from exc


def _write_hook(path: Path, text: str, *, mode: int | None) -> None:
    """Write atomically; an existing hook keeps ``mode``, a new one is 0o700."""
    temporary = path.with_name(f".{path.name}.repo-wiki-{os.getpid()}.tmp")
    temporary.write_bytes(text.encode("utf-8"))
    os.chmod(temporary, _NEW_HOOK_MODE if mode is None else mode)
    os.replace(temporary, path)


def _planned_install(
    top: Path, path: Path, hook: str, python: str
) -> tuple[str, str | None, int | None]:
    """(outcome, new text or None for no write, mode to keep)."""
    by_hand = f'call `python -m akms.repo_wiki.hooks run {hook} "$@"` from it by hand'
    if path.is_symlink():
        raise HookError(f"{path} is a symlink; {by_hand}", "hook_unsupported")
    if not path.exists():
        return "created", _SHEBANG + render_block(hook, python, created=True), None
    if not path.is_file():
        raise HookError(f"{path} is not a file", "hook_unsupported")
    if _is_tracked(top, path):
        raise HookError(
            f"{path} is tracked by git; installing would put this machine's paths "
            "in a committed file",
            "hook_tracked",
        )
    text = _read_hook(path, hook)
    mode = stat.S_IMODE(path.stat().st_mode)
    span = _find_block(text, path)
    if span is not None:
        created = _CREATED in text[span[0] : span[1]]
        new = (
            text[: span[0]]
            + render_block(hook, python, created=created)
            + text[span[1] :]
        )
        return ("unchanged", None, mode) if new == text else ("updated", new, mode)
    first, newline, rest = text.partition("\n")
    if not _shell_shebang(first):
        raise HookError(
            f"{path} is not a POSIX shell script; {by_hand}", "hook_unsupported"
        )
    if not os.access(path, os.X_OK):
        raise HookError(
            f"{path} is not executable, so git does not run it; make it executable "
            "or remove it, then install again",
            "hook_disabled",
        )
    block = render_block(hook, python, created=False)
    return "inserted", first + (newline or "\n") + block + rest, mode


# ------------------------------------------------------------------- commands


def _root_setting(top: Path, repo_root: Path) -> str:
    root = repo_root.resolve()
    try:
        return root.relative_to(top).as_posix() or "."
    except ValueError as exc:
        raise HookError(
            f"{root} is outside the git worktree {top}", "not_a_git_repository"
        ) from exc


def install_hooks(repo_root: Path) -> dict[str, Any]:
    """Install the four hook blocks idempotently and record the repo-wiki root."""
    top = _toplevel(repo_root)
    setting = _root_setting(top, repo_root)
    directory = hooks_directory(top)
    python = _python()
    plans = {
        hook: (directory / hook, *_planned_install(top, directory / hook, hook, python))
        for hook in HOOK_NAMES
    }
    completed = _git(top, "config", "--local", GIT_CONFIG_KEY, setting)
    if completed.returncode != 0:
        raise HookError(f"git config failed: {completed.stderr.strip()}", "git")
    directory.mkdir(parents=True, exist_ok=True)
    outcomes = {}
    for hook, (path, outcome, text, mode) in plans.items():
        if text is not None:
            _write_hook(path, text, mode=mode)
        outcomes[hook] = outcome
    return {
        "status": "ok",
        "action": "install",
        "hooks_dir": directory.as_posix(),
        "hooks": outcomes,
        "python": python,
        "root": setting,
    }


def uninstall_hooks(repo_root: Path) -> dict[str, Any]:
    """Remove exactly the blocks install added, and the recorded root."""
    top = _toplevel(repo_root)
    directory = hooks_directory(top)
    outcomes = {}
    for hook in HOOK_NAMES:
        path = directory / hook
        if path.is_symlink() or not path.is_file():
            outcomes[hook] = "absent"
            continue
        text = _read_hook(path, hook)
        span = _find_block(text, path)
        if span is None:
            outcomes[hook] = "absent"
            continue
        created = _CREATED in text[span[0] : span[1]]
        rest = text[: span[0]] + text[span[1] :]
        if created and rest == _SHEBANG:
            path.unlink()
            outcomes[hook] = "deleted"
        else:
            _write_hook(path, rest, mode=stat.S_IMODE(path.stat().st_mode))
            outcomes[hook] = "removed"
    removed = (
        _git(top, "config", "--local", "--unset-all", GIT_CONFIG_KEY).returncode == 0
    )
    return {
        "status": "ok",
        "action": "uninstall",
        "hooks_dir": directory.as_posix(),
        "hooks": outcomes,
        "root_setting_removed": removed,
    }


def _state_dir(root: Path) -> Path:
    return root / STATE_DIR


def hooks_status(repo_root: Path) -> dict[str, Any]:
    """Each hook's state, the recorded root and the background worker's last activity."""
    top = _toplevel(repo_root)
    directory = hooks_directory(top)
    python = _python()
    hooks: dict[str, Any] = {}
    for hook in HOOK_NAMES:
        path = directory / hook
        entry: dict[str, Any] = {
            "path": path.as_posix(),
            "exists": path.is_file(),
            "installed": False,
            "current": False,
        }
        if path.is_file() and not path.is_symlink():
            try:
                text = _read_hook(path, hook)
                span = _find_block(text, path)
            except HookError as exc:
                entry["error"] = {"code": exc.code, "message": str(exc)}
                span, text = None, ""
            if span is not None:
                block = text[span[0] : span[1]]
                created = _CREATED in block
                entry.update(
                    installed=True,
                    created=created,
                    current=block == render_block(hook, python, created=created),
                )
        hooks[hook] = entry
    count = sum(1 for entry in hooks.values() if entry["installed"])
    setting = _recorded_root(top)
    root = top.joinpath(*PurePosixPath(setting).parts) if setting else repo_root
    log = _state_dir(root) / LOG_NAME
    last = None
    if log.is_file():
        lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
        last = lines[-1] if lines else None
    return {
        "status": "ok",
        "hooks_dir": directory.as_posix(),
        "installed": "all"
        if count == len(HOOK_NAMES)
        else ("none" if not count else "partial"),
        "hooks": hooks,
        "root": setting,
        "opted_out": os.environ.get(OPT_OUT_ENV) == "0",
        "pending": (_state_dir(root) / PENDING_NAME).exists(),
        "log": log.as_posix(),
        "last_log_line": last,
    }


# ------------------------------------------------------------ run and worker


def _log(root: Path, message: str) -> None:
    directory = _state_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LOG_NAME
    try:
        if path.stat().st_size > LOG_LIMIT:
            os.replace(path, directory / f"{LOG_NAME}.1")
    except OSError:
        pass
    stamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} pid={os.getpid()} {message}\n")


def _worker_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _GIT_LOCATION_VARS}


def _spawn_worker(root: Path) -> None:
    log = (_state_dir(root) / LOG_NAME).open("a", encoding="utf-8")
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": log,
        "stderr": subprocess.STDOUT,
        "close_fds": True,
        "cwd": str(root),
        "env": _worker_env(),
    }
    if os.name == "nt":  # pragma: no cover - exercised on Windows only
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            [sys.executable, "-m", "akms.repo_wiki.hooks", "worker", str(root)],
            **kwargs,
        )
    finally:
        log.close()


def run_hook(hook: str, arguments: list[str], *, cwd: Path | None = None) -> int:
    """Entry point of the installed hooks. Always returns 0 and never waits for a build."""
    if os.environ.get(OPT_OUT_ENV) == "0":
        return 0
    try:
        top, git_dir = _locate(cwd or Path.cwd())
        refresh, reason = should_refresh(git_dir, hook, arguments)
        if not refresh:
            return 0
        setting = _recorded_root(top)
        if setting is None:
            # Not installed for this repository (a shared core.hooksPath can run these
            # hooks in repositories that never asked for them).
            return 0
        root = top.joinpath(*PurePosixPath(setting).parts)
        _log(root, f"trigger {hook}: {reason}")
        (_state_dir(root) / PENDING_NAME).write_text(f"{hook}\n", encoding="utf-8")
        if os.environ.get(SYNC_ENV) == "1":
            work(root)
        else:
            _spawn_worker(root)
    except Exception as exc:  # noqa: BLE001 - a hook must never fail the git command
        print(
            f"repo-wiki hook: skipped ({type(exc).__name__}): {' '.join(str(exc).split())}",
            file=sys.stderr,
        )
    return 0


def work(root: Path) -> int:
    """Refresh while a refresh is pending; one worker at a time. Always returns 0."""
    from akms.repo_wiki.locking import LockError, RepoLocalLock
    from akms.repo_wiki.refresh import refresh_graph

    pending = _state_dir(root) / PENDING_NAME
    while pending.exists():
        lock = RepoLocalLock(root, name=WORKER_LOCK_NAME, purpose="repo-wiki hooks")
        try:
            lock.acquire()
        except LockError:
            return 0  # the running worker will see the pending refresh
        try:
            while pending.exists():
                pending.unlink(missing_ok=True)
                try:
                    result = refresh_graph(root)
                    _log(root, f"refreshed: {json.dumps(result, sort_keys=True)}")
                except Exception as exc:  # noqa: BLE001 - logged, never raised
                    _log(root, f"refresh failed: {type(exc).__name__}: {exc}")
        finally:
            lock.release()
        # A trigger may have landed between the last check and the release: loop.
    return 0


# ------------------------------------------------------------------------ CLI


def _render(result: dict[str, Any]) -> str:
    if "installed" in result and "action" not in result:
        lines = [
            f"repo-wiki hooks: {result['installed']} installed in {result['hooks_dir']}"
        ]
        for hook, entry in result["hooks"].items():
            state = "installed" if entry["installed"] else "not installed"
            if entry["installed"] and not entry["current"]:
                state += " (outdated: run repo-wiki hooks install)"
            if "error" in entry:
                state = f"error: {entry['error']['message']}"
            lines.append(f"  {hook}: {state}")
        if result.get("opted_out"):
            lines.append(f"  {OPT_OUT_ENV}=0 is set: hooks are skipped in this shell")
        if result.get("last_log_line"):
            lines.append(f"  last: {result['last_log_line']}")
        return "\n".join(lines)
    lines = [f"repo-wiki hooks {result['action']}: {result['hooks_dir']}"]
    for hook, outcome in result["hooks"].items():
        lines.append(f"  {hook}: {outcome}")
    return "\n".join(lines)


def cli(action: str, repo_root: Path, *, as_json: bool) -> int:
    """``repo-wiki hooks install|uninstall|status``. Exit 0, or 1 with an error code."""
    commands = {
        "install": install_hooks,
        "uninstall": uninstall_hooks,
        "status": hooks_status,
    }
    try:
        result = commands[action](repo_root)
    except HookError as exc:
        print(f"repo-wiki hooks {action}: {exc}", file=sys.stderr)
        if as_json:
            payload = {
                "schema": "repo-wiki/error/v1",
                "error": {"code": exc.code, "message": str(exc)},
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
        return 1
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(_render(result))
    return 0


def main(argv: list[str] | None = None) -> int:
    """``python -m akms.repo_wiki.hooks run HOOK [ARGS...]`` or ``worker ROOT``."""
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) >= 2 and args[0] == "run":
        return run_hook(args[1], args[2:])
    if len(args) == 2 and args[0] == "worker":
        return work(Path(args[1]))
    print(
        "usage: python -m akms.repo_wiki.hooks run HOOK [ARGS...] | worker ROOT",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
