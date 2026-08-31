"""llm_router.py — Multi-provider LLM routing for AKMS internal calls.

Thin wrapper around LiteLLM. Used for dedup and drift checks only.
Subagents use the Claude Agent SDK directly via AKMSAgent.run().

**Deviation D2 from addendum:** Accepts PropagationConfig as parameter instead
of @lru_cache filesystem reads. More testable, consistent with AKMS patterns.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import litellm

if TYPE_CHECKING:
    from akms.schema.models import PropagationConfig

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Core Routing
# ═══════════════════════════════════════════════════════════════════════


def _get_model(call_type: str, config: PropagationConfig | None = None) -> str:
    """Resolve LiteLLM model string for a given call type.

    Args:
        call_type: One of: dedup_similarity, docstring_drift.
        config: PropagationConfig with model_routing section.
            When None, defaults to Anthropic Haiku.

    Returns:
        LiteLLM model string (e.g. "gemini/gemini-2.0-flash",
        "anthropic/claude-haiku-4-5-20251001").
    """
    if config is None:
        return "anthropic/claude-haiku-4-5-20251001"

    routing = config.model_routing
    entry = getattr(routing, call_type, None)
    if entry is None:
        return "anthropic/claude-haiku-4-5-20251001"

    provider = entry.provider
    model = entry.model

    # LiteLLM format: "provider/model" for non-OpenAI, just "model" for OpenAI
    if provider == "openai":
        return model
    return f"{provider}/{model}"


def call_llm(
    call_type: str,
    system: str,
    user: str,
    *,
    config: PropagationConfig | None = None,
    max_tokens: int = 500,
    temperature: float = 0.0,
) -> str:
    """Make a routed LLM call for AKMS internal operations.

    Args:
        call_type: Key matching a field in ModelRoutingConfig.
        system: System prompt.
        user: User message.
        config: PropagationConfig for model resolution.
        max_tokens: Max response tokens.
        temperature: Sampling temperature (0.0 for determinism).

    Returns:
        The model's text response.
    """
    model = _get_model(call_type, config)
    logger.debug("LLM call: type=%s model=%s", call_type, model)

    # Typed as ModelResponse | CustomStreamWrapper because litellm shares one
    # signature with its streaming mode. This call never sets stream=True.
    response: Any = litellm.completion(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    # ``content`` is optional on the provider schema; this function promises a
    # str, so an absent completion becomes an empty one.
    return response.choices[0].message.content or ""


# ═══════════════════════════════════════════════════════════════════════
#  Specific Call Types
# ═══════════════════════════════════════════════════════════════════════


def check_dedup_similarity(
    new_description: str,
    existing_title: str,
    existing_content: str,
    *,
    config: PropagationConfig | None = None,
) -> float:
    """Dedup similarity check for tentative node creation.

    Returns similarity score 0.0–1.0.
    Uses cheapest available model (configured in model_routing).
    """
    response = call_llm(
        call_type="dedup_similarity",
        system=(
            "You are a semantic similarity scorer. Compare the two texts below. "
            "Reply with ONLY a float between 0.0 and 1.0 indicating similarity. "
            "1.0 = identical meaning, 0.0 = completely unrelated."
        ),
        user=(
            f"Text A (new):\n{new_description}\n\n"
            f"Text B (existing):\n{existing_title}\n{existing_content[:500]}"
        ),
        config=config,
        max_tokens=10,
    )
    try:
        return float(response.strip())
    except ValueError:
        return 0.0  # Parse failure → treat as no match


def check_docstring_drift(
    docstring: str,
    param_names: list[str],
    return_annotation: str | None,
    *,
    config: PropagationConfig | None = None,
) -> tuple[bool, str]:
    """Lightweight docstring drift check for code mirror generation.

    Returns (drifted: bool, explanation: str).
    Uses mid-tier model (configured in model_routing).
    """
    params_str = ", ".join(param_names) if param_names else "(no parameters)"
    return_str = return_annotation or "(no return annotation)"

    response = call_llm(
        call_type="docstring_drift",
        system=(
            "You check whether a docstring accurately describes a function. "
            "Reply YES if accurate or if docstring is absent. "
            "Reply NO followed by one sentence explaining the mismatch."
        ),
        user=(
            f"Docstring:\n{docstring}\n\n"
            f"Parameters: {params_str}\n"
            f"Return type: {return_str}"
        ),
        config=config,
        max_tokens=100,
    )
    text = response.strip()
    if text.upper().startswith("YES"):
        return False, ""
    return True, text
