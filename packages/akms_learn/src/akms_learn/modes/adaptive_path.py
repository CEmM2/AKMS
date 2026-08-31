"""Mode: adaptive_path — learner-profile-guided prerequisite filtering.

Generates a learner-specific Learning Source Packet by optionally filtering
prerequisite nodes based on a declared :class:`~akms_learn.models.LearnerProfile`.

Design decisions
----------------
* **Conservative-by-default** — ``LearnerProfile.conservative_mode`` defaults
  to ``True``.  When ``True``, the compiler is a strict pass-through: every
  node in ``ordered_nodes`` is included and zero prerequisites are skipped.
  This invariant is enforced via a short-circuit guard *before* any
  consideration of ``knows``.
* **Explicit-skip path** — only when ``conservative_mode=False`` will the
  compiler consult ``knows`` to decide whether to mark a node as skipped.
  A node is skipped when *every* tag on the node appears in ``knows`` OR the
  ``node_id`` itself appears in ``knows``.  Matching is done against the
  **sorted, lowercased** representations of both sides for consistency.
* **Skipped nodes stay in provenance** — the underlying graph slice is never
  mutated.  The lesson body simply omits skipped nodes; they are recorded
  under ``adaptive_path_result.provenance_skipped`` with ``node_id``,
  ``reason``, and ``source`` (the originating ``requires`` edge id, or
  ``"<direct_learner_claim>"`` when the node_id was matched directly).
* **Unknown learner claims emit warnings** — each item in ``knows``, ``weak``,
  and ``goals`` that does not match any graph tag or node id is reported via a
  :class:`~akms_learn.models.LearningWarning` with code
  ``adaptive_learner_claim_unmatched``.  Warnings are deduped by
  ``(code, source_ref)`` via :class:`~akms_learn.warnings.WarningAccumulator`.
* **Deterministic output** — all set materialisations use ``sorted()``;
  tiebreaks are by ``node_id`` so that any two runs with the same profile and
  graph produce byte-identical packets.
* **Capability-gated** — requires the ``llm`` extra.
  :func:`require_capability("adaptive_path")` is called at the top of
  :func:`adaptive_path_mode` and raises
  :class:`~akms_learn.capability_gates.PreconditionError` if the extra is
  absent.
* **No execution at compile time** — no ``subprocess``, ``exec``, ``eval``,
  ``%run``, or ``nbclient`` calls anywhere in this module.
* **Pure function** — never mutates ``graph_slice``, ``ordered_nodes``, or
  ``request``.
* **Imports at module top** — no mid-module imports.

Warning codes
-------------
``adaptive_learner_claim_unmatched``
    Emitted once per unmatched claim item (deduplicated by claim text).
    ``source_ref`` carries the claim text so the accumulator deduplicates
    across the ``knows``, ``weak``, and ``goals`` collections.
"""

from __future__ import annotations

from typing import Any

from akms_learn.capability_gates import require_capability
from akms_learn.graph_import import GraphSlice
from akms_learn.models import LearningWarning
from akms_learn.models.learner_profile import LearnerProfile
from akms_learn.requests import LearningRequest
from akms_learn.warnings import WarningAccumulator

__all__ = [
    "AdaptivePathResult",
    "adaptive_path_mode",
]

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class AdaptivePathResult:
    """Structured result from :func:`adaptive_path_mode`.

    Attributes
    ----------
    active_nodes:
        Sorted list of node ids that are included in the lesson body
        (prerequisites NOT skipped).
    provenance_skipped:
        List of provenance records for nodes that were skipped.  Each record
        is a dict with keys ``node_id``, ``reason``, ``source``.  Empty when
        ``conservative_mode=True`` or when no prerequisite is covered by
        ``knows``.
    adaptive_summary:
        Plain-text Markdown block summarising the personalisation decisions:
        skipped count, reason summary, and a profile echo.
    warnings:
        List of :class:`~akms_learn.models.LearningWarning` instances emitted
        during compilation (unmatched claims, etc.).
    lesson_body:
        Dict mapping each active node id to its raw node dict (read-only copy).
    """

    __slots__ = (
        "active_nodes",
        "provenance_skipped",
        "adaptive_summary",
        "warnings",
        "lesson_body",
    )

    def __init__(
        self,
        active_nodes: list[str],
        provenance_skipped: list[dict[str, Any]],
        adaptive_summary: str,
        warnings: list[LearningWarning],
        lesson_body: dict[str, dict[str, Any]],
    ) -> None:
        self.active_nodes = active_nodes
        self.provenance_skipped = provenance_skipped
        self.adaptive_summary = adaptive_summary
        self.warnings = warnings
        self.lesson_body = lesson_body


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalise_claim(claim: str) -> str:
    """Lowercase + strip a single learner claim for matching."""
    return claim.strip().lower()


