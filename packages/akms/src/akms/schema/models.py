"""Pydantic models for all AKMS v2 schemas.

Frozen specification — any change requires a version bump and migration script.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

# ══════════════════════════════════════════════════════════════════════
#                           ENUMS
# ══════════════════════════════════════════════════════════════════════


class NodeStatus(str, Enum):
    DRAFT = "draft"
    TENTATIVE = "tentative"
    ESTABLISHED = "established"
    DEPRECATED = "deprecated"


class EdgeType(str, Enum):
    REQUIRES = "requires"
    FEEDS_INTO = "feeds-into"
    REFINES = "refines"
    CONTRADICTS = "contradicts"
    PITFALL = "pitfall"
    IMPLEMENTS = "implements"


class NodeSource(str, Enum):
    HUMAN = "human"
    AGENT = "agent"
    HYBRID = "hybrid"
    GENERATED = "generated"


class ContextSize(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class ReadingPriority(str, Enum):
    FULL = "full"
    SUMMARY = "summary"
    PITFALLS_ONLY = "pitfalls-only"


class TaskStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    DEFERRED = "deferred"


class Coverage(str, Enum):
    SUFFICIENT = "sufficient"
    MISSING_DETAIL = "missing-detail"
    OUTDATED = "outdated"


class AgentRole(str, Enum):
    IMPLEMENTER = "implementer"
    CODE_REVIEWER = "code_reviewer"
    PHYSICS_REVIEWER = "physics_reviewer"


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SessionOutcome(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class ImpactOnNextPhase(str, Enum):
    NONE = "none"
    LOW = "low"
    BLOCKING = "blocking"


class LoadoutMode(str, Enum):
    ROUTING = "routing"
    FULL = "full"


class TitleMatch(str, Enum):
    WHOLE_WORD = "whole_word"
    SUBSTRING = "substring"


# Loadable statuses for query_subgraph filtering
LOADABLE_STATUSES = {NodeStatus.TENTATIVE, NodeStatus.ESTABLISHED}

# Experiential fields that must NOT appear in global node frontmatter
EXPERIENTIAL_FIELDS = frozenset(
    {
        "activations",
        "last_activated",
        "activated_by_tasks",
        "session_refs",
        "auto_update",
    }
)


# ══════════════════════════════════════════════════════════════════════
#                     GLOBAL NODE FRONTMATTER
# ══════════════════════════════════════════════════════════════════════


class StructuralEdge(BaseModel):
    """An edge in the knowledge graph (from node frontmatter)."""

    to: str
    type: EdgeType
    weight: float = Field(ge=0.0, le=1.0)
    note: str = ""


class GlobalNodeFrontmatter(BaseModel):
    """Schema for global knowledge node YAML frontmatter (§1 of spec)."""

    # Identity
    id: str
    title: str
    domain: str
    subdomain: str | None = None
    tags: list[str] = Field(min_length=1)

    # Graph status
    status: NodeStatus
    confidence: float = Field(ge=0.0, le=1.0)
    source: NodeSource
    confidence_floor: float | None = Field(default=None, ge=0.0, le=1.0)

    # Structural edges
    edges: list[StructuralEdge] = Field(default_factory=list)

    # Loadout hints
    load_with: list[str] = Field(default_factory=list)
    context_size: ContextSize | None = None
    reading_priority: ReadingPriority | None = None
    content_ref: str | None = None

    # Schema version
    akms_schema: str = "v2"

    model_config = {"extra": "forbid"}


class LocalNodeFrontmatter(GlobalNodeFrontmatter):
    """Schema for local knowledge node frontmatter (§1a of spec).

    Same as global but with additional constraints:
    - source must be 'agent' or 'human' (not 'generated')
    - status must be 'tentative' when source is 'agent'
    """

    @field_validator("source")
    @classmethod
    def source_must_not_be_generated(cls, v: NodeSource) -> NodeSource:
        if v == NodeSource.GENERATED:
            raise ValueError(
                "Local nodes cannot have source 'generated' (reserved for code-mirror)"
            )
        return v

    @model_validator(mode="after")
    def enforce_agent_status_tentative(self) -> LocalNodeFrontmatter:
        if self.source == NodeSource.AGENT and self.status != NodeStatus.TENTATIVE:
            raise ValueError("Local nodes with source 'agent' must have status 'tentative'")
        return self


# ══════════════════════════════════════════════════════════════════════
#                   CODE MIRROR NODE FRONTMATTER
# ══════════════════════════════════════════════════════════════════════


class CodeMirrorNodeFrontmatter(BaseModel):
    """Schema for code-mirror node frontmatter (§6 of spec).

    Existence markers only — no tags, no edges, confidence always 1.0.
    """

    id: str
    title: str
    domain: str = "code-mirror"
    status: NodeStatus = NodeStatus.ESTABLISHED
    confidence: float = 1.0
    source: NodeSource = NodeSource.GENERATED
    auto_update: bool = True
    content_ref: str
    source_file: str
    generated_at: datetime
    generated_by_phase: int
    akms_schema: str = "v2"

    model_config = {"extra": "forbid"}


# ══════════════════════════════════════════════════════════════════════
#                    LOCAL STATE OVERLAY
# ══════════════════════════════════════════════════════════════════════


class NodeStateOverride(BaseModel):
    """Per-node experiential state in local_state.yaml."""

    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    activations: int = 0
    last_activated: date | None = None
    activated_by_tasks: list[str] = Field(default_factory=list)
    session_refs: list[str] = Field(default_factory=list)


class LocalEdge(BaseModel):
    """A repo-local edge (typically pitfall edges)."""

    # Using Field(alias=...) to handle the 'from' reserved keyword
    from_node: str = Field(alias="from")
    to: str
    type: EdgeType
    weight: float = Field(ge=0.0, le=1.0)
    note: str = ""
    # Optional session attribution used by the replay ledger (F-03) to
    # dedup pitfall edges that originate from the same session across
    # subsequent `update_graph` runs. Absent on pre-F-03 overlays —
    # default "" keeps the field non-breaking on v2.
    source_id: str = ""

    model_config = {"populate_by_name": True}


class SessionNodeEntry(BaseModel):
    """A session node registered in local_state.yaml."""

    title: str
    tags: list[str] = Field(default_factory=list)
    outcome: SessionOutcome
    content_ref: str
    phase: int


class LocalStateOverlay(BaseModel):
    """Schema for local_state.yaml (§2 of spec)."""

    akms_schema: str = "v2"
    repo_id: str = ""

    nodes: dict[str, NodeStateOverride] = Field(default_factory=dict)
    local_edges: list[LocalEdge] = Field(default_factory=list)
    session_nodes: dict[str, SessionNodeEntry] = Field(default_factory=dict)
    suppressed_edges: list[Any] = Field(default_factory=list)

    # Replay ledger — list of source_ids already processed by
    # update_graph. Additive-optional field; schema stays at v2. Same-source
    # replays short-circuit to a no-op once the id is present here (NFR-D03).
    processed_sources: list[str] = Field(default_factory=list)

    @field_validator("suppressed_edges")
    @classmethod
    def suppressed_must_be_empty(cls, v: list) -> list:
        if v:
            raise ValueError("suppressed_edges must be empty list in v2 (reserved)")
        return v


# ══════════════════════════════════════════════════════════════════════
#                       AGENT MEMORY
# ══════════════════════════════════════════════════════════════════════


class NodeUsedFeedback(BaseModel):
    """Feedback on a node used during a task."""

    id: str
    useful: bool
    coverage: Coverage
    note: str = ""


class NodeMissingEntry(BaseModel):
    """A node that was needed but didn't exist."""

    description: str
    suggested_id: str
    domain: str
    tags: list[str] = Field(default_factory=list)
    priority: Priority


