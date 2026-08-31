"""Tests for update_graph.py — Phase 4: PCD Processing & Local State Updates.

Coverage per development plan Task 4.5:
- Task 4.1: confidence mutations (boost, decay, auto_update skip, floor, idempotent)
- Task 4.2: neighbor propagation (predecessors, edge multipliers, hop_limit)
- Task 4.3: pitfalls → local_edges, session nodes, new knowledge + dedup
- Task 4.4: write-back + recompile (overlay correct, graph.json updated, globals untouched)
"""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest
import yaml

from akms.graph.build_graph import build_graph, load_graph
from akms.graph.update_graph import (
    _create_session_node,
    _extract_persistent_zone,
    _process_new_knowledge,
    _process_nodes_used,
    _process_pitfalls,
    _propagate_to_neighbors,
    _prune_session_refs,
    update_graph,
)
from akms.schema.models import (
    AgentMemory,
    Coverage,
    Lessons,
    NewKnowledge,
    NodeUsedFeedback,
    PCD,
    PitfallDiscovered,
    PropagationConfig,
    TaskStatus,
)

from .conftest import make_global_node, make_local_node, make_mirror_node


# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════


def _make_agent_memory(**overrides) -> AgentMemory:
    """Factory for AgentMemory with sensible defaults."""
    defaults = {
        "task_id": "task-001",
        "task_description": "Implement feature X",
        "phase_id": 1,
        "timestamp": datetime(2026, 3, 7, 12, 0, 0),
        "agent_model": "claude-opus-4-6",
        "loadout_used": "loadouts/phase1_task001.md",
        "status": TaskStatus.COMPLETE,
        "tests_passed": 5,
        "tests_total": 5,
        "nodes_used": [],
        "nodes_missing": [],
        "lessons": Lessons(),
        "pitfalls_discovered": [],
        "new_knowledge": [],
        "akms_schema": "v2",
    }
    defaults.update(overrides)
    return AgentMemory(**defaults)


def _make_pcd(**overrides) -> PCD:
    """Factory for PCD with sensible defaults."""
    defaults = {
        "phase_id": 1,
        "plan_file": "dev/plans/plan.md",
        "branch": "feat/phase-1",
        "date": date(2026, 3, 7),
        "loadout_used": "loadouts/phase1.md",
        "next_phase_warnings": ["No warnings"],
        "nodes_used": [],
        "nodes_missing": [],
        "lessons": Lessons(),
        "pitfalls_discovered": [],
        "new_knowledge": [],
        "akms_schema": "v2",
    }
    defaults.update(overrides)
    return PCD(**defaults)


def _build_and_load(tmp_repo, tmp_vault):
    """Build graph and return the DiGraph."""
    return build_graph(tmp_repo, global_vault=tmp_vault)


