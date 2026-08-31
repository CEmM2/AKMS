"""AssessmentItem model for the assessment_first compiler mode.

Defines the frozen Pydantic model carried by an LSP whose compiler mode is
``assessment_first``.  An :class:`AssessmentItem` is a single self-check,
exercise, derivation prompt, coding prompt, or debugging prompt, optionally
paired with a *hidden* answer key.

Design decisions
----------------
* **Frozen** — every field is immutable after construction so two equal items
  hash identically and the cross-run determinism tests have something stable
  to compare against.
* **Public/hidden separation is a HARD invariant.**  The ``prompt`` and
  ``hidden_answer`` fields live side-by-side on the model and MUST NEVER be
  merged at the data-model level.  There is intentionally no ``to_public()``
  method that returns a dict via blacklist filtering — the public/private
  slicing belongs to the assessment exporter and is implemented there as a field
  *allowlist*, not a blacklist.  Adding any helper here that returns prompt
  + hidden_answer in the same string would silently leak the answer key.
* **``kind`` is a Literal of exactly four values** — adding a kind is a
  deliberate contract change.
* **``target_node_ids`` is non-empty** — the invariant "every
  assessment item has target node ids" is enforced at construction time via
  a ``model_validator``.  Orphan-id checks (ids absent from ``packet.nodes``)
  are performed later by the compiler, since the model itself has no view of
  the packet's node set.
* **No I/O at construction time** — this is a pure data model; no graph
  access, no file I/O, no LLM calls.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "ASSESSMENT_ITEM_KINDS",
    "AssessmentItem",
    "AssessmentItemKind",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#   #: The exact set of allowed ``AssessmentItem.kind`` values.
ASSESSMENT_ITEM_KINDS: tuple[str, ...] = (
    "conceptual",
    "derivation",
    "coding",
    "debugging",
)

#: Literal alias for the four item kinds.
AssessmentItemKind = Literal["conceptual", "derivation", "coding", "debugging"]


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class AssessmentItem(BaseModel):
    """A single assessment item carried by an ``assessment_first`` LSP.

    Fields
    ------
    id
        Stable, deterministic identifier for the item.  Unique within a
        packet; used by the compiler for dedup and by warnings as
        ``source_ref``.
    kind
        One of ``"conceptual"`` / ``"derivation"`` / ``"coding"`` /
        ``"debugging"`` (plan §6 task 5).
    prompt
        The public prompt text shown to the learner.  MUST NOT contain any
        portion of ``hidden_answer`` — the compiler enforces this invariant
        via a canary test.
    hidden_answer
        Optional answer-key text.  When present, it is rendered to a
        separate output file by the assessment exporter (``rubric.md`` /
        the hidden side of ``assessment.json``).  ``None`` is the canonical
        "no answer key" value.
    target_node_ids
        Tuple of node ids in the same packet that justify this item.  MUST
        be non-empty; the compiler additionally enforces that every id
        resolves to a node in ``packet.nodes`` (orphan rejection).
    provenance
        Free-form provenance metadata.  Conventional keys include
        ``"derived_from"`` (``"heuristic"`` or ``"v21_hint"``) and
        ``"section_kind"`` (the approved heading used to derive the
        prompt).  Free-form so the model never needs revisiting when the
        compiler gains new derivation paths.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    kind: AssessmentItemKind
    prompt: str
    hidden_answer: Optional[str] = None
    target_node_ids: tuple[str, ...]
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_non_empty_target_node_ids(self) -> "AssessmentItem":
        """Enforce the invariant that ``target_node_ids`` is non-empty.

        The orphan-id check (ids must resolve to nodes in the packet) is
        the compiler's responsibility — see
        :func:`~akms_learn.modes.assessment_first.validate_assessment_references`.
        """
        if not self.target_node_ids:
            raise ValueError(
                f"AssessmentItem {self.id!r}: target_node_ids must be non-empty."
            )
        return self