class LessonFailed(BaseModel):
    """A failed approach with explanation."""

    what: str
    why: str
    fix: str


class Lessons(BaseModel):
    """Lessons learned from a task."""

    worked: list[str] = Field(default_factory=list)
    failed: list[LessonFailed] = Field(default_factory=list)


class PitfallDiscovered(BaseModel):
    """A pitfall discovered during task execution."""

    node_ref: str | None = None
    description: str
    severity: Severity
    suggested_id: str | None = None


class NewKnowledge(BaseModel):
    """New knowledge proposed by an agent."""

    suggested_id: str
    title: str = ""
    domain: str = ""
    tags: list[str] = Field(default_factory=list)
    content_draft: str
    status: str = "tentative"
    source: str = "agent"


class AgentMemory(BaseModel):
    """Schema for per-task AgentMemory (§3 of spec)."""

    task_id: str
    task_description: str = ""
    phase_id: int
    timestamp: datetime
    agent_model: str
    loadout_used: str

    # Outcome
    status: TaskStatus
    commit: str | None = None
    tests_passed: int
    tests_total: int
    completion_notes: str = ""

    # Node feedback (persistent zone)
    nodes_used: list[NodeUsedFeedback] = Field(default_factory=list)
    nodes_missing: list[NodeMissingEntry] = Field(default_factory=list)

    # Lessons (persistent zone)
    lessons: Lessons = Field(default_factory=Lessons)

    # Pitfalls (persistent zone)
    pitfalls_discovered: list[PitfallDiscovered] = Field(default_factory=list)

    # New knowledge (persistent zone)
    new_knowledge: list[NewKnowledge] = Field(default_factory=list)

    # Schema version
    akms_schema: str = "v2"




