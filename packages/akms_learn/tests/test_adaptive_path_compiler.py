"""Tests for adaptive_path compiler mode.

Covers all five acceptance criteria:

LearnerProfile model exposes knows/weak/goals/conservative_mode with
      conservative_mode defaulting True.
With conservative_mode=True, no prerequisite node is skipped under any input.
With conservative_mode=False, every skipped node is recorded in
      provenance.skipped_prerequisites with reason.
Unmatched learner claims emit warnings to packet.warnings
      (id + claim text + claim type).
Two runs with the same LearnerProfile + graph produce byte-identical packets.

Additional tests:
  - adaptive_summary surfaces personalisation decisions.
  - Compiler raises PreconditionError when the ``llm`` extra is absent.
  - Strategy registered as ``"adaptive_path"`` in ordering registry.
  - Plugin reports ``"adaptive_path"`` capability.
  - Conservative-mode fuzz: various ``knows`` lists (including full coverage)
    never result in skipped nodes.
  - Deterministic ordering: lesson_body keys always sorted.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest

import akms_learn.capability_gates as _cap_gates
from akms_learn.capability_gates import CapabilityGate, PreconditionError
from akms_learn.graph_import import GraphSlice
from akms_learn.models.learner_profile import LearnerProfile
from akms_learn.modes.adaptive_path import AdaptivePathResult, adaptive_path_mode
from akms_learn.ordering import get_strategy, list_strategies
from akms_learn.toy_fixtures import fixture_graph_toy_concept_kit
from akms_learn.plugin import get_plugin
from akms_learn.requests import LearningRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(
    profile: LearnerProfile | None = None,
    **overrides: Any,
) -> LearningRequest:
    defaults: dict[str, Any] = dict(
        topic="toy adaptive path",
        goal="Learn the adaptive path mode end-to-end.",
        audience="engineer",
        depth="implementation",
        generation_option="adaptive_path",
        seed_tags=[],
        exporters=[],
        learner_profile=profile,
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


@contextmanager
def _gate_open():
    """Patch probe_optional_extras so the ``llm`` extra appears installed.

    The ``llm`` extra uses ``None`` as its probe package (intentionally always
    absent), so patching ``find_spec`` is insufficient.  Instead we patch
    ``probe_optional_extras`` to return ``llm: True`` while preserving the
    real results for other extras.
    """
    original_probe = _cap_gates.probe_optional_extras

    def _patched_probe() -> dict[str, bool]:
        result = original_probe()
        result["llm"] = True
        return result

    with patch.object(_cap_gates, "probe_optional_extras", side_effect=_patched_probe):
        yield


def _simple_graph_with_prereqs() -> tuple[GraphSlice, list[str]]:
    """Return a tiny three-node graph with ``requires`` edges.

    Topology::

        prereq_a  ──requires──►  prereq_b  ──requires──►  target_c

    All three nodes are returned as ordered_nodes (prereq_a, prereq_b,
    target_c).  prereq_a and prereq_b carry distinct tags so they can be
    covered by a ``knows`` list.
    """
    nodes = [
        {
            "node_id": "prereq_a",
            "title": "Prerequisite A",
            "kind": "prerequisite",
            "domain": "toy",
            "subdomain": "sub",
            "tags": ["tag_a", "tag_x"],
            "status": "established",
            "source_path": "toy://a.md",
            "line_range": [1, 5],
        },
        {
            "node_id": "prereq_b",
            "title": "Prerequisite B",
            "kind": "prerequisite",
            "domain": "toy",
            "subdomain": "sub",
            "tags": ["tag_b", "tag_y"],
            "status": "established",
            "source_path": "toy://b.md",
            "line_range": [1, 5],
        },
        {
            "node_id": "target_c",
            "title": "Target C",
            "kind": "core_concept",
            "domain": "toy",
            "subdomain": "sub",
            "tags": ["tag_c"],
            "status": "established",
            "source_path": "toy://c.md",
            "line_range": [1, 10],
        },
    ]
    edges = [
        {
            "edge_id": "e_a_b",
            "from": "prereq_a",
            "to": "prereq_b",
            "type": "requires",
            "source_path": "toy://edges.md",
            "line_range": [1, 1],
        },
        {
            "edge_id": "e_b_c",
            "from": "prereq_b",
            "to": "target_c",
            "type": "requires",
            "source_path": "toy://edges.md",
            "line_range": [2, 2],
        },
    ]
    graph = GraphSlice(nodes=tuple(nodes), edges=tuple(edges), metadata={})
    ordered = ["prereq_a", "prereq_b", "target_c"]
    return graph, ordered


# ---------------------------------------------------------------------------
# LearnerProfile model
# ---------------------------------------------------------------------------


class TestLearnerProfileModel:
    """LearnerProfile exposes knows/weak/goals/conservative_mode."""

    @pytest.mark.unit
    def test_defaults(self):
        """Default LearnerProfile has empty tuples and conservative_mode=True."""
        lp = LearnerProfile()
        assert lp.knows == ()
        assert lp.weak == ()
        assert lp.goals == ()
        assert lp.conservative_mode is True

    @pytest.mark.unit
    def test_custom_values(self):
        """All four fields can be set and are accessible."""
        lp = LearnerProfile(
            knows=("alpha", "beta"),
            weak=("gamma",),
            goals=("understand_delta",),
            conservative_mode=False,
        )
        assert lp.knows == ("alpha", "beta")
        assert lp.weak == ("gamma",)
        assert lp.goals == ("understand_delta",)
        assert lp.conservative_mode is False

    @pytest.mark.unit
    def test_frozen(self):
        """LearnerProfile is frozen — mutation raises an error."""
        lp = LearnerProfile()
        with pytest.raises(Exception):
            lp.conservative_mode = False  # type: ignore[misc]

    @pytest.mark.unit
    def test_request_field_excluded_from_normalized_fields(self):
        """learner_profile is not in NORMALIZED_FIELDS (excluded from hash)."""
        from akms_learn.requests import NORMALIZED_FIELDS

        assert "learner_profile" not in NORMALIZED_FIELDS

    @pytest.mark.unit
    def test_two_requests_same_hash_different_profiles(self):
        """Requests differing only in learner_profile produce the same hash."""
        from akms_learn.requests import normalize_request, request_hash

        req1 = _make_request(profile=None)
        req2 = _make_request(
            profile=LearnerProfile(knows=("alpha",), conservative_mode=False)
        )
        assert request_hash(normalize_request(req1)) == request_hash(
            normalize_request(req2)
        )


# ---------------------------------------------------------------------------
# conservative_mode=True skips nothing
# ---------------------------------------------------------------------------


class TestConservativeModeSkipsNothing:
    """Conservative_mode=True never skips any prerequisite."""

    @pytest.mark.unit
    def test_conservative_default_includes_all_nodes(self):
        """Default profile (conservative=True) includes all nodes."""
        graph, ordered = _simple_graph_with_prereqs()
        req = _make_request(profile=LearnerProfile())
        with _gate_open():
            result, warnings = adaptive_path_mode(graph, ordered, req)
        assert result.provenance_skipped == []
        assert set(result.active_nodes) == {"prereq_a", "prereq_b", "target_c"}

    @pytest.mark.unit
    def test_conservative_true_explicit_full_knows(self):
        """conservative=True + knows covers every node → still skips nothing."""
        graph, ordered = _simple_graph_with_prereqs()
        # knows covers all tags of prereq_a and prereq_b
        profile = LearnerProfile(
            knows=("tag_a", "tag_x", "tag_b", "tag_y", "tag_c"),
            conservative_mode=True,
        )
        req = _make_request(profile=profile)
        with _gate_open():
            result, _ = adaptive_path_mode(graph, ordered, req)
        assert result.provenance_skipped == []
        assert len(result.active_nodes) == 3

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "knows",
        [
            (),
            ("tag_a",),
            ("tag_a", "tag_x"),
            ("tag_a", "tag_x", "tag_b", "tag_y"),
            ("tag_a", "tag_x", "tag_b", "tag_y", "tag_c"),
            ("prereq_a",),
            ("prereq_a", "prereq_b"),
            ("prereq_a", "prereq_b", "target_c"),
        ],
    )
    def test_conservative_mode_fuzz(self, knows):
        """Fuzz: any knows list with conservative=True produces zero skips."""
        graph, ordered = _simple_graph_with_prereqs()
        profile = LearnerProfile(knows=knows, conservative_mode=True)
        req = _make_request(profile=profile)
        with _gate_open():
            result, _ = adaptive_path_mode(graph, ordered, req)
        assert result.provenance_skipped == [], (
            f"Expected zero skips with conservative=True, knows={knows!r}; "
            f"got skipped={result.provenance_skipped}"
        )


# ---------------------------------------------------------------------------
# conservative_mode=False records skipped nodes in provenance
# ---------------------------------------------------------------------------


class TestExplicitSkipMode:
    """Conservative_mode=False with covered prereq → provenance recorded."""

    @pytest.mark.unit
    def test_skip_by_node_id(self):
        """A node whose node_id appears in knows is skipped and recorded."""
        graph, ordered = _simple_graph_with_prereqs()
        profile = LearnerProfile(knows=("prereq_a",), conservative_mode=False)
        req = _make_request(profile=profile)
        with _gate_open():
            result, _ = adaptive_path_mode(graph, ordered, req)

        skipped_ids = {r["node_id"] for r in result.provenance_skipped}
        assert "prereq_a" in skipped_ids
        # target_c not fully covered
        assert "target_c" not in skipped_ids

    @pytest.mark.unit
    def test_skip_by_all_tags(self):
        """A node whose ALL tags are in knows is skipped."""
        graph, ordered = _simple_graph_with_prereqs()
        # prereq_a has tags: tag_a, tag_x — both in knows
        profile = LearnerProfile(knows=("tag_a", "tag_x"), conservative_mode=False)
        req = _make_request(profile=profile)
        with _gate_open():
            result, _ = adaptive_path_mode(graph, ordered, req)

        skipped_ids = {r["node_id"] for r in result.provenance_skipped}
        assert "prereq_a" in skipped_ids

    @pytest.mark.unit
    def test_partial_tag_coverage_not_skipped(self):
        """A node with only SOME tags in knows is NOT skipped."""
        graph, ordered = _simple_graph_with_prereqs()
        # prereq_a has tags: tag_a, tag_x — only tag_a in knows
        profile = LearnerProfile(knows=("tag_a",), conservative_mode=False)
        req = _make_request(profile=profile)
        with _gate_open():
            result, _ = adaptive_path_mode(graph, ordered, req)

        skipped_ids = {r["node_id"] for r in result.provenance_skipped}
        assert "prereq_a" not in skipped_ids

    @pytest.mark.unit
    def test_provenance_record_has_required_fields(self):
        """Each provenance_skipped record has node_id, reason, source."""
        graph, ordered = _simple_graph_with_prereqs()
        profile = LearnerProfile(knows=("prereq_a",), conservative_mode=False)
        req = _make_request(profile=profile)
        with _gate_open():
            result, _ = adaptive_path_mode(graph, ordered, req)

        assert len(result.provenance_skipped) >= 1
        for record in result.provenance_skipped:
            assert "node_id" in record
            assert "reason" in record
            assert "source" in record
            assert record["reason"] == "covered_by_knows"

    @pytest.mark.unit
    def test_skipped_node_not_in_active_nodes(self):
        """Skipped nodes are removed from active_nodes but NOT deleted from graph."""
        graph, ordered = _simple_graph_with_prereqs()
        profile = LearnerProfile(knows=("prereq_a",), conservative_mode=False)
        req = _make_request(profile=profile)
        with _gate_open():
            result, _ = adaptive_path_mode(graph, ordered, req)

        assert "prereq_a" not in result.active_nodes
        # Graph slice is never mutated — original nodes intact
        node_ids_in_graph = {n.get("node_id") for n in graph.nodes}
        assert "prereq_a" in node_ids_in_graph

    @pytest.mark.unit
    def test_provenance_source_edge_id(self):
        """Provenance source is the requires edge id pointing at the skipped node."""
        graph, ordered = _simple_graph_with_prereqs()
        # prereq_b is pointed at by e_b_c — skip prereq_b
        profile = LearnerProfile(knows=("prereq_b",), conservative_mode=False)
        req = _make_request(profile=profile)
        with _gate_open():
            result, _ = adaptive_path_mode(graph, ordered, req)

        skipped = {r["node_id"]: r for r in result.provenance_skipped}
        assert "prereq_b" in skipped
        # e_b_c is the requires edge with to=prereq_b (edge from prereq_b to target_c is not it)
        # Actually prereq_b is TO node in e_a_b (from=prereq_a, to=prereq_b)
        # _find_source_edge looks for edges where type=requires and to=node_id
        assert skipped["prereq_b"]["source"] == "e_a_b"

    @pytest.mark.unit
    def test_skip_by_direct_claim_no_edge(self):
        """When a node has no incoming requires edge, source is the fallback sentinel."""
        graph, ordered = _simple_graph_with_prereqs()
        # prereq_a has no incoming requires edge in our fixture
        profile = LearnerProfile(knows=("prereq_a",), conservative_mode=False)
        req = _make_request(profile=profile)
        with _gate_open():
            result, _ = adaptive_path_mode(graph, ordered, req)

        skipped = {r["node_id"]: r for r in result.provenance_skipped}
        assert "prereq_a" in skipped
        # prereq_a has no incoming requires edge → sentinel
        assert skipped["prereq_a"]["source"] == "<direct_learner_claim>"


# ---------------------------------------------------------------------------
# Unmatched claims emit warnings
# ---------------------------------------------------------------------------


class TestUnmatchedClaimWarnings:
    """Unmatched learner claims emit warnings with code adaptive_learner_claim_unmatched."""

    @pytest.mark.unit
    def test_unmatched_knows_claim_emits_warning(self):
        """A knows claim not in graph vocab emits a warning."""
        graph, ordered = _simple_graph_with_prereqs()
        profile = LearnerProfile(
            knows=("nonexistent_topic",),
            conservative_mode=True,
        )
        req = _make_request(profile=profile)
        with _gate_open():
            result, warnings = adaptive_path_mode(graph, ordered, req)

        codes = [w.code for w in warnings]
        assert "adaptive_learner_claim_unmatched" in codes

    @pytest.mark.unit
    def test_unmatched_weak_claim_emits_warning(self):
        """A weak claim not in graph vocab emits a warning."""
        graph, ordered = _simple_graph_with_prereqs()
        profile = LearnerProfile(
            weak=("unknown_concept",),
            conservative_mode=True,
        )
        req = _make_request(profile=profile)
        with _gate_open():
            result, warnings = adaptive_path_mode(graph, ordered, req)

        codes = [w.code for w in warnings]
        assert "adaptive_learner_claim_unmatched" in codes

    @pytest.mark.unit
    def test_unmatched_goals_claim_emits_warning(self):
        """A goals claim not in graph vocab emits a warning."""
        graph, ordered = _simple_graph_with_prereqs()
        profile = LearnerProfile(
            goals=("goal_not_in_graph",),
            conservative_mode=True,
        )
        req = _make_request(profile=profile)
        with _gate_open():
            result, warnings = adaptive_path_mode(graph, ordered, req)

        codes = [w.code for w in warnings]
        assert "adaptive_learner_claim_unmatched" in codes

    @pytest.mark.unit
    def test_matched_claim_no_warning(self):
        """A claim that matches a graph tag does NOT emit an unmatched warning."""
        graph, ordered = _simple_graph_with_prereqs()
        profile = LearnerProfile(knows=("tag_a",), conservative_mode=True)
        req = _make_request(profile=profile)
        with _gate_open():
            result, warnings = adaptive_path_mode(graph, ordered, req)

        unmatched = [
            w for w in warnings if w.code == "adaptive_learner_claim_unmatched"
        ]
        assert unmatched == []

    @pytest.mark.unit
    def test_matched_node_id_claim_no_warning(self):
        """A claim that matches a node_id does NOT emit an unmatched warning."""
        graph, ordered = _simple_graph_with_prereqs()
        profile = LearnerProfile(knows=("prereq_a",), conservative_mode=True)
        req = _make_request(profile=profile)
        with _gate_open():
            result, warnings = adaptive_path_mode(graph, ordered, req)

        unmatched = [
            w for w in warnings if w.code == "adaptive_learner_claim_unmatched"
        ]
        assert unmatched == []

    @pytest.mark.unit
    def test_warning_has_structured_source_ref(self):
        """Unmatched claim warning carries source_ref `<claim_type>::<normalised>`."""
        graph, ordered = _simple_graph_with_prereqs()
        profile = LearnerProfile(knows=("MISSING_CONCEPT",), conservative_mode=True)
        req = _make_request(profile=profile)
        with _gate_open():
            result, warnings = adaptive_path_mode(graph, ordered, req)

        unmatched = [
            w for w in warnings if w.code == "adaptive_learner_claim_unmatched"
        ]
        assert len(unmatched) == 1
        # source_ref encodes both the claim type and the normalised (lowercased) claim,
        # so downstream consumers can recover both without parsing the message.
        assert unmatched[0].source_ref == "knows::missing_concept"

    @pytest.mark.unit
    def test_same_claim_across_types_emits_per_type_warning(self):
        """A claim appearing in knows AND weak emits one warning per claim type.

        Source_ref is `<claim_type>::<claim>` so dedup is per (code, claim_type, claim).
        This is a behaviour change from the previous string-only source_ref dedup —
        each declared context now gets its own unmatched warning, which is the
        more truthful audit signal.
        """
        graph, ordered = _simple_graph_with_prereqs()
        profile = LearnerProfile(
            knows=("alien_concept",),
            weak=("alien_concept",),
            conservative_mode=True,
        )
        req = _make_request(profile=profile)
        with _gate_open():
            result, warnings = adaptive_path_mode(graph, ordered, req)

        unmatched = [
            w for w in warnings if w.code == "adaptive_learner_claim_unmatched"
        ]
        refs = sorted(w.source_ref for w in unmatched)
        assert refs == ["knows::alien_concept", "weak::alien_concept"]


# ---------------------------------------------------------------------------
# Determinism — byte-identical output for same profile + graph
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Two runs with the same LearnerProfile + graph produce byte-identical packets."""

    def _result_to_json(self, result: AdaptivePathResult) -> str:
        """Serialise result to a canonical JSON string for comparison."""
        payload = {
            "active_nodes": result.active_nodes,
            "provenance_skipped": result.provenance_skipped,
            "adaptive_summary": result.adaptive_summary,
            "warnings": [
                {
                    "severity": w.severity,
                    "code": w.code,
                    "message": w.message,
                    "source_ref": w.source_ref,
                }
                for w in result.warnings
            ],
            # Serialise the full lesson_body — keys AND values — so a value-level
            # regression (e.g. dict-iteration order in a node copy) is caught.
            "lesson_body": result.lesson_body,
        }
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    @pytest.mark.unit
    def test_same_profile_same_graph_byte_identical(self):
        """Two invocations with same inputs produce byte-identical JSON."""
        graph, ordered = _simple_graph_with_prereqs()
        profile = LearnerProfile(
            knows=("tag_a", "tag_x"),
            weak=("tag_b",),
            goals=("tag_c",),
            conservative_mode=False,
        )
        req = _make_request(profile=profile)
        with _gate_open():
            result1, _ = adaptive_path_mode(graph, ordered, req)
            result2, _ = adaptive_path_mode(graph, ordered, req)

        j1 = self._result_to_json(result1)
        j2 = self._result_to_json(result2)
        assert j1 == j2, "Byte-identical outputs required for same inputs"

    @pytest.mark.unit
    def test_lesson_body_keys_always_sorted(self):
        """lesson_body dict keys are always in sorted order (determinism)."""
        graph, ordered = _simple_graph_with_prereqs()
        profile = LearnerProfile(conservative_mode=True)
        req = _make_request(profile=profile)
        with _gate_open():
            result, _ = adaptive_path_mode(graph, ordered, req)

        keys = list(result.lesson_body.keys())
        assert keys == sorted(keys), "lesson_body keys must be sorted"

    @pytest.mark.unit
    def test_active_nodes_always_sorted(self):
        """active_nodes list is always sorted (determinism)."""
        graph, ordered = _simple_graph_with_prereqs()
        profile = LearnerProfile(conservative_mode=True)
        req = _make_request(profile=profile)
        with _gate_open():
            result, _ = adaptive_path_mode(graph, ordered, req)

        assert result.active_nodes == sorted(result.active_nodes)

    @pytest.mark.unit
    def test_provenance_skipped_sorted_by_node_id(self):
        """provenance_skipped list is sorted by node_id (determinism)."""
        graph, ordered = _simple_graph_with_prereqs()
        # Cover both prereq_a and prereq_b
        profile = LearnerProfile(
            knows=("prereq_a", "prereq_b"),
            conservative_mode=False,
        )
        req = _make_request(profile=profile)
        with _gate_open():
            result, _ = adaptive_path_mode(graph, ordered, req)

        assert len(result.provenance_skipped) == 2
        node_ids = [r["node_id"] for r in result.provenance_skipped]
        assert node_ids == sorted(node_ids)

    @pytest.mark.unit
    def test_determinism_with_toy_concept_kit(self):
        """Byte-identical with the shared toy_concept_kit fixture."""
        graph = fixture_graph_toy_concept_kit()
        ordered = [n["node_id"] for n in graph.nodes]
        profile = LearnerProfile(
            knows=("concept_alpha",),
            conservative_mode=False,
        )
        req = _make_request(profile=profile)
        with _gate_open():
            result1, _ = adaptive_path_mode(graph, ordered, req)
            result2, _ = adaptive_path_mode(graph, ordered, req)

        j1 = self._result_to_json(result1)
        j2 = self._result_to_json(result2)
        assert j1 == j2


