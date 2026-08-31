"""Tests for derivation_first mode.

Covers all four acceptance criteria:

Derivation nodes precede implementation nodes in the ordered output.
Missing derivation sections produce a 'derivation_gap' warning with
      the offending node id in source_ref.
Cycle-breaking remains deterministic across two runs on the same fixture.
role_in_lesson values appear in the LSP only and are absent from any
      persisted AKMS graph file (graph slice is not mutated).

Plus auxiliary tests: role classification, gap-fixture targeting, no-spurious-
warnings on populated fixture, LLM-free import check.
"""

from __future__ import annotations

from typing import Any

import pytest

from akms_learn.graph_import import GraphSlice
from akms_learn.models import LearningWarning
from akms_learn.modes.derivation_first import (
    DERIVATION_GAP_CODE,
    DERIVATION_HEAVY_HEADINGS,
    IMPLEMENTATION_HEADINGS,
    DerivationFirstResult,
    NodeLessonRoleView,
    derivation_first_mode,
    derivation_first_strategy,
)
from akms_learn.ordering import get_strategy
from akms_learn.toy_fixtures import (
    fixture_graph_toy_concept_kit,
    fixture_graph_toy_derivation_gap,
    fixture_graph_toy_executable_bridge,
    fixture_graph_toy_workbench,
)
from akms_learn.requests import LearningRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(**overrides: Any) -> LearningRequest:
    defaults: dict[str, Any] = dict(
        topic="toy derivation pipeline",
        goal="Exercise the derivation_first mode end-to-end.",
        audience="engineer",
        depth="theory",
        generation_option="derivation_first",
        seed_tags=[],
        exporters=[],
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


def _run_mode(
    graph_slice: GraphSlice,
    request: LearningRequest | None = None,
) -> tuple[DerivationFirstResult, list[LearningWarning]]:
    if request is None:
        request = _make_request()
    return derivation_first_mode(graph_slice, request)


def _run_strategy(
    graph_slice: GraphSlice,
) -> tuple[list[str], list[LearningWarning]]:
    """Run the strategy (ordering-only, no role views or gap warnings)."""
    strategy = get_strategy("derivation_first")
    return strategy(graph_slice)


# ---------------------------------------------------------------------------
# Derivation nodes precede implementation nodes
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDerivationBeforeImplementation:
    """Derivation-heavy nodes appear before implementation-only nodes."""

    def test_workbench_derivation_before_implementation_nodes(self):
        """workbench fixture: derivation example precedes any implementation nodes."""
        gs = fixture_graph_toy_workbench()
        result, _ = _run_mode(gs)
        # workbench_example has a Derivation section; workbench_prereq has Prerequisites.
        # Neither node is an implementation-only node in the workbench fixture.
        # The test verifies the mode runs cleanly and produces a valid result.
        assert isinstance(result, DerivationFirstResult)
        assert set(result.ordered_nodes) == {n["node_id"] for n in gs.nodes}

    def test_gap_fixture_implementation_node_is_last(self):
        """Gap fixture: gap_implementation_node (implementation-only) comes after derivation nodes."""
        gs = fixture_graph_toy_derivation_gap()
        result, _ = _run_mode(gs)
        ordered = result.ordered_nodes
        assert "gap_implementation_node" in ordered
        impl_pos = ordered.index("gap_implementation_node")
        # Both gap_derivation_node and gap_missing_node are derivation-heavy
        # (they carry derivation/prerequisites/concept sections).
        for deriv_id in ("gap_derivation_node", "gap_missing_node"):
            if deriv_id in ordered:
                deriv_pos = ordered.index(deriv_id)
                assert deriv_pos < impl_pos, (
                    f"Expected {deriv_id!r} (pos {deriv_pos}) before "
                    f"gap_implementation_node (pos {impl_pos})"
                )

    def test_executable_bridge_derivation_before_implementation(self):
        """Bridge fixture: bridge_spec (derivation) precedes bridge_artifact (implementation)."""
        gs = fixture_graph_toy_executable_bridge()
        result, _ = _run_mode(gs)
        ordered = result.ordered_nodes
        if "bridge_spec" in ordered and "bridge_artifact" in ordered:
            spec_pos = ordered.index("bridge_spec")
            artifact_pos = ordered.index("bridge_artifact")
            assert spec_pos < artifact_pos, (
                f"Expected bridge_spec (pos {spec_pos}) before "
                f"bridge_artifact (pos {artifact_pos})"
            )

    def test_all_nodes_in_output(self):
        """Every node in the slice appears exactly once in ordered_nodes."""
        for factory in (
            fixture_graph_toy_concept_kit,
            fixture_graph_toy_workbench,
            fixture_graph_toy_executable_bridge,
            fixture_graph_toy_derivation_gap,
        ):
            gs = factory()
            result, _ = _run_mode(gs)
            expected_ids = {n["node_id"] for n in gs.nodes}
            assert set(result.ordered_nodes) == expected_ids, (
                f"{factory.__name__}: ordered_nodes {result.ordered_nodes!r} "
                f"does not match slice node ids {sorted(expected_ids)}"
            )
            assert len(result.ordered_nodes) == len(expected_ids), (
                f"{factory.__name__}: duplicate ids in ordered_nodes"
            )

    def test_strategy_consistent_with_mode(self):
        """Strategy-level ordering matches mode-level ordered_nodes."""
        gs = fixture_graph_toy_derivation_gap()
        strategy_order, _ = _run_strategy(gs)
        result, _ = _run_mode(gs)
        assert strategy_order == result.ordered_nodes, (
            f"Strategy order {strategy_order} != mode order {result.ordered_nodes}"
        )

    def test_strategy_registered_under_derivation_first_key(self):
        """The 'derivation_first' key in the strategy registry returns a real strategy."""
        strategy = get_strategy("derivation_first")
        gs = fixture_graph_toy_workbench()
        ordered, warnings = strategy(gs)
        assert isinstance(ordered, list)
        assert len(ordered) == len(gs.nodes)


# ---------------------------------------------------------------------------
# Missing derivation section produces derivation_gap warning
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDerivationGapWarnings:
    """Gap nodes emit derivation_gap warning with offending node id."""

    def test_gap_fixture_emits_derivation_gap_warning(self):
        """Gap fixture: at least one derivation_gap warning is emitted."""
        gs = fixture_graph_toy_derivation_gap()
        result, warnings = _run_mode(gs)
        gap_warnings = [w for w in warnings if w.code == DERIVATION_GAP_CODE]
        assert gap_warnings, (
            f"Expected at least one {DERIVATION_GAP_CODE!r} warning; "
            f"got {[w.code for w in warnings]}"
        )

    def test_gap_warning_names_offending_node(self):
        """derivation_gap warning source_ref must be the gap node id."""
        gs = fixture_graph_toy_derivation_gap()
        result, warnings = _run_mode(gs)
        gap_warnings = [w for w in warnings if w.code == DERIVATION_GAP_CODE]
        gap_source_refs = {w.source_ref for w in gap_warnings}
        # gap_missing_node has no derivation section and is required by gap_derivation_node.
        assert "gap_missing_node" in gap_source_refs, (
            f"Expected 'gap_missing_node' in gap warning source_refs; "
            f"got {gap_source_refs}"
        )

    def test_gap_warning_source_ref_is_valid_node_id(self):
        """source_ref in every derivation_gap warning must be a known node id."""
        gs = fixture_graph_toy_derivation_gap()
        node_ids = {n["node_id"] for n in gs.nodes}
        result, warnings = _run_mode(gs)
        for w in warnings:
            if w.code == DERIVATION_GAP_CODE:
                assert w.source_ref in node_ids, (
                    f"derivation_gap warning has unknown source_ref {w.source_ref!r}; "
                    f"valid ids: {sorted(node_ids)}"
                )

    def test_gap_warning_is_learning_warning_instance(self):
        gs = fixture_graph_toy_derivation_gap()
        _, warnings = _run_mode(gs)
        gap_warnings = [w for w in warnings if w.code == DERIVATION_GAP_CODE]
        assert gap_warnings, "No gap warnings emitted."
        for w in gap_warnings:
            assert isinstance(w, LearningWarning)
            assert w.severity == "warning"

    def test_gap_derivation_node_does_not_get_gap_warning(self):
        """gap_derivation_node itself has a derivation section — no gap warning for it."""
        gs = fixture_graph_toy_derivation_gap()
        _, warnings = _run_mode(gs)
        gap_refs = {w.source_ref for w in warnings if w.code == DERIVATION_GAP_CODE}
        assert "gap_derivation_node" not in gap_refs, (
            "gap_derivation_node incorrectly received a derivation_gap warning "
            "(it has a derivation section)."
        )

    def test_implementation_node_does_not_get_gap_warning(self):
        """gap_implementation_node is not part of the derivation chain — no gap warning."""
        gs = fixture_graph_toy_derivation_gap()
        _, warnings = _run_mode(gs)
        gap_refs = {w.source_ref for w in warnings if w.code == DERIVATION_GAP_CODE}
        assert "gap_implementation_node" not in gap_refs, (
            "gap_implementation_node incorrectly received a derivation_gap warning."
        )

    def test_fully_populated_derivation_fixture_no_gap_warning(self):
        """workbench fixture: all derivation-step dependencies are satisfied — no gap warning."""
        gs = fixture_graph_toy_workbench()
        _, warnings = _run_mode(gs)
        gap_warnings = [w for w in warnings if w.code == DERIVATION_GAP_CODE]
        assert not gap_warnings, (
            f"Unexpected derivation_gap warnings on fully-populated workbench fixture: "
            f"{[(w.code, w.source_ref) for w in gap_warnings]}"
        )

    def test_concept_kit_no_spurious_gap_warnings(self):
        """concept_kit has no derivation sections — no gap warnings because no derivation steps."""
        gs = fixture_graph_toy_concept_kit()
        _, warnings = _run_mode(gs)
        gap_warnings = [w for w in warnings if w.code == DERIVATION_GAP_CODE]
        assert not gap_warnings, (
            f"Unexpected derivation_gap warnings on concept_kit fixture: "
            f"{[(w.code, w.source_ref) for w in gap_warnings]}"
        )


# ---------------------------------------------------------------------------
# Determinism across two runs
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDeterminism:
    """Two consecutive runs on the same fixture produce identical node order."""

    @pytest.mark.parametrize(
        "factory",
        [
            fixture_graph_toy_concept_kit,
            fixture_graph_toy_workbench,
            fixture_graph_toy_executable_bridge,
            fixture_graph_toy_derivation_gap,
        ],
    )
    def test_two_runs_identical_node_order(self, factory):
        """Byte-identical ordered_nodes across two calls on the same graph slice."""
        gs = factory()
        request = _make_request()
        r1, w1 = derivation_first_mode(gs, request)
        r2, w2 = derivation_first_mode(gs, request)
        assert r1.ordered_nodes == r2.ordered_nodes, (
            f"{factory.__name__}: ordered_nodes differ between runs.\n"
            f"Run 1: {r1.ordered_nodes}\nRun 2: {r2.ordered_nodes}"
        )

    @pytest.mark.parametrize(
        "factory",
        [
            fixture_graph_toy_concept_kit,
            fixture_graph_toy_workbench,
            fixture_graph_toy_executable_bridge,
            fixture_graph_toy_derivation_gap,
        ],
    )
    def test_two_runs_identical_warnings(self, factory):
        """Warning codes + source_refs are identical across two calls."""
        gs = factory()
        request = _make_request()
        _, w1 = derivation_first_mode(gs, request)
        _, w2 = derivation_first_mode(gs, request)
        w1_tuples = [(w.code, w.source_ref) for w in w1]
        w2_tuples = [(w.code, w.source_ref) for w in w2]
        assert w1_tuples == w2_tuples, (
            f"{factory.__name__}: warnings differ between runs.\n"
            f"Run 1: {w1_tuples}\nRun 2: {w2_tuples}"
        )

    @pytest.mark.parametrize(
        "factory",
        [
            fixture_graph_toy_concept_kit,
            fixture_graph_toy_workbench,
            fixture_graph_toy_executable_bridge,
            fixture_graph_toy_derivation_gap,
        ],
    )
    def test_two_runs_identical_role_views(self, factory):
        """role_views are identical across two calls."""
        gs = factory()
        request = _make_request()
        r1, _ = derivation_first_mode(gs, request)
        r2, _ = derivation_first_mode(gs, request)
        rv1 = [(v.node_id, v.role_in_lesson) for v in r1.role_views]
        rv2 = [(v.node_id, v.role_in_lesson) for v in r2.role_views]
        assert rv1 == rv2, (
            f"{factory.__name__}: role_views differ between runs.\n"
            f"Run 1: {rv1}\nRun 2: {rv2}"
        )

    def test_strategy_two_runs_identical(self):
        """Strategy-level ordering is deterministic across two calls."""
        gs = fixture_graph_toy_derivation_gap()
        o1, _ = _run_strategy(gs)
        o2, _ = _run_strategy(gs)
        assert o1 == o2, (
            f"Strategy order differs between runs:\nRun 1: {o1}\nRun 2: {o2}"
        )


# ---------------------------------------------------------------------------
# role_in_lesson is LSP-only — graph slice is not mutated
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRoleInLessonLSPOnly:
    """Role_in_lesson lives only on result struct; graph slice is unchanged."""

    @pytest.mark.parametrize(
        "factory",
        [
            fixture_graph_toy_concept_kit,
            fixture_graph_toy_workbench,
            fixture_graph_toy_executable_bridge,
            fixture_graph_toy_derivation_gap,
        ],
    )
    def test_graph_slice_not_mutated(self, factory):
        """Graph slice nodes are byte-identical before and after the mode runs."""
        gs = factory()
        nodes_before = [dict(n) for n in gs.nodes]
        edges_before = [dict(e) for e in gs.edges]

        _run_mode(gs)

        nodes_after = [dict(n) for n in gs.nodes]
        edges_after = [dict(e) for e in gs.edges]

        assert nodes_before == nodes_after, (
            f"{factory.__name__}: graph slice nodes mutated by derivation_first_mode!"
        )
        assert edges_before == edges_after, (
            f"{factory.__name__}: graph slice edges mutated by derivation_first_mode!"
        )

    @pytest.mark.parametrize(
        "factory",
        [
            fixture_graph_toy_concept_kit,
            fixture_graph_toy_workbench,
            fixture_graph_toy_executable_bridge,
            fixture_graph_toy_derivation_gap,
        ],
    )
    def test_no_role_in_lesson_on_graph_nodes(self, factory):
        """None of the raw graph node dicts contain a 'role_in_lesson' key."""
        gs = factory()
        _run_mode(gs)
        for node in gs.nodes:
            assert "role_in_lesson" not in node, (
                f"node {node.get('node_id')!r} has 'role_in_lesson' in graph dict — "
                f"this field must stay in the LSP only."
            )

    def test_role_views_on_result_not_graph(self):
        """role_views are on DerivationFirstResult, not on graph node dicts."""
        gs = fixture_graph_toy_derivation_gap()
        result, _ = _run_mode(gs)
        # Result carries role views.
        assert result.role_views, "Expected non-empty role_views on result."
        for rv in result.role_views:
            assert isinstance(rv, NodeLessonRoleView)
            assert rv.role_in_lesson in (
                "assumption",
                "definition",
                "derivation_step",
                "result",
                "gap",
            )
        # Graph nodes carry no role info.
        for node in gs.nodes:
            assert "role_in_lesson" not in node

    def test_role_views_cover_all_ordered_nodes(self):
        """One role_view per ordered_node, in the same order."""
        gs = fixture_graph_toy_derivation_gap()
        result, _ = _run_mode(gs)
        assert len(result.role_views) == len(result.ordered_nodes), (
            f"role_views length {len(result.role_views)} != "
            f"ordered_nodes length {len(result.ordered_nodes)}"
        )
        for rv, nid in zip(result.role_views, result.ordered_nodes):
            assert rv.node_id == nid, (
                f"role_view.node_id {rv.node_id!r} != ordered_nodes entry {nid!r}"
            )


# ---------------------------------------------------------------------------
# Role classification
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRoleClassification:
    """role_in_lesson values are assigned correctly per documented heuristics."""

    def test_gap_node_gets_gap_role(self):
        """gap_missing_node must get role='gap' in the gap fixture."""
        gs = fixture_graph_toy_derivation_gap()
        result, _ = _run_mode(gs)
        roles = {rv.node_id: rv.role_in_lesson for rv in result.role_views}
        assert roles.get("gap_missing_node") == "gap", (
            f"gap_missing_node should have role='gap', got {roles.get('gap_missing_node')!r}"
        )

    def test_derivation_node_gets_derivation_step_role(self):
        """gap_derivation_node (has derivation section) must get role='derivation_step'."""
        gs = fixture_graph_toy_derivation_gap()
        result, _ = _run_mode(gs)
        roles = {rv.node_id: rv.role_in_lesson for rv in result.role_views}
        assert roles.get("gap_derivation_node") == "derivation_step", (
            f"gap_derivation_node should have role='derivation_step', "
            f"got {roles.get('gap_derivation_node')!r}"
        )

    def test_implementation_node_gets_result_role(self):
        """gap_implementation_node (implementation-only) gets role='result'."""
        gs = fixture_graph_toy_derivation_gap()
        result, _ = _run_mode(gs)
        roles = {rv.node_id: rv.role_in_lesson for rv in result.role_views}
        assert roles.get("gap_implementation_node") == "result", (
            f"gap_implementation_node should have role='result', "
            f"got {roles.get('gap_implementation_node')!r}"
        )

    def test_workbench_prereq_gets_assumption_role(self):
        """workbench_prereq carries a Prerequisites section → role='assumption'."""
        gs = fixture_graph_toy_workbench()
        result, _ = _run_mode(gs)
        roles = {rv.node_id: rv.role_in_lesson for rv in result.role_views}
        assert roles.get("workbench_prereq") == "assumption", (
            f"workbench_prereq should have role='assumption', "
            f"got {roles.get('workbench_prereq')!r}"
        )

    def test_workbench_example_gets_derivation_step_role(self):
        """workbench_example carries a Derivation section → role='derivation_step'."""
        gs = fixture_graph_toy_workbench()
        result, _ = _run_mode(gs)
        roles = {rv.node_id: rv.role_in_lesson for rv in result.role_views}
        assert roles.get("workbench_example") == "derivation_step", (
            f"workbench_example should have role='derivation_step', "
            f"got {roles.get('workbench_example')!r}"
        )

    def test_all_roles_are_valid_literals(self):
        """Every role_in_lesson value is one of the five documented roles."""
        valid_roles = {"assumption", "definition", "derivation_step", "result", "gap"}
        for factory in (
            fixture_graph_toy_concept_kit,
            fixture_graph_toy_workbench,
            fixture_graph_toy_executable_bridge,
            fixture_graph_toy_derivation_gap,
        ):
            gs = factory()
            result, _ = _run_mode(gs)
            for rv in result.role_views:
                assert rv.role_in_lesson in valid_roles, (
                    f"{factory.__name__}: node {rv.node_id!r} has invalid "
                    f"role_in_lesson {rv.role_in_lesson!r}"
                )


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResultStructure:
    """DerivationFirstResult has the expected attributes."""

    def test_result_is_derivation_first_result_instance(self):
        gs = fixture_graph_toy_workbench()
        result, _ = _run_mode(gs)
        assert isinstance(result, DerivationFirstResult)

    def test_result_carries_source_node_ids(self):
        gs = fixture_graph_toy_workbench()
        result, _ = _run_mode(gs)
        node_ids_in_slice = {n["node_id"] for n in gs.nodes}
        for nid in result.source_node_ids:
            assert nid in node_ids_in_slice, (
                f"result.source_node_ids contains unknown id {nid!r}"
            )

    def test_result_carries_edge_ids(self):
        gs = fixture_graph_toy_workbench()
        result, _ = _run_mode(gs)
        edge_ids_in_slice = {e["edge_id"] for e in gs.edges}
        for eid in result.edge_ids:
            assert eid in edge_ids_in_slice, (
                f"result.edge_ids contains unknown id {eid!r}"
            )

    def test_source_node_ids_sorted(self):
        """source_node_ids must be in sorted order."""
        gs = fixture_graph_toy_workbench()
        result, _ = _run_mode(gs)
        assert result.source_node_ids == sorted(result.source_node_ids)

    def test_edge_ids_sorted(self):
        """edge_ids must be in sorted order."""
        gs = fixture_graph_toy_workbench()
        result, _ = _run_mode(gs)
        assert result.edge_ids == sorted(result.edge_ids)

    def test_warnings_are_learning_warning_instances(self):
        gs = fixture_graph_toy_derivation_gap()
        result, warnings = _run_mode(gs)
        for w in warnings:
            assert isinstance(w, LearningWarning)

    def test_result_warnings_same_list_as_returned_warnings(self):
        """result.warnings and the returned warnings list are the same object."""
        gs = fixture_graph_toy_workbench()
        result, warnings = _run_mode(gs)
        assert result.warnings is warnings


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConstants:
    """Module-level constants are correct."""

    def test_derivation_heavy_headings_are_subset_of_approved(self):
        from akms_learn.section_extraction import APPROVED_HEADINGS

        for h in DERIVATION_HEAVY_HEADINGS:
            assert h in APPROVED_HEADINGS, (
                f"DERIVATION_HEAVY_HEADINGS contains {h!r} which is not "
                f"in APPROVED_HEADINGS"
            )

    def test_implementation_headings_are_subset_of_approved(self):
        from akms_learn.section_extraction import APPROVED_HEADINGS

        for h in IMPLEMENTATION_HEADINGS:
            assert h in APPROVED_HEADINGS, (
                f"IMPLEMENTATION_HEADINGS contains {h!r} which is not "
                f"in APPROVED_HEADINGS"
            )

    def test_derivation_gap_code_is_stable_string(self):
        assert DERIVATION_GAP_CODE == "derivation_gap"

    def test_disjoint_heavy_and_implementation_headings(self):
        """derivation-heavy and implementation heading sets are disjoint."""
        overlap = DERIVATION_HEAVY_HEADINGS & IMPLEMENTATION_HEADINGS
        assert not overlap, (
            f"DERIVATION_HEAVY_HEADINGS and IMPLEMENTATION_HEADINGS overlap: {overlap}"
        )


# ---------------------------------------------------------------------------
# LLM-free import guard
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_derivation_first_no_llm_imports():
    """The mode module source must not reference any LLM SDK.

    Reads the source file and asserts the canonical LLM client module
    names are absent. ``sys.modules`` membership is unreliable here —
    another test in the run may have imported one of those SDKs for an
    unrelated reason — so the check is source-level instead.
    """
    import importlib
    from pathlib import Path

    mod = importlib.import_module("akms_learn.modes.derivation_first")
    src_path = Path(getattr(mod, "__file__", "") or "")
    assert src_path.is_file(), "derivation_first module has no resolvable __file__"
    source = src_path.read_text(encoding="utf-8")
    for name in ("anthropic", "openai", "cohere", "langchain"):
        forbidden = (f"import {name}", f"from {name}")
        for token in forbidden:
            assert token not in source, (
                f"LLM SDK {name!r} appears in derivation_first source via "
                f"{token!r} — mode must remain LLM-free."
            )


# ---------------------------------------------------------------------------
# NodeLessonRoleView sidecar
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNodeLessonRoleView:
    """NodeLessonRoleView is a frozen dataclass with the right fields."""

    def test_frozen_dataclass(self):
        rv = NodeLessonRoleView(node_id="abc", role_in_lesson="assumption")
        with pytest.raises((AttributeError, TypeError)):
            rv.node_id = "changed"  # type: ignore[misc]

    def test_equality(self):
        rv1 = NodeLessonRoleView(node_id="abc", role_in_lesson="derivation_step")
        rv2 = NodeLessonRoleView(node_id="abc", role_in_lesson="derivation_step")
        assert rv1 == rv2

    def test_all_valid_roles(self):
        for role in ("assumption", "definition", "derivation_step", "result", "gap"):
            rv = NodeLessonRoleView(node_id="n1", role_in_lesson=role)  # type: ignore[arg-type]
            assert rv.role_in_lesson == role
