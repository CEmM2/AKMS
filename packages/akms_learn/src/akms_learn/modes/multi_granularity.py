"""Mode: multi_granularity — emit overview / standard / deep_dive variants.

Behaviour
---------
Detect the requested granularity from one of four conventions, in priority
order, and select an appropriate subset (or superset) of the ordered nodes:

1. **Explicit request selection** — :attr:`LearningRequest.granularity` is
   set to ``"overview"`` / ``"standard"`` / ``"deep_dive"``.
2. **Tag-based selection** — any node carries one of the tags ``"coarse"``,
   ``"standard"``, or ``"fine"`` (mapping ``coarse → overview``,
   ``standard → standard``, ``fine → deep_dive``). The most-permissive
   present tag wins (``fine`` beats ``standard`` beats ``coarse``) so the
   inferred level reflects the deepest content available in the slice.
3. **Id prefix/suffix selection** — any node id starts or ends with
   ``"coarse"``, ``"standard"``, or ``"fine"`` (with optional ``_`` /
   ``-`` separator). Same coarse/standard/fine semantics as the tag path.
4. **Domain / subdomain grouping** — when all nodes share exactly one
   ``(domain, subdomain)`` pair we treat the slice as a single
   granularity family and default to ``"standard"``.

If no signal is found the selector falls back to ``"standard"`` and emits a
single :class:`LearningWarning` with code
:data:`GRANULARITY_INFERENCE_FALLBACK_CODE`.

Selection semantics
-------------------
* ``overview``  → coarse / unmarked nodes (drop ``fine``-marked nodes).
* ``standard``  → coarse + standard nodes (drop ``fine`` only).
* ``deep_dive`` → every node in the slice.

Determinism
-----------
The mode never mutates the input slice. The ordered-node list is taken from
:func:`akms_learn.ordering.order_nodes` so the alphabetic-max
cycle-break and bucket order are preserved.

LSP-only metadata
-----------------
Per the Phase 2 context (§"Key Principles" item 3), the resolved
``selected_granularity`` lives on the LSP request block and on the
:class:`MultiGranularityResult`. It MUST NOT be written into the AKMS v2
graph. The mode is a pure function that returns a result struct; it never
mutates the slice.

Warning codes
-------------
``granularity_inference_fallback``
    Emitted exactly once when no convention (request / tag / id /
    domain) yields a usable signal. ``source_ref`` is the graph slice's
    ``metadata['family']`` value (or ``"<unknown-slice>"`` when absent).
    The compiler defaults to ``"standard"`` in this branch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from akms_learn.graph_import import GraphSlice
from akms_learn.models import LearningWarning
from akms_learn.ordering import order_nodes
from akms_learn.requests import LearningRequest

__all__ = [
    "Granularity",
    "MultiGranularityResult",
    "DEFAULT_GRANULARITY",
    "GRANULARITY_INFERENCE_FALLBACK_CODE",
    "GRANULARITY_VALUES",
    "TAG_TO_GRANULARITY",
    "multi_granularity_mode",
    "multi_granularity_strategy",
    "DetectionMethod",
]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

Granularity = Literal["overview", "standard", "deep_dive"]

DEFAULT_GRANULARITY: Granularity = "standard"
"""Default granularity used when no convention signal is found."""

GRANULARITY_INFERENCE_FALLBACK_CODE: str = "granularity_inference_fallback"
"""Stable warning code emitted when granularity cannot be inferred."""

GRANULARITY_VALUES: tuple[Granularity, ...] = ("overview", "standard", "deep_dive")
"""Canonical ordered tuple of granularity values."""

#   # Tag → granularity mapping. ``coarse`` and ``fine`` are the
#   # convention-level vocabulary; the canonical mode-level names are kept in
#   # :data:`GRANULARITY_VALUES`. The mapping is intentionally narrow —
#   # anything else is ignored at the tag-based detection step.
TAG_TO_GRANULARITY: dict[str, Granularity] = {
    "coarse": "overview",
    "standard": "standard",
    "fine": "deep_dive",
}

# Same mapping for id-prefix / id-suffix detection. Kept separate so future
# id-vocabulary expansion does not entangle the tag set.
_ID_TOKEN_TO_GRANULARITY: dict[str, Granularity] = {
    "coarse": "overview",
    "standard": "standard",
    "fine": "deep_dive",
}

# Permissiveness order: higher index = more permissive level. Used to pick the
# "deepest signal present" so a slice tagged with both ``coarse`` and ``fine``
# infers ``deep_dive`` rather than collapsing back to ``overview``.
_GRANULARITY_RANK: dict[Granularity, int] = {
    "overview": 0,
    "standard": 1,
    "deep_dive": 2,
}

DetectionMethod = Literal[
    "request",
    "tag",
    "id_prefix",
    "domain_grouping",
    "fallback",
]


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class MultiGranularityResult:
    """Structured result from :func:`multi_granularity_mode`.

    Attributes
    ----------
    selected_granularity:
        The resolved granularity literal. Always one of
        :data:`GRANULARITY_VALUES`.
    detection_method:
        How :attr:`selected_granularity` was inferred. One of
        ``request`` / ``tag`` / ``id_prefix`` / ``domain_grouping`` /
        ``fallback``.
    rationale:
        Human-readable string describing why this granularity was picked.
        Suitable for surfacing in the bundle manifest.
    ordered_nodes:
        Final node id list after the granularity-aware filter is applied.
        Same authoritative default order as :func:`order_nodes`.
    dropped_nodes:
        Sorted list of node ids that were filtered out by the granularity
        level (empty for ``deep_dive``).
    source_node_ids:
        Sorted list of node ids that contributed to the result.
    warnings:
        List of :class:`LearningWarning` instances; includes the
        ``granularity_inference_fallback`` entry when the selector could
        not decide.
    """

    selected_granularity: Granularity
    detection_method: DetectionMethod
    rationale: str
    ordered_nodes: list[str]
    dropped_nodes: list[str]
    source_node_ids: list[str]
    warnings: list[LearningWarning] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _normalise_request_value(raw: Any) -> Optional[Granularity]:
    """Return *raw* as a canonical granularity literal, or None."""
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if text in GRANULARITY_VALUES:
        return text  # type: ignore[return-value]
    return None


def _pick_most_permissive(
    found: list[Granularity],
) -> Optional[Granularity]:
    """Return the most-permissive granularity in *found*, or None."""
    if not found:
        return None
    return max(found, key=lambda g: _GRANULARITY_RANK[g])


def _granularity_from_tags(node: dict[str, Any]) -> Optional[Granularity]:
    """Return the most-permissive granularity inferred from a node's tags."""
    found: list[Granularity] = []
    for tag in node.get("tags") or []:
        key = str(tag).strip().lower()
        mapped = TAG_TO_GRANULARITY.get(key)
        if mapped is not None:
            found.append(mapped)
    return _pick_most_permissive(found)


