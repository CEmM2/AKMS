"""Tests for build_graph.py — the merge compiler (Phase 1).

Covers:
- Merging global + local nodes correctly
- Id collision handling (local skipped, warning logged)
- Overlay confidence overrides
- Local edges appear in compiled graph
- Nodes without overlay get global default confidence
- node_origin is correct
- graph.json is valid JSON
- Round-trip idempotency
- Code-mirror node loading
- Session node creation from overlay
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from akms.graph.build_graph import build_graph, load_graph
from akms.schema.errors import SchemaValidationError, SchemaVersionError

from .conftest import (
    make_global_node,
    make_local_node,
    make_mirror_node,
    set_overlay,
)


class TestPayloadDirectoriesIgnored:
    """A vault may ship ``content_ref`` payloads inline under ``content/``.

    Those payloads have frontmatter but no ``akms_schema``; the loader treats
    that as a fatal schema error and re-raises it whatever ``strict`` says.
    Collecting them as nodes therefore made the bundled corpus layout
    unbuildable.
    """

    def test_content_payloads_are_not_collected_as_nodes(self, tmp_repo, tmp_vault):
        make_global_node(tmp_vault, id="node-a", tags=["alpha"])
        payload = tmp_vault / "content" / "some-skill"
        payload.mkdir(parents=True)
        (payload / "SKILL.md").write_text(
            "---\nname: some-skill\ndescription: A payload, not a node.\n---\n\nBody.\n",
            encoding="utf-8",
        )

        G = build_graph(tmp_repo, global_vault=tmp_vault)

        assert G.number_of_nodes() == 1
        assert "node-a" in G.nodes

    def test_payloads_ignored_in_strict_mode(self, tmp_repo, tmp_vault):
        make_global_node(tmp_vault, id="node-a", tags=["alpha"])
        payload = tmp_vault / "content" / "nested" / "deeper"
        payload.mkdir(parents=True)
        (payload / "REFERENCE.md").write_text(
            "---\nname: ref\n---\n\nBody.\n", encoding="utf-8"
        )

        G = build_graph(tmp_repo, global_vault=tmp_vault, strict=True)

        assert G.number_of_nodes() == 1

    def test_node_named_content_md_is_still_collected(self, tmp_repo, tmp_vault):
        """Only ``content/`` *directories* are payloads; the name is not reserved
        for files."""
        make_global_node(tmp_vault, id="content", tags=["alpha"])

        G = build_graph(tmp_repo, global_vault=tmp_vault)

        assert "content" in G.nodes


class TestBuildGraphBasic:
    def test_empty_graph(self, tmp_repo, tmp_vault):
        """Empty vault + empty local → valid empty graph."""
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        assert G.number_of_nodes() == 0
        assert G.number_of_edges() == 0

    def test_global_nodes_loaded(self, tmp_repo, tmp_vault):
        make_global_node(tmp_vault, id="node-a", tags=["alpha"])
        make_global_node(tmp_vault, id="node-b", tags=["beta"])

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        assert G.number_of_nodes() == 2
        assert G.nodes["node-a"]["node_origin"] == "global"
        assert G.nodes["node-b"]["node_origin"] == "global"

    def test_global_edges_loaded(self, tmp_repo, tmp_vault):
        make_global_node(
            tmp_vault,
            id="parent",
            edges=[{"to": "child", "type": "requires", "weight": 1.0}],
        )
        make_global_node(tmp_vault, id="child")

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        assert G.has_edge("parent", "child")
        edge_data = G.edges["parent", "child"]
        assert edge_data["type"] == "requires"
        assert edge_data["weight"] == 1.0
        assert edge_data["edge_origin"] == "global"


class TestBuildGraphLocalNodes:
    def test_local_node_loaded(self, tmp_repo, tmp_vault):
        make_local_node(tmp_repo, id="local-1", tags=["local-tag"])

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        assert "local-1" in G.nodes
        assert G.nodes["local-1"]["node_origin"] == "local"

    def test_id_collision_skips_local(self, tmp_repo, tmp_vault):
        """When local node id collides with global, local is skipped."""
        make_global_node(tmp_vault, id="collision-node", confidence=0.95)
        make_local_node(tmp_repo, id="collision-node", confidence=0.50)

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        # Should have only one node, the global one
        assert G.nodes["collision-node"]["node_origin"] == "global"
        assert G.nodes["collision-node"]["confidence_default"] == 0.95

    def test_mixed_global_and_local(self, tmp_repo, tmp_vault):
        make_global_node(tmp_vault, id="global-1")
        make_local_node(tmp_repo, id="local-1")

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        assert G.number_of_nodes() == 2
        assert G.nodes["global-1"]["node_origin"] == "global"
        assert G.nodes["local-1"]["node_origin"] == "local"


class TestBuildGraphMirrorNodes:
    def test_mirror_node_loaded(self, tmp_repo, tmp_vault):
        make_mirror_node(
            tmp_repo,
            id="mirror-green",
            source_file="src/fft/green.py",
        )

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        assert "mirror-green" in G.nodes
        assert G.nodes["mirror-green"]["node_origin"] == "code-mirror"
        assert G.nodes["mirror-green"]["domain"] == "code-mirror"
        assert G.nodes["mirror-green"]["confidence"] == 1.0
        assert G.nodes["mirror-green"]["auto_update"] is True

    def test_mirror_missing_required_frontmatter_fails_validation(self, tmp_repo, tmp_vault):
        from .conftest import write_node_md

        write_node_md(
            tmp_repo / "knowledge" / "code-mirror" / "mirror-bad.md",
            {
                "id": "mirror-bad",
                "title": "Code Mirror: bad.py",
                "domain": "code-mirror",
                "status": "established",
                "confidence": 1.0,
                "source": "generated",
                "auto_update": True,
                # missing required content_ref
                "source_file": "src/bad.py",
                "generated_at": "2026-03-01T10:00:00",
                "generated_by_phase": 2,
                "akms_schema": "v2",
            },
            "# mirror",
        )

        with pytest.raises(SchemaValidationError):
            build_graph(tmp_repo, global_vault=tmp_vault)

    def test_mirror_with_extra_frontmatter_field_fails_validation(self, tmp_repo, tmp_vault):
        from .conftest import write_node_md

        write_node_md(
            tmp_repo / "knowledge" / "code-mirror" / "mirror-extra.md",
            {
                "id": "mirror-extra",
                "title": "Code Mirror: extra.py",
                "domain": "code-mirror",
                "status": "established",
                "confidence": 1.0,
                "source": "generated",
                "auto_update": True,
                "content_ref": "code-mirror/src/extra.md",
                "source_file": "src/extra.py",
                "generated_at": "2026-03-01T10:00:00",
                "generated_by_phase": 2,
                "akms_schema": "v2",
                "tags": ["should-not-be-here"],
            },
            "# mirror",
        )

        with pytest.raises(SchemaValidationError):
            build_graph(tmp_repo, global_vault=tmp_vault)


class TestBuildGraphOverlay:
    def test_overlay_confidence_overrides_global(self, tmp_repo, tmp_vault):
        make_global_node(tmp_vault, id="node-a", confidence=0.90)
        set_overlay(
            tmp_repo,
            nodes={
                "node-a": {
                    "confidence": 0.75,
                    "activations": 5,
                    "last_activated": "2026-01-15",
                }
            },
        )

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        assert G.nodes["node-a"]["confidence"] == 0.75
        assert G.nodes["node-a"]["confidence_default"] == 0.90
        assert G.nodes["node-a"]["activations"] == 5

    def test_node_without_overlay_gets_default(self, tmp_repo, tmp_vault):
        make_global_node(tmp_vault, id="no-overlay", confidence=0.88)

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        assert G.nodes["no-overlay"]["confidence"] == 0.88
        assert G.nodes["no-overlay"]["confidence_default"] == 0.88
        assert G.nodes["no-overlay"]["activations"] == 0

    def test_overlay_local_edges(self, tmp_repo, tmp_vault):
        make_global_node(tmp_vault, id="node-a")
        set_overlay(
            tmp_repo,
            local_edges=[
                {
                    "from": "node-a",
                    "to": "session-1",
                    "type": "pitfall",
                    "weight": 0.8,
                    "note": "Watch out!",
                }
            ],
            session_nodes={
                "session-1": {
                    "title": "Session 1",
                    "tags": ["test"],
                    "outcome": "success",
                    "content_ref": "sessions/s1.md",
                    "phase": 1,
                }
            },
        )

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        assert G.has_edge("node-a", "session-1")
        assert G.edges["node-a", "session-1"]["type"] == "pitfall"
        assert G.edges["node-a", "session-1"]["edge_origin"] == "local"

    def test_session_nodes_created(self, tmp_repo, tmp_vault):
        set_overlay(
            tmp_repo,
            session_nodes={
                "session-phase2": {
                    "title": "Session: phase2",
                    "tags": ["fft"],
                    "outcome": "success",
                    "content_ref": "sessions/phase2.md",
                    "phase": 2,
                }
            },
        )

        G = build_graph(tmp_repo, global_vault=tmp_vault)
        assert "session-phase2" in G.nodes
        assert G.nodes["session-phase2"]["domain"] == "session"
        assert G.nodes["session-phase2"]["auto_update"] is True

    def test_orphaned_overlay_warns(self, tmp_repo, tmp_vault, caplog):
        """Overlay entry for a node not in graph → warning (not error)."""
        import logging

        set_overlay(
            tmp_repo,
            nodes={"nonexistent": {"confidence": 0.5, "activations": 1}},
        )

        with caplog.at_level(logging.WARNING):
            G = build_graph(tmp_repo, global_vault=tmp_vault)

        assert any("Orphaned overlay" in r.message for r in caplog.records)


class TestBuildGraphSerialization:
    def test_graph_json_written(self, tmp_repo, tmp_vault):
        make_global_node(tmp_vault, id="node-a")
        output = tmp_repo / "knowledge" / "graph" / "graph.json"

        G = build_graph(tmp_repo, global_vault=tmp_vault)

        assert output.exists()
        data = json.loads(output.read_text())
        assert data["directed"] is True
        assert data["graph"]["akms_schema"] == "v2"
        assert data["graph"]["node_count"] == 1
        assert data["graph"]["repo_id"] == "test-repo"

    def test_graph_json_includes_repo_id_without_overlay(self, tmp_repo, tmp_vault):
        make_global_node(tmp_vault, id="node-a")
        (tmp_repo / "knowledge" / "graph" / "local_state.yaml").unlink()

        build_graph(tmp_repo, global_vault=tmp_vault)

        output = tmp_repo / "knowledge" / "graph" / "graph.json"
        data = json.loads(output.read_text())
        assert data["graph"]["repo_id"] == tmp_repo.name

    def test_graph_json_is_valid_json(self, tmp_repo, tmp_vault):
        make_global_node(tmp_vault, id="a")
        make_global_node(
            tmp_vault,
            id="b",
            edges=[{"to": "a", "type": "requires", "weight": 1.0}],
        )

        build_graph(tmp_repo, global_vault=tmp_vault)

        output = tmp_repo / "knowledge" / "graph" / "graph.json"
        data = json.loads(output.read_text())
        assert isinstance(data["nodes"], list)
        assert isinstance(data["links"], list)

    def test_roundtrip_idempotent(self, tmp_repo, tmp_vault):
        """Build twice → identical graph.json (except timestamp)."""
        make_global_node(
            tmp_vault,
            id="alpha",
            edges=[{"to": "beta", "type": "feeds-into", "weight": 0.5}],
        )
        make_global_node(tmp_vault, id="beta")

        G1 = build_graph(tmp_repo, global_vault=tmp_vault)
        output = tmp_repo / "knowledge" / "graph" / "graph.json"
        data1 = json.loads(output.read_text())

        G2 = build_graph(tmp_repo, global_vault=tmp_vault)
        data2 = json.loads(output.read_text())

        # Nodes and links should be identical
        assert data1["nodes"] == data2["nodes"]
        assert data1["links"] == data2["links"]
        assert data1["graph"]["node_count"] == data2["graph"]["node_count"]

    def test_load_graph_roundtrip(self, tmp_repo, tmp_vault):
        """Build → serialize → load → same structure."""
        make_global_node(
            tmp_vault,
            id="alpha",
            edges=[{"to": "beta", "type": "requires", "weight": 1.0}],
        )
        make_global_node(tmp_vault, id="beta")
        set_overlay(
            tmp_repo,
            nodes={"alpha": {"confidence": 0.80, "activations": 3}},
        )

        G_orig = build_graph(tmp_repo, global_vault=tmp_vault)
        output = tmp_repo / "knowledge" / "graph" / "graph.json"
        G_loaded = load_graph(output)

        assert set(G_loaded.nodes) == set(G_orig.nodes)
        assert set(G_loaded.edges) == set(G_orig.edges)
        assert G_loaded.nodes["alpha"]["confidence"] == 0.80
        assert G_loaded.nodes["alpha"]["confidence_default"] == 0.90


class TestBuildGraphSchemaErrors:
    def test_wrong_schema_version_halts(self, tmp_repo, tmp_vault):
        """A node with wrong schema version should halt compilation."""
        from .conftest import write_node_md

        write_node_md(
            tmp_vault / "bad.md",
            {
                "id": "bad",
                "title": "Bad",
                "domain": "test",
                "tags": ["test"],
                "status": "established",
                "confidence": 0.90,
                "source": "human",
                "akms_schema": "v1",
            },
        )

        with pytest.raises(SchemaVersionError):
            build_graph(tmp_repo, global_vault=tmp_vault)


class TestBuildGraphIntegration:
    def test_full_scenario(self, tmp_repo, tmp_vault):
        """Integration: global + local + mirror + overlay → correct compiled graph."""
        # 3 global nodes with edges
        make_global_node(
            tmp_vault,
            id="fft-basics",
            domain="fft-galerkin",
            tags=["fft", "spectral"],
            confidence=0.95,
        )
        make_global_node(
            tmp_vault,
            id="lippmann",
            domain="fft-galerkin",
            tags=["green-operator"],
            confidence=0.90,
            edges=[{"to": "fft-basics", "type": "requires", "weight": 1.0}],
        )
        make_global_node(
            tmp_vault,
            id="plasticity",
            domain="computational-mechanics",
            tags=["plasticity"],
            confidence=0.85,
        )

        # 1 local node
        make_local_node(
            tmp_repo,
            id="tifem-pitfall",
            domain="gpu-simulation",
            tags=["taichi", "pitfall"],
        )

        # 1 mirror node
        make_mirror_node(tmp_repo, id="mirror-green")

        # Overlay with confidence override + local edge + session node
        set_overlay(
            tmp_repo,
            nodes={
                "lippmann": {"confidence": 0.82, "activations": 5},
                "fft-basics": {"confidence": 0.92, "activations": 12},
            },
            local_edges=[
                {
                    "from": "lippmann",
                    "to": "session-phase1",
                    "type": "pitfall",
                    "weight": 0.8,
                    "note": "Epsilon regularization needed",
                }
            ],
            session_nodes={
                "session-phase1": {
                    "title": "Phase 1 session",
                    "tags": ["phase1"],
                    "outcome": "success",
                    "content_ref": "sessions/phase1.md",
                    "phase": 1,
                }
            },
        )

        G = build_graph(tmp_repo, global_vault=tmp_vault)

        # Verify counts
        # 3 global + 1 local + 1 mirror + 1 session = 6
        assert G.number_of_nodes() == 6

        # Verify origins
        assert G.nodes["fft-basics"]["node_origin"] == "global"
        assert G.nodes["lippmann"]["node_origin"] == "global"
        assert G.nodes["plasticity"]["node_origin"] == "global"
        assert G.nodes["tifem-pitfall"]["node_origin"] == "local"
        assert G.nodes["mirror-green"]["node_origin"] == "code-mirror"
        assert G.nodes["session-phase1"]["node_origin"] == "local"

        # Verify overlay applied
        assert G.nodes["lippmann"]["confidence"] == 0.82
        assert G.nodes["lippmann"]["confidence_default"] == 0.90
        assert G.nodes["fft-basics"]["confidence"] == 0.92
        assert G.nodes["fft-basics"]["activations"] == 12

        # Plasticity has no overlay → default
        assert G.nodes["plasticity"]["confidence"] == 0.85
        assert G.nodes["plasticity"]["activations"] == 0

        # Verify edges: 1 global (lippmann→fft-basics) + 1 local (lippmann→session)
        assert G.has_edge("lippmann", "fft-basics")
        assert G.edges["lippmann", "fft-basics"]["edge_origin"] == "global"
        assert G.has_edge("lippmann", "session-phase1")
        assert G.edges["lippmann", "session-phase1"]["edge_origin"] == "local"

        # Verify serialization
        output = tmp_repo / "knowledge" / "graph" / "graph.json"
        assert output.exists()
        data = json.loads(output.read_text())
        assert data["graph"]["node_count"] == 6
