"""AKMSAgent base class — sealed protocol + overridable execution seam.

The two-layer architecture:

Layer 1 — Protocol (sealed, AKMS-owned):
    ``AKMSAgent.run()`` is the entry point. It owns the full AKMS-mandated
    lifecycle for a single task: loadout resolution, system prompt assembly,
    and post-execution AgentMemory validation. Not overridable.

Layer 2 — Execution (open, project-owned):
    ``AKMSAgent.execute()`` is the seam. It receives the parsed task JSON,
    loaded Loadout, and assembled system prompt, and runs the agent.
    AKMS ships a concrete default implementation (Claude Agent SDK
    ``query()``) so the CLI works without subclassing.
    Projects override this method to add model tier selection, MCP servers,
    custom tools, hooks, or multi-turn ``ClaudeSDKClient`` sessions.

Subclassing contract:
    1. ``execute()`` MUST NOT write AgentMemory itself — the agent running
       inside the SDK call does that as part of its work. ``run()`` reads
       and validates the file after ``execute()`` returns.
    2. ``execute()`` MUST raise on fatal errors — ``run()`` catches and
       writes a ``status: failed`` AgentMemory.
    3. ``execute()`` MAY use ``query()`` or ``ClaudeSDKClient`` — single-shot
       via ``query()`` for simple tasks, or interactive multi-turn via
       ``ClaudeSDKClient`` for complex workflows. ``run()`` doesn't care.
"""

from __future__ import annotations

import logging
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import frontmatter
from pydantic import ValidationError

