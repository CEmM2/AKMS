"""akms completion provider — adapts ``akms.orchestrator.call_llm``.

A *completion* :class:`~akms_learn.llm.protocol.LLMProvider` that routes
``llm_expanded`` section generation through AKMS's litellm-backed multi-provider
router. akms-learn already hard-depends on ``akms``; the router import is **lazy**
(inside the call) so this module stays import-light and adds no new top-level
dependency — importing it never pulls ``akms.orchestrator`` (or litellm).

Source-locking is enforced two ways:
* the system prompt instructs the model to cite only the provided node ids and
  introduce no ungrounded claims (the ``policy`` is surfaced verbatim), and
* the adapter only ever sets ``source_node_ids`` to ids drawn from
  ``active_node_ids`` — any id supplied via ``sources`` that is not in the active
  set is dropped, so an un-cited ("orphan") reference can never leak into a
  section. The mode's citation validator is the final backstop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from akms_learn.llm.registry import register
from akms_learn.models.llm_expansion import (
    GeneratedSection,
    compute_content_hash,
)

if TYPE_CHECKING:
    from akms_learn.llm.protocol import ProviderSources
    from akms_learn.models.llm_expansion import LLMExpansionPolicy

__all__ = ["AKMS_PROVIDER_NAME", "akms_completion"]

#: Registry name + provenance ``generator`` id for this provider.
AKMS_PROVIDER_NAME = "akms"

#: ``model`` id surfaced on emitted sections. The concrete model is resolved by
#: AKMS's ``model_routing`` config + env keys and is not returned by ``call_llm``,
#: so we record the router rather than a specific model string.
_AKMS_MODEL = "akms-router"

#: ``call_llm`` routing key for LSP section expansion.
_CALL_TYPE = "lsp_expansion"


def _system_prompt(policy: LLMExpansionPolicy | None) -> str:
    return (
        "You expand a Learning Source Packet (LSP) section for a learner. "
        "Cite ONLY the provided source node ids. Introduce no claim that is not "
        "grounded in those sources — paraphrase, do not invent. "
        f"Expansion policy: {policy or 'source_locked'}."
    )


def akms_completion(
    topic: str,
    active_node_ids: tuple[str, ...] | list[str],
    policy: LLMExpansionPolicy | None = None,
    *,
    sources: ProviderSources | None = None,
) -> list[GeneratedSection]:
    """Generate one source-locked section via ``akms.orchestrator.call_llm``.

    Returns an empty list when there are no active node ids (nothing to ground).
    """
    # Lazy import — keeps the module dependency-free at load time.
    from akms.orchestrator import call_llm

    valid_ids = tuple(str(nid) for nid in active_node_ids if nid)
    if not valid_ids:
        return []

    user = (
        f"Topic: {topic}\n"
        f"Source node ids (cite only these): {', '.join(valid_ids)}\n"
        "Write one concise explanatory paragraph grounded in those sources."
    )
    content = call_llm(_CALL_TYPE, _system_prompt(policy), user, max_tokens=1024)

    section_id = f"{valid_ids[0]}::akms-expansion"
    return [
        GeneratedSection(
            id=section_id,
            generator=AKMS_PROVIDER_NAME,
            model=_AKMS_MODEL,
            source_node_ids=valid_ids,
            validation_status="valid",
            content_hash=compute_content_hash(
                section_id=section_id,
                source_node_ids=valid_ids,
                content=content,
            ),
            content=content,
        )
    ]


# Register on import so a caller that imports this module makes the ``akms``
# provider resolvable by name.
register(AKMS_PROVIDER_NAME, akms_completion)
