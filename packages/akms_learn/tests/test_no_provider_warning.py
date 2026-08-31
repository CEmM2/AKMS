"""The no-provider degraded mode is reported, never silent.

When a caller enables LLM expansion but no provider is configured,
auto-selection lands on the deterministic no-provider stub. The stub still
runs (its output is clearly labeled in provenance), but the mode must emit an
``llm_no_provider_configured`` warning so the degradation is visible — a
caller asked for expansion and did not get provider output.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from akms_learn.graph_import import GraphSlice
from akms_learn.llm.no_provider_stub import NO_PROVIDER_STUB_GENERATOR
from akms_learn.modes.llm_expanded import LLMExpansionRequest, llm_expanded_mode
from akms_learn.requests import LearningRequest


def _invoke(cfg: LLMExpansionRequest):
    slice_ = GraphSlice(nodes=[{"node_id": "n1"}], edges=[])
    request = LearningRequest(
        topic="t", goal="g", generation_option="deterministic_outline"
    )
    return llm_expanded_mode(slice_, ["n1"], request, expansion_request=cfg)


@pytest.mark.unit
def test_enabled_with_nothing_configured_warns():
    cfg = LLMExpansionRequest(enable_llm=True)  # provider left at stub default
    with patch(
        "akms_learn.modes.llm_expanded.resolve_default_provider",
        return_value=NO_PROVIDER_STUB_GENERATOR,
    ):
        result, warnings = _invoke(cfg)

    codes = [w.code for w in warnings]
    assert "llm_no_provider_configured" in codes
    w = next(w for w in warnings if w.code == "llm_no_provider_configured")
    assert w.severity == "warning"
    assert "no provider is configured" in w.message
    # The warning also rides on the result object.
    assert "llm_no_provider_configured" in [w.code for w in result.warnings]


@pytest.mark.unit
def test_disabled_emits_no_warning():
    cfg = LLMExpansionRequest(enable_llm=False)
    result, warnings = _invoke(cfg)
    assert warnings == []
    assert result.warnings == []


@pytest.mark.unit
def test_real_provider_selected_emits_no_such_warning():
    """Auto-selection resolving to a real provider must not carry the warning."""
    cfg = LLMExpansionRequest(enable_llm=True)
    with patch(
        "akms_learn.modes.llm_expanded.resolve_default_provider",
        return_value="akms",
    ), patch("akms_learn.modes.llm_expanded.require_capability"), patch(
        "akms_learn.modes.llm_expanded.resolve",
        return_value=lambda topic, ids, policy, *, sources=None: [],
    ):
        _, warnings = _invoke(cfg)
    assert "llm_no_provider_configured" not in [w.code for w in warnings]
