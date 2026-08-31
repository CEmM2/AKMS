"""orchestrator.py — AKMS Lead Orchestrator (§3 of system design).

The top-level controller that manages the full development lifecycle as a
7-stage state machine. The orchestrator itself is a Python program (not an LLM
agent) that dispatches agents via the AKMSAgent class and manages checkpoints.
All graph operations are deterministic Python functions.

**Stage pipeline:**
  INIT → PLAN → TASK_BREAKDOWN → SCAFFOLD → EXECUTE → REVIEW → FINALIZE

**Key responsibilities:**
  - Compile the knowledge graph at init
  - Generate loadouts per task (with tag derivation fallback)
  - Dispatch agents via AKMSAgent (or subclass) with task + loadout
  - Collect AgentMemories / PCDs
  - Update graph (confidence mutations, pitfalls, session nodes)
  - Present checkpoints for developer review
  - Drive post-phase AKMS graph/mirror/report cycle

**Agent dispatch:**
  The orchestrator accepts ``agent_cls: type[AKMSAgent]`` (default:
  ``AKMSAgent``). A fresh agent instance is constructed per task via
  ``agent_cls(config, model=model, repo_root=repo_root)``. The agent's
  ``run(task_json)`` method handles the full AKMS protocol lifecycle.
  When ``agent_cls`` is None, the orchestrator operates in graph-only
  mode for testing.

**Architecture:**
  The module exposes a single code path:
  1. ``run_pipeline()`` — async primary entry point (handler-based)
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from akms.graph.build_graph import build_graph, load_graph
from akms.graph.generate_loadout import generate_loadout, select_loadout_mode
from akms.graph.generate_mirror import generate_mirror
from akms.graph.graph_status import format_report, graph_status
from akms.graph.mirror_provider import (
    MirrorProviderError,
    public_provider_identity,
    resolve_mirror_config,
)
from akms.graph.qmd_cache import compute_graph_version
from akms.graph.query_subgraph import query_subgraph
from akms.graph.tag_derivation import derive_review_seeds, fill_task_tags
from akms.graph.update_graph import update_graph
from akms.orchestrator.agent_configs import get_special_agent_config
from akms.orchestrator.branch_workflow import (
    execute_git_ops,
    parent_branch,
    phase_branch_name,
    reverse_merge_plan,
)
from akms.orchestrator.checkpoint import (
    CheckpointHandler,
    FileCheckpointHandler,
)
from akms.orchestrator.stages import (
    STAGE_ORDER,
    CheckpointAction,
    PipelineState,
    Stage,
)
from akms.telemetry import traced
from akms.agents.base import AgentPreflightError, AKMSAgent
from akms.orchestrator.wave_dispatch import (
    dispatch_phase,
)
from akms.schema.models import AgentMemory, AgentRole, PropagationConfig
from akms.schema.validators import parse_propagation_config

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  PipelineContext
# ═══════════════════════════════════════════════════════════════════════


class StageFailedError(RuntimeError):
    """A pipeline stage's agent run failed.

    Raised by stage handlers whose agent produced no usable result, so the
    failure takes the pipeline's failure path (state saved, error propagated,
    resumable with ``--resume``) instead of being gated as if the stage had
    succeeded. Partial task failures in the EXECUTE stage are not raised here
    — the REVIEW stage exists to adjudicate those.
    """

    def __init__(self, stage: str, detail: str):
        super().__init__(f"{stage} stage failed: {detail}")
        self.stage = stage
        self.detail = detail


@dataclass
class PipelineContext:
    """Immutable context passed to all stage handlers.

    Separates handler dependencies from PipelineState (which is mutable
    and persisted). Handlers need repo_root, config, and agent_cls but
    those should not be serialized into pipeline_state.json.
    """

    repo_root: Path
    global_vault: str | Path | None
    config: PropagationConfig
    agent_cls: type[AKMSAgent] | None
    model: str | None
    spec_path: str = ""


# ═══════════════════════════════════════════════════════════════════════
#  Handler Return Type
# ═══════════════════════════════════════════════════════════════════════

HandlerResult = tuple[str, str, list[str]]


def normalize_task_envelope(task: dict[str, Any]) -> dict[str, Any]:
    """Ensure AKMS envelope keys are present with normalized shapes.

    Module-level function used by handlers and the Orchestrator wrapper.
    Mutates ``task`` in-place and returns it for chaining convenience.
    """
    if not task.get("akms_schema"):
        task["akms_schema"] = "v2"

    raw_tags = task.get("akms_tags")
    if raw_tags is None:
        task["akms_tags"] = []
    elif isinstance(raw_tags, str):
        task["akms_tags"] = [raw_tags] if raw_tags else []
    elif isinstance(raw_tags, (list, tuple, set)):
        task["akms_tags"] = [str(tag) for tag in raw_tags if str(tag)]
    else:
        task["akms_tags"] = []

    if "loadout_path" not in task or task.get("loadout_path") is None:
        task["loadout_path"] = ""
    else:
        task["loadout_path"] = str(task.get("loadout_path"))

    return task


def _extract_tasks_from_memory(memory_path: Path) -> list[dict]:
    """Read an AgentMemory frontmatter file and extract a task list.

    Looks for a ``tasks`` key in the YAML frontmatter metadata.
    Returns an empty list if the file is missing, unparseable, or
    contains no ``tasks`` array.
    """
    try:
        import frontmatter

        post = frontmatter.load(str(memory_path))
        tasks = post.metadata.get("tasks")
        if isinstance(tasks, list):
            return [t for t in tasks if isinstance(t, dict)]
    except Exception:
        logger.exception("Failed to extract tasks from %s", memory_path)
    return []


@dataclass(frozen=True)
class _GitDiffResult:
    """Phase-local changed paths together with collection status.

    ``paths=()`` and ``error=None`` is a successful empty diff.  That is
    materially different from an unavailable diff, for which ``error`` is set.
    """

    paths: tuple[str, ...]
    error: str | None = None


def _git_files_modified(repo_root: Path, parent_branch: str) -> _GitDiffResult:
    """Collect paths changed on the current branch vs ``parent_branch``.

    Used by ``handle_review`` to seed reviewer context from the actual
    phase-local diff (F-01e).  A successful empty diff remains valid for the
    documented task-scope fallback; collection failures retain their diagnostic
    so adopted exact-route repositories can fail closed.
    """
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "diff", f"{parent_branch}...HEAD", "--name-only"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except Exception as exc:
        detail = f"git diff {parent_branch}...HEAD failed: {type(exc).__name__}: {exc}"
        logger.warning(
            "%s",
            detail,
            exc_info=True,
        )
        return _GitDiffResult(paths=(), error=detail)
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        detail = (
            f"git diff {parent_branch}...HEAD failed with exit status {proc.returncode}"
        )
        if stderr:
            detail = f"{detail}: {stderr}"
        logger.warning("%s", detail)
        return _GitDiffResult(paths=(), error=detail)
    return _GitDiffResult(
        paths=tuple(
            line.strip() for line in (proc.stdout or "").splitlines() if line.strip()
        )
    )


# Conventional locations for the optional task route index used by exact
# required-knowledge resolution. Absence is normal for repos that have not
# adopted failure-memory routes yet — review falls back to tag-based loadouts.
_TASK_ROUTE_INDEX_CANDIDATES = (
    "knowledge/task-routes.yaml",
    "knowledge/task-routes.yml",
    "knowledge/task-routes.json",
    "knowledge/graph/task-routes.yaml",
    "knowledge/graph/task-routes.yml",
    "knowledge/graph/task-routes.json",
    "knowledge/routes/task-routes.yaml",
    "knowledge/routes/task-routes.json",
    "knowledge/failure-routes.yaml",
    "knowledge/failure-routes.json",
)


def _find_task_route_index(repo_root: Path) -> Path | None:
    """Return the first existing task route index under conventional paths."""
    for relative in _TASK_ROUTE_INDEX_CANDIDATES:
        candidate = repo_root / relative
        if candidate.is_file():
            return candidate
    return None


def _phase_tasks(state: PipelineState, phase: int) -> list[dict[str, Any]]:
    """Return task dicts belonging to ``phase`` (empty when none recorded)."""
    return [
        task
        for task in (state.tasks or [])
        if isinstance(task, dict) and int(task.get("phase", 1) or 1) == phase
    ]


def _build_phase_review_task(
    *,
    phase: int,
    task_id: str,
    title: str,
    phase_tasks: list[dict[str, Any]],
    fallback_tags: list[str],
) -> dict[str, Any]:
    """Synthesize a retrieval task from phase task declarations.

    Scope/deliverables/symbols are the sorted union of per-task values so
    pre-task required resolution reflects the declared phase surface. The
    actual git diff is supplied separately as ``changed_paths``.
    """
    scopes: set[str] = set()
    deliverables: set[str] = set()
    symbols: set[str] = set()
    steps: list[str] = []
    for task in phase_tasks:
        for raw in task.get("scope") or []:
            text = str(raw).strip()
            if text:
                scopes.add(text)
        for raw in task.get("deliverables") or []:
            text = str(raw).strip()
            if text:
                deliverables.add(text)
        for raw in task.get("symbols") or []:
            text = str(raw).strip()
            if text:
                symbols.add(text)
        for raw in task.get("implementation_steps") or []:
            text = str(raw).strip()
            if text:
                steps.append(text)
    return {
        "task_id": task_id,
        "phase": phase,
        "title": title,
        "objective": f"Review phase {phase} implementation changes.",
        "scope": sorted(scopes),
        "deliverables": sorted(deliverables),
        "symbols": sorted(symbols),
        "implementation_steps": steps,
        "akms_tags": list(fallback_tags),
        "akms_schema": "v2",
    }


def _try_required_reviewer_loadout(
    *,
    repo_root: Path,
    route_index: Path,
    task: Mapping[str, Any],
    agent_role: str,
    changed_paths: Sequence[str],
    phase: int,
    loadout_path: Path,
    manifest_path: Path,
    graph_path: Path | None,
    config: PropagationConfig,
    mode: str,
    available_context: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Attempt exact post-diff reviewer resolution.

    Returns ``(meta, error_message)``. On success ``meta`` carries loadout path,
    fingerprint, counts, and ``post_diff_only_required``. On failure ``meta`` is
    None and ``error_message`` is for the caller to fail closed when it has
    adopted a task route index.
    """
    from akms.task_context.review import resolve_reviewer_context

    # ``changed_paths`` must be a sequence (not a bare str). Empty is valid and
    # triggers empty-diff fallback inside resolve_reviewer_context.
    result = resolve_reviewer_context(
        repo_root=repo_root,
        task=task,
        route_index=route_index,
        agent_role=agent_role,
        changed_paths=list(changed_paths),
        graph_path=graph_path,
        loadout_path=loadout_path,
        manifest_path=manifest_path,
        mode=mode,
        available_context=available_context,
        phase=phase,
        config=config,
        write_artifacts=True,
    )
    if result.status != "ok":
        detail = result.error or result.error_code or "unknown error"
        logger.warning(
            "Required reviewer resolution failed for role=%s: %s",
            agent_role,
            detail,
        )
        return None, detail

    post_only = list(result.post_diff_only_required)
    if post_only:
        logger.info(
            "Reviewer role=%s post_diff_only_required=%s (empty_diff_fallback=%s)",
            agent_role,
            post_only,
            result.empty_diff_fallback,
        )
    else:
        logger.info(
            "Reviewer role=%s required resolution ok fingerprint=%s "
            "empty_diff_fallback=%s required=%s",
            agent_role,
            result.fingerprint,
            result.empty_diff_fallback,
            list(result.post_diff_required),
        )

    meta = {
        "loadout_path": result.loadout_path or str(loadout_path),
        "manifest_path": result.manifest_path or str(manifest_path),
        "fingerprint": result.fingerprint,
        "empty_diff_fallback": result.empty_diff_fallback,
        "pre_task_required": list(result.pre_task_required),
        "post_diff_required": list(result.post_diff_required),
        "post_diff_only_required": post_only,
        "required_count": len(result.post_diff_required),
        "coactivated_count": result.coactivated_count,
        "advisory_count": result.advisory_count,
        "resolution_source": "required_diff",
    }
    return meta, None