# ---------------------------------------------------------------------------
# Adaptive summary
# ---------------------------------------------------------------------------


class TestAdaptiveSummary:
    """adaptive_summary section surfaces personalisation decisions."""

    @pytest.mark.unit
    def test_summary_present(self):
        """adaptive_summary is a non-empty string."""
        graph, ordered = _simple_graph_with_prereqs()
        req = _make_request(profile=LearnerProfile())
        with _gate_open():
            result, _ = adaptive_path_mode(graph, ordered, req)
        assert isinstance(result.adaptive_summary, str)
        assert result.adaptive_summary.strip() != ""

    @pytest.mark.unit
    def test_summary_contains_profile_echo(self):
        """adaptive_summary mentions the profile's knows and conservative_mode."""
        graph, ordered = _simple_graph_with_prereqs()
        profile = LearnerProfile(knows=("tag_a",), conservative_mode=True)
        req = _make_request(profile=profile)
        with _gate_open():
            result, _ = adaptive_path_mode(graph, ordered, req)
        assert "tag_a" in result.adaptive_summary
        assert "True" in result.adaptive_summary

    @pytest.mark.unit
    def test_summary_conservative_mode_message(self):
        """Conservative-mode summary says no nodes were skipped."""
        graph, ordered = _simple_graph_with_prereqs()
        req = _make_request(profile=LearnerProfile(conservative_mode=True))
        with _gate_open():
            result, _ = adaptive_path_mode(graph, ordered, req)
        assert "conservative" in result.adaptive_summary.lower()

    @pytest.mark.unit
    def test_summary_skip_count(self):
        """Summary mentions the skipped node count when skipping occurs."""
        graph, ordered = _simple_graph_with_prereqs()
        profile = LearnerProfile(knows=("prereq_a",), conservative_mode=False)
        req = _make_request(profile=profile)
        with _gate_open():
            result, _ = adaptive_path_mode(graph, ordered, req)
        # Check it reports skip count (at least "1" somewhere meaningful)
        assert "1" in result.adaptive_summary

    @pytest.mark.unit
    def test_summary_heading(self):
        """adaptive_summary starts with the Adaptive Path Summary heading."""
        graph, ordered = _simple_graph_with_prereqs()
        req = _make_request(profile=LearnerProfile())
        with _gate_open():
            result, _ = adaptive_path_mode(graph, ordered, req)
        assert result.adaptive_summary.startswith("## Adaptive Path Summary")