class TestConfidenceMutations:
    """Tests for _process_nodes_used (Task 4.1)."""

    def test_boost_useful_node(self, tmp_vault, tmp_repo):
        """useful=true → confidence boosted by activation_boost."""
        make_global_node(tmp_vault, id="node-a", confidence=0.90)
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()
        events = _process_nodes_used(
            G,
            overlay,
            [{"id": "node-a", "useful": True, "coverage": "sufficient"}],
            config,
            "task-001",
            date(2026, 3, 7),
        )

        assert len(events) == 1
        assert events[0]["action"] == "boost"
        assert overlay["nodes"]["node-a"]["confidence"] == pytest.approx(0.92, abs=1e-4)

    def test_decay_missing_detail(self, tmp_vault, tmp_repo):
        """coverage=missing-detail → confidence multiplied by local_decay."""
        make_global_node(tmp_vault, id="node-a", confidence=0.90)
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()
        events = _process_nodes_used(
            G,
            overlay,
            [{"id": "node-a", "useful": False, "coverage": "missing-detail"}],
            config,
            "task-001",
            date(2026, 3, 7),
        )

        assert any(e["action"] == "decay" for e in events)
        # 0.90 * 0.85 = 0.765
        assert overlay["nodes"]["node-a"]["confidence"] == pytest.approx(
            0.765, abs=1e-3
        )

    def test_decay_outdated(self, tmp_vault, tmp_repo):
        """coverage=outdated → same decay as missing-detail."""
        make_global_node(tmp_vault, id="node-a", confidence=0.80)
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()
        events = _process_nodes_used(
            G,
            overlay,
            [{"id": "node-a", "useful": False, "coverage": "outdated"}],
            config,
            "task-001",
            date(2026, 3, 7),
        )

        assert any(e["action"] == "decay" for e in events)
        # 0.80 * 0.85 = 0.68
        assert overlay["nodes"]["node-a"]["confidence"] == pytest.approx(0.68, abs=1e-3)

    def test_boost_and_decay_combined(self, tmp_vault, tmp_repo):
        """useful=true AND coverage=missing-detail → boost first, then decay."""
        make_global_node(tmp_vault, id="node-a", confidence=0.90)
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()
        _process_nodes_used(
            G,
            overlay,
            [{"id": "node-a", "useful": True, "coverage": "missing-detail"}],
            config,
            "task-001",
            date(2026, 3, 7),
        )

        # boost: 0.90 + 0.02 = 0.92, then decay: 0.92 * 0.85 = 0.782
        assert overlay["nodes"]["node-a"]["confidence"] == pytest.approx(
            0.782, abs=1e-3
        )

    def test_skip_auto_update_node(self, tmp_vault, tmp_repo):
        """auto_update=true nodes are skipped entirely."""
        make_mirror_node(tmp_repo, id="mirror-node")
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()
        events = _process_nodes_used(
            G,
            overlay,
            [{"id": "mirror-node", "useful": True, "coverage": "sufficient"}],
            config,
            "task-001",
            date(2026, 3, 7),
        )

        assert len(events) == 0
        assert "mirror-node" not in overlay["nodes"]

    def test_confidence_floor_respected(self, tmp_vault, tmp_repo):
        """Decay cannot drop confidence below confidence_floor."""
        make_global_node(tmp_vault, id="node-a", confidence=0.72, confidence_floor=0.70)
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()
        _process_nodes_used(
            G,
            overlay,
            [{"id": "node-a", "useful": False, "coverage": "missing-detail"}],
            config,
            "task-001",
            date(2026, 3, 7),
        )

        # 0.72 * 0.85 = 0.612 → clamped to floor 0.70
        assert overlay["nodes"]["node-a"]["confidence"] == pytest.approx(0.70, abs=1e-4)

    def test_min_confidence_as_default_floor(self, tmp_vault, tmp_repo):
        """Without confidence_floor, min_confidence (0.10) is used as floor."""
        make_global_node(tmp_vault, id="node-a", confidence=0.12)
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()
        _process_nodes_used(
            G,
            overlay,
            [{"id": "node-a", "useful": False, "coverage": "outdated"}],
            config,
            "task-001",
            date(2026, 3, 7),
        )

        # 0.12 * 0.85 = 0.102 → above min_confidence (0.10), kept
        assert overlay["nodes"]["node-a"]["confidence"] >= 0.10

    def test_max_confidence_respected(self, tmp_vault, tmp_repo):
        """Boost cannot push confidence above max_confidence (0.99)."""
        make_global_node(tmp_vault, id="node-a", confidence=0.98)
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()
        _process_nodes_used(
            G,
            overlay,
            [{"id": "node-a", "useful": True, "coverage": "sufficient"}],
            config,
            "task-001",
            date(2026, 3, 7),
        )

        # 0.98 + 0.02 = 1.00 → clamped to 0.99
        assert overlay["nodes"]["node-a"]["confidence"] == pytest.approx(0.99, abs=1e-4)

    def test_activations_incremented(self, tmp_vault, tmp_repo):
        """Each nodes_used entry increments activations by 1."""
        make_global_node(tmp_vault, id="node-a", confidence=0.90)
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()
        _process_nodes_used(
            G,
            overlay,
            [{"id": "node-a", "useful": True, "coverage": "sufficient"}],
            config,
            "task-001",
            date(2026, 3, 7),
        )

        assert overlay["nodes"]["node-a"]["activations"] == 1

    def test_session_refs_appended(self, tmp_vault, tmp_repo):
        """Session ref is appended to node's session_refs."""
        make_global_node(tmp_vault, id="node-a", confidence=0.90)
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()
        _process_nodes_used(
            G,
            overlay,
            [{"id": "node-a", "useful": True, "coverage": "sufficient"}],
            config,
            "task-001",
            date(2026, 3, 7),
        )

        assert "sessions/task-001.md" in overlay["nodes"]["node-a"]["session_refs"]

    def test_nonexistent_node_skipped(self, tmp_vault, tmp_repo):
        """Node not in graph is logged and skipped."""
        make_global_node(tmp_vault, id="node-a", confidence=0.90)
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()
        events = _process_nodes_used(
            G,
            overlay,
            [{"id": "nonexistent", "useful": True, "coverage": "sufficient"}],
            config,
            "task-001",
            date(2026, 3, 7),
        )

        assert len(events) == 0
        assert "nonexistent" not in overlay["nodes"]

    def test_distinct_sources_accumulate(self, tmp_vault, tmp_repo):
        """Two distinct source_ids referencing the same node each add an
        activation (spec-conformant per NFR-D03: the PCD-level idempotency
        guarantee kicks in when the *same* source is replayed, not when two
        distinct events happen to cite the same node; the same-source
        byte-identical replay is covered separately).
        """
        make_global_node(tmp_vault, id="node-a", confidence=0.90)
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()
        feedback = [{"id": "node-a", "useful": True, "coverage": "sufficient"}]

        _process_nodes_used(G, overlay, feedback, config, "task-001", date(2026, 3, 7))
        first_conf = overlay["nodes"]["node-a"]["confidence"]

        # Second call reads from overlay (not graph), so boost applies on top
        _process_nodes_used(G, overlay, feedback, config, "task-002", date(2026, 3, 7))
        second_conf = overlay["nodes"]["node-a"]["confidence"]

        # Second boost: first_conf + 0.02
        assert second_conf == pytest.approx(first_conf + 0.02, abs=1e-4)
        assert overlay["nodes"]["node-a"]["activations"] == 2


