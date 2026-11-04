"""Git hooks that keep a project's generated lessons and code mirrors current.

``failure-memory hooks install`` adds one marked block to each of the
``post-checkout``, ``post-commit``, ``post-merge`` and ``post-rewrite`` hooks
in the directory git actually runs hooks from (``git rev-parse --git-path
hooks``, so ``core.hooksPath`` and linked worktrees are respected). The block
calls ``failure-memory hooks run <hook>``, which turns the hook's arguments
into a base commit and runs ``refresh if-stale``.

Composition: a hook that does not exist is created holding only the block. An
existing POSIX shell hook gets the block inserted right after its ``#!`` line,
so it runs whatever the rest of the hook does (an early ``exit`` included),
never reads the hook's stdin, and leaves ``$@`` untouched. Everything outside
the markers is kept byte for byte. Hooks in other languages, symlinked hooks,
hooks git would not run (not executable) and hooks tracked by git are refused
rather than edited. ``uninstall`` removes exactly the block, and deletes a
file only when install created it and nothing else was added since.

The machine-specific settings (global vault, project root, config path) live
in the repository's git config under ``akms-failure-memory.*``, never in a
tracked file.
"""

from __future__ import annotations

import logging
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path, PurePosixPath
from typing import Any, TextIO

from akms_failure_memory.config import load_project_config
from akms_failure_memory.errors import FailureMemoryError


HOOK_NAMES = ("post-checkout", "post-commit", "post-merge", "post-rewrite")
OPT_OUT_ENV = "AKMS_FAILURE_MEMORY_HOOKS"
GIT_CONFIG_SECTION = "akms-failure-memory"
_KEYS = ("globalVault", "root", "config")
_BEGIN = "# >>> akms-failure-memory hook >>>"
_END = "# <<< akms-failure-memory hook <<<"
_CREATED = "# akms-failure-memory created this file."
_SHEBANG = "#!/bin/sh\n"
_SHELLS = frozenset({"sh", "bash", "dash", "ash", "ksh", "mksh", "zsh"})
_DEFAULT_CONFIG = PurePosixPath(".knowledge/failure-memory.toml")
_PREFIX = "failure-memory hook"


# ── git plumbing ──────────────────────────────────────────────────────────


def _git(
    cwd: Path, *arguments: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(cwd), *arguments],
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise FailureMemoryError(f"git is unavailable: {exc}", code="git") from exc
    if check and completed.returncode != 0:
        raise FailureMemoryError(
            f"git {arguments[0]} failed: {completed.stderr.strip()}", code="git"
        )
    return completed


def _toplevel(path: Path) -> Path:
    completed = _git(path, "rev-parse", "--show-toplevel", check=False)
    if completed.returncode != 0 or not completed.stdout.strip():
        raise FailureMemoryError(
            f"{path} is not inside a git worktree", code="not_a_git_repository"
        )
    return Path(completed.stdout.strip()).resolve()


def hooks_directory(top: Path) -> Path:
    """The directory git runs hooks from (honours ``core.hooksPath``)."""
    raw = _git(top, "rev-parse", "--git-path", "hooks").stdout.strip()
    path = Path(raw)
    return (path if path.is_absolute() else top / path).absolute()


def _config_value(top: Path, key: str) -> str | None:
    completed = _git(top, "config", "--get", key, check=False)
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _get_setting(top: Path, key: str) -> str | None:
    return _config_value(top, f"{GIT_CONFIG_SECTION}.{key}")


def _set_setting(top: Path, key: str, value: str) -> None:
    _git(top, "config", "--local", f"{GIT_CONFIG_SECTION}.{key}", value)


def _unset_setting(top: Path, key: str) -> bool:
    completed = _git(
        top,
        "config",
        "--local",
        "--unset-all",
        f"{GIT_CONFIG_SECTION}.{key}",
        check=False,
    )
    return completed.returncode == 0


def _settings(top: Path) -> dict[str, str | None]:
    return {key: _get_setting(top, key) for key in _KEYS}