def _granularity_from_id(node: dict[str, Any]) -> Optional[Granularity]:
    """Return the granularity inferred from a node's id prefix/suffix.

    Accepts ``coarse_*``, ``*_coarse``, ``coarse-*``, ``*-coarse`` and the
    analogous shapes for ``standard`` and ``fine``. Case-insensitive.
    First-match wins (one signal per node id).
    """
    nid = node.get("node_id") or node.get("id")
    if not nid:
        return None
    text = str(nid).strip().lower()
    for token, granularity in _ID_TOKEN_TO_GRANULARITY.items():
        if (
            text.startswith(f"{token}_")
            or text.startswith(f"{token}-")
            or text.endswith(f"_{token}")
            or text.endswith(f"-{token}")
        ):
            return granularity
    return None


def _detect_from_tags(
    nodes: tuple[dict[str, Any], ...],
) -> Optional[Granularity]:
    """Scan node tags for ``coarse`` / ``standard`` / ``fine`` markers.

    Returns the most-permissive granularity whose tag is present, or
    ``None`` when no tag matches. Tag comparison is case-insensitive.
    """
    found: list[Granularity] = []
    for node in nodes:
        per_node = _granularity_from_tags(node)
        if per_node is not None:
            found.append(per_node)
    return _pick_most_permissive(found)


def _detect_from_ids(
    nodes: tuple[dict[str, Any], ...],
) -> Optional[Granularity]:
    """Scan node ids for ``coarse`` / ``standard`` / ``fine`` prefixes/suffixes."""
    found: list[Granularity] = []
    for node in nodes:
        per_node = _granularity_from_id(node)
        if per_node is not None:
            found.append(per_node)
    return _pick_most_permissive(found)


