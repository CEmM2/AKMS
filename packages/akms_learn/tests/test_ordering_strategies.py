"""Tests for Mode-specific ordering strategy framework.

Covers all four acceptance criteria:
  registry exposes the six required strategy keys
         (default + pedagogical_template + derivation_first
          + implementation_first + multi_granularity + pitfall_driven).
  looking up an unregistered key raises a clear ValueError
         (no silent fallback to default).
  the 'default' strategy reproduces the canonical ordering byte-for-byte
         on the fixture graph.
  Phase-1 stub strategies (pedagogical / derivation / implementation
         / multi_granularity) currently behave identically to default and
         carry an override-contract docstring.

Spec refs:
    the internal plan
    the akms-learn internal specification (not published)
    the akms-learn internal specification (not published)
"""

from __future__ import annotations

import pytest

from akms_learn.graph_import import GraphSlice, fixture_graph
from akms_learn.ordering import (
    STRATEGY_KEYS,
    OrderingStrategy,
    get_strategy,
    list_strategies,
    order_nodes,
)


REQUIRED_MODE_KEYS: frozenset[str] = frozenset(
    {
        "default",
        "pedagogical_template",
        "derivation_first",
        "implementation_first",
        "multi_granularity",
        "pitfall_driven",
        # Notebook source compiler mode.
        "notebook_source",
        # Adaptive path compiler mode.
        "adaptive_path",
        # Assessment-first compiler mode.
        "assessment_first",
        # llm_expanded compiler mode.
        "llm_expanded",
    }
)


class TestRegistryShape:
    """required keys are present and resolvable to callables."""

    @pytest.mark.unit
    def test_registry_exposes_six_required_keys(self):
        keys = set(list_strategies())
        assert keys == REQUIRED_MODE_KEYS, (
            f"Registry keys mismatch.\n"
            f"  expected: {sorted(REQUIRED_MODE_KEYS)}\n"
            f"  got:      {sorted(keys)}"
        )
        # STRATEGY_KEYS constant must match list_strategies() return shape.
        assert set(STRATEGY_KEYS) == REQUIRED_MODE_KEYS

    @pytest.mark.unit
    def test_every_key_resolves_to_callable(self):
        for mode in REQUIRED_MODE_KEYS:
            fn = get_strategy(mode)
            assert callable(fn), f"strategy for {mode!r} is not callable"

    @pytest.mark.unit
    def test_strategy_keys_declaration_order_is_stable(self):
        #   # Determinism: two consecutive reads of the registry surface must yield
        #           # the same key order.
        first = tuple(list_strategies())
        second = tuple(list_strategies())
        assert first == second
        assert first == STRATEGY_KEYS


class TestUnknownModeKeyRaises:
    """no silent fallback to default on unknown keys."""

    @pytest.mark.unit
    def test_unknown_key_raises_value_error(self):
        with pytest.raises(ValueError) as exc:
            get_strategy("not_a_real_mode")
        message = str(exc.value)
        assert "not_a_real_mode" in message
        # The error must enumerate available keys so callers can recover.
        for key in REQUIRED_MODE_KEYS:
            assert key in message, (
                f"Error message must list registered key {key!r}; got: {message!r}"
            )

    @pytest.mark.unit
    def test_unknown_key_does_not_silently_return_default(self):
        # Defense in depth: even though Python's `dict` would raise KeyError
        # on missing keys, future refactors might add a `.get()` with default.
        # Assert that we receive ValueError (not the default callable).
        with pytest.raises(ValueError):
            get_strategy("")
        with pytest.raises(ValueError):
            get_strategy("DEFAULT")  # case-sensitive lookup, per spec


class TestDefaultStrategyMatchesCanonicalOrdering:
    """'default' strategy reproduces the canonical ordering byte-for-byte."""

    @pytest.mark.unit
    def test_default_strategy_matches_order_nodes_on_fixture(self):
        slice_ = fixture_graph()
        ordered_via_strategy, warnings_via_strategy = get_strategy("default")(slice_)
        ordered_via_plan1, warnings_via_plan1 = order_nodes(slice_)
        assert ordered_via_strategy == ordered_via_plan1
        assert warnings_via_strategy == warnings_via_plan1

    @pytest.mark.unit
    def test_default_strategy_byte_stable_across_runs(self):
        slice_ = fixture_graph()
        fn = get_strategy("default")
        first = fn(slice_)
        second = fn(slice_)
        assert first == second


class TestStubStrategiesFallThroughToDefault:
    """Phase-1 stubs delegate to default and document the contract.

    Note: ``derivation_first`` is no longer a stub — it was implemented in
    Phase 2 and intentionally diverges from the default ordering.
    ``implementation_first`` is also live and diverges from the
    default ordering. Both are excluded from STUB_KEYS but covered by
    ``TestLiveDerivationFirstStrategy`` / ``TestLiveImplementationFirstStrategy``.
    """

    STUB_KEYS = (
        "pedagogical_template",
        "multi_granularity",
    )

    @pytest.mark.unit
    @pytest.mark.parametrize("mode", STUB_KEYS)
    def test_stub_strategy_equals_default_on_fixture(self, mode: str):
        slice_ = fixture_graph()
        stub_order, stub_warnings = get_strategy(mode)(slice_)
        default_order, default_warnings = get_strategy("default")(slice_)
        assert stub_order == default_order, (
            f"Stub strategy {mode!r} diverged from default ordering."
        )
        assert stub_warnings == default_warnings

    @pytest.mark.unit
    @pytest.mark.parametrize("mode", STUB_KEYS)
    def test_stub_strategy_carries_override_contract_docstring(self, mode: str):
        fn = get_strategy(mode)
        doc = (fn.__doc__ or "").lower()
        assert "override contract" in doc, (
            f"Stub strategy {mode!r} must document its override contract; "
            f"docstring lacks the phrase 'override contract'."
        )


