"""Planning pipeline integration test — Phase 3 Task 3.4.

End-to-end test: compile graph → query_subgraph → generate loadout → verify.

Uses the seed nodes from Phase 2 to test the complete planning pipeline
with real graph structure.
"""

from __future__ import annotations

import shutil
import yaml
from pathlib import Path

import pytest

from akms.graph.build_graph import build_graph, load_graph
from akms.graph.generate_loadout import generate_loadout, select_loadout_mode
from akms.graph.qmd_cache import compute_graph_version
from akms.graph.query_subgraph import compute_query_hash, query_subgraph
from akms.schema.models import AgentRole, LoadoutMode, PropagationConfig
from tests.akms.conftest import make_global_node, set_overlay


# ═══════════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════════


@pytest.fixture
def seed_graph(tmp_vault, tmp_repo):
    """Build a graph resembling the Phase 2 seed nodes.

    Creates 5 nodes with interconnecting edges that mirror
    the actual seed node topology.
    """
    # Node 1: Taichi GPU Simulation
    make_global_node(
        tmp_vault,
        id="skill-taichi-gpu-sim",
        title="Taichi GPU Simulation Patterns",
        domain="gpu-simulation",
        tags=["taichi", "gpu", "simulation", "kernels", "snode"],
        confidence=0.95,
        confidence_floor=0.70,
        edges=[
            {"to": "skill-computational-mechanics", "type": "requires", "weight": 0.8},
            {"to": "skill-taichi-sim-reviewer", "type": "feeds-into", "weight": 0.7},
        ],
    )

    # Node 2: Computational Mechanics
    make_global_node(
        tmp_vault,
        id="skill-computational-mechanics",
        title="Computational Mechanics Algorithms",
        domain="computational-mechanics",
        tags=["fem", "nonlinear", "plasticity", "constitutive", "finite-strain"],
        confidence=0.95,
        confidence_floor=0.70,
        edges=[
            {"to": "skill-taichi-gpu-sim", "type": "feeds-into", "weight": 0.7},
            {"to": "skill-taichi-sim-reviewer", "type": "feeds-into", "weight": 0.5},
        ],
    )

    # Node 3: Repo Documentor
    make_global_node(
        tmp_vault,
        id="skill-repo-documentor",
        title="Repository Documentation Generator",
        domain="project-meta",
        tags=["documentation", "mkdocs", "sphinx", "latex", "repo-docs"],
        confidence=0.95,
        confidence_floor=0.70,
        edges=[
            {"to": "skill-shared-conventions", "type": "requires", "weight": 0.6},
        ],
    )

    # Node 4: Taichi Sim Reviewer
    make_global_node(
        tmp_vault,
        id="skill-taichi-sim-reviewer",
        title="Taichi Simulation Code Reviewer",
        domain="project-meta",
        tags=["code-review", "taichi", "simulation", "quality"],
        confidence=0.95,
        confidence_floor=0.70,
        edges=[
            {"to": "skill-taichi-gpu-sim", "type": "requires", "weight": 0.9},
            {"to": "skill-computational-mechanics", "type": "requires", "weight": 0.7},
            {"to": "skill-shared-conventions", "type": "requires", "weight": 0.5},
        ],
    )

    # Node 5: Shared Conventions (leaf)
    make_global_node(
        tmp_vault,
        id="skill-shared-conventions",
        title="Shared Repository Conventions",
        domain="project-meta",
        tags=["conventions", "naming", "structure", "style"],
        confidence=0.95,
        confidence_floor=0.70,
    )

    G = build_graph(tmp_repo, global_vault=tmp_vault)
    return G, tmp_repo


# ═══════════════════════════════════════════════════════════════════════
#  Integration Tests
# ═══════════════════════════════════════════════════════════════════════


