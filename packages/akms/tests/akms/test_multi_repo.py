"""Tests for multi-repo isolation — Phase 6 Task 6.5.

Verifies that two repos sharing the same global vault maintain
independent local state without cross-contamination.

Success criteria (from development plan §6.5):
1. Repo-A boosts a node; Repo-B decays same node — independent
2. Global node file untouched
3. Pitfall in Repo-A doesn't appear in Repo-B
4. Same task tags → different loadouts in different repos
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml

from akms.graph.build_graph import build_graph, load_graph
from akms.graph.query_subgraph import query_subgraph
from akms.graph.update_graph import update_graph
from akms.schema.models import PropagationConfig

from .conftest import make_global_node


@pytest.fixture
def shared_vault(tmp_path):
    """Create a shared global vault."""
    vault = tmp_path / "shared_vault" / "nodes"
    vault.mkdir(parents=True)
    return vault


@pytest.fixture
def repo_a(tmp_path):
    """Create repo A with knowledge/ directory."""
    repo = tmp_path / "repo_a"
    repo.mkdir()
    knowledge = repo / "knowledge"
    for subdir in [
        "graph",
        "local-nodes",
        "sessions",
        "loadouts",
        "code-mirror",
        "qmd",
    ]:
        (knowledge / subdir).mkdir(parents=True)
    overlay_path = knowledge / "graph" / "local_state.yaml"
    overlay_path.write_text(
        yaml.dump(
            {
                "akms_schema": "v2",
                "repo_id": "repo-a",
                "nodes": {},
                "local_edges": [],
                "session_nodes": {},
                "suppressed_edges": [],
            }
        )
    )
    return repo


@pytest.fixture
def repo_b(tmp_path):
    """Create repo B with knowledge/ directory."""
    repo = tmp_path / "repo_b"
    repo.mkdir()
    knowledge = repo / "knowledge"
    for subdir in [
        "graph",
        "local-nodes",
        "sessions",
        "loadouts",
        "code-mirror",
        "qmd",
    ]:
        (knowledge / subdir).mkdir(parents=True)
    overlay_path = knowledge / "graph" / "local_state.yaml"
    overlay_path.write_text(
        yaml.dump(
            {
                "akms_schema": "v2",
                "repo_id": "repo-b",
                "nodes": {},
                "local_edges": [],
                "session_nodes": {},
                "suppressed_edges": [],
            }
        )
    )
    return repo


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestMultiRepoIsolation:
    """Verify per-repo isolation with shared global vault."""

    def test_independent_confidence(self, shared_vault, repo_a, repo_b, monkeypatch):
        """Repo-A boost and Repo-B decay produce different confidences."""
        monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(shared_vault))

        # Create shared global node
        make_global_node(shared_vault, id="node-x", confidence=0.90, tags=["shared"])

        # Build graphs in both repos
        build_graph(repo_a, global_vault=shared_vault)
        build_graph(repo_b, global_vault=shared_vault)

        # Repo-A: boost (useful)
        update_graph(
            {
                "nodes_used": [
                    {"id": "node-x", "useful": True, "coverage": "sufficient"}
                ],
                "pitfalls_discovered": [],
                "new_knowledge": [],
                "nodes_missing": [],
                "lessons": {"worked": [], "failed": []},
            },
            repo_a,
            global_vault=shared_vault,
        )

        # Repo-B: decay (outdated)
        update_graph(
            {
                "nodes_used": [
                    {"id": "node-x", "useful": True, "coverage": "outdated"}
                ],
                "pitfalls_discovered": [],
                "new_knowledge": [],
                "nodes_missing": [],
                "lessons": {"worked": [], "failed": []},
            },
            repo_b,
            global_vault=shared_vault,
        )

        # Load both graphs
        G_a = load_graph(repo_a / "knowledge" / "graph" / "graph.json")
        G_b = load_graph(repo_b / "knowledge" / "graph" / "graph.json")

        conf_a = G_a.nodes["node-x"].get("confidence", 0)
        conf_b = G_b.nodes["node-x"].get("confidence", 0)

        # Repo-A boosted → higher; Repo-B decayed → lower
        assert conf_a > conf_b
        assert conf_a > 0.90  # boosted
        assert conf_b < 0.90  # decayed

    def test_global_files_untouched(self, shared_vault, repo_a, monkeypatch):
        """Global node files remain byte-identical after update_graph."""
        monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(shared_vault))

        node_path = make_global_node(
            shared_vault, id="node-x", confidence=0.90, tags=["test"]
        )
        hash_before = _file_hash(node_path)

        build_graph(repo_a, global_vault=shared_vault)
        update_graph(
            {
                "nodes_used": [
                    {"id": "node-x", "useful": True, "coverage": "missing-detail"}
                ],
                "pitfalls_discovered": [],
                "new_knowledge": [],
                "nodes_missing": [],
                "lessons": {"worked": [], "failed": []},
            },
            repo_a,
            global_vault=shared_vault,
        )

        hash_after = _file_hash(node_path)
        assert hash_before == hash_after

    def test_pitfall_isolated(self, shared_vault, repo_a, repo_b, monkeypatch):
        """Pitfall in Repo-A doesn't appear in Repo-B."""
        monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(shared_vault))

        make_global_node(shared_vault, id="node-x", confidence=0.90, tags=["test"])

        build_graph(repo_a, global_vault=shared_vault)
        build_graph(repo_b, global_vault=shared_vault)

        # Add pitfall in Repo-A
        update_graph(
            {
                "nodes_used": [],
                "new_knowledge": [],
                "nodes_missing": [],
                "lessons": {"worked": [], "failed": []},
                "pitfalls_discovered": [
                    {
                        "node_ref": "node-x",
                        "description": "gotcha in repo-a",
                        "severity": "high",
                    }
                ],
            },
            repo_a,
            global_vault=shared_vault,
        )

        # Rebuild Repo-B graph
        G_b = build_graph(repo_b, global_vault=shared_vault)

        # Check Repo-B has no pitfall edges
        pitfall_edges = [
            (u, v) for u, v, d in G_b.edges(data=True) if d.get("type") == "pitfall"
        ]
        assert pitfall_edges == []

        # Repo-A should have the pitfall
        G_a = load_graph(repo_a / "knowledge" / "graph" / "graph.json")
        pitfall_edges_a = [
            (u, v) for u, v, d in G_a.edges(data=True) if d.get("type") == "pitfall"
        ]
        assert len(pitfall_edges_a) >= 1

    def test_different_loadouts_same_tags(
        self, shared_vault, repo_a, repo_b, monkeypatch
    ):
        """Same tags produce different loadouts when overlay states differ."""
        monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(shared_vault))

        make_global_node(shared_vault, id="node-x", confidence=0.90, tags=["shared"])
        make_global_node(shared_vault, id="node-y", confidence=0.85, tags=["shared"])

        # Repo-A: boost node-x heavily
        set_overlay_repo(repo_a, {"node-x": {"confidence": 0.99, "activations": 10}})
        G_a = build_graph(repo_a, global_vault=shared_vault)

        # Repo-B: boost node-y heavily
        set_overlay_repo(repo_b, {"node-y": {"confidence": 0.99, "activations": 10}})
        G_b = build_graph(repo_b, global_vault=shared_vault)

        config = PropagationConfig()

        # Query both
        nodes_a = query_subgraph(G_a, ["shared"], "implementer", config=config)
        nodes_b = query_subgraph(G_b, ["shared"], "implementer", config=config)

        # Both should have nodes but ordering may differ due to different activations
        ids_a = [n[0] for n in nodes_a]
        ids_b = [n[0] for n in nodes_b]

        # Both should include both nodes
        assert "node-x" in ids_a
        assert "node-y" in ids_a
        assert "node-x" in ids_b
        assert "node-y" in ids_b

        # Ranking should differ (node-x first in A, node-y first in B)
        if len(nodes_a) >= 2 and len(nodes_b) >= 2:
            assert ids_a[0] == "node-x"
            assert ids_b[0] == "node-y"


def set_overlay_repo(repo: Path, nodes: dict):
    """Helper to set overlay for multi-repo tests."""
    overlay_path = repo / "knowledge" / "graph" / "local_state.yaml"
    data = {
        "akms_schema": "v2",
        "repo_id": repo.name,
        "nodes": nodes,
        "local_edges": [],
        "session_nodes": {},
        "suppressed_edges": [],
    }
    overlay_path.write_text(yaml.dump(data, default_flow_style=False))