# ---------------------------------------------------------------------------
# Capability gate
# ---------------------------------------------------------------------------


class TestCapabilityGate:
    """adaptive_path raises PreconditionError when llm extra is absent."""

    @pytest.mark.unit
    def test_raises_precondition_error_without_extra(self):
        """PreconditionError raised when llm extra absent."""
        graph, ordered = _simple_graph_with_prereqs()
        req = _make_request(profile=LearnerProfile())
        # Do NOT open the gate — llm extra absent by default in test env
        with pytest.raises(PreconditionError) as exc_info:
            adaptive_path_mode(graph, ordered, req)
        assert exc_info.value.capability == "adaptive_path"
        assert exc_info.value.extra == "llm"

    @pytest.mark.unit
    def test_no_error_when_extra_present(self):
        """No PreconditionError when the gate is open."""
        graph, ordered = _simple_graph_with_prereqs()
        req = _make_request(profile=LearnerProfile())
        with _gate_open():
            result, _ = adaptive_path_mode(graph, ordered, req)
        assert isinstance(result, AdaptivePathResult)


# ---------------------------------------------------------------------------
# Registry and plugin wiring
# ---------------------------------------------------------------------------


class TestRegistryAndPlugin:
    """adaptive_path is registered in ordering registry + plugin capabilities."""

    @pytest.mark.unit
    def test_ordering_strategy_registered(self):
        """get_strategy('adaptive_path') returns a callable without error."""
        strategy = get_strategy("adaptive_path")
        assert callable(strategy)

    @pytest.mark.unit
    def test_strategy_in_list_strategies(self):
        """list_strategies() includes 'adaptive_path'."""
        assert "adaptive_path" in list_strategies()

    @pytest.mark.unit
    def test_plugin_reports_capability(self):
        """Plugin.capabilities() includes 'adaptive_path'."""
        plugin = get_plugin()
        assert "adaptive_path" in plugin.capabilities()

    @pytest.mark.unit
    def test_adaptive_path_after_notebook_source_in_plugin(self):
        """'adaptive_path' is declared after 'notebook_source' in capabilities()."""
        caps = get_plugin().capabilities()
        idx_ns = caps.index("notebook_source")
        idx_ap = caps.index("adaptive_path")
        assert idx_ap > idx_ns

    @pytest.mark.unit
    def test_strategy_uses_default_ordering(self):
        """adaptive_path strategy produces the same ordering as order_nodes."""
        from akms_learn.ordering import order_nodes

        graph, _ = _simple_graph_with_prereqs()
        strategy = get_strategy("adaptive_path")
        strategy_nodes, strategy_warnings = strategy(graph)
        default_nodes, default_warnings = order_nodes(graph)
        assert strategy_nodes == default_nodes


