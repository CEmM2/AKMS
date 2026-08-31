"""Tests for assessment_first compiler mode.

Covers all five acceptance criteria:

Compiler registered under mode key ``assessment_first``.
AssessmentItem.kind is a Literal of {conceptual, derivation, coding,
      debugging}.
Items with no ``target_node_ids`` or with ids absent from
      ``packet.nodes`` are rejected at LSP validation.
``hidden_answer`` is stored on the item but is never copied into the
      public ``prompt`` field (canary test).
Weak-support warning appears in packet.warnings with the item id and
      never raises.

Additional tests:
  - Compiler raises PreconditionError when the ``notebook`` extra is absent.
  - Strategy registered as ``"assessment_first"`` in ordering registry.
  - Plugin reports ``"assessment_first"`` capability AFTER existing entries.
  - v2.1 assessment_items hints are consumed when present.
  - Deterministic output: two runs produce byte-identical AssessmentItem lists.
  - Canary: assessment_first.py source contains no execution-at-compile-time
    patterns (subprocess/exec/eval/nbclient).
"""

from __future__ import annotations

import importlib.util
import json
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest

from akms_learn.capability_gates import PreconditionError
from akms_learn.compiler import compile_learning_source
from akms_learn.graph_import import GraphSlice
from akms_learn.models import AssessmentItem, AssessmentItemKind
from akms_learn.models.assessment import ASSESSMENT_ITEM_KINDS
from akms_learn.modes.assessment_first import (
    KIND_TO_SECTION_NAMES,
    WEAK_SUPPORT_THRESHOLD_CHARS,
    AssessmentFirstResult,
    AssessmentOrphanReferenceError,
    assessment_first_mode,
    validate_assessment_references,
)
from akms_learn.ordering import get_strategy, list_strategies, order_nodes
from akms_learn.plugin import get_plugin
from akms_learn.requests import LearningRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(**overrides: Any) -> LearningRequest:
    defaults: dict[str, Any] = dict(
        topic="toy assessment-first lesson",
        goal="Exercise the assessment_first compiler mode.",
        audience="engineer",
        depth="implementation",
        generation_option="assessment_first",
        seed_tags=[],
        exporters=[],
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


@contextmanager
def _gate_open():
    """Patch ``find_spec`` so the ``notebook`` extra (nbformat) reports present.

    Mirrors the pattern used by ``test_notebook_source_compiler.py`` — the
    ``assessment_first`` capability is gated on the ``notebook`` extra.
    """
    original = importlib.util.find_spec

    def _patched(name: str, *args: Any, **kwargs: Any):
        if name == "nbformat":
            return object()  # Truthy non-None — find_spec returns ModuleSpec
        return original(name, *args, **kwargs)

    with patch("importlib.util.find_spec", side_effect=_patched):
        yield


def _make_rich_node(
    node_id: str,
    *,
    extracted: dict[str, str] | None = None,
    title: str | None = None,
    tags: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic toy node payload with full approved-heading content."""
    node: dict[str, Any] = {
        "node_id": node_id,
        "title": title or f"Node {node_id}",
        "kind": "core_concept",
        "domain": "toy",
        "subdomain": "sub",
        "tags": tags or [],
        "status": "established",
        "source_path": f"toy://{node_id}.md",
        "line_range": [1, 10],
        "extracted": extracted or {},
    }
    if extra:
        node.update(extra)
    return node


def _graph_with_all_four_kinds() -> tuple[GraphSlice, list[str]]:
    """A single node whose ``extracted`` mapping carries all four section types.

    Produces one assessment item per kind.
    """
    node = _make_rich_node(
        "alpha",
        title="Alpha",
        extracted={
            "concept": (
                "Alpha is a foundational widget bridging two pipelines. "
                "It defines the canonical mapping between widget A and widget B."
            ),
            "derivation": (
                "Starting from the widget identity, apply step-1 reduction, "
                "then step-2 normalisation, to obtain the final form."
            ),
            "implementation": (
                "def alpha_compute(x):\n"
                "    return x * 2\n"
            ),
            "pitfalls": (
                "Beware: callers often confuse widget A and widget B; "
                "the canonical mapping requires sorted input."
            ),
        },
    )
    graph = GraphSlice(nodes=(node,), edges=(), metadata={})
    return graph, ["alpha"]


def _graph_with_v21_hint_long_answer() -> tuple[GraphSlice, list[str], str]:
    """Graph carrying a v2.1 ``assessment_items`` hint with a long answer.

    Returns ``(graph, ordered_nodes, expected_answer_text)`` so the canary
    test can substring-check against the answer.
    """
    answer_text = (
        "This is a long author-provided answer key, intentionally distinctive "
        "so the canary substring-check is meaningful: ZETA_SENTINEL_42."
    )
    node = _make_rich_node(
        "beta",
        title="Beta",
        extracted={
            "concept": (
                "Beta extends Alpha with the second mapping step. It is the "
                "core composition primitive in the toy pipeline."
            ),
        },
        extra={
            "assessment_items": [
                {
                    "id": "beta::hint-1",
                    "kind": "conceptual",
                    "prompt": "Describe Beta in your own words.",
                    "answer": answer_text,
                    "target_node_ids": ["beta"],
                },
            ],
        },
    )
    graph = GraphSlice(nodes=(node,), edges=(), metadata={})
    return graph, ["beta"], answer_text


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    """Compiler registered under mode key ``assessment_first``."""

    @pytest.mark.unit
    def test_ordering_strategy_registered(self):
        strategy = get_strategy("assessment_first")
        assert callable(strategy)

    @pytest.mark.unit
    def test_strategy_in_list_strategies(self):
        assert "assessment_first" in list_strategies()

    @pytest.mark.unit
    def test_plugin_reports_capability(self):
        assert "assessment_first" in get_plugin().capabilities()

    @pytest.mark.unit
    def test_capability_appears_after_existing_entries(self):
        """``assessment_first`` is appended after ``adaptive_path`` and ``notebook_source``."""
        caps = get_plugin().capabilities()
        idx_ns = caps.index("notebook_source")
        idx_ap = caps.index("adaptive_path")
        idx_af = caps.index("assessment_first")
        assert idx_af > idx_ns
        assert idx_af > idx_ap

    @pytest.mark.unit
    def test_strategy_uses_default_ordering(self):
        graph, _ = _graph_with_all_four_kinds()
        strategy = get_strategy("assessment_first")
        s_nodes, _ = strategy(graph)
        d_nodes, _ = order_nodes(graph)
        assert s_nodes == d_nodes


# ---------------------------------------------------------------------------
# kind Literal coverage
# ---------------------------------------------------------------------------


class TestAssessmentItemModel:
    """AssessmentItem.kind is a Literal of exactly four values."""

    @pytest.mark.unit
    def test_assessment_item_kinds_constant(self):
        assert ASSESSMENT_ITEM_KINDS == (
            "conceptual",
            "derivation",
            "coding",
            "debugging",
        )

    @pytest.mark.unit
    @pytest.mark.parametrize("kind", list(ASSESSMENT_ITEM_KINDS))
    def test_each_kind_constructs(self, kind: AssessmentItemKind):
        item = AssessmentItem(
            id=f"id::{kind}",
            kind=kind,
            prompt="prompt text",
            target_node_ids=("node-a",),
        )
        assert item.kind == kind

    @pytest.mark.unit
    def test_invalid_kind_rejected(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AssessmentItem(
                id="bad",
                kind="essay",  # type: ignore[arg-type]
                prompt="x",
                target_node_ids=("n",),
            )

    @pytest.mark.unit
    def test_target_node_ids_must_be_non_empty(self):
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            AssessmentItem(
                id="empty",
                kind="conceptual",
                prompt="x",
                target_node_ids=(),
            )

    @pytest.mark.unit
    def test_frozen_model(self):
        from pydantic import ValidationError
        item = AssessmentItem(
            id="x",
            kind="conceptual",
            prompt="p",
            target_node_ids=("n",),
        )
        with pytest.raises((ValidationError, TypeError)):
            item.prompt = "leaked"  # type: ignore[misc]

    @pytest.mark.unit
    def test_hidden_answer_defaults_none(self):
        item = AssessmentItem(
            id="x",
            kind="conceptual",
            prompt="p",
            target_node_ids=("n",),
        )
        assert item.hidden_answer is None


# ---------------------------------------------------------------------------
# Compiler — emits items for all four kinds
# ---------------------------------------------------------------------------


class TestCompilerEmitsAllKinds:
    """Verifies: compiler emits items for conceptual/derivation/coding/debugging."""

    @pytest.mark.unit
    def test_emits_one_item_per_kind(self):
        graph, ordered = _graph_with_all_four_kinds()
        req = _make_request()
        with _gate_open():
            result, _ = assessment_first_mode(graph, ordered, req)
        kinds_emitted = sorted(item.kind for item in result.assessment_items)
        assert kinds_emitted == sorted(ASSESSMENT_ITEM_KINDS)

    @pytest.mark.unit
    def test_each_kind_uses_matching_section(self):
        graph, ordered = _graph_with_all_four_kinds()
        req = _make_request()
        with _gate_open():
            result, _ = assessment_first_mode(graph, ordered, req)
        for item in result.assessment_items:
            expected_sections = KIND_TO_SECTION_NAMES[item.kind]
            # The provenance "section_kind" must be one of the heuristic targets.
            assert item.provenance.get("section_kind") in expected_sections, item

    @pytest.mark.unit
    def test_items_anchored_to_node(self):
        graph, ordered = _graph_with_all_four_kinds()
        req = _make_request()
        with _gate_open():
            result, _ = assessment_first_mode(graph, ordered, req)
        for item in result.assessment_items:
            assert item.target_node_ids == ("alpha",)

    @pytest.mark.unit
    def test_node_without_sections_produces_no_items(self):
        node = _make_rich_node("empty", extracted={})  # no approved-heading content
        graph = GraphSlice(nodes=(node,), edges=(), metadata={})
        req = _make_request()
        with _gate_open():
            result, _ = assessment_first_mode(graph, ["empty"], req)
        # No v2.1 hints, no heuristic sections → no items.
        assert result.assessment_items == []


# ---------------------------------------------------------------------------
# Orphan rejection
# ---------------------------------------------------------------------------


class TestOrphanRejection:
    """Items with target_node_ids absent from packet.nodes are rejected."""

    @pytest.mark.unit
    def test_validate_assessment_references_pure(self):
        items = [
            AssessmentItem(
                id="orphan-1",
                kind="conceptual",
                prompt="p",
                target_node_ids=("missing-node",),
            )
        ]
        orphans = validate_assessment_references(items, set())
        assert orphans == [("orphan-1", "missing-node")]

    @pytest.mark.unit
    def test_validate_assessment_references_clean(self):
        items = [
            AssessmentItem(
                id="ok",
                kind="conceptual",
                prompt="p",
                target_node_ids=("n",),
            )
        ]
        orphans = validate_assessment_references(items, {"n"})
        assert orphans == []

    @pytest.mark.unit
    def test_validate_orphans_sorted_deterministic(self):
        items = [
            AssessmentItem(
                id="b",
                kind="conceptual",
                prompt="p",
                target_node_ids=("z-missing", "a-missing"),
            ),
            AssessmentItem(
                id="a",
                kind="derivation",
                prompt="p",
                target_node_ids=("c-missing",),
            ),
        ]
        orphans = validate_assessment_references(items, set())
        assert orphans == sorted(orphans)

    @pytest.mark.unit
    def test_compiler_raises_on_orphan_hint(self):
        """A v2.1 hint pointing at a non-existent node id raises during compile."""
        node = _make_rich_node(
            "host",
            extracted={"concept": "Some content."},
            extra={
                "assessment_items": [
                    {
                        "id": "host::hint",
                        "kind": "conceptual",
                        "prompt": "Q?",
                        "target_node_ids": ["host", "ghost-node"],
                    }
                ],
            },
        )
        graph = GraphSlice(nodes=(node,), edges=(), metadata={})
        req = _make_request()
        with _gate_open():
            with pytest.raises(AssessmentOrphanReferenceError) as exc_info:
                assessment_first_mode(graph, ["host"], req)
        assert "ghost-node" in str(exc_info.value)
        assert "host::hint" in str(exc_info.value)

    @pytest.mark.unit
    def test_orphan_error_carries_issues_list(self):
        node = _make_rich_node(
            "host",
            extracted={"concept": "x" * 200},
            extra={
                "assessment_items": [
                    {
                        "id": "h",
                        "kind": "conceptual",
                        "prompt": "Q?",
                        "target_node_ids": ["missing"],
                    }
                ],
            },
        )
        graph = GraphSlice(nodes=(node,), edges=(), metadata={})
        req = _make_request()
        with _gate_open():
            with pytest.raises(AssessmentOrphanReferenceError) as exc_info:
                assessment_first_mode(graph, ["host"], req)
        assert isinstance(exc_info.value.issues, list)
        assert len(exc_info.value.issues) == 1


# ---------------------------------------------------------------------------
# Public/hidden separation (canary)
# ---------------------------------------------------------------------------


class TestPublicHiddenSeparation:
    """(closure-gate sensitive) Hidden_answer never leaks into prompt.

    The canary substring-checks every emitted item in both directions:
      - hidden_answer text MUST NOT appear in the prompt
      - prompt text MUST NOT appear in the hidden_answer
    """

    @pytest.mark.unit
    def test_canary_no_answer_leak_into_prompt(self):
        """The author-provided answer text must not appear in any prompt."""
        graph, ordered, answer_text = _graph_with_v21_hint_long_answer()
        req = _make_request()
        with _gate_open():
            result, _ = assessment_first_mode(graph, ordered, req)

        # At least one item must carry the hidden answer.
        with_answer = [it for it in result.assessment_items if it.hidden_answer]
        assert len(with_answer) >= 1, "Fixture failed to produce any item with hidden_answer"

        sentinel = "ZETA_SENTINEL_42"
        # Every item — answer-bearing or not — must not echo the sentinel in prompt.
        for item in result.assessment_items:
            assert sentinel not in item.prompt, (
                f"CANARY: hidden answer sentinel leaked into prompt of item {item.id!r}"
            )

    @pytest.mark.unit
    def test_canary_two_way_substring_separation(self):
        """For every item, neither field substring-contains the other (non-empty)."""
        graph, ordered, _ = _graph_with_v21_hint_long_answer()
        # Also include the rich four-kind node for breadth.
        rich_graph, _ = _graph_with_all_four_kinds()
        combined_nodes = tuple(list(graph.nodes) + list(rich_graph.nodes))
        merged = GraphSlice(nodes=combined_nodes, edges=(), metadata={})
        req = _make_request()
        with _gate_open():
            result, _ = assessment_first_mode(merged, ["beta", "alpha"], req)

        assert len(result.assessment_items) > 0
        for item in result.assessment_items:
            answer = item.hidden_answer
            prompt = item.prompt
            if answer and answer.strip():
                assert answer not in prompt, (
                    f"CANARY (forward): hidden_answer leaked into prompt of {item.id!r}"
                )
                # Reverse direction only if prompt is non-trivial (avoid trivial empty match).
                if prompt and prompt.strip():
                    assert prompt not in answer, (
                        f"CANARY (reverse): prompt leaked into hidden_answer of {item.id!r}"
                    )

    @pytest.mark.unit
    def test_heuristic_items_have_no_hidden_answer(self):
        """Pure-heuristic items never carry an answer key."""
        graph, ordered = _graph_with_all_four_kinds()
        req = _make_request()
        with _gate_open():
            result, _ = assessment_first_mode(graph, ordered, req)
        heuristic = [
            it for it in result.assessment_items
            if it.provenance.get("derived_from") == "heuristic"
        ]
        for item in heuristic:
            assert item.hidden_answer is None, (
                f"Heuristic item {item.id!r} unexpectedly carries hidden_answer"
            )

    @pytest.mark.unit
    def test_v21_hint_answer_preserved_on_item(self):
        """The v2.1 hint answer text is preserved verbatim on hidden_answer."""
        graph, ordered, answer_text = _graph_with_v21_hint_long_answer()
        req = _make_request()
        with _gate_open():
            result, _ = assessment_first_mode(graph, ordered, req)
        hinted = [
            it for it in result.assessment_items
            if it.provenance.get("derived_from") == "v21_hint"
        ]
        assert len(hinted) == 1
        assert hinted[0].hidden_answer == answer_text


# ---------------------------------------------------------------------------
# Weak-support warning (never raises)
# ---------------------------------------------------------------------------


class TestWeakSupportWarning:
    """Weak-support warning is recorded; the compiler never raises for it."""

    @pytest.mark.unit
    def test_weak_support_warning_emitted(self):
        # Node carries a v2.1 hint with an answer but TINY section content.
        node = _make_rich_node(
            "weak",
            extracted={"concept": "x"},  # 1 char — well under threshold
            extra={
                "assessment_items": [
                    {
                        "id": "weak::hint",
                        "kind": "conceptual",
                        "prompt": "Q?",
                        "answer": "An author-provided answer that isn't backed by sources.",
                        "target_node_ids": ["weak"],
                    }
                ],
            },
        )
        graph = GraphSlice(nodes=(node,), edges=(), metadata={})
        req = _make_request()
        with _gate_open():
            result, warnings = assessment_first_mode(graph, ["weak"], req)

        codes = [w.code for w in warnings]
        assert "assessment_weak_support" in codes

        # The warning must carry the item id as source_ref.
        weak = [w for w in warnings if w.code == "assessment_weak_support"]
        assert weak[0].source_ref == "weak::hint"

    @pytest.mark.unit
    def test_weak_support_does_not_raise(self):
        node = _make_rich_node(
            "weak",
            extracted={"concept": "x"},
            extra={
                "assessment_items": [
                    {
                        "id": "weak::hint",
                        "kind": "conceptual",
                        "prompt": "Q?",
                        "answer": "Answer.",
                        "target_node_ids": ["weak"],
                    }
                ],
            },
        )
        graph = GraphSlice(nodes=(node,), edges=(), metadata={})
        req = _make_request()
        with _gate_open():
            # No exception expected.
            result, warnings = assessment_first_mode(graph, ["weak"], req)
        assert isinstance(result, AssessmentFirstResult)

    @pytest.mark.unit
    def test_strong_support_emits_no_weak_warning(self):
        # Long concept content (well over threshold) plus a hinted answer.
        long_concept = "Plenty of source content. " * 20  # > 50 chars
        node = _make_rich_node(
            "strong",
            extracted={"concept": long_concept},
            extra={
                "assessment_items": [
                    {
                        "id": "strong::hint",
                        "kind": "conceptual",
                        "prompt": "Q?",
                        "answer": "Well-grounded answer.",
                        "target_node_ids": ["strong"],
                    }
                ],
            },
        )
        graph = GraphSlice(nodes=(node,), edges=(), metadata={})
        req = _make_request()
        with _gate_open():
            _, warnings = assessment_first_mode(graph, ["strong"], req)
        codes = [w.code for w in warnings]
        assert "assessment_weak_support" not in codes

    @pytest.mark.unit
    def test_no_answer_no_weak_warning(self):
        """Items without hidden_answer never trigger the weak-support warning."""
        graph, ordered = _graph_with_all_four_kinds()
        req = _make_request()
        with _gate_open():
            _, warnings = assessment_first_mode(graph, ordered, req)
        codes = [w.code for w in warnings]
        assert "assessment_weak_support" not in codes

    @pytest.mark.unit
    def test_threshold_constant_documented(self):
        """The threshold is exposed as a module-level constant for auditability."""
        assert isinstance(WEAK_SUPPORT_THRESHOLD_CHARS, int)
        assert WEAK_SUPPORT_THRESHOLD_CHARS > 0


# ---------------------------------------------------------------------------
# v2.1 hints consumed
# ---------------------------------------------------------------------------


class TestV21HintsConsumed:
    """v2.1 ``assessment_items`` metadata hints are consumed when present."""

    @pytest.mark.unit
    def test_hint_yields_item(self):
        graph, ordered, _ = _graph_with_v21_hint_long_answer()
        req = _make_request()
        with _gate_open():
            result, _ = assessment_first_mode(graph, ordered, req)
        ids = [it.id for it in result.assessment_items]
        assert "beta::hint-1" in ids

    @pytest.mark.unit
    def test_hint_provenance_records_derived_from(self):
        graph, ordered, _ = _graph_with_v21_hint_long_answer()
        req = _make_request()
        with _gate_open():
            result, _ = assessment_first_mode(graph, ordered, req)
        item = next(it for it in result.assessment_items if it.id == "beta::hint-1")
        assert item.provenance.get("derived_from") == "v21_hint"

    @pytest.mark.unit
    def test_hint_id_dedupes_against_heuristic(self):
        """When a hint has the same id as a heuristic item, only one is emitted."""
        node = _make_rich_node(
            "dup",
            extracted={"concept": "Lots of concept content here." * 4},
            extra={
                "assessment_items": [
                    {
                        # Same id heuristic would generate ("dup::conceptual").
                        "id": "dup::conceptual",
                        "kind": "conceptual",
                        "prompt": "Author-provided prompt",
                        "answer": "Author-provided answer."  # > 50 chars w/ section content
                        + " " * 10,
                        "target_node_ids": ["dup"],
                    }
                ],
            },
        )
        graph = GraphSlice(nodes=(node,), edges=(), metadata={})
        req = _make_request()
        with _gate_open():
            result, _ = assessment_first_mode(graph, ["dup"], req)
        # Exactly one item with that id — hint wins (processed first).
        matching = [it for it in result.assessment_items if it.id == "dup::conceptual"]
        assert len(matching) == 1
        assert matching[0].provenance.get("derived_from") == "v21_hint"

    @pytest.mark.unit
    def test_hint_with_unknown_kind_skipped(self):
        node = _make_rich_node(
            "u",
            extracted={"concept": "x" * 100},
            extra={
                "assessment_items": [
                    {
                        "id": "u::weird",
                        "kind": "essay",  # not one of the four
                        "prompt": "Q?",
                        "target_node_ids": ["u"],
                    }
                ],
            },
        )
        graph = GraphSlice(nodes=(node,), edges=(), metadata={})
        req = _make_request()
        with _gate_open():
            result, _ = assessment_first_mode(graph, ["u"], req)
        ids = [it.id for it in result.assessment_items]
        assert "u::weird" not in ids

    @pytest.mark.unit
    def test_hint_missing_required_fields_skipped(self):
        node = _make_rich_node(
            "m",
            extracted={"concept": "x" * 100},
            extra={
                "assessment_items": [
                    {"id": "no-kind", "prompt": "Q?"},
                    {"kind": "conceptual", "prompt": "no-id?"},
                    {"id": "no-prompt", "kind": "conceptual"},
                ],
            },
        )
        graph = GraphSlice(nodes=(node,), edges=(), metadata={})
        req = _make_request()
        with _gate_open():
            result, _ = assessment_first_mode(graph, ["m"], req)
        ids = [it.id for it in result.assessment_items]
        # None of the malformed hints should appear.
        assert "no-kind" not in ids
        assert "no-prompt" not in ids


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Two runs against the same graph produce byte-identical AssessmentItem lists."""

    def _items_to_json(self, items: list[AssessmentItem]) -> str:
        payload = [
            {
                "id": it.id,
                "kind": it.kind,
                "prompt": it.prompt,
                "hidden_answer": it.hidden_answer,
                "target_node_ids": list(it.target_node_ids),
                # Sort provenance keys for canonical comparison.
                "provenance": {k: it.provenance[k] for k in sorted(it.provenance)},
            }
            for it in items
        ]
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @pytest.mark.unit
    def test_byte_identical_output_two_runs(self):
        graph, ordered = _graph_with_all_four_kinds()
        req = _make_request()
        with _gate_open():
            r1, _ = assessment_first_mode(graph, ordered, req)
            r2, _ = assessment_first_mode(graph, ordered, req)
        assert self._items_to_json(r1.assessment_items) == self._items_to_json(
            r2.assessment_items
        )

    @pytest.mark.unit
    def test_items_sorted_by_kind_then_id(self):
        # Build a graph that produces multiple items spanning all kinds across
        # two nodes, so the sort key (kind, id) is exercised non-trivially.
        node_a = _make_rich_node(
            "a-node",
            extracted={
                "concept": "Concept content for A.",
                "derivation": "Derivation content for A.",
            },
        )
        node_b = _make_rich_node(
            "b-node",
            extracted={
                "concept": "Concept content for B.",
                "implementation": "def b():\n    return 1\n",
            },
        )
        graph = GraphSlice(nodes=(node_a, node_b), edges=(), metadata={})
        req = _make_request()
        with _gate_open():
            result, _ = assessment_first_mode(graph, ["a-node", "b-node"], req)

        # Canonical order: kind order × id order within each kind.
        kind_index = {
            "conceptual": 0,
            "derivation": 1,
            "coding": 2,
            "debugging": 3,
        }
        keys = [(kind_index[it.kind], it.id) for it in result.assessment_items]
        assert keys == sorted(keys), f"items not in canonical order: {keys}"

    @pytest.mark.unit
    def test_source_node_ids_sorted(self):
        node_a = _make_rich_node("zzz", extracted={"concept": "z"})
        node_b = _make_rich_node("aaa", extracted={"concept": "a"})
        graph = GraphSlice(nodes=(node_a, node_b), edges=(), metadata={})
        req = _make_request()
        with _gate_open():
            result, _ = assessment_first_mode(graph, ["zzz", "aaa"], req)
        assert result.source_node_ids == sorted(result.source_node_ids)


# ---------------------------------------------------------------------------
# Capability gate
# ---------------------------------------------------------------------------


class TestCapabilityGate:
    """assessment_first raises PreconditionError when the notebook extra is absent."""

    @pytest.mark.unit
    def test_raises_precondition_error_without_extra(self):
        graph, ordered = _graph_with_all_four_kinds()
        req = _make_request()
        original = importlib.util.find_spec

        def _absent(name: str, *args: Any, **kwargs: Any):
            if name == "nbformat":
                return None
            return original(name, *args, **kwargs)

        with patch("importlib.util.find_spec", side_effect=_absent):
            with pytest.raises(PreconditionError) as exc_info:
                assessment_first_mode(graph, ordered, req)
        assert exc_info.value.capability == "assessment_first"
        assert exc_info.value.extra == "notebook"

    @pytest.mark.unit
    def test_no_error_when_extra_present(self):
        graph, ordered = _graph_with_all_four_kinds()
        req = _make_request()
        with _gate_open():
            result, _ = assessment_first_mode(graph, ordered, req)
        assert isinstance(result, AssessmentFirstResult)


# ---------------------------------------------------------------------------
# Source canary: no forbidden patterns
# ---------------------------------------------------------------------------


class TestSourceCanary:
    """Canary: assessment_first.py contains no execution-at-compile-time patterns."""

    @pytest.mark.unit
    def test_no_exec_eval_subprocess_in_source(self):
        import re
        from pathlib import Path
        src_path = (
            Path(__file__).parent.parent
            / "src" / "akms_learn" / "modes" / "assessment_first.py"
        )
        src = src_path.read_text(encoding="utf-8")
        forbidden_patterns = [
            (r"\bexec\s*\(", "exec() call"),
            (r"\beval\s*\(", "eval() call"),
            (r"\bimport\s+subprocess\b|subprocess\s*\.", "subprocess import or call"),
            (r"%%run\b", "%run magic"),
            (r"\bimport\s+nbclient\b", "nbclient import"),
        ]
        for pattern, label in forbidden_patterns:
            assert not re.search(pattern, src), (
                f"assessment_first.py contains forbidden pattern ({label}): {pattern!r}"
            )

    @pytest.mark.unit
    def test_no_to_public_helper_on_model(self):
        """The AssessmentItem model exposes NO to_public() helper.

        The public/hidden separation is a closure-gate invariant: any helper
        that bundles prompt + hidden_answer into a single output is the
        easiest place to silently leak the answer key.  Enforce by source-grep
        that no such method exists on the model class.
        """
        from pathlib import Path
        src_path = (
            Path(__file__).parent.parent
            / "src" / "akms_learn" / "models" / "assessment.py"
        )
        src = src_path.read_text(encoding="utf-8")
        assert "def to_public" not in src
        assert "def render_for_export" not in src

    @pytest.mark.unit
    def test_compiler_never_assigns_answer_into_prompt(self):
        """Static check: the compiler source never writes hidden_answer onto a prompt field."""
        from pathlib import Path
        src_path = (
            Path(__file__).parent.parent
            / "src" / "akms_learn" / "modes" / "assessment_first.py"
        )
        src = src_path.read_text(encoding="utf-8")
        # Crude but effective: no construction of an AssessmentItem where the
        # prompt= keyword arg references hidden_answer.
        # We check by ensuring "prompt=hidden_answer" and "prompt = hidden_answer"
        # never appear in source, and that no f-string concatenates the two
        # known field names.
        forbidden_substrings = [
            "prompt=hidden_answer",
            "prompt = hidden_answer",
            "{hidden_answer}",
            "{item.hidden_answer}",
        ]
        for snippet in forbidden_substrings:
            assert snippet not in src, (
                f"CANARY: forbidden cross-field reference {snippet!r} in compiler source"
            )


# ---------------------------------------------------------------------------
# Compiler wiring (run_pipeline) — assessments + references populate the body
# ---------------------------------------------------------------------------


class TestCompilerWiresAssessmentsAndReferences:
    """Previously compiler.py hardcoded assessments=[] and references=[]."""

    @pytest.mark.unit
    def test_assessment_first_populates_body_assessments(self):
        """compile_learning_source surfaces assessment_first items in the body."""
        graph, _ = _graph_with_all_four_kinds()
        req = _make_request()
        with _gate_open():
            result = compile_learning_source(request=req, graph_slice=graph)
        body = result.packet.body
        assert body.assessments, "assessment_first must emit items via the compiler"
        kinds = {a.model_dump().get("kind") for a in body.assessments}
        assert kinds == set(ASSESSMENT_ITEM_KINDS)
        # Every item anchors to a node that survived into the packet (no orphans).
        node_ids = {n.node_id for n in body.nodes}
        for a in body.assessments:
            for tid in a.model_dump().get("target_node_ids", ()):
                assert tid in node_ids

    @pytest.mark.unit
    def test_non_assessment_mode_emits_no_assessments(self):
        """The assessment block is gated on the assessment_first strategy."""
        graph, _ = _graph_with_all_four_kinds()
        req = _make_request(generation_option="default")
        with _gate_open():
            result = compile_learning_source(request=req, graph_slice=graph)
        assert result.packet.body.assessments == []

    @pytest.mark.unit
    def test_references_derived_from_references_section(self):
        """References section content becomes ReferenceView entries in the body."""
        node = _make_rich_node(
            "refnode",
            extra={
                "markdown": (
                    "## Implementation\nthe code\n\n"
                    "## References\n"
                    "- Smith 2020 — A foundational paper\n"
                    "- Jones 2019 — A follow-up\n"
                ),
            },
        )
        graph = GraphSlice(nodes=(node,), edges=(), metadata={})
        req = _make_request(generation_option="default")
        result = compile_learning_source(request=req, graph_slice=graph)
        citations = [r.citation for r in result.packet.body.references]
        assert any("Smith 2020" in (c or "") for c in citations)
        assert any("Jones 2019" in (c or "") for c in citations)
        # Bullet markers are stripped; provenance points back at the node.
        assert all(not (c or "").startswith("-") for c in citations)
        assert all(r.source_node_ids == ["refnode"] for r in result.packet.body.references)

    @pytest.mark.unit
    def test_references_empty_when_no_references_section(self):
        """A node without a References section contributes nothing (baseline-safe)."""
        node = _make_rich_node(
            "plain", extra={"markdown": "## Implementation\njust code, no refs\n"}
        )
        graph = GraphSlice(nodes=(node,), edges=(), metadata={})
        req = _make_request(generation_option="default")
        result = compile_learning_source(request=req, graph_slice=graph)
        assert result.packet.body.references == []
