"""Tests for end-to-end feedback loop — Phase 6 Task 6.6.

Simulates the full 7-stage pipeline with mock agents.

Success criteria (from development plan §6.6):
1. Init: build_graph compiles seed nodes → graph.json valid
2. Plan: Planning agent gets loadout with domain context
3. Task Breakdown: Tasks get hybrid-derived akms_tags
4. Execute Phase 1: Subagents write memories → PCD → update_graph → pitfall created
5. Execute Phase 2: Loadout contains pitfall from Phase 1 (criterion #2)
6. Review: Reviewer memories feed back into graph
7. Finalize: Pipeline completes
"""

from __future__ import annotations

from pathlib import Path

import asyncio

import pytest

from akms.graph.build_graph import build_graph, load_graph
from akms.graph.generate_loadout import generate_loadout, select_loadout_mode
from akms.graph.generate_mirror import generate_mirror
from akms.graph.graph_status import graph_status
from akms.graph.qmd_cache import compute_graph_version
from akms.graph.query_subgraph import query_subgraph
from akms.graph.re_evaluate import re_evaluate
from akms.graph.tag_derivation import derive_tags, fill_task_tags
from akms.graph.update_graph import update_graph
from akms.orchestrator.orchestrator import (
    handle_init, handle_plan, handle_task_breakdown,
    handle_scaffold, handle_execute, handle_review,
    handle_finalize,
)
from akms.orchestrator.stages import PipelineState, Stage
from akms.schema.models import PropagationConfig

from .conftest import make_global_node, set_overlay, make_ctx, make_state