def _load_forward_briefing(repo_root: Path, last_pcd_path: str) -> dict | None:
    """Extract the ephemeral zone from a handoff PCD file for forward briefing.

    Returns None when the file is missing or unparseable so the caller can
    gracefully skip attaching a briefing (phase 1, or clean repo states).
    """
    candidate = Path(last_pcd_path)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    if not candidate.exists():
        return None
    try:
        from akms.schema.validators import parse_pcd

        pcd = parse_pcd(candidate)
        return pcd.extract_ephemeral_zone()
    except Exception:
        logger.warning(
            "Failed to parse prior-phase PCD at %s", candidate, exc_info=True
        )
        return None


def _read_memories_from_results(
    task_results: list,
    repo_root: Path,
) -> list[AgentMemory]:
    """Read AgentMemory frontmatter from completed TaskResult memory files.

    Parses each file into a typed ``AgentMemory`` instance so downstream
    writers (``update_graph``) take the AgentMemory branch and correctly
    map ``status`` → ``outcome`` on session nodes. Skips failed results,
    missing files, and any frontmatter that fails schema validation (the
    failure is logged so it remains observable).

    Returns a list in deterministic order (sorted by ``task_id``).
    """
    import frontmatter
    from pydantic import ValidationError

    memories: list[tuple[str, AgentMemory]] = []
    for tr in task_results:
        if tr.status != "complete" or not tr.memory_path:
            continue
        mp = Path(tr.memory_path)
        if not mp.exists():
            continue
        try:
            post = frontmatter.load(str(mp))
            memory = AgentMemory(**dict(post.metadata))
        except (OSError, ValidationError):
            logger.exception("Failed to parse typed AgentMemory from %s", mp)
            continue
        except Exception:
            logger.exception("Unexpected error reading memory from %s", mp)
            continue
        memories.append((tr.task_id, memory))
    # Deterministic order by task_id
    memories.sort(key=lambda pair: pair[0])
    return [m for _, m in memories]


