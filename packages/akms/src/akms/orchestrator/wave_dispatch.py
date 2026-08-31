"""wave_dispatch.py — Parallel subagent dispatch within Execute/Review phases.

Uses asyncio.gather with dependency checking. No framework needed —
just structured concurrency with the existing AKMSAgent protocol.

**Deviation D1 from addendum:** Uses AKMSAgent.run() instead of raw
claude_agent_sdk.query(). This preserves the sealed run() + open execute()
architecture — loadout resolution, system prompt assembly, and AgentMemory
validation all happen inside the agent's lifecycle.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from akms.orchestrator.agent_configs import get_agent_config, get_special_agent_config
from akms.telemetry import trace_agent_call

if TYPE_CHECKING:
    from akms.agents.base import AKMSAgent
    from akms.schema.models import AgentMemory, PropagationConfig

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Data Types
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class TaskResult:
    """Result of a single subagent dispatch."""

    task_id: str
    status: str
    memory_path: str  # path to AgentMemory file
    error: str | None = None


# ═══════════════════════════════════════════════════════════════════════
#  Model Resolution
# ═══════════════════════════════════════════════════════════════════════


def resolve_model_for_tier(
    model_tier: str,
    model_override: str | None = None,
    config: PropagationConfig | None = None,
) -> str:
    """Resolve dispatch model from role tier and orchestrator defaults.

    Priority: explicit override > tier mapping > config default.

    Note: AgentConfig has no resolve_model() method — it only has a
    model_tier: str field. This function is the resolution point.
    """
    if model_override:
        return model_override
    tier_map = {
        "opus": "claude-opus-4-6",
        "sonnet": "claude-sonnet-4-6",
        "haiku": "claude-haiku-4-5",
    }
    if model_tier in tier_map:
        return tier_map[model_tier]
    if config is not None:
        return config.orchestrator.default_model
    return "claude-sonnet-4-6"


# ═══════════════════════════════════════════════════════════════════════
#  Single Agent Dispatch (with AgentConfig wiring — closes Q4 gap)
# ═══════════════════════════════════════════════════════════════════════


async def run_subagent(
    task_json: dict[str, Any],
    agent_cls: type[AKMSAgent],
    config: PropagationConfig,
    repo_root: Path,
    model_override: str | None = None,
) -> TaskResult:
    """Run a single subagent for a task via AKMSAgent protocol.

    **AgentConfig wiring (Q4):** This function closes the gap between
    agent_configs.py declarations and actual dispatch. It reads model_tier
    from AgentConfig, passes it to resolve_model_for_tier(), and injects
    system_prompt_additions and tools into task_json.
    """
    task_id = task_json.get("task_id", "unknown")
    role = task_json.get("agent_role", "implementer")

    # ── Resolve AgentConfig for this role ──
    try:
        agent_config = get_agent_config(role)
        model_tier = agent_config.model_tier
        system_additions = agent_config.system_prompt_additions
        tools = agent_config.tools
        receives_diffs = agent_config.receives_phase_diffs
    except ValueError:
        try:
            special_config = get_special_agent_config(role)
            model_tier = special_config.model_tier
            system_additions = special_config.system_prompt_additions
            tools = special_config.tools
            receives_diffs = False
        except ValueError:
            model_tier = "sonnet"
            system_additions = ""
            tools = []
            receives_diffs = False

    effective_model = resolve_model_for_tier(model_tier, model_override, config)

    # ── Enrich task_json with role-specific context ──
    task_json.setdefault("system_prompt_additions", system_additions)
    task_json.setdefault("tools", tools)

    # Populate phase_diffs for reviewers
    if receives_diffs and "phase_diffs" not in task_json:
        phase_diffs = await _get_phase_diffs(repo_root, task_json)
        if phase_diffs:
            task_json["phase_diffs"] = phase_diffs

    # ── Dispatch via AKMSAgent protocol ──
    span = trace_agent_call(task_id, role, effective_model)
    try:
        agent = agent_cls(
            config=config,
            model=effective_model,
            repo_root=repo_root,
        )
        memory: AgentMemory = await agent.run(task_json)

        memory_path = ""
        if hasattr(memory, "task_id"):
            memory_path = str(
                repo_root / "knowledge" / "sessions" / f"{memory.task_id}.md"
            )

        # The sealed run() never raises for an agent failure — it writes and
        # returns a failed AgentMemory instead. The memory's own status is
        # therefore the task outcome; reporting "complete" here would present
        # a failed agent as a successful stage.
        memory_status = getattr(memory, "status", "complete") or "complete"
        # TaskStatus is a str-mixin enum; normalize to its plain value.
        memory_status = str(getattr(memory_status, "value", memory_status))
        task_status = (
            memory_status
            if memory_status in {"complete", "partial", "failed", "deferred"}
            else "complete"
        )
        span.set_attribute("akms.success", task_status == "complete")
        return TaskResult(
            task_id=task_id,
            status=task_status,
            memory_path=memory_path,
            error=None
            if task_status == "complete"
            else f"agent memory status: {memory_status}",
        )
    except Exception as e:
        span.set_attribute("akms.success", False)
        span.record_exception(e)
        logger.exception("Subagent failed: task_id=%s role=%s", task_id, role)
        return TaskResult(
            task_id=task_id,
            status="failed",
            memory_path="",
            error=str(e),
        )
    finally:
        span.end()


async def _get_phase_diffs(repo_root: Path, task_json: dict) -> str:
    """Get git diff for phase branch (for reviewers with receives_phase_diffs).

    Uses asyncio subprocess to avoid blocking the event loop during
    parallel wave dispatch.
    """
    try:
        from akms.orchestrator.branch_workflow import phase_branch_name, parent_branch

        phase = task_json.get("phase_id", task_json.get("phase", 0))
        plan_name = task_json.get("plan_name", "plan")
        base_branch = task_json.get("base_branch", "main")

        pb = phase_branch_name(plan_name, phase)
        parent = parent_branch(plan_name, base_branch, phase)

        proc = await asyncio.create_subprocess_exec(
            "git",
            "diff",
            f"{parent}...{pb}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=repo_root,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return ""
        return stdout.decode() if proc.returncode == 0 else ""
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════════════
#  Wave Building
# ═══════════════════════════════════════════════════════════════════════


def build_waves(tasks: list[dict]) -> list[list[dict]]:
    """Organize tasks into dependency-ordered waves.

    Wave 1: all tasks with no blocked_by (or all blockers already complete)
    Wave N+1: tasks whose blocked_by set is fully satisfied by waves 1..N

    Raises:
        ValueError: On circular dependencies or unresolvable blockers.
    """
    completed: set[str] = set()
    remaining = list(tasks)
    waves: list[list[dict]] = []

    while remaining:
        wave = [
            t
            for t in remaining
            if all(dep in completed for dep in t.get("blocked_by", []))
        ]
        if not wave:
            unresolved = [t.get("task_id", "?") for t in remaining]
            raise ValueError(f"Cannot resolve dependencies for: {unresolved}")

        waves.append(wave)
        completed.update(t.get("task_id", "") for t in wave)
        remaining = [t for t in remaining if t.get("task_id", "") not in completed]

    return waves


def validate_scope_disjointness(wave: list[dict]) -> None:
    """Verify no two tasks in a wave touch the same files.

    Raises:
        ValueError: If any file path is claimed by multiple tasks.
    """
    seen_files: dict[str, str] = {}
    for task in wave:
        task_id = task.get("task_id", task.get("id", "unknown"))
        for file_path in task.get("scope", []):
            if file_path in seen_files:
                raise ValueError(
                    f"Scope conflict: {file_path} claimed by both "
                    f"{seen_files[file_path]} and {task_id}"
                )
            seen_files[file_path] = task_id


def find_blocked_tasks(
    remaining_waves: list[list[dict]],
    failed_ids: set[str],
) -> list[str]:
    """Find tasks in remaining waves that depend on failed tasks."""
    blocked = []
    for wave in remaining_waves:
        for task in wave:
            deps = set(task.get("blocked_by", []))
            if deps & failed_ids:
                blocked.append(task.get("task_id", "?"))
    return blocked


async def dispatch_phase(
    tasks: list[dict],
    agent_cls: type[AKMSAgent],
    config: PropagationConfig,
    repo_root: Path,
    model_override: str | None = None,
) -> list[TaskResult]:
    """Dispatch all tasks in a phase, respecting wave dependencies.

    Tasks within a wave run in parallel via asyncio.gather.
    Waves execute sequentially.

    **Bug fix:** Uses return_exceptions=True so one failed task does NOT
    kill other tasks in the same wave (matches existing ThreadPoolExecutor
    behavior and system design doc Section 8, wave dispatch rule 4).
    """
    waves = build_waves(tasks)
    all_results: list[TaskResult] = []

    for wave_idx, wave in enumerate(waves):
        validate_scope_disjointness(wave)

        raw_results = await asyncio.gather(
            *[
                run_subagent(task, agent_cls, config, repo_root, model_override)
                for task in wave
            ],
            return_exceptions=True,
        )

        # Convert bare exceptions to TaskResult(status="failed")
        results: list[TaskResult] = []
        for i, r in enumerate(raw_results):
            if isinstance(r, Exception):
                task_id = wave[i].get("task_id", "unknown")
                logger.exception(
                    "Unhandled exception in wave dispatch: task_id=%s",
                    task_id,
                    exc_info=r,
                )
                results.append(
                    TaskResult(
                        task_id=task_id,
                        status="failed",
                        memory_path="",
                        error=str(r),
                    )
                )
            else:
                results.append(r)

        all_results.extend(results)

        # Check for failures that block downstream waves
        failed = {r.task_id for r in results if r.status == "failed"}
        if failed and wave_idx + 1 < len(waves):
            blocked = find_blocked_tasks(waves[wave_idx + 1 :], failed)
            if blocked:
                logger.warning("Failed tasks %s block downstream: %s", failed, blocked)

    return all_results
