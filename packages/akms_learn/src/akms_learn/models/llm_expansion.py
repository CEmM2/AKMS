"""LLMExpansionPolicy + GeneratedSection models for the ``llm_expanded`` mode.

These models back the ``llm_expanded`` compiler mode.  They are
intentionally lightweight pure-data containers; the mode
logic — including citation validation and the deterministic-LSP capture step
— lives in :mod:`akms_learn.modes.llm_expanded`.

Design decisions
----------------
* **Frozen** — every field is immutable so two equal sections hash identically
  and the cross-run byte-identical determinism contract has something
  stable to compare against.
* **``policy`` is a Literal of exactly three values**:
  ``source_locked`` / ``explanatory_only`` / ``no_new_claims``.  Adding a
  policy value is a deliberate contract change.  The same three values are
  enforced upstream by
  :data:`akms_learn.optional_metadata.EXPANSION_POLICY_VALUES` so the v2.1
  metadata hint set and the compiler model never drift.
* **``validation_status`` is a Literal of exactly three values** (plan §7
  task 3):

  - ``"valid"`` — citations all in packet.nodes; policy satisfied.
  - ``"rejected_orphan_citation"`` — at least one ``source_node_id`` is
    absent from ``packet.nodes``.
  - ``"rejected_policy"`` — section violated the active expansion policy
    (currently unused by the stub provider; reserved for downstream
    providers).

  Rejected sections are NEVER attached to the LSP — the citation-validator
  branch in :func:`~akms_learn.modes.llm_expanded.llm_expanded_mode` filters
  them out and emits an ``llm_citation_outside_packet`` warning instead
  (conservative path).
* **``content_hash`` is SHA-256** of a sorted, deterministic JSON encoding
  of ``(id, source_node_ids, content)`` — never of the full model
  representation.  This makes the hash stable across hash-irrelevant model
  evolution and prevents accidental hash changes when forward-compatible
  fields are added.
* **No I/O at construction time** — pure data, no LLM calls, no graph
  access, no filesystem touch.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict

__all__ = [
    "LLM_EXPANSION_POLICIES",
    "LLM_VALIDATION_STATUSES",
    "GeneratedSection",
    "GeneratedSectionValidationStatus",
    "LLMExpansionPolicy",
    "build_llm_provenance",
    "compute_content_hash",
]


# ---------------------------------------------------------------------------
# Policy + validation-status literals
# ---------------------------------------------------------------------------

#   #: The exact set of allowed ``LLMExpansionPolicy`` values.
#   #:
#   #: Kept tuple-shaped so callers iterating for tests get a deterministic order.
LLM_EXPANSION_POLICIES: Final[tuple[str, str, str]] = (
    "source_locked",
    "explanatory_only",
    "no_new_claims",
)

#: Literal alias for the three allowed policies.
LLMExpansionPolicy = Literal["source_locked", "explanatory_only", "no_new_claims"]

#   #: The exact set of allowed ``GeneratedSection.validation_status`` values.
LLM_VALIDATION_STATUSES: Final[tuple[str, str, str]] = (
    "valid",
    "rejected_orphan_citation",
    "rejected_policy",
)

#: Literal alias for the three allowed validation statuses.
GeneratedSectionValidationStatus = Literal["valid", "rejected_orphan_citation", "rejected_policy"]


# ---------------------------------------------------------------------------
# Content-hash helper
# ---------------------------------------------------------------------------


def compute_content_hash(
    section_id: str,
    source_node_ids: tuple[str, ...],
    content: str,
) -> str:
    """Return a stable SHA-256 hex digest for a GeneratedSection's content.

    The hashed payload is a canonical JSON dump of
    ``[section_id, sorted(source_node_ids), content]`` with
    ``sort_keys=True``, ``separators=(",", ":")``, and
    ``ensure_ascii=False``.  These three settings collectively make the
    digest byte-identical across Python sessions, locales, and OSes —
    matching the determinism contract of :func:`request_hash` in
    :mod:`akms_learn.requests`.

    Note: only the *content-defining* triple participates in the hash.
    Fields that may legitimately differ between providers (``generator``,
    ``model``) or whose value derives from the content
    (``validation_status``, ``content_hash``) are intentionally excluded so
    the hash remains a true content fingerprint, not a model fingerprint.
    """
    payload = json.dumps(
        [section_id, sorted(source_node_ids), content],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Provenance block (single canonical shape)
# ---------------------------------------------------------------------------


def build_llm_provenance(
    *,
    provider: str,
    model: str | None,
    policy: LLMExpansionPolicy | None,
    section_count: int,
    citation_count: int,
    rejected_count: int,
) -> dict[str, Any]:
    """Return the canonical ``provenance.llm`` block.

    Single source of truth for the LLM provenance shape so the mode
    (:func:`akms_learn.modes.llm_expanded.llm_expanded_mode`, which writes it
    onto ``result.packet``) and the compiler (which writes the authoritative
    block onto the surfaced :class:`~akms_learn.models.lsp.PacketBody`) cannot
    drift: both call this helper and therefore emit identical keys.
    """
    return {
        "provider": provider,
        "model": model,
        "policy": policy,
        "section_count": section_count,
        "citation_count": citation_count,
        "rejected_count": rejected_count,
    }


# ---------------------------------------------------------------------------
# GeneratedSection
# ---------------------------------------------------------------------------


class GeneratedSection(BaseModel):
    """A single LLM-generated section attached to an ``llm_expanded`` LSP.

    Fields
    ------
    id:
        Stable, deterministic identifier for the section.  Unique within a
        packet; used by the compiler for dedup and by warnings as
        ``source_ref``.
    generator:
        Identifier of the entity that produced the section
        (e.g. ``"no_provider_stub"``).  Always populated — even the
        no-provider stub names itself so provenance is preserved.
    model:
        Identifier of the underlying model.  For the no-provider stub the
        value is ``"deterministic-stub-v1"``.
    source_node_ids:
        Tuple of node ids in the same packet that the section cites.  Every
        id MUST appear in ``packet.nodes`` — the mode's citation validator
        rejects any out-of-scope id and never attaches the rejected section
        to the final LSP.
    validation_status:
        One of ``"valid"`` / ``"rejected_orphan_citation"`` /
        ``"rejected_policy"``.  Only ``"valid"`` sections survive into the
        final ``generated_sections`` list on the LSP.
    content_hash:
        SHA-256 hex digest of a canonical encoding of ``(id,
        source_node_ids, content)`` — see :func:`compute_content_hash`.
    content:
        The generated prose text.  Plain string — never HTML, never
        markdown-formatted, never a dict.  Exporters own downstream
        formatting.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    generator: str
    model: str
    source_node_ids: tuple[str, ...]
    validation_status: GeneratedSectionValidationStatus
    content_hash: str
    content: str
