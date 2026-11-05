"""Several processes writing at once, and writers killed mid-write.

Kept small for CI. SIGKILL tests process crashes, not power loss: data in the
operating system's page cache survives a SIGKILL.
"""

from __future__ import annotations

import random
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from akms_records import RecordStore, ReplayError, Scope
from akms_records.fsio import TMP_RE
from akms_records.schemas import load_template

PROCESSES = 4


def spawn(worker: Path, *args: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, str(worker), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def finish(process: subprocess.Popen[str]) -> list[str]:
    out, err = process.communicate(timeout=120)
    assert process.returncode == 0, err
    return out.splitlines()


def no_tmp(root: Path) -> bool:
    return not [p for p in root.rglob("*") if TMP_RE.fullmatch(p.name)]


@pytest.fixture
def shared(repo, doc):
    store = RecordStore.open(Scope("project", "example"), repo=repo)
    store.register_schema(load_template("decision"), actor="t")
    return store


def test_racing_amends_lose_no_update(shared, repo, doc, worker):
    rid = shared.create(doc(), actor="t").record_id
    per_process = 12
    processes = [
        spawn(worker, "amend-loop", str(repo), rid, str(per_process), f"w{n}")
        for n in range(PROCESSES)
    ]
    acks = [
        line.split() for p in processes for line in finish(p) if line.startswith("ACK")
    ]
    assert len(acks) == PROCESSES * per_process
    history = shared.history(rid)
    assert len(history) == 1 + PROCESSES * per_process
    by_revision = {event["revision"]: event["event_id"] for event in history}
    for _, _, revision, event_id in acks:
        assert by_revision[int(revision)] == event_id  # every ACK is on disk
    assert len({event["event_id"] for event in history}) == len(history)
    # Windows may keep a temp link it could not delete while a reader held
    # the file open; doctor removes it once its writer has exited.
    assert shared.doctor(fix=True)["status"] == "ok"
    assert no_tmp(shared.root)


def test_racing_creates_with_one_event_id_make_one_record(shared, repo, worker):
    for trial in range(3):
        processes = [
            spawn(worker, "create-same", str(repo), f"shared-{trial}")
            for _ in range(PROCESSES)
        ]
        lines = [
            line.split()
            for p in processes
            for line in finish(p)
            if line.startswith("ACK")
        ]
        assert len({line[1] for line in lines}) == 1
        assert sum(1 for line in lines if line[2] == "0") == 1  # exactly one real write
        directory = shared.record_dir(lines[0][1])
        assert sorted(p.name for p in directory.iterdir()) == ["000001.json"]


def test_concurrent_creates_get_distinct_ids(shared, repo, worker):
    processes = [
        spawn(worker, "create-many", str(repo), "15", f"c{n}") for n in range(PROCESSES)
    ]
    ids = [
        line.split()[1]
        for p in processes
        for line in finish(p)
        if line.startswith("ACK")
    ]
    assert len(ids) == len(set(ids)) == PROCESSES * 15
    records = list(shared.iter_records())
    assert len(records) == PROCESSES * 15
    assert not [r for r in records if isinstance(r, ReplayError)]


@pytest.mark.skipif(sys.platform == "win32", reason="SIGKILL is POSIX only")
def test_killed_writers_never_lose_or_corrupt_acknowledged_events(
    shared, repo, doc, worker, items
):
    for i in range(5):
        shared.create(doc(f"seed {i}"), actor="t")
    rng = random.Random(1234)
    acked: dict[tuple[str, int], str] = {}
    for run in range(16):
        pause = "0.005" if run % 2 == 0 else "0"
        process = spawn(worker, "crash-loop", str(repo), str(run), pause)
        assert process.stdout is not None
        ready = process.stdout.readline().strip()
        assert ready == "READY", process.stderr.read() if process.stderr else ""
        time.sleep(rng.uniform(0.01, 0.15))
        process.send_signal(signal.SIGKILL)
        out, _ = process.communicate(timeout=60)
        for line in out.splitlines():
            if line.startswith("ACK "):
                _, rid, revision, event_id = line.split()
                acked[(rid, int(revision))] = event_id
        store = RecordStore.open(Scope("project", "example"), repo=repo)
        for (rid, revision), event_id in acked.items():
            events = store.history(rid)
            assert events[revision - 1]["event_id"] == event_id
        for item in store.iter_records():
            assert not isinstance(item, ReplayError), item
        report = store.doctor(fix=True, force_tmp=True)  # no writer is alive now
        assert report["status"] == "ok", report
        assert no_tmp(store.root)
        after = store.doctor()
        assert after["status"] == "ok"
        assert not items(after, "empty_dirs") and not items(after, "recent_empty_dirs")
    assert acked