class TestNeighborPropagation:
    """Tests for _propagate_to_neighbors (Task 4.2)."""

    def test_predecessor_receives_propagated_decay(self, tmp_vault, tmp_repo):
        """Predecessor of a decayed node gets a proportional confidence hit."""
        make_global_node(
            tmp_vault,
            id="parent",
            confidence=0.90,
            edges=[{"to": "child", "type": "requires", "weight": 0.8}],
        )
        make_global_node(tmp_vault, id="child", confidence=0.80)
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()

        # Simulate a decay event on 'child'
        decay_events = [
            {
                "node_id": "child",
                "action": "decay",
                "old": 0.80,
                "new": 0.68,
                "reason": "coverage=missing-detail",
            }
        ]

        prop_events = _propagate_to_neighbors(G, overlay, decay_events, config)

        assert len(prop_events) == 1
        assert prop_events[0]["node_id"] == "parent"
        assert prop_events[0]["action"] == "propagated_decay"
        # hit = 0.30 * 1.0 (requires) * 0.8 (weight) * 0.12 (decay magnitude) = 0.0288
        assert prop_events[0]["hit"] == pytest.approx(0.0288, abs=1e-3)
        assert overlay["nodes"]["parent"]["confidence"] < 0.90

    def test_edge_type_multiplier_refines(self, tmp_vault, tmp_repo):
        """refines edge has multiplier 0.7."""
        make_global_node(
            tmp_vault,
            id="parent",
            confidence=0.90,
            edges=[{"to": "child", "type": "refines", "weight": 0.7}],
        )
        make_global_node(tmp_vault, id="child", confidence=0.80)
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()

        decay_events = [
            {
                "node_id": "child",
                "action": "decay",
                "old": 0.80,
                "new": 0.68,
                "reason": "decay",
            }
        ]

        prop_events = _propagate_to_neighbors(G, overlay, decay_events, config)

        # hit = 0.30 * 0.7 (refines) * 0.7 (weight) * 0.12 = 0.01764
        assert len(prop_events) == 1
        assert prop_events[0]["hit"] == pytest.approx(0.01764, abs=1e-3)

    def test_mixed_edge_weights_propagate_proportionally(self, tmp_vault, tmp_repo):
        make_global_node(
            tmp_vault,
            id="parent-high",
            confidence=0.90,
            edges=[{"to": "child", "type": "requires", "weight": 0.9}],
        )
        make_global_node(
            tmp_vault,
            id="parent-low",
            confidence=0.90,
            edges=[{"to": "child", "type": "requires", "weight": 0.2}],
        )
        make_global_node(tmp_vault, id="child", confidence=0.80)
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()
        decay_events = [
            {
                "node_id": "child",
                "action": "decay",
                "old": 0.80,
                "new": 0.68,
                "reason": "decay",
            }
        ]

        prop_events = _propagate_to_neighbors(G, overlay, decay_events, config)
        events_by_node = {event["node_id"]: event for event in prop_events}

        assert set(events_by_node) == {"parent-high", "parent-low"}
        assert events_by_node["parent-high"]["hit"] == pytest.approx(0.0324, abs=1e-3)
        assert events_by_node["parent-low"]["hit"] == pytest.approx(0.0072, abs=1e-3)
        assert (
            events_by_node["parent-high"]["hit"] > events_by_node["parent-low"]["hit"]
        )

    def test_contradicts_no_propagation(self, tmp_vault, tmp_repo):
        """contradicts edge has multiplier 0.0 — no propagation."""
        make_global_node(
            tmp_vault,
            id="parent",
            confidence=0.90,
            edges=[{"to": "child", "type": "contradicts", "weight": 0.5}],
        )
        make_global_node(tmp_vault, id="child", confidence=0.80)
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()

        decay_events = [
            {
                "node_id": "child",
                "action": "decay",
                "old": 0.80,
                "new": 0.68,
                "reason": "decay",
            }
        ]

        prop_events = _propagate_to_neighbors(G, overlay, decay_events, config)

        assert len(prop_events) == 0
        assert "parent" not in overlay.get("nodes", {})

    def test_pitfall_edge_no_propagation(self, tmp_vault, tmp_repo):
        """pitfall edge has multiplier 0.0 — no propagation."""
        make_global_node(
            tmp_vault,
            id="parent",
            confidence=0.90,
            edges=[{"to": "child", "type": "pitfall", "weight": 0.5}],
        )
        make_global_node(tmp_vault, id="child", confidence=0.80)
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()

        decay_events = [
            {
                "node_id": "child",
                "action": "decay",
                "old": 0.80,
                "new": 0.68,
                "reason": "decay",
            }
        ]

        prop_events = _propagate_to_neighbors(G, overlay, decay_events, config)
        assert len(prop_events) == 0

    def test_implements_no_propagation(self, tmp_vault, tmp_repo):
        """implements edge has multiplier 0.0 — no propagation."""
        make_global_node(
            tmp_vault,
            id="parent",
            confidence=0.90,
            edges=[{"to": "child", "type": "implements", "weight": 0.5}],
        )
        make_global_node(tmp_vault, id="child", confidence=0.80)
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()

        decay_events = [
            {
                "node_id": "child",
                "action": "decay",
                "old": 0.80,
                "new": 0.68,
                "reason": "decay",
            }
        ]

        prop_events = _propagate_to_neighbors(G, overlay, decay_events, config)
        assert len(prop_events) == 0

    def test_boost_events_not_propagated(self, tmp_vault, tmp_repo):
        """Only decay events trigger neighbor propagation."""
        make_global_node(
            tmp_vault,
            id="parent",
            confidence=0.90,
            edges=[{"to": "child", "type": "requires", "weight": 0.8}],
        )
        make_global_node(tmp_vault, id="child", confidence=0.80)
        G = _build_and_load(tmp_repo, tmp_vault)

        overlay = {"nodes": {}}
        config = PropagationConfig()

        boost_events = [
            {
                "node_id": "child",
                "action": "boost",
                "old": 0.80,
                "new": 0.82,
                "reason": "useful=true",
            }
        ]

        prop_events = _propagate_to_neighbors(G, overlay, boost_events, config)
        assert len(prop_events) == 0

    def test_auto_update_predecessor_skipped(self, tmp_vault, tmp_repo):
        """auto_update predecessors are not affected by propagation."""
        make_mirror_node(tmp_repo, id="mirror-parent")
        # We need the mirror parent to have an edge to child in the graph.
        # Mirror nodes don't have edges, so we add via overlay.
        make_global_node(tmp_vault, id="child", confidence=0.80)
        G = _build_and_load(tmp_repo, tmp_vault)

        # Manually add edge in graph for testing
        G.add_edge("mirror-parent", "child", type="requires", weight=0.8)

        overlay = {"nodes": {}}
        config = PropagationConfig()

        decay_events = [
            {
                "node_id": "child",
                "action": "decay",
                "old": 0.80,
                "new": 0.68,
                "reason": "decay",
            }
        ]

        prop_events = _propagate_to_neighbors(G, overlay, decay_events, config)
        assert len(prop_events) == 0