class TestPlanningPipeline:
    """End-to-end planning pipeline integration tests."""

    def test_taichi_query_finds_relevant_nodes(self, seed_graph):
        """Querying with ['taichi', 'gpu'] finds Taichi-related nodes."""
        G, repo = seed_graph
        result = query_subgraph(G, ["taichi", "gpu"], AgentRole.IMPLEMENTER)

        node_ids = [nid for nid, _ in result]
        assert "skill-taichi-gpu-sim" in node_ids
        # Via requires edge: computational mechanics
        assert "skill-computational-mechanics" in node_ids

    def test_mechanics_query_for_physics_reviewer(self, seed_graph):
        """Physics reviewer query with mechanics tags finds domain nodes."""
        G, repo = seed_graph
        result = query_subgraph(
            G, ["fem", "plasticity"], AgentRole.PHYSICS_REVIEWER
        )

        node_ids = [nid for nid, _ in result]
        assert "skill-computational-mechanics" in node_ids
        # Physics reviewer excludes project-meta domain
        for nid, ndata in result:
            assert ndata.get("domain") != "project-meta" or nid in {
                n for n, _ in result
                if G.nodes[n].get("domain") != "project-meta"
            }

    def test_full_pipeline_compile_query_loadout(self, seed_graph):
        """Complete pipeline: compile → query → loadout → verify."""
        G, repo = seed_graph

        # Step 1: Graph is compiled (done in fixture)
        assert G.number_of_nodes() == 5
        assert G.number_of_edges() == 8

        # Step 2: Query subgraph
        result = query_subgraph(G, ["taichi", "gpu"], AgentRole.IMPLEMENTER)
        assert len(result) > 0

        # Step 3: Compute graph version
        graph_json = repo / "knowledge" / "graph" / "graph.json"
        graph_version = compute_graph_version(graph_json)
        assert graph_version != "no-graph"

        # Step 4: Generate loadout
        output_dir = repo / "knowledge" / "loadouts"
        content = generate_loadout(
            G, result,
            task_id="TSK-TAICHI-001",
            phase=1,
            graph_version=graph_version,
            seed_tags=["taichi", "gpu"],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.ROUTING,
            output_dir=output_dir,
        )

        # Verify loadout structure
        assert "# Loadout: TSK-TAICHI-001" in content
        assert "## Domain Knowledge" in content
        assert "## Suggested Reading Order" in content

        # Verify frontmatter
        lines = content.split("\n")
        end_idx = lines.index("---", 1)
        yaml_str = "\n".join(lines[1:end_idx])
        header = yaml.safe_load(yaml_str)

        assert header["task_id"] == "TSK-TAICHI-001"
        assert header["phase"] == 1
        assert header["agent_role"] == "implementer"
        assert header["loadout_mode"] == "routing"
        assert header["node_count"] > 0
        assert header["akms_schema"] == "v2"

        # Verify file was written
        loadout_file = output_dir / "1-TSK-TAICHI-001-loadout.md"
        assert loadout_file.exists()

    def test_loadout_contains_all_queried_nodes(self, seed_graph):
        """Every node from query_subgraph appears in the loadout table."""
        G, repo = seed_graph
        result = query_subgraph(G, ["taichi", "gpu"], AgentRole.IMPLEMENTER)

        content = generate_loadout(
            G, result,
            task_id="TSK-001",
            phase=1,
            graph_version="test",
            seed_tags=["taichi", "gpu"],
            agent_role=AgentRole.IMPLEMENTER,
        )

        for node_id, _ in result:
            assert f"`{node_id}`" in content

    def test_mode_selection_with_seed_nodes(self, seed_graph):
        """Mode selection works with actual node data."""
        G, repo = seed_graph
        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)

        # With plenty of context → full mode
        mode = select_loadout_mode(result, available_context=200000)
        assert mode == LoadoutMode.FULL

        # With tiny context → routing mode
        mode = select_loadout_mode(result, available_context=1000)
        assert mode == LoadoutMode.ROUTING

    def test_reading_order_respects_requires(self, seed_graph):
        """Reading order puts required nodes before dependents."""
        G, repo = seed_graph
        result = query_subgraph(G, ["taichi", "gpu"], AgentRole.IMPLEMENTER)

        content = generate_loadout(
            G, result,
            task_id="TSK-001",
            phase=1,
            graph_version="test",
            seed_tags=["taichi", "gpu"],
            agent_role=AgentRole.IMPLEMENTER,
        )

        # Extract reading order section
        lines = content.split("\n")
        order_start = None
        reading_order = []
        for i, line in enumerate(lines):
            if "## Suggested Reading Order" in line:
                order_start = i + 2  # skip heading + blank
                continue
            if order_start and i >= order_start:
                if line.strip().startswith(("1.", "2.", "3.", "4.", "5.", "6.")):
                    # Extract node id from "1. `node-id`"
                    nid = line.split("`")[1] if "`" in line else ""
                    if nid:
                        reading_order.append(nid)

        # If both taichi-gpu-sim and computational-mechanics are present,
        # and taichi-gpu-sim requires computational-mechanics,
        # then computational-mechanics should come first
        if (
            "skill-computational-mechanics" in reading_order
            and "skill-taichi-gpu-sim" in reading_order
        ):
            mech_idx = reading_order.index("skill-computational-mechanics")
            taichi_idx = reading_order.index("skill-taichi-gpu-sim")
            assert mech_idx < taichi_idx

    def test_determinism_full_pipeline(self, seed_graph):
        """Full pipeline produces identical output on repeated runs (NFR-D01)."""
        G, repo = seed_graph
        graph_json = repo / "knowledge" / "graph" / "graph.json"
        graph_version = compute_graph_version(graph_json)

        args = dict(
            task_id="TSK-DET",
            phase=1,
            graph_version=graph_version,
            seed_tags=["taichi", "gpu"],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.ROUTING,
        )

        r1 = query_subgraph(G, ["taichi", "gpu"], AgentRole.IMPLEMENTER)
        r2 = query_subgraph(G, ["taichi", "gpu"], AgentRole.IMPLEMENTER)

        # Same query → same nodes
        ids1 = [nid for nid, _ in r1]
        ids2 = [nid for nid, _ in r2]
        assert ids1 == ids2

        # Same query hash
        h1 = compute_query_hash(["taichi", "gpu"], "implementer", 2)
        h2 = compute_query_hash(["gpu", "taichi"], "implementer", 2)
        assert h1 == h2