def _memory_task_id(m: object) -> str:
    """Extract ``task_id`` from an ``AgentMemory`` or legacy dict memory."""
    if isinstance(m, dict):
        return str(m.get("task_id", ""))
    return str(getattr(m, "task_id", ""))


def _memory_has_persistent_zone(m: object) -> bool:
    """Return True if a memory carries any field update_graph persists.

    Persistent-zone fields per the schema (§3 of spec / update_graph.py):
      - nodes_used, nodes_missing, pitfalls_discovered, new_knowledge
      - lessons.worked, lessons.failed

    Handles both typed ``AgentMemory`` instances (canonical) and legacy
    dict shapes (older fakes / direct MCP payloads). If any of the above
    is non-empty the memory must be routed to ``update_graph`` so the
    session is recorded; otherwise it can be skipped.
    """
    if isinstance(m, dict):
        if any(
            m.get(k)
            for k in (
                "nodes_used",
                "nodes_missing",
                "pitfalls_discovered",
                "new_knowledge",
            )
        ):
            return True
        lessons = m.get("lessons") or {}
        if isinstance(lessons, dict):
            return bool(lessons.get("worked") or lessons.get("failed"))
        return bool(
            getattr(lessons, "worked", None) or getattr(lessons, "failed", None)
        )

    if any(
        getattr(m, k, None)
        for k in (
            "nodes_used",
            "nodes_missing",
            "pitfalls_discovered",
            "new_knowledge",
        )
    ):
        return True
    lessons = getattr(m, "lessons", None)
    if lessons is None:
        return False
    return bool(getattr(lessons, "worked", None) or getattr(lessons, "failed", None))


# ═══════════════════════════════════════════════════════════════════════
#  Stage Handlers
# ═══════════════════════════════════════════════════════════════════════


@traced("akms.stage.init")
async def handle_init(state: PipelineState, ctx: PipelineContext) -> HandlerResult:
    """Stage 0: Compile graph from global + local sources."""
    G = build_graph(ctx.repo_root, global_vault=ctx.global_vault)

    graph_json = ctx.repo_root / "knowledge" / "graph" / "graph.json"
    graph_version = compute_graph_version(graph_json) if graph_json.exists() else ""

    state.started_at = state.started_at or datetime.now().isoformat()

    stage_output = (
        f"Graph compiled: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges"
    )
    akms_status = f"version={graph_version}"
    return stage_output, akms_status, []


@traced("akms.stage.plan")
async def handle_plan(state: PipelineState, ctx: PipelineContext) -> HandlerResult:
    """Stage 1: Planning agent produces plan.md."""
    graph_json = ctx.repo_root / "knowledge" / "graph" / "graph.json"
    G = (
        load_graph(graph_json)
        if graph_json.exists()
        else build_graph(
            ctx.repo_root,
            global_vault=ctx.global_vault,
        )
    )

    warnings: list[str] = []

    if ctx.agent_cls is None:
        return "skipped (graph-only mode)", f"nodes={G.number_of_nodes()}", warnings

    get_special_agent_config("planner")
    task_desc = "Produce plan.md from specification."
    if ctx.spec_path:
        task_desc = f"Generate plan from specification at: {ctx.spec_path}"
    planner_task: dict[str, Any] = {
        "task_id": "stage-plan",
        "title": "Pipeline plan generation",
        "objective": f"Generate plan for: {state.goal}",
        "task_description": task_desc,
        "phase_id": 0,
        "loadout_path": "",
        "agent_role": "planner",
        "akms_tags": [],
        "akms_schema": "v2",
    }
    if ctx.spec_path:
        planner_task["task_instructions_path"] = ctx.spec_path

    results = await dispatch_phase(
        [planner_task],
        agent_cls=ctx.agent_cls,
        config=ctx.config,
        repo_root=ctx.repo_root,
        model_override=ctx.model,
    )

    if not (results and results[0].status == "complete"):
        # The stage cannot succeed without a plan; take the pipeline's
        # failure path rather than presenting the failure at a gate as a
        # normal result.
        raise StageFailedError(
            "PLAN",
            f"planner agent returned: {results[0].status if results else 'no result'}",
        )
    stage_output = f"Plan written: {results[0].memory_path}"

    akms_status = f"nodes={G.number_of_nodes()}"
    return stage_output, akms_status, warnings