def _is_tracked(top: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(top)
    except ValueError:
        return False
    completed = _git(
        top, "ls-files", "--error-unmatch", "--", str(path.resolve()), check=False
    )
    return completed.returncode == 0


def _git_path(top: Path, name: str) -> Path | None:
    """``name`` inside this worktree's git directory, or None."""
    raw = _git(top, "rev-parse", "--git-path", name, check=False).stdout.strip()
    if not raw:
        return None
    return Path(raw) if Path(raw).is_absolute() else top / raw


def _in_progress_rebase(top: Path) -> bool:
    """A rebase (either backend) or a ``git am`` is in progress."""
    for name in ("rebase-merge", "rebase-apply"):
        path = _git_path(top, name)
        if path is not None and path.is_dir():
            return True
    return False


def _commit_base(top: Path) -> tuple[bool, str | None]:
    """(run?, base ref) for ``post-commit``, which git passes no arguments.

    Measured with git 2.54, post-commit runs for:

    * every commit a rebase makes, with ``rebase-merge/`` present; post-rewrite
      refreshes once at the end, so these are skipped (as is a ``git commit``
      while a rebase or ``git am`` is paused);
    * an amend, which post-rewrite(amend) follows; the reflog entry
      ``commit (amend)`` tells them apart, and the amend is left to it;
    * every commit a multi-commit cherry-pick or revert makes, with
      ``sequencer/`` present and the command being committed still listed in
      ``sequencer/todo``. No post-rewrite follows these, so all but the last
      are skipped and the last (one command left) refreshes from where the
      sequence started (``sequencer/head``). When the last command stopped on
      a conflict, git has already removed ``sequencer/`` by the time its
      commit is made, and the recorded refresh covers the earlier picks.
      ``CHERRY_PICK_HEAD`` is present for single picks too, so it says
      nothing about a sequence;
    * a commit that concludes a conflicted merge, cherry-pick or revert, after
      git removed ``MERGE_HEAD``/``CHERRY_PICK_HEAD``/``REVERT_HEAD``: a plain
      commit, refreshed from its first parent.

    A root commit has no parent: like a checkout after a clone, there is no
    base, so it is the recorded refresh's commit or a full export.
    """
    if _in_progress_rebase(top):
        return False, None
    action = _git(top, "reflog", "-1", "--format=%gs", "HEAD", check=False)
    if action.returncode == 0 and action.stdout.startswith("commit (amend)"):
        return False, None
    sequencer = _git_path(top, "sequencer")
    if sequencer is not None and sequencer.is_dir():
        try:
            todo = (sequencer / "todo").read_text(encoding="utf-8", errors="replace")
            start = (sequencer / "head").read_text(encoding="utf-8").strip()
        except OSError:
            todo, start = "", ""
        remaining = [
            line
            for line in todo.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        if len(remaining) > 1:
            return False, None
        if start:
            return True, start
    parent = _git(top, "rev-parse", "--verify", "--quiet", "HEAD^", check=False)
    return True, parent.stdout.strip() or None


# ── the hook block ────────────────────────────────────────────────────────


def _sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def _python() -> str:
    # Not resolved: a virtual environment's interpreter is often a symlink to
    # the base one, which does not see the environment's packages.
    return Path(sys.executable).absolute().as_posix()


def render_block(hook: str, python: str, *, created: bool) -> str:
    quoted = _sh_quote(python)
    lines = [
        _BEGIN,
        "# Added by `failure-memory hooks install`; `failure-memory hooks uninstall`",
        "# removes it. It refreshes stale failure-memory outputs and never fails",
        f"# the git command. Set {OPT_OUT_ENV}=0 to skip it.",
        *([_CREATED] if created else []),
        f'if [ "${{{OPT_OUT_ENV}:-1}}" != "0" ]; then',
        f"  if [ -x {quoted} ]; then",
        f'    {quoted} -m akms_failure_memory.cli hooks run {hook} "$@" </dev/null || true',
        "  else",
        f"    echo '{_PREFIX}: skipped, its Python is gone; "
        "re-run failure-memory hooks install' >&2",
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
        raise FailureMemoryError(
            f"{path} has damaged akms-failure-memory markers; fix them by hand",
            code="hook_block_damaged",
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


def _read_hook(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FailureMemoryError(
            f"{path} is not a text file; call `failure-memory hooks run "
            f"{path.name}` from it by hand",
            code="hook_unsupported",
        ) from exc


def _executable(path: Path) -> bool:
    return os.access(path, os.X_OK)


_NEW_HOOK_MODE = 0o700  # owner only: git runs hooks as the user who commits


def _write_hook(path: Path, text: str, *, mode: int | None) -> None:
    """Write atomically; an existing hook keeps ``mode``, a new one is 0o700."""
    temporary = path.with_name(f".{path.name}.akms-{os.getpid()}.tmp")
    temporary.write_bytes(text.encode("utf-8"))
    os.chmod(temporary, _NEW_HOOK_MODE if mode is None else mode)
    os.replace(temporary, path)


def _planned_install(
    top: Path, path: Path, hook: str, python: str
) -> tuple[str, str | None, int | None]:
    """(outcome, new text or None for no write, mode to keep)."""
    if path.is_symlink():
        raise FailureMemoryError(
            f"{path} is a symlink; add `failure-memory hooks run {hook} "
            '"$@"` to its target by hand',
            code="hook_unsupported",
        )
    if not path.exists():
        return "created", _SHEBANG + render_block(hook, python, created=True), None
    if not path.is_file():
        raise FailureMemoryError(f"{path} is not a file", code="hook_unsupported")
    if _is_tracked(top, path):
        raise FailureMemoryError(
            f"{path} is tracked by git; installing would put this machine's "
            "paths in a committed file",
            code="hook_tracked",
        )
    text = _read_hook(path)
    mode = stat.S_IMODE(path.stat().st_mode)
    span = _find_block(text, path)
    if span is not None:
        created = _CREATED in text[span[0] : span[1]]
        block = render_block(hook, python, created=created)
        new = text[: span[0]] + block + text[span[1] :]
        return ("unchanged", None, mode) if new == text else ("updated", new, mode)
    first, newline, rest = text.partition("\n")
    if not _shell_shebang(first):
        raise FailureMemoryError(
            f"{path} is not a POSIX shell script; call `failure-memory hooks run "
            f'{hook} "$@"` from it by hand',
            code="hook_unsupported",
        )
    if not _executable(path):
        raise FailureMemoryError(
            f"{path} is not executable, so git does not run it; make it "
            "executable or remove it, then install again",
            code="hook_disabled",
        )
    block = render_block(hook, python, created=False)
    return "inserted", first + (newline or "\n") + block + rest, mode


# ── commands ──────────────────────────────────────────────────────────────


def _project_root(top: Path, repository_root: str | Path) -> tuple[Path, str]:
    root = Path(repository_root).resolve(strict=True)
    try:
        relative = root.relative_to(top).as_posix()
    except ValueError as exc:
        raise FailureMemoryError(
            f"{root} is outside the git worktree {top}", code="not_a_git_repository"
        ) from exc
    return root, relative or "."


def _config_setting(root: Path, config_path: str | Path) -> tuple[Path, str]:
    config = Path(config_path)
    config = (config if config.is_absolute() else Path.cwd() / config).resolve()
    try:
        return config, config.relative_to(root).as_posix()
    except ValueError:
        return config, config.as_posix()


def install_hooks(
    *,
    repository_root: str | Path,
    config_path: str | Path,
    global_vault: str | Path | None = None,
) -> dict[str, Any]:
    """Install the hooks idempotently and record the vault in git config."""
    top = _toplevel(Path(repository_root))
    root, root_setting = _project_root(top, repository_root)
    config_file, config_setting = _config_setting(root, config_path)
    load_project_config(config_file)
    vault_value = (
        str(global_vault)
        if global_vault is not None
        else _get_setting(top, "globalVault")
    )
    if vault_value is None:
        raise FailureMemoryError(
            "hooks install needs --global-vault the first time",
            code="global_vault_required",
        )
    vault = Path(vault_value).expanduser().resolve()
    if not vault.is_dir():
        raise FailureMemoryError(
            f"Global vault {vault} is not a directory", code="global_vault_missing"
        )
    directory = hooks_directory(top)
    python = _python()
    plans = {
        hook: (directory / hook, *_planned_install(top, directory / hook, hook, python))
        for hook in HOOK_NAMES
    }
    _set_setting(top, "globalVault", vault.as_posix())
    _set_setting(top, "root", root_setting)
    _set_setting(top, "config", config_setting)
    directory.mkdir(parents=True, exist_ok=True)
    outcomes = {}
    for hook, (path, outcome, text, mode) in plans.items():
        if text is not None:
            _write_hook(path, text, mode=mode)
        outcomes[hook] = outcome
    warnings = []
    common = Path(_git(top, "rev-parse", "--git-common-dir").stdout.strip())
    common = (common if common.is_absolute() else top / common).resolve()
    if directory.resolve().is_relative_to(
        top
    ) and not directory.resolve().is_relative_to(common):
        warnings.append(
            f"the hooks directory {directory.as_posix()} is inside the worktree; "
            "keep the hook files untracked"
        )
    return {
        "status": "ok",
        "action": "install",
        "hooks_dir": directory.as_posix(),
        "hooks": outcomes,
        "python": python,
        "git_config": _settings(top),
        "warnings": warnings,
    }


def uninstall_hooks(*, repository_root: str | Path) -> dict[str, Any]:
    """Remove exactly what install added: the blocks and the git config keys."""
    top = _toplevel(Path(repository_root))
    directory = hooks_directory(top)
    outcomes = {}
    for hook in HOOK_NAMES:
        path = directory / hook
        if path.is_symlink() or not path.is_file():
            outcomes[hook] = "absent"
            continue
        text = _read_hook(path)
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
    removed = [key for key in _KEYS if _unset_setting(top, key)]
    return {
        "status": "ok",
        "action": "uninstall",
        "hooks_dir": directory.as_posix(),
        "hooks": outcomes,
        "git_config_removed": [f"{GIT_CONFIG_SECTION}.{key}" for key in removed],
    }


_PYTHON_IN_BLOCK = re.compile(r"^\s*if \[ -x '((?:[^']|'\"'\"')*)' \]; then\s*$", re.M)


def hooks_status(*, repository_root: str | Path) -> dict[str, Any]:
    """Report each hook and the recorded settings without changing anything."""
    top = _toplevel(Path(repository_root))
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
            "executable": path.is_file() and _executable(path),
        }
        if path.is_file() and not path.is_symlink():
            try:
                text = _read_hook(path)
                span = _find_block(text, path)
            except FailureMemoryError as exc:
                entry["error"] = {"code": exc.code, "message": str(exc)}
                span = None
                text = ""
            if span is not None:
                block = text[span[0] : span[1]]
                created = _CREATED in block
                match = _PYTHON_IN_BLOCK.search(block)
                recorded = match.group(1).replace("'\"'\"'", "'") if match else None
                entry.update(
                    installed=True,
                    created=created,
                    python=recorded,
                    python_exists=bool(recorded) and Path(recorded).is_file(),
                    current=block == render_block(hook, python, created=created),
                )
        hooks[hook] = entry
    count = sum(1 for entry in hooks.values() if entry["installed"])
    return {
        "status": "ok",
        "hooks_dir": directory.as_posix(),
        "core_hooks_path": _config_value(top, "core.hooksPath"),
        "installed": "all"
        if count == len(HOOK_NAMES)
        else "none"
        if not count
        else "partial",
        "hooks": hooks,
        "git_config": _settings(top),
        "opted_out": os.environ.get(OPT_OUT_ENV) == "0",
    }


# ── hooks run ─────────────────────────────────────────────────────────────


def _hook_base(top: Path, hook: str, arguments: list[str]) -> tuple[bool, str | None]:
    """(run?, base ref) for one hook invocation."""
    if hook == "post-checkout":
        # <previous HEAD> <new HEAD> <1 for a branch checkout, 0 for files>
        if len(arguments) < 3 or arguments[2] != "1":
            return False, None
        # `git rebase` checks out its base first; post-rewrite covers it.
        if _in_progress_rebase(top):
            return False, None
        return True, arguments[0]
    if hook == "post-commit":
        return _commit_base(top)
    if hook == "post-merge":
        return True, "ORIG_HEAD"
    if hook == "post-rewrite":
        kind = arguments[0] if arguments else ""
        if kind == "rebase":
            # Runs once, after the last commit is rewritten.
            return True, "ORIG_HEAD"
        # An amend while a rebase is paused; the rebase's own post-rewrite follows.
        if _in_progress_rebase(top):
            return False, None
        return True, "HEAD@{1}"
    return False, None


def _summary(result: dict[str, Any], seconds: float) -> str | None:
    stages = result["stages"]
    parts = []
    lessons = stages["lessons"]
    if lessons["status"] == "recompiled":
        counts = lessons.get("counts", {})
        parts.append(f"lessons recompiled ({counts.get('lessons', 0)} lessons)")
    mirror = stages["mirror"]
    if mirror["status"] == "refreshed" and (
        mirror["selection"] == "full" or mirror["written"] + mirror["removed"]
    ):
        text = f"{mirror['written']} mirror(s) refreshed"
        if mirror["removed"]:
            text += f", {mirror['removed']} removed"
        if mirror["selection"] == "full":
            text += f" (full refresh: {mirror['reason']})"
        parts.append(text)
    if stages["graph"]["status"] == "rebuilt":
        parts.append("graph rebuilt")
    for warning in result.get("warnings", []):
        parts.append(f"warning: {warning}")
    if not parts:
        return None
    return f"failure-memory: {'; '.join(parts)} [{seconds:.1f}s]"


def _one_line(message: object) -> str:
    return " ".join(str(message).split())


def run_hook(
    hook: str,
    arguments: list[str],
    *,
    cwd: str | Path | None = None,
    stream: TextIO | None = None,
) -> int:
    """Entry point of the installed hooks. Always returns 0.

    Prints nothing when there was nothing to do, one summary line when it
    refreshed something, and one warning line when it could not.
    """
    out = stream if stream is not None else sys.stderr
    if os.environ.get(OPT_OUT_ENV) == "0":
        return 0
    started = time.monotonic()
    previous_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        top = _toplevel(Path(cwd) if cwd is not None else Path.cwd())
        settings = _settings(top)
        if settings["globalVault"] is None:
            # Not installed for this repository: a shared core.hooksPath can
            # run these hooks in repositories that never asked for them.
            return 0
        should_run, base = _hook_base(top, hook, arguments)
        if not should_run:
            return 0
        root = top.joinpath(*PurePosixPath(settings["root"] or ".").parts)
        config = Path(settings["config"] or _DEFAULT_CONFIG.as_posix())
        config = config if config.is_absolute() else root / config
        from akms_failure_memory.refresh import refresh_if_stale

        result = refresh_if_stale(
            config_path=config,
            repository_root=root,
            global_vault=settings["globalVault"],
            since=base,
            lock_timeout_seconds=0,
        )
        line = _summary(result, time.monotonic() - started)
        if line:
            print(line, file=out)
    except FailureMemoryError as exc:
        if exc.code == "lock_contention":
            print(
                f"{_PREFIX}: skipped, another failure-memory command holds the "
                "project lock; run `failure-memory refresh if-stale` later",
                file=out,
            )
        else:
            print(f"{_PREFIX}: skipped ({exc.code}): {_one_line(exc)}", file=out)
    except Exception as exc:  # noqa: BLE001 - a hook must never fail the git command
        print(
            f"{_PREFIX}: skipped (internal_error): {type(exc).__name__}: {_one_line(exc)}",
            file=out,
        )
    finally:
        logging.disable(previous_disable)
    return 0


__all__ = [
    "GIT_CONFIG_SECTION",
    "HOOK_NAMES",
    "OPT_OUT_ENV",
    "hooks_directory",
    "hooks_status",
    "install_hooks",
    "render_block",
    "run_hook",
    "uninstall_hooks",
]
