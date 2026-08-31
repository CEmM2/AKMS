"""9-stage LSP compiler pipeline orchestration (plan §9, L167-L217).

This module implements :func:`compile_learning_source` — the public entry point
that fans-in every Phase 2 / Phase 3 module and produces a fully-validated
:class:`~akms_learn.models.LearningSourcePacket`.

The 9 stages run in fixed order, with explicit instrumentation via
:attr:`CompileResult.stage_log`:

1. ``plugin_compat_check``
2. ``request_normalization``
3. ``graph_source_resolution``
4. ``seed_tag_handling``
5. ``slice_conversion``
6. ``learning_ordering``
7. ``section_extraction``
8. ``packet_assembly_and_validation``
9. ``export``

**Determinism contract** (plan §9 + Phase 3 context summary L17):
Every stage MUST produce the same output bytes when fed the same input,
*except* for the :class:`~akms_learn.models.LearningSourcePacket.created_at`
timestamp. Test :func:`test_compile_byte_stable_except_timestamp` enforces
this.

**Read-only graph access**: this orchestrator never mutates ``graph_slice`` or
any node/edge dict it receives. The seed-tag filter constructs a fresh
:class:`~akms_learn.graph_import.GraphSlice` rather than mutating the input.

Spec refs: the akms-learn internal specification (not published),
plan1 §9 L167-L217, plan1 §21 L394-L411.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pydantic

if TYPE_CHECKING:
    # Imported lazily at runtime inside the LLM expansion step to mirror the
    # established mode-import pattern in this module (multi_granularity /
    # adaptive_path are likewise imported inside the pipeline) and avoid an
    # import cycle through ``akms_learn.modes``.
    from akms_learn.modes.llm_expanded import LLMExpansionRequest

from akms_learn._code_links import (
    build_code_links as _shared_build_code_links,
)
from akms_learn._code_links import (
    coerce_line_range as _coerce_line_range,
)
from akms_learn.domain_packs import (
    DomainPackRegistry,
    LearningCapabilityError,
    SourcePackDescriptor,
    build_registry_from_paths,
    load_source_pack_from_yaml,
)
from akms_learn.exporters import KNOWN_EXPORTERS
from akms_learn.graph_import import (
    GraphSlice,
    compute_graph_hash,
    load_graph,
)
from akms_learn.models import (
    AssessmentView,
    CodeLinkView,
    CompilerInfo,
    GeneratedSection,
    LearningEdgeView,
    LearningNodeView,
    LearningRequestInfo,
    LearningSourcePacket,
    LearningWarning,
    PacketBody,
    PitfallView,
    ReferenceView,
    SourceInfo,
    build_llm_provenance,
)
from akms_learn.ordering import STRATEGY_KEYS, get_strategy
from akms_learn.plugin import Plugin, get_plugin
from akms_learn.requests import LearningRequest, normalize_request, request_hash
from akms_learn.sections import extract_sections
from akms_learn.validation import validate_packet
from akms_learn.warnings import (
    WarningAccumulator,
    emit_code_mirror_missing_source_path_warning,
)

__all__ = [
    "STAGES",
    "CompileResult",
    "compile_learning_source",
]


# ---------------------------------------------------------------------------
# Stage names — fixed order, asserted by :func:`test_compile_stage_order`.
# ---------------------------------------------------------------------------

STAGES: tuple[str, ...] = (
    "plugin_compat_check",
    "request_normalization",
    "graph_source_resolution",
    "seed_tag_handling",
    "slice_conversion",
    "learning_ordering",
    "section_extraction",
    "packet_assembly_and_validation",
    "export",
)


# ---------------------------------------------------------------------------
# CompileResult
# ---------------------------------------------------------------------------


@dataclass
class CompileResult:
    """Result bundle returned by :func:`compile_learning_source`.

    Fields
    ------
    packet:
        The fully-assembled, validated :class:`LearningSourcePacket`.
    packet_path:
        Filesystem path the canonical JSON packet was written to (Stage 9),
        or ``None`` when no ``output_dir`` was supplied.
    export_paths:
        Paths of every artifact produced by Stage 9 exporters. Always
        includes ``packet_path`` when present.
    warnings:
        Accumulated :class:`LearningWarning` instances from every stage.
    unavailable_capabilities:
        Capability strings that were requested but not satisfied by either
        the static plugin set or the domain-pack registry.
    stage_log:
        List of stage names appended *after* each stage completes. Always
        ends equal to ``STAGES`` on success.
    """

    packet: LearningSourcePacket
    packet_path: Path | None = None
    export_paths: list[Path] = field(default_factory=list)
    warnings: list[LearningWarning] = field(default_factory=list)
    unavailable_capabilities: list[str] = field(default_factory=list)
    stage_log: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_graph_slice(
    graph_path: str | Path | None,
    graph_slice: Any,
) -> GraphSlice:
    """Resolve ``graph_path`` / ``graph_slice`` into a validated GraphSlice.

    Accepts a ``GraphSlice`` instance directly (passes through) or a dict
    payload (forwarded to :func:`load_graph`).
    """
    if isinstance(graph_slice, GraphSlice):
        if graph_path is not None:
            raise ValueError(
                "compile_learning_source: 'graph_path' and 'graph_slice' "
                "are mutually exclusive — supply exactly one, not both."
            )
        return graph_slice
    return load_graph(graph_path=graph_path, graph_slice=graph_slice)


def _node_id(node: dict[str, Any]) -> str:
    """Return the canonical id of a node dict.

    Provenance requires every node carry a ``node_id``; we raise rather than
    fabricate a fallback (e.g. ``"id"``) because a missing identifier breaks
    deterministic ordering, section attachment, and reading-order assembly.
    """
    nid = node.get("node_id")
    if not nid:
        raise ValueError(f"GraphSlice node missing required 'node_id': {node!r}")
    return str(nid)


def _request_get(
    request: LearningRequest | dict[str, Any], name: str, default: Any = None
) -> Any:
    """Look up *name* on *request*, supporting both Pydantic models and dicts.

    ``compile_learning_source`` accepts ``request`` as either a
    :class:`LearningRequest` instance OR a raw ``dict`` (see signature).
    Using bare ``getattr`` on a dict silently returns the default because
    dict keys are not attributes — that caused two regressions caught in
    PR review:

    * ``required_capabilities`` checks were skipped for dict requests.
    * ``akms_schema`` overrides were ignored, always falling through to v2.

    This helper centralises the dual-shape lookup so every read of a
    request field goes through one well-tested path.
    """
    if isinstance(request, dict):
        return request.get(name, default)
    return getattr(request, name, default)


# Granularity literals accepted by ``LearningRequest.granularity``. Mirrors the
# ``Literal[...]`` on the model; kept here so the dict-coercion below can pre-
# sanitise the field without importing the mode-level constant.
_GRANULARITY_LITERALS = frozenset({"overview", "standard", "deep_dive"})


def _as_learning_request(
    request: LearningRequest | dict[str, Any],
) -> LearningRequest:
    """Coerce *request* to a :class:`LearningRequest` for mode dispatch.

    ``compile_learning_source`` accepts ``request`` as either a
    :class:`LearningRequest` OR a raw ``dict`` (the CLI builds dicts). The
    ``multi_granularity`` and ``adaptive_path`` modes read attributes
    (``request.granularity`` / ``request.learner_profile``) that a bare dict
    does not expose: ``adaptive_path_mode`` would raise ``AttributeError`` and
    ``multi_granularity_mode`` would silently treat the granularity as unset.
    This converts dict requests once so both modes see a real model.

    ``granularity`` is a ``Literal`` on the model, so strict validation of a
    dict carrying an unrecognised value would *raise* where the old
    ``getattr``-on-dict path silently fell back to ``None``. To preserve that
    permissiveness, an out-of-range ``granularity`` is coerced to ``None``
    before validation (the mode then re-derives it from conventions).
    """
    if isinstance(request, LearningRequest):
        return request
    data = dict(request)
    gran = data.get("granularity")
    if gran is not None and str(gran).strip().lower() not in _GRANULARITY_LITERALS:
        data["granularity"] = None
    return LearningRequest.model_validate(data)


def _build_llm_expansion_request(
    request: LearningRequest | dict[str, Any],
) -> LLMExpansionRequest | None:
    """Build an :class:`LLMExpansionRequest` from *request*, or ``None``.

    **Single mapping adapter.**  This is the ONE place where the public
    :class:`~akms_learn.requests.LearningRequest` ``llm_*`` fields are mapped
    onto the mode-internal :class:`~akms_learn.modes.llm_expanded.LLMExpansionRequest`
    fields::

        llm_enable  → enable_llm
        llm_provider → provider
        llm_policy  → policy
        sources     → sources

    Returning ``None`` (when ``llm_enable`` is falsy) means the compiler skips
    the LLM step entirely, preserving the byte-identical deterministic
    baseline.

    Raises
    ------
    ValueError
        When ``llm_policy`` is set to a value not in
        :data:`~akms_learn.models.llm_expansion.LLM_EXPANSION_POLICIES`.
    """
    if not _request_get(request, "llm_enable", False):
        return None

    from akms_learn.models.llm_expansion import LLM_EXPANSION_POLICIES
    from akms_learn.modes.llm_expanded import LLMExpansionRequest

    provider = _request_get(request, "llm_provider", None)
    policy = _request_get(request, "llm_policy", None)
    sources = _request_get(request, "sources", None)

    # Validate policy against the known literals before constructing the
    # internal request — reject unknown values with a clear error so callers
    # get actionable feedback rather than a cryptic Pydantic ValidationError.
    if policy is not None and policy not in LLM_EXPANSION_POLICIES:
        raise ValueError(
            f"Unknown llm_policy {policy!r}. Allowed values: {list(LLM_EXPANSION_POLICIES)}"
        )

    kwargs: dict[str, Any] = {"enable_llm": True}
    if provider is not None:
        kwargs["provider"] = provider
    if policy is not None:
        kwargs["policy"] = policy
    if sources is not None:
        kwargs["sources"] = sources
    return LLMExpansionRequest(**kwargs)


def _filter_by_seed_tags(slice_: GraphSlice, seed_tags: list[str]) -> GraphSlice:
    """Return a fresh GraphSlice filtered by ``seed_tags`` (deterministic).

    Semantics (plan §9 stage 4):

    * If ``seed_tags`` is empty, every node is retained (slice copy returned).
    * Otherwise, retain nodes whose ``tags`` (case-insensitive) intersect
      ``seed_tags``.
    * Edges are kept iff both endpoints survive the node filter.
    * Filtered nodes are emitted sorted by ``node_id`` for byte-stability;
      filtered edges are sorted by ``edge_id``.

    The input ``slice_`` is NEVER mutated.
    """
    seed_lower = {t.strip().lower() for t in seed_tags if t and t.strip()}

    if not seed_lower:
        # No filtering — still sort for stable output.
        sorted_nodes = tuple(sorted(slice_.nodes, key=_node_id))
        sorted_edges = tuple(sorted(slice_.edges, key=lambda e: e.get("edge_id", "")))
        return GraphSlice(
            nodes=sorted_nodes,
            edges=sorted_edges,
            metadata=dict(slice_.metadata),
        )

    kept_nodes: list[dict[str, Any]] = []
    kept_ids: set[str] = set()
    for node in slice_.nodes:
        node_tags = {str(t).strip().lower() for t in (node.get("tags") or []) if t}
        if seed_lower & node_tags:
            kept_nodes.append(node)
            kept_ids.add(_node_id(node))

    kept_edges = [
        e for e in slice_.edges if e.get("from") in kept_ids and e.get("to") in kept_ids
    ]

    kept_nodes.sort(key=_node_id)
    kept_edges.sort(key=lambda e: e.get("edge_id", ""))

    return GraphSlice(
        nodes=tuple(kept_nodes),
        edges=tuple(kept_edges),
        metadata=dict(slice_.metadata),
    )


def _build_node_view(
    node: dict[str, Any],
    sections_for_node: dict[str, Any],
) -> LearningNodeView:
    """Build a LearningNodeView from a raw node dict + extracted sections.

    Missing ``source_path``/``line_range`` are filled with deterministic
    placeholders (``"unknown"`` and ``(0, 0)``) — we never invent provenance,
    but the model contract requires both fields to be present.

    Sections are serialized via ``SectionView.model_dump()`` so the resulting
    NodeView remains JSON-safe.
    """
    nid = _node_id(node)
    serialised_sections: dict[str, Any] = {}
    for key, view in sections_for_node.items():
        if view is None:
            serialised_sections[key] = None
        elif hasattr(view, "model_dump"):
            serialised_sections[key] = view.model_dump()
        else:
            serialised_sections[key] = view

    return LearningNodeView(
        node_id=nid,
        source_path=str(node.get("source_path") or "unknown"),
        line_range=_coerce_line_range(node.get("line_range")),
        title=node.get("title"),
        domain=node.get("domain"),
        subdomain=node.get("subdomain"),
        status=node.get("status"),
        confidence=node.get("confidence"),
        source=node.get("source"),
        node_origin=node.get("node_origin"),
        tags=list(node.get("tags") or []),
        context_size=node.get("context_size"),
        reading_priority=node.get("reading_priority"),
        included_sections=serialised_sections,
        extracted=dict(node.get("extracted") or {}),
        provenance=dict(node.get("provenance") or {}),
    )


def _build_edge_view(edge: dict[str, Any]) -> LearningEdgeView:
    """Build a LearningEdgeView from a raw edge dict."""
    return LearningEdgeView(
        edge_id=str(edge.get("edge_id") or ""),
        source_path=str(edge.get("source_path") or "unknown"),
        line_range=_coerce_line_range(edge.get("line_range")),
        **{"from": str(edge.get("from") or ""), "to": str(edge.get("to") or "")},
        type=edge.get("type"),
        weight=edge.get("weight"),
        note=edge.get("note"),
        included_reason=edge.get("included_reason"),
    )


def _build_references(
    ordered_ids: list[str],
    sections_by_node: dict[str, dict[str, Any]],
) -> list[ReferenceView]:
    """Derive ReferenceView entries from each node's extracted References section.

    One entry per non-empty line of a node's ``References`` section, in reading
    order then document order; leading list markers are stripped and duplicate
    (node, citation) pairs collapsed. ``packet.body.references`` was previously
    hardcoded empty, so the lesson References section never populated even when
    nodes carried a References section.
    """
    references: list[ReferenceView] = []
    seen: set[tuple[str, str]] = set()
    for nid in ordered_ids:
        view = (sections_by_node.get(nid) or {}).get("References")
        content = getattr(view, "content", None)
        if not content:
            continue
        for raw_line in content.splitlines():
            citation = raw_line.strip().lstrip("-*+").strip()
            if not citation:
                continue
            key = (nid, citation)
            if key in seen:
                continue
            seen.add(key)
            references.append(ReferenceView(citation=citation, source_node_ids=[nid]))
    return references


def _split_pitfall_paragraphs(content: str) -> list[str]:
    """Split a Pitfalls section into individual pitfall entries.

    The vault template formats each pitfall as a blank-line-separated
    ``**Title:** explanation`` paragraph. Internal whitespace within a paragraph
    is collapsed to single spaces so each entry renders as one clean line.
    A section with no blank-line split yields a single entry.
    """
    paragraphs = re.split(r"\n\s*\n", content.strip())
    return [" ".join(p.split()) for p in paragraphs if p.strip()]


def _build_pitfalls(
    nodes_by_id: dict[str, dict[str, Any]],
    ordered_ids: list[str],
    sections_by_node: dict[str, dict[str, Any]],
) -> list[PitfallView]:
    """Roll up pitfalls into PitfallView entries from BOTH representations.

    AKMS authors pitfalls two ways: as dedicated ``kind == 'pitfall'`` nodes, or
    as a ``Pitfalls`` section inside a content node (the Nodes_Vault template's
    "Known Pitfalls"). Both are surfaced here so the unified
    ``packet.body.pitfalls`` channel — and every exporter that renders it — sees
    them. Section-based pitfalls are split on blank lines so each
    ``**Title:** ...`` paragraph becomes its own entry.
    """
    pitfalls: list[PitfallView] = []
    for nid in ordered_ids:
        node = nodes_by_id.get(nid, {})

        # (1) Dedicated pitfall node.
        if node.get("kind") == "pitfall":
            pitfalls.append(
                PitfallView(
                    pitfall_id=nid,
                    source_node_id=nid,
                    source_path=node.get("source_path"),
                    line_range=(
                        _coerce_line_range(node["line_range"])
                        if "line_range" in node
                        else None
                    ),
                    message=str(
                        node.get("title") or node.get("message") or f"Pitfall: {nid}"
                    ),
                    severity="warning",
                )
            )
            continue

        # (2) Pitfalls section inside a content node (the common vault shape).
        section = (sections_by_node.get(nid) or {}).get("Pitfalls")
        content = getattr(section, "content", None)
        if not content or not content.strip():
            continue
        line_range = getattr(section, "line_range", None)
        source_path = getattr(section, "source_path", None) or node.get("source_path")
        for idx, paragraph in enumerate(_split_pitfall_paragraphs(content)):
            pitfalls.append(
                PitfallView(
                    pitfall_id=f"{nid}::pitfall::{idx}",
                    source_node_id=nid,
                    source_path=source_path,
                    line_range=line_range,
                    message=paragraph,
                    severity="warning",
                )
            )
    return pitfalls


def _build_code_links(
    edges: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
    accumulator: WarningAccumulator,
) -> list[CodeLinkView]:
    """Walk ``implements`` edges and emit one CodeLinkView per edge.

    Thin wrapper over :func:`akms_learn._code_links.build_code_links` that
    routes ``code_mirror_missing_source_path`` warnings through the
    compiler's :class:`WarningAccumulator`. The mode-level caller
    (``implementation_first``) skips this callback and emits its own
    ``implementation_anchor_missing_source`` warning instead.
    """

    def _on_missing_mirror_source(mirror_node_id: str, edge_id: str) -> None:
        accumulator.append(
            emit_code_mirror_missing_source_path_warning(
                mirror_node_id=mirror_node_id, edge_id=edge_id
            )
        )

    return _shared_build_code_links(
        edges,
        nodes_by_id,
        on_missing_mirror_source=_on_missing_mirror_source,
    )


def _resolve_domain_pack_provenance(
    domain_pack_paths: list[str | Path] | None,
) -> tuple[list[dict[str, Any]] | None, DomainPackRegistry | None]:
    """Build a DomainPackRegistry from paths; return (provenance_list, registry).

    Returns ``(None, None)`` when ``domain_pack_paths`` is falsy. Missing
    files raise :class:`LearningCapabilityError` so callers see a clear
    diagnostic. Successfully-loaded descriptors are returned in
    deterministic (alphabetic-by-id) order.
    """
    if not domain_pack_paths:
        return None, None

    paths: list[Path] = []
    for p in domain_pack_paths:
        path = Path(p)
        # Allow a directory of fixtures (e.g. .../compmech_reference/) —
        # auto-resolve to its ``domain_pack.yaml`` sibling.
        if path.is_dir():
            candidate = path / "domain_pack.yaml"
            if not candidate.exists():
                raise LearningCapabilityError(
                    f"Domain-pack directory {path!s} contains no 'domain_pack.yaml'."
                )
            path = candidate
        if not path.exists():
            raise LearningCapabilityError(f"Domain-pack path does not exist: {path!s}")
        paths.append(path)

    registry = build_registry_from_paths(paths)
    descriptors = registry.ordered_descriptors()
    return [d.model_dump(mode="json") for d in descriptors], registry


def _resolve_source_pack_provenance(
    source_pack_paths: list[str | Path] | None,
) -> list[dict[str, Any]] | None:
    """Load SourcePackDescriptor YAMLs from paths.

    Returns ``None`` when ``source_pack_paths`` is falsy. Missing files raise
    :class:`LearningCapabilityError`.
    """
    if not source_pack_paths:
        return None

    descriptors: list[SourcePackDescriptor] = []
    for p in source_pack_paths:
        path = Path(p)
        if not path.exists():
            raise LearningCapabilityError(f"Source-pack path does not exist: {path!s}")
        descriptors.append(load_source_pack_from_yaml(path))

    descriptors.sort(key=lambda d: d.id)
    return [d.model_dump(mode="json") for d in descriptors]


def _check_required_capabilities(
    request: LearningRequest | Any,
    plugin: Plugin,
    domain_pack_paths: list[str | Path] | None,
    source_pack_paths: list[str | Path] | None,
) -> list[str]:
    """Verify any ``request.required_capabilities`` are present.

    The check is satisfied if a capability appears in ``plugin.capabilities()``
    OR if it is a domain-pack capability and ``domain_pack_paths`` /
    ``source_pack_paths`` were supplied. Unsatisfied required capabilities
    raise :class:`LearningCapabilityError`.

    Returns the (possibly empty) list of unavailable-but-not-required
    capabilities recorded on the request.
    """
    required: list[str] = list(_request_get(request, "required_capabilities", []) or [])
    if not required:
        return []

    available: set[str] = set(plugin.capabilities())
    if domain_pack_paths:
        available.update(("domain_pack_registry", "static_domain_pack_descriptors"))
    if source_pack_paths:
        available.add("source_pack_descriptors")

    unavailable = [cap for cap in required if cap not in available]
    if unavailable:
        raise LearningCapabilityError(
            f"Required capability/capabilities unavailable: {unavailable!r}"
        )
    return []


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compile_learning_source(
    request: LearningRequest | dict[str, Any],
    graph_path: str | Path | None = None,
    graph_slice: GraphSlice | dict[str, Any] | None = None,
    output_dir: str | Path | None = None,
    domain_pack_paths: list[str | Path] | None = None,
    source_pack_paths: list[str | Path] | None = None,
) -> CompileResult:
    """Run the 9-stage LSP compiler pipeline.

    Parameters
    ----------
    request:
        A :class:`LearningRequest` instance OR a raw dict that
        :func:`normalize_request` will canonicalise.
    graph_path:
        Filesystem path to a graph JSON. Mutually exclusive with
        ``graph_slice``.
    graph_slice:
        Either a :class:`GraphSlice` instance or a raw dict payload.
        Mutually exclusive with ``graph_path``.
    output_dir:
        If provided, the canonical packet JSON is written to
        ``<output_dir>/<request_hash>.json`` (Stage 9). Directory is created
        on demand.
    domain_pack_paths:
        Optional list of paths to ``domain_pack.yaml`` files (or directories
        containing one). Loaded into a :class:`DomainPackRegistry` whose
        descriptors are attached to the packet body.
    source_pack_paths:
        Optional list of paths to source-pack YAMLs whose descriptors are
        attached to the packet body.

    Returns
    -------
    CompileResult
        Wraps the validated packet, any export paths, warnings, and the
        stage execution log.

    Raises
    ------
    LearningCapabilityError
        If a required capability is unavailable, or a domain-pack /
        source-pack path is missing or invalid.
    PacketValidationError
        If the assembled packet violates a hard cross-field invariant.
    ValueError
        If neither / both of ``graph_path`` and ``graph_slice`` are given.
    """
    accumulator = WarningAccumulator()
    stage_log: list[str] = []

    # -----------------------------------------------------------------
    # Stage 1 — plugin and compatibility check
    # -----------------------------------------------------------------
    plugin = get_plugin()
    #   # ``LearningRequest`` carries no ``akms_schema`` field, so the check
    #       # defaults to "v2": existing requests pass cleanly while mis-typed
    #       # override values supplied via ad-hoc dicts are still rejected.
    requested_schema = str(_request_get(request, "akms_schema", "v2") or "v2")
    if requested_schema not in (
        plugin.supported_akms_schema_min,
        plugin.supported_akms_schema_max,
    ):
        raise LearningCapabilityError(
            f"Unsupported akms_schema {requested_schema!r}; plugin supports "
            f"{plugin.supported_akms_schema_min}..{plugin.supported_akms_schema_max}."
        )

    _check_required_capabilities(request, plugin, domain_pack_paths, source_pack_paths)
    stage_log.append("plugin_compat_check")

    # -----------------------------------------------------------------
    # Stage 2 — request normalization
    # -----------------------------------------------------------------
    normalized = normalize_request(request)
    req_hash = request_hash(normalized)
    stage_log.append("request_normalization")

    # -----------------------------------------------------------------
    # Stage 3 — graph source resolution
    # -----------------------------------------------------------------
    resolved_slice = _ensure_graph_slice(graph_path, graph_slice)
    graph_hash = compute_graph_hash(resolved_slice)
    stage_log.append("graph_source_resolution")

    # -----------------------------------------------------------------
    # Stage 4 — deterministic seed-tag handling
    # -----------------------------------------------------------------
    seed_tags = list(normalized.get("seed_tags") or [])
    filtered_slice = _filter_by_seed_tags(resolved_slice, seed_tags)
    stage_log.append("seed_tag_handling")

    # -----------------------------------------------------------------
    # Stage 5 — slice conversion (preserve provenance, no invention)
    # -----------------------------------------------------------------
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for node in filtered_slice.nodes:
        # Copy so any downstream stage cannot mutate the input dict.
        nodes_by_id[_node_id(node)] = dict(node)
    stage_log.append("slice_conversion")

    # -----------------------------------------------------------------
    # Stage 6 — learning ordering
    # -----------------------------------------------------------------
    # Dispatch through the mode-specific ordering-strategy registry rather than
    # calling order_nodes() directly. The strategy for ``generation_option`` is
    # looked up in :data:`STRATEGY_KEYS`; options without a registered strategy
    # (e.g. ``deterministic_outline``, ``anthology``, ``bundle``) fall back to
    # ``"default"``, which delegates to :func:`order_nodes` unchanged. Modes with
    # a real reordering strategy (``derivation_first``, ``implementation_first``)
    # now have that ordering reflected in the LSP ``reading_order`` — previously
    # the registry was defined but never reached from the compiler.
    gen_opt = (normalized.get("generation_option") or "").strip().lower()
    strategy_key = gen_opt if gen_opt in STRATEGY_KEYS else "default"
    if strategy_key == "multi_granularity":
        # The multi_granularity ordering strategy is request-less and therefore
        # cannot apply the granularity filter, so the LSP reading_order would
        # otherwise be identical across overview/standard/deep_dive variants.
        # Route through the full mode here: it reads request.granularity (and
        # the tag/id/domain conventions) and returns the variant's node subset
        # — overview drops ``fine``-marked nodes, deep_dive keeps all. granularity
        # is intentionally excluded from request_hash (see NORMALIZED_FIELDS), so
        # the variant changes rendered output without changing request identity.
        from akms_learn.modes.multi_granularity import multi_granularity_mode

        mg_result, ordering_warnings = multi_granularity_mode(
            filtered_slice, _as_learning_request(request)
        )
        ordered_ids = list(mg_result.ordered_nodes)
    else:
        ordered_ids, ordering_warnings = get_strategy(strategy_key)(filtered_slice)
    accumulator.extend(ordering_warnings)

    if strategy_key == "adaptive_path":
        # adaptive_path is capability-gated (requires the ``llm`` extra) and its
        # ordering strategy is request-less, so the learner-profile prerequisite
        # skip would otherwise never reach the LSP. When the capability is
        # available, route the default-ordered nodes through the mode so skipped
        # prerequisites are dropped from ``reading_order`` (the slice is never
        # mutated — skips are preserved in the mode's provenance). When the extra
        # is absent the mode is unavailable, so the default ordering is kept
        # unchanged — matching how the capability catalog and bundle generator
        # already treat adaptive_path as unavailable in a clean checkout. The
        # ``active_nodes`` set is intersected against ``ordered_ids`` so reading
        # order is preserved (the result's own list is sorted, not ordered).
        from akms_learn.capability_gates import build_capability_gate

        if build_capability_gate().adaptive_path:
            from akms_learn.modes.adaptive_path import adaptive_path_mode

            ap_result, ap_warnings = adaptive_path_mode(
                filtered_slice, ordered_ids, _as_learning_request(request)
            )
            active = set(ap_result.active_nodes)
            ordered_ids = [nid for nid in ordered_ids if nid in active]
            accumulator.extend(ap_warnings)
    stage_log.append("learning_ordering")

    # -----------------------------------------------------------------
    # Stage 7 — section extraction
    # -----------------------------------------------------------------
    sections_by_node: dict[str, dict[str, Any]] = {}
    for nid in ordered_ids:
        node = nodes_by_id.get(nid, {})
        markdown = node.get("markdown") or node.get("body")
        if not markdown:
            sections_by_node[nid] = {}
            continue
        sections, section_warnings = extract_sections(
            markdown,
            str(node.get("source_path") or "unknown"),
            node_id=nid,
        )
        sections_by_node[nid] = sections
        accumulator.extend(section_warnings)
    stage_log.append("section_extraction")

    # -----------------------------------------------------------------
    # Stage 7b — LLM expansion
    # -----------------------------------------------------------------
    # Strictly between section extraction (stage 7) and packet assembly
    # (stage 8). Runs ONLY when the request opts in; otherwise the step is
    # skipped entirely so the packet stays byte-identical to the deterministic
    # baseline. The mode is a pure function that freezes a deep copy of
    # the deterministic packet BEFORE any provider call and never mutates the
    # inputs, so the surrounding pipeline is unaffected when expansion is off.
    llm_generated_sections: list[GeneratedSection] = []
    llm_provenance: dict[str, Any] = {}
    expansion_request = _build_llm_expansion_request(request)
    if expansion_request is not None:
        # Lazy module import mirrors the multi_granularity / adaptive_path
        # pattern below and avoids an import cycle through ``akms_learn.modes``.
        # Referencing the function via the module (rather than a bound local)
        # keeps it patchable by tests that instrument the pipeline step.
        from akms_learn.modes import llm_expanded as _llm_expanded

        llm_result, llm_warnings = _llm_expanded.llm_expanded_mode(
            filtered_slice,
            ordered_ids,
            _as_learning_request(request),
            expansion_request=expansion_request,
        )
        # Surface mode warnings (e.g. llm_citation_outside_packet,
        # llm_provider_unavailable) without touching the deterministic body.
        accumulator.extend(llm_warnings)
        llm_generated_sections = list(llm_result.generated_sections)
        # Record provenance.llm whenever the expansion step ran — even when the
        # provider returned nothing or every section was rejected — so consumers
        # can see the expansion was attempted. The mode's frozen
        # pre_expansion_packet guarantees the deterministic body is unchanged
        # regardless. ``model/notebook`` is read off the attached sections (all
        # share one provider/model) and is ``None`` when no section survived.
        #
        # This is the AUTHORITATIVE block written onto the PacketBody. It shares
        # ``build_llm_provenance`` (the single canonical shape) with the mode's
        # own ``result.packet`` block so the two cannot drift. ``rejected_count``
        # is read from the mode's block (the mode knows the raw vs. valid count);
        # it defaults to 0 on the fallback paths that don't populate it.
        citation_count = sum(len(s.source_node_ids) for s in llm_generated_sections)
        model_id = llm_generated_sections[0].model if llm_generated_sections else None
        mode_llm_prov = (llm_result.packet.get("provenance") or {}).get("llm") or {}
        # Prefer the provider the mode actually dispatched to: when the request
        # left the provider at its default, the mode auto-selects one by env
        # precedence (nlm → akms → stub), so the mode's own provenance block is
        # the authoritative name. Fall back to the request's provider on paths
        # that don't populate it (e.g. unavailable-provider fallback).
        effective_provider = mode_llm_prov.get("provider") or expansion_request.provider
        llm_provenance = {
            "llm": build_llm_provenance(
                provider=effective_provider,
                model=model_id,
                policy=llm_result.policy,
                section_count=len(llm_generated_sections),
                citation_count=citation_count,
                rejected_count=int(mode_llm_prov.get("rejected_count", 0)),
            )
        }

    # -----------------------------------------------------------------
    # Stage 8 — packet assembly and validation
    # -----------------------------------------------------------------
    # Resolve domain-pack / source-pack provenance up-front so we know which
    # capabilities ended up unsatisfied.
    domain_pack_provenance, _registry = _resolve_domain_pack_provenance(
        domain_pack_paths
    )
    source_pack_provenance = _resolve_source_pack_provenance(source_pack_paths)

    node_views = [
        _build_node_view(nodes_by_id[nid], sections_by_node.get(nid, {}))
        for nid in ordered_ids
        if nid in nodes_by_id
    ]
    # Restrict edges to those whose BOTH endpoints survive in the reading order.
    # For every non-dropping mode all nodes are retained, so this is a no-op; for
    # the node-dropping modes (``multi_granularity`` overview/standard,
    # ``adaptive_path``) it removes edges that would otherwise dangle against a
    # dropped node and fail packet validation. Mirrors the edge filter in
    # :func:`_filter_by_seed_tags`.
    reading_order_ids = set(ordered_ids)
    effective_edges = tuple(
        e
        for e in filtered_slice.edges
        if e.get("from") in reading_order_ids and e.get("to") in reading_order_ids
    )
    edge_views = [_build_edge_view(e) for e in effective_edges]
    pitfall_views = _build_pitfalls(nodes_by_id, ordered_ids, sections_by_node)
    code_links = _build_code_links(effective_edges, nodes_by_id, accumulator)

    # References: derive from each node's extracted References section. Empty for
    # nodes/fixtures that carry no References section (deterministic-baseline safe).
    reference_views = _build_references(ordered_ids, sections_by_node)

    # Assessments: when the assessment_first strategy is selected and its
    # capability extra (``notebook``) is present, generate items and surface them
    # in the packet body. Mirrors the adaptive_path capability-gated dispatch
    # above. The mode reads node["extracted"]; nodes without it yield no items.
    assessment_views: list[AssessmentView] = []
    if strategy_key == "assessment_first":
        from akms_learn.capability_gates import build_capability_gate

        if build_capability_gate().assessment_first:
            from akms_learn.modes.assessment_first import assessment_first_mode

            assessment_result, assessment_warnings = assessment_first_mode(
                filtered_slice, ordered_ids, _as_learning_request(request)
            )
            accumulator.extend(assessment_warnings)
            assessment_views = [
                AssessmentView(**item.model_dump())
                for item in assessment_result.assessment_items
            ]

    body = PacketBody(
        nodes=node_views,
        edges=edge_views,
        pitfalls=pitfall_views,
        code_links=code_links,
        assessments=assessment_views,
        references=reference_views,
        reading_order=list(ordered_ids),
        sections=[],
        domain_pack_provenance=domain_pack_provenance,
        source_pack_provenance=source_pack_provenance,
        generated_sections=llm_generated_sections,
        provenance=llm_provenance,
    )

    compiler_info = CompilerInfo(
        name="akms-learn",
        version="1.0",
        plugin_api=plugin.plugin_api,
    )

    source_info = SourceInfo(
        graph_hash=graph_hash,
        graph_path=str(graph_path) if graph_path is not None else "<in-memory>",
        graph_version=str(filtered_slice.metadata.get("graph_version") or "") or None,
        query_hash=req_hash,
    )

    # ``granularity`` is read off the raw request — it is
    # intentionally excluded from ``normalize_request`` / ``request_hash`` so
    # two requests that differ only in granularity hash identically (see
    # :data:`akms_learn.requests.NORMALIZED_FIELDS`). It is surfaced on the
    # LSP request block so downstream consumers (e.g. the bundle manifest)
    # can read the selected variant without re-running the mode.
    raw_granularity = _request_get(request, "granularity", None)
    # ``rich_html`` — like granularity, read off the raw request and
    # excluded from request_hash; it only toggles the html exporter's rendering.
    raw_rich_html = bool(_request_get(request, "rich_html", False))
    request_info = LearningRequestInfo(
        topic=str(normalized.get("topic") or ""),
        goal=normalized.get("goal") or None,
        audience=normalized.get("audience"),
        depth=normalized.get("depth"),
        generation_option=normalized.get("generation_option"),
        seed_tags=tuple(normalized.get("seed_tags") or ()),
        max_nodes=normalized.get("max_nodes"),
        max_depth=normalized.get("max_depth"),
        include_pitfalls=normalized.get("include_pitfalls"),
        include_code_links=normalized.get("include_code_links"),
        exporters=tuple(normalized.get("exporters") or ()),
        request_hash=req_hash,
        granularity=raw_granularity
        if raw_granularity in ("overview", "standard", "deep_dive")
        else None,
        rich_html=raw_rich_html,
    )

    # Deterministic packet_id derived from request_hash + graph_hash.
    # Byte-stability across identical invocations is required, so no per-call
    # entropy (no uuid, no timestamp suffix) may appear in this identifier.
    packet_id = f"lsp-{req_hash[:16]}-{graph_hash[:8]}"

    packet = LearningSourcePacket(
        packet_id=packet_id,
        created_at=datetime.now(UTC).isoformat(),
        compiler=compiler_info,
        source=source_info,
        request=request_info,
        body=body,
        warnings=accumulator.finalize(),
    )

    # Hard validation + soft-warning accumulation.
    validation_warnings = validate_packet(packet)
    accumulator.extend(validation_warnings)
    # Re-build with the (possibly extended) warning list so consumers see them.
    if validation_warnings:
        packet = packet.model_copy(update={"warnings": accumulator.finalize()})

    #   # Round-trip sanity check — provenance must never be destroyed. We narrow
    #       # the exception type to pydantic's validation error because any other
    #       # failure here is a programming bug, not a packet-shape issue, and should
    #       # surface with its native traceback.
    try:
        LearningSourcePacket.model_validate(packet.model_dump(by_alias=True))
    except pydantic.ValidationError as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"LearningSourcePacket round-trip failed: {exc}") from exc

    stage_log.append("packet_assembly_and_validation")

    # -----------------------------------------------------------------
    # Stage 9 — export
    #
    # Ordering matters: we (1) probe declared exporters and accumulate any
    # ``exporter_unavailable`` warnings, (2) rebuild the final packet so its
    # ``warnings`` field includes the exporter warnings, and (3) only then
    # write the canonical JSON file to disk. Inverting this order causes the
    # persisted JSON to omit warnings that the in-memory packet later carries
    # (regression: ``test_compile_export_warnings_persisted``).
    # -----------------------------------------------------------------
    export_paths: list[Path] = []
    packet_path: Path | None = None

    # (1) Probe declared exporters. ``KNOWN_EXPORTERS`` is the single source
    # of truth for the names the compiler will attempt to dispatch (see
    # ``exporters/__init__.py``). Any name outside that set emits
    # ``exporter_unavailable`` without raising.
    requested_exporters: list[str] = list(normalized.get("exporters") or [])
    for exporter_name in requested_exporters:
        if exporter_name in KNOWN_EXPORTERS:
            module_name = f"akms_learn.exporters.{exporter_name}"
            try:
                mod = __import__(module_name, fromlist=["*"])
            except ImportError:  # pragma: no cover - stubs are importable
                accumulator.append(
                    LearningWarning(
                        severity="warning",
                        code="exporter_unavailable",
                        message=(
                            f"Exporter {exporter_name!r} module not available; skipped."
                        ),
                        source_ref=exporter_name,
                    )
                )
                continue
            # If the module exposes an ``export`` callable, invoke it now.
            if hasattr(mod, "export") and output_dir is not None:
                try:
                    produced = mod.export(packet, Path(output_dir))
                    export_paths.extend(produced)
                # One exporter's failure is isolated to a warning so it never
                # aborts the compile or the other exporters (broad by design).
                except Exception as exc:
                    accumulator.append(
                        LearningWarning(
                            severity="warning",
                            code="exporter_failed",
                            message=(
                                f"Exporter {exporter_name!r} raised an exception: {exc}"
                            ),
                            source_ref=exporter_name,
                        )
                    )
            elif not hasattr(mod, "export") and not hasattr(mod, "render"):
                accumulator.append(
                    LearningWarning(
                        severity="warning",
                        code="exporter_unavailable",
                        message=(
                            f"Exporter {exporter_name!r} is a Phase 1 stub; no artifact produced."
                        ),
                        source_ref=exporter_name,
                    )
                )
        else:
            accumulator.append(
                LearningWarning(
                    severity="warning",
                    code="exporter_unavailable",
                    message=(
                        f"Exporter {exporter_name!r} is not registered; no artifact produced."
                    ),
                    source_ref=exporter_name,
                )
            )

    # (2) Sync the final warning list into the packet BEFORE writing JSON.
    if accumulator.finalize() != list(packet.warnings):
        packet = packet.model_copy(update={"warnings": accumulator.finalize()})

    # (3) Write the canonical packet JSON to disk if an output directory was
    # supplied. The written file is now guaranteed to include every warning
    # the in-memory packet carries.
    if output_dir is not None:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        packet_path = out_dir / f"{req_hash}.json"
        payload = json.dumps(
            packet.model_dump(by_alias=True, mode="json"),
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        packet_path.write_text(payload, encoding="utf-8")
        export_paths.append(packet_path)
    stage_log.append("export")

    # Capabilities that the request signalled interest in but that the
    # current pipeline could not satisfy. There is no soft-capability
    # surface yet; we leave it as an explicit empty list for forward compat.
    unavailable_capabilities: list[str] = []

    return CompileResult(
        packet=packet,
        packet_path=packet_path,
        export_paths=export_paths,
        warnings=accumulator.finalize(),
        unavailable_capabilities=unavailable_capabilities,
        stage_log=stage_log,
    )
