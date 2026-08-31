"""Tests for query_subgraph.py — Phase 3 Task 3.1.

Tests the 12-step subgraph extraction algorithm:
  - Seed matching via tag intersection
  - Ego graph expansion + union
  - Status filtering (LOADABLE_STATUSES only)
  - Edge type filtering per role profile
  - Domain preference boost (×1.5)
  - Domain exclusion
  - Confidence threshold
  - Ranking by formula
  - Max node cap
  - Pitfall injection override
  - Query hash determinism
"""

from __future__ import annotations

import pytest

from akms.graph.build_graph import build_graph
from akms.graph.query_subgraph import (
    _compute_rank,
    _find_pitfall_nodes,
    _find_seed_nodes,
    compute_query_hash,
    query_subgraph,
)
from akms.schema.models import AgentRole, PropagationConfig, QueryRoleProfile
from tests.akms.conftest import (
    make_global_node,
    make_local_node,
    set_overlay,
)


# ═══════════════════════════════════════════════════════════════════════
#  Test: Seed Node Matching
# ═══════════════════════════════════════════════════════════════════════


class TestSeedMatching:
    """Step 2: Find seed nodes matching any tag in domain_tags."""

    def test_finds_nodes_by_tag(self, tmp_vault, tmp_repo):
        """Nodes whose tags intersect domain_tags are found as seeds."""
        make_global_node(tmp_vault, id="n1", tags=["taichi", "gpu"])
        make_global_node(tmp_vault, id="n2", tags=["fem", "mechanics"])
        make_global_node(tmp_vault, id="n3", tags=["taichi", "kernels"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        seeds = _find_seed_nodes(G, ["taichi"])
        assert seeds == {"n1", "n3"}

    def test_no_match_returns_empty(self, tmp_vault, tmp_repo):
        """No matching tags → empty seed set."""
        make_global_node(tmp_vault, id="n1", tags=["fem"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        seeds = _find_seed_nodes(G, ["nonexistent"])
        assert seeds == set()

    def test_multiple_tags_union(self, tmp_vault, tmp_repo):
        """Multiple domain_tags seed via union."""
        make_global_node(tmp_vault, id="n1", tags=["taichi"])
        make_global_node(tmp_vault, id="n2", tags=["fem"])
        make_global_node(tmp_vault, id="n3", tags=["other"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        seeds = _find_seed_nodes(G, ["taichi", "fem"])
        assert seeds == {"n1", "n2"}


# ═══════════════════════════════════════════════════════════════════════
#  Test: Full Query Pipeline
# ═══════════════════════════════════════════════════════════════════════


class TestQuerySubgraph:
    """Full 12-step algorithm tests."""

    def test_basic_query_returns_matching_nodes(self, tmp_vault, tmp_repo):
        """Basic query with seed tags returns ranked nodes."""
        make_global_node(tmp_vault, id="n1", tags=["taichi", "gpu"], confidence=0.9)
        make_global_node(
            tmp_vault,
            id="n2",
            tags=["mechanics"],
            confidence=0.8,
            edges=[{"to": "n1", "type": "feeds-into", "weight": 0.7}],
        )
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        assert len(result) > 0
        node_ids = [nid for nid, _ in result]
        assert "n1" in node_ids

    def test_ego_graph_expansion(self, tmp_vault, tmp_repo):
        """Nodes connected to seeds via edges are included."""
        make_global_node(
            tmp_vault,
            id="seed",
            tags=["taichi"],
            confidence=0.9,
            edges=[{"to": "neighbor", "type": "requires", "weight": 0.8}],
        )
        make_global_node(tmp_vault, id="neighbor", tags=["gpu"], confidence=0.85)
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER, max_depth=2)
        node_ids = [nid for nid, _ in result]
        assert "seed" in node_ids
        assert "neighbor" in node_ids

    def test_status_filter_excludes_draft(self, tmp_vault, tmp_repo):
        """Draft nodes are excluded (only tentative + established pass)."""
        make_global_node(tmp_vault, id="good", tags=["taichi"], status="established")
        make_global_node(tmp_vault, id="draft", tags=["taichi"], status="draft")
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        node_ids = [nid for nid, _ in result]
        assert "good" in node_ids
        assert "draft" not in node_ids

    def test_status_filter_includes_tentative(self, tmp_vault, tmp_repo):
        """Tentative nodes pass the status filter."""
        make_global_node(tmp_vault, id="tent", tags=["taichi"], status="tentative")
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        node_ids = [nid for nid, _ in result]
        assert "tent" in node_ids

    def test_deprecated_excluded(self, tmp_vault, tmp_repo):
        """Deprecated nodes are excluded."""
        make_global_node(tmp_vault, id="old", tags=["taichi"], status="deprecated")
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        assert len(result) == 0

    def test_confidence_threshold(self, tmp_vault, tmp_repo):
        """Nodes below min_confidence_threshold are excluded."""
        make_global_node(tmp_vault, id="high", tags=["taichi"], confidence=0.9)
        make_global_node(tmp_vault, id="low", tags=["taichi"], confidence=0.1)

        config = PropagationConfig()
        config.loadout.min_confidence_threshold = 0.3

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER, config=config)
        node_ids = [nid for nid, _ in result]
        assert "high" in node_ids
        assert "low" not in node_ids

    def test_max_nodes_cap(self, tmp_vault, tmp_repo):
        """Result is capped at max_nodes_per_loadout."""
        for i in range(15):
            make_global_node(
                tmp_vault, id=f"n{i:02d}", tags=["taichi"], confidence=0.9 - i * 0.01
            )

        config = PropagationConfig()
        config.loadout.max_nodes_per_loadout = 5

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER, config=config)
        assert len(result) <= 5

    def test_ranking_by_confidence_times_activations(self, tmp_vault, tmp_repo):
        """Implementer rank formula: confidence * (activations + 1)."""
        make_global_node(tmp_vault, id="high", tags=["taichi"], confidence=0.9)
        make_global_node(tmp_vault, id="low", tags=["taichi"], confidence=0.5)

        # Give "low" more activations via overlay
        set_overlay(
            tmp_repo,
            nodes={"low": {"confidence": 0.5, "activations": 10}},
        )

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        node_ids = [nid for nid, _ in result]
        # "low" has 0.5 * 11 = 5.5, "high" has 0.9 * 1 = 0.9
        assert node_ids[0] == "low"

    def test_ranking_physics_reviewer_by_confidence_only(self, tmp_vault, tmp_repo):
        """Physics reviewer rank formula: confidence only."""
        make_global_node(
            tmp_vault,
            id="high",
            tags=["mechanics"],
            confidence=0.95,
            domain="computational-mechanics",
        )
        make_global_node(
            tmp_vault,
            id="activated",
            tags=["mechanics"],
            confidence=0.5,
            domain="computational-mechanics",
        )

        set_overlay(
            tmp_repo,
            nodes={"activated": {"confidence": 0.5, "activations": 100}},
        )

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        result = query_subgraph(G, ["mechanics"], AgentRole.PHYSICS_REVIEWER)
        node_ids = [nid for nid, _ in result]
        # Physics reviewer uses confidence only, so "high" should be first
        # Both get ×1.5 prefer_domains boost for computational-mechanics
        assert node_ids[0] == "high"


# ═══════════════════════════════════════════════════════════════════════
#  Test: Domain Filters
# ═══════════════════════════════════════════════════════════════════════


class TestDomainFilters:
    """Steps 7-8: prefer_domains boost and exclude_domains filter."""

    def test_prefer_domains_boost(self, tmp_vault, tmp_repo):
        """Nodes in preferred domains get rank × 1.5."""
        make_global_node(
            tmp_vault,
            id="preferred",
            tags=["topic"],
            confidence=0.6,
            domain="computational-mechanics",
        )
        make_global_node(
            tmp_vault,
            id="normal",
            tags=["topic"],
            confidence=0.8,
            domain="other",
        )

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        result = query_subgraph(G, ["topic"], AgentRole.PHYSICS_REVIEWER)
        node_ids = [nid for nid, _ in result]
        # preferred: 0.6 * 1.5 = 0.9, normal: 0.8 * 1.0 = 0.8
        assert node_ids[0] == "preferred"

    def test_exclude_domains(self, tmp_vault, tmp_repo):
        """Nodes in excluded domains are removed."""
        make_global_node(
            tmp_vault,
            id="keep",
            tags=["topic"],
            domain="computational-mechanics",
        )
        make_global_node(
            tmp_vault,
            id="exclude",
            tags=["topic"],
            domain="code-mirror",
        )

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        result = query_subgraph(G, ["topic"], AgentRole.PHYSICS_REVIEWER)
        node_ids = [nid for nid, _ in result]
        assert "keep" in node_ids
        assert "exclude" not in node_ids


# ═══════════════════════════════════════════════════════════════════════
#  Test: Pitfall Injection
# ═══════════════════════════════════════════════════════════════════════


class TestPitfallInjection:
    """Step 12: Pitfall nodes always included regardless of rank."""

    def test_pitfall_nodes_always_included(self, tmp_vault, tmp_repo):
        """Nodes connected by pitfall edges are always in the result."""
        make_global_node(tmp_vault, id="n1", tags=["taichi"], confidence=0.9)
        make_global_node(
            tmp_vault, id="pitfall-target", tags=["taichi"], confidence=0.3
        )

        set_overlay(
            tmp_repo,
            local_edges=[
                {"from": "n1", "to": "pitfall-target", "type": "pitfall", "weight": 0.8}
            ],
        )

        config = PropagationConfig()
        config.loadout.min_confidence_threshold = 0.5  # below pitfall-target's conf

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER, config=config)
        node_ids = [nid for nid, _ in result]
        # pitfall-target should be included even though confidence < threshold
        assert "pitfall-target" in node_ids

    def test_pitfall_nodes_capped(self, tmp_vault, tmp_repo):
        """Pitfall nodes are capped at max_pitfall_nodes."""
        make_global_node(tmp_vault, id="n1", tags=["taichi"])

        # Create many pitfall targets
        edges = []
        for i in range(10):
            make_global_node(tmp_vault, id=f"pit-{i}", tags=["taichi"], confidence=0.9)
            edges.append(
                {
                    "from": "n1",
                    "to": f"pit-{i}",
                    "type": "pitfall",
                    "weight": 0.5,
                }
            )

        set_overlay(tmp_repo, local_edges=edges)

        config = PropagationConfig()
        config.loadout.max_pitfall_nodes = 3
        config.loadout.max_nodes_per_loadout = 15

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        pitfall_set = _find_pitfall_nodes(G, set(G.nodes))
        assert len(pitfall_set) > 3  # more pitfall nodes than cap

    def test_session_nodes_excluded_from_result_but_pitfall_edges_keep_working(
        self, tmp_vault, tmp_repo
    ):
        make_global_node(tmp_vault, id="n1", tags=["taichi"], confidence=0.9)
        set_overlay(
            tmp_repo,
            local_edges=[
                {"from": "n1", "to": "session-task-1", "type": "pitfall", "weight": 0.8}
            ],
            session_nodes={
                "session-task-1": {
                    "title": "Session",
                    "tags": ["phase1"],
                    "outcome": "success",
                    "content_ref": "sessions/task-1.md",
                    "phase": 1,
                }
            },
        )

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        node_ids = [nid for nid, _ in result]

        assert "n1" in node_ids
        assert "session-task-1" not in node_ids
        assert G.has_edge("n1", "session-task-1")


# ═══════════════════════════════════════════════════════════════════════
#  Test: Edge Type Filtering
# ═══════════════════════════════════════════════════════════════════════


class TestEdgeTypeFiltering:
    """Step 6: Filter edges to profile's edge_types."""

    def test_implementer_includes_requires_feeds_into(self, tmp_vault, tmp_repo):
        """Implementer profile includes requires+feeds-into edges."""
        make_global_node(
            tmp_vault,
            id="n1",
            tags=["taichi"],
            edges=[
                {"to": "n2", "type": "requires", "weight": 0.8},
                {"to": "n3", "type": "contradicts", "weight": 0.5},
            ],
        )
        make_global_node(tmp_vault, id="n2", tags=["mechanics"])
        make_global_node(tmp_vault, id="n3", tags=["alt"])

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER, max_depth=2)
        node_ids = [nid for nid, _ in result]
        # n2 connected via requires (allowed), n3 via contradicts (not in implementer profile)
        assert "n1" in node_ids
        assert "n2" in node_ids

    def test_physics_reviewer_includes_contradicts(self, tmp_vault, tmp_repo):
        """Physics reviewer profile includes contradicts edges."""
        make_global_node(
            tmp_vault,
            id="n1",
            tags=["mechanics"],
            domain="computational-mechanics",
            edges=[{"to": "n2", "type": "contradicts", "weight": 0.5}],
        )
        make_global_node(
            tmp_vault, id="n2", tags=["alt"], domain="computational-mechanics"
        )

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        result = query_subgraph(
            G, ["mechanics"], AgentRole.PHYSICS_REVIEWER, max_depth=2
        )
        node_ids = [nid for nid, _ in result]
        assert "n1" in node_ids
        assert "n2" in node_ids

    def test_seed_anchored_strict_filter_drops_disallowed_bridge(
        self, tmp_vault, tmp_repo
    ):
        """Nodes reached via disallowed bridge edges are excluded."""
        make_global_node(
            tmp_vault,
            id="seed",
            tags=["topic"],
            edges=[{"to": "bridge", "type": "contradicts", "weight": 1.0}],
        )
        make_global_node(
            tmp_vault,
            id="bridge",
            tags=["bridge-tag"],
            edges=[{"to": "allowed-target", "type": "requires", "weight": 1.0}],
        )
        make_global_node(tmp_vault, id="allowed-target", tags=["target-tag"])

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        result = query_subgraph(G, ["topic"], AgentRole.IMPLEMENTER, max_depth=2)
        node_ids = [nid for nid, _ in result]

        assert "seed" in node_ids
        assert "bridge" not in node_ids
        assert "allowed-target" not in node_ids

    def test_seed_without_allowed_edges_is_retained(self, tmp_vault, tmp_repo):
        """Seed nodes remain in result even if they have no allowed edges."""
        make_global_node(
            tmp_vault,
            id="seed-only",
            tags=["solo"],
            edges=[{"to": "other", "type": "contradicts", "weight": 1.0}],
        )
        make_global_node(tmp_vault, id="other", tags=["other-tag"])

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        result = query_subgraph(G, ["solo"], AgentRole.IMPLEMENTER, max_depth=1)
        node_ids = [nid for nid, _ in result]

        assert "seed-only" in node_ids
        assert "other" not in node_ids


# ═══════════════════════════════════════════════════════════════════════
#  Test: Determinism (NFR-D01)
# ═══════════════════════════════════════════════════════════════════════


class TestDeterminism:
    """NFR-D01: Same input → same output."""

    def test_query_deterministic(self, tmp_vault, tmp_repo):
        """Running the same query twice produces identical results."""
        for i in range(5):
            make_global_node(
                tmp_vault,
                id=f"n{i}",
                tags=["taichi"],
                confidence=0.9 - i * 0.05,
            )
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        r1 = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        r2 = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)

        ids1 = [nid for nid, _ in r1]
        ids2 = [nid for nid, _ in r2]
        assert ids1 == ids2

    def test_query_hash_deterministic(self):
        """Same query parameters → same hash."""
        h1 = compute_query_hash(["taichi", "gpu"], "implementer", 2)
        h2 = compute_query_hash(["gpu", "taichi"], "implementer", 2)  # different order
        assert h1 == h2

    def test_query_hash_different_for_different_inputs(self):
        """Different parameters → different hash."""
        h1 = compute_query_hash(["taichi"], "implementer", 2)
        h2 = compute_query_hash(["taichi"], "physics_reviewer", 2)
        assert h1 != h2


