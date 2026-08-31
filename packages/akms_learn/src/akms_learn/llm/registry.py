"""Name-keyed LLM provider registry.

Providers are registered by string name and resolved at dispatch time.  The
built-in ``no_provider_stub`` is pre-registered under the name
``"no_provider_stub"`` and doubles as the default fallback when no provider is
requested.

Public API
----------
:func:`register`
    Register a provider callable under a name.  Overwrites silently (allows
    re-registration in tests).
:func:`resolve`
    Return the provider callable for *name*.  Raises
    :class:`~akms_learn.capability_gates.PreconditionError` for unknown names.
:func:`default_provider`
    Return the default provider (``no_provider_stub``).  Never raises.
:func:`resolve_default_provider`
    Return the *name* of the provider to use when the caller did not name one
    explicitly, by precedence: configured ``nlm`` grounded provider →
    completion ``akms`` provider (API key present) → ``no_provider_stub``.
    Never raises.
:data:`NO_PROVIDER_STUB_NAME`
    The canonical registry name for the built-in stub.  Import this instead
    of hard-coding the string so refactors propagate cleanly.

Design notes
------------
* Single module-level ``_REGISTRY`` dict.  Thread safety is not required —
  registration happens at import time or in test setup; concurrent mutation is
  not a supported use case.
* No optional imports.  The registry itself has zero extra dependencies; each
  provider module is responsible for its own optional imports.
* ``no_provider_stub`` is the only pre-registered provider.  The akms and
  nlm adapters call :func:`register` from their own modules on import.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from akms_learn.capability_gates import PreconditionError
from akms_learn.llm.no_provider_stub import (
    NO_PROVIDER_STUB_GENERATOR,
    no_provider_stub,
)

if TYPE_CHECKING:
    from akms_learn.llm.protocol import LLMProvider

__all__ = [
    "NO_PROVIDER_STUB_NAME",
    "default_provider",
    "register",
    "resolve",
    "resolve_default_provider",
]

# ---------------------------------------------------------------------------
# Registry name constant
# ---------------------------------------------------------------------------

#: Canonical registry name for the built-in no-op stub.  Identical to
#: :data:`~akms_learn.llm.no_provider_stub.NO_PROVIDER_STUB_GENERATOR` so
#: the two representations stay in sync without duplication.
NO_PROVIDER_STUB_NAME: str = NO_PROVIDER_STUB_GENERATOR


# ---------------------------------------------------------------------------
# Internal registry store
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, LLMProvider] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def register(name: str, provider: LLMProvider) -> None:
    """Register *provider* under *name*.

    Overwrites any previous registration for *name* without error so that
    test fixtures can re-register providers cleanly.

    Parameters
    ----------
    name:
        Non-empty string key.  By convention, provider names are lowercase
        and match the ``generator`` field they set on their
        :class:`~akms_learn.models.llm_expansion.GeneratedSection` outputs
        (e.g. ``"no_provider_stub"``, ``"akms"``, ``"nlm"``).
    provider:
        Any callable satisfying the
        :class:`~akms_learn.llm.protocol.LLMProvider` Protocol.
    """
    _REGISTRY[name] = provider  # type: ignore[assignment]


def resolve(name: str) -> LLMProvider:
    """Return the provider registered under *name*.

    Parameters
    ----------
    name:
        The registry key to look up.

    Returns
    -------
    LLMProvider
        The callable registered under *name*.

    Raises
    ------
    PreconditionError
        When *name* has no registered provider.  ``capability`` is set to
        *name* and ``extra`` is set to *name* so the error message reads
        ``"<name> requires extra '<name>' (install akms-learn[<name>])"``,
        indicating the caller needs to install / register the named provider.
    """
    provider = _REGISTRY.get(name)
    if provider is None:
        raise PreconditionError(capability=name, extra=name)
    return provider


def default_provider() -> LLMProvider:
    """Return the default provider (``no_provider_stub``).

    Always succeeds — the stub is pre-registered at module import time and
    is never removed from the registry.
    """
    return _REGISTRY[NO_PROVIDER_STUB_NAME]  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Auto default-provider selection (defaults to nlm-grounded)
# ---------------------------------------------------------------------------

#: Env vars whose presence indicates a usable completion-provider key for AKMS's
#: litellm router (the ``akms`` adapter).  Mirrors
#: ``capability_gates._LLM_PROVIDER_ENV_VARS``.
_COMPLETION_PROVIDER_ENV_VARS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
)

#: Env vars naming a configured NotebookLM notebook for the grounded ``nlm``
#: provider.  Mirrors ``capability_gates._NLM_CONFIG_ENV_VARS``.
_NLM_CONFIG_ENV_VARS: tuple[str, ...] = (
    "AKMS_LEARN_NLM_NOTEBOOK_ID",
    "NLM_NOTEBOOK_ID",
)


def _ensure_pluggable_providers_registered() -> None:
    """Import the pluggable provider adapters so they self-register.

    The ``akms`` and ``nlm`` adapters register themselves on import (the
    ``nlm`` one only when its CLI is on PATH).  They are not imported anywhere
    on the critical path otherwise, so :func:`resolve_default_provider` imports
    them lazily here before consulting the registry.  Import failures degrade
    silently — auto-selection simply falls back to a provider that *is*
    available (ultimately the always-present stub).
    """
    import contextlib
    import importlib

    for module in (
        "akms_learn.llm.providers.akms_completion",
        "akms_learn.llm.providers.nlm_cli",
    ):
        with contextlib.suppress(Exception):
            importlib.import_module(module)


def resolve_default_provider() -> str:
    """Return the provider *name* to use when the caller named none explicitly.

    Precedence (each step requires **explicit** configuration so the default
    stays closed and "no provider configured → stub → unchanged packet"
    is preserved):

    1. **nlm grounded** — a NotebookLM notebook is configured via env
       (``AKMS_LEARN_NLM_NOTEBOOK_ID`` or ``NLM_NOTEBOOK_ID``) **and** the
       ``nlm`` CLI is on PATH (so the adapter actually registered).
    2. **akms completion** — a completion API key is present in the environment
       (``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY`` / ``GOOGLE_API_KEY``).
    3. **no_provider_stub** — nothing configured (safe, deterministic default).

    ``os.environ`` and ``shutil.which`` (via the adapters' own registration) are
    consulted on every call so test patching always takes effect.  Never raises:
    a route is only selected when its provider is genuinely resolvable, so the
    returned name always resolves via :func:`resolve`.
    """
    import os

    _ensure_pluggable_providers_registered()

    # 1. nlm grounded — configured notebook AND the adapter registered (CLI on
    #    PATH).  Registration is the proxy for "nlm CLI present", so we never
    #    return "nlm" when ``resolve`` would fail.
    nlm_configured = any(os.environ.get(var) for var in _NLM_CONFIG_ENV_VARS)
    if nlm_configured and NLM_PROVIDER_NAME in _REGISTRY:
        return NLM_PROVIDER_NAME

    # 2. akms completion — an API key is present and the adapter registered.
    if any(os.environ.get(var) for var in _COMPLETION_PROVIDER_ENV_VARS):
        if AKMS_PROVIDER_NAME in _REGISTRY:
            return AKMS_PROVIDER_NAME

    # 3. Safe default — always-present stub.
    return NO_PROVIDER_STUB_NAME


#: Provider names used by :func:`resolve_default_provider`.  Kept as plain
#: string constants (not imports) so this module has zero load-time dependency
#: on the optional adapter modules — they are imported lazily on demand.
NLM_PROVIDER_NAME: str = "nlm"
AKMS_PROVIDER_NAME: str = "akms"


# ---------------------------------------------------------------------------
# Pre-register the built-in stub as the default
# ---------------------------------------------------------------------------

# This runs exactly once at import time.  Subsequent imports hit the module
# cache and do not re-register.  Tests that need a clean registry should
# call register() directly rather than manipulating _REGISTRY.
register(NO_PROVIDER_STUB_NAME, no_provider_stub)  # type: ignore[arg-type]
