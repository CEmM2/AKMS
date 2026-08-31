"""Pydantic v2 models for Learning Source Packets (LSP) and related artifacts.

These models are the canonical in-memory representation of an LSP as defined in
the akms-learn internal specification (not published) (frozen v0.1).

All 12 models are pure data containers; no business logic or I/O at import time.

Provenance is REQUIRED on view-type models (LearningNodeView, LearningEdgeView):
omitting ``source_path`` / ``line_range`` / ``node_id`` / ``edge_id`` will raise
``pydantic.ValidationError``.

``AssessmentView`` is a forward-compatibility stub (``extra="allow"``); it accepts
arbitrary keys and its schema is not enforced.

``PacketBody`` carries two optional forward-compat fields,
``domain_pack_provenance`` and ``source_pack_provenance``, so the domain-pack
layer can populate metadata without a schema bump.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from akms_learn.models.llm_expansion import GeneratedSection

__all__ = [
    "AssessmentView",
    "CodeLinkView",
    "CompilerInfo",
    "LearningEdgeView",
    "LearningNodeView",
    "LearningRequestInfo",
    "LearningSourcePacket",
    "LearningWarning",
    "PacketBody",
    "PitfallView",
    "ReferenceView",
    "SourceInfo",
]


# ---------------------------------------------------------------------------
# Warnings (declared first because other models reference list[LearningWarning])
# ---------------------------------------------------------------------------


class LearningWarning(BaseModel):
    """Soft validation issue emitted during LSP compilation.

    Severity follows the spec's tri-state: ``info`` / ``warning`` / ``error``.
    ``source_ref`` is an optional free-form reference to the offending input
    (e.g. node id, request field, descriptor path).
    """

    model_config = ConfigDict(frozen=True)

    severity: Literal["info", "warning", "error"]
    code: str
    message: str
    source_ref: str | None = None


# ---------------------------------------------------------------------------
# Top-level header blocks (spec §3, L33-L69)
# ---------------------------------------------------------------------------


class CompilerInfo(BaseModel):
    """Identifies the compiler that produced the packet (spec §3)."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    plugin_api: str | None = None


class SourceInfo(BaseModel):
    """Identifies the AKMS graph + query that produced this packet (spec §3).

    ``graph_hash`` and ``graph_path`` are the stable provenance anchors that
    let the review bundle reproduce the packet from the same graph.
    """

    model_config = ConfigDict(frozen=True)

    graph_hash: str
    graph_path: str
    graph_version: str | None = None
    query_hash: str | None = None
    repo_root: str | None = None
    global_vault: str | None = None


class LearningRequestInfo(BaseModel):
    """Normalized request snapshot + hash (spec §3, plan §10).

    Only the normalized 11 request fields contribute to ``request_hash``; UI
    state from Logic-Loom must NOT contribute (plan §10, L203). Hash stability
    is enforced upstream in ``request.normalize``.
    """

    model_config = ConfigDict(frozen=True)

    topic: str
    goal: str | None = None
    audience: str | None = None
    depth: str | None = None
    generation_option: str | None = None
    seed_tags: tuple[str, ...] = ()
    max_nodes: int | None = None
    max_depth: int | None = None
    include_pitfalls: bool | None = None
    include_code_links: bool | None = None
    exporters: tuple[str, ...] = ()
    request_hash: str
    # Selected granularity variant for the multi_granularity
    # mode. ``None`` is the canonical "not applicable / not specified" value.
    # Values: ``"overview"`` | ``"standard"`` | ``"deep_dive"``. Excluded from
    # ``request_hash`` upstream (see :data:`akms_learn.requests.NORMALIZED_FIELDS`).
    # This value never enters the AKMS v2 graph.
    granularity: Literal["overview", "standard", "deep_dive"] | None = None
    # Opt-in "rich" HTML export: when True the html exporter renders a
    # MathJax + rendered-algorithm page (drops the offline/self-contained
    # guarantee). Excluded from ``request_hash`` (not in NORMALIZED_FIELDS), like
    # ``granularity`` — it changes presentation only, not node selection.
    rich_html: bool = False


# ---------------------------------------------------------------------------
# View models (spec §4-§5, L71-L124) — all carry required provenance.
# ---------------------------------------------------------------------------


class LearningNodeView(BaseModel):
    """A node included in the packet (spec §4).

    Required provenance: ``node_id``, ``source_path``, ``line_range``.
    ``line_range`` is a ``(start, end)`` tuple of 1-indexed inclusive line
    numbers into ``source_path``.
    """

    model_config = ConfigDict()

    node_id: str
    source_path: str
    line_range: tuple[int, int]

    # Optional spec fields
    title: str | None = None
    domain: str | None = None
    subdomain: str | None = None
    status: str | None = None
    confidence: float | None = None
    source: str | None = None
    node_origin: str | None = None
    tags: list[str] = Field(default_factory=list)
    context_size: str | None = None
    reading_priority: str | None = None
    included_sections: dict[str, Any] = Field(default_factory=dict)
    extracted: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)