# ═══════════════════════════════════════════════════════════════════════
#  Test: Empty/Edge Cases
# ═══════════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge cases and empty inputs."""

    def test_empty_graph(self, tmp_vault, tmp_repo):
        """Query on empty graph returns empty."""
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        assert result == []

    def test_no_matching_tags(self, tmp_vault, tmp_repo):
        """No matching tags → empty result."""
        make_global_node(tmp_vault, id="n1", tags=["fem"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        result = query_subgraph(G, ["nonexistent"], AgentRole.IMPLEMENTER)
        assert result == []

    def test_unknown_role_falls_back(self, tmp_vault, tmp_repo):
        """Unknown role falls back to implementer profile."""
        make_global_node(tmp_vault, id="n1", tags=["taichi"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        result = query_subgraph(G, ["taichi"], "unknown_role")
        assert len(result) > 0

    def test_local_nodes_included(self, tmp_vault, tmp_repo):
        """Local nodes participate in queries alongside global nodes."""
        make_global_node(tmp_vault, id="g1", tags=["taichi"])
        make_local_node(tmp_repo, id="l1", tags=["taichi"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        node_ids = [nid for nid, _ in result]
        assert "g1" in node_ids
        assert "l1" in node_ids


# ═══════════════════════════════════════════════════════════════════════
#  Test: load_with Co-activation (FR-G10)
# ═══════════════════════════════════════════════════════════════════════


class TestLoadWithCoactivation:
    """FR-G10: load_with hints promote co-activated nodes, bypassing the
    semantic-edge traversal they are explicitly distinct from."""

    def test_coactivates_unconnected_node(self, tmp_vault, tmp_repo):
        """A loadable node referenced via load_with is pulled in even with no
        edge path to the seed, and is tagged ``_coactivated``."""
        make_global_node(
            tmp_vault,
            id="seed",
            tags=["taichi"],
            confidence=0.9,
            load_with=["companion"],
        )
        make_global_node(
            tmp_vault,
            id="companion",
            tags=["unrelated"],
            confidence=0.9,
        )
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        data_by_id = dict(result)
        assert "seed" in data_by_id
        assert "companion" in data_by_id
        assert data_by_id["companion"].get("_coactivated") is True
        # The seed itself is not flagged co-activated.
        assert not data_by_id["seed"].get("_coactivated")

    def test_non_loadable_companion_not_coactivated(self, tmp_vault, tmp_repo):
        """A non-loadable (draft) load_with target is not promoted."""
        make_global_node(
            tmp_vault,
            id="seed",
            tags=["taichi"],
            confidence=0.9,
            load_with=["draft-comp"],
        )
        make_global_node(
            tmp_vault,
            id="draft-comp",
            tags=["unrelated"],
            status="draft",
            confidence=0.9,
        )
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        assert "draft-comp" not in [nid for nid, _ in result]

    def test_no_load_with_leaves_result_unchanged(self, tmp_vault, tmp_repo):
        """Without load_with, no node is flagged and nothing extra is added."""
        make_global_node(tmp_vault, id="seed", tags=["taichi"], confidence=0.9)
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        result = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        assert [nid for nid, _ in result] == ["seed"]
        assert all(not data.get("_coactivated") for _, data in result)
