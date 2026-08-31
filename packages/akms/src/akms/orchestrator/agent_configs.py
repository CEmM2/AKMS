"""agent_configs.py — Per-Role Agent Configurations (§3 of system design).

Defines the configuration and behavior profiles for different agent roles
within the AKMS orchestrator pipeline.

Three primary roles:
- **Implementer**: Standard tools + AKMS loadout for task execution
- **Code Reviewer**: Phase diffs + search_mirror.qmd access for code review
- **Physics Reviewer**: contradicts edges, domain-focused loadout for physics validation
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from akms.schema.models import AgentRole

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for an agent role."""

    role: AgentRole
    name: str
    description: str
    model_tier: str = "sonnet"
    tools: list[str] = field(default_factory=list)
    system_prompt_additions: str = ""
    loadout_required: bool = True
    receives_phase_diffs: bool = False
    parallel_capable: bool = True


# ═══════════════════════════════════════════════════════════════════════
#  Default Agent Configurations
# ═══════════════════════════════════════════════════════════════════════


#   # ═══════════════════════════════════════════════════════════════════════
#   #  Logical → Runtime Tool Map
#   # ═══════════════════════════════════════════════════════════════════════

TOOL_NAME_MAP: dict[str, list[str]] = {
    # File-system reads
    "file_read": ["Read", "Glob"],
    # File-system writes
    "file_edit": ["Read", "Write", "Edit", "MultiEdit"],
    "terminal": ["Bash"],
    # Concept search across nodes + sessions (qmd-backed)
    "search": [
        "mcp__akms__akms_search_nodes",
        "mcp__akms__akms_search_sessions",
    ],
    # Code-mirror search + pitfalls (qmd-backed) — FR-Q05 reviewer surface
    "search_mirror": [
        "mcp__akms__akms_search_mirror",
        "mcp__akms__akms_get_pitfalls",
    ],
    # Loadout is delivered via file path; Read covers it
    "akms_loadout": ["Read"],
}