def _build_graph_vocabulary(nodes_by_id: dict[str, dict[str, Any]]) -> frozenset[str]:
    """Return the set of all valid graph tokens: node ids + tags (normalised).

    Used to validate learner claims against the actual graph vocabulary.
    Every node id and every tag value is included.  A frozenset is returned
    so membership tests are O(1); callers that need a deterministic order
    must sort the result themselves.
    """
    tokens: set[str] = set()
    for nid, node in nodes_by_id.items():
        tokens.add(_normalise_claim(nid))
        for tag in node.get("tags") or []:
            tokens.add(_normalise_claim(str(tag)))
    return frozenset(tokens)


def _check_claims(
    claims: tuple[str, ...],
    claim_type: str,
    graph_vocab: frozenset[str],
    acc: WarningAccumulator,
) -> None:
    """Emit a warning for each claim in *claims* not found in *graph_vocab*.

    Parameters
    ----------
    claims:
        Tuple of learner-declared strings (knows / weak / goals).
    claim_type:
        Label for the warning message (``"knows"`` / ``"weak"`` / ``"goals"``).
    graph_vocab:
        Normalised graph vocabulary from :func:`_build_graph_vocabulary`.
    acc:
        Warning accumulator; deduplication is handled by the accumulator.
    """
    for claim in sorted(claims):  # sorted for deterministic warning order
        normalised = _normalise_claim(claim)
        if normalised not in graph_vocab:
            # ``source_ref`` carries a structured ``<claim_type>::<claim>`` key
            # so downstream consumers can recover both the claim text and the
            # claim category without parsing the human-readable message.
            acc.append(
                LearningWarning(
                    severity="warning",
                    code="adaptive_learner_claim_unmatched",
                    message=(
                        f"Learner {claim_type!r} claim {claim!r} does not match "
                        "any graph tag or node id."
                    ),
                    source_ref=f"{claim_type}::{normalised}",
                )
            )


def _node_covered_by_knows(
    node: dict[str, Any],
    knows_normalised: frozenset[str],
) -> bool:
    """Return True if ``knows`` covers the node.

    A node is considered covered when:

    * Its ``node_id`` (normalised) appears in ``knows_normalised``, **OR**
    * Every tag on the node (normalised) appears in ``knows_normalised``.

    The second condition (tags) is intentionally strict: *every* tag must
    match, not just one.  This prevents aggressive skipping on loosely-tagged
    nodes where a single shared tag (e.g. ``"toy"``) would otherwise
    disqualify the whole node.
    """
    nid_norm = _normalise_claim(node.get("node_id") or "")
    if nid_norm and nid_norm in knows_normalised:
        return True

    tags = [_normalise_claim(str(t)) for t in (node.get("tags") or [])]
    if tags and all(t in knows_normalised for t in tags):
        return True

    return False


def _find_source_edge(
    node_id: str,
    edges: tuple[dict[str, Any], ...],
) -> str:
    """Return the edge_id of the first ``requires`` edge pointing at *node_id*.

    Used to populate the ``source`` field of a provenance-skipped record.
    Falls back to ``"<direct_learner_claim>"`` when no such edge exists in
    the slice (the node was matched by node_id directly, not via a graph edge).
    """
    for edge in edges:
        if edge.get("type") == "requires" and edge.get("to") == node_id:
            eid = edge.get("edge_id")
            if eid is not None:
                return str(eid)
    return "<direct_learner_claim>"


