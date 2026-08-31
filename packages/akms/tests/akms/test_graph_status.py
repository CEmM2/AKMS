"""Tests for graph_status.py — Phase 5: Health Check & Review Report.

Coverage:
- Degraded nodes (confidence < 0.5)
- Tentative nodes awaiting promotion
- Id collisions between global and local nodes
- Orphaned nodes (no edges)
- Stale nodes (last_activated > N days)
- Orphaned overlay entries
- Report formatting
- Full pipeline: graph_status() end-to-end
"""

from __future__ import annotations

from datetime import date

import yaml

from akms.graph.build_graph import build_graph
from akms.graph.graph_status import (
    _check_blocked_tasks,
    _check_coverage_flags,
    _check_degraded_nodes,
    _check_dedup_events,
    _check_id_collisions,
    _check_orphaned_nodes,
    _check_orphaned_overlay_entries,
    _check_stale_nodes,
    _check_tentative_nodes,
    format_report,
    graph_status,
)

from .conftest import make_global_node, make_local_node


# ═══════════════════════════════════════════════════════════════════════
#  Degraded Nodes
# ═══════════════════════════════════════════════════════════════════════


class TestDegradedNodes:
    def test_finds_low_confidence_nodes(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="low-node", confidence=0.30)
        make_global_node(tmp_vault, id="high-node", confidence=0.90)
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        degraded = _check_degraded_nodes(G, {})
        ids = [d["node_id"] for d in degraded]
        assert "low-node" in ids
        assert "high-node" not in ids

    def test_overlay_confidence_overrides(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", confidence=0.90)
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        overlay = {"nodes": {"node-a": {"confidence": 0.20}}}
        degraded = _check_degraded_nodes(G, overlay)
        assert len(degraded) == 1
        assert degraded[0]["overlay_confidence"] == 0.20

    def test_custom_threshold(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", confidence=0.60)
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        degraded = _check_degraded_nodes(G, {}, threshold=0.7)
        assert len(degraded) == 1


# ═══════════════════════════════════════════════════════════════════════
#  Tentative Nodes
# ═══════════════════════════════════════════════════════════════════════


class TestTentativeNodes:
    def test_finds_tentative(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="tent-node", status="tentative", confidence=0.50)
        make_global_node(
            tmp_vault, id="est-node", status="established", confidence=0.90
        )
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        tentative = _check_tentative_nodes(G)
        ids = [t["node_id"] for t in tentative]
        assert "tent-node" in ids
        assert "est-node" not in ids

    def test_reports_origin(self, tmp_vault, tmp_repo):
        make_local_node(tmp_repo, id="local-tent", status="tentative")
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        tentative = _check_tentative_nodes(G)
        assert len(tentative) == 1
        assert tentative[0]["origin"] == "local"


# ═══════════════════════════════════════════════════════════════════════
#  Id Collisions
# ═══════════════════════════════════════════════════════════════════════


class TestIdCollisions:
    def test_detects_collision(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="shared-id", confidence=0.90)
        make_local_node(tmp_repo, id="shared-id")

        local_dir = tmp_repo / "knowledge" / "local-nodes"
        collisions = _check_id_collisions(tmp_vault, local_dir)
        assert len(collisions) == 1
        assert collisions[0]["node_id"] == "shared-id"

    def test_no_collision(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="global-only", confidence=0.90)
        make_local_node(tmp_repo, id="local-only")

        local_dir = tmp_repo / "knowledge" / "local-nodes"
        collisions = _check_id_collisions(tmp_vault, local_dir)
        assert len(collisions) == 0

    def test_detects_collision_in_nested_paths_with_reported_paths(
        self, tmp_vault, tmp_repo
    ):
        nested_global = tmp_vault / "deep" / "topic"
        nested_global.mkdir(parents=True)
        nested_local = tmp_repo / "knowledge" / "local-nodes" / "wave-1"
        nested_local.mkdir(parents=True)

        global_path = make_global_node(tmp_vault, id="nested-shared", confidence=0.90)
        local_path = make_local_node(tmp_repo, id="nested-shared")

        moved_global = nested_global / global_path.name
        moved_local = nested_local / local_path.name
        global_path.rename(moved_global)
        local_path.rename(moved_local)

        collisions = _check_id_collisions(
            tmp_vault, tmp_repo / "knowledge" / "local-nodes"
        )
        assert len(collisions) == 1
        assert collisions[0]["node_id"] == "nested-shared"
        assert collisions[0]["global_path"] == str(moved_global)
        assert collisions[0]["local_path"] == str(moved_local)


# ═══════════════════════════════════════════════════════════════════════
#  Orphaned Nodes
# ═══════════════════════════════════════════════════════════════════════


class TestOrphanedNodes:
    def test_finds_orphaned(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="lonely", confidence=0.90)
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        orphaned = _check_orphaned_nodes(G)
        ids = [o["node_id"] for o in orphaned]
        assert "lonely" in ids

    def test_connected_not_orphaned(self, tmp_vault, tmp_repo):
        make_global_node(
            tmp_vault,
            id="parent",
            confidence=0.90,
            edges=[{"to": "child", "type": "requires", "weight": 0.8}],
        )
        make_global_node(tmp_vault, id="child", confidence=0.90)
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        orphaned = _check_orphaned_nodes(G)
        ids = [o["node_id"] for o in orphaned]
        assert "parent" not in ids
        assert "child" not in ids


# ═══════════════════════════════════════════════════════════════════════
#  Stale Nodes
# ═══════════════════════════════════════════════════════════════════════


class TestStaleNodes:
    def test_finds_stale(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", confidence=0.90)
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        today = date(2026, 6, 15)
        overlay = {"nodes": {"node-a": {"last_activated": "2026-01-01"}}}
        stale = _check_stale_nodes(G, overlay, stale_days=90, today=today)

        assert len(stale) == 1
        assert stale[0]["node_id"] == "node-a"
        assert stale[0]["days_inactive"] > 90

    def test_recently_active_not_stale(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", confidence=0.90)
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        today = date(2026, 3, 7)
        overlay = {"nodes": {"node-a": {"last_activated": "2026-03-01"}}}
        stale = _check_stale_nodes(G, overlay, stale_days=90, today=today)

        assert len(stale) == 0

    def test_never_activated_not_stale(self, tmp_vault, tmp_repo):
        """Nodes without last_activated are not flagged (never used is not stale)."""
        make_global_node(tmp_vault, id="node-a", confidence=0.90)
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        stale = _check_stale_nodes(G, {}, stale_days=90, today=date(2026, 3, 7))
        assert len(stale) == 0


# ═══════════════════════════════════════════════════════════════════════
#  Orphaned Overlay Entries
# ═══════════════════════════════════════════════════════════════════════


class TestOrphanedOverlay:
    def test_finds_orphaned_overlay(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", confidence=0.90)
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        overlay = {"nodes": {"node-a": {}, "ghost-node": {"confidence": 0.5}}}
        orphaned = _check_orphaned_overlay_entries(G, overlay)

        assert len(orphaned) == 1
        assert orphaned[0]["node_id"] == "ghost-node"

    def test_no_orphaned(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", confidence=0.90)
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        overlay = {"nodes": {"node-a": {"confidence": 0.92}}}
        orphaned = _check_orphaned_overlay_entries(G, overlay)
        assert len(orphaned) == 0


# ═══════════════════════════════════════════════════════════════════════
#  Coverage Flags / Dedup / Blocked Tasks
# ═══════════════════════════════════════════════════════════════════════


class TestExtendedReportCategories:
    def test_coverage_flags_loaded_from_overlay(self):
        overlay = {
            "coverage_flags": [
                {
                    "node_id": "node-a",
                    "coverage": "missing-detail",
                    "source_id": "task-1",
                    "phase": 1,
                    "date": "2026-03-09",
                },
                {
                    "node_id": "node-b",
                    "coverage": "outdated",
                    "source_id": "task-2",
                    "phase": 2,
                    "date": "2026-03-10",
                },
            ]
        }
        flags = _check_coverage_flags(overlay)
        assert len(flags) == 2
        assert {f["coverage"] for f in flags} == {"missing-detail", "outdated"}

    def test_dedup_events_loaded_from_overlay(self):
        overlay = {
            "dedup_events": [
                {
                    "action": "dedup_append",
                    "merged_into": "node-a",
                    "node_id": "node-a",
                    "source_id": "task-1",
                    "phase": 1,
                },
            ]
        }
        dedup = _check_dedup_events(overlay)
        assert len(dedup) == 1
        assert dedup[0]["action"] == "dedup_append"
        assert dedup[0]["merged_into"] == "node-a"

    def test_blocked_tasks_loaded_from_overlay_or_explicit_arg(self):
        overlay = {
            "blocked_tasks": [{"task": "task-014", "reason": "awaiting promotion"}]
        }

        from_overlay = _check_blocked_tasks(overlay)
        assert len(from_overlay) == 1
        assert from_overlay[0]["task"] == "task-014"

        explicit = _check_blocked_tasks(
            overlay,
            blocked_tasks=[{"task": "task-099", "reason": "manual block"}],
        )
        assert len(explicit) == 1
        assert explicit[0]["task"] == "task-099"


# ═══════════════════════════════════════════════════════════════════════
#  Report Formatting
# ═══════════════════════════════════════════════════════════════════════


class TestFormatReport:
    def test_formats_complete_report(self):
        report = {
            "total_nodes": 10,
            "total_edges": 5,
            "degraded_nodes": [
                {
                    "node_id": "n1",
                    "graph_confidence": 0.3,
                    "overlay_confidence": None,
                    "effective_confidence": 0.3,
                    "origin": "global",
                },
            ],
            "tentative_nodes": [],
            "id_collisions": [],
            "orphaned_nodes": [],
            "stale_nodes": [],
            "orphaned_overlay_entries": [],
            "coverage_flags": [],
            "dedup_events": [],
            "blocked_tasks": [],
            "drift_warnings": [],
        }
        text = format_report(report)
        assert "AKMS Graph Health Report" in text
        assert "n1" in text
        assert "10" in text

    def test_drift_warnings_in_report(self):
        report = {
            "total_nodes": 5,
            "total_edges": 2,
            "degraded_nodes": [],
            "tentative_nodes": [],
            "id_collisions": [],
            "orphaned_nodes": [],
            "stale_nodes": [],
            "orphaned_overlay_entries": [],
            "coverage_flags": [],
            "dedup_events": [],
            "blocked_tasks": [],
            "drift_warnings": [
                {
                    "function": "compute",
                    "file": "src/mod.py",
                    "type": "missing_param",
                    "detail": "Param X missing",
                },
            ],
        }
        text = format_report(report)
        assert "Docstring Drift" in text
        assert "compute" in text


# ═══════════════════════════════════════════════════════════════════════
#  Full Pipeline
# ═══════════════════════════════════════════════════════════════════════


class TestGraphStatusIntegration:
    def test_full_report(self, tmp_vault, tmp_repo):
        make_global_node(
            tmp_vault,
            id="healthy",
            confidence=0.90,
            edges=[{"to": "degraded", "type": "requires", "weight": 0.8}],
        )
        make_global_node(tmp_vault, id="degraded", confidence=0.30)
        make_global_node(tmp_vault, id="tent", status="tentative", confidence=0.50)
        make_global_node(tmp_vault, id="orphan", confidence=0.90)

        report = graph_status(tmp_repo, global_vault=tmp_vault)

        assert report["total_nodes"] >= 4
        assert len(report["degraded_nodes"]) >= 1
        assert len(report["tentative_nodes"]) >= 1
        # orphan has no edges
        orphan_ids = [o["node_id"] for o in report["orphaned_nodes"]]
        assert "orphan" in orphan_ids

    def test_drift_warnings_passed_through(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", confidence=0.90)

        drift = [{"function": "fn", "type": "drift", "detail": "mismatch"}]
        report = graph_status(tmp_repo, global_vault=tmp_vault, drift_warnings=drift)

        assert len(report["drift_warnings"]) == 1

    def test_extended_categories_included(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", confidence=0.90)

        overlay_path = tmp_repo / "knowledge" / "graph" / "local_state.yaml"
        overlay = yaml.safe_load(overlay_path.read_text())
        overlay["coverage_flags"] = [
            {
                "node_id": "node-a",
                "coverage": "missing-detail",
                "source_id": "task-1",
                "phase": 1,
                "date": "2026-03-09",
            }
        ]
        overlay["dedup_events"] = [
            {
                "action": "dedup_append",
                "merged_into": "node-a",
                "node_id": "node-a",
                "source_id": "task-1",
                "phase": 1,
            }
        ]
        overlay["blocked_tasks"] = [
            {"task": "task-014", "reason": "awaiting tentative promotion"}
        ]
        overlay_path.write_text(yaml.dump(overlay))

        report = graph_status(tmp_repo, global_vault=tmp_vault)
        assert len(report["coverage_flags"]) == 1
        assert len(report["dedup_events"]) == 1
        assert len(report["blocked_tasks"]) == 1


# ═══════════════════════════════════════════════════════════════════════
#  content_draft Inline in Review (FR-R05)
# ═══════════════════════════════════════════════════════════════════════


class TestContentDraftInReview:
    """FR-R05: the review report shows the agent-written content_draft inline."""

    def test_tentative_entry_includes_content_draft(self, tmp_vault, tmp_repo):
        make_local_node(
            tmp_repo,
            id="local-tent",
            status="tentative",
            content="DRAFT BODY HERE",
        )
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        local_nodes_dir = tmp_repo / "knowledge" / "local-nodes"

        tentative = _check_tentative_nodes(G, tmp_repo, local_nodes_dir)
        entry = next(t for t in tentative if t["node_id"] == "local-tent")
        assert "DRAFT BODY HERE" in entry["content_draft"]

    def test_draft_rendered_in_formatted_report(self, tmp_vault, tmp_repo):
        make_local_node(
            tmp_repo,
            id="local-tent",
            status="tentative",
            content="UNIQUE DRAFT MARKER",
        )
        report = graph_status(tmp_repo, global_vault=tmp_vault)
        text = format_report(report)
        assert "content_draft" in text
        assert "UNIQUE DRAFT MARKER" in text

    def test_no_draft_without_dirs(self, tmp_vault, tmp_repo):
        """Backward-compatible: called without repo paths, draft is empty."""
        make_global_node(tmp_vault, id="g-tent", status="tentative")
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        tentative = _check_tentative_nodes(G)
        entry = next(t for t in tentative if t["node_id"] == "g-tent")
        assert entry["content_draft"] == ""
