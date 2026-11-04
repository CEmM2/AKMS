"""Child process for the concurrency and crash tests.

Usage: writer.py <mode> <repo> <args...>

Modes:
  amend-loop <record_id> <count> <tag>   amend with retry-on-stale; print ACKs
  create-same <event_id>                 one create with a shared event ID
  create-many <count> <tag>              independent creates
  crash-loop <seed> <pause>              creates and amends until killed
"""

from __future__ import annotations

import random
import sys
import time
from pathlib import Path

from akms_records import RecordStore, Scope, StaleRevision
from akms_records import fsio


def document(text: str) -> dict:
    return {
        "schema_ref": "decision/v1",
        "payload": {"decision": text, "rationale": "concurrency test"},
    }


def main(argv: list[str]) -> int:
    mode, repo = argv[0], Path(argv[1])
    store = RecordStore.open(Scope("project", "example"), repo=repo)
    if mode == "amend-loop":
        record_id, count, tag = argv[2], int(argv[3]), argv[4]
        stale = 0
        for index in range(count):
            event_id = f"{tag}-{index}"
            while True:
                head = store.get(record_id).revision
                try:
                    result = store.amend(
                        record_id,
                        {"summary": f"{tag} {index}"},
                        expected_revision=head,
                        actor=tag,
                        event_id=event_id,
                    )
                    break
                except StaleRevision:
                    stale += 1
            print(f"ACK {result.record_id} {result.revision} {event_id}", flush=True)
        print(f"STALE {stale}", flush=True)
        return 0
    if mode == "create-same":
        result = store.create(document("same"), actor="racer", event_id=argv[2])
        print(f"ACK {result.record_id} {int(result.noop)}", flush=True)
        return 0
    if mode == "create-many":
        count, tag = int(argv[2]), argv[3]
        for index in range(count):
            result = store.create(document(f"{tag} {index}"), actor=tag)
            print(f"ACK {result.record_id} 1 {result.event_id}", flush=True)
        return 0
    if mode == "crash-loop":
        rng = random.Random(int(argv[2]))
        pause = float(argv[3])
        if pause:
            fsio.before_link = lambda: time.sleep(pause)
        pool = [
            r.record_id for r in store.iter_records() if not isinstance(r, Exception)
        ]
        print("READY", flush=True)
        while True:
            if not pool or rng.random() < 0.3:
                result = store.create(document("crash"), actor="crash")
                pool.append(result.record_id)
            else:
                record_id = rng.choice(pool)
                head = store.get(record_id).revision
                try:
                    result = store.amend(
                        record_id,
                        {"summary": f"crash {rng.random()}"},
                        expected_revision=head,
                        actor="crash",
                    )
                except StaleRevision:
                    continue
            print(
                f"ACK {result.record_id} {result.revision} {result.event_id}",
                flush=True,
            )
    raise SystemExit(f"unknown mode {mode}")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