def resolve_runtime_tools(logical_tools: list[str]) -> list[str]:
    """Translate a list of logical tool names into concrete runtime names.

    Grep is never introduced. Unknown logical names produce a warning and
    are skipped. The result is deterministically ordered and deduplicated.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for name in logical_tools or []:
        mapping = TOOL_NAME_MAP.get(name)
        if mapping is None:
            logger.warning("Unknown logical tool name: %r — skipping", name)
            continue
        for concrete in mapping:
            if concrete == "Grep":
                # Defensive — FR-C05 forbids Grep.
                continue
            if concrete not in seen:
                seen.add(concrete)
                ordered.append(concrete)
    return ordered


#: Baseline runtime tools when task_json['tools'] is empty (legacy callers).
#: Grep is explicitly NOT in this list (FR-C05 / F-11 removal).
BASELINE_ALLOWED_TOOLS: list[str] = [
    "Read",
    "Write",
    "Edit",
    "MultiEdit",
    "Glob",
    "Bash",
]


AGENT_CONFIGS: dict[AgentRole, AgentConfig] = {
    AgentRole.IMPLEMENTER: AgentConfig(
        role=AgentRole.IMPLEMENTER,
        name="Implementer",
        description="Task execution agent with standard tools and AKMS loadout",
        model_tier="sonnet",
        tools=["file_edit", "terminal", "search", "akms_loadout"],
        system_prompt_additions=(
            "You are an implementation agent. Your loadout file contains domain "
            "knowledge, pitfall warnings, and session history relevant to your task. "
            "Read the loadout before starting implementation. "
            "Write an AgentMemory file when done."
        ),
        loadout_required=True,
        receives_phase_diffs=False,
        parallel_capable=True,
    ),
    AgentRole.CODE_REVIEWER: AgentConfig(
        role=AgentRole.CODE_REVIEWER,
        name="Code Reviewer",
        description="Code review agent with phase diffs and code mirror access",
        model_tier="sonnet",
        tools=["file_read", "search", "akms_loadout", "search_mirror"],
        system_prompt_additions=(
            "You are a code review agent. Review the phase diffs for correctness, "
            "style, and alignment with the domain knowledge in your loadout. "
            "Use search_mirror to trace code back to knowledge concepts. "
            "Flag any nodes as 'outdated' if the code has evolved past them. "
            "Write an AgentMemory file with your review findings."
        ),
        loadout_required=True,
        receives_phase_diffs=True,
        parallel_capable=True,
    ),
    AgentRole.PHYSICS_REVIEWER: AgentConfig(
        role=AgentRole.PHYSICS_REVIEWER,
        name="Physics Reviewer",
        description="Domain validation agent with contradicts edges and physics-focused loadout",
        model_tier="opus",
        tools=["file_read", "search", "akms_loadout"],
        system_prompt_additions=(
            "You are a physics/domain review agent. Your loadout includes 'contradicts' "
            "edges highlighting potential conflicts between domain knowledge nodes. "
            "Review the implementation for physical correctness and domain consistency. "
            "Flag any nodes as 'outdated' if the implementation reveals errors. "
            "Write an AgentMemory file with your findings."
        ),
        loadout_required=True,
        receives_phase_diffs=True,
        parallel_capable=True,
    ),
}


def get_agent_config(role: AgentRole | str) -> AgentConfig:
    """Get the agent configuration for a role.

    Args:
        role: Agent role (enum or string).

    Returns:
        AgentConfig for the role.

    Raises:
        ValueError: If role is unknown.
    """
    if isinstance(role, str):
        try:
            role = AgentRole(role)
        except ValueError:
            raise ValueError(f"Unknown agent role: {role}")

    if role not in AGENT_CONFIGS:
        raise ValueError(f"No configuration for role: {role}")

    return AGENT_CONFIGS[role]


@dataclass
class SpecialAgentConfig:
    """Configuration for non-role-based agents (planner, scaffolder, etc.)."""

    name: str
    description: str
    model_tier: str = "sonnet"
    tools: list[str] = field(default_factory=list)
    system_prompt_additions: str = ""


SPECIAL_AGENTS: dict[str, SpecialAgentConfig] = {
    "planner": SpecialAgentConfig(
        name="Planning Agent",
        description="Produces plan.md with design decisions from spec + domain loadout",
        model_tier="opus",
        tools=["file_read", "file_edit", "search", "akms_loadout"],
        system_prompt_additions=(
            "You are a planning agent. Produce a detailed plan.md with design "
            "decisions based on the specification and your domain loadout. "
            "Write an AgentMemory file when done."
        ),
    ),
    "task_decomposer": SpecialAgentConfig(
        name="Task Decomposition Agent",
        description="Breaks plan into task JSONs per phase",
        model_tier="sonnet",
        tools=["file_read", "file_edit", "akms_loadout"],
        system_prompt_additions=(
            "You are a task decomposition agent. Break the approved plan into "
            "task JSONs with phases, waves, dependencies (blocked_by), and "
            "scope fields. Your AgentMemory file MUST include a 'tasks' key "
            "in the YAML frontmatter containing the list of task dicts. "
            "If a task_instructions_path is provided in your task assignment, "
            "read that file for detailed decomposition instructions. "
            "Example frontmatter:\n"
            "---\n"
            "task_id: stage-task-breakdown\n"
            "status: complete\n"
            "tasks:\n"
            "  - {task_id: T-001, phase: 1, title: ...}\n"
            "  - {task_id: T-002, phase: 1, blocked_by: [T-001], ...}\n"
            "---"
        ),
    ),
    "scaffolder": SpecialAgentConfig(
        name="Scaffold Agent",
        description="Produces test stubs and scaffold validation report",
        model_tier="sonnet",
        tools=["file_read", "file_edit", "terminal", "akms_loadout"],
        system_prompt_additions=(
            "You are a scaffold agent. Create test stubs and project scaffolding "
            "based on the task breakdown. Validate that the scaffold covers all "
            "tasks. Write an AgentMemory file when done."
        ),
    ),
    "phase_agent": SpecialAgentConfig(
        name="Phase Agent",
        description="Dispatches subagents per wave and aggregates AgentMemories into PCD",
        model_tier="sonnet",
        tools=["file_read", "file_edit", "terminal", "search", "akms_loadout"],
        system_prompt_additions=(
            "You are a phase execution agent. Dispatch subagents per wave "
            "(respecting blocked_by dependencies). Aggregate all subagent "
            "AgentMemories into a Phase Completion Document (PCD)."
        ),
    ),
}


def get_special_agent_config(name: str) -> SpecialAgentConfig:
    """Get a special (non-role-based) agent configuration.

    Args:
        name: Agent name (planner, task_decomposer, scaffolder, phase_agent).

    Returns:
        SpecialAgentConfig.

    Raises:
        ValueError: If agent name is unknown.
    """
    if name not in SPECIAL_AGENTS:
        raise ValueError(
            f"Unknown special agent: {name}. Available: {list(SPECIAL_AGENTS.keys())}"
        )
    return SPECIAL_AGENTS[name]