class ReviewBreakdown(BaseModel):
    """Review severity breakdown."""

    minor: int = 0
    medium: int = 0
    high: int = 0
    critical: int = 0


class PCDTaskSummary(BaseModel):
    """Per-task summary within a PCD."""

    task_id: str
    title: str
    commit: str | None = None
    tests_passed: int
    tests_total: int
    status: TaskStatus
    agent_model: str
    review_score: int = 0
    review_breakdown: ReviewBreakdown | None = None


class OverallTestStatus(BaseModel):
    """Aggregate test status for a phase."""

    dedicated_passing: int
    dedicated_total: int
    dedicated_skipped: int = 0
    previously_failing_fixed: int = 0


class FileCreated(BaseModel):
    path: str
    description: str


class FileModified(BaseModel):
    path: str
    changes: str


class FileDeleted(BaseModel):
    path: str
    reason: str


class InterfaceAdded(BaseModel):
    name: str
    description: str


class TaichiFieldAdded(BaseModel):
    name: str
    spec: str = ""
    purpose: str = ""


class Assumption(BaseModel):
    claim: str
    where: str
    rationale: str
    risk_if_wrong: str


class FailingTest(BaseModel):
    tests: str
    reason: str
    impact_on_next_phase: ImpactOnNextPhase = ImpactOnNextPhase.NONE


class KnownIssues(BaseModel):
    failing_tests: list[FailingTest] = Field(default_factory=list)
    bugs: list[str] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)