class TestPitfallEdges:
    """Tests for _process_pitfalls (Task 4.3)."""

    def test_pitfall_creates_local_edge(self):
        """Pitfall with node_ref creates a pitfall edge in local_edges."""
        overlay = {"local_edges": []}
        events = _process_pitfalls(
            overlay,
            [
                {
                    "node_ref": "node-a",
                    "description": "Watch out for X",
                    "severity": "high",
                }
            ],
            "session-task-001",
        )

        assert len(events) == 1
        assert events[0]["action"] == "pitfall_edge"
        assert len(overlay["local_edges"]) == 1
        edge = overlay["local_edges"][0]
        assert edge["from"] == "node-a"
        assert edge["to"] == "session-task-001"
        assert edge["type"] == "pitfall"
        assert edge["weight"] == 0.8  # high severity

    def test_pitfall_medium_severity_weight(self):
        """Medium severity pitfall gets weight 0.5."""
        overlay = {"local_edges": []}
        _process_pitfalls(
            overlay,
            [
                {
                    "node_ref": "node-a",
                    "description": "Minor issue",
                    "severity": "medium",
                }
            ],
            "session-task-001",
        )

        assert overlay["local_edges"][0]["weight"] == 0.5

    def test_pitfall_without_node_ref_skipped(self):
        """Pitfall without node_ref creates no edge."""
        overlay = {"local_edges": []}
        events = _process_pitfalls(
            overlay,
            [{"description": "General warning", "severity": "low"}],
            "session-task-001",
        )

        assert len(events) == 0
        assert len(overlay["local_edges"]) == 0

    def test_duplicate_pitfall_edge_preserved_as_additive_evidence(self):
        """Repeated pitfall discoveries are preserved as separate evidence entries."""
        overlay = {
            "local_edges": [
                {
                    "from": "node-a",
                    "to": "session-task-001",
                    "type": "pitfall",
                    "weight": 0.8,
                    "note": "old",
                },
            ]
        }
        events = _process_pitfalls(
            overlay,
            [{"node_ref": "node-a", "description": "Same issue", "severity": "high"}],
            "session-task-001",
        )

        assert len(events) == 1
        assert len(overlay["local_edges"]) == 2


