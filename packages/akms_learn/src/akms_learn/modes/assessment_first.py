"""Mode: assessment_first — assessment-item-oriented compiler.

Generates a Learning Source Packet that carries a deterministic collection of
:class:`~akms_learn.models.AssessmentItem` records: self-checks, derivation
tasks, coding prompts, and debugging prompts.  Each item is anchored to one or
more source nodes via ``target_node_ids``; optional ``hidden_answer`` text is
kept **strictly separate** from the public ``prompt`` so the assessment
exporter can
render the public side without ever materialising the answer key.

Design decisions
----------------
* **Capability-gated** — the mode requires the ``notebook`` extra
  (``nbformat``) to be importable.
  ``require_capability("assessment_first")`` is the first operation in
  :func:`assessment_first_mode`; a missing extra raises
  :class:`~akms_learn.capability_gates.PreconditionError`.
* **Public/hidden separation is a HARD invariant** — the compiler never
  copies ``hidden_answer`` content into ``prompt`` under any code path.
  ``hidden_answer`` is populated **only** from a v2.1 hint that explicitly
  provides an ``answer`` field.  The mode NEVER invents answers from node
  body text.  A canary test in
  ``tests/test_assessment_first_compiler.py`` walks every emitted item and
  asserts ``hidden_answer not in prompt`` (and the reverse) for every item.
* **Field allowlist, not blacklist** — the model exposes ``prompt`` and
  ``hidden_answer`` as two independent fields.  The mode does not provide a
  helper that returns prompt + hidden_answer joined as a string, since any
  such helper would risk silently leaking the answer key when a new field is
  added.  The assessment exporter owns the public-side renderer and uses
  an allowlist there.
* **Heuristic item generation is conservative** — the four item kinds derive
  from specific approved-heading slots on each node:

  ``conceptual``  ← ``concept`` / ``motivation``
  ``derivation``  ← ``derivation``
  ``coding``      ← ``implementation``
  ``debugging``   ← ``pitfalls``

  A node only contributes items for sections it actually carries.  v2.1
  ``assessment_items`` hints (per :mod:`akms_learn.optional_metadata`)
  override and supplement the heuristic items; the dedup key is the item
  ``id``.
* **Orphan-reference validation** — :func:`validate_assessment_references`
  returns the list of (item_id, missing_node_id) pairs whose
  ``target_node_ids`` point outside the packet's known node set.  The mode
  raises :class:`AssessmentOrphanReferenceError` when any orphan is detected,
  matching the hard-error pattern of
  :class:`~akms_learn.validation.PacketValidationError`.
* **Weak-support warning** — when a ``hidden_answer`` is populated for an
  item whose combined target-section content is shorter than
  :data:`WEAK_SUPPORT_THRESHOLD_CHARS`, the mode emits a
  ``assessment_weak_support`` warning to the result.  Weak support NEVER
  raises; it is a soft annotation.  ``source_ref`` carries the item id.
* **Deterministic output** — every dict/set/iter is sorted; the item list is
  ordered by ``(kind, id)``.  Two compilations against the same graph
  produce byte-identical AssessmentItem collections.
* **Pure function** — never mutates ``graph_slice``, ``ordered_nodes``, or
  ``request``.
* **No execution at compile time** — no ``subprocess``, ``exec``, ``eval``,
  ``%run``, or ``nbclient`` calls anywhere in this module.

Warning codes
-------------
``assessment_weak_support``
    Emitted once per item whose ``hidden_answer`` is populated but whose
    combined target-section content is shorter than
    :data:`WEAK_SUPPORT_THRESHOLD_CHARS`.  ``source_ref`` is the item id.
"""

from __future__ import annotations

from typing import Any, Optional

from akms_learn.capability_gates import PreconditionError, require_capability
from akms_learn.graph_import import GraphSlice
from akms_learn.models import AssessmentItem, AssessmentItemKind, LearningWarning
from akms_learn.optional_metadata import read_v21_metadata
from akms_learn.requests import LearningRequest
from akms_learn.section_extraction import (
    ExtractedSection,
    extract_sections_from_node,
)
from akms_learn.warnings import WarningAccumulator