@traced("akms.stage.task_breakdown")
async def handle_task_breakdown(
    state: PipelineState,
    ctx: PipelineContext,
    tasks: list[dict] | None = None,
) -> HandlerResult:
    """Stage 2: Task decomposition with tag derivation."""
    graph_json = ctx.repo_root / "knowledge" / "graph" / "graph.json"
    G = (
        load_graph(graph_json)
        if graph_json.exists()
        else build_graph(
            ctx.repo_root,
            global_vault=ctx.global_vault,
        )
    )

    effective_tasks = list(tasks or [])
    warnings: list[str] = []

    # Dispatch decomposer if no tasks provided
    if not effective_tasks and ctx.agent_cls is not None:
        get_special_agent_config("task_decomposer")
        decomposer_task: dict[str, Any] = {
            "task_id": "stage-task-breakdown",
            "title": "Task decomposition",
            "objective": "Break approved plan into phased task JSONs.",
            "task_description": "Generate task breakdown artifacts.",
            "phase_id": 0,
            "loadout_path": "",
            "agent_role": "task_decomposer",
            "akms_tags": [],
            "akms_schema": "v2",
        }
        # Point the decomposer at detailed instructions if the file exists
        instructions_path = ctx.repo_root / "knowledge" / "task_instructions.md"
        if instructions_path.exists():
            decomposer_task["task_instructions_path"] = str(instructions_path)
        results = await dispatch_phase(
            [decomposer_task],
            agent_cls=ctx.agent_cls,
            config=ctx.config,
            repo_root=ctx.repo_root,
            model_override=ctx.model,
        )
        # Extract tasks from decomposer agent memory
        if results and results[0].status == "complete" and results[0].memory_path:
            effective_tasks = _extract_tasks_from_memory(Path(results[0].memory_path))
        if not effective_tasks:
            raise RuntimeError(
                "Task decomposer completed but produced no parseable tasks. "
                "The decomposer agent memory must include a 'tasks' key in its "
                "YAML frontmatter containing a list of task dicts."
            )
    elif not effective_tasks and ctx.agent_cls is None:
        return (
            "skipped (graph-only mode, no tasks provided)",
            f"nodes={G.number_of_nodes()}",
            warnings,
        )

    # Normalize and fill tags
    for task in effective_tasks:
        normalize_task_envelope(task)
    fill_task_tags(G, effective_tasks, ctx.config)

    # Count phases and initialize current_phase for the first execute cycle
    phases = {t.get("phase", 1) for t in effective_tasks}
    state.phase_order = sorted(phases)
    state.total_phases = len(phases)
    if phases and state.current_phase == 0:
        state.current_phase = state.phase_order[0]

    # Persist tasks on state so EXECUTE can access them across handler calls
    state.tasks = effective_tasks

    tags_filled = sum(1 for t in effective_tasks if t.get("akms_tags"))
    stage_output = f"{len(effective_tasks)} tasks across {len(phases)} phases"
    akms_status = f"tags_derived={tags_filled}"
    return stage_output, akms_status, warnings


@traced("akms.stage.scaffold")
async def handle_scaffold(state: PipelineState, ctx: PipelineContext) -> HandlerResult:
    """Stage 3: Scaffold agent produces test stubs."""
    warnings: list[str] = []

    if ctx.agent_cls is None:
        return "skipped (graph-only mode)", "", warnings

    get_special_agent_config("scaffolder")
    scaffolder_task = {
        "task_id": "stage-scaffold",
        "title": "Scaffold generation",
        "objective": "Generate test stubs and scaffold report.",
        "task_description": "Produce scaffold outputs for planned tasks.",
        "phase_id": 0,
        "loadout_path": "",
        "agent_role": "scaffolder",
        "akms_tags": [],
        "akms_schema": "v2",
    }

    results = await dispatch_phase(
        [scaffolder_task],
        agent_cls=ctx.agent_cls,
        config=ctx.config,
        repo_root=ctx.repo_root,
        model_override=ctx.model,
    )

    if not (results and results[0].status == "complete"):
        raise StageFailedError(
            "SCAFFOLD",
            f"scaffold agent returned: {results[0].status if results else 'no result'}",
        )
    stage_output = f"Scaffold complete: {results[0].memory_path}"

    return stage_output, "", warnings


