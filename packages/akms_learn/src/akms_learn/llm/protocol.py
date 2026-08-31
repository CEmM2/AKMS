"""LLMProvider Protocol — the provider seam for the ``llm_expanded`` mode.

All LLM provider implementations — built-in or external — must satisfy this
Protocol.  The signature is the load-bearing public contract that every
provider adapter and the compiler bind to.  Changing it is a breaking
change for all registered providers.

Protocol signature
------------------
::

    (
        topic:           str,
        active_node_ids: tuple[str, ...] | list[str],
        policy:          LLMExpansionPolicy,
        *,
        sources:         ProviderSources | None = None,
    ) -> list[GeneratedSection]

``sources`` is an optional bundle of node refs and PDF paths consumed by
grounded providers (nlm).  Completion providers (the akms adapter)
ignore it; the stub ignores it.  Presence here means callers never
need to special-case provider kinds at the call site.

Design notes
------------
* ``@runtime_checkable`` is set so ``isinstance(fn, LLMProvider)`` works in
  tests and registry checks.  Python's runtime check tests only for attribute
  presence (``__call__``), not full signature compatibility — that is enforced
  by the type checker (mypy) rather than at runtime.
* ``ProviderSources`` is a plain ``dict`` alias (not a ``TypedDict``) so it is
  import-light and requires no optional dependencies. It may be tightened
  to a ``TypedDict`` if grounded providers need stronger shape guarantees.
* No I/O at import time.  No optional packages imported.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from akms_learn.models.llm_expansion import GeneratedSection, LLMExpansionPolicy

__all__ = [
    "LLMProvider",
    "ProviderSources",
]


# ---------------------------------------------------------------------------
# ProviderSources — optional grounded-context bundle
# ---------------------------------------------------------------------------

# NOTE: Using a plain dict alias rather than TypedDict so this module stays
# importable with zero optional dependencies.  This may be tightened to a
# TypedDict if grounded providers need stronger shape guarantees.
ProviderSources = dict  # node refs + optional PDF paths


# ---------------------------------------------------------------------------
# LLMProvider Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProvider(Protocol):
    """Structural Protocol for all LLM provider callables.

    A provider is any callable that accepts the five-argument signature below
    and returns a list of :class:`~akms_learn.models.llm_expansion.GeneratedSection`.

    Parameters
    ----------
    topic:
        Free-form topic string from the learning request.  Passed verbatim to
        the provider so it can orient generated content.
    active_node_ids:
        The node ids present in the packet being expanded.  Every
        ``GeneratedSection`` returned MUST cite only ids from this collection —
        the mode's citation validator rejects any orphan citation.
    policy:
        The resolved :class:`~akms_learn.models.llm_expansion.LLMExpansionPolicy`
        for this expansion call.  One of ``"source_locked"`` /
        ``"explanatory_only"`` / ``"no_new_claims"``.
    sources:
        Optional grounded-context bundle carrying node refs and PDF paths.
        Consumed by grounded providers (the nlm adapter); ignored by
        completion providers and the built-in stub.  Defaults to ``None``.

    Returns
    -------
    list[GeneratedSection]
        Zero or more sections.  Empty list is valid (provider found nothing
        to say).  All sections must have citations within ``active_node_ids``
        — orphan citations are caught by the mode's citation validator, not
        by the provider itself.
    """

    def __call__(
        self,
        topic: str,
        active_node_ids: tuple[str, ...] | list[str],
        policy: LLMExpansionPolicy | None = None,
        *,
        sources: ProviderSources | None = None,
    ) -> list[GeneratedSection]: ...
