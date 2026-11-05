"""Files the store creates are owner-only."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from akms_records import fsio

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.fixture
def open_umask():
    previous = os.umask(0o022)
    try:
        yield
    finally:
        os.umask(previous)


def test_primitives_create_owner_only_files(tmp_path: Path, open_umask) -> None:
    fsio.write_exclusive(tmp_path, "event.json", b"{}")
    fsio.replace_file(tmp_path / "state.json", b"{}")
    fsio.append_line(tmp_path / "log.jsonl", "{}")
    for name in ("event.json", "state.json", "log.jsonl"):
        assert mode(tmp_path / name) == 0o600, name


def test_record_events_are_owner_only(store, doc, open_umask) -> None:
    store.create(doc(), actor="tester")
    events = [p for p in store.root.rglob("*.json") if p.parent.name.startswith("rec-")]
    assert events
    assert {mode(p) for p in events} == {0o600}


def test_index_files_are_owner_only(store, doc, open_umask) -> None:
    store.create(doc(), actor="tester")
    store.recall("model")
    index = store.index_path
    assert index.is_file()
    for path in [index, *index.parent.glob(index.name + "-*")]:
        assert mode(path) == 0o600, path.name


def test_pending_markers_are_owner_only(store, open_umask) -> None:
    store.recall()
    index = store.index_for_read()
    assert index is not None
    marker = index.mark("rec-20261103-00000000")
    assert marker is not None
    try:
        assert mode(marker) == 0o600
    finally:
        index.unmark(marker)