@traced("akms.stage.execute")
async def handle_execute(
    state: PipelineState,
    ctx: PipelineContext,
    tasks: list[dict] | None = None,
) -> HandlerResult:
    """Stage 4: Execute phase -- dispatch subagents, collect memories, update graph.

    Only processes tasks whose ``phase`` matches ``state.current_phase``.
    Callers should pre-filter, but this handler applies a defensive filter
    to enforce the per-phase contract (FR-S05).
    """
    phase = state.current_phase
    graph_json = ctx.repo_root / "knowledge" / "graph" / "graph.json"
    G = (
        load_graph(graph_json)
        if graph_json.exists()
        else build_graph(
            ctx.repo_root,
            global_vault=ctx.global_vault,
        )
    )
    graph_version = compute_graph_version(graph_json) if graph_json.exists() else ""

    effective_tasks = list(tasks or [])
    warnings: list[str] = []

    if effective_tasks:
        effective_tasks = [t for t in effective_tasks if t.get("phase", 1) == phase]

    # Tag derivation + loadout generation
    for task in effective_tasks:
        normalize_task_envelope(task)
    fill_task_tags(G, effective_tasks, ctx.config)

    loadouts_dir = ctx.repo_root / "knowledge" / "loadouts"
    loadouts_dir.mkdir(parents=True, exist_ok=True)

    if state.last_pcd_path and effective_tasks:
        briefing = _load_forward_briefing(ctx.repo_root, state.last_pcd_path)
        if briefing is not None:
            for task in effective_tasks:
                task.setdefault("forward_briefing", briefing)

    for task in effective_tasks:
        task_id = task.get("task_id", "unknown")
        seed_tags = task.get("akms_tags", [])
        agent_role = task.get("agent_role", "implementer")

        ranked_nodes = query_subgraph(G, seed_tags, agent_role, config=ctx.config)
        available_ctx = task.get("available_context", 50000)
        mode = select_loadout_mode(ranked_nodes, available_ctx, ctx.config)

        loadout_path = loadouts_dir / f"{phase}-{task_id}-loadout.md"
        generate_loadout(
            G=G,
            ranked_nodes=ranked_nodes,
            task_id=task_id,
            phase=phase,
            graph_version=graph_version,
            seed_tags=seed_tags,
            agent_role=agent_role,
            mode=mode,
            available_context=available_ctx,
            config=ctx.config,
            output_path=loadout_path,
            repo_root=str(ctx.repo_root),
        )
        task["loadout_path"] = str(loadout_path)

    # Dispatch (graph-only mode skips this)
    if ctx.agent_cls is not None and effective_tasks:
        task_results = await dispatch_phase(
            effective_tasks,
            agent_cls=ctx.agent_cls,
            config=ctx.config,
            repo_root=ctx.repo_root,
            model_override=ctx.model,
        )
        failed = [r for r in task_results if r.status == "failed"]
        if failed:
            warnings.append(
                f"{len(failed)} tasks failed: {[r.task_id for r in failed]}"
            )

        #   # Post-dispatch: aggregate per-task AgentMemories into a single PCD,
        #           # write the handoff file, and apply it via update_graph once. Keeps the
        #           # knowledge-writeback path LLM-free while delivering phase aggregation.
        memories = _read_memories_from_results(task_results, ctx.repo_root)
        if memories:
            try:
                from akms.orchestrator.pcd_builder import build_pcd, write_handoff

                effective_plan_pcd = (
                    state.plan_name or ctx.config.orchestrator.plan_name or "plan"
                )
                phase_branch = phase_branch_name(effective_plan_pcd, phase)
                pcd_parent = parent_branch(
                    effective_plan_pcd,
                    ctx.config.orchestrator.base_branch,
                    phase,
                    phase_order=state.phase_order,
                )
                pcd_diff = _git_files_modified(ctx.repo_root, pcd_parent)
                git_state = {
                    "branch": phase_branch,
                    "plan_file": state.spec_path or "",
                    "files_modified": [
                        {"path": path, "changes": ""} for path in pcd_diff.paths
                    ],
                    "loadout_used": "",
                }
                pcd = build_pcd(memories, phase=phase, git_state=git_state)
                handoff_path = write_handoff(pcd, ctx.repo_root)
                try:
                    rel = handoff_path.relative_to(ctx.repo_root)
                    state.last_pcd_path = str(rel)
                except ValueError:
                    state.last_pcd_path = str(handoff_path)
                update_graph(
                    pcd,
                    ctx.repo_root,
                    config=ctx.config,
                    global_vault=ctx.global_vault,
                )
            except Exception:
                logger.exception("PCD aggregation / update_graph failed")

        #   # Generate code mirror via the configured provider. Use the phase-local
        #           # parent branch (NFR-B02). Capture drift_warnings for graph_status.
        #           # Deterministic refresh never passes llm_fn.
        effective_plan = state.plan_name or ctx.config.orchestrator.plan_name or "plan"
        effective_base = ctx.config.orchestrator.base_branch
        mirror_parent = parent_branch(
            effective_plan, effective_base, phase, phase_order=state.phase_order
        )
        mirror_cfg = resolve_mirror_config(ctx.config)
        try:
            mirror_result = generate_mirror(
                ctx.repo_root,
                phase=phase,
                parent_branch=mirror_parent,
                config=ctx.config,
                # Explicit no-LLM on the deterministic orchestrator path.
                llm_fn=None,
            )
            phase_drift_warnings = list(mirror_result.get("drift_warnings", []) or [])
            if mirror_result.get("fallback_used"):
                warnings.append(
                    f"mirror provider fell back to legacy from "
                    f"{mirror_result.get('provider_metadata', {}).get('fallback_from', '?')}"
                )
            phase_mirror_provider = {
                **public_provider_identity(mirror_cfg),
                "resolved_provider": mirror_result.get("provider"),
                "success": mirror_result.get("success", True),
                "fallback_used": mirror_result.get("fallback_used", False),
                "errors": list(mirror_result.get("errors") or []),
            }
        except MirrorProviderError as exc:
            phase_drift_warnings = []
            phase_mirror_provider = {
                **public_provider_identity(mirror_cfg),
                "resolved_provider": exc.provider or mirror_cfg.provider,
                "success": False,
                "fallback_used": False,
                "errors": [
                    {
                        "code": exc.code,
                        "message": str(exc),
                        "provider": exc.provider,
                    }
                ],
            }
            warnings.append(
                f"mirror provider {exc.provider or mirror_cfg.provider!r} failed: {exc}"
            )
            # Block graph rebuild when policy requires success (A2-6).
            if mirror_cfg.require_success or (
                mirror_cfg.provider != "legacy" and not mirror_cfg.fallback_on_error
            ):
                logger.error(
                    "Blocking post-phase graph status after required mirror failure "
                    "(provider=%s code=%s)",
                    exc.provider,
                    exc.code,
                )
                raise
    elif ctx.agent_cls is None:
        warnings.append("graph-only mode: agent dispatch skipped")
        phase_drift_warnings = []
        phase_mirror_provider = None
    else:
        phase_drift_warnings = []
        phase_mirror_provider = None

    #   # Post-phase: graph status — forward drift_warnings so the checkpoint sees them.
    status_result = graph_status(
        ctx.repo_root,
        global_vault=ctx.global_vault,
        config=ctx.config,
        drift_warnings=phase_drift_warnings or None,
        mirror_provider=phase_mirror_provider,
    )

    if status_result.get("degraded_nodes"):
        warnings.append(f"{len(status_result['degraded_nodes'])} degraded nodes")
    if phase_drift_warnings:
        warnings.append(f"{len(phase_drift_warnings)} docstring drift warnings")

    stage_output = f"Phase {phase} complete: {len(effective_tasks)} tasks"
    akms_status = format_report(status_result)
    return stage_output, akms_status, warnings


