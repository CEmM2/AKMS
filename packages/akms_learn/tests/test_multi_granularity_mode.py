"""Tests for multi_granularity mode.

Covers all four acceptance criteria:

Same graph can emit overview and deep_dive variants with different
      node sets or section depth.
Selected granularity appears in the LSP request block and source
      metadata (mode result struct + LearningRequestInfo).
No AKMS v3 ontology is required (request-level + tag-level
      conventions only).
When granularity cannot be inferred the compiler defaults to
      'standard' and emits the documented warning.

Plus convention-priority tests (explicit > tag > id > domain) and the
no-graph-leak snapshot.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from akms_learn.graph_import import GraphSlice
from akms_learn.models import LearningRequestInfo, LearningWarning
from akms_learn.modes.multi_granularity import (
    DEFAULT_GRANULARITY,
    GRANULARITY_INFERENCE_FALLBACK_CODE,
    GRANULARITY_VALUES,
    MultiGranularityResult,
    multi_granularity_mode,
    multi_granularity_strategy,
)
from akms_learn.ordering import get_strategy
from akms_learn.toy_fixtures import (
    fixture_graph_toy_concept_kit,
    fixture_graph_toy_multi_granularity,
)
from akms_learn.requests import (
    NORMALIZED_FIELDS,
    LearningRequest,
    normalize_request,
    request_hash,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(**overrides: Any) -> LearningRequest:
    defaults: dict[str, Any] = dict(
        topic="toy multi-granularity",
        goal="Exercise the multi_granularity mode.",
        audience="engineer",
        depth="implementation",
        generation_option="multi_granularity",
        seed_tags=[],
        exporters=[],
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


def _run(
    graph_slice: GraphSlice,
    granularity: Any = None,
) -> tuple[MultiGranularityResult, list[LearningWarning]]:
    req = _make_request(granularity=granularity) if granularity is not None else _make_request()
    return multi_granularity_mode(graph_slice, req)


def _slice_snapshot(slice_: GraphSlice) -> dict[str, Any]:
    """Return a deep-copy snapshot used to assert no-mutation."""
    return {
        "nodes": copy.deepcopy(list(slice_.nodes)),
        "edges": copy.deepcopy(list(slice_.edges)),
        "metadata": copy.deepcopy(dict(slice_.metadata)),
    }


# ---------------------------------------------------------------------------
# overview vs deep_dive yields different node sets
# ---------------------------------------------------------------------------


class TestOverviewVsDeepDive:
    """Overview vs deep_dive variants of the same graph differ."""

    def test_overview_and_deep_dive_differ_on_multi_granularity_fixture(self):
        slice_ = fixture_graph_toy_multi_granularity()

        overview_res, _ = _run(slice_, "overview")
        deep_res, _ = _run(slice_, "deep_dive")

        assert overview_res.selected_granularity == "overview"
        assert deep_res.selected_granularity == "deep_dive"

        # Deep dive keeps every node.
        deep_ids = set(deep_res.ordered_nodes)
        overview_ids = set(overview_res.ordered_nodes)
        assert overview_ids != deep_ids, (
            "overview and deep_dive must produce different node sets"
        )
        # Overview is a strict subset of deep_dive.
        assert overview_ids.issubset(deep_ids)
        # Overview drops the fine-tagged nodes.
        assert "fine_detail_gamma" not in overview_ids
        assert "fine_detail_delta" not in overview_ids
        # Overview keeps the coarse-tagged node.
        assert "coarse_overview_alpha" in overview_ids

    def test_standard_sits_between_overview_and_deep_dive(self):
        slice_ = fixture_graph_toy_multi_granularity()

        overview_res, _ = _run(slice_, "overview")
        standard_res, _ = _run(slice_, "standard")
        deep_res, _ = _run(slice_, "deep_dive")

        overview_ids = set(overview_res.ordered_nodes)
        standard_ids = set(standard_res.ordered_nodes)
        deep_ids = set(deep_res.ordered_nodes)

        # Standard keeps coarse + standard but drops fine.
        assert "fine_detail_gamma" not in standard_ids
        assert "std_node_beta" in standard_ids
        assert overview_ids.issubset(standard_ids)
        assert standard_ids.issubset(deep_ids)


# ---------------------------------------------------------------------------
# selected granularity surfaces on result + LSP request block
# ---------------------------------------------------------------------------


class TestGranularityVisibility:
    """Selected granularity appears on the mode result and the
    LSP request block."""

    def test_result_struct_exposes_selected_granularity(self):
        slice_ = fixture_graph_toy_multi_granularity()
        result, _ = _run(slice_, "overview")
        assert result.selected_granularity == "overview"
        assert result.detection_method == "request"
        assert "request.granularity" in result.rationale

    def test_lsp_request_info_carries_granularity(self):
        info = LearningRequestInfo(
            topic="toy",
            generation_option="multi_granularity",
            request_hash="0" * 64,
            granularity="deep_dive",
        )
        assert info.granularity == "deep_dive"

    def test_lsp_request_info_granularity_defaults_to_none(self):
        info = LearningRequestInfo(
            topic="toy",
            generation_option="multi_granularity",
            request_hash="0" * 64,
        )
        assert info.granularity is None


# ---------------------------------------------------------------------------
# no v3 ontology — convention detection only
# ---------------------------------------------------------------------------


class TestConventionDetectionOnly:
    """No AKMS v3 ontology is required."""

    def test_tag_detection_uses_coarse_standard_fine(self):
        slice_ = fixture_graph_toy_multi_granularity()
        # No explicit request — should detect "fine" tag in fixture and
        # pick deep_dive as the most-permissive available signal.
        result, _ = _run(slice_, None)
        assert result.detection_method == "tag"
        assert result.selected_granularity == "deep_dive"
        assert "tags" in result.rationale.lower()

    def test_id_prefix_detection_when_no_tags_present(self):
        # Build a synthetic slice where granularity lives only in the id
        # prefix — no tag conveys the signal.
        nodes = [
            {
                "node_id": "coarse_node_alpha",
                "title": "Coarse Alpha",
                "kind": "core_concept",
                "domain": "toy_domain_a",
                "subdomain": "toy_subdomain_aa",
                "tags": ["toy"],  # no coarse/standard/fine tag
                "status": "established",
                "source_path": "toy://granularity/idprefix_alpha.md",
                "line_range": [1, 4],
                "extracted": {},
            },
            {
                "node_id": "node_beta_fine",
                "title": "Beta Fine",
                "kind": "core_concept",
                "domain": "toy_domain_b",
                "subdomain": "toy_subdomain_bb",
                "tags": ["toy"],  # no coarse/standard/fine tag
                "status": "established",
                "source_path": "toy://granularity/idsuffix_beta.md",
                "line_range": [1, 4],
                "extracted": {},
            },
        ]
        slice_ = GraphSlice(
            nodes=tuple(nodes),
            edges=tuple(),
            metadata={"family": "synthetic_id_only", "graph_version": "test"},
        )
        result, _ = _run(slice_, None)
        assert result.detection_method == "id_prefix"
        # Two id-derived signals: 'coarse' and 'fine'; most permissive wins.
        assert result.selected_granularity == "deep_dive"

    def test_domain_grouping_detection_when_no_tags_or_ids(self):
        # All nodes share the same (domain, subdomain) and carry no
        # granularity tags / id prefixes — domain grouping picks "standard".
        nodes = [
            {
                "node_id": "plain_alpha",
                "title": "Plain Alpha",
                "kind": "core_concept",
                "domain": "toy_shared_domain",
                "subdomain": "toy_shared_subdomain",
                "tags": ["toy"],
                "status": "established",
                "source_path": "toy://granularity/plain_alpha.md",
                "line_range": [1, 4],
                "extracted": {},
            },
            {
                "node_id": "plain_beta",
                "title": "Plain Beta",
                "kind": "core_concept",
                "domain": "toy_shared_domain",
                "subdomain": "toy_shared_subdomain",
                "tags": ["toy"],
                "status": "established",
                "source_path": "toy://granularity/plain_beta.md",
                "line_range": [1, 4],
                "extracted": {},
            },
        ]
        slice_ = GraphSlice(
            nodes=tuple(nodes),
            edges=tuple(),
            metadata={"family": "synthetic_domain_only", "graph_version": "test"},
        )
        result, _ = _run(slice_, None)
        assert result.detection_method == "domain_grouping"
        assert result.selected_granularity == DEFAULT_GRANULARITY


# ---------------------------------------------------------------------------
# fallback to standard + warning when no signal
# ---------------------------------------------------------------------------


class TestFallbackWarning:
    """Missing signal => default 'standard' + warning."""

    def _ambiguous_slice(self) -> GraphSlice:
        # Multiple (domain, subdomain) pairs, no granularity tags,
        # no granularity-tokens in id => domain grouping returns None
        # and the selector hits the fallback path.
        nodes = [
            {
                "node_id": "plain_alpha",
                "title": "Plain Alpha",
                "kind": "core_concept",
                "domain": "toy_domain_a",
                "subdomain": "toy_subdomain_aa",
                "tags": ["toy"],
                "status": "established",
                "source_path": "toy://granularity/ambig_alpha.md",
                "line_range": [1, 4],
                "extracted": {},
            },
            {
                "node_id": "plain_beta",
                "title": "Plain Beta",
                "kind": "core_concept",
                "domain": "toy_domain_b",
                "subdomain": "toy_subdomain_bb",
                "tags": ["toy"],
                "status": "established",
                "source_path": "toy://granularity/ambig_beta.md",
                "line_range": [1, 4],
                "extracted": {},
            },
        ]
        return GraphSlice(
            nodes=tuple(nodes),
            edges=tuple(),
            metadata={"family": "ambiguous_fallback", "graph_version": "test"},
        )

    def test_fallback_defaults_to_standard(self):
        slice_ = self._ambiguous_slice()
        result, _ = _run(slice_, None)
        assert result.selected_granularity == DEFAULT_GRANULARITY == "standard"
        assert result.detection_method == "fallback"

    def test_fallback_emits_documented_warning(self):
        slice_ = self._ambiguous_slice()
        result, warnings = _run(slice_, None)
        codes = [w.code for w in warnings]
        assert GRANULARITY_INFERENCE_FALLBACK_CODE in codes
        # Warning carries the slice family as the source_ref so downstream
        # logs can attribute it.
        fallback = next(
            w for w in warnings if w.code == GRANULARITY_INFERENCE_FALLBACK_CODE
        )
        assert fallback.source_ref == "ambiguous_fallback"
        assert fallback.severity == "warning"

    def test_fallback_warning_only_fires_in_fallback_branch(self):
        """The warning must NOT appear when any convention fires."""
        slice_ = fixture_graph_toy_multi_granularity()
        _, warnings = _run(slice_, None)  # tag-based detection fires
        codes = [w.code for w in warnings]
        assert GRANULARITY_INFERENCE_FALLBACK_CODE not in codes


# ---------------------------------------------------------------------------
# Convention priority ordering
# ---------------------------------------------------------------------------


class TestConventionPriority:
    """Priority order: explicit request > tag > id prefix > domain grouping."""

    def test_explicit_request_beats_tag(self):
        slice_ = fixture_graph_toy_multi_granularity()
        # Slice would tag-detect deep_dive; explicit request="overview" wins.
        result, _ = _run(slice_, "overview")
        assert result.selected_granularity == "overview"
        assert result.detection_method == "request"

    def test_tag_beats_id_prefix(self):
        # Build a slice with conflicting signals — tag says coarse, id
        # prefix says fine. Tag wins.
        nodes = [
            {
                "node_id": "fine_named_node",
                "title": "Fine-named Node",
                "kind": "core_concept",
                "domain": "toy_domain",
                "subdomain": "toy_subdomain_z",
                "tags": ["toy", "coarse"],
                "status": "established",
                "source_path": "toy://granularity/conflict.md",
                "line_range": [1, 4],
                "extracted": {},
            },
        ]
        slice_ = GraphSlice(
            nodes=tuple(nodes),
            edges=tuple(),
            metadata={"family": "tag_vs_id"},
        )
        result, _ = _run(slice_, None)
        assert result.detection_method == "tag"
        assert result.selected_granularity == "overview"

    def test_id_prefix_beats_domain_grouping(self):
        # No tags, but ids carry granularity tokens. Even though the slice
        # has a single shared (domain, subdomain), id-prefix detection
        # (priority 3) wins over domain grouping (priority 4).
        nodes = [
            {
                "node_id": "fine_alpha",
                "title": "Fine Alpha",
                "kind": "core_concept",
                "domain": "toy_shared",
                "subdomain": "toy_shared_sub",
                "tags": ["toy"],
                "status": "established",
                "source_path": "toy://granularity/idwin_alpha.md",
                "line_range": [1, 4],
                "extracted": {},
            },
        ]
        slice_ = GraphSlice(
            nodes=tuple(nodes),
            edges=tuple(),
            metadata={"family": "id_vs_domain"},
        )
        result, _ = _run(slice_, None)
        assert result.detection_method == "id_prefix"
        assert result.selected_granularity == "deep_dive"


# ---------------------------------------------------------------------------
# request_hash invariant — granularity must NOT enter the hash
# ---------------------------------------------------------------------------


class TestRequestHashStability:
    """granularity is excluded from NORMALIZED_FIELDS — hash must be stable
    across granularity values (mirrors the policy-exclusion pattern)."""

    def test_granularity_not_in_normalized_fields(self):
        assert "granularity" not in NORMALIZED_FIELDS

    def test_hash_invariant_under_granularity_change(self):
        base = dict(
            topic="toy multi-granularity",
            goal="hash invariance check",
            audience="engineer",
            depth="implementation",
            generation_option="multi_granularity",
        )
        h_none = request_hash(normalize_request(dict(base)))
        for g in GRANULARITY_VALUES:
            req = dict(base, granularity=g)
            assert request_hash(normalize_request(req)) == h_none, (
                f"granularity={g!r} must not change the request hash"
            )


# ---------------------------------------------------------------------------
# No-graph-leak invariant — granularity must NOT be written into AKMS nodes
# ---------------------------------------------------------------------------


class TestNoGraphLeak:
    """Phase 2 context §"Key Principles" item 3: granularity is LSP-only."""

    def test_mode_does_not_mutate_graph_slice(self):
        slice_ = fixture_graph_toy_multi_granularity()
        before = _slice_snapshot(slice_)
        for g in (None, "overview", "standard", "deep_dive"):
            _run(slice_, g)
        after = _slice_snapshot(slice_)
        assert before == after, "multi_granularity_mode must not mutate the slice"

    def test_no_node_carries_granularity_field_after_mode_run(self):
        slice_ = fixture_graph_toy_multi_granularity()
        _run(slice_, "deep_dive")
        for node in slice_.nodes:
            assert "granularity" not in node, (
                f"node {node.get('node_id')!r} must not carry a 'granularity' "
                f"key after multi_granularity_mode runs (Phase 2 graph-leak "
                f"invariant)"
            )


# ---------------------------------------------------------------------------
# Strategy registry wiring
# ---------------------------------------------------------------------------


class TestStrategyRegistry:
    """multi_granularity is discoverable via the ordering strategy registry."""

    def test_get_strategy_returns_callable(self):
        strat = get_strategy("multi_granularity")
        assert callable(strat)

    def test_strategy_returns_default_ordering_on_concept_kit(self):
        # Without a request the strategy cannot filter — it must return the
        # default order unchanged (i.e. all nodes preserved).
        slice_ = fixture_graph_toy_concept_kit()
        ordered, _ = multi_granularity_strategy(slice_)
        node_ids = {n["node_id"] for n in slice_.nodes}
        assert set(ordered) == node_ids


# ---------------------------------------------------------------------------
# Unrecognised explicit value falls through to convention detection
# ---------------------------------------------------------------------------


class TestUnrecognisedExplicitValue:
    """An unrecognised request.granularity value falls through to detection."""

    def test_unknown_explicit_value_falls_through(self):
        slice_ = fixture_graph_toy_multi_granularity()
        # Bypass Pydantic Literal validation by passing the field via dict
        # then patching it onto a stub request-like object — but the simpler
        # path is: a Pydantic-rejected value never reaches the mode. So we
        # construct a plain object that exposes the attribute.
        class _StubReq:
            granularity = "bogus_value"
        result, warnings = multi_granularity_mode(slice_, _StubReq())  # type: ignore[arg-type]
        # tag-based detection still fires on the fixture.
        assert result.detection_method == "tag"
        assert result.selected_granularity == "deep_dive"
