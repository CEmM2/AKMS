"""Tests for baked-in notebook/html extras + default-provider auto-selection.

PART 1 — nbformat/jinja2 are now BASE dependencies, so the notebook/html
capabilities (assessment_first, quiz_export, html_export, notebook_source,
notebook_export) report available by default.

PART 2 — :func:`resolve_default_provider` picks a provider by precedence when
the caller names none explicitly: configured nlm grounded → akms completion
(API key) → no_provider_stub. An explicitly-named provider always wins.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from akms_learn.capability_gates import build_capability_gate, probe_optional_extras
from akms_learn.llm.no_provider_stub import NO_PROVIDER_STUB_GENERATOR
from akms_learn.llm.registry import resolve_default_provider

# Every env var that can flip auto-selection — cleared before each precedence test.
_ALL_PROVIDER_ENV = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "NLM_NOTEBOOK_ID",
    "AKMS_LEARN_NLM_NOTEBOOK_ID",
)

_NLM_NAME = "nlm"
_AKMS_NAME = "akms"


# ---------------------------------------------------------------------------
# PART 1 — notebook/html capabilities available by default
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNotebookHtmlCapabilitiesDefaultOn:
    """nbformat/jinja2 are now base deps, so their capabilities are on by default."""

    def test_nbformat_and_jinja2_importable_by_default(self):
        """The backing modules are importable in the default install."""
        extras = probe_optional_extras()
        assert extras["notebook"] is True
        assert extras["html"] is True

    def test_notebook_capabilities_available_by_default(self):
        """assessment_first / notebook_source / notebook_export are on by default."""
        gate = build_capability_gate()
        assert gate.assessment_first is True
        assert gate.notebook_source is True
        assert gate.notebook_export is True

    def test_html_capabilities_available_by_default(self):
        """quiz_export / html_export are on by default."""
        gate = build_capability_gate()
        assert gate.quiz_export is True
        assert gate.html_export is True

    def test_llm_capabilities_still_gated_by_provider(self):
        """The llm gate is NOT weakened: no provider configured -> llm modes closed."""
        with patch(
            "akms_learn.capability_gates._llm_provider_configured", return_value=False
        ):
            gate = build_capability_gate()
        assert gate.llm_expanded is False
        assert gate.adaptive_path is False
        # notebook/html stay on regardless of the llm route.
        assert gate.assessment_first is True
        assert gate.html_export is True


# ---------------------------------------------------------------------------
# PART 2 — resolve_default_provider precedence
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveDefaultProvider:
    """Precedence: nlm-configured -> nlm; key-only -> akms; nothing -> stub."""

    def _clear_env(self, monkeypatch):
        for var in _ALL_PROVIDER_ENV:
            monkeypatch.delenv(var, raising=False)

    def test_nothing_configured_falls_back_to_stub(self, monkeypatch):
        """No env, no CLI -> the always-safe no_provider_stub."""
        self._clear_env(monkeypatch)
        with patch("shutil.which", return_value=None):
            assert resolve_default_provider() == NO_PROVIDER_STUB_GENERATOR

    def test_completion_api_key_selects_akms(self, monkeypatch):
        """A completion API key (no nlm) -> the akms completion provider."""
        self._clear_env(monkeypatch)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with patch("shutil.which", return_value=None):
            assert resolve_default_provider() == _AKMS_NAME

    def test_nlm_configured_selects_nlm(self, monkeypatch):
        """A configured notebook env AND nlm CLI on PATH -> the nlm grounded provider."""
        self._clear_env(monkeypatch)
        monkeypatch.setenv("NLM_NOTEBOOK_ID", "nb-1")
        # nlm_cli.register_nlm_provider() registers only when the CLI is present;
        # patch shutil.which so the (re)import-time registration succeeds.
        with patch("shutil.which", return_value="/usr/bin/nlm"):
            # Force re-registration under the patched PATH.
            import akms_learn.llm.providers.nlm_cli as nlm_mod

            nlm_mod.register_nlm_provider()
            assert resolve_default_provider() == _NLM_NAME

    def test_nlm_precedence_over_completion_key(self, monkeypatch):
        """nlm configured wins over a completion key (precedence order)."""
        self._clear_env(monkeypatch)
        monkeypatch.setenv("NLM_NOTEBOOK_ID", "nb-1")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        with patch("shutil.which", return_value="/usr/bin/nlm"):
            import akms_learn.llm.providers.nlm_cli as nlm_mod

            nlm_mod.register_nlm_provider()
            assert resolve_default_provider() == _NLM_NAME

    def test_nlm_env_without_cli_falls_through_to_key(self, monkeypatch):
        """nlm notebook env but no CLI -> nlm route declined; completion key wins."""
        self._clear_env(monkeypatch)
        monkeypatch.setenv("NLM_NOTEBOOK_ID", "nb-1")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
        # Drop any prior nlm registration so the absent-CLI path is exercised.
        from akms_learn.llm import registry as reg

        reg._REGISTRY.pop(_NLM_NAME, None)
        with patch("shutil.which", return_value=None):
            assert resolve_default_provider() == _AKMS_NAME

    def test_nlm_env_without_cli_and_no_key_falls_back_to_stub(self, monkeypatch):
        """nlm notebook env, no CLI, no key -> stub (graceful closed default)."""
        self._clear_env(monkeypatch)
        monkeypatch.setenv("AKMS_LEARN_NLM_NOTEBOOK_ID", "nb-1")
        from akms_learn.llm import registry as reg

        reg._REGISTRY.pop(_NLM_NAME, None)
        with patch("shutil.which", return_value=None):
            assert resolve_default_provider() == NO_PROVIDER_STUB_GENERATOR


# ---------------------------------------------------------------------------
# PART 2 — explicit provider always wins over auto-selection (mode wiring)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModeRespectsExplicitProvider:
    """In llm_expanded_mode, an explicitly-named provider beats auto-selection."""

    def test_explicit_provider_skips_auto_selection(self):
        """When the request names a non-stub provider, resolve_default_provider is never called."""
        from akms_learn.graph_import import GraphSlice
        from akms_learn.modes.llm_expanded import LLMExpansionRequest, llm_expanded_mode
        from akms_learn.requests import LearningRequest

        # Register a recording provider so we can assert it was dispatched to.
        from akms_learn.llm import registry as reg

        captured: dict[str, bool] = {"called": False}

        def _explicit_provider(topic, active_node_ids, policy, *, sources=None):
            captured["called"] = True
            return []

        reg.register("explicit_recorder_prov", _explicit_provider)

        slice_ = GraphSlice(nodes=[{"node_id": "n1"}], edges=[])
        request = LearningRequest(
            topic="t", goal="g", generation_option="deterministic_outline"
        )
        cfg = LLMExpansionRequest(
            enable_llm=True, provider="explicit_recorder_prov"
        )

        with patch(
            "akms_learn.modes.llm_expanded.resolve_default_provider"
        ) as auto, patch(
            "akms_learn.modes.llm_expanded.require_capability"
        ):
            result, _ = llm_expanded_mode(
                slice_, ["n1"], request, expansion_request=cfg
            )
        auto.assert_not_called()
        assert captured["called"] is True

    def test_default_provider_triggers_auto_selection(self):
        """When the request leaves provider at the stub default, auto-selection runs."""
        from akms_learn.graph_import import GraphSlice
        from akms_learn.modes.llm_expanded import LLMExpansionRequest, llm_expanded_mode
        from akms_learn.requests import LearningRequest

        slice_ = GraphSlice(nodes=[{"node_id": "n1"}], edges=[])
        request = LearningRequest(
            topic="t", goal="g", generation_option="deterministic_outline"
        )
        cfg = LLMExpansionRequest(enable_llm=True)  # provider == stub default

        with patch(
            "akms_learn.modes.llm_expanded.resolve_default_provider",
            return_value=NO_PROVIDER_STUB_GENERATOR,
        ) as auto:
            llm_expanded_mode(slice_, ["n1"], request, expansion_request=cfg)
        auto.assert_called_once()

    def test_no_provider_configured_packet_unchanged(self):
        """Nothing configured -> auto picks stub -> packet == deterministic baseline."""
        from akms_learn.graph_import import GraphSlice
        from akms_learn.modes.llm_expanded import LLMExpansionRequest, llm_expanded_mode
        from akms_learn.requests import LearningRequest

        slice_ = GraphSlice(nodes=[{"node_id": "n1"}, {"node_id": "n2"}], edges=[])
        request = LearningRequest(
            topic="t", goal="g", generation_option="deterministic_outline"
        )
        cfg = LLMExpansionRequest(enable_llm=True)

        with patch(
            "akms_learn.modes.llm_expanded.resolve_default_provider",
            return_value=NO_PROVIDER_STUB_GENERATOR,
        ):
            result, _ = llm_expanded_mode(
                slice_, ["n1", "n2"], request, expansion_request=cfg
            )
        # The stub does run (it's always-available) and produces sections; the
        # deterministic baseline (pre_expansion_packet) is preserved verbatim.
        assert result.pre_expansion_packet["node_ids"] == ["n1", "n2"]
        assert (
            result.packet["node_ids"] == result.pre_expansion_packet["node_ids"]
        )