@traced("akms.stage.review")
async def handle_review(
    state: PipelineState,
    ctx: PipelineContext,
) -> HandlerResult:
    """Stage 5: Code + physics reviewers with role-specific loadouts.

    When a task route index is present, reviewer loadouts are produced via
    :func:`~akms.task_context.review.resolve_reviewer_context` so post-diff
    required lessons are delivered (with empty-diff fallback to task scope).
    When the route index is absent, the historical tag-based
    ``query_subgraph`` + ``generate_loadout`` path is used. With an adopted
    route index, diff collection and required-resolution failures fail closed.
    """
    phase = state.current_phase
    warnings: list[str] = []

    if ctx.agent_cls is None:
        status = graph_status(
            ctx.repo_root, global_vault=ctx.global_vault, config=ctx.config
        )
        return "skipped (graph-only mode)", format_report(status), warnings

    # Build graph for reviewer loadout generation
    graph_json = ctx.repo_root / "knowledge" / "graph" / "graph.json"
    G = (
        load_graph(graph_json)
        if graph_json.exists()
        else build_graph(
            ctx.repo_root,
            global_vault=ctx.global_vault,
        )
    )
    graph_version = compute_graph_version(graph_json) if graph_json.exists() else ""
    loadouts_dir = ctx.repo_root / "knowledge" / "loadouts"
    loadouts_dir.mkdir(parents=True, exist_ok=True)
    manifests_dir = ctx.repo_root / "knowledge" / "resolution-manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)

    reviewer_roles = [
        (
            f"phase-{phase}-code-review",
            f"Phase {phase} code review",
            AgentRole.CODE_REVIEWER.value,
        ),
        (
            f"phase-{phase}-physics-review",
            f"Phase {phase} physics review",
            AgentRole.PHYSICS_REVIEWER.value,
        ),
    ]

    #   # Derive seed tags from the phase branch's modified files, falling back
    #       # to the union of completed-task akms_tags this phase so the reviewer
    #       # loadout is never empty-by-construction.
    effective_plan = state.plan_name or ctx.config.orchestrator.plan_name or "plan"
    effective_base = ctx.config.orchestrator.base_branch
    review_parent = parent_branch(
        effective_plan,
        effective_base,
        phase,
        phase_order=state.phase_order,
    )
    diff_result = _git_files_modified(ctx.repo_root, review_parent)
    files_modified = list(diff_result.paths)
    phase_tasks = _phase_tasks(state, phase)
    fallback_tags: list[str] = []
    for task in phase_tasks:
        fallback_tags.extend(task.get("akms_tags") or [])
    # Preserve order while de-duplicating.
    fallback_tags = list(dict.fromkeys(fallback_tags))
    # Optional exact required-knowledge path (A2-3 wiring).
    route_index_path = _find_task_route_index(ctx.repo_root)
    if route_index_path is None:
        logger.info(
            "No task route index under knowledge/; reviewer loadouts use "
            "tag-based advisory resolution only"
        )
        warnings.append(
            "reviewer required-knowledge skipped: no task route index "
            "(looked under knowledge/task-routes.{yaml,json} and friends)"
        )
        if diff_result.error:
            warnings.append(
                "reviewer actual diff collection failed; using legacy advisory "
                f"fallback because no task route index is adopted: {diff_result.error}"
            )
    else:
        logger.info(
            "Using task route index for reviewer resolution: %s", route_index_path
        )
        if diff_result.error:
            diagnostic = (
                "reviewer required-knowledge resolution could not collect actual "
                f"diff for adopted route index {route_index_path}: {diff_result.error}"
            )
            logger.error("%s", diagnostic)
            raise RuntimeError(diagnostic)

    seed_tags = derive_review_seeds(
        G,
        files_modified,
        fallback_tags=fallback_tags,
    )

    post_diff_only_all: list[str] = []
    required_resolution_used = 0
    available_ctx = 50000

    reviewer_tasks = []
    for task_id, title, role in reviewer_roles:
        loadout_path = loadouts_dir / f"{phase}-{task_id}-loadout.md"
        manifest_path = manifests_dir / f"{phase}-{task_id}-manifest.json"
        resolution_meta: dict[str, Any] | None = None

        # Mode selection still uses advisory seed cost so full vs routing
        # stays consistent with the legacy path.
        ranked_nodes = query_subgraph(G, seed_tags, role, config=ctx.config)
        mode = select_loadout_mode(ranked_nodes, available_ctx, ctx.config)
        mode_str = mode.value if hasattr(mode, "value") else str(mode)

        if route_index_path is not None:
            review_task = _build_phase_review_task(
                phase=phase,
                task_id=task_id,
                title=title,
                phase_tasks=phase_tasks,
                fallback_tags=fallback_tags or list(seed_tags),
            )
            resolution_meta, resolve_error = _try_required_reviewer_loadout(
                repo_root=ctx.repo_root,
                route_index=route_index_path,
                task=review_task,
                agent_role=role,
                changed_paths=files_modified,
                phase=phase,
                loadout_path=loadout_path,
                manifest_path=manifest_path,
                graph_path=graph_json if graph_json.exists() else None,
                config=ctx.config,
                mode=mode_str,
                available_context=available_ctx,
            )
            if resolution_meta is None:
                detail = (
                    resolve_error or "required reviewer resolution returned no result"
                )
                diagnostic = (
                    "reviewer required-knowledge resolution failed for adopted "
                    f"route index {route_index_path}, role={role}: {detail}"
                )
                logger.error("%s", diagnostic)
                raise RuntimeError(diagnostic)

        if resolution_meta is None:
            # Legacy tag-based advisory loadout (also the soft-fail path).
            generate_loadout(
                G=G,
                ranked_nodes=ranked_nodes,
                task_id=task_id,
                phase=phase,
                graph_version=graph_version,
                seed_tags=seed_tags,
                agent_role=role,
                mode=mode,
                available_context=available_ctx,
                config=ctx.config,
                output_path=loadout_path,
                repo_root=str(ctx.repo_root),
            )
            resolution_source = "advisory_tags"
        else:
            required_resolution_used += 1
            resolution_source = "required_diff"
            post_diff_only_all.extend(
                resolution_meta.get("post_diff_only_required") or []
            )

        task_entry: dict[str, Any] = {
            "task_id": task_id,
            "title": title,
            "objective": f"Review phase {phase} changes.",
            "task_description": f"Run {role} for phase {phase}.",
            "phase_id": phase,
            "loadout_path": str(loadout_path),
            "agent_role": role,
            "plan_name": state.plan_name or ctx.config.orchestrator.plan_name,
            "base_branch": ctx.config.orchestrator.base_branch,
            "akms_tags": list(seed_tags),
            "akms_schema": "v2",
            "files_modified": list(files_modified),
            "resolution_source": resolution_source,
        }
        if resolution_meta is not None:
            task_entry["resolution_fingerprint"] = resolution_meta.get("fingerprint")
            task_entry["manifest_path"] = resolution_meta.get("manifest_path")
            task_entry["post_diff_only_required"] = list(
                resolution_meta.get("post_diff_only_required") or []
            )
            task_entry["pre_task_required"] = list(
                resolution_meta.get("pre_task_required") or []
            )
            task_entry["post_diff_required"] = list(
                resolution_meta.get("post_diff_required") or []
            )
            task_entry["empty_diff_fallback"] = bool(
                resolution_meta.get("empty_diff_fallback")
            )
        reviewer_tasks.append(task_entry)

    # Surface post-diff-only required lessons once for the stage (non-secret).
    if post_diff_only_all:
        unique_post_only = sorted(set(post_diff_only_all))
        warnings.append("post_diff_only_required: " + ", ".join(unique_post_only))
        logger.info(
            "Phase %s review post_diff_only_required=%s",
            phase,
            unique_post_only,
        )

    task_results = await dispatch_phase(
        reviewer_tasks,
        agent_cls=ctx.agent_cls,
        config=ctx.config,
        repo_root=ctx.repo_root,
        model_override=ctx.model,
    )

    completed = [r for r in task_results if r.status == "complete"]
    failed = [r for r in task_results if r.status == "failed"]
    if failed:
        warnings.append(f"{len(failed)} reviewers failed")

    # Update graph from review memories — route to update_graph only when
    # the memory carries persistent-zone content (nodes_used /
    # nodes_missing / pitfalls_discovered / new_knowledge / lessons).
    review_memories = _read_memories_from_results(task_results, ctx.repo_root)
    for memory in review_memories:
        if _memory_has_persistent_zone(memory):
            try:
                update_graph(
                    memory,
                    ctx.repo_root,
                    config=ctx.config,
                    global_vault=ctx.global_vault,
                )
            except Exception:
                logger.exception(
                    "update_graph failed for review %s",
                    _memory_task_id(memory),
                )

    stage_output = (
        f"Phase {phase} review: {len(completed)}/{len(task_results)} "
        f"reviewers completed"
    )
    akms_status = (
        f"reviews={len(completed)};"
        f"required_resolution={required_resolution_used};"
        f"changed_files={len(files_modified)}"
    )
    return stage_output, akms_status, warnings


