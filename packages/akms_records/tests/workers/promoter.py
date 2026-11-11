"""Controlled process barriers for promotion locking regression tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time

from akms_records import RecordStore, Scope, RecordsError
from akms_records import bridge


def main():
    repo, rid, mode, barriers = (
        Path(sys.argv[1]),
        sys.argv[2],
        sys.argv[3],
        Path(sys.argv[4]),
    )
    used = False

    def pause():
        nonlocal used
        if used:
            return
        used = True
        (barriers / f"{mode}.ready").touch()
        deadline = time.monotonic() + 30
        while not (barriers / f"{mode}.release").exists():
            if time.monotonic() > deadline:
                raise RuntimeError("promotion test barrier timed out")
            time.sleep(0.01)

    original_open = os.open
    original_write_text = Path.write_text
    original_body = bridge._Job.body

    def controlled_open(path, flags, *args, **kwargs):
        fd = original_open(path, flags, *args, **kwargs)
        name = Path(path).name
        if (
            mode == "init"
            and flags & os.O_EXCL
            and (name == bridge.LOCK_NAME or name.startswith(f".{bridge.LOCK_NAME}."))
        ):
            pause()  # descriptor exists, PID bytes have not been published
        return fd

    def controlled_write(path, data, *args, **kwargs):
        if mode == "write" and path.name == "shared.md" and rid in data:
            pause()  # dedup read/modify completed; pause before overwriting disk
        return original_write_text(path, data, *args, **kwargs)

    def controlled_body(job):
        if mode == "body":
            pause()  # repository lock is held, but no projection is written
        return original_body(job)

    os.open = controlled_open
    Path.write_text = controlled_write
    bridge._Job.body = controlled_body
    store = RecordStore.open(Scope("project", "example"), repo=repo)
    try:
        result = bridge.promote(store, rid, review="approved", repo=repo, actor="t")
    except RecordsError as exc:
        result = {"error": exc.code}
    (barriers / f"{mode}.result.json").write_text(json.dumps(result))


if __name__ == "__main__":
    main()