# ---------------------------------------------------------------------------
# Source canary: no forbidden calls in the mode source
# ---------------------------------------------------------------------------


class TestSourceCanary:
    """Canary: adaptive_path.py must not contain execution-at-compile-time patterns."""

    @pytest.mark.unit
    def test_no_exec_eval_subprocess_in_source(self):
        """adaptive_path.py source does not call exec/eval/subprocess/%run/nbclient."""
        import re
        from pathlib import Path

        src_path = (
            Path(__file__).parent.parent
            / "src"
            / "akms_learn"
            / "modes"
            / "adaptive_path.py"
        )
        src = src_path.read_text(encoding="utf-8")
        # Check for actual call/import syntax — not bare word mentions in docstrings.
        # subprocess: check for import or attribute-call syntax (subprocess.run, etc.)
        # exec/eval: check for call syntax only.
        # nbclient/%%run: bare word (these should never appear as import or call).
        forbidden_patterns = [
            (r"\bexec\s*\(", "exec() call"),
            (r"\beval\s*\(", "eval() call"),
            (r"\bimport\s+subprocess\b|subprocess\s*\.", "subprocess import or call"),
            (r"%%run\b", "%run magic"),
            (r"\bimport\s+nbclient\b", "nbclient import"),
        ]
        for pattern, label in forbidden_patterns:
            assert not re.search(pattern, src), (
                f"adaptive_path.py contains forbidden pattern ({label}): {pattern!r}"
            )

    @pytest.mark.unit
    def test_all_set_iterations_use_sorted(self):
        """Check source for unsorted set-to-list coercions (spot check)."""
        import ast
        from pathlib import Path

        src_path = (
            Path(__file__).parent.parent
            / "src"
            / "akms_learn"
            / "modes"
            / "adaptive_path.py"
        )
        src = src_path.read_text(encoding="utf-8")
        # Parse AST to verify frozenset/set literals are not iterated without sorted()
        # Simple heuristic: no bare 'list(<set_var>)' calls
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "list":
                    # list(<something>) — check if the arg is a set or frozenset literal
                    for arg in node.args:
                        assert not isinstance(arg, (ast.Set,)), (
                            "Unsorted set-to-list conversion found in adaptive_path.py"
                        )


