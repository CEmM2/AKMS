"""Optional-dependency probe and capability gating framework.

This module answers the question: *which optional extras are installed, and
which capabilities does that make available?*

Design constraints
------------------
* **No eager imports** of optional packages.  ``nbformat`` and ``jinja2`` are
  never imported at module top-level; probing is done exclusively via
  :func:`importlib.util.find_spec`.
* **Deterministic output** — all capability listings are sorted so callers
  and downstream tests get a stable order regardless of dict/set iteration.
* **Cache-free probing** — :func:`probe_optional_extras` re-runs
  ``find_spec`` on every call so that test monkeypatching of
  ``importlib.util.find_spec`` is always honoured without needing an explicit
  cache-reset API.

Capability strings
------------------
Seven optional capabilities are defined:

    notebook_source    — requires the ``notebook`` extra (``nbformat``)
    notebook_export    — requires the ``notebook`` extra (``nbformat``)
    assessment_first   — requires the ``notebook`` extra (``nbformat``)
    quiz_export        — requires the ``html`` extra (``jinja2``)
    html_export        — requires the ``html`` extra (``jinja2``)
    llm_expanded       — requires the ``llm`` extra
    adaptive_path      — requires the ``llm`` extra

Public API
----------
:func:`probe_optional_extras`
    Returns ``dict[str, bool]`` mapping extra name → importability.
:class:`CapabilityGate`
    Frozen dataclass that records availability for all optional capabilities.
    Constructed via :func:`build_capability_gate`.
:func:`build_capability_gate`
    Probe extras and build a :class:`CapabilityGate` in one call.
:func:`available_capabilities`
    Return a sorted list of capability names whose backing extras are present.
:func:`require_capability`
    Assert a capability is available; raise :class:`PreconditionError` if not.
:class:`PreconditionError`
    Raised when a capability is requested without its backing extra installed.
    The message always names *both* the capability and the missing extra.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass

__all__ = [
    "CapabilityGate",
    "PreconditionError",
    "available_capabilities",
    "build_capability_gate",
    "probe_optional_extras",
    "require_capability",
]

# ---------------------------------------------------------------------------
# Mapping: extra name → the PyPI/importable package that probes its presence.
# ---------------------------------------------------------------------------
#
# The ``llm`` extra is intentionally empty (provider-specific packages added
# only when needed, per plan §4).  We probe the sentinel name ``_llm_extra``
# which will never be installed, so the extra always reports absent unless the
# caller installs an LLM provider and overrides the mapping.  A deliberately
# unreachable sentinel is cleaner than a hardcoded LLM provider name.
#
# For testing purposes callers monkeypatch ``importlib.util.find_spec`` and
# do not need to know the sentinel name.

_EXTRA_PROBE_MAP: dict[str, str | None] = {
    "notebook": "nbformat",
    "html": "jinja2",
    "llm": None,  # empty extra — always absent unless explicitly installed
}

# ---------------------------------------------------------------------------
# Capability → required extra mapping.
# ---------------------------------------------------------------------------

_CAPABILITY_EXTRA_MAP: dict[str, str] = {
    "notebook_source": "notebook",
    "notebook_export": "notebook",
    "assessment_first": "notebook",
    "quiz_export": "html",
    "html_export": "html",
    "llm_expanded": "llm",
    "adaptive_path": "llm",
}


# ---------------------------------------------------------------------------
# PreconditionError
# ---------------------------------------------------------------------------


class PreconditionError(Exception):
    """Raised when a capability is requested but its backing extra is absent.

    The message always includes *both* the affected capability and the missing
    extra, e.g.::

        notebook_source requires extra 'notebook' (install akms-learn[notebook])

    Attributes
    ----------
    capability:
        The requested capability string (e.g. ``"notebook_source"``).
    extra:
        The optional-dependency group that must be installed
        (e.g. ``"notebook"``).
    """

    def __init__(self, capability: str, extra: str) -> None:
        self.capability: str = capability
        self.extra: str = extra
        super().__init__(
            f"{capability} requires extra '{extra}' (install akms-learn[{extra}])"
        )


# ---------------------------------------------------------------------------
# probe_optional_extras
# ---------------------------------------------------------------------------


def probe_optional_extras() -> dict[str, bool]:
    """Probe which optional extras are importable.

    Uses :func:`importlib.util.find_spec` exclusively — no package is
    actually imported.  The function is *cache-free*: every call re-runs
    ``find_spec`` so that test monkeypatching always takes effect.

    Returns
    -------
    dict[str, bool]
        Keys are the three extra names (``"notebook"``, ``"html"``,
        ``"llm"``); values are ``True`` iff the sentinel package is
        importable.
    """
    result: dict[str, bool] = {}
    for extra, package in _EXTRA_PROBE_MAP.items():
        if extra == "llm":
            # The `llm` extra is package-less; resolve it to whether a
            # real llm_expanded provider is configured rather than a dead
            # always-False sentinel. See _llm_provider_configured().
            result[extra] = _llm_provider_configured()
        elif package is None:
            # Empty extra — treat as absent.
            result[extra] = False
        else:
            result[extra] = importlib.util.find_spec(package) is not None
    return result


#: Env vars whose presence indicates a usable completion-provider key for AKMS's
#: litellm router (the `akms` adapter).
_LLM_PROVIDER_ENV_VARS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
)

#: Env vars naming a configured NotebookLM notebook for the grounded provider
#: (the `nlm` adapter). A *configured notebook* — not merely the CLI
#: being on PATH — is the deliberate opt-in, so a dev machine that happens to
#: have `nlm` installed does not implicitly enable the capability.
_NLM_CONFIG_ENV_VARS: tuple[str, ...] = (
    "AKMS_LEARN_NLM_NOTEBOOK_ID",
    "NLM_NOTEBOOK_ID",
)


def _llm_provider_configured() -> bool:
    """Return ``True`` when an ``llm_expanded`` provider is usable.

    Two routes flip the ``llm`` capability on, both requiring **explicit**
    configuration so the default stays closed (graceful):

    * **completion** — an LLM API key is present in the environment for AKMS's
      litellm router (the ``akms`` adapter), or
    * **grounded** — a NotebookLM notebook is configured via env **and** the
      ``nlm`` CLI is on PATH (the ``nlm`` adapter). Ambient CLI presence alone is
      intentionally not enough.

    ``os.environ`` and ``shutil.which`` are read on every call so test patching
    always takes effect.
    """
    if any(os.environ.get(var) for var in _LLM_PROVIDER_ENV_VARS):
        return True
    nlm_configured = any(os.environ.get(var) for var in _NLM_CONFIG_ENV_VARS)
    return nlm_configured and shutil.which("nlm") is not None


# ---------------------------------------------------------------------------
# CapabilityGate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapabilityGate:
    """Frozen snapshot of which optional capabilities are available.

    Each attribute corresponds to one optional capability and is
    ``True`` iff its backing extra is importable
    at construction time.

    Construct via :func:`build_capability_gate` rather than directly.
    """

    notebook_source: bool = False
    notebook_export: bool = False
    assessment_first: bool = False
    quiz_export: bool = False
    html_export: bool = False
    llm_expanded: bool = False
    adaptive_path: bool = False


def build_capability_gate() -> CapabilityGate:
    """Probe extras and return a :class:`CapabilityGate`.

    Calls :func:`probe_optional_extras` internally — no arguments needed.
    """
    extras = probe_optional_extras()
    notebook = extras.get("notebook", False)
    html = extras.get("html", False)
    llm = extras.get("llm", False)
    return CapabilityGate(
        notebook_source=notebook,
        notebook_export=notebook,
        assessment_first=notebook,
        quiz_export=html,
        html_export=html,
        llm_expanded=llm,
        adaptive_path=llm,
    )


# ---------------------------------------------------------------------------
# available_capabilities / require_capability
# ---------------------------------------------------------------------------


def available_capabilities(gate: CapabilityGate | None = None) -> list[str]:
    """Return a sorted list of capability names that are currently available.

    If *gate* is ``None``, one is built by calling
    :func:`build_capability_gate` (which probes extras on the fly).

    The result is always sorted so downstream code and tests get a stable,
    deterministic order.
    """
    if gate is None:
        gate = build_capability_gate()
    return sorted(cap for cap in _CAPABILITY_EXTRA_MAP if getattr(gate, cap, False))


def require_capability(capability: str, gate: CapabilityGate | None = None) -> None:
    """Assert *capability* is available; raise :class:`PreconditionError` if not.

    Parameters
    ----------
    capability:
        One of the six optional capability strings (e.g. ``"notebook_source"``).
    gate:
        Optional pre-built :class:`CapabilityGate`.  If ``None``, a fresh gate
        is built via :func:`build_capability_gate`.

    Raises
    ------
    PreconditionError
        When the capability is not available.  The message names both the
        capability and the missing extra.
    ValueError
        When *capability* is not a recognised optional capability name.
    """
    if capability not in _CAPABILITY_EXTRA_MAP:
        raise ValueError(
            f"Unknown capability {capability!r}. "
            f"Known capabilities: {sorted(_CAPABILITY_EXTRA_MAP)}"
        )
    if gate is None:
        gate = build_capability_gate()
    if not getattr(gate, capability, False):
        extra = _CAPABILITY_EXTRA_MAP[capability]
        raise PreconditionError(capability=capability, extra=extra)