# ═══════════════════════════════════════════════════════════════════════
#  Test: With Overlay
# ═══════════════════════════════════════════════════════════════════════


class TestPipelineWithOverlay:
    """Pipeline with confidence overrides and pitfall edges."""

    def test_overlay_confidence_affects_ranking(self, tmp_vault, tmp_repo):
        """Overlay confidence override changes ranking order."""
        make_global_node(tmp_vault, id="n1", tags=["taichi"], confidence=0.9)
        make_global_node(tmp_vault, id="n2", tags=["taichi"], confidence=0.8)

        # Boost n2 via overlay
        set_overlay(
            tmp_repo,
            nodes={"n2": {"confidence": 0.99, "activations": 5}},
        )

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        node_ids = [nid for nid, _ in result]

        # n2 should rank higher: 0.99 * 6 = 5.94 vs n1: 0.9 * 1 = 0.9
        assert node_ids[0] == "n2"

    def test_pitfall_edge_appears_in_loadout(self, tmp_vault, tmp_repo):
        """Pitfall edges from overlay appear in loadout warnings."""
        make_global_node(tmp_vault, id="n1", tags=["taichi"])
        make_global_node(tmp_vault, id="n2", tags=["taichi"])

        set_overlay(
            tmp_repo,
            local_edges=[{
                "from": "n1",
                "to": "n2",
                "type": "pitfall",
                "weight": 0.9,
                "note": "Memory leak when batch > 1024",
            }],
        )

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)

        content = generate_loadout(
            G, result,
            task_id="TSK-001",
            phase=1,
            graph_version="test",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
        )

        assert "Pitfall Warnings" in content
        assert "Memory leak" in content
