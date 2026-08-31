"""LearnerProfile request model for the adaptive_path compiler mode.

Defines the frozen Pydantic model that callers attach to
:class:`~akms_learn.requests.LearningRequest` to personalise the adaptive
path compilation.

Design decisions
----------------
* **Frozen** — all four fields are immutable after construction so that the
  same profile value is hashable and can be compared by equality for
  determinism tests.
* **Tuples, not lists** — the three string collections use ``tuple[str, ...]``
  so the model is frozen at the Pydantic level (lists are mutable).
* **conservative_mode defaults True** — per plan §8 and the Phase 2 context
  "Conservative-by-default adaptation" invariant.  Callers must explicitly
  opt out by passing ``conservative_mode=False``; the mode compiler enforces
  this at the guard level before considering ``knows`` at all.
* **No LLM at construction time** — this is a pure data model; no graph
  access, no file I/O, no network calls.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = ["LearnerProfile"]


class LearnerProfile(BaseModel):
    """Declarative learner profile attached to an adaptive-path request.

    Fields
    ------
    knows:
        Concepts, topic tags, or node ids the learner asserts they already
        know.  Used to decide which prerequisite nodes to skip when
        ``conservative_mode=False``.
    weak:
        Topics the learner considers their weak areas; surfaced in the
        ``adaptive_summary`` section but does not trigger skipping.
    goals:
        High-level learning goals the learner is pursuing; surfaced in the
        ``adaptive_summary`` section but does not affect node selection.
    conservative_mode:
        When ``True`` (the default), no prerequisite node is ever skipped
        regardless of the contents of ``knows``.  Set to ``False`` only when
        the caller explicitly authorises skipping based on self-reported
        knowledge.
    """

    model_config = ConfigDict(frozen=True)

    knows: tuple[str, ...] = ()
    weak: tuple[str, ...] = ()
    goals: tuple[str, ...] = ()
    conservative_mode: bool = True