def _detect_from_domain_grouping(
    nodes: tuple[dict[str, Any], ...],
) -> Optional[Granularity]:
    """Domain/subdomain grouping fallback.

    When every node in the slice shares the same ``(domain, subdomain)``
    pair AND that pair is non-trivial (i.e. neither component is empty /
    None), treat the slice as a single granularity family and select
    :data:`DEFAULT_GRANULARITY`. Otherwise return ``None`` so the caller
    can fall back to the warning path.
    """
    if not nodes:
        return None
    pairs: set[tuple[Optional[str], Optional[str]]] = set()
    for node in nodes:
        domain = node.get("domain")
        subdomain = node.get("subdomain")
        if not domain or not subdomain:
            return None
        pairs.add((str(domain).strip().lower(), str(subdomain).strip().lower()))
    if len(pairs) == 1:
        return DEFAULT_GRANULARITY
    return None


def _filter_nodes_by_granularity(
    ordered_ids: list[str],
    nodes_by_id: dict[str, dict[str, Any]],
    granularity: Granularity,
) -> tuple[list[str], list[str]]:
    """Filter *ordered_ids* by *granularity*; return ``(kept, dropped)``.

    Filter semantics:

    * ``overview``  — drop nodes carrying the ``fine`` tag OR a ``fine_`` /
      ``_fine`` (etc.) id token. The ``coarse`` and unmarked nodes are kept.
    * ``standard``  — drop ``fine`` only. Keep ``coarse``, ``standard``,
      and unmarked nodes.
    * ``deep_dive`` — keep everything (the empty-drop baseline).
    """
    if granularity == "deep_dive":
        return list(ordered_ids), []

    drop_levels: set[Granularity]
    if granularity == "overview":
        # Overview is the shallowest level — drop anything marked as fine
        # (deep_dive). Standard-marked nodes are also dropped so the
        # overview is genuinely narrower than the standard variant.
        drop_levels = {"deep_dive", "standard"}
    elif granularity == "standard":
        drop_levels = {"deep_dive"}
    else:  # pragma: no cover - exhaustive Literal coverage
        drop_levels = set()

    kept: list[str] = []
    dropped: list[str] = []
    for nid in ordered_ids:
        node = nodes_by_id.get(nid, {})
        node_level = _node_granularity_level(node)
        if node_level in drop_levels:
            dropped.append(nid)
        else:
            kept.append(nid)
    return kept, sorted(dropped)


def _node_granularity_level(node: dict[str, Any]) -> Optional[Granularity]:
    """Return the inferred granularity level for a single node, or None.

    Uses the same shared helpers as :func:`_detect_from_tags` and
    :func:`_detect_from_ids` so the per-node filter step and the
    slice-level detectors stay in lockstep. When a node carries multiple
    signals the most-permissive wins (same rule as the slice-level
    detector).
    """
    found: list[Granularity] = []
    tag_pick = _granularity_from_tags(node)
    if tag_pick is not None:
        found.append(tag_pick)
    id_pick = _granularity_from_id(node)
    if id_pick is not None:
        found.append(id_pick)
    return _pick_most_permissive(found)


def _slice_family_ref(graph_slice: GraphSlice) -> str:
    """Return a stable ``source_ref`` string for warnings on this slice."""
    family = (graph_slice.metadata or {}).get("family")
    if family:
        return str(family)
    version = (graph_slice.metadata or {}).get("graph_version")
    if version:
        return str(version)
    return "<unknown-slice>"


# ---------------------------------------------------------------------------
# Public ordering strategy (registered in ordering.py)
# ---------------------------------------------------------------------------


