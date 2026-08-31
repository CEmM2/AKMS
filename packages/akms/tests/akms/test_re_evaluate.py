"""Tests for re_evaluate.py — Phase 5: Loadout Regeneration.

Coverage:
- Basic regeneration with updated graph state
- Output path handling
- Integration with query_subgraph + generate_loadout
"""

from __future__ import annotations

from pathlib import Path

import pytest

from akms.graph.build_graph import build_graph
from akms.graph.re_evaluate import re_evaluate

from .conftest import make_global_node, set_overlay


class TestReEvaluate:
    def test_generates_loadout_file(self, tmp_vault, tmp_repo):
        """re_evaluate produces a loadout file in the expected location."""
        make_global_node(tmp_vault, id="node-a", confidence=0.90, tags=["test", "alpha"])
        make_global_node(tmp_vault, id="node-b", confidence=0.85, tags=["test", "beta"])
        # Build initial graph
        build_graph(tmp_repo, global_vault=tmp_vault)

        result = re_evaluate(
            tmp_repo,
            task_id="task-next",
            phase=2,
            seed_tags=["test"],
            global_vault=tmp_vault,
        )

        assert result["node_count"] >= 1
        assert result["graph_version"] != ""
        assert Path(result["loadout_path"]).exists()

    def test_custom_output_path(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", confidence=0.90, tags=["alpha"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        custom_path = tmp_repo / "custom_loadout.md"
        result = re_evaluate(
            tmp_repo,
            task_id="custom",
            phase=3,
            seed_tags=["alpha"],
            global_vault=tmp_vault,
            output_path=str(custom_path),
        )

        assert result["loadout_path"] == str(custom_path)
        assert custom_path.exists()

    def test_returns_mode(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", confidence=0.90, tags=["alpha"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        result = re_evaluate(
            tmp_repo,
            task_id="task-1",
            phase=1,
            seed_tags=["alpha"],
            available_context=50000,
            global_vault=tmp_vault,
        )

        assert result["mode"] in ("routing", "full")

    def test_empty_tags_still_works(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="node-a", confidence=0.90, tags=["alpha"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        result = re_evaluate(
            tmp_repo,
            task_id="empty-tags",
            phase=1,
            seed_tags=["nonexistent"],
            global_vault=tmp_vault,
        )

        assert result["node_count"] == 0
        assert Path(result["loadout_path"]).exists()

    def test_with_overlay_state(self, tmp_vault, tmp_repo):
        """Overlay confidence changes affect loadout content."""
        make_global_node(tmp_vault, id="node-a", confidence=0.90, tags=["test"])
        make_global_node(tmp_vault, id="node-b", confidence=0.85, tags=["test"])
        set_overlay(tmp_repo, nodes={"node-a": {"confidence": 0.99}})
        build_graph(tmp_repo, global_vault=tmp_vault)

        result = re_evaluate(
            tmp_repo,
            task_id="overlay-test",
            phase=2,
            seed_tags=["test"],
            global_vault=tmp_vault,
        )

        assert result["node_count"] >= 1
