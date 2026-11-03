"""Mirror documents and export locks take the process umask's file mode."""

from __future__ import annotations

import os
import stat
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from akms.repo_wiki.export.akms import atomic_write_text
from akms.repo_wiki.locking import RepoLocalLock

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")


@pytest.fixture(params=[0o022, 0o077])
def umask(request: pytest.FixtureRequest) -> Iterator[int]:
    previous = os.umask(request.param)
    try:
        yield request.param
    finally:
        os.umask(previous)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.mark.unit
def test_mirror_write_follows_umask(tmp_path: Path, umask: int):
    target = tmp_path / "code-mirror" / "pkg" / "value.md"

    atomic_write_text(target, "mirror\n")

    assert target.read_text(encoding="utf-8") == "mirror\n"
    assert _mode(target) == 0o666 & ~umask
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


@pytest.mark.unit
def test_mirror_overwrite_follows_umask(tmp_path: Path, umask: int):
    target = tmp_path / "value.md"
    target.write_text("old\n", encoding="utf-8")
    target.chmod(0o600)

    atomic_write_text(target, "new\n")

    assert target.read_text(encoding="utf-8") == "new\n"
    assert _mode(target) == 0o666 & ~umask


@pytest.mark.unit
def test_export_lock_follows_umask(tmp_path: Path, umask: int):
    lock = RepoLocalLock(tmp_path, lock_file=tmp_path / ".repo2md-export.lock")

    lock.acquire()
    try:
        assert _mode(lock.path) == 0o666 & ~umask
    finally:
        lock.release()