def multi_granularity_strategy(
    graph_slice: GraphSlice,
) -> tuple[list[str], list[LearningWarning]]:
    """Ordering strategy for the ``multi_granularity`` mode.

    Returns the default-ordered node list unchanged — without a request
    object the strategy cannot read explicit granularity selection or
    emit a meaningful warning, so it does NOT filter. The full
    :func:`multi_granularity_mode` is the supported API for the rich
    result (filter, rationale, fallback warning, detection method).
    """
    return order_nodes(graph_slice)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def multi_granularity_mode(
    graph_slice: GraphSlice,
    request: LearningRequest,
) -> tuple[MultiGranularityResult, list[LearningWarning]]:
    """Build the multi_granularity mode view.

    Pure function — never mutates ``graph_slice`` or ``request``.

    Parameters
    ----------
    graph_slice:
        Immutable :class:`~akms_learn.graph_import.GraphSlice` from the
        compiler pipeline.
    request:
        The validated :class:`~akms_learn.requests.LearningRequest`. Reads
        ``request.granularity`` (Optional). Unrecognised values are
        treated as "no explicit selection" and fall through to convention
        detection.

    Returns
    -------
    (result, warnings)
        ``result`` is a :class:`MultiGranularityResult` exposing
        ``selected_granularity``, ``detection_method``, ``rationale``,
        the filtered node list and the dropped-node list.
        ``warnings`` is the same list as ``result.warnings`` —
        includes :data:`GRANULARITY_INFERENCE_FALLBACK_CODE` when no
        signal was available.
    """
    nodes_tuple: tuple[dict[str, Any], ...] = tuple(graph_slice.nodes)
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for raw in nodes_tuple:
        nid = raw.get("node_id") or raw.get("id")
        if nid is not None:
            nodes_by_id[str(nid)] = dict(raw)

    # Authoritative default ordering — preserves the alphabetic-max
    # cycle-break and the bucket order.
    default_ordered, default_warnings = order_nodes(graph_slice)

    warnings: list[LearningWarning] = []
    #   # Forward all default-ordering warnings unchanged (matches the other
    #       # ordering modes).
    warnings.extend(default_warnings)

    # ------------------------------------------------------------------
    # Convention priority order:
    #
    #   1. explicit request selection
    #   2. tag-based detection
    #   3. id prefix/suffix detection
    #   4. domain/subdomain grouping
    #   5. fallback → DEFAULT_GRANULARITY + warning
    # ------------------------------------------------------------------
    selected: Optional[Granularity]
    method: DetectionMethod
    rationale: str

    explicit = _normalise_request_value(getattr(request, "granularity", None))
    if explicit is not None:
        selected = explicit
        method = "request"
        rationale = (
            f"Explicit request.granularity={explicit!r}; convention "
            f"detection skipped."
        )
    else:
        tag_pick = _detect_from_tags(nodes_tuple)
        if tag_pick is not None:
            selected = tag_pick
            method = "tag"
            rationale = (
                f"Inferred granularity={tag_pick!r} from node tags "
                f"(coarse / standard / fine vocabulary)."
            )
        else:
            id_pick = _detect_from_ids(nodes_tuple)
            if id_pick is not None:
                selected = id_pick
                method = "id_prefix"
                rationale = (
                    f"Inferred granularity={id_pick!r} from node id "
                    f"prefix/suffix conventions."
                )
            else:
                domain_pick = _detect_from_domain_grouping(nodes_tuple)
                if domain_pick is not None:
                    selected = domain_pick
                    method = "domain_grouping"
                    rationale = (
                        f"Inferred granularity={domain_pick!r} from shared "
                        f"(domain, subdomain) grouping; defaulted to "
                        f"{DEFAULT_GRANULARITY!r}."
                    )
                else:
                    selected = DEFAULT_GRANULARITY
                    method = "fallback"
                    rationale = (
                        f"No granularity signal in request, tags, ids, or "
                        f"domain grouping; defaulted to "
                        f"{DEFAULT_GRANULARITY!r}."
                    )
                    warnings.append(
                        LearningWarning(
                            severity="warning",
                            code=GRANULARITY_INFERENCE_FALLBACK_CODE,
                            source_ref=_slice_family_ref(graph_slice),
                            message=(
                                "Granularity could not be inferred from the "
                                "request, node tags, node ids, or domain "
                                "grouping; defaulting to "
                                f"{DEFAULT_GRANULARITY!r}."
                            ),
                        )
                    )

    # Apply the granularity-aware filter.
    kept, dropped = _filter_nodes_by_granularity(
        default_ordered, nodes_by_id, selected
    )

    source_node_ids = sorted(nid for nid in kept if nid in nodes_by_id)

    result = MultiGranularityResult(
        selected_granularity=selected,
        detection_method=method,
        rationale=rationale,
        ordered_nodes=kept,
        dropped_nodes=dropped,
        source_node_ids=source_node_ids,
        warnings=warnings,
    )
    return result, warnings