@traced("akms.stage.finalize")
async def handle_finalize(state: PipelineState, ctx: PipelineContext) -> HandlerResult:
    """Stage 6: Final graph_status report, branch merge."""
    warnings: list[str] = []

    effective_plan = state.plan_name or ctx.config.orchestrator.plan_name or "plan"
    effective_base = ctx.config.orchestrator.base_branch

    finalize_ops = reverse_merge_plan(
        effective_plan,
        state.total_phases,
        effective_base,
        phase_order=state.phase_order,
    )
    execute_git_ops(finalize_ops, apply=False, repo_root=ctx.repo_root)

    state.stage_history.append(
        {
            "action": "branch_ops_finalize",
            "plan_name": effective_plan,
            "total_phases": state.total_phases,
            "planned_ops": finalize_ops,
            "timestamp": datetime.now().isoformat(),
        }
    )

    status_result = graph_status(
        ctx.repo_root,
        global_vault=ctx.global_vault,
        config=ctx.config,
    )
    report = format_report(status_result)

    stage_output = "Pipeline complete — final review"
    return stage_output, report, warnings


# ═══════════════════════════════════════════════════════════════════════
#  Handler Registry
# ═══════════════════════════════════════════════════════════════════════

STAGE_HANDLERS: dict[Stage, Any] = {
    Stage.INIT: handle_init,
    Stage.PLAN: handle_plan,
    Stage.TASK_BREAKDOWN: handle_task_breakdown,
    Stage.SCAFFOLD: handle_scaffold,
    Stage.EXECUTE: handle_execute,
    Stage.REVIEW: handle_review,
    Stage.FINALIZE: handle_finalize,
}


# ═══════════════════════════════════════════════════════════════════════
#  run_pipeline() — New Primary Entry Point
# ═══════════════════════════════════════════════════════════════════════