class TestSessionNodes:
    """Tests for _create_session_node (Task 4.3)."""

    def test_agent_memory_creates_session_node(self):
        """AgentMemory creates a session node entry."""
        overlay = {"session_nodes": {}}
        mem = _make_agent_memory(task_id="task-001", status=TaskStatus.COMPLETE)
        session_id = _create_session_node(overlay, "task-001", mem, 1)

        assert session_id == "session-task-001"
        assert "session-task-001" in overlay["session_nodes"]
        node = overlay["session_nodes"]["session-task-001"]
        assert node["outcome"] == "success"
        assert node["phase"] == 1

    def test_pcd_creates_session_node(self):
        """PCD creates a session node per phase."""
        overlay = {"session_nodes": {}}
        pcd = _make_pcd(phase_id=2)
        session_id = _create_session_node(overlay, "phase-2", pcd, 2)

        assert session_id == "session-phase-2"
        assert "session-phase-2" in overlay["session_nodes"]

    def test_dict_source_creates_session_node(self):
        """Dict source creates a session node."""
        overlay = {"session_nodes": {}}
        session_id = _create_session_node(
            overlay,
            "task-dict",
            {"outcome": "success"},
            1,
        )

        assert session_id == "session-task-dict"
        assert overlay["session_nodes"]["session-task-dict"]["outcome"] == "success"

    def test_duplicate_session_node_skipped(self):
        """Existing session node is not overwritten."""
        overlay = {
            "session_nodes": {
                "session-task-001": {
                    "title": "Original",
                    "tags": [],
                    "outcome": "failed",
                    "content_ref": "x",
                    "phase": 1,
                },
            }
        }
        mem = _make_agent_memory(task_id="task-001", status=TaskStatus.COMPLETE)
        session_id = _create_session_node(overlay, "task-001", mem, 1)

        assert session_id == "session-task-001"
        assert overlay["session_nodes"]["session-task-001"]["outcome"] == "failed"

    def test_task_status_mapping(self):
        """TaskStatus values map correctly to SessionOutcome."""
        for status, expected_outcome in [
            (TaskStatus.COMPLETE, "success"),
            (TaskStatus.PARTIAL, "partial"),
            (TaskStatus.FAILED, "failed"),
            (TaskStatus.DEFERRED, "partial"),
        ]:
            overlay = {"session_nodes": {}}
            mem = _make_agent_memory(task_id=f"task-{status.value}", status=status)
            _create_session_node(overlay, f"task-{status.value}", mem, 1)
            node = overlay["session_nodes"][f"session-task-{status.value}"]
            assert node["outcome"] == expected_outcome, f"Failed for {status}"


