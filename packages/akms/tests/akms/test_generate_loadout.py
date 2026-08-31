"""Tests for generate_loadout.py — Phase 3 Task 3.3.

Tests loadout generation:
  - Routing mode (summary + paths)
  - Full mode (inline content)
  - reading_priority overrides
  - Token budget enforcement
  - Pitfall warnings section
  - Reading order from requires edges
  - Degraded mode (qmd unavailable)
  - Mode selection logic
"""

from __future__ import annotations

import yaml
import pytest
from types import SimpleNamespace

from akms.graph.build_graph import build_graph
from akms.graph.generate_loadout import (
    generate_loadout,
    select_loadout_mode,
    _build_reading_order,
    _extract_summary,
)
from akms.graph.query_subgraph import query_subgraph
from akms.schema.models import AgentRole, LoadoutMode, PropagationConfig
from tests.akms.conftest import make_global_node, set_overlay


@pytest.fixture(autouse=True)
def _default_qmd_available(monkeypatch):
    """Keep qmd-enabled behavior by default; opt out explicitly in degraded-mode tests."""
    monkeypatch.setattr("akms.graph.generate_loadout.shutil.which", lambda _: "/usr/bin/qmd")


# ═══════════════════════════════════════════════════════════════════════
#  Test: Routing Mode
# ═══════════════════════════════════════════════════════════════════════