class LearningEdgeView(BaseModel):
    """An edge included in the packet (spec §5).

    Required provenance: ``edge_id``, ``source_path``, ``line_range``. The
    ``from``/``to`` semantic endpoints from the spec YAML are mapped via
    aliases so the dumped form matches the spec key names.
    """

    model_config = ConfigDict(populate_by_name=True)

    edge_id: str
    source_path: str
    line_range: tuple[int, int]

    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    type: str | None = None
    weight: float | None = None
    note: str | None = None
    included_reason: str | None = None


class PitfallView(BaseModel):
    """A pitfall surfaced into the packet (spec §4, extracted.pitfalls + §6)."""

    model_config = ConfigDict()

    pitfall_id: str | None = None
    source_node_id: str | None = None
    source_path: str | None = None
    line_range: tuple[int, int] | None = None
    message: str
    severity: Literal["info", "warning", "error"] | None = None


class CodeLinkView(BaseModel):
    """A code link (spec §7).

    This view-type carries optional fields that the
    implementation-first mode populates when walking ``implements``
    edges:

    * ``source_node_id`` — the learning/spec node from which the edge starts.
    * ``target`` — the code-mirror node id (preferred) or the source-file
      path of the implementation referenced by the edge.
    * ``relation`` — the edge type that produced this view. Defaults to
      ``"implements"`` since CodeLinkViews are only emitted from
      ``implements`` edges.
    * ``file_path`` — optional file path of the implementation.
    * ``line_range`` — optional ``(start, end)`` line range.

    The original fields (``node_id``, ``source_file``, ``symbols``,
    ``concept``, ``mirror_node_id``, ``explanation_mode``) are preserved.
    CodeLinkView is a view-type and may be extended; the v2 graph schema
    (node/edge models) remains frozen.
    """

    model_config = ConfigDict()

    node_id: str
    source_file: str
    symbols: list[str] = Field(default_factory=list)
    concept: str | None = None
    mirror_node_id: str | None = None
    explanation_mode: str | None = None

    # Optional extensions — no required-field churn.
    source_node_id: str | None = None
    target: str | None = None
    relation: str | None = "implements"
    file_path: str | None = None
    line_range: tuple[int, int] | None = None


class AssessmentView(BaseModel):
    """Forward-compatibility stub for assessment items (spec §8).

    Schema is NOT enforced; arbitrary keys are accepted. An empty
    ``assessments=[]`` is the typical value.
    """

    model_config = ConfigDict(extra="allow")


class ReferenceView(BaseModel):
    """A reference / further-reading entry (spec §9, references array)."""

    model_config = ConfigDict()

    reference_id: str | None = None
    title: str | None = None
    url: str | None = None
    citation: str | None = None
    source_node_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Body container + root packet
# ---------------------------------------------------------------------------


class PacketBody(BaseModel):
    """The body of the LSP — all the rendered view collections (spec §3).

    Optional forward-compat fields ``domain_pack_provenance`` and
    ``source_pack_provenance`` exist so the domain-pack layer can populate
    metadata without forcing a v2 schema bump (spec §12).
    """

    model_config = ConfigDict()

    nodes: list[LearningNodeView] = Field(default_factory=list)
    edges: list[LearningEdgeView] = Field(default_factory=list)
    pitfalls: list[PitfallView] = Field(default_factory=list)
    code_links: list[CodeLinkView] = Field(default_factory=list)
    assessments: list[AssessmentView] = Field(default_factory=list)
    references: list[ReferenceView] = Field(default_factory=list)
    reading_order: list[str] = Field(default_factory=list)
    sections: list[dict[str, Any]] = Field(default_factory=list)

    # Forward-compat slots populated by the domain-pack layer (spec §12).
    domain_pack_provenance: Any | None = None
    source_pack_provenance: Any | None = None

    # LLM-expanded surface. Populated only when LLM expansion
    # runs in the compiler step between section extraction (stage 7) and packet
    # assembly (stage 8); empty / absent otherwise so the deterministic baseline
    # stays byte-identical when expansion is disabled or unavailable.
    generated_sections: list[GeneratedSection] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class LearningSourcePacket(BaseModel):
    """Root of the LSP (spec §3, L33-L69).

    Holds top-level header fields, the request snapshot, the packet body, and
    a list of soft warnings accumulated during compilation.
    """

    model_config = ConfigDict()

    akms_learning_schema: str = "learn/v0.1"
    packet_id: str
    created_at: str
    compiler: CompilerInfo
    source: SourceInfo
    request: LearningRequestInfo
    body: PacketBody
    warnings: list[LearningWarning] = Field(default_factory=list)
    policy: dict[str, Any] = Field(default_factory=dict)
    validation: dict[str, Any] = Field(default_factory=dict)
