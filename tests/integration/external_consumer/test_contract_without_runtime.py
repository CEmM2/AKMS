"""External-consumer contract test: projections and evidence without the runtime.

AKMS documents two public contract surfaces for external consumers:

* **Projection contract** — ``akms.task_context`` (task-knowledge queries, seed
  resolution, routes, manifests) together with ``akms.graph.query_subgraph``
  and ``akms.graph.generate_loadout``.
* **Evidence contract** — ``akms.graph.update_graph.update_graph``, which
  ingests ``AgentMemory``, ``PCD``, or a plain persistent-zone dict. The
  evidence models live in ``akms.schema.models`` (core-owned).

This test proves both contracts are usable by a consumer that never imports
the embedded first-party runtime: the whole workflow runs in a subprocess and
asserts that neither ``akms.orchestrator`` nor ``akms.agents`` (nor any
submodule of either) ever enters ``sys.modules``.

The subprocess is deliberate. An in-process assertion would be contaminated by
whatever earlier tests imported; a fresh interpreter is the only honest
witness for "this consumer path does not load the runtime".
"""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

CONSUMER_SCRIPT = r"""
import json
import sys
from pathlib import Path

tmp = Path(sys.argv[1])

# ---------------------------------------------------------------------------
# Fixture: one global node in a vault, one empty project repo.
# ---------------------------------------------------------------------------
vault = tmp / "global_vault" / "nodes"
vault.mkdir(parents=True)
(vault / "demo-node.md").write_text(
    "\n".join(
        [
            "---",
            "akms_schema: v2",
            "id: demo-node",
            "title: Demo Node",
            "domain: demo-domain",
            "tags:",
            "- demo",
            "status: established",
            "confidence: 0.9",
            "source: human",
            "edges: []",
            "---",
            "",
            "Demo content.",
        ]
    )
)

repo = tmp / "repo"
for sub in ["graph", "local-nodes", "sessions", "loadouts", "code-mirror", "qmd"]:
    (repo / "knowledge" / sub).mkdir(parents=True)
(repo / "knowledge" / "graph" / "local_state.yaml").write_text(
    "akms_schema: v2\nnodes: {}\n"
)

# ---------------------------------------------------------------------------
# Projection contract: compile the graph and query it.
# ---------------------------------------------------------------------------
from akms.graph.build_graph import build_graph
from akms.graph.query_subgraph import query_subgraph

graph = build_graph(repo, global_vault=vault)
assert "demo-node" in graph.nodes, "compiled graph is missing the vault node"

projection = query_subgraph(graph, domain_tags=["demo"], agent_role="implementer")
assert any(node_id == "demo-node" for node_id, _ in projection), (
    "projection did not select the seeded node"
)

# ---------------------------------------------------------------------------
# Evidence contract: ingest a plain persistent-zone dict (no runtime models
# required) and confirm the graph mutates.
# ---------------------------------------------------------------------------
from akms.graph.update_graph import update_graph

evidence = {
    "task_id": "external-task-001",
    "nodes_used": [{"id": "demo-node", "useful": True, "coverage": "sufficient"}],
    "nodes_missing": [],
    "lessons": {},
    "pitfalls_discovered": [],
    "new_knowledge": [],
}
summary = update_graph(evidence, repo, global_vault=vault)
assert summary["confidence_events"], "evidence ingestion produced no events"

# The projection surface package itself.
import akms.task_context  # noqa: F401

# ---------------------------------------------------------------------------
# The actual contract assertion: the runtime never loaded.
# ---------------------------------------------------------------------------
runtime_modules = sorted(
    m
    for m in sys.modules
    if m == "akms.orchestrator"
    or m.startswith("akms.orchestrator.")
    or m == "akms.agents"
    or m.startswith("akms.agents.")
)
print(json.dumps({"runtime_modules": runtime_modules, "events": len(summary["confidence_events"])}))
"""


@pytest.mark.integration
@pytest.mark.external_consumer
def test_projection_and_evidence_contracts_do_not_load_runtime(tmp_path):
    """A consumer can project and ingest evidence with the runtime never imported."""
    result = subprocess.run(
        [sys.executable, "-c", CONSUMER_SCRIPT, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"external-consumer workflow failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["runtime_modules"] == [], (
        "the external-consumer path imported runtime modules: "
        f"{payload['runtime_modules']}"
    )
    assert payload["events"] >= 1
