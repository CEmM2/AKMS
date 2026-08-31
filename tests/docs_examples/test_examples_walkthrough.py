"""Execute the examples/ walkthrough and compare against committed outputs.

Documentation examples are maintained by running them, not by promising they
work: this test executes the exact flow in ``examples/README.md`` against the
installed package and diffs the results with ``examples/expected-output/``.

Volatile fields are normalized before comparison:

* ``graph.json`` header: ``generated_at`` (timestamp), ``global_vault`` and
  ``repo_id`` (environment-dependent paths/names) are dropped.
* ``akms query`` JSON: ``graph_path`` is replaced by a placeholder.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
BIN = Path(sys.executable).parent

VOLATILE_GRAPH_KEYS = ("generated_at", "global_vault", "repo_id")


def _run(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=cwd, timeout=120
    )
    assert result.returncode == 0, f"{cmd} failed:\n{result.stderr}"
    return result.stdout


@pytest.mark.e2e
def test_examples_walkthrough_matches_expected_output(tmp_path):
    # Work on a copy so the committed tree stays pristine.
    shutil.copytree(EXAMPLES / "minimal-vault", tmp_path / "minimal-vault")
    shutil.copytree(EXAMPLES / "sample-project", tmp_path / "sample-project")
    project = tmp_path / "sample-project"

    _run(
        [
            sys.executable,
            "-c",
            "from akms.graph.build_graph import build_graph; "
            "build_graph('sample-project', global_vault='minimal-vault/nodes')",
        ],
        cwd=tmp_path,
    )

    # Compiled graph, minus volatile header fields.
    graph = json.loads((project / "knowledge" / "graph" / "graph.json").read_text())
    for key in VOLATILE_GRAPH_KEYS:
        graph["graph"].pop(key, None)
    expected_graph = json.loads(
        (EXAMPLES / "expected-output" / "graph.normalized.json").read_text()
    )
    assert graph == expected_graph

    # Health report, byte-for-byte.
    status = _run([str(BIN / "akms"), "status"], cwd=project)
    assert status == (EXAMPLES / "expected-output" / "status.txt").read_text()

    # Query output, with the absolute graph_path normalized away.
    query = json.loads(_run([str(BIN / "akms"), "query", "demo"], cwd=project))
    query["graph_path"] = "<repo>/knowledge/graph/graph.json"
    expected_query = json.loads(
        (EXAMPLES / "expected-output" / "query-demo.txt").read_text()
    )
    assert query == expected_query
