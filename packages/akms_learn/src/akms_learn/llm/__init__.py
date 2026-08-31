"""LLM-provider subpackage for ``akms_learn``.

Currently exposes a single built-in provider: :func:`no_provider_stub`.
External providers must declare their own optional-dependency extras and gate
through :func:`akms_learn.capability_gates.require_capability("llm_expanded")`
before being invoked.
"""

from __future__ import annotations

from akms_learn.llm.no_provider_stub import (
    NO_PROVIDER_STUB_GENERATOR,
    NO_PROVIDER_STUB_MODEL,
    no_provider_stub,
)

__all__ = [
    "NO_PROVIDER_STUB_GENERATOR",
    "NO_PROVIDER_STUB_MODEL",
    "no_provider_stub",
]
