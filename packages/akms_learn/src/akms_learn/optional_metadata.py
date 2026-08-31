"""Optional AKMS v2.1 metadata support layer.

This module introduces a non-breaking metadata hint layer.  Nodes that carry
v2.1 fields are read via :func:`read_v21_metadata`; nodes without them receive
fully-defaulted instances.  **No node mutation, no vault writes.**

Six optional hint fields (plan §9, L195-L200):

- ``expansion_policy``            — LLM expansion policy for option 4 compilers.
- ``llm_allowed``                 — whether LLM calls are permitted on this node.
- ``generated_section_validation``— validation hint for generated sections.
- ``learner_profile``             — learner-profile hint carried on the node
                                    (metadata shape only; the runtime request
                                    model is ``LearnerProfile``).
- ``skipped_prerequisites``       — audit list of skipped prerequisite node ids.
- ``assessment_items``            — assessment item hints for option 10 compilers.

Allowed ``expansion_policy`` values:

    ``source_locked`` | ``explanatory_only`` | ``no_new_claims``

Any other value raises :class:`V21MetadataError` at read time.

Read-only contract
------------------
:func:`read_v21_metadata` accepts a raw node ``dict`` (as carried by
:class:`~akms_learn.graph_import.GraphSlice`) and returns a
:class:`V21Metadata` instance.  It never mutates its argument, never writes to
the AKMS global vault (``~/.claude/akms/nodes/`` or ``$AKMS_GLOBAL_VAULT``),
and never touches the filesystem.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ExpansionPolicy",
    "V21Metadata",
    "V21MetadataError",
    "read_v21_metadata",
    "EXPANSION_POLICY_VALUES",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#   #: The exact set of allowed ``expansion_policy`` values.
EXPANSION_POLICY_VALUES: frozenset[str] = frozenset(
    {"source_locked", "explanatory_only", "no_new_claims"}
)

#: Type alias for expansion_policy literal values.
ExpansionPolicy = Literal["source_locked", "explanatory_only", "no_new_claims"]


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------


class V21MetadataError(ValueError):
    """Raised when a v2.1 metadata field carries an invalid value.

    Currently only ``expansion_policy`` is validated; future fields may extend
    this exception.
    """


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class V21Metadata(BaseModel):
    """Frozen container for optional AKMS v2.1 node metadata hints.

    All six fields are optional with safe defaults so downstream compilers can
    unconditionally call ``read_v21_metadata(node)`` without branching on field
    presence.

    Fields
    ------
    expansion_policy
        LLM expansion policy consumed by option 4 source compilers.
        ``None`` means "no policy set — compiler applies its own default".
        When present, must be one of the three allowed values.
    llm_allowed
        Whether LLM calls are permitted when expanding this node.
        ``None`` means "no explicit override — follow compiler default".
    generated_section_validation
        Validation hint for generated sections (e.g. a schema name or
        severity level).  Opaque string; interpretation is up to the
        option 4 compiler.
    learner_profile
        Learner-profile *hint* carried on the node (metadata shape).
        This is distinct from the runtime ``LearnerProfile`` request
        model — the node field is an advisory annotation only.
    skipped_prerequisites
        Audit list of prerequisite node ids that were intentionally skipped
        by the learner (option 9 audit records).
    assessment_items
        Assessment item hints for option 10 compilers.  Each entry is a
        free-form dict — the exact schema is defined by the consuming
        compiler.
    """

    model_config = ConfigDict(frozen=True)

    expansion_policy: Optional[ExpansionPolicy] = None
    llm_allowed: Optional[bool] = None
    generated_section_validation: Optional[str] = None
    learner_profile: Optional[str] = None
    skipped_prerequisites: tuple[str, ...] = Field(default_factory=tuple)
    assessment_items: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Accessor
# ---------------------------------------------------------------------------


def read_v21_metadata(node: dict[str, Any]) -> V21Metadata:
    """Return the v2.1 metadata hints carried by *node*, defaulting absent fields.

    Parameters
    ----------
    node:
        Raw AKMS node ``dict`` as carried by
        :class:`~akms_learn.graph_import.GraphSlice`.  The caller's dict is
        never mutated.

    Returns
    -------
    V21Metadata
        A frozen :class:`V21Metadata` instance.  Fields absent from *node*
        receive their safe default values.

    Raises
    ------
    V21MetadataError
        If ``expansion_policy`` is present but not in
        :data:`EXPANSION_POLICY_VALUES`.

    Notes
    -----
    * This function is strictly read-only.  It never writes to *node*, to the
      AKMS global vault, or to any other filesystem path.
    * ``skipped_prerequisites`` and ``assessment_items`` are sorted before
      construction so set-valued sources produce deterministic output
      (cross-phase determinism contract).
    """
    # -- expansion_policy: validate if present --------------------------------
    raw_policy = node.get("expansion_policy")
    if raw_policy is not None and raw_policy not in EXPANSION_POLICY_VALUES:
        raise V21MetadataError(
            f"Invalid expansion_policy {raw_policy!r}. "
            f"Allowed values: {sorted(EXPANSION_POLICY_VALUES)}"
        )

    # -- skipped_prerequisites: sort for determinism --------------------------
    raw_skipped = node.get("skipped_prerequisites")
    if raw_skipped is None:
        skipped: tuple[str, ...] = ()
    else:
        skipped = tuple(sorted(str(s) for s in raw_skipped))

    # -- assessment_items: preserve order but coerce to tuple ----------------
    raw_assessments = node.get("assessment_items")
    if raw_assessments is None:
        assessments: tuple[dict[str, Any], ...] = ()
    else:
        assessments = tuple(dict(item) for item in raw_assessments)

    return V21Metadata(
        expansion_policy=raw_policy,
        llm_allowed=node.get("llm_allowed"),
        generated_section_validation=node.get("generated_section_validation"),
        learner_profile=node.get("learner_profile"),
        skipped_prerequisites=skipped,
        assessment_items=assessments,
    )