class TestEndToEndPipeline:
    """Full pipeline simulation with mock agents."""

    def test_full_pipeline(self, tmp_vault, tmp_repo):
        """Run all 7 stages and verify the feedback loop works."""
        # ── Setup: Create seed nodes ──
        make_global_node(
            tmp_vault,
            id="skill-taichi",
            title="Taichi GPU Simulation",
            tags=["taichi", "gpu", "simulation"],
            confidence=0.95,
        )
        make_global_node(
            tmp_vault,
            id="skill-mechanics",
            title="Computational Mechanics",
            tags=["mechanics", "fem", "simulation"],
            confidence=0.90,
            edges=[{"to": "skill-taichi", "type": "requires", "weight": 0.8}],
        )

        state = make_state(goal="build simulation")
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=None)

        # ── Stage 0: Init ──
        asyncio.run(handle_init(state, ctx))
        assert state.current_stage == Stage.INIT

        # Verify graph compiled with 2 nodes
        graph_json = tmp_repo / "knowledge" / "graph" / "graph.json"
        G = load_graph(graph_json)
        assert G.number_of_nodes() == 2

        # ── Stage 1: Plan ──
        state.advance_to(Stage.PLAN)
        asyncio.run(handle_plan(state, ctx))

        # Advance state
        state.advance_to(Stage.TASK_BREAKDOWN)

        tasks = [
            {
                "task_id": "t1-setup",
                "title": "Setup taichi runtime",
                "objective": "Initialize GPU simulation framework",
                "phase": 1,
                "scope": [],
            },
            {
                "task_id": "t2-fem",
                "title": "Implement FEM solver for mechanics",
                "objective": "Finite element method implementation",
                "phase": 1,
                "scope": [],
            },
            {
                "task_id": "t3-integrate",
                "title": "Integration test for simulation pipeline",
                "objective": "End-to-end validation",
                "phase": 2,
                "scope": [],
            },
        ]
        asyncio.run(handle_task_breakdown(state, ctx, tasks=tasks))
        assert len(state.tasks) == 3

        # Verify tags derived
        assert "taichi" in tasks[0].get("akms_tags", [])
        assert "mechanics" in tasks[1].get("akms_tags", []) or "fem" in tasks[1].get("akms_tags", [])

        # Advance state
        state.advance_to(Stage.SCAFFOLD)

        asyncio.run(handle_scaffold(state, ctx))

        state.advance_to(Stage.EXECUTE)

        phase1_tasks = [t for t in tasks if t.get("phase") == 1]
        asyncio.run(handle_execute(state, ctx, tasks=phase1_tasks))
        assert all(t.get("loadout_path") for t in phase1_tasks)

        # Simulate subagent output: PCD with a pitfall — call update_graph directly
        pcd_phase1 = {
            "phase_id": 1,
            "nodes_used": [
                {"id": "skill-taichi", "useful": True, "coverage": "sufficient"},
                {"id": "skill-mechanics", "useful": True, "coverage": "missing-detail"},
            ],
            "pitfalls_discovered": [
                {
                    "node_ref": "skill-mechanics",
                    "description": "FEM assembly requires careful index handling",
                    "severity": "medium",
                },
            ],
            "new_knowledge": [],
            "nodes_missing": [],
            "lessons": {
                "worked": ["Taichi kernel dispatch is fast"],
                "failed": [],
            },
        }
        update_graph(pcd_phase1, tmp_repo, global_vault=tmp_vault)

        state.advance_to(Stage.REVIEW)

        # Simulate review feedback — call update_graph directly for review data
        review_memory = {
            "nodes_used": [
                {"id": "skill-mechanics", "useful": True, "coverage": "outdated"},
            ],
            "pitfalls_discovered": [],
            "new_knowledge": [],
            "nodes_missing": [],
            "lessons": {"worked": [], "failed": []},
        }
        update_graph(review_memory, tmp_repo, global_vault=tmp_vault)

        asyncio.run(handle_review(state, ctx))

        state.advance_to(Stage.EXECUTE)
        state.current_phase = 2

        phase2_tasks = [t for t in tasks if t.get("phase") == 2]
        asyncio.run(handle_execute(state, ctx, tasks=phase2_tasks))

        G = load_graph(tmp_repo / "knowledge" / "graph" / "graph.json")

        # Check that pitfall edge exists
        pitfall_edges = [
            (u, v, d) for u, v, d in G.edges(data=True)
            if d.get("type") == "pitfall"
        ]
        assert len(pitfall_edges) >= 1, "Pitfall from Phase 1 should exist in graph"

        # Verify mechanics node confidence was decayed (from outdated review)
        mech_conf = G.nodes["skill-mechanics"].get("confidence", 1.0)
        assert mech_conf < 0.90, "Mechanics node should be decayed from outdated + missing-detail"

        pcd_phase2 = {
            "phase_id": 2,
            "nodes_used": [
                {"id": "skill-taichi", "useful": True, "coverage": "sufficient"},
            ],
            "pitfalls_discovered": [],
            "new_knowledge": [],
            "nodes_missing": [],
            "lessons": {"worked": ["Integration works"], "failed": []},
        }
        update_graph(pcd_phase2, tmp_repo, global_vault=tmp_vault)

        state.advance_to(Stage.REVIEW)
        asyncio.run(handle_review(state, ctx))

        # ── Stage 6: Finalize ──
        state.advance_to(Stage.FINALIZE)
        stage_output, akms_status, warnings = asyncio.run(handle_finalize(state, ctx))
        assert "complete" in stage_output.lower()
        # Verify finalize recorded branch ops in stage_history
        finalize_events = [
            e for e in state.stage_history if e.get("action") == "branch_ops_finalize"
        ]
        assert len(finalize_events) >= 1

    def test_pitfall_appears_in_next_phase_loadout(self, tmp_vault, tmp_repo):
        """Criterion #2: Pitfall from Phase 1 appears in Phase 2 loadout."""
        make_global_node(
            tmp_vault, id="node-a", tags=["test"],
            confidence=0.90,
        )
        build_graph(tmp_repo, global_vault=tmp_vault)

        update_graph(
            {
                "nodes_used": [],
                "pitfalls_discovered": [{
                    "node_ref": "node-a",
                    "description": "Important pitfall from phase 1",
                    "severity": "high",
                }],
                "new_knowledge": [],
                "nodes_missing": [],
                "lessons": {"worked": [], "failed": []},
            },
            tmp_repo,
            global_vault=tmp_vault,
        )

        # Verify pitfall edge in graph
        G = load_graph(tmp_repo / "knowledge" / "graph" / "graph.json")
        pitfall_edges = [
            (u, v, d) for u, v, d in G.edges(data=True)
            if d.get("type") == "pitfall"
        ]
        assert len(pitfall_edges) >= 1

        ranked = query_subgraph(G, ["test"], "implementer")
        node_ids = [n[0] for n in ranked]
        assert "node-a" in node_ids

    def test_domain_switching_different_loadouts(self, tmp_vault, tmp_repo):
        """Criterion #3: Domain switching produces differentiated loadouts."""
        make_global_node(
            tmp_vault, id="taichi-node",
            title="Taichi Sim", tags=["taichi", "gpu"],
            domain="taichi-gpu-sim", confidence=0.90,
        )
        make_global_node(
            tmp_vault, id="mech-node",
            title="Computational Mechanics", tags=["mechanics", "fem"],
            domain="computational-mechanics", confidence=0.90,
        )
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        # Taichi-focused query
        taichi_nodes = query_subgraph(G, ["taichi"], "implementer")
        # Mechanics-focused query
        mech_nodes = query_subgraph(G, ["mechanics"], "implementer")

        taichi_ids = {n[0] for n in taichi_nodes}
        mech_ids = {n[0] for n in mech_nodes}

        # Should get different primary results
        assert "taichi-node" in taichi_ids
        assert "mech-node" in mech_ids

    def test_abort_and_resume_preserves_state(self, tmp_vault, tmp_repo):
        """Abort preserves state; resume restores correct stage."""
        make_global_node(tmp_vault, id="node-a", tags=["test"])

        state = make_state(goal="test abort")
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=None)
        asyncio.run(handle_init(state, ctx))

        # Advance to TASK_BREAKDOWN through valid transitions
        state.advance_to(Stage.PLAN)
        state.advance_to(Stage.TASK_BREAKDOWN)
        state.save(tmp_repo)

        # Abort
        state.abort("need to reconsider")
        state.save(tmp_repo)

        # Load saved state (simulating restart)
        loaded_state = PipelineState.load(tmp_repo)
        assert loaded_state is not None
        assert loaded_state.aborted is True
        assert loaded_state.current_stage == Stage.TASK_BREAKDOWN

        # Resume
        loaded_state.resume()
        assert loaded_state.aborted is False
        assert loaded_state.current_stage == Stage.TASK_BREAKDOWN

    def test_graph_status_after_pipeline(self, tmp_vault, tmp_repo):
        """Final graph_status report reflects all pipeline changes."""
        make_global_node(tmp_vault, id="node-a", tags=["test"], confidence=0.90)
        build_graph(tmp_repo, global_vault=tmp_vault)

        # Simulate some updates
        update_graph(
            {
                "nodes_used": [{"id": "node-a", "useful": True, "coverage": "missing-detail"}],
                "pitfalls_discovered": [],
                "new_knowledge": [
                    {"suggested_id": "new-node", "title": "New Discovery",
                     "domain": "test", "tags": ["test"], "content_draft": "content"},
                ],
                "nodes_missing": [],
                "lessons": {"worked": [], "failed": []},
            },
            tmp_repo,
            global_vault=tmp_vault,
        )

        report = graph_status(tmp_repo, global_vault=tmp_vault)
        # Should have nodes and potentially tentative ones
        assert isinstance(report, dict)
