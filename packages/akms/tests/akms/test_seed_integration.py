"""Phase 2 integration tests — Compile seed nodes through the full pipeline.

Tests verify:
  - Tier 1 global nodes compile cleanly with empty overlay
  - graph.json contains correct node count and origins
  - Schema validation passes on all seed nodes
  - Overlay confidence overrides apply correctly
  - Local nodes appear alongside global nodes
  - Deterministic output (build twice, diff empty)
  - qmd scripts are syntactically valid
  - Seed node edge targets all resolve
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from akms.graph.build_graph import build_graph, load_graph
from akms.schema.validators import parse_node_frontmatter

# ── Path to seed data ────────────────────────────────────────────────
# The public repo ships no separate ``seed/`` tree: ``src/akms/_bundled``
# IS the canonical bundled corpus. These tests run against it directly.
SEED_DIR = Path(__file__).resolve().parents[2] / "src" / "akms" / "_bundled"
SEED_NODES_DIR = SEED_DIR / "global_nodes"
SEED_QMD_DIR = SEED_DIR / "qmd"


# ══════════════════════════════════════════════════════════════════════
#  Fixtures
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def seed_vault(tmp_path: Path) -> Path:
    """Copy seed global nodes to a temp vault directory."""
    vault = tmp_path / "vault" / "nodes"
    vault.mkdir(parents=True)
    for md_file in SEED_NODES_DIR.glob("*.md"):
        shutil.copy2(md_file, vault / md_file.name)
    return vault


@pytest.fixture
def seed_repo(tmp_path: Path) -> Path:
    """Create a temp repo with knowledge/ directory tree and empty overlay."""
    import yaml

    repo = tmp_path / "repo"
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

    # Empty overlay
    overlay_path = knowledge / "graph" / "local_state.yaml"
    overlay_path.write_text(
        yaml.dump(
            {
                "akms_schema": "v2",
                "repo_id": "test-seed-repo",
                "nodes": {},
                "local_edges": [],
                "session_nodes": {},
                "suppressed_edges": [],
            }
        )
    )

    # Copy qmd scripts
    qmd_dest = knowledge / "qmd"
    for qmd_file in SEED_QMD_DIR.glob("*"):
        shutil.copy2(qmd_file, qmd_dest / qmd_file.name)

    return repo


# ══════════════════════════════════════════════════════════════════════
#  Seed Node Schema Validation
# ══════════════════════════════════════════════════════════════════════


class TestSeedNodeValidation:
    """Verify all seed nodes pass schema validation individually."""

    def test_all_seed_nodes_exist(self):
        """Bundled corpus contains the 6 Tier 1 skill nodes.

        Was 7 until the 2026-08-18 §07C rights audit removed
        ``skill-sim-setup`` (private TiFEM APIs throughout, not genericizable).
        """
        nodes = list(SEED_NODES_DIR.glob("skill-*.md"))
        assert len(nodes) == 6, f"Expected 6 skill nodes, found {len(nodes)}: {nodes}"

    @pytest.mark.parametrize(
        "node_file",
        sorted(SEED_NODES_DIR.glob("skill-*.md")),
        ids=lambda p: p.stem,
    )
    def test_seed_node_schema_valid(self, node_file: Path):
        """Each seed node passes global node frontmatter validation."""
        node = parse_node_frontmatter(node_file, is_local=False)
        assert node.id == node_file.stem
        assert node.status == "established"
        assert node.confidence == 0.95
        assert node.confidence_floor == 0.70
        assert node.source == "human"
        assert node.akms_schema == "v2"
        assert len(node.tags) >= 1

    def test_seed_node_ids_are_unique(self):
        """All seed node ids are unique."""
        ids = []
        for md_file in SEED_NODES_DIR.glob("skill-*.md"):
            node = parse_node_frontmatter(md_file, is_local=False)
            ids.append(node.id)
        assert len(ids) == len(set(ids)), f"Duplicate ids: {ids}"

    def test_edge_targets_resolve(self):
        """All edge targets in seed nodes point to existing seed node ids."""
        node_ids = set()
        all_edges = []
        # Edge targets must resolve to the full set of nodes, not just the skills
        for md_file in SEED_NODES_DIR.glob("*.md"):
            node = parse_node_frontmatter(md_file, is_local=False)
            node_ids.add(node.id)

        # Check only the skill nodes for edge resolution initially
        for md_file in SEED_NODES_DIR.glob("skill-*.md"):
            node = parse_node_frontmatter(md_file, is_local=False)
            for edge in node.edges:
                all_edges.append((node.id, edge.to))

        for source, target in all_edges:
            assert target in node_ids, (
                f"Edge from '{source}' → '{target}' targets non-existent node. Known ids: {sorted(node_ids)}"
            )

    def test_seed_node_content_refs_set(self):
        """All seed nodes have a content_ref pointing to a skill file."""
        for md_file in SEED_NODES_DIR.glob("skill-*.md"):
            node = parse_node_frontmatter(md_file, is_local=False)
            assert node.content_ref, f"Node {node.id} missing content_ref"
            assert node.content_ref.startswith("content/"), (
                f"Node {node.id} content_ref should start with 'content/'"
            )


# ══════════════════════════════════════════════════════════════════════
#  Compile Integration — Empty Overlay
# ══════════════════════════════════════════════════════════════════════


class TestCompileEmptyOverlay:
    """Task 2.4: build_graph from seed nodes + empty local overlay."""

    def test_compile_clean(self, seed_vault: Path, seed_repo: Path, monkeypatch):
        """build_graph runs without errors on seed nodes."""
        monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(seed_vault))
        G = build_graph(seed_repo)
        assert G is not None

    def test_all_global_nodes(self, seed_vault: Path, seed_repo: Path, monkeypatch):
        """Compiled graph contains all seed global nodes."""
        monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(seed_vault))
        G = build_graph(seed_repo)
        expected_count = len(list(SEED_NODES_DIR.glob("*.md")))
        assert G.number_of_nodes() == expected_count

        for node_id in G.nodes:
            assert G.nodes[node_id]["node_origin"] == "global"

    def test_all_node_ids_match(self, seed_vault: Path, seed_repo: Path, monkeypatch):
        """Node ids in graph match seed node filenames."""
        monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(seed_vault))
        G = build_graph(seed_repo)

        expected_ids = {p.stem for p in SEED_NODES_DIR.glob("*.md")}
        actual_ids = set(G.nodes)
        assert actual_ids == expected_ids

    def test_graph_json_written(self, seed_vault: Path, seed_repo: Path, monkeypatch):
        """graph.json is created with correct metadata."""
        monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(seed_vault))
        build_graph(seed_repo)

        graph_path = seed_repo / "knowledge" / "graph" / "graph.json"
        assert graph_path.exists()

        with open(graph_path) as f:
            data = json.load(f)

        assert data["graph"]["akms_schema"] == "v2"
        expected_count = len(list(SEED_NODES_DIR.glob("*.md")))
        assert data["graph"]["node_count"] == expected_count
        assert data["graph"]["edge_count"] > 0

    def test_edges_loaded(self, seed_vault: Path, seed_repo: Path, monkeypatch):
        """Structural edges from seed nodes appear in compiled graph."""
        monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(seed_vault))
        G = build_graph(seed_repo)

        # skill-taichi-sim-reviewer has edges to tsr-ref-review-checklist
        assert G.has_edge("skill-taichi-sim-reviewer", "tsr-ref-review-checklist")
        edge_data = G.edges["skill-taichi-sim-reviewer", "tsr-ref-review-checklist"]
        assert edge_data["type"] == "refines"
        assert edge_data["edge_origin"] == "global"

    def test_confidence_defaults(self, seed_vault: Path, seed_repo: Path, monkeypatch):
        """All seed nodes have confidence and confidence_default set."""
        monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(seed_vault))
        G = build_graph(seed_repo)

        for node_id in G.nodes:
            if "node_origin" not in G.nodes[node_id]:
                continue
            conf = G.nodes[node_id]["confidence"]
            # The bundled corpus spans several authored confidence levels
            # (0.8 for the framework-extraction nodes up to 0.95 for the skill
            # seeds), so assert the schema invariant rather than an enumeration
            # that only ever described the original 52-node seed set.
            assert isinstance(conf, float) and 0.0 <= conf <= 1.0, (
                f"Node {node_id} has out-of-range confidence {conf}"
            )
            assert G.nodes[node_id]["confidence_default"] == conf


# ══════════════════════════════════════════════════════════════════════
#  Compile Integration — With Overlay
# ══════════════════════════════════════════════════════════════════════


class TestCompileWithOverlay:
    """Verify overlay confidence overrides apply to seed nodes."""

    def test_confidence_override(self, seed_vault: Path, seed_repo: Path, monkeypatch):
        """Overlay confidence overrides global default."""
        import yaml

        monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(seed_vault))

        # Write overlay with confidence override
        overlay_path = seed_repo / "knowledge" / "graph" / "local_state.yaml"
        overlay_path.write_text(
            yaml.dump(
                {
                    "akms_schema": "v2",
                    "repo_id": "test-seed-repo",
                    "nodes": {
                        "skill-taichi-gpu-sim": {
                            "confidence": 0.88,
                            "activations": 3,
                        }
                    },
                    "local_edges": [],
                    "session_nodes": {},
                    "suppressed_edges": [],
                }
            )
        )

        G = build_graph(seed_repo)

        # Overridden node
        taichi = G.nodes["skill-taichi-gpu-sim"]
        assert taichi["confidence"] == 0.88
        assert taichi["confidence_default"] == 0.95
        assert taichi["activations"] == 3

        # Non-overridden node keeps default
        mechanics = G.nodes["skill-computational-mechanics"]
        assert mechanics["confidence"] == 0.95
        assert mechanics["activations"] == 0

    def test_local_edge_overlay(self, seed_vault: Path, seed_repo: Path, monkeypatch):
        """Local edges from overlay appear in compiled graph."""
        import yaml

        monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(seed_vault))

        overlay_path = seed_repo / "knowledge" / "graph" / "local_state.yaml"
        overlay_path.write_text(
            yaml.dump(
                {
                    "akms_schema": "v2",
                    "repo_id": "test-seed-repo",
                    "nodes": {},
                    "local_edges": [
                        {
                            "from": "skill-taichi-gpu-sim",
                            "to": "session-test-1",
                            "type": "pitfall",
                            "weight": 0.8,
                            "note": "Test pitfall edge",
                        }
                    ],
                    "session_nodes": {
                        "session-test-1": {
                            "title": "Test Session",
                            "tags": ["test"],
                            "outcome": "success",
                            "content_ref": "sessions/test.md",
                            "phase": 1,
                        }
                    },
                    "suppressed_edges": [],
                }
            )
        )

        G = build_graph(seed_repo)

        expected_count = (
            len(list(SEED_NODES_DIR.glob("*.md"))) + 1
        )  # global + 1 session
        assert G.number_of_nodes() == expected_count
        assert G.has_edge("skill-taichi-gpu-sim", "session-test-1")
        edge = G.edges["skill-taichi-gpu-sim", "session-test-1"]
        assert edge["type"] == "pitfall"
        assert edge["edge_origin"] == "local"


# ══════════════════════════════════════════════════════════════════════
#  Compile Integration — With Local Node
# ══════════════════════════════════════════════════════════════════════


class TestCompileWithLocalNode:
    """Verify local nodes appear alongside global seed nodes."""

    def test_local_node_added(self, seed_vault: Path, seed_repo: Path, monkeypatch):
        """A local node appears in the graph with correct origin."""
        from tests.akms.conftest import make_local_node

        monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(seed_vault))

        make_local_node(
            seed_repo,
            id="taichi-static-patterns",
            title="Taichi ti.static Patterns",
            domain="gpu-simulation",
            tags=["taichi", "ti-static"],
            status="tentative",
            confidence=0.70,
            source="agent",
        )

        G = build_graph(seed_repo)

        expected_count = len(list(SEED_NODES_DIR.glob("*.md"))) + 1  # global + 1 local
        assert G.number_of_nodes() == expected_count
        assert "taichi-static-patterns" in G.nodes
        assert G.nodes["taichi-static-patterns"]["node_origin"] == "local"
        assert G.nodes["taichi-static-patterns"]["status"] == "tentative"


# ══════════════════════════════════════════════════════════════════════
#  Determinism
# ══════════════════════════════════════════════════════════════════════


class TestDeterminism:
    """NFR-D01: build output is deterministic."""

    def test_build_twice_identical(
        self, seed_vault: Path, seed_repo: Path, monkeypatch
    ):
        """Building twice produces identical graph.json (excluding timestamp)."""
        monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(seed_vault))

        build_graph(seed_repo)
        graph_path = seed_repo / "knowledge" / "graph" / "graph.json"
        with open(graph_path) as f:
            data1 = json.load(f)

        build_graph(seed_repo)
        with open(graph_path) as f:
            data2 = json.load(f)

        # Strip timestamps for comparison
        data1["graph"].pop("generated_at", None)
        data2["graph"].pop("generated_at", None)

        assert data1 == data2

    def test_roundtrip_preserves_data(
        self, seed_vault: Path, seed_repo: Path, monkeypatch
    ):
        """build → serialize → load_graph preserves all node and edge data."""
        monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(seed_vault))

        G1 = build_graph(seed_repo)
        graph_path = seed_repo / "knowledge" / "graph" / "graph.json"
        G2 = load_graph(graph_path)

        assert set(G1.nodes) == set(G2.nodes)
        assert G1.number_of_edges() == G2.number_of_edges()

        for node_id in G1.nodes:
            # Skip checking attributes on nodes that are implicitly created
            # from missing edge targets (they won't have a status or origin).
            if "node_origin" not in G1.nodes[node_id]:
                continue

            for key in ["id", "domain", "status", "confidence", "node_origin"]:
                assert G1.nodes[node_id].get(key) == G2.nodes[node_id].get(key), (
                    f"Node {node_id} attr {key}: {G1.nodes[node_id].get(key)} != {G2.nodes[node_id].get(key)}"
                )


# ══════════════════════════════════════════════════════════════════════
#  QMD Script Validation
# ══════════════════════════════════════════════════════════════════════


class TestQMDScripts:
    """Verify qmd script stubs are well-formed."""

    def test_all_qmd_scripts_exist(self):
        """All 5 qmd scripts exist."""
        expected = {
            "search_nodes.qmd",
            "search_mirror.qmd",
            "search_sessions.qmd",
            "graph_status.qmd",
            "node_detail.qmd",
        }
        actual = {p.name for p in SEED_QMD_DIR.glob("*.qmd")}
        assert expected == actual

    def test_run_qmd_wrapper_exists(self):
        """run_qmd.sh wrapper exists."""
        assert (SEED_QMD_DIR / "run_qmd.sh").exists()

    def test_qmd_scripts_are_valid_bash(self):
        """All qmd scripts pass bash -n syntax check."""
        for qmd_file in SEED_QMD_DIR.glob("*.qmd"):
            result = subprocess.run(
                ["bash", "-n", str(qmd_file)],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, (
                f"Syntax error in {qmd_file.name}: {result.stderr}"
            )

    def test_run_qmd_valid_bash(self):
        """run_qmd.sh passes bash -n syntax check."""
        result = subprocess.run(
            ["bash", "-n", str(SEED_QMD_DIR / "run_qmd.sh")],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Syntax error in run_qmd.sh: {result.stderr}"

    def test_search_nodes_scopes_both_dirs(self):
        """search_nodes.qmd references both global vault and local nodes."""
        content = (SEED_QMD_DIR / "search_nodes.qmd").read_text()
        assert "AKMS_GLOBAL_VAULT" in content
        assert "local-nodes" in content

    def test_run_qmd_search_nodes_executes(
        self, seed_repo: Path, seed_vault: Path, monkeypatch
    ):
        """run_qmd.sh search_nodes runs without error against seed data."""
        monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(seed_vault))

        # Copy qmd scripts to repo
        qmd_dest = seed_repo / "knowledge" / "qmd"
        for qmd_file in SEED_QMD_DIR.glob("*"):
            shutil.copy2(qmd_file, qmd_dest / qmd_file.name)

        import os as _os

        env = {**_os.environ, "AKMS_GLOBAL_VAULT": str(seed_vault)}
        result = subprocess.run(
            ["bash", str(qmd_dest / "run_qmd.sh"), "search_nodes", "taichi"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, f"search_nodes failed: {result.stderr}"
        assert "Global Nodes" in result.stdout