class TestNewKnowledge:
    """Tests for _process_new_knowledge (Task 4.3)."""

    def test_creates_new_local_node(self, tmp_vault, tmp_repo):
        """New knowledge creates a tentative .md file in local-nodes/."""
        G = _build_and_load(tmp_repo, tmp_vault)
        config = PropagationConfig()

        events = _process_new_knowledge(
            G,
            tmp_repo,
            [
                {
                    "suggested_id": "new-concept",
                    "title": "New Concept",
                    "domain": "test",
                    "tags": ["test"],
                    "content_draft": "Some new knowledge.",
                }
            ],
            config,
        )

        assert len(events) == 1
        assert events[0]["action"] == "new_node"
        node_path = tmp_repo / "knowledge" / "local-nodes" / "new-concept.md"
        assert node_path.exists()

        # Verify frontmatter
        import frontmatter as fm

        post = fm.load(str(node_path))
        assert post.metadata["id"] == "new-concept"
        assert post.metadata["status"] == "tentative"
        assert post.metadata["source"] == "agent"
        assert post.metadata["akms_schema"] == "v2"

    def test_dedup_appends_to_existing_local(self, tmp_vault, tmp_repo):
        """If local-nodes/ already has same id, append content."""
        # Create existing local node
        make_local_node(tmp_repo, id="existing-concept", content="Original content.")
        G = _build_and_load(tmp_repo, tmp_vault)
        config = PropagationConfig()

        events = _process_new_knowledge(
            G,
            tmp_repo,
            [
                {
                    "suggested_id": "existing-concept",
                    "title": "Existing",
                    "domain": "test-domain",
                    "tags": ["test"],
                    "content_draft": "Appended content.",
                }
            ],
            config,
        )

        assert len(events) == 1
        assert events[0]["action"] == "dedup_append"

        # Verify content was appended
        import frontmatter as fm

        node_path = tmp_repo / "knowledge" / "local-nodes" / "existing-concept.md"
        post = fm.load(str(node_path))
        assert "Original content." in post.content
        assert "Appended content." in post.content

    def test_dedup_global_tentative_creates_local_variant(self, tmp_vault, tmp_repo):
        """Global tentative match → create local variant with -local suffix."""
        make_global_node(
            tmp_vault, id="global-concept", status="tentative", confidence=0.50
        )
        G = _build_and_load(tmp_repo, tmp_vault)
        config = PropagationConfig()

        events = _process_new_knowledge(
            G,
            tmp_repo,
            [
                {
                    "suggested_id": "global-concept",
                    "title": "Global Concept",
                    "domain": "test-domain",
                    "tags": ["test"],
                    "content_draft": "Local variant content.",
                }
            ],
            config,
        )

        # Should have both dedup_global_skip and new_node events
        actions = [e["action"] for e in events]
        assert "dedup_global_skip" in actions
        assert "new_node" in actions

        # Local variant created with -local suffix
        local_path = tmp_repo / "knowledge" / "local-nodes" / "global-concept-local.md"
        assert local_path.exists()

    def test_empty_suggested_id_skipped(self, tmp_vault, tmp_repo):
        """Entry with empty suggested_id is skipped."""
        G = _build_and_load(tmp_repo, tmp_vault)
        config = PropagationConfig()

        events = _process_new_knowledge(
            G,
            tmp_repo,
            [{"suggested_id": "", "content_draft": "No id."}],
            config,
        )

        assert len(events) == 0

    def test_dedup_threshold_controls_similarity_merge(self, tmp_vault, tmp_repo):
        """Lower threshold merges similar tentative knowledge, higher threshold does not."""
        make_local_node(
            tmp_repo,
            id="kernel-guidance",
            domain="gpu-simulation",
            status="tentative",
            title="Taichi kernel launch guide",
            content="Use block dim tuning for reduction kernels.",
        )
        G = _build_and_load(tmp_repo, tmp_vault)

        entry = {
            "suggested_id": "candidate-kernel-note",
            "title": "Taichi kernel launch bounds",
            "domain": "gpu-simulation",
            "tags": ["taichi", "gpu"],
            "content_draft": "Use block dim tuning and shared memory for reduction kernels.",
        }

        # Lower threshold: should merge into existing local tentative node.
        low_threshold = PropagationConfig()
        low_threshold.graph.dedup_threshold = 0.4
        low_events = _process_new_knowledge(G, tmp_repo, [entry], low_threshold)
        low_actions = [e["action"] for e in low_events]
        assert "dedup_append" in low_actions

        # Reset repo state for high-threshold branch.
        make_local_node(
            tmp_repo,
            id="kernel-guidance",
            domain="gpu-simulation",
            status="tentative",
            title="Taichi kernel launch guide",
            content="Use block dim tuning for reduction kernels.",
        )
        G2 = _build_and_load(tmp_repo, tmp_vault)

        high_threshold = PropagationConfig()
        high_threshold.graph.dedup_threshold = 0.9
        high_events = _process_new_knowledge(G2, tmp_repo, [entry], high_threshold)
        high_actions = [e["action"] for e in high_events]
        assert "new_node" in high_actions


class TestPruneSessionRefs:
    """Tests for _prune_session_refs."""

    def test_prune_excess_refs(self):
        """Session refs beyond max are pruned (oldest removed)."""
        overlay = {
            "nodes": {
                "node-a": {
                    "session_refs": [f"sessions/task-{i:03d}.md" for i in range(15)],
                },
            }
        }
        _prune_session_refs(overlay, max_refs=10)

        assert len(overlay["nodes"]["node-a"]["session_refs"]) == 10
        # Keeps the 10 most recent (last 10)
        assert overlay["nodes"]["node-a"]["session_refs"][0] == "sessions/task-005.md"

    def test_no_prune_under_limit(self):
        """Refs under limit are not touched."""
        overlay = {
            "nodes": {
                "node-a": {"session_refs": ["sessions/a.md", "sessions/b.md"]},
            }
        }
        _prune_session_refs(overlay, max_refs=10)

        assert len(overlay["nodes"]["node-a"]["session_refs"]) == 2


# ═══════════════════════════════════════════════════════════════════════
#  Persistent Zone Extraction
# ═══════════════════════════════════════════════════════════════════════


