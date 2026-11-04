"""Single-writer export locks with ownership diagnostics and stale-lock recovery.

``--force-lock`` never steals a live exporter's lock.
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from akms.repo_wiki.errors import RepoWikiError

DEFAULT_LOCK_NAME: Final = "export-akms"
LOCK_DIR_RELATIVE: Final = ".repo_wiki/locks"
OUTPUT_LOCK_FILENAME: Final = ".repo2md-export.lock"
OUTPUT_LOCK_PREFIX: Final = ".repo2md-export-"
# Fallback when process liveness cannot be checked (foreign host / restricted OS).
DEFAULT_STALE_SECONDS: Final = 6 * 60 * 60
# Holders killed (SIGKILL) between create and write leave empty locks; reclaim after a short grace.
UNREADABLE_STALE_SECONDS: Final = 5.0
_EXPORTER_MARKERS: Final = (
    "export-akms",
    "repo-wiki",
    "akms.repo_wiki",
    "akms/repo_wiki",
    # The standalone repo2md distribution, which predates this module.
    "repo2md.cli",
    "repo2md.export",
    "repo2md/export",
)


class LockError(RepoWikiError):
    """Raised when an export lock cannot be acquired safely."""


@dataclass(frozen=True, slots=True)
class LockOwnership:
    """Identity recorded inside a held export lock file."""

    pid: int
    hostname: str
    user: str
    acquired_at: str
    lock_name: str
    purpose: str
    # Best-effort process fingerprint (PID reuse guard); optional so older lock files still read.
    process_started_at: str | None = None
    cmdline_fingerprint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LockOwnership:
        started = data.get("process_started_at")
        cmdline = data.get("cmdline_fingerprint")
        return cls(
            pid=int(data["pid"]),
            hostname=str(data["hostname"]),
            user=str(data["user"]),
            acquired_at=str(data["acquired_at"]),
            lock_name=str(data["lock_name"]),
            purpose=str(data.get("purpose", data["lock_name"])),
            process_started_at=None if started in (None, "") else str(started),
            cmdline_fingerprint=None if cmdline in (None, "") else str(cmdline),
        )

    def describe(self) -> str:
        parts = [
            f"pid={self.pid}",
            f"host={self.hostname}",
            f"user={self.user}",
            f"acquired_at={self.acquired_at}",
            f"purpose={self.purpose}",
        ]
        if self.process_started_at:
            parts.append(f"started={self.process_started_at}")
        return " ".join(parts)


def lock_path(repo_root: Path, name: str = DEFAULT_LOCK_NAME) -> Path:
    """Return a repository-local lock path (legacy helper for diagnostics/tests)."""

    safe = name.replace("/", "-").replace("\\", "-")
    if not safe or safe in {".", ".."} or ".." in Path(safe).parts:
        raise ValueError(f"invalid lock name: {name!r}")
    return Path(repo_root).resolve() / LOCK_DIR_RELATIVE / f"{safe}.lock"


def output_lock_path(output_root: Path | str) -> Path:
    """Lock path for an output tree: sibling ``.repo2md-export-<16-hex>.lock`` (path hash)."""

    resolved = Path(output_root).resolve()
    digest = hashlib.sha256(os.fsencode(str(resolved))).hexdigest()[:16]
    return resolved.parent / f"{OUTPUT_LOCK_PREFIX}{digest}.lock"


def _current_user() -> str:
    return (
        os.environ.get("USER")
        or os.environ.get("USERNAME")
        or os.environ.get("LOGNAME")
        or "unknown"
    )


def _process_alive(pid: int) -> bool | None:
    """Return whether ``pid`` appears alive; ``None`` when liveness cannot be determined."""

    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def _process_identity(pid: int) -> tuple[str | None, str | None]:
    """Return ``(process_started_at, cmdline)`` via ``/proc`` or ``ps``; ``None`` if unavailable."""

    if pid <= 0:
        return None, None

    proc_dir = Path(f"/proc/{pid}")
    if proc_dir.is_dir():
        started: str | None = None
        cmdline: str | None = None
        try:
            # Field 22 (1-indexed) of /proc/<pid>/stat is starttime (clock ticks).
            stat_text = (proc_dir / "stat").read_text(
                encoding="utf-8", errors="replace"
            )
            # comm may contain spaces/parens; split after the closing paren.
            after_comm = stat_text.rsplit(")", 1)[-1].strip().split()
            # after_comm[0] is stat field 3 (state), so starttime (field 22) is index 19.
            if len(after_comm) >= 20:
                started = after_comm[19]
        except OSError:
            started = None
        try:
            raw = (proc_dir / "cmdline").read_bytes()
            cmdline = (
                raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
                or None
            )
        except OSError:
            cmdline = None
        return started, cmdline

    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["ps", "-p", str(pid), "-o", "lstart=", "-o", "command="],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None, None
    if completed.returncode != 0:
        return None, None
    line = completed.stdout.strip()
    if not line:
        return None, None
    parts = line.split()
    if len(parts) >= 6:
        started = " ".join(parts[:5])
        cmdline = " ".join(parts[5:]) or None
        return started, cmdline
    return line, None


def _self_process_identity() -> tuple[str | None, str | None]:
    started, cmdline = _process_identity(os.getpid())
    if not cmdline:
        cmdline = " ".join(sys.argv) if sys.argv else None
    return started, cmdline


def _normalize_cmdline(cmdline: str | None) -> str | None:
    if cmdline is None:
        return None
    collapsed = " ".join(cmdline.split())
    return collapsed or None


def _looks_like_exporter(cmdline: str | None, *, purpose: str) -> bool | None:
    """Whether cmdline appears to be this exporter; ``None`` when cmdline is unavailable."""

    if not cmdline:
        return None
    lower = cmdline.lower()
    if purpose and purpose.lower() in lower:
        return True
    return any(marker in lower for marker in _EXPORTER_MARKERS)


def _pid_reuse(
    ownership: LockOwnership,
    *,
    current_started: str | None,
    current_cmd: str | None,
) -> tuple[bool, str]:
    """Detect PID reuse by comparing process start tokens and cmdline fingerprints."""

    current_cmd = _normalize_cmdline(current_cmd)

    if (
        ownership.process_started_at
        and current_started
        and ownership.process_started_at != current_started
    ):
        return True, (
            f"PID reuse detected for pid={ownership.pid}: "
            f"lock started_at={ownership.process_started_at!r} "
            f"current started_at={current_started!r}"
        )

    if ownership.process_started_at and current_started:
        if ownership.process_started_at == current_started:
            return False, ""

    recorded = _normalize_cmdline(ownership.cmdline_fingerprint)
    if recorded and current_cmd:
        if recorded == current_cmd:
            return False, ""
        recorded_looks = _looks_like_exporter(recorded, purpose=ownership.purpose)
        current_looks = _looks_like_exporter(current_cmd, purpose=ownership.purpose)
        if recorded_looks is True and current_looks is False:
            return True, (
                f"PID reuse detected for pid={ownership.pid}: "
                f"live process command does not match export fingerprint "
                f"({current_cmd!r})"
            )
        # Different commands without a start-time match: fail closed (treat as held).
        return False, ""

    if recorded and current_cmd is None:
        return False, ""

    return False, ""


def _parse_ownership(path: Path) -> LockOwnership | None:
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        return LockOwnership.from_dict(data)
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None


def _is_stale(
    ownership: LockOwnership | None,
    *,
    path: Path,
    stale_seconds: float,
    hostname: str,
) -> tuple[bool, str]:
    """Decide whether an existing lock may be reclaimed as stale/dead/reused."""

    if ownership is None:
        try:
            age = time.time() - path.stat().st_mtime
        except OSError:
            age = stale_seconds + 1
        threshold = min(float(stale_seconds), UNREADABLE_STALE_SECONDS)
        if age >= threshold:
            return True, (
                f"unreadable or corrupt lock older than {threshold:.0f}s "
                f"(unreadable grace {UNREADABLE_STALE_SECONDS:.0f}s)"
            )
        return False, "unreadable or corrupt lock still within short grace window"

    if ownership.hostname == hostname:
        alive = _process_alive(ownership.pid)
        if alive is False:
            return True, f"owner process {ownership.pid} is not running on {hostname}"
        if alive is True:
            current_started, current_cmd = _process_identity(ownership.pid)
            reused, reuse_reason = _pid_reuse(
                ownership,
                current_started=current_started,
                current_cmd=current_cmd,
            )
            if reused:
                return True, reuse_reason
            return False, (
                f"owner process {ownership.pid} is still running on {hostname} "
                f"({ownership.describe()})"
            )

    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return True, "lock file disappeared during staleness check"
    if age >= stale_seconds:
        return True, (
            f"lock age {age:.0f}s exceeds stale threshold {stale_seconds:.0f}s "
            f"(owner {ownership.describe()})"
        )
    return False, f"lock is held by {ownership.describe()}"


def _is_live_matching_owner(
    ownership: LockOwnership | None,
    *,
    hostname: str,
) -> bool:
    """True when a same-host owner PID is alive and fingerprints still match."""

    if ownership is None or ownership.hostname != hostname:
        return False
    if _process_alive(ownership.pid) is not True:
        return False
    current_started, current_cmd = _process_identity(ownership.pid)
    reused, _reason = _pid_reuse(
        ownership,
        current_started=current_started,
        current_cmd=current_cmd,
    )
    return not reused


class RepoLocalLock:
    """Exclusive lock via ``O_CREAT | O_EXCL`` with stale-lock recovery.

    ``force=True`` reclaims only stale/dead/unreadable/expired locks, never a live matching owner's.
    """

    def __init__(
        self,
        repo_root: Path | str | None = None,
        *,
        name: str = DEFAULT_LOCK_NAME,
        stale_seconds: float = DEFAULT_STALE_SECONDS,
        force: bool = False,
        purpose: str = "export-akms",
        lock_file: Path | str | None = None,
    ) -> None:
        if lock_file is not None:
            self.path = Path(lock_file).resolve()
            self.repo_root = (
                Path(repo_root).resolve() if repo_root is not None else self.path.parent
            )
        elif repo_root is not None:
            self.repo_root = Path(repo_root).resolve()
            self.path = lock_path(self.repo_root, name)
        else:
            raise ValueError("RepoLocalLock requires lock_file or repo_root")
        self.name = name
        self.stale_seconds = float(stale_seconds)
        self.force = force
        self.purpose = purpose
        self._ownership: LockOwnership | None = None
        self._held = False
        self.reclaim_reason: str | None = None

    def acquire(self) -> LockOwnership:
        """Acquire the lock or raise :class:`LockError` with owner diagnostics."""

        if self._held:
            assert self._ownership is not None
            return self._ownership

        self.path.parent.mkdir(parents=True, exist_ok=True)
        started, cmdline = _self_process_identity()
        ownership = LockOwnership(
            pid=os.getpid(),
            hostname=socket.gethostname(),
            user=_current_user(),
            acquired_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            lock_name=self.name,
            purpose=self.purpose,
            process_started_at=started,
            cmdline_fingerprint=_normalize_cmdline(cmdline),
        )
        payload = (
            json.dumps(ownership.to_dict(), sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")

        # Exclusive create with the umask's ordinary file mode: other accounts
        # that share the checkout must be able to read the owner to judge liveness.
        try:
            handle = open(self.path, "xb")
        except FileExistsError:
            return self._acquire_existing(ownership, payload)
        try:
            with handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            self.path.unlink(missing_ok=True)
            raise
        self._ownership = ownership
        self._held = True
        return ownership

    def _acquire_existing(
        self, ownership: LockOwnership, payload: bytes
    ) -> LockOwnership:
        existing = _parse_ownership(self.path)
        hostname = ownership.hostname
        stale, reason = _is_stale(
            existing,
            path=self.path,
            stale_seconds=self.stale_seconds,
            hostname=hostname,
        )

        if not stale:
            if _is_live_matching_owner(existing, hostname=hostname):
                holder = (
                    existing.describe()
                    if existing is not None
                    else self.path.as_posix()
                )
                age = ""
                try:
                    seconds = max(0.0, time.time() - self.path.stat().st_mtime)
                    age = f" age={seconds:.0f}s"
                except OSError:
                    pass
                raise LockError(
                    f"export lock is held by a live writer ({holder});{age} "
                    f"path={self.path}. {reason}. "
                    f"--force-lock refuses to steal locks from live owners; "
                    f"wait for the export to finish or stop pid={existing.pid if existing else '?'}."
                )

            if self.force and existing is None:
                reason = "forced reclaim of unreadable/corrupt lock"
            elif self.force and existing is not None and existing.hostname != hostname:
                reason = f"forced reclaim of foreign-host lock ({existing.describe()})"
            elif not self.force:
                holder = (
                    existing.describe()
                    if existing is not None
                    else self.path.as_posix()
                )
                raise LockError(
                    f"export lock is held ({holder}); {reason}. "
                    f"If the owner crashed, wait for automatic staleness "
                    f"({self.stale_seconds:.0f}s / unreadable grace "
                    f"{UNREADABLE_STALE_SECONDS:.0f}s) or re-run with --force-lock "
                    f"only for dead/unreadable/expired locks (never against a live exporter)."
                )
            else:
                # force=True but not stale, unreadable or foreign: refuse (concurrent-writer risk).
                holder = (
                    existing.describe()
                    if existing is not None
                    else self.path.as_posix()
                )
                raise LockError(
                    f"export lock is held ({holder}); {reason}. "
                    f"--force-lock only reclaims stale, dead, unreadable, or expired locks."
                )

        diagnostic = (
            f"reclaiming {'forced' if self.force and not stale else 'stale'} lock at "
            f"{self.path}: {reason}"
        )
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise LockError(f"failed to remove stale lock {self.path}: {exc}") from exc
        try:
            handle = open(self.path, "xb")
        except FileExistsError as exc:
            competitor = _parse_ownership(self.path)
            detail = (
                competitor.describe() if competitor is not None else "unknown owner"
            )
            raise LockError(
                f"lost race reclaiming export lock ({detail}); original reason: {diagnostic}"
            ) from exc
        try:
            with handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            self.path.unlink(missing_ok=True)
            raise
        self._ownership = ownership
        self._held = True
        self.reclaim_reason = diagnostic
        return ownership

    def release(self) -> None:
        """Release the lock if this instance still owns it."""

        if not self._held:
            return
        try:
            current = _parse_ownership(self.path)
            if current is not None and self._ownership is not None:
                if (
                    current.pid == self._ownership.pid
                    and current.hostname == self._ownership.hostname
                    and current.acquired_at == self._ownership.acquired_at
                ):
                    self.path.unlink(missing_ok=True)
            elif self._ownership is not None:
                self.path.unlink(missing_ok=True)
        finally:
            self._held = False
            self._ownership = None

    def __enter__(self) -> LockOwnership:
        return self.acquire()

    def __exit__(self, *_exc: object) -> None:
        self.release()


BUILD_LOCK_NAME: Final = "repo-wiki-build"


def acquire_build_lock(
    repo_root: Path | str,
    *,
    wait_seconds: float = 0.0,
    poll_seconds: float = 0.2,
    on_wait: Any = None,
) -> RepoLocalLock:
    """Take the lock that serializes ``repo-wiki build`` runs, waiting up to *wait_seconds*.

    ``on_wait`` (if given) is called once, with the holder's description, when the lock
    is busy and the caller starts waiting. Raises :class:`LockError` when it stays busy.
    """
    lock = RepoLocalLock(repo_root, name=BUILD_LOCK_NAME, purpose="repo-wiki build")
    deadline = time.monotonic() + max(0.0, wait_seconds)
    waiting = False
    while True:
        try:
            lock.acquire()
            return lock
        except LockError as exc:
            holder = _parse_ownership(lock.path)
            who = holder.describe() if holder is not None else "unknown owner"
            if time.monotonic() >= deadline:
                raise LockError(
                    f"another repo-wiki build is running ({who}; lock {lock.path}); "
                    "try again when it finishes"
                ) from exc
            if not waiting and on_wait is not None:
                on_wait(who)
            waiting = True
            time.sleep(poll_seconds)
