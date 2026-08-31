"""Tests for ``llm_expanded`` compiler mode.

Covers all five acceptance criteria:

Deterministic LSP captured before any LLM call; byte-identical to
      disabled-LLM output.
LLMExpansionPolicy has exactly {source_locked, explanatory_only,
      no_new_claims}.
generated_sections entries carry generator id, model,
      source_node_ids, validation_status, content_hash.
Citations outside packet.nodes are rejected (validation_status
      reflects failure; warning emitted; rejected sections NOT included in
      final generated_sections).
With LLM disabled OR ``llm`` extra absent for an external provider,
      compiler returns the deterministic LSP unchanged.

Additional tests:
  - Strategy registered as ``"llm_expanded"`` in ordering registry.
  - Plugin reports ``"llm_expanded"`` capability AFTER existing entries.
  - Canary: every code path that attaches a GeneratedSection runs the
    citation validator first (injecting an orphan citation never leaks
    into the final packet).
  - no_provider_stub is deterministic (two runs => byte-identical
    content_hashes).
  - Hash is SHA-256 of the canonical (id, source_node_ids, content)
    triple — provider/model changes do not perturb it.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import akms_learn.capability_gates as _cap_gates
import pytest
from akms_learn.capability_gates import PreconditionError
from akms_learn.graph_import import GraphSlice
from akms_learn.llm.no_provider_stub import (
    NO_PROVIDER_STUB_GENERATOR,
    NO_PROVIDER_STUB_MODEL,
    no_provider_stub,
)
from akms_learn.models import (
    LLM_EXPANSION_POLICIES,
    LLM_VALIDATION_STATUSES,
    GeneratedSection,
    compute_content_hash,
)
from akms_learn.modes.llm_expanded import (
    LLMExpansionRequest,
    llm_expanded_mode,
)
from akms_learn.ordering import get_strategy, list_strategies, order_nodes
from akms_learn.plugin import get_plugin
from akms_learn.requests import LearningRequest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(**overrides: Any) -> LearningRequest:
    defaults: dict[str, Any] = dict(
        topic="toy llm-expanded lesson",
        goal="Exercise the llm_expanded compiler mode.",
        audience="engineer",
        depth="implementation",
        generation_option="llm_expanded",
        seed_tags=[],
        exporters=[],
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


def _make_node(node_id: str, **extra: Any) -> dict[str, Any]:
    node: dict[str, Any] = {
        "node_id": node_id,
        "title": f"Node {node_id}",
        "kind": "core_concept",
        "domain": "toy",
        "subdomain": "sub",
        "tags": [],
        "status": "established",
        "source_path": f"toy://{node_id}.md",
        "line_range": [1, 10],
    }
    node.update(extra)
    return node


def _toy_graph() -> tuple[GraphSlice, list[str]]:
    """Three-node toy graph used by most tests."""
    nodes = [_make_node("alpha"), _make_node("beta"), _make_node("gamma")]
    slice_ = GraphSlice(nodes=tuple(nodes), edges=(), metadata={})
    return slice_, ["alpha", "beta", "gamma"]


def _canonical_json(payload: Any) -> str:
    """Canonical JSON dump used for byte-identical assertions."""
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


@contextmanager
def _gate_open():
    """Patch ``probe_optional_extras`` so the ``llm`` extra reports installed.

    The ``llm`` extra uses ``None`` as its probe package (intentionally always
    absent), so patching ``find_spec`` is insufficient.  This helper mirrors
    the pattern from the adaptive_path test suite.
    """
    original_probe = _cap_gates.probe_optional_extras

    def _patched_probe() -> dict[str, bool]:
        result = original_probe()
        result["llm"] = True
        return result

    with patch.object(_cap_gates, "probe_optional_extras", side_effect=_patched_probe):
        yield


# ---------------------------------------------------------------------------
# LLMExpansionPolicy enum
# ---------------------------------------------------------------------------


class TestPolicyEnum:
    """LLMExpansionPolicy has exactly three values."""

    @pytest.mark.unit
    def test_policy_values_exact(self):
        assert set(LLM_EXPANSION_POLICIES) == {
            "source_locked",
            "explanatory_only",
            "no_new_claims",
        }

    @pytest.mark.unit
    def test_policy_count_is_three(self):
        assert len(LLM_EXPANSION_POLICIES) == 3

    @pytest.mark.unit
    def test_validation_status_values_exact(self):
        assert set(LLM_VALIDATION_STATUSES) == {
            "valid",
            "rejected_orphan_citation",
            "rejected_policy",
        }


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegistration:
    """Mode is registered in ordering + plugin capabilities."""

    @pytest.mark.unit
    def test_ordering_strategy_registered(self):
        strategy = get_strategy("llm_expanded")
        assert callable(strategy)

    @pytest.mark.unit
    def test_strategy_in_list_strategies(self):
        assert "llm_expanded" in list_strategies()

    @pytest.mark.unit
    def test_plugin_reports_capability(self):
        assert "llm_expanded" in get_plugin().capabilities()

    @pytest.mark.unit
    def test_capability_appears_after_existing_entries(self):
        caps = get_plugin().capabilities()
        idx_af = caps.index("assessment_first")
        idx_le = caps.index("llm_expanded")
        assert idx_le > idx_af

    @pytest.mark.unit
    def test_strategy_uses_default_ordering(self):
        graph, _ = _toy_graph()
        strategy = get_strategy("llm_expanded")
        s_nodes, _ = strategy(graph)
        d_nodes, _ = order_nodes(graph)
        assert s_nodes == d_nodes


# ---------------------------------------------------------------------------
# Deterministic packet captured first; LLM-disabled is identical
# ---------------------------------------------------------------------------


class TestDeterministicBaseline:
    """Deterministic LSP captured before any LLM call; disabled path identical."""

    @pytest.mark.unit
    def test_pre_expansion_packet_populated(self):
        graph, ordered = _toy_graph()
        result, _ = llm_expanded_mode(graph, ordered, _make_request())
        assert result.pre_expansion_packet is not None
        assert set(result.pre_expansion_packet["node_ids"]) == {
            "alpha",
            "beta",
            "gamma",
        }

    @pytest.mark.unit
    def test_disabled_returns_byte_identical_packet(self):
        graph, ordered = _toy_graph()
        # LLM disabled by default — packet must equal pre_expansion_packet.
        result, _ = llm_expanded_mode(graph, ordered, _make_request())
        assert _canonical_json(result.packet) == _canonical_json(
            result.pre_expansion_packet
        )

    @pytest.mark.unit
    def test_disabled_has_no_generated_sections_key(self):
        graph, ordered = _toy_graph()
        result, _ = llm_expanded_mode(graph, ordered, _make_request())
        assert "generated_sections" not in result.packet

    @pytest.mark.unit
    def test_disabled_policy_is_none(self):
        graph, ordered = _toy_graph()
        result, _ = llm_expanded_mode(graph, ordered, _make_request())
        assert result.policy is None

    @pytest.mark.unit
    def test_two_consecutive_runs_byte_identical_disabled(self):
        graph, ordered = _toy_graph()
        r1, _ = llm_expanded_mode(graph, ordered, _make_request())
        r2, _ = llm_expanded_mode(graph, ordered, _make_request())
        assert _canonical_json(r1.packet) == _canonical_json(r2.packet)

    @pytest.mark.unit
    def test_pre_expansion_packet_byte_stable(self):
        graph, ordered = _toy_graph()
        r1, _ = llm_expanded_mode(graph, ordered, _make_request())
        r2, _ = llm_expanded_mode(graph, ordered, _make_request())
        assert _canonical_json(r1.pre_expansion_packet) == _canonical_json(
            r2.pre_expansion_packet
        )

    @pytest.mark.unit
    def test_pre_expansion_packet_no_timestamp(self):
        """No timestamp / non-deterministic field appears in the packet."""
        graph, ordered = _toy_graph()
        result, _ = llm_expanded_mode(graph, ordered, _make_request())
        # Whitelist of allowed top-level keys in the deterministic packet.
        assert set(result.pre_expansion_packet.keys()) == {
            "nodes",
            "node_ids",
            "reading_order",
            "edge_ids",
        }


class TestLLMDisabledPath:
    """When LLM is not enabled, no provider call is ever made."""

    @pytest.mark.unit
    def test_no_provider_called_when_disabled(self):
        graph, ordered = _toy_graph()
        with patch("akms_learn.modes.llm_expanded.resolve") as resolve_mock:
            llm_expanded_mode(graph, ordered, _make_request())
            resolve_mock.assert_not_called()

    @pytest.mark.unit
    def test_no_provider_called_when_llm_allowed_false(self):
        """A node carrying ``llm_allowed=False`` short-circuits before the provider."""
        node = _make_node("alpha", llm_allowed=False)
        graph = GraphSlice(nodes=(node,), edges=(), metadata={})
        with patch("akms_learn.modes.llm_expanded.resolve") as resolve_mock:
            result, _ = llm_expanded_mode(
                graph,
                ["alpha"],
                _make_request(),
                expansion_request=LLMExpansionRequest(enable_llm=True),
            )
            resolve_mock.assert_not_called()
        # Packet is still byte-identical to the deterministic baseline.
        assert _canonical_json(result.packet) == _canonical_json(
            result.pre_expansion_packet
        )


# ---------------------------------------------------------------------------
# Stub provider: determinism + content_hash
# ---------------------------------------------------------------------------


class TestNoProviderStub:
    """The built-in stub is deterministic and source-locked by construction."""

    @pytest.mark.unit
    def test_one_section_per_active_node(self):
        sections = no_provider_stub(
            topic="t", active_node_ids=["alpha", "beta", "gamma"]
        )
        assert len(sections) == 3
        assert sorted(s.source_node_ids[0] for s in sections) == [
            "alpha",
            "beta",
            "gamma",
        ]

    @pytest.mark.unit
    def test_sections_sorted_by_source_node_id(self):
        sections = no_provider_stub(
            topic="t", active_node_ids=["gamma", "alpha", "beta"]
        )
        ids = [s.source_node_ids[0] for s in sections]
        assert ids == sorted(ids)

    @pytest.mark.unit
    def test_dedup_input(self):
        sections = no_provider_stub(
            topic="t", active_node_ids=["alpha", "alpha", "beta"]
        )
        assert len(sections) == 2

    @pytest.mark.unit
    def test_generator_and_model_populated(self):
        sections = no_provider_stub(topic="t", active_node_ids=["alpha"])
        assert sections[0].generator == NO_PROVIDER_STUB_GENERATOR
        assert sections[0].model == NO_PROVIDER_STUB_MODEL

    @pytest.mark.unit
    def test_content_hash_stable_across_runs(self):
        s1 = no_provider_stub(topic="t1", active_node_ids=["alpha", "beta"])
        s2 = no_provider_stub(topic="t1", active_node_ids=["alpha", "beta"])
        assert [s.content_hash for s in s1] == [s.content_hash for s in s2]

    @pytest.mark.unit
    def test_content_hash_changes_with_topic(self):
        s1 = no_provider_stub(topic="t1", active_node_ids=["alpha"])
        s2 = no_provider_stub(topic="t2", active_node_ids=["alpha"])
        assert s1[0].content_hash != s2[0].content_hash

    @pytest.mark.unit
    def test_content_hash_matches_canonical_formula(self):
        sections = no_provider_stub(topic="hello", active_node_ids=["alpha"])
        s = sections[0]
        expected = compute_content_hash(
            section_id=s.id,
            source_node_ids=s.source_node_ids,
            content=s.content,
        )
        assert s.content_hash == expected

    @pytest.mark.unit
    def test_stub_returns_only_valid_status(self):
        sections = no_provider_stub(topic="t", active_node_ids=["alpha"])
        assert all(s.validation_status == "valid" for s in sections)


# ---------------------------------------------------------------------------
# GeneratedSection fields
# ---------------------------------------------------------------------------


class TestGeneratedSectionFields:
    """Generated_sections carry generator, model, source_node_ids,
    validation_status, content_hash."""

    @pytest.mark.unit
    def test_all_required_fields_present(self):
        graph, ordered = _toy_graph()
        result, _ = llm_expanded_mode(
            graph,
            ordered,
            _make_request(),
            expansion_request=LLMExpansionRequest(enable_llm=True),
        )
        assert len(result.generated_sections) == 3
        for section in result.generated_sections:
            assert section.id
            assert section.generator == NO_PROVIDER_STUB_GENERATOR
            assert section.model == NO_PROVIDER_STUB_MODEL
            assert section.source_node_ids
            assert section.validation_status == "valid"
            assert section.content_hash
            assert len(section.content_hash) == 64  # SHA-256 hex digest

    @pytest.mark.unit
    def test_generated_sections_attached_to_packet_dict(self):
        graph, ordered = _toy_graph()
        result, _ = llm_expanded_mode(
            graph,
            ordered,
            _make_request(),
            expansion_request=LLMExpansionRequest(enable_llm=True),
        )
        assert "generated_sections" in result.packet
        sections = result.packet["generated_sections"]
        assert isinstance(sections, list)
        assert len(sections) == 3
        for s in sections:
            assert {
                "id",
                "generator",
                "model",
                "source_node_ids",
                "validation_status",
                "content_hash",
                "content",
            }.issubset(s.keys())


# ---------------------------------------------------------------------------
# Source-locking — citations must be in packet.nodes
# ---------------------------------------------------------------------------


class TestSourceLocking:
    """Rejected citations never appear in the final generated_sections."""

    @pytest.mark.unit
    def test_orphan_citation_rejected_and_excluded(self):
        """Inject a GeneratedSection citing a node id outside the packet.

        Expectation: section is NOT attached to the final LSP, and one
        ``llm_citation_outside_packet`` warning is emitted with the section
        id as ``source_ref``.
        """
        graph, ordered = _toy_graph()

        orphan_section = GeneratedSection(
            id="malicious::orphan",
            generator="canary_injector",
            model="canary-v1",
            source_node_ids=("ZZZ_NOT_IN_PACKET",),
            validation_status="valid",
            content_hash=compute_content_hash(
                section_id="malicious::orphan",
                source_node_ids=("ZZZ_NOT_IN_PACKET",),
                content="orphan content",
            ),
            content="orphan content",
        )

        # Patch the stub to additionally return the orphan section.
        original_stub = no_provider_stub

        def _injecting_stub(topic, active_node_ids, policy=None, *, sources=None):
            return original_stub(topic=topic, active_node_ids=active_node_ids) + [
                orphan_section
            ]

        with patch(
            "akms_learn.modes.llm_expanded.resolve", return_value=_injecting_stub
        ):
            result, warnings = llm_expanded_mode(
                graph,
                ordered,
                _make_request(),
                expansion_request=LLMExpansionRequest(enable_llm=True),
            )

        # Section MUST NOT appear in the final packet or model list.
        attached_ids = {s.id for s in result.generated_sections}
        assert "malicious::orphan" not in attached_ids
        packet_ids = {s["id"] for s in result.packet.get("generated_sections", [])}
        assert "malicious::orphan" not in packet_ids

        # Exactly one warning emitted, naming the rejected section.
        orphan_warnings = [
            w for w in warnings if w.code == "llm_citation_outside_packet"
        ]
        assert len(orphan_warnings) == 1
        assert orphan_warnings[0].source_ref == "malicious::orphan"
        assert "ZZZ_NOT_IN_PACKET" in orphan_warnings[0].message

    @pytest.mark.unit
    def test_mixed_valid_and_orphan_only_valid_survives(self):
        graph, ordered = _toy_graph()

        orphan_section = GeneratedSection(
            id="x::orphan",
            generator="canary_injector",
            model="canary-v1",
            source_node_ids=("alpha", "ZZZ_NOT_IN_PACKET"),  # mixed
            validation_status="valid",
            content_hash="0" * 64,
            content="mixed",
        )
        valid_section = GeneratedSection(
            id="x::valid",
            generator="canary_injector",
            model="canary-v1",
            source_node_ids=("alpha",),
            validation_status="valid",
            content_hash="1" * 64,
            content="valid",
        )

        def _injecting_stub(topic, active_node_ids, policy=None, *, sources=None):
            return [valid_section, orphan_section]

        with patch(
            "akms_learn.modes.llm_expanded.resolve", return_value=_injecting_stub
        ):
            result, _ = llm_expanded_mode(
                graph,
                ordered,
                _make_request(),
                expansion_request=LLMExpansionRequest(enable_llm=True),
            )

        ids = {s.id for s in result.generated_sections}
        assert "x::valid" in ids
        assert "x::orphan" not in ids

    @pytest.mark.unit
    def test_canary_no_bypass_branch(self):
        """Even when every section is orphan, the final packet has zero sections.

        This is the closure-gate test: there must be NO code path that
        attaches a GeneratedSection without running the validator.
        """
        graph, ordered = _toy_graph()

        bad_section = GeneratedSection(
            id="all::bad",
            generator="canary_injector",
            model="canary-v1",
            source_node_ids=("ZZZ_NOT_IN_PACKET",),
            validation_status="valid",
            content_hash="2" * 64,
            content="bad",
        )

        with patch(
            "akms_learn.modes.llm_expanded.resolve",
            return_value=lambda topic, active_node_ids, policy=None, *, sources=None: [
                bad_section
            ],
        ):
            result, _ = llm_expanded_mode(
                graph,
                ordered,
                _make_request(),
                expansion_request=LLMExpansionRequest(enable_llm=True),
            )

        assert result.generated_sections == []
        assert result.packet.get("generated_sections") == []


# ---------------------------------------------------------------------------
# External provider absent — fall back to deterministic packet
# ---------------------------------------------------------------------------


class TestExternalProviderAbsent:
    """External provider requested but ``llm`` extra absent → PreconditionError."""

    @pytest.mark.unit
    def test_external_provider_raises_when_llm_extra_absent(self):
        graph, ordered = _toy_graph()
        with pytest.raises(PreconditionError) as exc_info:
            llm_expanded_mode(
                graph,
                ordered,
                _make_request(),
                expansion_request=LLMExpansionRequest(
                    enable_llm=True, provider="acme_llm"
                ),
            )
        assert exc_info.value.capability == "llm_expanded"
        assert exc_info.value.extra == "llm"

    @pytest.mark.unit
    def test_external_provider_with_gate_open_falls_back(self):
        """Gate open but provider not wired → deterministic-packet fallback + warning."""
        graph, ordered = _toy_graph()
        with _gate_open():
            result, warnings = llm_expanded_mode(
                graph,
                ordered,
                _make_request(),
                expansion_request=LLMExpansionRequest(
                    enable_llm=True, provider="acme_llm"
                ),
            )
        assert result.generated_sections == []
        assert _canonical_json(result.packet) == _canonical_json(
            result.pre_expansion_packet
        )
        assert any(w.code == "llm_provider_unavailable" for w in warnings)


# ---------------------------------------------------------------------------
# Determinism of generated_sections list (byte-identical across runs)
# ---------------------------------------------------------------------------


class TestEnabledDeterminism:
    """Two LLM-enabled runs produce byte-identical packets."""

    @pytest.mark.unit
    def test_two_enabled_runs_byte_identical(self):
        graph, ordered = _toy_graph()
        r1, _ = llm_expanded_mode(
            graph,
            ordered,
            _make_request(),
            expansion_request=LLMExpansionRequest(enable_llm=True),
        )
        r2, _ = llm_expanded_mode(
            graph,
            ordered,
            _make_request(),
            expansion_request=LLMExpansionRequest(enable_llm=True),
        )
        assert _canonical_json(r1.packet) == _canonical_json(r2.packet)

    @pytest.mark.unit
    def test_content_hashes_stable_across_compilations(self):
        graph, ordered = _toy_graph()
        r1, _ = llm_expanded_mode(
            graph,
            ordered,
            _make_request(),
            expansion_request=LLMExpansionRequest(enable_llm=True),
        )
        r2, _ = llm_expanded_mode(
            graph,
            ordered,
            _make_request(),
            expansion_request=LLMExpansionRequest(enable_llm=True),
        )
        h1 = [s.content_hash for s in r1.generated_sections]
        h2 = [s.content_hash for s in r2.generated_sections]
        assert h1 == h2


# ---------------------------------------------------------------------------
# Policy resolution from v2.1 hints
# ---------------------------------------------------------------------------


class TestPolicyResolution:
    """v2.1 ``expansion_policy`` hint flows into the result.policy."""

    @pytest.mark.unit
    def test_node_hint_picks_up_policy(self):
        node = _make_node("alpha", expansion_policy="explanatory_only")
        graph = GraphSlice(nodes=(node,), edges=(), metadata={})
        result, _ = llm_expanded_mode(
            graph,
            ["alpha"],
            _make_request(),
            expansion_request=LLMExpansionRequest(enable_llm=True),
        )
        assert result.policy == "explanatory_only"

    @pytest.mark.unit
    def test_explicit_policy_overrides_hint(self):
        node = _make_node("alpha", expansion_policy="explanatory_only")
        graph = GraphSlice(nodes=(node,), edges=(), metadata={})
        result, _ = llm_expanded_mode(
            graph,
            ["alpha"],
            _make_request(),
            expansion_request=LLMExpansionRequest(
                enable_llm=True, policy="no_new_claims"
            ),
        )
        assert result.policy == "no_new_claims"

    @pytest.mark.unit
    def test_default_policy_is_source_locked(self):
        graph, ordered = _toy_graph()
        result, _ = llm_expanded_mode(
            graph,
            ordered,
            _make_request(),
            expansion_request=LLMExpansionRequest(enable_llm=True),
        )
        assert result.policy == "source_locked"


# ---------------------------------------------------------------------------
# Provenance block on the final packet
# ---------------------------------------------------------------------------


class TestProvenance:
    @pytest.mark.unit
    def test_llm_provenance_populated_when_enabled(self):
        graph, ordered = _toy_graph()
        result, _ = llm_expanded_mode(
            graph,
            ordered,
            _make_request(),
            expansion_request=LLMExpansionRequest(enable_llm=True),
        )
        llm_prov = result.packet["provenance"]["llm"]
        assert llm_prov["provider"] == NO_PROVIDER_STUB_GENERATOR
        assert llm_prov["policy"] == "source_locked"
        assert llm_prov["section_count"] == 3
        assert llm_prov["rejected_count"] == 0

    @pytest.mark.unit
    def test_provenance_absent_when_disabled(self):
        graph, ordered = _toy_graph()
        result, _ = llm_expanded_mode(graph, ordered, _make_request())
        assert "provenance" not in result.packet


# ---------------------------------------------------------------------------
# Source canary: no execution-at-compile-time patterns
# ---------------------------------------------------------------------------


class TestSourceCanaries:
    """The mode source MUST NOT call subprocess/exec/eval/network."""

    @pytest.mark.unit
    def test_no_execution_patterns_in_source(self):
        """Inspect the module's AST: no import / call of forbidden runtime modules."""
        import ast
        from pathlib import Path

        src = (
            Path(__file__).parent.parent
            / "src"
            / "akms_learn"
            / "modes"
            / "llm_expanded.py"
        )
        tree = ast.parse(src.read_text(encoding="utf-8"))

        forbidden_modules = {
            "subprocess",
            "nbclient",
            "requests",
            "urllib",
            "urllib.request",
            "socket",
        }
        forbidden_calls = {"exec", "eval", "__import__", "compile"}

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    assert top not in forbidden_modules, (
                        f"llm_expanded.py imports forbidden module {alias.name!r}"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    top = node.module.split(".")[0]
                    assert top not in forbidden_modules, (
                        f"llm_expanded.py from-imports forbidden module {node.module!r}"
                    )
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id not in forbidden_calls, (
                        f"llm_expanded.py calls forbidden function {node.func.id!r}"
                    )


@pytest.mark.unit
def test_registered_provider_dispatched_through_registry():
    """A non-stub provider registered by name is resolved and invoked by the mode.

    Provider-registry integration coverage: exercises the real registry resolve()-then-call
    dispatch path (not a patched resolve).
    """
    from akms_learn.llm.registry import register

    sentinel = GeneratedSection(
        id="alpha::custom",
        generator="testprov_p1_1",
        model="m",
        source_node_ids=("alpha",),
        validation_status="valid",
        content_hash="3" * 64,
        content="custom provider output",
    )

    def _prov(topic, active_node_ids, policy, *, sources=None):
        return [sentinel]

    register("testprov_p1_1", _prov)
    graph, ordered = _toy_graph()
    with _gate_open():
        result, _ = llm_expanded_mode(
            graph,
            ordered,
            _make_request(),
            expansion_request=LLMExpansionRequest(
                enable_llm=True, provider="testprov_p1_1"
            ),
        )
    assert any(s.id == "alpha::custom" for s in result.generated_sections)
