"""pcd_builder.py — PCD aggregation and handoff writer.

Two pure-Python deterministic helpers:

- ``build_pcd(memories, phase, git_state)`` aggregates a list of typed
  ``AgentMemory`` instances (one per task) into a validated ``PCD`` instance.
  The persistent zone is the union of per-memory persistent zones; the
  ephemeral zone is derived from the ``git_state`` dict that the orchestrator
  passes in (files_modified + branch + plan_file + forward briefing).

- ``write_handoff(pcd, repo_root)`` writes the PCD to
  ``knowledge/sessions/handoff_phase_{N}.md`` using python-frontmatter so the
  file round-trips cleanly through the existing validators.

No LLM calls — all aggregation is pure field merging.
"""

from __future__ import annotations

import logging
from datetime import date as _date
from datetime import datetime
from pathlib import Path
from typing import Any

import frontmatter

from akms.schema.models import (
    AgentMemory,
    KnownIssues,
    Lessons,
    OverallTestStatus,
    PCD,
    PCDTaskSummary,
)

logger = logging.getLogger(__name__)


def _aggregate_lessons(memories: list[AgentMemory]) -> Lessons:
    """Merge Lessons across memories (preserve order, dedup exact duplicates)."""
    worked: list[str] = []
    failed: list[Any] = []
    for m in memories:
        l = m.lessons
        for w in l.worked if l else []:
            if w not in worked:
                worked.append(w)
        for f in l.failed if l else []:
            if f not in failed:
                failed.append(f)
    return Lessons(worked=worked, failed=failed)


def _aggregate_overall_test_status(
    memories: list[AgentMemory],
) -> OverallTestStatus | None:
    """Sum tests_passed / tests_total across memories."""
    if not memories:
        return None
    passing = sum(int(m.tests_passed or 0) for m in memories)
    total = sum(int(m.tests_total or 0) for m in memories)
    if total == 0:
        return None
    return OverallTestStatus(
        dedicated_passing=passing,
        dedicated_total=total,
    )


def _memory_to_task_summary(m: AgentMemory) -> PCDTaskSummary:
    return PCDTaskSummary(
        task_id=m.task_id,
        title=m.task_description or m.task_id,
        commit=m.commit,
        tests_passed=int(m.tests_passed or 0),
        tests_total=int(m.tests_total or 0),
        status=m.status,
        agent_model=m.agent_model or "",
    )


def build_pcd(
    memories: list[AgentMemory],
    phase: int,
    git_state: dict | None = None,
) -> PCD:
    """Aggregate per-task ``AgentMemory`` instances into a ``PCD``.

    ``git_state`` may include:
      - ``branch``: current phase branch name (str).
      - ``plan_file``: path to the plan markdown (str).
      - ``files_modified``: list[{"path", "changes"}] from generate_mirror input.
      - ``files_created`` / ``files_deleted``: similar shape.
      - ``loadout_used``: reference loadout path (str).
      - ``next_phase_warnings``: list[str]; a default is supplied when empty
        because the PCD schema requires ≥1 entry.
      - ``assumptions``, ``known_issues``, ``recommended_start``: optional
        ephemeral-zone inputs (pass-through).

    The builder is deterministic: memories are sorted by ``task_id`` before
    aggregation so byte-identical outputs are guaranteed for the same inputs.
    """
    git_state = dict(git_state or {})
    # Deterministic ordering regardless of caller input order.
    ordered = sorted(list(memories or []), key=lambda m: m.task_id)

    # Persistent zone — union across memories (preserve duplicates per NFR-C05).
    nodes_used = [n for m in ordered for n in (m.nodes_used or [])]
    nodes_missing = [n for m in ordered for n in (m.nodes_missing or [])]
    pitfalls_discovered = [p for m in ordered for p in (m.pitfalls_discovered or [])]
    new_knowledge = [k for m in ordered for k in (m.new_knowledge or [])]

    # Ephemeral zone defaults — PCD schema requires next_phase_warnings ≥ 1.
    next_phase_warnings = list(git_state.get("next_phase_warnings") or [])
    if not next_phase_warnings:
        next_phase_warnings = ["No warnings from phase execution."]

    pcd = PCD(
        phase_id=phase,
        plan_file=str(git_state.get("plan_file", "")),
        branch=str(git_state.get("branch", "")),
        date=git_state.get("date") or _date.today(),
        loadout_used=str(git_state.get("loadout_used", "")),
        tasks=[_memory_to_task_summary(m) for m in ordered],
        overall_test_status=_aggregate_overall_test_status(ordered),
        files_created=list(git_state.get("files_created") or []),
        files_modified=list(git_state.get("files_modified") or []),
        files_deleted=list(git_state.get("files_deleted") or []),
        interfaces_added=list(git_state.get("interfaces_added") or []),
        taichi_fields_added=list(git_state.get("taichi_fields_added") or []),
        assumptions=list(git_state.get("assumptions") or []),
        known_issues=git_state.get("known_issues") or KnownIssues(),
        next_phase_warnings=next_phase_warnings,
        recommended_start=git_state.get("recommended_start"),
        nodes_used=nodes_used,
        nodes_missing=nodes_missing,
        lessons=_aggregate_lessons(ordered),
        pitfalls_discovered=pitfalls_discovered,
        new_knowledge=new_knowledge,
    )
    return pcd


def _default_handoff_path(repo_root: Path, phase: int) -> Path:
    return repo_root / "knowledge" / "sessions" / f"handoff_phase_{phase}.md"


def write_handoff(
    pcd: PCD,
    repo_root: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    """Serialize a ``PCD`` into a handoff markdown file.

    The file layout mirrors AgentMemory files so existing parsers (the PCD
    validators + qmd search_sessions) see consistent shape:

      ---
      <PCD model_dump as YAML frontmatter>
      ---
      ## Task Notes

      <prose: per-task summary table + warnings block>

    Returns the absolute Path of the file that was written.
    """
    repo_root = Path(repo_root)
    target = (
        Path(output_path)
        if output_path
        else _default_handoff_path(repo_root, pcd.phase_id)
    )
    target.parent.mkdir(parents=True, exist_ok=True)

    meta = pcd.model_dump(mode="json")
    # Date fields round-trip cleaner when stored as iso strings; Pydantic
    # already does this for `date` via model_dump(mode="json").
    body_lines: list[str] = [
        "## Phase Completion Document",
        "",
        f"**Phase:** {pcd.phase_id}",
        f"**Branch:** {pcd.branch}",
        f"**Plan:** {pcd.plan_file}",
        f"**Date:** {pcd.date.isoformat()}",
        "",
        "### Tasks",
    ]
    if pcd.tasks:
        for t in pcd.tasks:
            body_lines.append(
                f"- `{t.task_id}` ({t.status.value if hasattr(t.status, 'value') else t.status}): "
                f"{t.title} — {t.tests_passed}/{t.tests_total} tests"
            )
    else:
        body_lines.append("_(no task summaries)_")

    body_lines += ["", "### Next-phase warnings"]
    for w in pcd.next_phase_warnings:
        body_lines.append(f"- {w}")

    if pcd.recommended_start:
        body_lines += ["", f"### Recommended start\n\n{pcd.recommended_start}"]

    body = "\n".join(body_lines) + "\n"
    post = frontmatter.Post(content=body, **meta)
    with open(target, "wb") as f:
        frontmatter.dump(post, f)
    logger.info("Handoff PCD written to %s", target)
    return target