__all__ = [
    "WEAK_SUPPORT_THRESHOLD_CHARS",
    "KIND_TO_SECTION_NAMES",
    "AssessmentFirstResult",
    "AssessmentOrphanReferenceError",
    "assessment_first_mode",
    "validate_assessment_references",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Minimum combined source-section length (in characters) required to consider
#: a ``hidden_answer`` "well-supported".  Items with populated answers but
#: shorter combined section text trigger an ``assessment_weak_support``
#: warning.  Per the cross-phase guidance and conservative-by-default
#: principle: ~50 chars.
WEAK_SUPPORT_THRESHOLD_CHARS: int = 50

#: Mapping from AssessmentItem kind → tuple of approved heading names that
#: feed prompts of that kind.  The first matching section wins (deterministic
#: via the canonical order in :data:`KIND_TO_SECTION_NAMES`).
KIND_TO_SECTION_NAMES: dict[AssessmentItemKind, tuple[str, ...]] = {
    "conceptual": ("concept", "motivation"),
    "derivation": ("derivation",),
    "coding": ("implementation",),
    "debugging": ("pitfalls",),
}

#: Canonical ordering of the four kinds — used for deterministic emission.
_KIND_ORDER: tuple[AssessmentItemKind, ...] = (
    "conceptual",
    "derivation",
    "coding",
    "debugging",
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AssessmentOrphanReferenceError(ValueError):
    """Raised when one or more AssessmentItem references resolve outside the packet.

    Mirrors the shape of :class:`~akms_learn.validation.PacketValidationError`:
    carries a list of human-readable issue strings joined with ``"; "`` in the
    canonical message.
    """

    def __init__(self, issues: list[str]) -> None:
        self.issues: list[str] = list(issues)
        super().__init__("; ".join(self.issues))


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class AssessmentFirstResult:
    """Structured result from :func:`assessment_first_mode`.

    Attributes
    ----------
    assessment_items:
        Deterministic list of :class:`AssessmentItem` records ordered by
        ``(kind, id)``.
    source_node_ids:
        Sorted list of node ids that contributed at least one assessment item.
    warnings:
        List of :class:`~akms_learn.models.LearningWarning` instances emitted
        during compilation (e.g. ``assessment_weak_support``).
    """

    __slots__ = ("assessment_items", "source_node_ids", "warnings")

    def __init__(
        self,
        assessment_items: list[AssessmentItem],
        source_node_ids: list[str],
        warnings: list[LearningWarning],
    ) -> None:
        self.assessment_items = assessment_items
        self.source_node_ids = source_node_ids
        self.warnings = warnings


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _section_lookup(
    sections: list[ExtractedSection],
) -> dict[str, ExtractedSection]:
    """Index extracted sections by their canonical (normalized) heading name."""
    return {s.normalized_name: s for s in sections}


def _prompt_for_kind(
    kind: AssessmentItemKind,
    section: ExtractedSection,
    node_title: str,
) -> str:
    """Build a deterministic public prompt for a single section-derived item.

    The prompt text is built from the *section name and the source-node title
    only* — never from the answer key.  This keeps the public/hidden
    separation easy to audit: the function has no access to any
    ``hidden_answer`` text.
    """
    if kind == "conceptual":
        return (
            f"Explain in your own words the core idea behind {node_title!r}, "
            f"drawing on the {section.normalized_name!r} section."
        )
    if kind == "derivation":
        return (
            f"Reproduce the derivation for {node_title!r} step-by-step, "
            f"justifying each transformation."
        )
    if kind == "coding":
        return (
            f"Implement the algorithm described in {node_title!r}; verify "
            f"the result against the section's worked example where present."
        )
    if kind == "debugging":
        return (
            f"Identify and explain the common pitfalls listed for "
            f"{node_title!r}, and describe how each one manifests in practice."
        )
    # Defensive fallback — should never trigger because kind is a Literal.
    return f"Self-check for {node_title!r} ({kind})."


def _node_title(node: dict[str, Any]) -> str:
    """Return a deterministic display title for a node."""
    title = node.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    nid = node.get("node_id")
    if isinstance(nid, str) and nid:
        return nid
    return "<untitled node>"


def _coerce_str(value: Any) -> Optional[str]:
    """Coerce a free-form value to ``Optional[str]`` without inventing content."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _items_from_heuristic(
    node: dict[str, Any],
    sections_by_node: dict[str, list[ExtractedSection]],
) -> list[AssessmentItem]:
    """Build heuristic items for one node, one per kind whose section is present.

    Conservative: a node contributes a kind only when the corresponding
    approved-heading section exists on it.  The returned items carry no
    ``hidden_answer`` — answer-key text is populated **only** via the v2.1
    hint path (see :func:`_items_from_v21_hints`).
    """
    nid = str(node.get("node_id") or "")
    if not nid:
        return []
    sections = sections_by_node.get(nid, [])
    lookup = _section_lookup(sections)
    title = _node_title(node)

    items: list[AssessmentItem] = []
    for kind in _KIND_ORDER:
        candidate_names = KIND_TO_SECTION_NAMES[kind]
        chosen: Optional[ExtractedSection] = None
        for name in candidate_names:
            if name in lookup:
                chosen = lookup[name]
                break
        if chosen is None:
            continue
        item_id = f"{nid}::{kind}"
        prompt = _prompt_for_kind(kind, chosen, title)
        items.append(
            AssessmentItem(
                id=item_id,
                kind=kind,
                prompt=prompt,
                hidden_answer=None,
                target_node_ids=(nid,),
                provenance={
                    "derived_from": "heuristic",
                    "section_kind": chosen.normalized_name,
                },
            )
        )
    return items


def _items_from_v21_hints(
    node: dict[str, Any],
) -> list[AssessmentItem]:
    """Build items from v2.1 ``assessment_items`` hints carried on the node.

    A hint is consumed only when it carries the minimum required fields
    (``id``, ``kind``, ``prompt``).  ``hidden_answer`` is taken from the
    ``answer`` field of the hint, if present — never invented.
    ``target_node_ids`` defaults to ``(node_id,)`` when the hint does not
    specify any.

    Hints whose ``kind`` is not one of the four supported values are silently
    skipped (the v2.1 layer is intentionally tolerant of forward-compatible
    extensions; non-canonical kinds are left for future modes to consume).
    """
    nid = str(node.get("node_id") or "")
    if not nid:
        return []

    try:
        meta = read_v21_metadata(node)
    except Exception:
        # The v2.1 read layer raises only on invalid expansion_policy, which
        # is unrelated to assessment_items.  Defensively swallow other errors
        # so a single malformed hint cannot break the whole compilation.
        return []

    items: list[AssessmentItem] = []
    for hint in meta.assessment_items:
        if not isinstance(hint, dict):
            continue
        hint_id = _coerce_str(hint.get("id"))
        hint_kind = _coerce_str(hint.get("kind"))
        hint_prompt = _coerce_str(hint.get("prompt"))
        if not hint_id or not hint_kind or not hint_prompt:
            continue
        if hint_kind not in KIND_TO_SECTION_NAMES:
            continue
        hint_answer = _coerce_str(hint.get("answer"))
        # target_node_ids: prefer explicit list on the hint; default to (nid,).
        raw_targets = hint.get("target_node_ids")
        if isinstance(raw_targets, (list, tuple)) and raw_targets:
            targets = tuple(str(t) for t in raw_targets)
        else:
            targets = (nid,)
        items.append(
            AssessmentItem(
                id=hint_id,
                kind=hint_kind,  # type: ignore[arg-type]  # validated above
                prompt=hint_prompt,
                hidden_answer=hint_answer,
                target_node_ids=targets,
                provenance={
                    "derived_from": "v21_hint",
                    "source_node_id": nid,
                },
            )
        )
    return items


def _combined_section_length(
    item: AssessmentItem,
    sections_by_node: dict[str, list[ExtractedSection]],
) -> int:
    """Sum the length of all target-section contents for *item*.

    Used by the weak-support heuristic.  The "relevant section kind" is
    derived from :data:`KIND_TO_SECTION_NAMES`; when an item's kind does not
    map to any heading (defensive), the full set of sections on each target
    node is summed.
    """
    relevant_names = set(KIND_TO_SECTION_NAMES.get(item.kind, ()))
    total = 0
    for nid in item.target_node_ids:
        sections = sections_by_node.get(nid, [])
        for section in sections:
            if not relevant_names or section.normalized_name in relevant_names:
                total += len(section.content or "")
    return total


# ---------------------------------------------------------------------------
# Orphan-reference validation
# ---------------------------------------------------------------------------


def validate_assessment_references(
    items: list[AssessmentItem],
    packet_node_ids: set[str],
) -> list[tuple[str, str]]:
    """Return ``(item_id, missing_node_id)`` pairs for orphan references.

    An assessment item is considered to have an orphan reference when any
    entry of its ``target_node_ids`` does not appear in *packet_node_ids*.

    The returned list is sorted deterministically by ``(item_id,
    missing_node_id)`` so two equal inputs always produce equal outputs.
    An empty return value indicates no orphans.

    The function is pure — it does not mutate either argument and never
    raises.  Callers convert orphans into a hard error via
    :class:`AssessmentOrphanReferenceError` at their own discretion.
    """
    orphans: list[tuple[str, str]] = []
    for item in items:
        for target in item.target_node_ids:
            if target not in packet_node_ids:
                orphans.append((item.id, target))
    return sorted(orphans)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def assessment_first_mode(
    graph_slice: GraphSlice,
    ordered_nodes: list[str],
    request: LearningRequest,
) -> tuple["AssessmentFirstResult", list[LearningWarning]]:
    """Build the assessment_first mode view.

    Requires the ``notebook`` extra (``nbformat``) to be installed.  If the
    extra is absent, :class:`~akms_learn.capability_gates.PreconditionError`
    is raised before any computation is done.

    Pure function — never mutates ``graph_slice``, ``ordered_nodes``, or
    ``request``.

    Parameters
    ----------
    graph_slice:
        Immutable :class:`~akms_learn.graph_import.GraphSlice` from the
        compiler pipeline.
    ordered_nodes:
        Node id list in learning order.  Iterated to walk the graph subgraph
        in a deterministic sequence.
    request:
        The validated :class:`~akms_learn.requests.LearningRequest`.
        Currently unused by this mode (no per-request item filtering); the
        parameter is retained for signature consistency with the other
        structured modes and so future filtering can be added without
        breaking callers.

    Returns
    -------
    (result, warnings)
        ``result`` is an :class:`AssessmentFirstResult`.  ``warnings`` is the
        same list as ``result.warnings``.

    Raises
    ------
    PreconditionError
        When the ``notebook`` extra is not installed.
    AssessmentOrphanReferenceError
        When any emitted AssessmentItem has a ``target_node_ids`` entry that
        is not present in ``graph_slice.nodes``.
    """
    # ------------------------------------------------------------------
    # Capability gate — must be the very first operation.
    # ------------------------------------------------------------------
    require_capability("assessment_first")

    # ------------------------------------------------------------------
    # Index nodes by id (read-only copies).
    # ------------------------------------------------------------------
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for raw in graph_slice.nodes:
        nid = raw.get("node_id")
        if nid is not None:
            nodes_by_id[nid] = dict(raw)

    # Set of every known node id; orphan validation uses this.
    packet_node_ids: set[str] = set(nodes_by_id.keys())

    # ------------------------------------------------------------------
    # Extract approved-heading sections for every node (deterministic).
    # ------------------------------------------------------------------
    sections_by_node: dict[str, list[ExtractedSection]] = {}
    for nid in sorted(nodes_by_id.keys()):
        sections_by_node[nid] = extract_sections_from_node(nodes_by_id[nid])

    # ------------------------------------------------------------------
    # Build the deduped item collection.
    # Order of iteration:
    #   1. v2.1 hints first (so an explicit hint with the same id as a
    #      heuristic item wins via the "first occurrence keeps") -- this
    #      preserves author-provided answers.
    #   2. Heuristic items next (filling in kinds the hints did not cover).
    # ------------------------------------------------------------------
    by_id: dict[str, AssessmentItem] = {}

    for nid in [n for n in ordered_nodes if n in nodes_by_id]:
        for hint_item in _items_from_v21_hints(nodes_by_id[nid]):
            if hint_item.id not in by_id:
                by_id[hint_item.id] = hint_item

    for nid in [n for n in ordered_nodes if n in nodes_by_id]:
        for heuristic_item in _items_from_heuristic(nodes_by_id[nid], sections_by_node):
            if heuristic_item.id not in by_id:
                by_id[heuristic_item.id] = heuristic_item

    # ------------------------------------------------------------------
    # Deterministic ordering: by (kind, id).
    # ------------------------------------------------------------------
    _kind_index: dict[AssessmentItemKind, int] = {
        k: i for i, k in enumerate(_KIND_ORDER)
    }
    assessment_items: list[AssessmentItem] = sorted(
        by_id.values(),
        key=lambda it: (_kind_index.get(it.kind, len(_KIND_ORDER)), it.id),
    )

    # ------------------------------------------------------------------
    # Orphan-reference validation — HARD error if any orphan is found.
    # ------------------------------------------------------------------
    orphans = validate_assessment_references(assessment_items, packet_node_ids)
    if orphans:
        issues = [
            f"AssessmentItem {iid!r} target_node_id {nid!r} not in packet.nodes"
            for iid, nid in orphans
        ]
        raise AssessmentOrphanReferenceError(issues)

    # ------------------------------------------------------------------
    # Weak-support warnings (soft; never raise).
    # ------------------------------------------------------------------
    acc = WarningAccumulator()
    for item in assessment_items:
        if item.hidden_answer is None or not item.hidden_answer.strip():
            continue
        combined = _combined_section_length(item, sections_by_node)
        if combined < WEAK_SUPPORT_THRESHOLD_CHARS:
            acc.append(
                LearningWarning(
                    severity="warning",
                    code="assessment_weak_support",
                    source_ref=item.id,
                    message=(
                        f"Assessment item {item.id!r} has a hidden_answer but "
                        f"its target sections carry only {combined} chars of "
                        f"source content (< {WEAK_SUPPORT_THRESHOLD_CHARS}); "
                        "answer may be poorly grounded in sources."
                    ),
                )
            )

    # ------------------------------------------------------------------
    # Source-node id collection — sorted for determinism.
    # ------------------------------------------------------------------
    contributing: set[str] = set()
    for item in assessment_items:
        contributing.update(item.target_node_ids)
    source_node_ids = sorted(contributing)

    warnings = acc.finalize()
    result = AssessmentFirstResult(
        assessment_items=assessment_items,
        source_node_ids=source_node_ids,
        warnings=warnings,
    )
    return result, warnings
