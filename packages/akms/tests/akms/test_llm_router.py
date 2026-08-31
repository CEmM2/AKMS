"""Tests for llm_router.py — multi-provider LLM routing."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from akms.orchestrator.llm_router import (
    _get_model,
    call_llm,
    check_dedup_similarity,
    check_docstring_drift,
)
from akms.schema.models import PropagationConfig


@pytest.fixture
def config() -> PropagationConfig:
    """Config with explicit model routing."""
    return PropagationConfig.model_validate(
        {
            "model_routing": {
                "dedup_similarity": {
                    "provider": "gemini",
                    "model": "gemini-2.0-flash",
                },
                "docstring_drift": {
                    "provider": "anthropic",
                    "model": "claude-haiku-4-5-20251001",
                },
            }
        }
    )


class TestGetModel:
    def test_none_config_returns_default(self):
        assert _get_model("dedup_similarity") == "anthropic/claude-haiku-4-5-20251001"

    def test_gemini_provider(self, config):
        assert _get_model("dedup_similarity", config) == "gemini/gemini-2.0-flash"

    def test_anthropic_provider(self, config):
        assert (
            _get_model("docstring_drift", config)
            == "anthropic/claude-haiku-4-5-20251001"
        )

    def test_openai_provider_no_prefix(self):
        cfg = PropagationConfig.model_validate(
            {
                "model_routing": {
                    "dedup_similarity": {"provider": "openai", "model": "gpt-4o-mini"},
                }
            }
        )
        assert _get_model("dedup_similarity", cfg) == "gpt-4o-mini"

    def test_unknown_call_type_returns_default(self, config):
        assert (
            _get_model("nonexistent_type", config)
            == "anthropic/claude-haiku-4-5-20251001"
        )


class TestCallLlm:
    @patch("akms.orchestrator.llm_router.litellm")
    def test_calls_litellm_completion(self, mock_litellm, config):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "test response"
        mock_litellm.completion.return_value = mock_response

        result = call_llm("dedup_similarity", "system", "user", config=config)

        assert result == "test response"
        mock_litellm.completion.assert_called_once()
        call_args = mock_litellm.completion.call_args
        assert call_args.kwargs["model"] == "gemini/gemini-2.0-flash"


class TestCheckDedupSimilarity:
    @patch("akms.orchestrator.llm_router.litellm")
    def test_returns_float(self, mock_litellm):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "0.85"
        mock_litellm.completion.return_value = mock_response

        score = check_dedup_similarity("new desc", "old title", "old content")
        assert score == pytest.approx(0.85)

    @patch("akms.orchestrator.llm_router.litellm")
    def test_parse_failure_returns_zero(self, mock_litellm):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "I cannot compare these"
        mock_litellm.completion.return_value = mock_response

        score = check_dedup_similarity("new desc", "old title", "old content")
        assert score == 0.0


class TestCheckDocstringDrift:
    @patch("akms.orchestrator.llm_router.litellm")
    def test_no_drift(self, mock_litellm):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "YES"
        mock_litellm.completion.return_value = mock_response

        drifted, explanation = check_docstring_drift(
            "Adds two numbers.", ["a", "b"], "int"
        )
        assert drifted is False
        assert explanation == ""

    @patch("akms.orchestrator.llm_router.litellm")
    def test_drift_detected(self, mock_litellm):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[
            0
        ].message.content = "NO Missing parameter c in docstring."
        mock_litellm.completion.return_value = mock_response

        drifted, explanation = check_docstring_drift(
            "Adds two numbers.", ["a", "b", "c"], "int"
        )
        assert drifted is True
        assert "Missing parameter" in explanation