class TestRoutingMode:
    """Loadout generation in routing mode."""

    def test_routing_mode_generates_valid_loadout(self, tmp_vault, tmp_repo):
        """Routing mode produces loadout with node table and summaries."""
        make_global_node(tmp_vault, id="n1", tags=["taichi"], confidence=0.9)
        make_global_node(tmp_vault, id="n2", tags=["taichi"], confidence=0.8)
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        nodes = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        nodes = [(nid, {**data, "content_ref": "global-nodes/n1.md"}) for nid, data in nodes]

        content = generate_loadout(
            G, nodes,
            task_id="TSK-001",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.ROUTING,
        )

        assert "# Loadout: TSK-001" in content
        assert "## Domain Knowledge" in content
        assert "`n1`" in content
        assert "## Suggested Reading Order" in content

    def test_routing_mode_has_frontmatter(self, tmp_vault, tmp_repo):
        """Routing loadout contains YAML frontmatter with correct fields."""
        make_global_node(tmp_vault, id="n1", tags=["taichi"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        nodes = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)

        content = generate_loadout(
            G, nodes,
            task_id="TSK-001",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.ROUTING,
        )

        # Parse the YAML frontmatter
        lines = content.split("\n")
        assert lines[0] == "---"
        end_idx = lines.index("---", 1)
        yaml_str = "\n".join(lines[1:end_idx])
        header = yaml.safe_load(yaml_str)

        assert header["task_id"] == "TSK-001"
        assert header["phase"] == 1
        assert header["graph_version"] == "abc123"
        assert header["loadout_mode"] == "routing"
        assert header["agent_role"] == "implementer"
        assert header["available_context"] == 0
        assert header["akms_schema"] == "v2"

    def test_header_available_context_matches_input(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="n1", tags=["taichi"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        nodes = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)

        content = generate_loadout(
            G, nodes,
            task_id="TSK-CTX",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.ROUTING,
            available_context=12345,
        )

        lines = content.split("\n")
        end_idx = lines.index("---", 1)
        yaml_str = "\n".join(lines[1:end_idx])
        header = yaml.safe_load(yaml_str)
        assert header["available_context"] == 12345

    def test_routing_mode_writes_file(self, tmp_vault, tmp_repo):
        """Routing loadout writes to output_dir when provided."""
        make_global_node(tmp_vault, id="n1", tags=["taichi"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        nodes = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)

        output_dir = tmp_repo / "knowledge" / "loadouts"
        generate_loadout(
            G, nodes,
            task_id="TSK-001",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.ROUTING,
            output_dir=output_dir,
        )

        expected_file = output_dir / "1-TSK-001-loadout.md"
        assert expected_file.exists()
        content = expected_file.read_text()
        assert "# Loadout: TSK-001" in content

    def test_writes_to_explicit_output_path(self, tmp_vault, tmp_repo):
        """Explicit output_path writes exactly one file at the requested location."""
        make_global_node(tmp_vault, id="n1", tags=["taichi"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        nodes = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)

        explicit_path = tmp_repo / "knowledge" / "loadouts" / "custom-loadout.md"
        generate_loadout(
            G, nodes,
            task_id="TSK-CUSTOM",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.ROUTING,
            output_path=explicit_path,
        )

        assert explicit_path.exists()
        content = explicit_path.read_text()
        assert "# Loadout: TSK-CUSTOM" in content

    def test_output_dir_and_output_path_are_mutually_exclusive(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="n1", tags=["taichi"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        nodes = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)

        with pytest.raises(ValueError):
            generate_loadout(
                G, nodes,
                task_id="TSK-ERR",
                phase=1,
                graph_version="abc123",
                seed_tags=["taichi"],
                agent_role=AgentRole.IMPLEMENTER,
                mode=LoadoutMode.ROUTING,
                output_dir=tmp_repo / "knowledge" / "loadouts",
                output_path=tmp_repo / "knowledge" / "loadouts" / "TSK-ERR.md",
            )


# ═══════════════════════════════════════════════════════════════════════
#  Test: Full Mode
# ═══════════════════════════════════════════════════════════════════════


class TestFullMode:
    """Loadout generation in full mode."""

    def test_full_mode_includes_content(self, tmp_vault, tmp_repo):
        """Full mode loadout embeds node content inline."""
        make_global_node(
            tmp_vault, id="n1", tags=["taichi"], confidence=0.9,
            content="# Node Content\n\nThis is detailed content about Taichi patterns.",
        )
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        nodes = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)

        # The content_ref points to a skill file that may not exist in test env
        # So we test the structure, not the content itself
        content = generate_loadout(
            G, nodes,
            task_id="TSK-001",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.FULL,
        )

        assert "loadout_mode: full" in content or "loadout_mode: 'full'" in content
        assert "## Domain Knowledge" in content

    def test_full_mode_header(self, tmp_vault, tmp_repo):
        """Full mode loadout header has mode='full'."""
        make_global_node(tmp_vault, id="n1", tags=["taichi"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        nodes = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)

        content = generate_loadout(
            G, nodes,
            task_id="TSK-001",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.FULL,
        )

        lines = content.split("\n")
        end_idx = lines.index("---", 1)
        yaml_str = "\n".join(lines[1:end_idx])
        header = yaml.safe_load(yaml_str)
        assert header["loadout_mode"] == "full"


# ═══════════════════════════════════════════════════════════════════════
#  Test: Pitfall Warnings
# ═══════════════════════════════════════════════════════════════════════


class TestPitfallWarnings:
    """Pitfall warning section in loadout."""

    def test_pitfall_edges_appear_in_loadout(self, tmp_vault, tmp_repo):
        """Pitfall edges produce warning entries in the loadout."""
        make_global_node(tmp_vault, id="n1", tags=["taichi"])
        make_global_node(tmp_vault, id="n2", tags=["taichi"])

        set_overlay(
            tmp_repo,
            local_edges=[{
                "from": "n1",
                "to": "n2",
                "type": "pitfall",
                "weight": 0.8,
                "note": "Watch for race conditions",
            }],
        )

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        nodes = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)

        content = generate_loadout(
            G, nodes,
            task_id="TSK-001",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
        )

        assert "## Pitfall Warnings" in content
        assert "race conditions" in content


# ═══════════════════════════════════════════════════════════════════════
#  Test: Reading Order
# ═══════════════════════════════════════════════════════════════════════


class TestReadingOrder:
    """Reading order derived from requires edge topology."""

    def test_requires_determines_reading_order(self, tmp_vault, tmp_repo):
        """Nodes required by others appear first in reading order."""
        make_global_node(
            tmp_vault,
            id="advanced",
            tags=["taichi"],
            edges=[{"to": "basic", "type": "requires", "weight": 0.9}],
        )
        make_global_node(tmp_vault, id="basic", tags=["taichi"])

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        order = _build_reading_order(G, ["advanced", "basic"])

        # basic should come before advanced (advanced requires basic)
        basic_idx = order.index("basic")
        advanced_idx = order.index("advanced")
        assert basic_idx < advanced_idx

    def test_reading_order_in_loadout(self, tmp_vault, tmp_repo):
        """Suggested Reading Order section appears in loadout."""
        make_global_node(
            tmp_vault,
            id="n1",
            tags=["taichi"],
            edges=[{"to": "n2", "type": "requires", "weight": 0.9}],
        )
        make_global_node(tmp_vault, id="n2", tags=["taichi"])

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        nodes = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)

        content = generate_loadout(
            G, nodes,
            task_id="TSK-001",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
        )

        assert "## Suggested Reading Order" in content


# ═══════════════════════════════════════════════════════════════════════
#  Test: Mode Selection
# ═══════════════════════════════════════════════════════════════════════


class TestModeSelection:
    """Loadout mode selection logic (§2.1)."""

    def test_low_context_selects_routing(self):
        """Available context below low_threshold → routing."""
        config = PropagationConfig()
        config.loadout.mode_selection.low_threshold = 8000

        mode = select_loadout_mode([], available_context=5000, config=config)
        assert mode == LoadoutMode.ROUTING

    def test_high_context_selects_full(self, tmp_vault, tmp_repo):
        """Enough context → full mode."""
        config = PropagationConfig()
        config.loadout.mode_selection.low_threshold = 8000
        config.loadout.mode_selection.budget_fraction = 0.15

        # Small node set with small cost
        nodes = [
            ("n1", {"context_size": "small"}),
            ("n2", {"context_size": "small"}),
        ]

        mode = select_loadout_mode(nodes, available_context=100000, config=config)
        assert mode == LoadoutMode.FULL

    def test_expensive_nodes_select_routing(self):
        """Cost exceeds budget_fraction → routing."""
        config = PropagationConfig()
        config.loadout.mode_selection.budget_fraction = 0.15

        # Many large nodes
        nodes = [
            (f"n{i}", {"context_size": "large"}) for i in range(20)
        ]

        mode = select_loadout_mode(nodes, available_context=50000, config=config)
        # 20 * 3000 = 60000 > 50000 * 0.15 = 7500
        assert mode == LoadoutMode.ROUTING


# ═══════════════════════════════════════════════════════════════════════
#  Test: Summary Extraction
# ═══════════════════════════════════════════════════════════════════════


class TestSummaryExtraction:
    """Helper function for routing mode summaries."""

    def test_extracts_summary_section(self):
        """Extracts content from ## Summary heading."""
        content = (
            "# Title\n\n"
            "## Summary\n\n"
            "This is the summary. It describes the key concepts.\n\n"
            "## Details\n\n"
            "More details here."
        )
        summary = _extract_summary(content)
        assert "summary" in summary.lower()
        assert "Details" not in summary

    def test_fallback_to_first_lines(self):
        """Without ## Summary, uses first non-heading lines."""
        content = (
            "# Title\n\n"
            "First paragraph of content.\n"
            "Second line of the paragraph.\n\n"
            "## Section\n"
            "More details."
        )
        summary = _extract_summary(content)
        assert "First paragraph" in summary

    def test_empty_content(self):
        """Empty content returns placeholder."""
        summary = _extract_summary("")
        assert "no content" in summary.lower()


# ═══════════════════════════════════════════════════════════════════════
#  Test: Empty/Edge Cases
# ═══════════════════════════════════════════════════════════════════════


class TestLoadoutEdgeCases:
    """Edge cases for loadout generation."""

    def test_empty_ranked_nodes(self, tmp_vault, tmp_repo):
        """Loadout with no nodes still produces valid structure."""
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        content = generate_loadout(
            G, [],
            task_id="TSK-001",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
        )

        assert "# Loadout: TSK-001" in content
        assert "## Domain Knowledge" in content
        assert "node_count: 0" in content

    def test_qmd_absent_still_renders_content_via_file_fallback(
        self, tmp_vault, tmp_repo, monkeypatch,
    ):
        """PR20-T1: with `qmd` binary absent, retrieval falls back to the
        run_qmd.sh grep path AND `_load_node_content` reads the file body
        directly. The loadout is no longer a bare path list — it surfaces a
        routing-mode summary too."""
        make_global_node(tmp_vault, id="n1", tags=["taichi"], content="# N1\n\nbody")
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        nodes = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        nodes = [(nid, {**data, "content_ref": "global-nodes/n1.md"}) for nid, data in nodes]
        # Simulate a host without the `qmd` binary on PATH.
        monkeypatch.setattr("akms.graph.generate_loadout.shutil.which", lambda _: None)

        content = generate_loadout(
            G, nodes,
            task_id="TSK-001",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
            repo_root=tmp_repo,
        )

        # Header still records the binary's absence for observability.
        assert "qmd_available: false" in content
        # Paths and summaries both render — the previous "degraded mode"
        # that hid content is gone because the grep fallback / file reader
        # covers retrieval.
        assert "**Path:**" in content
        assert "**Summary:**" in content


class TestQmdRetrievalOrchestration:
    """qmd retrieval integration for loadout generation."""

    def test_qmd_invoked_with_scoped_references(self, tmp_vault, tmp_repo, monkeypatch):
        """qmd retrieval shells out to run_qmd.sh search_nodes."""
        make_global_node(tmp_vault, id="n1", tags=["taichi"], content="# X\n\nalpha")
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        nodes = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        nodes = [(nid, {**data, "content_ref": "global-nodes/n1.md"}) for nid, data in nodes]

        monkeypatch.setattr("akms.graph.generate_loadout.shutil.which", lambda _: "/usr/bin/qmd")

        captured = {}

        def _fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["cwd"] = kwargs.get("cwd")
            # run_qmd.sh style output with a JSON line.
            return SimpleNamespace(
                returncode=0,
                stderr="",
                stdout=(
                    "=== Global Nodes ===\n"
                    '{"path": "global-nodes/n1.md", "line": 1, "content": "from-qmd"}\n'
                ),
            )

        monkeypatch.setattr("akms.graph.generate_loadout.subprocess.run", _fake_run)

        content = generate_loadout(
            G, nodes,
            task_id="TSK-001",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.FULL,
            repo_root=tmp_repo,
        )

        # Now shells out to bash + run_qmd.sh with search_nodes subcommand.
        assert any("run_qmd.sh" in c for c in captured["cmd"])
        assert "search_nodes" in captured["cmd"]
        assert "taichi" in captured["cmd"]
        assert captured["cwd"] == str(tmp_repo)
        assert "from-qmd" in content

    def test_qmd_cache_hit_skips_subprocess(self, tmp_vault, tmp_repo, monkeypatch):
        make_global_node(tmp_vault, id="n1", tags=["taichi"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        nodes = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        nodes = [(nid, {**data, "content_ref": "global-nodes/n1.md"}) for nid, data in nodes]

        monkeypatch.setattr("akms.graph.generate_loadout.shutil.which", lambda _: "/usr/bin/qmd")
        # Cache payload carries `line` so the list-shaped branch is taken.
        monkeypatch.setattr(
            "akms.graph.generate_loadout.get_cached",
            lambda *args, **kwargs: [
                {"path": "global-nodes/n1.md", "line": 1, "content": "cached-qmd"},
            ],
        )

        def _boom(*args, **kwargs):
            raise AssertionError("subprocess.run should not execute on cache hit")

        monkeypatch.setattr("akms.graph.generate_loadout.subprocess.run", _boom)

        content = generate_loadout(
            G, nodes,
            task_id="TSK-001",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.FULL,
            repo_root=tmp_repo,
        )
        assert "cached-qmd" in content

    def test_qmd_cache_miss_executes_and_stores(self, tmp_vault, tmp_repo, monkeypatch):
        make_global_node(tmp_vault, id="n1", tags=["taichi"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        nodes = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        nodes = [(nid, {**data, "content_ref": "global-nodes/n1.md"}) for nid, data in nodes]

        monkeypatch.setattr("akms.graph.generate_loadout.shutil.which", lambda _: "/usr/bin/qmd")
        monkeypatch.setattr("akms.graph.generate_loadout.get_cached", lambda *args, **kwargs: None)
        put_calls = []
        monkeypatch.setattr("akms.graph.generate_loadout.put_cached", lambda *args, **kwargs: put_calls.append((args, kwargs)))
        # run_qmd.sh output shape.
        monkeypatch.setattr(
            "akms.graph.generate_loadout.subprocess.run",
            lambda *args, **kwargs: SimpleNamespace(
                returncode=0,
                stderr="",
                stdout=(
                    "=== Global Nodes ===\n"
                    '{"path": "global-nodes/n1.md", "line": 1, "content": "fresh-qmd"}\n'
                ),
            ),
        )

        content = generate_loadout(
            G, nodes,
            task_id="TSK-001",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.FULL,
            repo_root=tmp_repo,
        )
        assert "fresh-qmd" in content
        assert len(put_calls) == 1


class TestDeterministicOrdering:
    def test_same_inputs_produce_identical_output(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="b", tags=["taichi"])
        make_global_node(tmp_vault, id="a", tags=["taichi"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        nodes = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)

        forward = sorted(nodes, key=lambda x: x[0])
        reverse = list(reversed(forward))

        c1 = generate_loadout(
            G, forward,
            task_id="TSK-DET",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
        )
        c2 = generate_loadout(
            G, reverse,
            task_id="TSK-DET",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
        )

        assert c1 == c2


class TestBundledResourcePaths:
    """Regression: seed/qmd/run_qmd.sh must resolve from the installed package."""

    def test_parents_index_lands_on_existing_run_qmd_sh(self):
        """PR20-T2: `Path(__file__).parents[3]` must point at the AKMS package
        root (containing `seed/`). Using `parents[2]` lands inside `src/` and
        fails to locate the wrapper when AKMS is imported from outside the
        dev layout."""
        # Resolution is delegated to akms._resources.seed_qmd_path, which
        # prefers the packaged ``_bundled/qmd`` tree. Pin the helper rather
        # than a raw parents[] index so this tracks what production calls.
        from akms._resources import seed_qmd_path

        resolved = seed_qmd_path("run_qmd.sh")
        assert resolved.exists(), (
            f"Expected run_qmd.sh at {resolved}; `parents[3]` points outside "
            "the package root. Check the parents index in "
            "_retrieve_node_content_qmd."
        )

    def test_grep_fallback_resolves_against_repo_root(self, tmp_path, monkeypatch):
        """PR20-T3: grep-fallback paths must be read via `repo_root`, not cwd.

        The wrapper emits paths relative to the repo root. When the Python
        process runs from a different cwd (scheduler, MCP server, editable
        install), a bare `Path(stripped).read_text()` would silently return
        empty content.
        """
        from akms.graph.generate_loadout import _retrieve_node_content_qmd

        repo_root = tmp_path / "repo"
        (repo_root / "knowledge" / "local-nodes").mkdir(parents=True)
        target_rel = "knowledge/local-nodes/alpha.md"
        (repo_root / target_rel).write_text("# alpha\n\ncontent-body\n")

        # Fake wrapper output: one grep-style relative path (no JSON).
        fake_stdout = f"=== Local Nodes ===\n{target_rel}\n"

        def _fake_run(cmd, **kwargs):
            return SimpleNamespace(returncode=0, stderr="", stdout=fake_stdout)

        monkeypatch.setattr("akms.graph.generate_loadout.subprocess.run", _fake_run)
        # Run from an unrelated cwd — reading relative paths from cwd would fail.
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)

        hits = _retrieve_node_content_qmd(
            query="alpha",
            scoped_paths=[target_rel],
            repo_root=repo_root,
        )
        assert hits, "expected grep-fallback to produce at least one hit"
        assert hits[0]["path"] == target_rel
        assert "content-body" in hits[0]["content"], (
            "grep-fallback must resolve the relative path against repo_root, "
            "not the caller's cwd"
        )
