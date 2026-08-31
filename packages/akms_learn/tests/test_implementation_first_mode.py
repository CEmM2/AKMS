"""Tests for implementation_first mode.

Covers all four acceptance criteria:

implementation_first output includes implements-edge artifacts when
      present in the request slice.
Concept nodes remain linked to code nodes through provenance.
Missing code paths do not crash the compiler — a warning fires and
      ordering still produces a valid LSP.
code_first policy places code section first; concept_first policy
      places concepts first.

Plus auxiliary tests: strategy/mode consistency, default-policy fallback,
LearningRequest.policy round-trip, and a synthetic policy fixture.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from akms_learn.graph_import import GraphSlice
from akms_learn.models import CodeLinkView, LearningWarning
from akms_learn.modes.implementation_first import (
    DEFAULT_POLICY,
    IMPLEMENTATION_ANCHOR_MISSING_SOURCE_CODE,
    MISSING_SOURCE_PATH_SENTINELS,
    ImplementationFirstResult,
    implementation_first_mode,
    implementation_first_strategy,
)
from akms_learn.ordering import get_strategy
from akms_learn.toy_fixtures import (
    fixture_graph_toy_concept_kit,
    fixture_graph_toy_executable_bridge,
    fixture_graph_toy_workbench,
)
from akms_learn.requests import LearningRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(**overrides: Any) -> LearningRequest:
    defaults: dict[str, Any] = dict(
        topic="toy implementation bridge",
        goal="Exercise the implementation_first mode end-to-end.",
        audience="engineer",
        depth="implementation",
        generation_option="implementation_first",
        seed_tags=[],
        exporters=[],
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


def _run_mode(
    graph_slice: GraphSlice,
    request: LearningRequest | None = None,
) -> tuple[ImplementationFirstResult, list[LearningWarning]]:
    if request is None:
        request = _make_request()
    return implementation_first_mode(graph_slice, request)


def _policy_fixture() -> GraphSlice:
    """Build a synthetic slice exercising the policy switch.

    Topology::

        policy_concept_a  ──requires──►  policy_impl_target
        policy_concept_b  ──requires──►  policy_concept_a
        policy_spec       ──implements──►  policy_impl_target

    ``policy_impl_target`` is the implementation anchor (target of an
    ``implements`` edge). The concept prereqs are
    ``policy_concept_a`` and ``policy_concept_b``.
    """
    nodes: list[dict[str, Any]] = [
        {
            "node_id": "policy_concept_a",
            "title": "Concept A (policy fixture)",
            "kind": "core_concept",
            "source_path": "toy://policy/concept_a.md",
            "line_range": [1, 4],
            "extracted": {"concept": "# Concept\nFoundation A."},
        },
        {
            "node_id": "policy_concept_b",
            "title": "Concept B (policy fixture)",
            "kind": "core_concept",
            "source_path": "toy://policy/concept_b.md",
            "line_range": [1, 4],
            "extracted": {"concept": "# Concept\nFoundation B."},
        },
        {
            "node_id": "policy_impl_target",
            "title": "Implementation Target (policy fixture)",
            "kind": "implementation",
            "source_path": "toy://policy/impl.py",
            "line_range": [10, 30],
            "extracted": {"implementation": "# Implementation\nThe target."},
        },
        {
            "node_id": "policy_spec",
            "title": "Spec (policy fixture)",
            "kind": "derivation",
            "source_path": "toy://policy/spec.md",
            "line_range": [1, 6],
            "extracted": {"derivation": "# Derivation\nSpec body."},
        },
    ]
    edges: list[dict[str, Any]] = [
        {
            "edge_id": "e_policy_a_to_impl",
            "from": "policy_concept_a",
            "to": "policy_impl_target",
            "type": "requires",
            "source_path": "toy://policy/edges.md",
            "line_range": [1, 1],
        },
        {
            "edge_id": "e_policy_b_to_a",
            "from": "policy_concept_b",
            "to": "policy_concept_a",
            "type": "requires",
            "source_path": "toy://policy/edges.md",
            "line_range": [2, 2],
        },
        {
            "edge_id": "e_policy_spec_implements_impl",
            "from": "policy_spec",
            "to": "policy_impl_target",
            "type": "implements",
            "source_path": "toy://policy/edges.md",
            "line_range": [3, 3],
        },
    ]
    metadata = {
        "description": "Synthetic policy fixture for the implementation_first mode.",
        "graph_version": "toy-policy-v1",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "family": "toy_policy",
    }
    return GraphSlice(nodes=tuple(nodes), edges=tuple(edges), metadata=metadata)


# ---------------------------------------------------------------------------
# implements-edge artifacts appear in result
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestImplementsEdgeArtifacts:
    """Implements-edge artifacts appear in implementation_first output."""

    def test_bridge_fixture_produces_code_references(self):
        gs = fixture_graph_toy_executable_bridge()
        result, _ = _run_mode(gs)
        assert isinstance(result, ImplementationFirstResult)
        assert result.code_references, (
            "Expected non-empty code_references for executable_bridge fixture; "
            f"got {result.code_references!r}"
        )

    def test_code_references_are_codelinkview_instances(self):
        gs = fixture_graph_toy_executable_bridge()
        result, _ = _run_mode(gs)
        for cr in result.code_references:
            assert isinstance(cr, CodeLinkView)

    def test_code_reference_has_implements_relation(self):
        gs = fixture_graph_toy_executable_bridge()
        result, _ = _run_mode(gs)
        for cr in result.code_references:
            assert cr.relation == "implements"

    def test_code_reference_carries_source_and_target_node_ids(self):
        """Every emitted CodeLinkView must carry source_node_id and target."""
        gs = fixture_graph_toy_executable_bridge()
        result, _ = _run_mode(gs)
        for cr in result.code_references:
            assert cr.source_node_id, f"missing source_node_id on {cr!r}"
            assert cr.target, f"missing target on {cr!r}"

    def test_implementation_anchor_appears_in_ordered_output(self):
        """The implements-edge target (bridge_artifact) is in ordered_nodes."""
        gs = fixture_graph_toy_executable_bridge()
        result, _ = _run_mode(gs)
        assert "bridge_artifact" in result.ordered_nodes


# ---------------------------------------------------------------------------
# Concept nodes remain linked to code nodes through provenance
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestConceptCodeProvenance:
    """Concept→code provenance is preserved by the result struct."""

    def test_code_section_contains_anchors(self):
        gs = _policy_fixture()
        result, _ = _run_mode(gs)
        assert "policy_impl_target" in result.code_section

    def test_concept_section_contains_prereqs(self):
        """Backward walk surfaces both transitive prereqs."""
        gs = _policy_fixture()
        result, _ = _run_mode(gs)
        # policy_concept_a directly requires policy_impl_target.
        # policy_concept_b requires policy_concept_a (transitive).
        assert "policy_concept_a" in result.concept_section
        assert "policy_concept_b" in result.concept_section

    def test_concept_section_is_disjoint_from_code_section(self):
        gs = _policy_fixture()
        result, _ = _run_mode(gs)
        assert not (set(result.concept_section) & set(result.code_section))

    def test_code_reference_target_matches_anchor_node_id(self):
        """The implements-edge target node id appears as a code-reference target."""
        gs = _policy_fixture()
        result, _ = _run_mode(gs)
        targets = {cr.target for cr in result.code_references}
        assert "policy_impl_target" in targets

    def test_code_reference_source_matches_implements_edge_from(self):
        """The implements-edge ``from`` node id appears as source_node_id."""
        gs = _policy_fixture()
        result, _ = _run_mode(gs)
        sources = {cr.source_node_id for cr in result.code_references}
        assert "policy_spec" in sources

    def test_provenance_lists_match_slice(self):
        gs = _policy_fixture()
        result, _ = _run_mode(gs)
        expected_node_ids = sorted(n["node_id"] for n in gs.nodes)
        assert result.source_node_ids == expected_node_ids
        expected_edge_ids = sorted(
            str(e["edge_id"]) for e in gs.edges if e.get("edge_id")
        )
        assert result.edge_ids == expected_edge_ids


# ---------------------------------------------------------------------------
# Missing source path emits warning, LSP still valid
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMissingSourceWarning:
    """Anchor missing source_path emits warning; result still valid."""

    def test_bridge_fixture_does_not_crash_on_unknown_source(self):
        """The executable_bridge fixture seeds 'unknown' source paths."""
        gs = fixture_graph_toy_executable_bridge()
        # Must not raise.
        result, warnings = _run_mode(gs)
        assert isinstance(result, ImplementationFirstResult)
        assert isinstance(result.ordered_nodes, list)
        assert result.ordered_nodes, "ordered_nodes must not be empty"

    def test_bridge_fixture_emits_missing_source_warning_for_unknown_anchor(self):
        """bridge_code_mirror has source_path='unknown' — anchor warning fires."""
        gs = fixture_graph_toy_executable_bridge()
        _, warnings = _run_mode(gs)
        codes = [w.code for w in warnings]
        assert IMPLEMENTATION_ANCHOR_MISSING_SOURCE_CODE in codes, (
            f"Expected {IMPLEMENTATION_ANCHOR_MISSING_SOURCE_CODE!r} in warnings; "
            f"got {codes}"
        )

    def test_missing_source_warning_names_offending_anchor(self):
        gs = fixture_graph_toy_executable_bridge()
        _, warnings = _run_mode(gs)
        missing = [
            w for w in warnings
            if w.code == IMPLEMENTATION_ANCHOR_MISSING_SOURCE_CODE
        ]
        assert any(w.source_ref == "bridge_code_mirror" for w in missing), (
            "Expected bridge_code_mirror in missing-source warning source_refs; "
            f"got {[w.source_ref for w in missing]}"
        )

    def test_missing_source_warning_is_learning_warning_instance(self):
        gs = fixture_graph_toy_executable_bridge()
        _, warnings = _run_mode(gs)
        missing = [
            w for w in warnings
            if w.code == IMPLEMENTATION_ANCHOR_MISSING_SOURCE_CODE
        ]
        for w in missing:
            assert isinstance(w, LearningWarning)
            assert w.severity == "warning"

    def test_no_warning_when_all_anchors_have_source_paths(self):
        """policy fixture has usable source_path on all anchors."""
        gs = _policy_fixture()
        _, warnings = _run_mode(gs)
        missing = [
            w for w in warnings
            if w.code == IMPLEMENTATION_ANCHOR_MISSING_SOURCE_CODE
        ]
        assert not missing, (
            "Did not expect missing-source warnings on the policy fixture; "
            f"got {[w.source_ref for w in missing]}"
        )

    def test_concept_kit_no_anchors_no_anchor_warnings(self):
        """No implements edges → no anchor warnings, but result is still valid."""
        gs = fixture_graph_toy_concept_kit()
        result, warnings = _run_mode(gs)
        missing = [
            w for w in warnings
            if w.code == IMPLEMENTATION_ANCHOR_MISSING_SOURCE_CODE
        ]
        assert not missing
        assert set(result.ordered_nodes) == {n["node_id"] for n in gs.nodes}

    def test_missing_source_sentinels_include_unknown(self):
        assert "unknown" in MISSING_SOURCE_PATH_SENTINELS
        assert "none" in MISSING_SOURCE_PATH_SENTINELS
        assert "null" in MISSING_SOURCE_PATH_SENTINELS


# ---------------------------------------------------------------------------
# code_first vs concept_first policy
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPolicySectionOrder:
    """Code_first puts code first; concept_first puts concepts first."""

    def test_code_first_places_code_section_before_concept_section(self):
        gs = _policy_fixture()
        req = _make_request(policy="code_first")
        result, _ = _run_mode(gs, req)
        assert result.policy == "code_first"
        # Code section (anchors) must appear before concept section in
        # ordered_nodes.
        first_anchor = result.code_section[0]
        first_concept = result.concept_section[0]
        assert result.ordered_nodes.index(first_anchor) < result.ordered_nodes.index(
            first_concept
        ), (
            f"code_first: expected anchor {first_anchor!r} before concept "
            f"{first_concept!r}; ordered_nodes={result.ordered_nodes}"
        )

    def test_concept_first_places_concept_section_before_code_section(self):
        gs = _policy_fixture()
        req = _make_request(policy="concept_first")
        result, _ = _run_mode(gs, req)
        assert result.policy == "concept_first"
        first_anchor = result.code_section[0]
        first_concept = result.concept_section[0]
        assert result.ordered_nodes.index(first_concept) < result.ordered_nodes.index(
            first_anchor
        ), (
            f"concept_first: expected concept {first_concept!r} before anchor "
            f"{first_anchor!r}; ordered_nodes={result.ordered_nodes}"
        )

    def test_default_policy_is_concept_first(self):
        """Unspecified policy normalises to concept_first."""
        gs = _policy_fixture()
        # No policy set → request.policy is None → resolved to concept_first.
        req = _make_request()
        assert req.policy is None
        result, _ = _run_mode(gs, req)
        assert result.policy == DEFAULT_POLICY == "concept_first"

    def test_unknown_policy_falls_back_to_default(self):
        gs = _policy_fixture()
        req = _make_request(policy="banana")
        result, _ = _run_mode(gs, req)
        assert result.policy == DEFAULT_POLICY

    def test_policy_case_insensitive(self):
        gs = _policy_fixture()
        req = _make_request(policy="CODE_FIRST")
        result, _ = _run_mode(gs, req)
        assert result.policy == "code_first"


# ---------------------------------------------------------------------------
# Auxiliary: strategy registration + determinism
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestStrategyIntegration:
    """The implementation_first strategy is registered and consistent."""

    def test_strategy_registered_under_implementation_first_key(self):
        strategy = get_strategy("implementation_first")
        gs = fixture_graph_toy_executable_bridge()
        ordered, warnings = strategy(gs)
        assert isinstance(ordered, list)
        assert set(ordered) == {n["node_id"] for n in gs.nodes}

    def test_strategy_matches_mode_default_policy(self):
        """Strategy ordering (default = concept_first) matches mode result."""
        gs = _policy_fixture()
        strategy_order, _ = implementation_first_strategy(gs)
        result, _ = _run_mode(gs)  # default policy = concept_first
        assert strategy_order == result.ordered_nodes

    def test_deterministic_across_two_runs(self):
        gs = fixture_graph_toy_executable_bridge()
        r1, _ = _run_mode(gs)
        r2, _ = _run_mode(gs)
        assert r1.ordered_nodes == r2.ordered_nodes
        assert r1.code_section == r2.code_section
        assert r1.concept_section == r2.concept_section

    def test_no_mutation_of_graph_slice(self):
        gs = fixture_graph_toy_executable_bridge()
        before = copy.deepcopy([dict(n) for n in gs.nodes])
        _ = _run_mode(gs)
        after = [dict(n) for n in gs.nodes]
        assert before == after

    def test_request_without_policy_is_valid(self):
        """LearningRequest constructs without policy and treats it as None."""
        req = _make_request()
        assert req.policy is None


# ---------------------------------------------------------------------------
# Auxiliary: workbench fixture has no implements edges
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestWorkbenchNoAnchors:
    """The workbench fixture has no implements edges — code_references empty."""

    def test_workbench_has_no_code_references(self):
        gs = fixture_graph_toy_workbench()
        result, _ = _run_mode(gs)
        assert result.code_references == []

    def test_workbench_concept_section_is_empty(self):
        gs = fixture_graph_toy_workbench()
        result, _ = _run_mode(gs)
        # No implements edges, no code_mirror nodes → no anchors, no prereq walk.
        assert result.code_section == []
        assert result.concept_section == []

    def test_workbench_ordered_nodes_covers_slice(self):
        gs = fixture_graph_toy_workbench()
        result, _ = _run_mode(gs)
        assert set(result.ordered_nodes) == {n["node_id"] for n in gs.nodes}
