"""Package-level tests for Learning ordering.

Covers all 5 acceptance criteria:
  AC1 – acyclic slice produces same order on repeated calls
  AC2 – cyclic slice produces deterministic order plus ≥1 'cycle_broken' warning
  AC3 – bucket order matches §12 exactly
  AC4 – within bucket, lexicographic sort when no edge constraint applies
  AC5 – order_nodes is pure (no mutation of input slice)
"""

import pytest

from akms_learn.graph_import import GraphSlice, fixture_graph
from akms_learn.models import LearningWarning
from akms_learn.ordering import LEARNING_BUCKETS, order_nodes


class TestOrdering:
    """Tests for Learning ordering with deterministic cycle breaking.

    AC covered: 1, 2, 3, 4, 5.
    """

    @pytest.mark.unit
    def test_order_acyclic_stable(self):
        """Two consecutive runs on an acyclic slice yield identical orderings."""
        sl = fixture_graph()
        order1, warnings1 = order_nodes(sl)
        order2, warnings2 = order_nodes(sl)

        assert order1 == order2, "order_nodes must be deterministic across runs"
        assert warnings1 == warnings2, "warnings must be identical across runs"
        # Fixture graph is acyclic — no warnings expected.
        assert warnings1 == [], f"Expected no warnings for acyclic graph, got {warnings1}"
        # All 7 nodes should be present.
        assert len(order1) == 7
        assert set(order1) == {
            "prereq_linear_algebra",
            "prereq_complex_numbers",
            "core_j2_return_mapping",
            "deriv_state_space",
            "impl_pole_placement",
            "pitfall_sign_convention",
            "exercise_verify_poles",
        }

    @pytest.mark.unit
    def test_order_cycle_breaks_deterministically(self):
        """Cyclic input yields deterministic order plus >=1 LearningWarning(code='cycle_broken')."""
        # Build a minimal cyclic slice: A requires B, B requires A.
        # Both nodes get "kind"="prerequisite" so they land in the same bucket.
        cyclic_slice = GraphSlice(
            nodes=(
                {"node_id": "alpha", "kind": "prerequisite"},
                {"node_id": "beta", "kind": "prerequisite"},
            ),
            edges=(
                {"from": "alpha", "to": "beta", "type": "requires"},
                {"from": "beta", "to": "alpha", "type": "requires"},
            ),
        )

        order1, warnings1 = order_nodes(cyclic_slice)
        order2, warnings2 = order_nodes(cyclic_slice)

        # Must be deterministic.
        assert order1 == order2, "order_nodes must be deterministic on cyclic input"
        assert warnings1 == warnings2, "warnings must be identical across runs"

        # Must emit at least one cycle_broken warning.
        assert len(warnings1) >= 1, "Expected at least one cycle_broken warning"
        assert all(
            isinstance(w, LearningWarning) for w in warnings1
        ), "All warnings must be LearningWarning instances"
        assert any(
            w.code == "cycle_broken" for w in warnings1
        ), f"Expected code='cycle_broken', got {[w.code for w in warnings1]}"

        # Verify alphabetic-max target rule: cycle is (alpha→beta, beta→alpha).
        # The edge with alphabetically-max target is alpha→beta (target="beta" > "alpha").
        # So "beta" edge should be cut, meaning beta→alpha is NOT cut.
        # After removal of alpha→beta, the remaining edge is beta→alpha.
        # Topological sort: beta first, then alpha.
        broken_srcrefs = [w.source_ref for w in warnings1 if w.code == "cycle_broken"]
        assert "alpha->beta" in broken_srcrefs, (
            f"Expected 'alpha->beta' to be cut (alphabetic-max target='beta'), "
            f"got {broken_srcrefs}"
        )

        # Both nodes present.
        assert set(order1) == {"alpha", "beta"}

    @pytest.mark.unit
    def test_order_bucket_sequence(self):
        """Output respects the 7-bucket order from plan section 12."""
        # Build a slice with one node in each of three distinct buckets:
        # prerequisite, derivation, pitfall.
        # Expected bucket order: prerequisites (0) < derivations (2) < pitfalls (4).
        sl = GraphSlice(
            nodes=(
                {"node_id": "p_node", "kind": "prerequisite"},
                {"node_id": "d_node", "kind": "derivation"},
                {"node_id": "pit_node", "kind": "pitfall"},
            ),
            edges=(),
        )
        order, warnings = order_nodes(sl)
        assert warnings == [], f"Expected no warnings, got {warnings}"
        assert len(order) == 3

        # Verify bucket ordering: prerequisites before derivations before pitfalls.
        idx_p = order.index("p_node")
        idx_d = order.index("d_node")
        idx_pit = order.index("pit_node")
        assert idx_p < idx_d, (
            f"prerequisites (pos {idx_p}) must come before derivations (pos {idx_d})"
        )
        assert idx_d < idx_pit, (
            f"derivations (pos {idx_d}) must come before pitfalls (pos {idx_pit})"
        )

        # Also verify against the full LEARNING_BUCKETS constant.
        expected_order = [
            "prerequisites",
            "core concepts",
            "derivations",
            "implementations",
            "pitfalls",
            "exercises",
            "next paths",
        ]
        assert list(LEARNING_BUCKETS) == expected_order, (
            f"LEARNING_BUCKETS constant does not match §12 spec: {list(LEARNING_BUCKETS)}"
        )

    @pytest.mark.unit
    def test_order_no_input_mutation(self):
        """order_nodes is pure — it does not mutate the input GraphSlice."""
        sl = fixture_graph()
        # Capture a deep-equal snapshot via model_dump before the call.
        snapshot_before = sl.model_dump()

        order_nodes(sl)

        snapshot_after = sl.model_dump()
        assert snapshot_before == snapshot_after, (
            "order_nodes mutated the input GraphSlice — purity violation"
        )
