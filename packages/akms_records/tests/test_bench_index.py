"""A small run of the index benchmark (``bench_index.py``), marked slow.

It checks that the benchmark runs and that rebuild parity holds. Timing
thresholds apply to the full sizes on a comparable machine, so they are not
asserted here.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow


def test_benchmark_runs_at_a_small_size():
    path = Path(__file__).with_name("bench_index.py")
    spec = importlib.util.spec_from_file_location("bench_index", path)
    assert spec is not None and spec.loader is not None
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    result = bench.run_size(400, n_queries=20, n_appends=20, seed=1)
    assert result["records"] == 400 and result["rebuild_parity"] is True
    for key in ("recall_full_top10", "recall_query_only", "wake", "create_indexed"):
        assert result[key]["n"] > 0 and result[key]["p95_ms"] > 0
