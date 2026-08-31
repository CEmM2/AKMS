"""stages.py — Stage State Machine for AKMS Orchestrator (§3 of system design).

Defines the 8-stage pipeline and transition rules. Each stage has:
- An associated set of AKMS operations (compile, loadout, update, etc.)
- A checkpoint requirement (all stages except INIT and COMPLETE)
- Valid transitions to next stages

The orchestrator drives the state machine; stages are passive definitions.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Stage Definitions
# ═══════════════════════════════════════════════════════════════════════


class Stage(IntEnum):
    """Orchestrator pipeline stages per §3 of system design."""

    INIT = 0
    PLAN = 1            # planning agent + loadout
    TASK_BREAKDOWN = 2
    SCAFFOLD = 3
    EXECUTE = 4
    REVIEW = 5          # code + physics reviewers
    FINALIZE = 6        # final report, branch merge
    COMPLETE = 7        # terminal state — pipeline finished


# ═══════════════════════════════════════════════════════════════════════
#  Stage Wire Serialization
# ═══════════════════════════════════════════════════════════════════════

def stage_to_wire(stage: Stage) -> str:
    """Serialize Stage to wire format (lowercase string).

    Used in checkpoint files and pipeline_state.json.
    Example: Stage.EXECUTE → "execute"
    """
    return stage.name.lower()


def stage_from_wire(raw: object) -> Stage:
    """Deserialize Stage from wire format with backward compatibility.

    Accepts:
        - Stage enum member: Stage.EXECUTE → Stage.EXECUTE
        - int: 4 → Stage.EXECUTE
        - string int: "4" → Stage.EXECUTE
        - uppercase name: "EXECUTE" → Stage.EXECUTE
        - lowercase name: "execute" → Stage.EXECUTE
        - prefixed name: "Stage.EXECUTE" → Stage.EXECUTE

    Raises:
        ValueError: If raw cannot be parsed as a Stage.
    """
    if isinstance(raw, Stage):
        return raw
    if isinstance(raw, int):
        return Stage(raw)
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("Stage."):
            s = s.split(".", 1)[1]
        if s.isdigit():
            return Stage(int(s))
        try:
            return Stage[s.upper()]
        except KeyError:
            raise ValueError(f"Invalid stage string: {raw!r}")
    raise ValueError(f"Invalid stage type: {type(raw).__name__} ({raw!r})")


class CheckpointAction(str, Enum):
    """Actions available at a checkpoint."""

    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    ABORT = "abort"


# Checkpoint actions as wire-format constants
CHECKPOINT_ACTIONS = [action.value for action in CheckpointAction]


# ═══════════════════════════════════════════════════════════════════════
#  Stage Metadata
# ═══════════════════════════════════════════════════════════════════════


class StageDefinition:
    """Metadata for a pipeline stage."""

    def __init__(
        self,
        stage: Stage,
        name: str,
        requires_checkpoint: bool,
        akms_operations: list[str],
        valid_next: list[Stage],
        description: str = "",
    ):
        self.stage = stage
        self.name = name
        self.requires_checkpoint = requires_checkpoint
        self.akms_operations = akms_operations
        self.valid_next = valid_next
        self.description = description


# Stage registry — defines the full pipeline
STAGE_DEFINITIONS: dict[Stage, StageDefinition] = {
    Stage.INIT: StageDefinition(
        stage=Stage.INIT,
        name="Init",
        requires_checkpoint=False,
        akms_operations=["build_graph"],
        valid_next=[Stage.PLAN],
        description="Compile graph from global + local sources",
    ),
    Stage.PLAN: StageDefinition(
        stage=Stage.PLAN,
        name="Plan",
        requires_checkpoint=True,
        akms_operations=["generate_loadout"],
        valid_next=[Stage.TASK_BREAKDOWN],
        description="Planning agent produces plan.md with design decisions",
    ),
    Stage.TASK_BREAKDOWN: StageDefinition(
        stage=Stage.TASK_BREAKDOWN,
        name="Task Breakdown",
        requires_checkpoint=True,
        akms_operations=["generate_loadout", "derive_tags"],
        valid_next=[Stage.SCAFFOLD],
        description="Task decomposition agent produces task JSONs per phase",
    ),
    Stage.SCAFFOLD: StageDefinition(
        stage=Stage.SCAFFOLD,
        name="Scaffold",
        requires_checkpoint=True,
        akms_operations=["generate_loadout"],
        valid_next=[Stage.EXECUTE],
        description="Scaffold agent produces test stubs and validation report",
    ),
    Stage.EXECUTE: StageDefinition(
        stage=Stage.EXECUTE,
        name="Execute",
        requires_checkpoint=True,
        akms_operations=[
            "generate_loadout", "derive_tags", "update_graph",
            "generate_mirror", "graph_status", "re_evaluate",
        ],
        valid_next=[Stage.REVIEW],
        description="Phase loop: dispatch subagents, collect memories, update graph",
    ),
    Stage.REVIEW: StageDefinition(
        stage=Stage.REVIEW,
        name="Review",
        requires_checkpoint=True,
        akms_operations=["generate_loadout", "update_graph"],
        valid_next=[Stage.EXECUTE, Stage.FINALIZE],
        description="Code + physics reviewers with role-specific loadouts",
    ),
    Stage.FINALIZE: StageDefinition(
        stage=Stage.FINALIZE,
        name="Finalize",
        requires_checkpoint=True,
        akms_operations=["graph_status"],
        valid_next=[Stage.COMPLETE],
        description="Final graph_status report, node promotions, branch merge",
    ),
    Stage.COMPLETE: StageDefinition(
        stage=Stage.COMPLETE,
        name="Complete",
        requires_checkpoint=False,
        akms_operations=[],
        valid_next=[],
        description="Terminal state — pipeline finished",
    ),
}


def get_stage_definition(stage: Stage) -> StageDefinition:
    """Get the definition for a stage."""
    return STAGE_DEFINITIONS[stage]


def is_valid_transition(from_stage: Stage, to_stage: Stage) -> bool:
    """Check if a stage transition is valid."""
    defn = STAGE_DEFINITIONS[from_stage]
    return to_stage in defn.valid_next


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline Convenience Constants
# ═══════════════════════════════════════════════════════════════════════

# All 8 stages in canonical pipeline order (INIT → COMPLETE).
STAGE_ORDER: list[Stage] = [
    Stage.INIT,
    Stage.PLAN,
    Stage.TASK_BREAKDOWN,
    Stage.SCAFFOLD,
    Stage.EXECUTE,
    Stage.REVIEW,
    Stage.FINALIZE,
    Stage.COMPLETE,
]

# Stages that form the execute/review loop (may repeat across phases).
LOOPING_STAGES: set[Stage] = {Stage.EXECUTE, Stage.REVIEW}


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline State (Persistent)
# ═══════════════════════════════════════════════════════════════════════


class PipelineState:
    """Persistent pipeline state for abort/resume support.

    Saved as JSON to ``knowledge/graph/pipeline_state.json``.
    """

    def __init__(
        self,
        current_stage: Stage = Stage.INIT,
        current_phase: int = 0,
        total_phases: int = 0,
        plan_name: str = "",
        goal: str = "",
        started_at: str | None = None,
        stage_history: list[dict] | None = None,
        aborted: bool = False,
        abort_reason: str = "",
        completed: bool = False,
        tasks: list[dict] | None = None,
        phase_order: list[int] | None = None,
        spec_path: str = "",
        last_pcd_path: str = "",
    ):
        self.current_stage = current_stage
        self.current_phase = current_phase
        self.total_phases = total_phases
        self.plan_name = plan_name
        self.goal = goal
        self.started_at = started_at or datetime.now().isoformat()
        self.stage_history = stage_history or []
        self.aborted = aborted
        self.abort_reason = abort_reason
        self.completed = completed
        self.tasks: list[dict] = tasks or []
        self.phase_order: list[int] = phase_order or []
        self.spec_path: str = spec_path
        # Path to the most recent phase's handoff_phase_{N}.md.
        # Used by handle_execute of phase N+1 to attach a forward briefing
        # block to subagent task prompts. Relative to repo_root.
        self.last_pcd_path: str = last_pcd_path

    def advance_to(self, next_stage: Stage, metadata: dict | None = None) -> None:
        """Advance the pipeline to the next stage.

        Raises ValueError if the transition is invalid.
        """
        if not is_valid_transition(self.current_stage, next_stage):
            raise ValueError(
                f"Invalid transition: {self.current_stage.name} → {next_stage.name}. "
                f"Valid targets: {[s.name for s in STAGE_DEFINITIONS[self.current_stage].valid_next]}"
            )

        self.stage_history.append({
            "from_stage": self.current_stage.name,
            "to_stage": next_stage.name,
            "timestamp": datetime.now().isoformat(),
            "phase": self.current_phase,
            **(metadata or {}),
        })
        self.current_stage = next_stage

    def abort(self, reason: str = "") -> None:
        """Abort the pipeline, preserving state for resumption."""
        self.aborted = True
        self.abort_reason = reason
        self.stage_history.append({
            "action": "abort",
            "stage": self.current_stage.name,
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
        })

    def resume(self) -> None:
        """Resume from an aborted state."""
        if not self.aborted:
            raise ValueError("Pipeline is not aborted — cannot resume")
        self.aborted = False
        self.abort_reason = ""
        self.stage_history.append({
            "action": "resume",
            "stage": self.current_stage.name,
            "timestamp": datetime.now().isoformat(),
        })

    def mark_completed(self) -> None:
        """Mark the pipeline as completed."""
        self.completed = True
        self.stage_history.append({
            "action": "completed",
            "stage": self.current_stage.name,
            "timestamp": datetime.now().isoformat(),
        })

    def to_dict(self) -> dict:
        """Serialize to a dict for JSON persistence."""
        return {
            "current_stage": stage_to_wire(self.current_stage),
            "current_phase": self.current_phase,
            "total_phases": self.total_phases,
            "plan_name": self.plan_name,
            "goal": self.goal,
            "started_at": self.started_at,
            "stage_history": self.stage_history,
            "aborted": self.aborted,
            "abort_reason": self.abort_reason,
            "completed": self.completed,
            "tasks": self.tasks,
            "phase_order": self.phase_order,
            "spec_path": self.spec_path,
            "last_pcd_path": self.last_pcd_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PipelineState:
        """Deserialize from a dict."""
        raw_stage = data.get("current_stage", "init")
        try:
            current_stage = stage_from_wire(raw_stage)
        except (ValueError, KeyError):
            current_stage = Stage.INIT

        return cls(
            current_stage=current_stage,
            current_phase=data.get("current_phase", 0),
            total_phases=data.get("total_phases", 0),
            plan_name=data.get("plan_name", ""),
            goal=data.get("goal", ""),
            started_at=data.get("started_at"),
            stage_history=data.get("stage_history", []),
            aborted=data.get("aborted", False),
            abort_reason=data.get("abort_reason", ""),
            completed=data.get("completed", False),
            tasks=data.get("tasks", []),
            phase_order=data.get("phase_order", []),
            spec_path=data.get("spec_path", ""),
            last_pcd_path=data.get("last_pcd_path", ""),
        )

    def save(self, repo_root: Path) -> Path:
        """Save pipeline state to knowledge/graph/pipeline_state.json."""
        state_path = repo_root / "knowledge" / "graph" / "pipeline_state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with open(state_path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info("Pipeline state saved: stage=%s", self.current_stage.name)
        return state_path

    @classmethod
    def load(cls, repo_root: Path) -> PipelineState | None:
        """Load pipeline state from knowledge/graph/pipeline_state.json.

        Returns None if no state file exists.
        """
        state_path = repo_root / "knowledge" / "graph" / "pipeline_state.json"
        if not state_path.exists():
            return None
        with open(state_path) as f:
            data = json.load(f)
        logger.info("Pipeline state loaded: stage=%s", data.get("current_stage"))
        return cls.from_dict(data)

    @classmethod
    def load_or_create(cls, repo_root: Path, **kwargs: Any) -> PipelineState:
        """Load existing state or create a new one."""
        existing = cls.load(repo_root)
        if existing is not None:
            return existing
        state = cls(**kwargs)
        state.save(repo_root)
        return state
