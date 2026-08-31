"""Tests for AKMS schema models and validators (Phase 1).

Covers:
- Global node frontmatter validation
- Local node frontmatter validation
- Local state overlay validation
- AgentMemory validation
- PCD validation
- Schema version enforcement
- Experiential field rejection in global nodes
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from akms.schema.errors import SchemaValidationError, SchemaVersionError
from akms.schema.models import (
    AgentMemory,
    GlobalNodeFrontmatter,
    LocalNodeFrontmatter,
    LocalStateOverlay,
    NodeStatus,
    PCD,
    PropagationConfig,
)
from akms.schema.validators import (
    parse_agent_memory,
    parse_local_state,
    parse_node_frontmatter,
    parse_pcd,
    parse_propagation_config,
)

from .conftest import make_global_node, make_local_node, write_node_md


# ══════════════════════════════════════════════════════════════════════
#  Global Node Frontmatter Tests
# ══════════════════════════════════════════════════════════════════════


class TestGlobalNodeFrontmatter:
    def test_valid_global_node_parses(self, tmp_vault):
        path = make_global_node(
            tmp_vault,
            id="lippmann-schwinger",
            title="Lippmann-Schwinger Equation",
            domain="fft-galerkin",
            tags=["green-operator", "spectral"],
            confidence=0.90,
            edges=[
                {"to": "fft-basics", "type": "requires", "weight": 1.0},
            ],
        )
        node = parse_node_frontmatter(path, is_local=False)
        assert isinstance(node, GlobalNodeFrontmatter)
        assert node.id == "lippmann-schwinger"
        assert node.confidence == 0.90
        assert len(node.edges) == 1
        assert node.edges[0].type.value == "requires"

    def test_missing_required_field_raises(self, tmp_vault):
        """Node without 'id' should fail."""
        path = write_node_md(
            tmp_vault / "bad.md",
            {
                # Missing 'id'
                "title": "Bad Node",
                "domain": "test",
                "tags": ["test"],
                "status": "established",
                "confidence": 0.90,
                "source": "human",
                "akms_schema": "v2",
            },
        )
        with pytest.raises(SchemaValidationError):
            parse_node_frontmatter(path)

    def test_bad_status_enum_raises(self, tmp_vault):
        path = write_node_md(
            tmp_vault / "bad-status.md",
            {
                "id": "bad-status",
                "title": "Bad Status",
                "domain": "test",
                "tags": ["test"],
                "status": "invalid-status",
                "confidence": 0.90,
                "source": "human",
                "akms_schema": "v2",
            },
        )
        with pytest.raises(SchemaValidationError):
            parse_node_frontmatter(path)

    def test_schema_version_mismatch_raises(self, tmp_vault):
        path = write_node_md(
            tmp_vault / "old.md",
            {
                "id": "old-node",
                "title": "Old Node",
                "domain": "test",
                "tags": ["test"],
                "status": "established",
                "confidence": 0.90,
                "source": "human",
                "akms_schema": "v1",
            },
        )
        with pytest.raises(SchemaVersionError) as exc_info:
            parse_node_frontmatter(path)
        assert exc_info.value.found == "v1"

    def test_experiential_field_in_global_raises(self, tmp_vault):
        """Global nodes must not have activations, session_refs, etc."""
        path = write_node_md(
            tmp_vault / "exp.md",
            {
                "id": "exp-node",
                "title": "Node with activations",
                "domain": "test",
                "tags": ["test"],
                "status": "established",
                "confidence": 0.90,
                "source": "human",
                "activations": 5,  # Not allowed in global
                "akms_schema": "v2",
            },
        )
        with pytest.raises(SchemaValidationError, match="experiential"):
            parse_node_frontmatter(path)

    def test_confidence_out_of_range_raises(self, tmp_vault):
        path = write_node_md(
            tmp_vault / "high.md",
            {
                "id": "high-conf",
                "title": "Too High",
                "domain": "test",
                "tags": ["test"],
                "status": "established",
                "confidence": 1.5,
                "source": "human",
                "akms_schema": "v2",
            },
        )
        with pytest.raises(SchemaValidationError):
            parse_node_frontmatter(path)

    def test_empty_tags_raises(self, tmp_vault):
        path = write_node_md(
            tmp_vault / "no-tags.md",
            {
                "id": "no-tags",
                "title": "No Tags",
                "domain": "test",
                "tags": [],
                "status": "established",
                "confidence": 0.90,
                "source": "human",
                "akms_schema": "v2",
            },
        )
        with pytest.raises(SchemaValidationError):
            parse_node_frontmatter(path)

    def test_optional_fields_default(self, tmp_vault):
        path = make_global_node(tmp_vault, id="minimal")
        node = parse_node_frontmatter(path)
        assert node.subdomain is None
        assert node.confidence_floor is None
        assert node.context_size is None
        assert node.content_ref is None
        assert node.load_with == []

    def test_all_edge_types_valid(self, tmp_vault):
        edges = [
            {"to": "a", "type": "requires", "weight": 1.0},
            {"to": "b", "type": "feeds-into", "weight": 0.5},
            {"to": "c", "type": "refines", "weight": 0.7},
            {"to": "d", "type": "contradicts", "weight": 0.3},
            {"to": "e", "type": "pitfall", "weight": 0.8},
            {"to": "f", "type": "implements", "weight": 0.6},
        ]
        path = make_global_node(tmp_vault, id="all-edges", edges=edges)
        node = parse_node_frontmatter(path)
        assert len(node.edges) == 6


# ══════════════════════════════════════════════════════════════════════
#  Local Node Frontmatter Tests
# ══════════════════════════════════════════════════════════════════════


class TestLocalNodeFrontmatter:
    def test_valid_local_node_parses(self, tmp_repo):
        path = make_local_node(
            tmp_repo,
            id="local-pitfall",
            source="agent",
            status="tentative",
        )
        node = parse_node_frontmatter(path, is_local=True)
        assert isinstance(node, LocalNodeFrontmatter)
        assert node.source.value == "agent"

    def test_local_source_generated_raises(self, tmp_repo):
        """Local nodes cannot have source='generated' (reserved for code-mirror)."""
        path = write_node_md(
            tmp_repo / "knowledge" / "local-nodes" / "bad.md",
            {
                "id": "bad-local",
                "title": "Bad Local",
                "domain": "test",
                "tags": ["test"],
                "status": "tentative",
                "confidence": 0.70,
                "source": "generated",
                "akms_schema": "v2",
            },
        )
        with pytest.raises(SchemaValidationError):
            parse_node_frontmatter(path, is_local=True)

    def test_local_human_source_valid(self, tmp_repo):
        path = make_local_node(tmp_repo, id="human-local", source="human")
        node = parse_node_frontmatter(path, is_local=True)
        assert node.source.value == "human"

    def test_local_agent_source_requires_tentative_status(self, tmp_repo):
        path = make_local_node(
            tmp_repo,
            id="agent-established-invalid",
            source="agent",
            status="established",
        )
        with pytest.raises(SchemaValidationError):
            parse_node_frontmatter(path, is_local=True)

    def test_local_human_source_can_be_established(self, tmp_repo):
        path = make_local_node(
            tmp_repo,
            id="human-established-valid",
            source="human",
            status="established",
        )
        node = parse_node_frontmatter(path, is_local=True)
        assert node.source.value == "human"
        assert node.status.value == "established"


# ══════════════════════════════════════════════════════════════════════
#  Local State Overlay Tests
# ══════════════════════════════════════════════════════════════════════


class TestLocalStateOverlay:
    def test_valid_overlay_parses(self, tmp_path):
        path = tmp_path / "local_state.yaml"
        data = {
            "akms_schema": "v2",
            "repo_id": "tifem",
            "nodes": {
                "lippmann-schwinger": {
                    "confidence": 0.85,
                    "activations": 7,
                    "last_activated": "2025-06-01",
                }
            },
            "local_edges": [
                {
                    "from": "lippmann-schwinger",
                    "to": "session-phase2",
                    "type": "pitfall",
                    "weight": 0.8,
                    "note": "Division by zero near zero freq",
                }
            ],
            "session_nodes": {
                "session-phase2": {
                    "title": "Session: phase2",
                    "tags": ["fft"],
                    "outcome": "success",
                    "content_ref": "sessions/phase2.md",
                    "phase": 2,
                }
            },
            "suppressed_edges": [],
        }
        path.write_text(yaml.dump(data))
        overlay = parse_local_state(path)
        assert isinstance(overlay, LocalStateOverlay)
        assert "lippmann-schwinger" in overlay.nodes
        assert overlay.nodes["lippmann-schwinger"].confidence == 0.85
        assert len(overlay.local_edges) == 1
        assert overlay.local_edges[0].from_node == "lippmann-schwinger"

    def test_non_empty_suppressed_edges_raises(self, tmp_path):
        path = tmp_path / "bad_overlay.yaml"
        data = {
            "akms_schema": "v2",
            "nodes": {},
            "local_edges": [],
            "session_nodes": {},
            "suppressed_edges": [{"from": "a", "to": "b"}],
        }
        path.write_text(yaml.dump(data))
        with pytest.raises(SchemaValidationError, match="suppressed"):
            parse_local_state(path)

    def test_empty_overlay_returns_default(self, tmp_path):
        path = tmp_path / "empty.yaml"
        path.write_text("")
        overlay = parse_local_state(path)
        assert isinstance(overlay, LocalStateOverlay)
        assert overlay.nodes == {}

    def test_local_edge_source_id_roundtrip(self, tmp_path):
        """PR19-T1: LocalEdge.source_id is preserved through parse/serialize so
        the replay ledger (F-03) can dedup across sessions even if the overlay
        is round-tripped through the Pydantic model."""
        path = tmp_path / "overlay.yaml"
        data = {
            "akms_schema": "v2",
            "local_edges": [
                {
                    "from": "node-a",
                    "to": "session-1",
                    "type": "pitfall",
                    "weight": 0.5,
                    "note": "first sighting",
                    "source_id": "task-123",
                },
                {
                    "from": "node-a",
                    "to": "session-2",
                    "type": "pitfall",
                    "weight": 0.5,
                    "note": "second sighting",
                    # no source_id — defaults to ""
                },
            ],
        }
        path.write_text(yaml.dump(data))

        overlay = parse_local_state(path)
        assert overlay.local_edges[0].source_id == "task-123"
        assert overlay.local_edges[1].source_id == ""

        # Serialize back through the model — field must survive.
        dumped = overlay.model_dump(by_alias=True)
        assert dumped["local_edges"][0]["source_id"] == "task-123"
        assert dumped["local_edges"][1]["source_id"] == ""


# ══════════════════════════════════════════════════════════════════════
#  AgentMemory Tests
# ══════════════════════════════════════════════════════════════════════


class TestAgentMemory:
    def test_valid_agent_memory_parses(self, tmp_path):
        path = write_node_md(
            tmp_path / "TCR-101.md",
            {
                "task_id": "TCR-101",
                "task_description": "Fix get_Edot",
                "phase_id": 1,
                "timestamp": "2026-03-04T10:32:00",
                "agent_model": "claude-opus-4-6",
                "loadout_used": "loadouts/phase1-loadout.md",
                "status": "complete",
                "tests_passed": 7,
                "tests_total": 7,
                "nodes_used": [
                    {"id": "skill-cm", "useful": True, "coverage": "sufficient"},
                ],
                "nodes_missing": [],
                "pitfalls_discovered": [],
                "new_knowledge": [],
                "akms_schema": "v2",
            },
            "## Task Notes\nSome observations.",
        )
        mem = parse_agent_memory(path)
        assert isinstance(mem, AgentMemory)
        assert mem.task_id == "TCR-101"
        assert mem.tests_passed == 7
        assert len(mem.nodes_used) == 1

    def test_missing_task_id_raises(self, tmp_path):
        path = write_node_md(
            tmp_path / "bad.md",
            {
                # Missing task_id
                "phase_id": 1,
                "timestamp": "2026-03-04T10:32:00",
                "agent_model": "claude-opus-4-6",
                "loadout_used": "loadouts/x.md",
                "status": "complete",
                "tests_passed": 0,
                "tests_total": 0,
                "akms_schema": "v2",
            },
        )
        with pytest.raises(SchemaValidationError):
            parse_agent_memory(path)


# ══════════════════════════════════════════════════════════════════════
#  PCD Tests
# ══════════════════════════════════════════════════════════════════════


class TestPCD:
    def test_valid_pcd_parses(self, tmp_path):
        path = write_node_md(
            tmp_path / "handoff_phase_1.md",
            {
                "phase_id": 1,
                "plan_file": "dev/plans/review.md",
                "branch": "review_phase-1",
                "date": "2026-03-04",
                "loadout_used": "loadouts/phase1-loadout.md",
                "tasks": [
                    {
                        "task_id": "TCR-101",
                        "title": "Fix get_Edot",
                        "tests_passed": 7,
                        "tests_total": 7,
                        "status": "complete",
                        "agent_model": "claude-opus-4-6",
                    }
                ],
                "overall_test_status": {
                    "dedicated_passing": 73,
                    "dedicated_total": 74,
                },
                "next_phase_warnings": ["No warnings"],
                "nodes_used": [
                    {"id": "skill-cm", "useful": True, "coverage": "sufficient"},
                ],
                "pitfalls_discovered": [
                    {
                        "node_ref": "skill-cm",
                        "description": "Matrix product order",
                        "severity": "medium",
                    },
                ],
                "new_knowledge": [],
                "akms_schema": "v2",
            },
            "## Session Notes\nPhase 1 complete.",
        )
        pcd = parse_pcd(path)
        assert isinstance(pcd, PCD)
        assert pcd.phase_id == 1
        assert len(pcd.tasks) == 1

    def test_pcd_extract_persistent_zone(self, tmp_path):
        path = write_node_md(
            tmp_path / "handoff.md",
            {
                "phase_id": 1,
                "plan_file": "plan.md",
                "branch": "b",
                "date": "2026-03-04",
                "loadout_used": "l.md",
                "next_phase_warnings": ["warning"],
                "nodes_used": [
                    {"id": "n1", "useful": True, "coverage": "sufficient"},
                ],
                "pitfalls_discovered": [
                    {"node_ref": "n1", "description": "pitfall", "severity": "high"},
                ],
                "new_knowledge": [
                    {
                        "suggested_id": "new-1",
                        "content_draft": "Draft content",
                        "status": "tentative",
                        "source": "agent",
                    }
                ],
                "akms_schema": "v2",
            },
        )
        pcd = parse_pcd(path)
        persistent = pcd.extract_persistent_zone()
        assert len(persistent["nodes_used"]) == 1
        assert len(persistent["pitfalls_discovered"]) == 1
        assert len(persistent["new_knowledge"]) == 1

    def test_pcd_empty_warnings_raises(self, tmp_path):
        path = write_node_md(
            tmp_path / "bad-pcd.md",
            {
                "phase_id": 1,
                "plan_file": "plan.md",
                "branch": "b",
                "date": "2026-03-04",
                "loadout_used": "l.md",
                "next_phase_warnings": [],  # Must have at least one
                "akms_schema": "v2",
            },
        )
        with pytest.raises(SchemaValidationError):
            parse_pcd(path)


# ══════════════════════════════════════════════════════════════════════
#  Propagation Config Tests
# ══════════════════════════════════════════════════════════════════════


class TestPropagationConfig:
    def test_default_config(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text(yaml.dump({"akms_schema": "v2"}))
        config = parse_propagation_config(path)
        assert isinstance(config, PropagationConfig)
        assert config.confidence.local_decay == 0.85
        assert config.confidence.hop_limit == 1
        assert "implementer" in config.query_roles

    def test_custom_config_overrides(self, tmp_path):
        path = tmp_path / "config.yaml"
        path.write_text(
            yaml.dump(
                {
                    "akms_schema": "v2",
                    "confidence": {"local_decay": 0.90, "hop_limit": 2},
                }
            )
        )
        config = parse_propagation_config(path)
        assert config.confidence.local_decay == 0.90
        assert config.confidence.hop_limit == 2