from akms.schema.errors import SchemaValidationError
from akms.schema.models import (
    AgentMemory,
    LoadoutHeader,
    PropagationConfig,
    TaskStatus,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#                          DATA CLASSES
# ══════════════════════════════════════════════════════════════════════


@dataclass
class Loadout:
    """Parsed loadout data passed to execute().

    Metadata fields mirror ``LoadoutHeader`` from ``akms.schema.models``
    (§5 of spec doc 03). The ``content`` field carries the raw markdown
    body which is not part of the schema header.
    """

    path: str
    task_id: str = ""
    phase: int = 0
    graph_version: str = ""
    seed_tags: list[str] = field(default_factory=list)
    agent_role: str = "implementer"
    node_count: int = 0
    loadout_mode: str = "routing"
    available_context: int = 0
    qmd_available: bool = True
    content: str = ""  # Full loadout markdown body (not in LoadoutHeader)


# ══════════════════════════════════════════════════════════════════════
#                         AKMSAgent BASE CLASS
# ══════════════════════════════════════════════════════════════════════


# Template for the AgentMemory schema instructions injected into system
# prompts.  The agent must write this file on task completion.
_AGENT_MEMORY_INSTRUCTIONS = textwrap.dedent("""\
    # AgentMemory Write Instructions

    On task completion you MUST write an AgentMemory file to:
        {memory_path}

    The file must be valid YAML frontmatter (delimited by ``---``) followed
    by a free-form ``## Task Notes`` markdown section with your observations.

    Required frontmatter fields:
    ```yaml
    ---
    task_id: "{task_id}"
    task_description: "<brief description>"
    phase_id: {phase_id}
    timestamp: "<ISO 8601>"
    agent_model: "<model used>"
    loadout_used: "{loadout_path}"
    status: complete|partial|failed|deferred
    commit: <commit hash or null>
    tests_passed: <int>
    tests_total: <int>
    completion_notes: "<summary>"
    nodes_used:          # list — for each knowledge node you consulted
      - id: "<node-id>"
        useful: true|false
        coverage: sufficient|missing-detail|outdated
        note: "<optional feedback>"
    nodes_missing:       # list — knowledge you needed but didn't exist
      - description: "<what was missing>"
        suggested_id: "<kebab-case-id>"
        domain: "<domain>"
        tags: [...]
        priority: high|medium|low
    lessons:
      worked: ["<what worked>"]
      failed:
        - what: "<what failed>"
          why: "<root cause>"
          fix: "<how to fix>"
    pitfalls_discovered:
      - description: "<pitfall>"
        severity: high|medium|low
        node_ref: "<optional node id>"
        suggested_id: "<optional pitfall node id>"
    new_knowledge:
      - suggested_id: "<kebab-case-id>"
        title: "<title>"
        domain: "<domain>"
        tags: [...]
        content_draft: "<markdown content>"
        status: tentative
        source: agent
    akms_schema: "v2"
    ---
    ## Task Notes

    <Your free-form observations, reasoning, and notes here.>
    ```
""")


class AgentPreflightError(RuntimeError):
    """An agent backend cannot run in this environment.

    Raised by the orchestrator before any stage executes when the selected
    agent's :meth:`AKMSAgent.preflight` reports a missing requirement. The
    message is the human-actionable reason (what is missing and how to
    install it) — callers can surface it verbatim.
    """


class AKMSAgent:
    """AKMS agent base class — sealed protocol + execution seam.

    The orchestrator constructs a fresh agent instance per task.

    Args:
        config: PropagationConfig for this repo.
        repo_root: Repository root path (required).
        model: Model string override.  Falls back to
            ``config.orchestrator.default_model``.
    """

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if "run" in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} must not override AKMSAgent.run(). "
                f"Override execute() instead."
            )

    def __init__(
        self,
        config: PropagationConfig,
        repo_root: str | Path,
        model: str | None = None,
    ):
        self.config = config
        self.repo_root = Path(repo_root)
        self.model = model or config.orchestrator.default_model

    # ── Environment preflight ────────────────────────────────────────

    def preflight(self) -> str | None:
        """Report whether this agent can run in the current environment.

        Returns ``None`` when the agent's execution backend is available, or
        a human-actionable reason string (what is missing and how to install
        it) when it is not. The orchestrator calls this once before the
        pipeline starts and aborts with :class:`AgentPreflightError` on a
        non-``None`` result — before any stage runs or any file is written.

        The check must be cheap and side-effect free: probe with
        :func:`importlib.util.find_spec` or :func:`shutil.which`; never
        import the backend itself.

        This base implementation checks the Claude Agent SDK, because
        :meth:`AKMSAgent.execute` drives it. Subclasses that use a different
        execution backend must override ``preflight()`` to check their own
        requirements (an SDK module, a binary on PATH, an endpoint setting).
        A subclass with no external requirements should return ``None``.
        """
        import importlib.util

        if importlib.util.find_spec("claude_agent_sdk") is None:
            return (
                "The default agent backend needs the Claude Agent SDK, which "
                'is not installed. Install it with: pip install "akms[agents]" '
                '(or "akms[orchestration]" for the complete embedded runtime).'
            )
        return None

    # ── Sealed protocol ──────────────────────────────────────────────

    async def run(self, task_json: dict) -> AgentMemory:
        """Entry point.  Not overridable.  Owns AKMS protocol lifecycle.

        Steps:
            1. Resolve loadout_path from task_json
            2. Read and parse loadout file → Loadout object
            3. Build system prompt: CLAUDE.md kernel + AgentMemory schema
               instructions (loadout delivered via file path, not system prompt)
            4. Call ``await self.execute(task_json, loadout, system_prompt)``
            5. Read AgentMemory file from expected path
            6. Parse and validate AgentMemory against schema
            7. Return parsed AgentMemory

        If ``execute()`` raises or the agent fails to write AgentMemory,
        a ``status: failed`` AgentMemory is written with error details.

        Args:
            task_json: Task assignment dict with at least ``task_id``,
                ``phase`` (or ``phase_id``), and ``loadout_path``.

        Returns:
            Validated AgentMemory instance.

        Raises:
            SchemaValidationError: If the written AgentMemory fails
                Pydantic validation (indicates an agent output bug).
        """
        task_id = task_json.get("task_id", task_json.get("id", "unknown"))
        loadout_path = task_json.get("loadout_path", "")

        # 1–2. Read and parse loadout
        loadout = self._read_loadout(loadout_path) if loadout_path else Loadout(path="")

        # 3. Build system prompt (no loadout content — per FR-L04 agents
        #    receive a file path to their loadout, not the content inline)
        system_prompt = self._build_system_prompt(loadout, task_json)

        # 4. Execute — the seam
        try:
            await self.execute(task_json, loadout, system_prompt)
        except Exception as exc:
            logger.error(
                "execute() failed for task %s: %s", task_id, exc, exc_info=True
            )
            return self._write_failed_memory(
                task_json, f"execute() raised: {type(exc).__name__}: {exc}"
            )

        # 5. Read AgentMemory from disk
        memory_path = self._expected_memory_path(task_json)
        if not memory_path.exists():
            return self._write_failed_memory(
                task_json, f"Agent did not write AgentMemory to {memory_path}"
            )

        # 6–7. Parse, validate, and return
        return self._parse_and_validate_memory(memory_path)

    # ── Protocol helpers (not overridable) ────────────────────────────

    def _read_loadout(self, path: str) -> Loadout:
        """Read and parse a loadout .md file into a Loadout dataclass."""
        loadout_path = Path(path)
        if not loadout_path.exists():
            logger.warning("Loadout file not found: %s", path)
            return Loadout(path=path)

        try:
            post = frontmatter.load(str(loadout_path))
            meta = dict(post.metadata)
            try:
                LoadoutHeader(**meta)
            except Exception as exc:
                logger.warning(
                    "Loadout %s failed LoadoutHeader validation (schema drift?): %s",
                    path,
                    exc,
                )
            return Loadout(
                path=path,
                task_id=meta.get("task_id", ""),
                phase=meta.get("phase", 0),
                graph_version=meta.get("graph_version", ""),
                seed_tags=meta.get("seed_tags", []),
                agent_role=meta.get("agent_role", "implementer"),
                node_count=meta.get("node_count", 0),
                loadout_mode=meta.get("loadout_mode", "routing"),
                available_context=meta.get("available_context", 0),
                qmd_available=meta.get("qmd_available", True),
                content=post.content,
            )
        except Exception as exc:
            logger.warning("Failed to parse loadout %s: %s", path, exc)
            return Loadout(path=path)

    def _build_system_prompt(self, loadout: Loadout, task_json: dict) -> str:
        """Assemble system prompt: CLAUDE.md kernel + AgentMemory instructions.

        The loadout content is NOT included here — per FR-L04 (§2.2, spec
        doc 02), agents receive a file path to their loadout.  The loadout
        path is communicated in the task prompt built by
        ``_build_task_prompt()``.
        """
        task_id = task_json.get("task_id", task_json.get("id", "unknown"))
        phase_id = task_json.get("phase_id", task_json.get("phase", 0))
        loadout_path = task_json.get("loadout_path", "")
        memory_path = self._expected_memory_path(task_json)

        parts: list[str] = []

        # CLAUDE.md kernel — persistent instructions for every agent
        claude_md = self.repo_root / "CLAUDE.md"
        if claude_md.exists():
            parts.append(claude_md.read_text(encoding="utf-8"))

        # AgentMemory schema + write instructions
        parts.append(
            _AGENT_MEMORY_INSTRUCTIONS.format(
                memory_path=memory_path,
                task_id=task_id,
                phase_id=phase_id,
                loadout_path=loadout_path,
            )
        )

        # Role-specific instructions injected by wave_dispatch / agent_configs
        system_additions = task_json.get("system_prompt_additions", "")
        if system_additions:
            parts.append(f"# Role-Specific Instructions\n\n{system_additions}")

        return "\n\n".join(parts)

    # Budget for the embedded phase diff in the user-turn prompt. Reviewers
    # can always open the full diff via Bash/git if they need more — this cap
    # keeps the prompt under control.  ~4 chars/token gives ~3.75k tokens.
    PHASE_DIFF_MAX_CHARS = 15_000

    def _build_task_prompt(self, task_json: dict) -> str:
        """Build the user-turn prompt from task JSON fields.

        Includes: task_id, title, objective, implementation_steps,
        success_metrics, phase diffs (for reviewers), and explicit
        instruction to write AgentMemory on completion. Also includes
        the loadout file path so the agent can read it via its Read tool.
        """
        task_id = task_json.get("task_id", task_json.get("id", "unknown"))
        title = task_json.get("title", task_json.get("task_description", ""))
        objective = task_json.get("objective", "")
        steps = task_json.get("implementation_steps", [])
        metrics = task_json.get("success_metrics", [])
        loadout_path = task_json.get("loadout_path", "")
        phase_diffs = task_json.get("phase_diffs", "") or ""

        parts = [f"# Task: {title}", f"Task ID: {task_id}"]

        if objective:
            parts.append(f"\n## Objective\n{objective}")

        if loadout_path:
            parts.append(
                f"\n## Knowledge Loadout\n"
                f"Read your AKMS knowledge loadout from: {loadout_path}"
            )

        task_instructions_path = task_json.get("task_instructions_path", "")
        if task_instructions_path:
            parts.append(
                f"\n## Task Instructions\n"
                f"Read detailed task decomposition instructions from: {task_instructions_path}"
            )

        if steps:
            parts.append("\n## Implementation Steps")
            for i, step in enumerate(steps, 1):
                parts.append(f"{i}. {step}")

        if metrics:
            parts.append("\n## Success Metrics")
            for m in metrics:
                parts.append(f"- {m}")

        # Forward briefing from the prior-phase PCD. The orchestrator
        # attaches the ephemeral zone of the previous phase's handoff PCD so
        # every subagent in phase N+1 sees assumptions, known_issues,
        # next_phase_warnings, and recommended_start before starting work.
        briefing = task_json.get("forward_briefing") or {}
        if isinstance(briefing, dict) and briefing:
            briefing_lines: list[str] = ["\n## Forward Briefing from Prior Phase"]
            warnings = briefing.get("next_phase_warnings")
            if isinstance(warnings, list) and warnings:
                briefing_lines.append("\n**Next-phase warnings:**")
                for w in warnings:
                    briefing_lines.append(f"- {w}")
            assumptions = briefing.get("assumptions")
            if isinstance(assumptions, list) and assumptions:
                briefing_lines.append("\n**Assumptions:**")
                for a in assumptions:
                    if isinstance(a, dict):
                        briefing_lines.append(
                            f"- {a.get('claim', '')} (risk: {a.get('risk_if_wrong', '')})"
                        )
                    else:
                        briefing_lines.append(f"- {a}")
            known = briefing.get("known_issues") or {}
            failing = known.get("failing_tests") if isinstance(known, dict) else None
            if isinstance(failing, list) and failing:
                briefing_lines.append("\n**Known failing tests:**")
                for ft in failing:
                    if isinstance(ft, dict):
                        briefing_lines.append(
                            f"- {ft.get('tests', '?')}: {ft.get('reason', '')}"
                        )
            rec = briefing.get("recommended_start")
            if rec:
                briefing_lines.append(f"\n**Recommended start:** {rec}")
            parts.append("\n".join(briefing_lines))

        #   # Reviewers receive the phase diff inline so they can actually review
        #           # the delta. Truncated to PHASE_DIFF_MAX_CHARS with a visible suffix so
        #           # the agent knows it must open the full diff via Bash if needed.
        if phase_diffs:
            diff_body = phase_diffs
            if len(diff_body) > self.PHASE_DIFF_MAX_CHARS:
                diff_body = (
                    diff_body[: self.PHASE_DIFF_MAX_CHARS]
                    + f"\n[... diff truncated to {self.PHASE_DIFF_MAX_CHARS} chars;"
                    " run `git diff` for the full delta]"
                )
            parts.append("\n## Phase Diffs\n```diff\n" + diff_body + "\n```")

        parts.append(
            "\n## Required Output\n"
            "On completion, write your AgentMemory file as specified in "
            "the system prompt instructions."
        )

        return "\n".join(parts)

    def _expected_memory_path(self, task_json: dict) -> Path:
        """knowledge/sessions/{task_id}.md"""
        task_id = task_json.get("task_id", task_json.get("id", "unknown"))
        return self.repo_root / "knowledge" / "sessions" / f"{task_id}.md"

    def _parse_and_validate_memory(self, path: Path) -> AgentMemory:
        """Read the AgentMemory file the agent wrote, parse YAML
        frontmatter, validate against AgentMemory schema.

        Raises:
            SchemaValidationError: If parsing or validation fails.
        """
        try:
            post = frontmatter.load(str(path))
            meta = dict(post.metadata)
        except Exception as exc:
            raise SchemaValidationError(
                f"Failed to parse AgentMemory frontmatter from {path}: {exc}",
                path=str(path),
            ) from exc

        try:
            memory = AgentMemory(**meta)
        except ValidationError as ve:
            raise SchemaValidationError(
                f"AgentMemory at {path} failed schema validation: {ve}",
                path=str(path),
            ) from ve

        return memory

    def _write_failed_memory(self, task_json: dict, reason: str) -> AgentMemory:
        """Write a minimal status: failed AgentMemory when the agent
        didn't produce one.  Ensures the pipeline always has a memory
        file to process.
        """
        task_id = task_json.get("task_id", task_json.get("id", "unknown"))
        phase_id = task_json.get("phase_id", task_json.get("phase", 0))
        loadout_path = task_json.get("loadout_path", "")

        memory = AgentMemory(
            task_id=task_id,
            task_description=task_json.get(
                "title", task_json.get("task_description", "")
            ),
            phase_id=int(phase_id),
            timestamp=datetime.now(),
            agent_model=self.model,
            loadout_used=loadout_path,
            status=TaskStatus.FAILED,
            tests_passed=0,
            tests_total=0,
            completion_notes=reason,
        )

        # Write to disk
        sessions_dir = self.repo_root / "knowledge" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        output_path = sessions_dir / f"{task_id}.md"

        memory_dict = memory.model_dump(mode="json")
        post = frontmatter.Post(
            content=f"\n## Task Notes\n\nFailed: {reason}\n",
            **memory_dict,
        )
        with open(output_path, "wb") as f:
            frontmatter.dump(post, f)

        logger.warning("Wrote failed AgentMemory to %s: %s", output_path, reason)
        return memory

    # ── Role-aware tool resolution (F-01c) ───────────────────────────

    def _resolve_allowed_tools(self, task_json: dict) -> list[str]:
        """Compute the allowed_tools list from task_json['tools'].

        Translates the declarative logical names in agent_configs.py
        (``file_edit``, ``search_mirror``, …) into the concrete SDK names
        via ``TOOL_NAME_MAP``. Legacy callers with an empty tools list get
        the ``BASELINE_ALLOWED_TOOLS`` fallback — which deliberately does
        NOT include Grep (FR-C05).

        The import is deferred inside a try block so tests that monkeypatch
        ``builtins.__import__`` to raise on unrelated module names (see
        tests/akms/test_agents_codex.py::test_codex_import_error_message)
        can still reach the ``from agents import …`` call downstream.
        """
        try:
            from akms.orchestrator.agent_configs import (
                BASELINE_ALLOWED_TOOLS,
                resolve_runtime_tools,
            )
        except ImportError:
            # If the registry itself is unavailable, fall back to a conservative
            # static allowlist (still Grep-free).
            return ["Read", "Write", "Edit", "MultiEdit", "Glob", "Bash"]

        logical = task_json.get("tools") or []
        if not logical:
            return list(BASELINE_ALLOWED_TOOLS)
        return resolve_runtime_tools(logical)

    # ── Execution seam ───────────────────────────────────────────────

    async def execute(
        self,
        task_json: dict,
        loadout: Loadout,
        system_prompt: str,
    ) -> None:
        """Override in subclasses to customize agent execution.

        Default: single-shot ``claude-agent-sdk`` ``query()`` with
        standard Claude Code tools.  The agent runs with file system tools
        in the repo working directory.  It performs the task and writes
        AgentMemory per the system prompt instructions.

        Projects override this method to add model tier selection,
        MCP servers, custom tools, hooks, or multi-turn
        ``ClaudeSDKClient`` sessions.

        Args:
            task_json: Full task assignment dict.
            loadout: Parsed loadout with metadata and content.
            system_prompt: Pre-assembled system prompt with CLAUDE.md
                kernel and AgentMemory write instructions.

        Returns:
            None.  AgentMemory is read from disk by ``run()``.

        Raises:
            Any exception — ``run()`` catches and writes failed memory.
        """
        try:
            from claude_agent_sdk import (  # type: ignore[import-untyped]
                ClaudeAgentOptions,
                ResultMessage,
                query,
            )
        except ImportError as exc:
            raise ImportError(
                "Agent execution requires the optional agent backends, which are "
                'not installed. Install them with: pip install "akms[agents]" '
                '(or "akms[orchestration]" for the complete embedded runtime).'
            ) from exc

        # F-01b / FR-Q05: register the AKMS MCP server so agents can invoke
        # the qmd-backed search tools that `TOOL_NAME_MAP` resolves to
        # (`mcp__akms__akms_search_nodes`, …). Without this registration the
        # MCP-named tools in `allowed_tools` are unreachable, regressing the
        # reviewer surface previously covered by Grep (FR-C05).
        from akms.orchestrator.mcp_tools import create_mcp_server

        akms_server = create_mcp_server(repo_root=self.repo_root)

        options = ClaudeAgentOptions(
            model=self.model,
            system_prompt=system_prompt,
            allowed_tools=self._resolve_allowed_tools(task_json),
            mcp_servers={
                "akms": {
                    "type": "sdk",
                    "name": "akms",
                    "instance": akms_server,
                },
            },
            permission_mode="acceptEdits",
            cwd=str(self.repo_root),
        )

        prompt = self._build_task_prompt(task_json)

        async for message in query(prompt=prompt, options=options):
            # Stream handling — log progress, detect errors.
            # The agent writes AgentMemory as part of its work.
            if isinstance(message, ResultMessage):
                if message.is_error:
                    raise RuntimeError(f"Agent run failed: {message.result}")
