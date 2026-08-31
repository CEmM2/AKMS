"""Project-local exclusive lock with safe stale-owner recovery."""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from pathlib import Path

from akms_failure_memory.errors import FailureMemoryError


class ProjectLock:
    """An O_EXCL lock file whose ownership token prevents foreign unlocks."""

    _state_guard = threading.RLock()
    _held: dict[str, tuple[int, int, str, int]] = {}

    def __init__(
        self,
        path: str | Path,
        *,
        timeout_seconds: float = 30.0,
        force_stale: bool = False,
        create_parent_directories: bool = True,
    ) -> None:
        self.path = Path(path)
        self.timeout_seconds = float(timeout_seconds)
        self.force_stale = force_stale
        self.create_parent_directories = create_parent_directories
        self.token = secrets.token_hex(16)
        self._owned = False
        self._key: str | None = None

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _recover_stale(self) -> bool:
        if self.path.is_symlink():
            raise FailureMemoryError("Refusing symlink lock path", code="lock_path")
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            pid = int(raw["pid"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            if not self.force_stale:
                return False
        else:
            if self._pid_alive(pid) and not self.force_stale:
                return False
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        return True

    def acquire(self) -> "ProjectLock":
        # Read-only callers (create_parent_directories=False) must not have
        # the side effect of creating filesystem structure in the target
        # repository just by acquiring a lock to serialize against
        # concurrent writers. If the parent already exists, a real O_EXCL
        # lock is still taken below -- this only removes the *creation*,
        # not the mutual-exclusion guarantee, for the common case where a
        # write has already happened at least once. If the parent does not
        # exist, there is categorically nothing yet to coordinate against
        # (every write path creates this directory on its own first write),
        # so failing closed with a typed error is honest instead of
        # silently creating the very structure a read must not create.
        if self.create_parent_directories:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        elif not self.path.parent.is_dir():
            raise FailureMemoryError(
                f"Project lock parent directory does not exist: {self.path.parent}. "
                "Read-only operations do not create it. Run a write operation "
                "(record a lesson, compile in write mode, or refresh) at least "
                "once first, or pre-create the directory explicitly.",
                code="lock_parent_missing",
            )
        if self.path.is_symlink():
            raise FailureMemoryError("Refusing symlink lock path", code="lock_path")
        self._key = str(self.path.resolve(strict=False))
        process_id = os.getpid()
        thread_id = threading.get_ident()
        with self._state_guard:
            held = self._held.get(self._key)
            if held is not None and held[:2] == (process_id, thread_id):
                self.token = held[2]
                self._held[self._key] = (*held[:3], held[3] + 1)
                self._owned = True
                return self
        deadline = time.monotonic() + self.timeout_seconds
        payload = (
            json.dumps(
                {"pid": os.getpid(), "token": self.token, "version": 1},
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        while True:
            try:
                descriptor = os.open(
                    self.path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
            except FileExistsError:
                if self._recover_stale():
                    continue
                if time.monotonic() >= deadline:
                    raise FailureMemoryError(
                        f"Timed out waiting for project lock {self.path}",
                        code="lock_contention",
                    )
                time.sleep(0.02)
                continue
            try:
                os.write(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self._owned = True
            with self._state_guard:
                self._held[self._key] = (process_id, thread_id, self.token, 1)
            return self

    def release(self) -> None:
        if not self._owned:
            return
        process_id = os.getpid()
        thread_id = threading.get_ident()
        with self._state_guard:
            held = self._held.get(self._key or "")
            if held is None or held[:3] != (process_id, thread_id, self.token):
                raise FailureMemoryError(
                    "In-process project lock ownership changed", code="lock_ownership"
                )
            if held[3] > 1:
                self._held[self._key or ""] = (*held[:3], held[3] - 1)
                self._owned = False
                return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FailureMemoryError(
                f"Cannot verify lock ownership: {exc}", code="lock_ownership"
            ) from exc
        if raw.get("token") != self.token:
            raise FailureMemoryError(
                "Project lock ownership changed", code="lock_ownership"
            )
        self.path.unlink()
        with self._state_guard:
            self._held.pop(self._key or "", None)
        self._owned = False

    def __enter__(self) -> "ProjectLock":
        return self.acquire()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()


__all__ = ["ProjectLock"]