class PCD(BaseModel):
    """Schema for Phase Completion Document (§3a of spec).

    Split into ephemeral zone (for orchestrator + next agent) and
    persistent zone (for AKMS graph updates).
    """

    phase_id: int
    plan_file: str
    branch: str
    date: date
    loadout_used: str

    # Ephemeral zone — completion
    tasks: list[PCDTaskSummary] = Field(default_factory=list)
    overall_test_status: OverallTestStatus | None = None

    # Ephemeral zone — architecture state
    files_created: list[FileCreated] = Field(default_factory=list)
    files_modified: list[FileModified] = Field(default_factory=list)
    files_deleted: list[FileDeleted] = Field(default_factory=list)
    interfaces_added: list[InterfaceAdded] = Field(default_factory=list)
    taichi_fields_added: list[TaichiFieldAdded] = Field(default_factory=list)

    # Ephemeral zone — risk & forward briefing
    assumptions: list[Assumption] = Field(default_factory=list)
    known_issues: KnownIssues = Field(default_factory=KnownIssues)
    next_phase_warnings: list[str] = Field(min_length=1)
    recommended_start: str | None = None

    # Persistent zone — AKMS graph feedback
    nodes_used: list[NodeUsedFeedback] = Field(default_factory=list)
    nodes_missing: list[NodeMissingEntry] = Field(default_factory=list)
    lessons: Lessons = Field(default_factory=Lessons)
    pitfalls_discovered: list[PitfallDiscovered] = Field(default_factory=list)
    new_knowledge: list[NewKnowledge] = Field(default_factory=list)

    # Schema version
    akms_schema: str = "v2"

    def extract_persistent_zone(self) -> dict:
        """Extract the persistent zone fields for update_graph.py consumption."""
        return {
            "nodes_used": [n.model_dump() for n in self.nodes_used],
            "nodes_missing": [n.model_dump() for n in self.nodes_missing],
            "lessons": self.lessons.model_dump(),
            "pitfalls_discovered": [p.model_dump() for p in self.pitfalls_discovered],
            "new_knowledge": [k.model_dump() for k in self.new_knowledge],
        }

    def extract_ephemeral_zone(self) -> dict:
        """Extract the ephemeral zone fields for next-phase agent consumption."""
        return {
            "tasks": [t.model_dump() for t in self.tasks],
            "overall_test_status": (
                self.overall_test_status.model_dump() if self.overall_test_status else None
            ),
            "files_created": [f.model_dump() for f in self.files_created],
            "files_modified": [f.model_dump() for f in self.files_modified],
            "files_deleted": [f.model_dump() for f in self.files_deleted],
            "interfaces_added": [i.model_dump() for i in self.interfaces_added],
            "assumptions": [a.model_dump() for a in self.assumptions],
            "known_issues": self.known_issues.model_dump(),
            "next_phase_warnings": self.next_phase_warnings,
            "recommended_start": self.recommended_start,
        }




class TaskJSONAKMS(BaseModel):
    """AKMS-specific fields added to task JSON (§4 of spec)."""

    akms_tags: list[str] = Field(default_factory=list)
    loadout_path: str | None = None
    akms_schema: str = "v2"


# ══════════════════════════════════════════════════════════════════════
#                      LOADOUT HEADER
# ══════════════════════════════════════════════════════════════════════


class LoadoutHeader(BaseModel):
    """Schema for loadout file YAML frontmatter (§5 of spec)."""

    task_id: str
    phase: int
    generated_at: datetime
    graph_version: str
    seed_tags: list[str]
    agent_role: AgentRole
    node_count: int
    loadout_mode: LoadoutMode
    available_context: int = 0
    qmd_available: bool = True
    akms_schema: str = "v2"


# ══════════════════════════════════════════════════════════════════════
#                    PROPAGATION CONFIG
# ══════════════════════════════════════════════════════════════════════


class ConfidenceConfig(BaseModel):
    local_decay: float = 0.85
    propagation_factor: float = 0.30
    activation_boost: float = 0.02
    min_confidence: float = 0.10
    max_confidence: float = 0.99
    hop_limit: int = 1


class LoadoutModeSelection(BaseModel):
    budget_fraction: float = 0.15
    low_threshold: int = 8000
    safety_margin: int = 4000
    default_mode: LoadoutMode = LoadoutMode.ROUTING


class ContextSizeTokens(BaseModel):
    small: int = 500
    medium: int = 1500
    large: int = 3000


class LoadoutConfig(BaseModel):
    max_nodes_per_loadout: int = 8
    max_pitfall_nodes: int = 4
    min_confidence_threshold: float = 0.30
    max_loadout_tokens: int = 12000
    context_size_tokens: ContextSizeTokens = Field(default_factory=ContextSizeTokens)
    routing_tokens_per_node: int = 200
    mode_selection: LoadoutModeSelection = Field(default_factory=LoadoutModeSelection)


class GraphConfig(BaseModel):
    stale_node_days: int = 90
    orphan_warning: bool = True
    max_session_refs: int = 10
    dedup_threshold: float = 0.75


class QueryRoleProfile(BaseModel):
    edge_types: list[str] = Field(default_factory=list)
    rank_formula: str = "confidence * activations"
    prefer_domains: list[str] = Field(default_factory=list)
    exclude_domains: list[str] = Field(default_factory=list)