def _build_adaptive_summary(
    profile: LearnerProfile,
    active_count: int,
    skipped_count: int,
) -> str:
    """Build the Markdown adaptive_summary block.

    The summary includes:

    * A profile echo (knows / weak / goals) so a reviewer can confirm the
      profile that drove the compilation.
    * A personalisation decision summary (how many nodes were skipped and why).

    Returns a Markdown string suitable for embedding in the lesson body.
    """
    lines: list[str] = [
        "## Adaptive Path Summary",
        "",
        "### Learner Profile",
        f"- **knows**: {', '.join(sorted(profile.knows)) or '(none declared)'}",
        f"- **weak**: {', '.join(sorted(profile.weak)) or '(none declared)'}",
        f"- **goals**: {', '.join(sorted(profile.goals)) or '(none declared)'}",
        f"- **conservative_mode**: {profile.conservative_mode}",
        "",
        "### Personalisation Decisions",
    ]

    if profile.conservative_mode:
        lines.append(
            "Conservative mode is active — no prerequisite nodes were skipped."
        )
    elif skipped_count == 0:
        lines.append(
            "No prerequisite nodes were skipped (no claims matched graph nodes)."
        )
    else:
        lines.append(
            f"{skipped_count} prerequisite node(s) skipped because every "
            "declared fact about them is covered by the learner's `knows` list."
        )

    lines += [
        "",
        f"Active nodes: {active_count}",
        f"Skipped nodes: {skipped_count}",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def adaptive_path_mode(
    graph_slice: GraphSlice,
    ordered_nodes: list[str],
    request: LearningRequest,
) -> tuple["AdaptivePathResult", list[LearningWarning]]:
    """Build the adaptive_path mode view.

    Requires the ``llm`` extra to be installed.  If the extra is absent,
    :class:`~akms_learn.capability_gates.PreconditionError` is raised before
    any computation is done.

    Pure function — never mutates ``graph_slice``, ``ordered_nodes``, or
    ``request``.

    Parameters
    ----------
    graph_slice:
        Immutable :class:`~akms_learn.graph_import.GraphSlice` from the
        compiler pipeline.
    ordered_nodes:
        Node id list in learning order (from the ordering strategy).
    request:
        The validated :class:`~akms_learn.requests.LearningRequest`.  The
        ``learner_profile`` field is consumed here; a ``None`` profile is
        treated as a default-conservative profile.

    Returns
    -------
    (result, warnings)
        ``result`` is an :class:`AdaptivePathResult`.
        ``warnings`` is a list of :class:`~akms_learn.models.LearningWarning`
        (same list as ``result.warnings``).

    Raises
    ------
    PreconditionError
        When the ``llm`` extra is not installed.
    """
    # ------------------------------------------------------------------
    # Capability gate — must be the very first operation.
    # ------------------------------------------------------------------
    require_capability("adaptive_path")

    # ------------------------------------------------------------------
    # Resolve the learner profile — default to conservative if absent.
    # ------------------------------------------------------------------
    profile: LearnerProfile = request.learner_profile or LearnerProfile()

    # ------------------------------------------------------------------
    # Index nodes by id (read-only copies).
    # ------------------------------------------------------------------
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for raw in graph_slice.nodes:
        nid = raw.get("node_id")
        if nid is not None:
            nodes_by_id[nid] = dict(raw)

    # ------------------------------------------------------------------
    # Build graph vocabulary for claim validation.
    # ------------------------------------------------------------------
    graph_vocab: frozenset[str] = _build_graph_vocabulary(nodes_by_id)

    # ------------------------------------------------------------------
    # Emit warnings for unmatched learner claims (knows / weak / goals).
    # ------------------------------------------------------------------
    acc = WarningAccumulator()
    _check_claims(profile.knows, "knows", graph_vocab, acc)
    _check_claims(profile.weak, "weak", graph_vocab, acc)
    _check_claims(profile.goals, "goals", graph_vocab, acc)

    # ------------------------------------------------------------------
    # Determine active vs. skipped nodes.
    # Conservative mode: short-circuit — include everything, skip nothing.
    # ------------------------------------------------------------------
    provenance_skipped: list[dict[str, Any]] = []
    active_nodes: list[str] = []

    if profile.conservative_mode:
        # No skipping ever — full pass-through.
        active_nodes = [nid for nid in ordered_nodes if nid in nodes_by_id]
    else:
        knows_normalised: frozenset[str] = frozenset(
            _normalise_claim(k) for k in profile.knows
        )
        for nid in ordered_nodes:
            node = nodes_by_id.get(nid)
            if node is None:
                continue
            if _node_covered_by_knows(node, knows_normalised):
                source_edge = _find_source_edge(nid, graph_slice.edges)
                provenance_skipped.append(
                    {
                        "node_id": nid,
                        "reason": "covered_by_knows",
                        "source": source_edge,
                    }
                )
            else:
                active_nodes.append(nid)

    # Provenance list must be deterministically ordered.
    provenance_skipped = sorted(provenance_skipped, key=lambda r: r["node_id"])

    # ------------------------------------------------------------------
    # Build lesson body from active nodes (sorted for determinism in
    # the dict; iteration order matches active_nodes list order).
    # ------------------------------------------------------------------
    lesson_body: dict[str, dict[str, Any]] = {
        nid: dict(nodes_by_id[nid])
        for nid in sorted(active_nodes)
        if nid in nodes_by_id
    }

    # ------------------------------------------------------------------
    # Build adaptive summary.
    # ------------------------------------------------------------------
    adaptive_summary = _build_adaptive_summary(
        profile=profile,
        active_count=len(active_nodes),
        skipped_count=len(provenance_skipped),
    )

    # ------------------------------------------------------------------
    # Finalise warnings.
    # ------------------------------------------------------------------
    warnings = acc.finalize()

    result = AdaptivePathResult(
        active_nodes=sorted(active_nodes),
        provenance_skipped=provenance_skipped,
        adaptive_summary=adaptive_summary,
        warnings=warnings,
        lesson_body=lesson_body,
    )
    return result, warnings