class TestPersistentZoneExtraction:
    """Tests for _extract_persistent_zone."""

    def test_extract_from_agent_memory(self):
        """AgentMemory persistent zone extraction."""
        mem = _make_agent_memory(
            nodes_used=[
                NodeUsedFeedback(id="n1", useful=True, coverage=Coverage.SUFFICIENT)
            ],
            pitfalls_discovered=[
                PitfallDiscovered(node_ref="n1", description="bug", severity="high")
            ],
        )
        pz = _extract_persistent_zone(mem)

        assert len(pz["nodes_used"]) == 1
        assert pz["nodes_used"][0]["id"] == "n1"
        assert len(pz["pitfalls_discovered"]) == 1

    def test_extract_from_pcd(self):
        """PCD persistent zone extraction."""
        pcd = _make_pcd(
            nodes_used=[
                NodeUsedFeedback(id="n1", useful=True, coverage=Coverage.SUFFICIENT)
            ],
        )
        pz = _extract_persistent_zone(pcd)

        assert len(pz["nodes_used"]) == 1

    def test_extract_from_dict(self):
        """Dict passthrough."""
        d = {"nodes_used": [{"id": "n1"}], "pitfalls_discovered": []}
        pz = _extract_persistent_zone(d)
        assert pz is d

    def test_unsupported_type_raises(self):
        """Unsupported type raises TypeError."""
        with pytest.raises(TypeError):
            _extract_persistent_zone(42)


# ═══════════════════════════════════════════════════════════════════════
#  Integration: Full update_graph Pipeline
# ═══════════════════════════════════════════════════════════════════════


