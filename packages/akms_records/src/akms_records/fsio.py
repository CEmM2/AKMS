"""Crash-safe file primitives.

``write_exclusive`` is the store's only way to create an immutable file:

1. write the bytes to a temp file ``.<name>.<pid>.<random>.tmp`` in the same
   directory, created with ``O_EXCL``;
2. ``fsync`` the temp file;
3. ``os.link`` it to the final name, which fails if that name exists;
4. unlink the temp file;
5. ``fsync`` the directory, where the operating system allows it.

Step 3 is the concurrency check: of several writers racing for the same file
exactly one link succeeds, and readers only ever see complete files. No lock
is taken. On Windows, a filesystem without hard links falls back to
``os.rename``, which there also refuses to replace an existing file.

Durability: ``fsync`` is used by default. On macOS that does not flush the
drive's write cache; set ``AKMS_RECORDS_FULL_FSYNC=1`` for ``F_FULLFSYNC``,
which costs roughly 15 ms per write.
"""

from __future__ import annotations

import errno
import os
import re
import secrets
import sys
from collections.abc import Callable
from pathlib import Path

from akms_records.errors import RecordsError

FULL_FSYNC_ENV = "AKMS_RECORDS_FULL_FSYNC"
TMP_RE = re.compile(r"\.(?P<name>.+)\.(?P<pid>[0-9]+)\.(?P<rand>[0-9a-f]{8})\.tmp")
_O_BINARY = getattr(os, "O_BINARY", 0)

# Test hook: called between the temp-file fsync and the link. Crash tests set
# it to widen the window a SIGKILL can land in.
before_link: Callable[[], None] | None = None


def full_fsync_requested() -> bool:
    return os.environ.get(FULL_FSYNC_ENV, "") == "1"


def fsync_fd(fd: int) -> None:
    if sys.platform == "darwin" and full_fsync_requested():
        import fcntl

        fcntl.fcntl(fd, fcntl.F_FULLFSYNC)
    else:
        os.fsync(fd)


def fsync_dir(path: Path) -> None:
    """Flush a directory entry change. A no-op on Windows."""
    if os.name == "nt":
        return  # Windows cannot open a directory for fsync.
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        fsync_fd(fd)
    except OSError as exc:
        if exc.errno not in (errno.EINVAL, errno.ENOTSUP, errno.EBADF):
            raise
    finally:
        os.close(fd)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        view = view[written:]


def temp_name(name: str) -> str:
    return f".{name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"


def _write_temp(directory: Path, name: str, data: bytes) -> Path:
    tmp = directory / temp_name(name)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_BINARY, 0o644)
    try:
        _write_all(fd, data)
        fsync_fd(fd)
    finally:
        os.close(fd)
    return tmp


def _link_exclusive(tmp: Path, final: Path) -> None:
    try:
        os.link(tmp, final)
    except FileExistsError:
        raise
    except OSError as exc:
        if os.name == "nt":
            # No hard links on this volume (FAT, some network shares).
            # os.rename does not replace an existing file on Windows.
            os.rename(tmp, final)
            return
        raise RecordsError(
            f"the filesystem holding {final.parent} does not support hard links "
            f"({exc.strerror}); the store needs them for exclusive writes",
            code="link_unsupported",
        ) from exc


def _unlink_quietly(path: Path) -> None:
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except PermissionError:
        # Windows refuses to delete a link while another process holds the
        # file open. The temp file is cleaned up later by doctor --fix or the next
        # writer once this process has exited.
        pass


def write_exclusive(directory: Path, name: str, data: bytes) -> None:
    """Create ``directory/name`` with ``data``; ``FileExistsError`` if it exists."""
    final = directory / name
    tmp = _write_temp(directory, name, data)
    try:
        if before_link is not None:
            before_link()
        _link_exclusive(tmp, final)
    finally:
        _unlink_quietly(tmp)
    fsync_dir(directory)


def replace_file(path: Path, data: bytes) -> None:
    """Atomically replace ``path`` (for the few mutable files, such as a policy)."""
    tmp = _write_temp(path.parent, path.name, data)
    try:
        os.replace(tmp, path)
    except BaseException:
        _unlink_quietly(tmp)
        raise
    fsync_dir(path.parent)


def append_line(path: Path, line: str) -> None:
    """Append one line to an append-only log and flush it."""
    created = not path.exists()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND | _O_BINARY, 0o644)
    try:
        _write_all(fd, (line + "\n").encode("utf-8"))
        fsync_fd(fd)
    finally:
        os.close(fd)
    if created:
        fsync_dir(path.parent)


__all__ = [
    "FULL_FSYNC_ENV",
    "TMP_RE",
    "append_line",
    "fsync_dir",
    "replace_file",
    "write_exclusive",
]