class TestAdaptivePathCompilerWiring:
    """Stage-6 wiring: ``compile_learning_source`` routes ``adaptive_path``
    through its mode when the capability is available, so the learner-profile
    prerequisite skip reaches the LSP ``reading_order``. Dangling edges left by a
    skipped node are dropped at packet assembly so the packet still validates.
    """

    @pytest.mark.integration
    def test_known_prereq_skipped_from_reading_order(self):
        from akms_learn.compiler import compile_learning_source

        graph, _ = _simple_graph_with_prereqs()
        req = _make_request(
            profile=LearnerProfile(knows=("prereq_a",), conservative_mode=False)
        )
        with _gate_open():
            result = compile_learning_source(request=req, graph_slice=graph)
        body = result.packet.body
        # prereq_a is covered by `knows` → dropped from the reading order and body...
        assert "prereq_a" not in body.reading_order
        assert "prereq_b" in body.reading_order
        assert "target_c" in body.reading_order
        assert "prereq_a" not in {n.node_id for n in body.nodes}
        # ...and the now-dangling edge e_a_b is removed so the packet validates.
        edge_ids = {e.edge_id for e in body.edges}
        assert "e_a_b" not in edge_ids
        assert "e_b_c" in edge_ids

    @pytest.mark.integration
    def test_conservative_mode_keeps_all_nodes(self):
        from akms_learn.compiler import compile_learning_source

        graph, _ = _simple_graph_with_prereqs()
        req = _make_request(
            profile=LearnerProfile(knows=("prereq_a",), conservative_mode=True)
        )
        with _gate_open():
            result = compile_learning_source(request=req, graph_slice=graph)
        assert "prereq_a" in result.packet.body.reading_order

    @pytest.mark.integration
    def test_capability_absent_falls_back_to_default_ordering(self):
        """Without the ``llm`` extra the mode is unavailable; ``adaptive_path``
        compiles with the default ordering (no skip), preserving the pre-wiring
        behaviour and never raising a PreconditionError from the compiler."""
        from akms_learn.compiler import compile_learning_source

        graph, _ = _simple_graph_with_prereqs()
        req = _make_request(
            profile=LearnerProfile(knows=("prereq_a",), conservative_mode=False)
        )
        # No _gate_open(): capability unavailable → no skip, full reading order.
        result = compile_learning_source(request=req, graph_slice=graph)
        assert "prereq_a" in result.packet.body.reading_order

    @pytest.mark.integration
    def test_dict_request_routes_through_mode(self):
        """A raw ``dict`` request (the CLI path) must reach ``adaptive_path_mode``
        without raising ``AttributeError`` on ``request.learner_profile``. The
        compiler coerces dict requests to a ``LearningRequest``, parsing the
        nested ``learner_profile`` sub-dict, so the prereq skip still applies.
        """
        from akms_learn.compiler import compile_learning_source

        graph, _ = _simple_graph_with_prereqs()
        req = {
            "topic": "toy adaptive path",
            "goal": "Learn the adaptive path mode end-to-end.",
            "generation_option": "adaptive_path",
            "learner_profile": {
                "knows": ["prereq_a"],
                "conservative_mode": False,
            },
        }
        with _gate_open():
            result = compile_learning_source(request=req, graph_slice=graph)
        assert "prereq_a" not in result.packet.body.reading_order
        assert "prereq_b" in result.packet.body.reading_order