class TestUpdateGraphIntegration:
    """End-to-end integration tests for update_graph()."""

    def test_full_mutation_chain(self, tmp_vault, tmp_repo):
        """Full pipeline: AgentMemory → confidence + pitfall + session + knowledge."""
        make_global_node(tmp_vault, id="node-a", confidence=0.90, tags=["test"])
        make_global_node(
            tmp_vault,
            id="node-b",
            confidence=0.85,
            tags=["test"],
            edges=[{"to": "node-a", "type": "requires", "weight": 0.8}],
        )

        mem = _make_agent_memory(
            nodes_used=[
                NodeUsedFeedback(
                    id="node-a", useful=True, coverage=Coverage.MISSING_DETAIL
                ),
            ],
            pitfalls_discovered=[
                PitfallDiscovered(
                    node_ref="node-a", description="Edge case X", severity="high"
                ),
            ],
            new_knowledge=[
                NewKnowledge(
                    suggested_id="discovery-1",
                    title="Discovery 1",
                    domain="test",
                    tags=["test"],
                    content_draft="New finding.",
                ),
            ],
        )

        result = update_graph(mem, tmp_repo, global_vault=tmp_vault)

        # Confidence events
        assert len(result["confidence_events"]) >= 1

        # Propagation events (node-b is predecessor of node-a via requires)
        assert len(result["propagation_events"]) >= 1

        # Pitfall
        assert len(result["pitfall_events"]) == 1

        # Knowledge
        assert len(result["knowledge_events"]) == 1

        # Session node
        assert result["session_node_id"] == "session-task-001"

        # Verify local_state.yaml was written
        overlay_path = tmp_repo / "knowledge" / "graph" / "local_state.yaml"
        assert overlay_path.exists()
        overlay = yaml.safe_load(overlay_path.read_text())
        assert "node-a" in overlay["nodes"]
        assert "session-task-001" in overlay["session_nodes"]
        assert len(overlay["local_edges"]) >= 1
        assert len(overlay.get("coverage_flags", [])) >= 1

        # Verify graph.json was recompiled
        graph_json = tmp_repo / "knowledge" / "graph" / "graph.json"
        assert graph_json.exists()

    def test_global_files_untouched(self, tmp_vault, tmp_repo):
        """Global node .md files are never modified by update_graph."""
        global_path = make_global_node(tmp_vault, id="node-a", confidence=0.90)
        original_content = global_path.read_bytes()

        mem = _make_agent_memory(
            nodes_used=[
                NodeUsedFeedback(id="node-a", useful=False, coverage=Coverage.OUTDATED),
            ],
        )

        update_graph(mem, tmp_repo, global_vault=tmp_vault)

        # Global file content is IDENTICAL
        assert global_path.read_bytes() == original_content

    def test_pcd_source_works(self, tmp_vault, tmp_repo):
        """PCD is processed identically to AgentMemory."""
        make_global_node(tmp_vault, id="node-a", confidence=0.90)

        pcd = _make_pcd(
            nodes_used=[
                NodeUsedFeedback(
                    id="node-a", useful=True, coverage=Coverage.SUFFICIENT
                ),
            ],
        )

        result = update_graph(pcd, tmp_repo, global_vault=tmp_vault)

        assert len(result["confidence_events"]) == 1
        assert result["session_node_id"] == "session-phase-1"

    def test_dict_source_works(self, tmp_vault, tmp_repo):
        """Dict persistent zone is processed correctly."""
        make_global_node(tmp_vault, id="node-a", confidence=0.90)

        source = {
            "task_id": "dict-task",
            "phase_id": 1,
            "nodes_used": [{"id": "node-a", "useful": True, "coverage": "sufficient"}],
            "pitfalls_discovered": [],
            "new_knowledge": [],
        }

        result = update_graph(source, tmp_repo, global_vault=tmp_vault)

        assert len(result["confidence_events"]) == 1

    def test_recompile_false_skips_build(self, tmp_vault, tmp_repo):
        """recompile=False skips graph.json rebuild."""
        make_global_node(tmp_vault, id="node-a", confidence=0.90)
        # Build initial graph
        build_graph(tmp_repo, global_vault=tmp_vault)

        graph_json = tmp_repo / "knowledge" / "graph" / "graph.json"
        original_mtime = graph_json.stat().st_mtime

        import time

        time.sleep(0.05)

        mem = _make_agent_memory(
            nodes_used=[
                NodeUsedFeedback(id="node-a", useful=True, coverage=Coverage.SUFFICIENT)
            ],
        )

        update_graph(mem, tmp_repo, global_vault=tmp_vault, recompile=False)

        # graph.json should not have been rewritten
        # (mtime stays the same)
        assert graph_json.stat().st_mtime == original_mtime

    def test_overlay_confidence_applied_in_recompiled_graph(self, tmp_vault, tmp_repo):
        """After update_graph + recompile, graph.json reflects new confidence."""
        make_global_node(tmp_vault, id="node-a", confidence=0.90)

        mem = _make_agent_memory(
            nodes_used=[
                NodeUsedFeedback(
                    id="node-a", useful=True, coverage=Coverage.SUFFICIENT
                ),
            ],
        )

        update_graph(mem, tmp_repo, global_vault=tmp_vault)

        # Load recompiled graph
        graph_json = tmp_repo / "knowledge" / "graph" / "graph.json"
        G = load_graph(graph_json)

        # Confidence should reflect the boost (0.90 + 0.02 = 0.92)
        assert G.nodes["node-a"]["confidence"] == pytest.approx(0.92, abs=1e-3)

    def test_new_knowledge_file_in_recompiled_graph(self, tmp_vault, tmp_repo):
        """New knowledge node appears in recompiled graph."""
        make_global_node(tmp_vault, id="node-a", confidence=0.90)

        mem = _make_agent_memory(
            nodes_used=[
                NodeUsedFeedback(
                    id="node-a", useful=True, coverage=Coverage.SUFFICIENT
                ),
            ],
            new_knowledge=[
                NewKnowledge(
                    suggested_id="new-discovery",
                    title="New Discovery",
                    domain="test",
                    tags=["test"],
                    content_draft="Important finding.",
                ),
            ],
        )

        update_graph(mem, tmp_repo, global_vault=tmp_vault)

        # Recompiled graph should contain the new local node
        graph_json = tmp_repo / "knowledge" / "graph" / "graph.json"
        G = load_graph(graph_json)
        assert "new-discovery" in G.nodes

    def test_dedup_events_persisted_to_overlay(self, tmp_vault, tmp_repo):
        """Dedup actions are persisted for graph_status reporting."""
        make_local_node(
            tmp_repo,
            id="existing-idea",
            domain="test-domain",
            status="tentative",
            content="Original idea text.",
        )
        build_graph(tmp_repo, global_vault=tmp_vault)

        mem = _make_agent_memory(
            new_knowledge=[
                NewKnowledge(
                    suggested_id="existing-idea",
                    title="Existing Idea",
                    domain="test-domain",
                    tags=["test"],
                    content_draft="Original idea text with more detail.",
                ),
            ],
        )

        update_graph(mem, tmp_repo, global_vault=tmp_vault)

        overlay = yaml.safe_load(
            (tmp_repo / "knowledge" / "graph" / "local_state.yaml").read_text()
        )
        dedup_events = overlay.get("dedup_events", [])
        assert len(dedup_events) >= 1
        assert dedup_events[-1]["action"] in ("dedup_append", "dedup_global_skip")

    def test_rebuild_from_scratch_yields_identical(self, tmp_vault, tmp_repo):
        """Rebuilding graph from scratch after update yields same result."""
        make_global_node(tmp_vault, id="node-a", confidence=0.90)

        mem = _make_agent_memory(
            nodes_used=[
                NodeUsedFeedback(
                    id="node-a", useful=True, coverage=Coverage.SUFFICIENT
                ),
            ],
        )

        update_graph(mem, tmp_repo, global_vault=tmp_vault)

        # Load first graph
        graph_json = tmp_repo / "knowledge" / "graph" / "graph.json"
        first = json.loads(graph_json.read_text())

        # Rebuild from scratch
        build_graph(tmp_repo, global_vault=tmp_vault)
        second = json.loads(graph_json.read_text())

        assert first == second
