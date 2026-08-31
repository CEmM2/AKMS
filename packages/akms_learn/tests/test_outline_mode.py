"""Package-level tests for Mode 1 deterministic outline.

AC covered: 1, 2, 3, 4, 5, 6.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from akms_learn import LearningRequest, fixture_graph, order_nodes
from akms_learn.modes.outline import outline_mode


# Path to the outline module (used by the AST scan test).
_OUTLINE_PY = (
    Path(__file__).resolve().parent.parent
    / "src"
    / "akms_learn"
    / "modes"
    / "outline.py"
)


def _make_request(**overrides) -> LearningRequest:
    """Build a minimal LearningRequest for the fixture graph."""
    defaults = dict(
        topic="j² return mapping",
        goal="Understand the j² return-mapping algorithm",
        audience="engineer",
        depth="implementation",
        generation_option="deterministic_outline",
        seed_tags=[],
        exporters=[],
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


class TestOutlineMode:
    """Tests for Mode 1 deterministic outline.

    AC covered: 1, 2, 3, 4, 5, 6.
    """

    @pytest.mark.integration
    def test_outline_byte_stable_except_timestamp(self) -> None:
        """Two outline runs on the same fixture produce identical dicts.

        The outline_mode return value itself carries no timestamp — the
        timestamp lives in the LSP packet header, which the orchestrator
        attaches later. So dict equality is sufficient here.
        """
        graph = fixture_graph()
        ordered, _ = order_nodes(graph)
        request = _make_request()

        outline_a, warnings_a = outline_mode(graph, ordered, request)
        outline_b, warnings_b = outline_mode(graph, ordered, request)

        assert outline_a == outline_b
        assert warnings_a == warnings_b

    @pytest.mark.integration
    def test_outline_provenance_complete(self) -> None:
        """Every node_id in core_path/prereqs is in the slice; every `requires`
        edge_id appears in concept_map.
        """
        graph = fixture_graph()
        ordered, _ = order_nodes(graph)
        request = _make_request()

        outline, _ = outline_mode(graph, ordered, request)

        slice_node_ids = {
            (n.get("node_id") or n.get("id")) for n in graph.nodes
        }
        for nid in outline["core_path"]:
            assert nid in slice_node_ids, f"core_path node {nid!r} missing from slice"
        for nid in outline["prerequisites"]:
            assert (
                nid in slice_node_ids
            ), f"prerequisite node {nid!r} missing from slice"
        for nid in outline["branches"]:
            assert nid in slice_node_ids, f"branch node {nid!r} missing from slice"

        # Every `requires` edge_id must appear in concept_map["edges"].
        requires_edge_ids = {
            e["edge_id"] for e in graph.edges if e.get("type") == "requires"
        }
        assert requires_edge_ids, "fixture must have at least one `requires` edge"
        for eid in requires_edge_ids:
            assert (
                eid in outline["concept_map"]["edges"]
            ), f"requires edge {eid!r} missing from concept_map"

        #   # Buckets are DISJOINT by construction, so reading_order length equals
        #           # the literal sum of the four bucket lengths — no dedup collapse.
        prereqs = outline["prerequisites"]
        core = outline["core_path"]
        branches = outline["branches"]
        pitfalls = outline["pitfalls"]
        assert set(prereqs).isdisjoint(core)
        assert set(prereqs).isdisjoint(branches)
        assert set(prereqs).isdisjoint(pitfalls)
        assert set(core).isdisjoint(branches)
        assert set(core).isdisjoint(pitfalls)
        assert set(branches).isdisjoint(pitfalls)
        assert len(outline["reading_order"]) == (
            len(prereqs) + len(core) + len(branches) + len(pitfalls)
        )

    @pytest.mark.integration
    def test_outline_no_llm_imports(self) -> None:
        """AST scan of outline.py finds no import of any LLM client library."""
        source = _OUTLINE_PY.read_text(encoding="utf-8")
        tree = ast.parse(source)

        forbidden = {
            "openai",
            "anthropic",
            "litellm",
            "cohere",
            "langchain",
            "llama_index",
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    assert (
                        root not in forbidden
                    ), f"outline.py imports forbidden LLM module {alias.name!r}"
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                assert (
                    root not in forbidden
                ), f"outline.py imports from forbidden LLM module {node.module!r}"

    @pytest.mark.integration
    def test_outline_pitfalls_gated_by_request_flag(self) -> None:
        """include_pitfalls=False → empty pitfalls; True → populated from fixture."""
        graph = fixture_graph()
        ordered, _ = order_nodes(graph)

        outline_off, _ = outline_mode(graph, ordered, _make_request(include_pitfalls=False))
        assert outline_off["pitfalls"] == []

        outline_on, _ = outline_mode(graph, ordered, _make_request(include_pitfalls=True))
        # Fixture has e_core_pitfall: core_j2_return_mapping → pitfall_sign_convention
        assert "pitfall_sign_convention" in outline_on["pitfalls"]
        # All pitfall ids are sorted.
        assert outline_on["pitfalls"] == sorted(outline_on["pitfalls"])
