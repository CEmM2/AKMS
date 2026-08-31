"""The committed standalone-runtime example must actually run and complete.

Executes examples/standalone-runtime/run_demo.py as a subprocess — offline,
deterministic — and asserts the pipeline reaches COMPLETE with exit 0.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLE_DIR = Path(__file__).resolve().parents[3] / "examples" / "standalone-runtime"


@pytest.mark.e2e
@pytest.mark.runtime
def test_standalone_runtime_example_completes(tmp_path):
    result = subprocess.run(
        [sys.executable, "run_demo.py", str(tmp_path / "ws")],
        capture_output=True,
        text=True,
        cwd=EXAMPLE_DIR,
        timeout=120,
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert "pipeline COMPLETED" in result.stdout
    assert "stage=PLAN -> APPROVE" in result.stdout
    assert list((tmp_path / "ws" / "knowledge" / "sessions").glob("*.md"))