async def run_pipeline(
    repo_root: Path,
    spec_path: str = "",
    goal: str = "",
    plan_name: str = "",
    *,
    resume: bool = False,
    global_vault: str | Path | None = None,
    config: PropagationConfig | None = None,
    agent_cls: type[AKMSAgent] | None = AKMSAgent,
    model: str | None = None,
    checkpoint_handler: CheckpointHandler | None = None,
) -> "PipelineState":
    """Main orchestrator loop — new primary entry point.

    Linear state machine with developer gates. Checkpoint after every stage.
    Resume on crash or abort. Returns the final :class:`PipelineState`;
    inspect ``state.completed`` / ``state.aborted`` for the outcome.

    Raises:
        AgentPreflightError: The selected agent backend cannot run in this
            environment. Raised before any stage executes and before any
            file is written.
        StageFailedError: A stage's agent run failed. State is saved first,
            so the run is resumable with ``resume=True``.

    Args:
        repo_root: Repository root path.
        spec_path: Path to specification file.
        goal: High-level goal description.
        plan_name: Name for branches and artifacts.
        resume: Whether to resume from existing state.
        global_vault: Override global vault path.
        config: PropagationConfig (loads from file if None).
        agent_cls: AKMSAgent subclass (None = graph-only mode).
        model: Model string override.
        checkpoint_handler: How to present checkpoints.
            Defaults to FileCheckpointHandler.
    """
    repo_root = Path(repo_root)

    # Load config
    if config is None:
        config_path = repo_root / "knowledge" / "graph" / "propagation_config.yaml"
        if config_path.exists():
            config = parse_propagation_config(config_path)
        else:
            config = PropagationConfig()

    handler = checkpoint_handler or FileCheckpointHandler()

    # Agent preflight — before any stage runs and before any file is written.
    # A backend that cannot run here (missing SDK, missing binary) must fail
    # now with an actionable message, not deep inside the first dispatched
    # stage. The probe instance is constructed exactly as dispatch would
    # construct it and is discarded after the check.
    if agent_cls is not None:
        probe = agent_cls(config, repo_root=repo_root, model=model)
        # Duck-typed agent classes (the extension seam accepts anything with
        # the right constructor and execute()) may not implement preflight;
        # they are simply not checked.
        probe_preflight = getattr(probe, "preflight", None)
        reason = probe_preflight() if callable(probe_preflight) else None
        if reason:
            raise AgentPreflightError(reason)

    # F-06: resolve the effective vault once, up front, via the shared
    # helper so every handler sees the same path (precedence: explicit arg
    # > AKMS_GLOBAL_VAULT env var > config.global_vault > default).
    from akms.graph.build_graph import resolve_global_vault

    effective_vault: Path | str | None = (
        resolve_global_vault(explicit=global_vault, config=config)
        if (global_vault is not None or getattr(config, "global_vault", None))
        else None  # leave unset so downstream can honor env/default lazily
    )

    ctx = PipelineContext(
        repo_root=repo_root,
        global_vault=effective_vault,
        config=config,
        agent_cls=agent_cls,
        model=model,
        spec_path=spec_path,
    )

    # Resume or initialize state
    if resume:
        state = PipelineState.load(repo_root)
        if state is None:
            logger.warning("No state to resume — starting fresh")
            state = PipelineState(
                goal=goal,
                plan_name=plan_name or config.orchestrator.plan_name,
                spec_path=spec_path,
            )
        else:
            if state.aborted:
                state.resume()
            # Restore spec_path from persisted state if caller didn't re-pass it
            if not ctx.spec_path and state.spec_path:
                ctx = PipelineContext(
                    repo_root=ctx.repo_root,
                    global_vault=ctx.global_vault,
                    config=ctx.config,
                    agent_cls=ctx.agent_cls,
                    model=ctx.model,
                    spec_path=state.spec_path,
                )
        logger.info(
            "Resuming from stage: %s, phase: %d",
            state.current_stage.name,
            state.current_phase,
        )
    else:
        state = PipelineState(
            goal=goal,
            plan_name=plan_name or config.orchestrator.plan_name,
            spec_path=spec_path,
        )

    # Main loop
    current_idx = list(Stage).index(state.current_stage)

    while current_idx < list(Stage).index(Stage.COMPLETE):
        stage = STAGE_ORDER[current_idx]
        stage_handler = STAGE_HANDLERS.get(stage)
        if stage_handler is None:
            raise NotImplementedError(f"No handler for stage: {stage.name}")

        # Execute handler — stage-specific argument passing
        try:
            if stage == Stage.EXECUTE:
                phase_tasks = [
                    t for t in state.tasks if t.get("phase", 1) == state.current_phase
                ]
                result = await stage_handler(state, ctx, tasks=phase_tasks)
            elif stage == Stage.TASK_BREAKDOWN:
                # Always pass tasks=None: forces decomposer re-dispatch on
                # REJECT/EDIT re-runs instead of reusing stale state.tasks.
                result = await stage_handler(state, ctx, tasks=None)
            else:
                result = await stage_handler(state, ctx)
            stage_output, akms_status, warnings = result
        except Exception as e:
            state.save(repo_root)
            logger.error("Stage %s failed: %s", stage.name, e)
            logger.info("State saved. Resume with --resume flag.")
            raise

        state.stage_history.append(
            {
                "stage": stage.name,
                "phase": state.current_phase,
                "completed_at": datetime.now().isoformat(),
            }
        )
        state.save(repo_root)

        # INIT is automatic (no checkpoint)
        if stage == Stage.INIT:
            current_idx += 1
            state.current_stage = STAGE_ORDER[current_idx]
            state.save(repo_root)
            continue

        # Developer gate
        action = handler.present(state, stage_output, akms_status, warnings, repo_root)

        if action == CheckpointAction.APPROVE:
            if stage == Stage.REVIEW and state.phase_order:
                phase_idx = (
                    state.phase_order.index(state.current_phase)
                    if state.current_phase in state.phase_order
                    else -1
                )
                if phase_idx + 1 < len(state.phase_order):
                    # More phases to execute — loop back to EXECUTE
                    state.current_phase = state.phase_order[phase_idx + 1]
                    current_idx = list(Stage).index(Stage.EXECUTE)
                else:
                    # All phases done — advance past REVIEW to FINALIZE
                    current_idx += 1
            else:
                current_idx += 1
            state.current_stage = STAGE_ORDER[current_idx]

        elif action == CheckpointAction.REJECT:
            state.stage_history.append(
                {
                    "action": "rejected",
                    "stage": stage.name,
                    "at": datetime.now().isoformat(),
                }
            )
            # Re-run same stage (don't advance current_idx)

        elif action == CheckpointAction.EDIT:
            state.stage_history.append(
                {
                    "action": "edit",
                    "stage": stage.name,
                    "at": datetime.now().isoformat(),
                }
            )
            # Re-run same stage after manual edits

        elif action == CheckpointAction.ABORT:
            state.abort("Developer abort")
            state.save(repo_root)
            logger.info("Pipeline aborted. State saved. Resume with --resume.")
            return state

        state.save(repo_root)

    # Pipeline complete
    state.mark_completed()
    state.save(repo_root)
    logger.info("Pipeline complete.")
    return state
