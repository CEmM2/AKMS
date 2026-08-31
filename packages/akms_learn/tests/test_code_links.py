"""Tests for CodeLinkView + implements-edge handling.

Verifies:

* CodeLinkView carries source_node_id, target, relation='implements',
  optional file_path + line_range.
* Compiler emits one CodeLinkView per implements edge in the slice.
* A code-mirror node with missing source path triggers exactly one
  ``code_mirror_missing_source_path`` warning.
* Compiler does not crash on slices that have no implements edges,
  and produces zero CodeLinkViews + no missing-source warning in that case.

Also asserts determinism: compiling the same slice twice yields identical
CodeLinkView lists.
"""

from __future__ import annotations

import pytest

from akms_learn import LearningRequest, compile_learning_source
from akms_learn.models import CodeLinkView
from akms_learn.toy_fixtures import (
    fixture_graph_toy_concept_kit,
    fixture_graph_toy_executable_bridge,
    fixture_graph_toy_workbench,
)


def _make_request(**overrides) -> LearningRequest:
    """Build a minimal LearningRequest that admits every toy fixture."""
    defaults = dict(
        topic="toy pipeline implementation",
        goal="Exercise the implements-edge collector.",
        audience="engineer",
        depth="implementation",
        generation_option="deterministic_outline",
        seed_tags=[],
        exporters=[],
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


# ---------------------------------------------------------------------------
# CodeLinkView field surface
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCodeLinkViewFieldSurface:
    """CodeLinkView exposes the extended code-link fields."""

    def test_required_p1_3_fields_present_with_defaults(self):
        """source_node_id, target, relation, file_path, line_range exist."""
        view = CodeLinkView(node_id="x", source_file="src/x.py")
        # All four extended optional fields exist on the model.
        assert hasattr(view, "source_node_id")
        assert hasattr(view, "target")
        assert hasattr(view, "relation")
        assert hasattr(view, "file_path")
        assert hasattr(view, "line_range")
        # Default relation is "implements" (the only emitted edge type).
        assert view.relation == "implements"
        # All other new fields default to None.
        assert view.source_node_id is None
        assert view.target is None
        assert view.file_path is None
        assert view.line_range is None

    def test_explicit_field_assignment_round_trips(self):
        """Setting every extended field round-trips through model_dump."""
        view = CodeLinkView(
            node_id="spec_a",
            source_file="src/impl.py",
            source_node_id="spec_a",
            target="impl_a",
            relation="implements",
            file_path="src/impl.py",
            line_range=(12, 24),
        )
        dumped = view.model_dump()
        assert dumped["source_node_id"] == "spec_a"
        assert dumped["target"] == "impl_a"
        assert dumped["relation"] == "implements"
        assert dumped["file_path"] == "src/impl.py"
        assert dumped["line_range"] == (12, 24)

    def test_legacy_call_signature_still_works(self):
        """Legacy canary: positional/default-only construction still valid."""
        view = CodeLinkView(node_id="legacy", source_file="src/legacy.py")
        assert view.node_id == "legacy"
        assert view.source_file == "src/legacy.py"


# ---------------------------------------------------------------------------
# Compiler emits one CodeLinkView per implements edge
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestImplementsEdgeProducesCodeLink:
    """Implements edges in the slice produce CodeLinkView entries."""

    def test_executable_bridge_yields_one_code_link(self):
        result = compile_learning_source(
            request=_make_request(),
            graph_slice=fixture_graph_toy_executable_bridge(),
        )
        code_links = result.packet.body.code_links
        # The bridge fixture has exactly one implements edge.
        assert len(code_links) == 1, (
            f"expected exactly one CodeLinkView from toy_executable_bridge, "
            f"got {len(code_links)}: {code_links!r}"
        )

    def test_code_link_carries_required_p1_3_fields(self):
        result = compile_learning_source(
            request=_make_request(),
            graph_slice=fixture_graph_toy_executable_bridge(),
        )
        link = result.packet.body.code_links[0]
        assert link.relation == "implements"
        assert link.source_node_id == "bridge_spec"
        # ``target`` resolves to the target node id when present.
        assert link.target == "bridge_artifact"


# ---------------------------------------------------------------------------
# Missing source path on code mirror triggers warning
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMissingSourcePathWarning:
    """Code-mirror with missing source path triggers warning code."""

    def test_bridge_fixture_with_implements_to_mirror_warns(self):
        """Seed an implements edge straight into the code_mirror node."""
        slice_ = fixture_graph_toy_executable_bridge()
        # Build a modified slice where the implements edge points directly
        # at the code-mirror node (with source_path == 'unknown').
        edges = [
            {
                "edge_id": "e_bridge_spec_mirror",
                "from": "bridge_spec",
                "to": "bridge_code_mirror",
                "type": "implements",
                "source_path": "toy://bridge/edges.md",
                "line_range": [3, 3],
            },
        ]
        from akms_learn.graph_import import GraphSlice

        seeded = GraphSlice(
            nodes=slice_.nodes,
            edges=tuple(edges),
            metadata=dict(slice_.metadata),
        )
        result = compile_learning_source(
            request=_make_request(),
            graph_slice=seeded,
        )
        codes = [w.code for w in result.warnings]
        assert codes.count("code_mirror_missing_source_path") == 1, (
            f"expected exactly one code_mirror_missing_source_path warning, "
            f"got codes={codes}"
        )
        # Source ref must identify the offending mirror node.
        warn = next(
            w
            for w in result.warnings
            if w.code == "code_mirror_missing_source_path"
        )
        assert warn.source_ref == "bridge_code_mirror"

    def test_no_warning_when_mirror_has_usable_source_path(self):
        """A code-mirror with a concrete source path produces no warning."""
        slice_ = fixture_graph_toy_executable_bridge()
        # Patch the mirror node so its source_path is now usable.
        nodes = []
        for node in slice_.nodes:
            n = dict(node)
            if n["node_id"] == "bridge_code_mirror":
                n["source_path"] = "src/bridge/mirror.py"
                n["line_range"] = [1, 20]
            nodes.append(n)
        edges = [
            {
                "edge_id": "e_bridge_spec_mirror",
                "from": "bridge_spec",
                "to": "bridge_code_mirror",
                "type": "implements",
                "source_path": "toy://bridge/edges.md",
                "line_range": [3, 3],
            },
        ]
        from akms_learn.graph_import import GraphSlice

        seeded = GraphSlice(
            nodes=tuple(nodes),
            edges=tuple(edges),
            metadata=dict(slice_.metadata),
        )
        result = compile_learning_source(
            request=_make_request(),
            graph_slice=seeded,
        )
        codes = [w.code for w in result.warnings]
        assert "code_mirror_missing_source_path" not in codes
        # The produced CodeLinkView now carries the resolved file_path/line.
        link = result.packet.body.code_links[0]
        assert link.file_path == "src/bridge/mirror.py"
        assert link.line_range == (1, 20)


# ---------------------------------------------------------------------------
# Compiler graceful when no implements edges
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNoImplementsEdgesGraceful:
    """Slices without implements edges yield no views and no warning."""

    @pytest.mark.parametrize(
        "factory,family",
        [
            (fixture_graph_toy_concept_kit, "toy_concept_kit"),
            (fixture_graph_toy_workbench, "toy_workbench"),
        ],
    )
    def test_zero_code_links_zero_warning(self, factory, family):
        result = compile_learning_source(
            request=_make_request(),
            graph_slice=factory(),
        )
        assert result.packet.body.code_links == [], (
            f"expected no CodeLinkViews for {family!r}, got "
            f"{result.packet.body.code_links!r}"
        )
        codes = [w.code for w in result.warnings]
        assert "code_mirror_missing_source_path" not in codes


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCodeLinkDeterminism:
    """CodeLinkView collection is deterministic across runs."""

    def test_double_compile_identical_code_links(self):
        slice_ = fixture_graph_toy_executable_bridge()
        a = compile_learning_source(request=_make_request(), graph_slice=slice_)
        b = compile_learning_source(request=_make_request(), graph_slice=slice_)
        assert [
            link.model_dump() for link in a.packet.body.code_links
        ] == [
            link.model_dump() for link in b.packet.body.code_links
        ]
