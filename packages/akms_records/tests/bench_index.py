"""Benchmark the records index: recall, wake, rebuild and indexed appends.

Run it directly (it is not collected by pytest)::

    uv run python packages/akms_records/tests/bench_index.py --sizes 10000,100000

For each size it builds a synthetic store (Zipf-weighted words, eight
project scopes in one root, records spread over 24 months, 10 % amended),
then measures:

* ``recall``: p50/p95 of a scoped query plus fetching the top 10 full
  records from their files (``full=True``), and of the query alone;
* ``wake``: p50/p95 at the smallest size of at least 10,000 records;
* ``rebuild``: a full index rebuild from the event files;
* ``append``: p50/p95 of creates and amends through the API, with ``fsync``
  and the index update.

The corpus is generated through the normal write path with ``fsync`` off and
without index updates (followed by one rebuild); that changes speed, not
content. Timed appends run with ``fsync`` on. ``test_bench_index.py`` runs a
small version of this as a ``slow`` test.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from akms_records import RecordStore, Scope, fsio, wake
from akms_records.schemas import load_template

THRESHOLDS_MS = {
    "recall_p95_10k": 10.0,
    "recall_p95_100k": 50.0,
    "create_p95": 5.0,
    "amend_p95_10k": 15.0,
    "amend_p95_100k": 40.0,
}
REBUILD_LIMIT_S_100K = 60.0
SCOPES = [f"p{n}" for n in range(8)]
VOCABULARY = [f"w{n:04d}" for n in range(4000)]
WEIGHTS = [1.0 / (rank + 1) for rank in range(len(VOCABULARY))]


class SpreadClock:
    """Timestamps from 2024-11-01, spread evenly over 24 months."""

    def __init__(self, total: int) -> None:
        self.at = datetime(2024, 11, 1, tzinfo=UTC)
        self.step = timedelta(days=730) / max(total, 1)

    def __call__(self) -> str:
        self.at += self.step
        return self.at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def words(rng: random.Random, count: int) -> str:
    return " ".join(rng.choices(VOCABULARY, WEIGHTS, k=count))


def percentiles(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    pick = lambda q: ordered[min(len(ordered) - 1, int(q * len(ordered)))]  # noqa: E731
    return {
        "p50_ms": round(statistics.median(ordered) * 1000, 3),
        "p95_ms": round(pick(0.95) * 1000, 3),
        "p99_ms": round(pick(0.99) * 1000, 3),
        "n": len(ordered),
    }


@contextmanager
def no_fsync() -> Iterator[None]:
    saved = fsio.fsync_fd, fsio.fsync_dir
    fsio.fsync_fd = lambda fd: None  # type: ignore[assignment]
    fsio.fsync_dir = lambda path: None  # type: ignore[assignment]
    try:
        yield
    finally:
        fsio.fsync_fd, fsio.fsync_dir = saved


def timed(call: Callable[[], Any]) -> float:
    start = time.perf_counter()
    call()
    return time.perf_counter() - start


def build(repo: Path, total: int, rng: random.Random) -> dict[str, RecordStore]:
    clock = SpreadClock(total)
    stores = {
        name: RecordStore.open(
            Scope("project", name), repo=repo, clock=clock, index=False
        )
        for name in SCOPES
    }
    stores[SCOPES[0]].register_schema(load_template("decision"), actor="bench")
    created: list[tuple[str, str]] = []
    with no_fsync():
        for n in range(total):
            name = SCOPES[n % len(SCOPES)]
            result = stores[name].create(
                {
                    "schema_ref": "decision/v1",
                    "payload": {
                        "decision": words(rng, 8),
                        "rationale": words(rng, 30),
                        "context": words(rng, 20),
                    },
                    "tags": [f"t{rng.randrange(20)}"],
                    "review_state": rng.choice(
                        ["unreviewed", "agent_reviewed", "user_confirmed"]
                    ),
                },
                actor="bench",
                event_id=f"bench-{n}",
            )
            created.append((name, result.record_id))
        for name, record_id in rng.sample(created, total // 10):
            stores[name].amend(
                record_id,
                {"summary": "Amended: " + words(rng, 6)},
                expected_revision=1,
                actor="bench",
            )
    return stores


def queries(rng: random.Random, count: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n in range(count):
        kind = n % 4
        if kind == 0:
            out.append({"query": rng.choice(VOCABULARY[:50])})
        elif kind == 1:
            out.append({"query": rng.choice(VOCABULARY[500:3000])})
        elif kind == 2:
            out.append({"query": " ".join(rng.sample(VOCABULARY[:200], 2))})
        else:
            out.append(
                {
                    "query": rng.choice(VOCABULARY[:200]),
                    "tags": [f"t{rng.randrange(20)}"],
                }
            )
    return out


def run_size(
    total: int, *, n_queries: int, n_appends: int, seed: int
) -> dict[str, Any]:
    rng = random.Random(seed)
    with tempfile.TemporaryDirectory(prefix="akms-records-bench-") as tmp:
        repo = Path(tmp)
        started = time.perf_counter()
        stores = build(repo, total, rng)
        generate_s = time.perf_counter() - started
        reader = RecordStore.open(Scope("project", SCOPES[0]), repo=repo)
        index = reader.open_index()
        rebuild_s = timed(index.rebuild)
        parity = index.compare()["status"] == "ok"
        time.sleep(2.1)  # let directory signatures settle (see akms_records.index)
        reader.recall()  # warm-up: records the settled signatures
        plan = queries(rng, n_queries)
        full = [
            timed(lambda q=q: reader.recall(limit=10, full=True, **q)) for q in plan
        ]
        query_only = [timed(lambda q=q: reader.recall(limit=10, **q)) for q in plan]
        hits = [len(reader.recall(limit=10, **q).hits) for q in plan]
        tasks = [words(rng, 6) for _ in range(max(20, n_queries // 4))]
        wakes = [
            timed(
                lambda task=task: wake(
                    agent="bench",
                    task=task,
                    budget_tokens=2000,
                    scopes=[f"project:{SCOPES[0]}"],
                    repo=repo,
                    home=repo / "home",
                )
            )
            for task in tasks
        ]
        writer = RecordStore.open(Scope("project", SCOPES[1]), repo=repo)
        creates, amends = [], []
        for n in range(n_appends):
            document = {
                "schema_ref": "decision/v1",
                "payload": {"decision": words(rng, 8), "rationale": words(rng, 30)},
            }
            start = time.perf_counter()
            result = writer.create(document, actor="bench")
            creates.append(time.perf_counter() - start)
            start = time.perf_counter()
            writer.amend(
                result.record_id,
                {"summary": "Changed " + str(n)},
                expected_revision=1,
                actor="bench",
            )
            amends.append(time.perf_counter() - start)
        index_bytes = sum(
            p.stat().st_size for p in index.directory.glob("records.sqlite*")
        )
        for store in (*stores.values(), reader, writer):
            store.close()
    return {
        "records": total,
        "generate_s": round(generate_s, 2),
        "rebuild_s": round(rebuild_s, 2),
        "rebuild_parity": parity,
        "recall_full_top10": percentiles(full),
        "recall_query_only": percentiles(query_only),
        "recall_mean_hits": round(statistics.mean(hits), 2),
        "wake": percentiles(wakes),
        "create_indexed": percentiles(creates),
        "amend_indexed": percentiles(amends),
        "index_mb": round(index_bytes / 1e6, 1),
    }


def verdicts(results: list[dict[str, Any]]) -> list[str]:
    lines = []
    for result in results:
        size = result["records"]
        p95 = result["recall_full_top10"]["p95_ms"]
        create = result["create_indexed"]["p95_ms"]
        amend = result["amend_indexed"]["p95_ms"]
        if size == 10_000:
            lines.append(
                _verdict("recall p95 @10k", p95, THRESHOLDS_MS["recall_p95_10k"])
            )
            lines.append(
                _verdict("amend p95 @10k", amend, THRESHOLDS_MS["amend_p95_10k"])
            )
        if size == 100_000:
            lines.append(
                _verdict("recall p95 @100k", p95, THRESHOLDS_MS["recall_p95_100k"])
            )
            lines.append(
                _verdict("amend p95 @100k", amend, THRESHOLDS_MS["amend_p95_100k"])
            )
            lines.append(
                _verdict(
                    "rebuild @100k", result["rebuild_s"], REBUILD_LIMIT_S_100K, "s"
                )
            )
        lines.append(
            _verdict(f"create p95 @{size}", create, THRESHOLDS_MS["create_p95"])
        )
        lines.append(
            f"rebuild parity @{size}: {'pass' if result['rebuild_parity'] else 'FAIL'}"
        )
    return lines


def _verdict(name: str, value: float, limit: float, unit: str = "ms") -> str:
    state = "pass" if value <= limit else "FAIL"
    return f"{name}: {value} {unit} (threshold {limit} {unit}) {state}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--sizes", default="10000,100000")
    parser.add_argument("--queries", type=int, default=200)
    parser.add_argument("--appends", type=int, default=500)
    parser.add_argument("--seed", type=int, default=20261104)
    parser.add_argument("--output", type=Path, help="also write the results as JSON")
    args = parser.parse_args(argv)
    results = []
    for size in (int(text) for text in args.sizes.split(",")):
        print(f"benchmarking {size} records ...", file=sys.stderr, flush=True)
        results.append(
            run_size(
                size, n_queries=args.queries, n_appends=args.appends, seed=args.seed
            )
        )
    report = {
        "machine": {
            "platform": sys.platform,
            "python": sys.version.split()[0],
            "cpus": os.cpu_count(),
        },
        "results": results,
        "verdicts": verdicts(results),
    }
    text = json.dumps(report, indent=2, sort_keys=True)
    print(text)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    return 0 if not any("FAIL" in line for line in report["verdicts"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