class TagDerivationConfig(BaseModel):
    min_tag_length: int = 2
    title_match: TitleMatch = TitleMatch.WHOLE_WORD
    log_derived_tags: bool = True


class OrchestratorConfig(BaseModel):
    plan_name: str = ""
    base_branch: str = "main"
    default_model: str = "claude-sonnet-4-6"


class ModelRoutingEntry(BaseModel):
    """Provider + model pair for a single LLM call type."""

    provider: str = "anthropic"
    model: str = "claude-haiku-4-5-20251001"


class ModelRoutingConfig(BaseModel):
    """Routing config for AKMS internal LLM calls (dedup, drift).

    NOT for subagent model selection — subagents use agent_configs.py.
    """

    dedup_similarity: ModelRoutingEntry = Field(default_factory=ModelRoutingEntry)
    docstring_drift: ModelRoutingEntry = Field(default_factory=ModelRoutingEntry)
    # Routing key for the `akms` completion provider's
    # LSP-section expansion calls, so operators can route llm_expanded to a
    # different provider/model than the internal dedup/drift checks.
    lsp_expansion: ModelRoutingEntry = Field(default_factory=ModelRoutingEntry)


class MirrorConfig(BaseModel):
    """Optional code-mirror provider configuration (A2-4).

    Additive on :class:`PropagationConfig`. Defaults preserve the legacy
    in-process Python AST generator. External providers (repo2md) are
    selected by name; fallback to legacy is never silent.
    """

    # Provider registry name: "legacy" (default) or "repo2md".
    provider: str = "legacy"
    # Argv prefix for external providers (never shell-interpolated).
    command: list[str] = Field(default_factory=lambda: ["repo-wiki"])
    timeout_seconds: float = 120.0
    # When True, a failed non-legacy provider falls back to legacy and records
    # the fallback in result metadata. When False (default), failure raises.
    fallback_on_error: bool = False
    # When True, orchestrator blocks graph rebuild on provider failure.
    require_success: bool = False
    # Timestamp policy: now | source_date_epoch | request
    generated_at_source: str = "now"
    # Selection: changed (git-base parent) | full | paths
    selection_mode: str = "changed"
    prune: bool = False
    force_lock: bool = False
    expected_export_schema_version: int = 1
    expected_akms_schema_version: str = "v2"


class PropagationConfig(BaseModel):
    """Schema for propagation_config.yaml (§7 of spec)."""

    akms_schema: str = "v2"
    global_vault: str = "~/.claude/akms/nodes"

    confidence: ConfidenceConfig = Field(default_factory=ConfidenceConfig)
    edge_type_propagation: dict[str, float] = Field(
        default_factory=lambda: {
            "requires": 1.0,
            "refines": 0.7,
            "feeds-into": 0.5,
            "contradicts": 0.0,
            "pitfall": 0.0,
            "implements": 0.0,
        }
    )
    loadout: LoadoutConfig = Field(default_factory=LoadoutConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    query_roles: dict[str, QueryRoleProfile] = Field(
        default_factory=lambda: {
            "implementer": QueryRoleProfile(
                edge_types=["requires", "feeds-into", "pitfall"],
                rank_formula="confidence * activations",
            ),
            "code_reviewer": QueryRoleProfile(
                edge_types=["requires", "feeds-into", "pitfall"],
                rank_formula="confidence * activations",
            ),
            "physics_reviewer": QueryRoleProfile(
                edge_types=["requires", "contradicts"],
                rank_formula="confidence",
                prefer_domains=["computational-mechanics", "fft-galerkin"],
                exclude_domains=["code-mirror", "project-meta"],
            ),
        }
    )
    tag_derivation: TagDerivationConfig = Field(default_factory=TagDerivationConfig)
    orchestrator: OrchestratorConfig = Field(default_factory=OrchestratorConfig)
    model_routing: ModelRoutingConfig = Field(default_factory=ModelRoutingConfig)
    # A2-4: optional mirror provider block (defaults keep legacy behavior).
    mirror: MirrorConfig = Field(default_factory=MirrorConfig)
