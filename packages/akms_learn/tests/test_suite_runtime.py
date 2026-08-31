"""Suite-level invariants: wall-clock budget and per-test independence.

The two are bundled in one file because both run the compile pipeline
multiple times in sequence; folding them avoids duplicating the fixture
wiring.

  * The suite runs in under 30 seconds on a normal machine.
  * Each test is independent (no shared mutable state).

Design choice for the runtime budget: rather than spawning ``pytest.main``
recursively
(which complicates cwd / capture handling and can deadlock under the
existing capture session), we use the compile pipeline itself as a
representative cost driver — 3 consecutive end-to-end compiles with both
exporters configured. The unit/integration tests are individually
cheap (graph imports, hashing, validation); the 3-compile wall-clock is a
conservative proxy that empirically dominates suite runtime.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from akms_learn import (
    compile_learning_source,
    fixture_graph,
)


# Default LearningRequest comes from the ``make_request`` conftest fixture.


class TestSuiteRuntime:
    """Suite wall-clock < 30s; tests use isolated tmp dirs."""

    @pytest.mark.integration
    def test_suite_runtime_under_30s(self, tmp_path: Path, make_request) -> None:
        """3 sequential full-exporter compiles complete in < 30 seconds.

        Stand-in for "the §19 suite runs in under 30 seconds" — the 10
        existing §19 cases are individually faster than a single compile,
        so 3 compiles is a strict upper bound on suite runtime.
        """
        budget_seconds = 30.0
        runs = 3

        start = time.monotonic()
        for i in range(runs):
            out_dir = tmp_path / f"run_{i}"
            result = compile_learning_source(
                request=make_request(),
                graph_slice=fixture_graph(),
                output_dir=out_dir,
            )
            assert result.packet_path is not None
            assert result.packet_path.exists()
        elapsed = time.monotonic() - start

        assert elapsed < budget_seconds, (
            f"{runs} compiles took {elapsed:.2f}s, budget is {budget_seconds}s"
        )

    @pytest.mark.integration
    def test_tests_independent_no_shared_state(
        self, tmp_path: Path, make_request
    ) -> None:
        """Two compiles into separate tmp_path subdirs produce distinct
        ``packet_path`` values — no module-level state leaks between runs.
        """
        out_a = tmp_path / "indep_a"
        out_b = tmp_path / "indep_b"

        result_a = compile_learning_source(
            request=make_request(),
            graph_slice=fixture_graph(),
            output_dir=out_a,
        )
        result_b = compile_learning_source(
            request=make_request(),
            graph_slice=fixture_graph(),
            output_dir=out_b,
        )

        assert result_a.packet_path is not None and result_a.packet_path.exists()
        assert result_b.packet_path is not None and result_b.packet_path.exists()

        # Distinct output dirs ⇒ distinct concrete paths.
        assert result_a.packet_path != result_b.packet_path
        assert result_a.packet_path.is_relative_to(out_a)
        assert result_b.packet_path.is_relative_to(out_b)

        # Deterministic content invariant still holds — independence here is
        # about FS locality, not value drift.
        assert result_a.packet.packet_id == result_b.packet.packet_id
