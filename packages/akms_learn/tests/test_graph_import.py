"""Package-level tests for Graph import.

AC covered:
  1. load_graph with graph_path reads a JSON file and returns GraphSlice
  2. load_graph with graph_slice accepts a dict matching schema
  3. load_graph errors when both inputs supplied (and when neither supplied)
  4. compute_graph_hash is stable across runs, key-order-insensitive
  5. fixture_graph() returns a GraphSlice with >=3 nodes and >=1 pitfall edge
  6. Source file timestamps unchanged after load
"""

import json
import os

import pytest

from akms_learn.graph_import import (
    GraphSlice,
    compute_graph_hash,
    fixture_graph,
    load_graph,
)


# ---------------------------------------------------------------------------
# Shared minimal graph payload
# ---------------------------------------------------------------------------

_MINIMAL_PAYLOAD: dict = {
    "nodes": [
        {"node_id": "n1", "kind": "prerequisite"},
        {"node_id": "n2", "kind": "core_concept"},
        {"node_id": "n3", "kind": "pitfall"},
    ],
    "edges": [
        {"edge_id": "e1", "from": "n1", "to": "n2", "type": "requires"},
        {"edge_id": "e2", "from": "n2", "to": "n3", "type": "pitfall_of"},
    ],
    "metadata": {"description": "minimal test graph"},
}


class TestGraphImport:
    """Tests for Graph import (path, GraphSlice, fixture).

    AC covered: 1, 2, 3, 4, 5, 6.
    """

    @pytest.mark.unit
    def test_load_graph_from_path(self, tmp_path):
        """load_graph(graph_path=...) reads graph.json and returns a GraphSlice.

        AC 1 + AC 6: returns GraphSlice with correct content; source mtime unchanged.
        """
        graph_file = tmp_path / "graph.json"
        graph_file.write_text(json.dumps(_MINIMAL_PAYLOAD), encoding="utf-8")

        mtime_before = os.path.getmtime(graph_file)

        result = load_graph(graph_path=graph_file)

        mtime_after = os.path.getmtime(graph_file)

        # Returns a GraphSlice
        assert isinstance(result, GraphSlice)

        # Nodes and edges match
        assert len(result.nodes) == 3
        assert len(result.edges) == 2
        assert result.nodes[0]["node_id"] == "n1"
        assert result.edges[0]["type"] == "requires"

        # Metadata preserved
        assert result.metadata["description"] == "minimal test graph"

        # Source file mtime is unchanged (AC 6)
        assert mtime_after == mtime_before, (
            f"load_graph must not touch source file timestamps: "
            f"before={mtime_before}, after={mtime_after}"
        )

    @pytest.mark.unit
    def test_load_graph_from_slice(self):
        """load_graph(graph_slice=...) accepts a dict matching the GraphSlice schema.

        AC 2: in-memory dict is validated into a GraphSlice.
        """
        result = load_graph(graph_slice=_MINIMAL_PAYLOAD)

        assert isinstance(result, GraphSlice)
        assert len(result.nodes) == 3
        assert len(result.edges) == 2
        assert result.metadata["description"] == "minimal test graph"

        # Node and edge content is round-trippable
        node_ids = {n["node_id"] for n in result.nodes}
        assert node_ids == {"n1", "n2", "n3"}

        edge_types = {e["type"] for e in result.edges}
        assert "pitfall_of" in edge_types

    @pytest.mark.unit
    def test_load_graph_mutual_exclusion(self, tmp_path):
        """load_graph errors when both graph_path and graph_slice are supplied.

        AC 3: mutual exclusion raises ValueError; neither supplied also raises ValueError.
        """
        graph_file = tmp_path / "graph.json"
        graph_file.write_text(json.dumps(_MINIMAL_PAYLOAD), encoding="utf-8")

        # Both supplied → ValueError
        with pytest.raises(ValueError, match="mutually exclusive"):
            load_graph(graph_path=graph_file, graph_slice=_MINIMAL_PAYLOAD)

        # Neither supplied → ValueError
        with pytest.raises(ValueError):
            load_graph()

    @pytest.mark.unit
    def test_graph_hash_stable(self):
        """compute_graph_hash returns the same digest across repeated calls.

        AC 4: stable (same input → same digest); differs on changed content;
        insensitive to dict key ordering.
        """
        slice_a = load_graph(graph_slice=_MINIMAL_PAYLOAD)

        hash1 = compute_graph_hash(slice_a)
        hash2 = compute_graph_hash(slice_a)

        # Stability across two calls
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex digest

        # Different content → different hash
        different_payload = {
            "nodes": [{"node_id": "x", "kind": "core_concept"}],
            "edges": [],
            "metadata": {},
        }
        slice_b = load_graph(graph_slice=different_payload)
        hash_b = compute_graph_hash(slice_b)
        assert hash_b != hash1

        # Key-ordering insensitivity within a node dict
        # Build two slices whose node dicts have keys in different order
        payload_key_order_a = {
            "nodes": [{"node_id": "k1", "kind": "prerequisite", "extra": "val"}],
            "edges": [],
            "metadata": {},
        }
        payload_key_order_b = {
            "nodes": [{"extra": "val", "kind": "prerequisite", "node_id": "k1"}],
            "edges": [],
            "metadata": {},
        }
        slice_ko_a = load_graph(graph_slice=payload_key_order_a)
        slice_ko_b = load_graph(graph_slice=payload_key_order_b)
        assert compute_graph_hash(slice_ko_a) == compute_graph_hash(slice_ko_b)

    @pytest.mark.unit
    def test_fixture_graph_shape(self):
        """fixture_graph() returns a GraphSlice with >=3 nodes and >=1 pitfall edge.

        AC 5.
        """
        g = fixture_graph()

        assert isinstance(g, GraphSlice)

        # At least 3 nodes
        assert len(g.nodes) >= 3, f"Expected >=3 nodes, got {len(g.nodes)}"

        # At least 1 pitfall_of edge
        pitfall_edges = [e for e in g.edges if e.get("type") == "pitfall_of"]
        assert len(pitfall_edges) >= 1, (
            f"Expected >=1 edge with type='pitfall_of', found none. "
            f"Edge types present: {[e.get('type') for e in g.edges]}"
        )

        #   # Nodes include at least one of each kind the ordering step requires.
        node_kinds = {n.get("kind") for n in g.nodes}
        assert "prerequisite" in node_kinds, (
            f"No prerequisite node; kinds: {node_kinds}"
        )
        assert "core_concept" in node_kinds, (
            f"No core_concept node; kinds: {node_kinds}"
        )
        assert "pitfall" in node_kinds, f"No pitfall node; kinds: {node_kinds}"