class TestLiveDerivationFirstStrategy:
    """derivation_first is a live strategy, no longer a stub."""

    @pytest.mark.unit
    def test_derivation_first_is_callable(self):
        fn = get_strategy("derivation_first")
        assert callable(fn)

    @pytest.mark.unit
    def test_derivation_first_carries_override_contract_docstring(self):
        fn = get_strategy("derivation_first")
        doc = (fn.__doc__ or "").lower()
        assert "override contract" in doc, (
            "derivation_first strategy must document its override contract; "
            "docstring lacks the phrase 'override contract'."
        )

    @pytest.mark.unit
    def test_derivation_first_is_deterministic(self):
        slice_ = fixture_graph()
        fn = get_strategy("derivation_first")
        first_order, first_warnings = fn(slice_)
        second_order, second_warnings = fn(slice_)
        assert first_order == second_order
        assert [(w.code, w.source_ref) for w in first_warnings] == [
            (w.code, w.source_ref) for w in second_warnings
        ]

    @pytest.mark.unit
    def test_derivation_first_returns_all_nodes(self):
        slice_ = fixture_graph()
        fn = get_strategy("derivation_first")
        ordered, _ = fn(slice_)
        expected_ids = {n.get("node_id") or n.get("id") for n in slice_.nodes}
        expected_ids.discard(None)
        assert set(ordered) == expected_ids


class TestLiveImplementationFirstStrategy:
    """implementation_first is a live strategy, no longer a stub."""

    @pytest.mark.unit
    def test_implementation_first_is_callable(self):
        fn = get_strategy("implementation_first")
        assert callable(fn)

    @pytest.mark.unit
    def test_implementation_first_carries_override_contract_docstring(self):
        fn = get_strategy("implementation_first")
        doc = (fn.__doc__ or "").lower()
        assert "override contract" in doc, (
            "implementation_first strategy must document its override contract; "
            "docstring lacks the phrase 'override contract'."
        )

    @pytest.mark.unit
    def test_implementation_first_is_deterministic(self):
        slice_ = fixture_graph()
        fn = get_strategy("implementation_first")
        first_order, first_warnings = fn(slice_)
        second_order, second_warnings = fn(slice_)
        assert first_order == second_order
        assert [(w.code, w.source_ref) for w in first_warnings] == [
            (w.code, w.source_ref) for w in second_warnings
        ]

    @pytest.mark.unit
    def test_implementation_first_returns_all_nodes(self):
        slice_ = fixture_graph()
        fn = get_strategy("implementation_first")
        ordered, _ = fn(slice_)
        expected_ids = {n.get("node_id") or n.get("id") for n in slice_.nodes}
        expected_ids.discard(None)
        assert set(ordered) == expected_ids


class TestPitfallDrivenPreserved:
    """Canary — pitfall_driven must keep its existing behaviour."""

    @pytest.mark.unit
    def test_pitfall_driven_matches_plan1_on_fixture(self):
        slice_ = fixture_graph()
        pitfall_order, pitfall_warnings = get_strategy("pitfall_driven")(slice_)
        plan1_order, plan1_warnings = order_nodes(slice_)
        assert pitfall_order == plan1_order
        assert pitfall_warnings == plan1_warnings

    @pytest.mark.unit
    def test_pitfall_driven_byte_stable_across_runs(self):
        slice_ = fixture_graph()
        fn = get_strategy("pitfall_driven")
        first = fn(slice_)
        second = fn(slice_)
        assert first == second

    @pytest.mark.unit
    def test_pitfall_driven_handles_cyclic_input(self):
        #   # Mirror of the default-ordering canary: pitfall_driven must still break
        #           # cycles via the alphabetic-max-target rule.
        cyclic = GraphSlice(
            nodes=(
                {"node_id": "alpha", "kind": "prerequisite"},
                {"node_id": "beta", "kind": "prerequisite"},
            ),
            edges=(
                {"from": "alpha", "to": "beta", "type": "requires"},
                {"from": "beta", "to": "alpha", "type": "requires"},
            ),
        )
        order_pf, warnings_pf = get_strategy("pitfall_driven")(cyclic)
        order_pl1, warnings_pl1 = order_nodes(cyclic)
        assert order_pf == order_pl1
        assert warnings_pf == warnings_pl1


class TestStrategyTypeContract:
    """The :data:`OrderingStrategy` alias is the documented public contract."""

    @pytest.mark.unit
    def test_ordering_strategy_alias_is_importable(self):
        # Trivial smoke-check that the alias is exposed for type hints.
        assert OrderingStrategy is not None
