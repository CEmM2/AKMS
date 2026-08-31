"""Deterministic branch workflow helpers for phased execution."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


def _normalize_plan_name(plan_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", plan_name.strip()).strip("-").lower()
    return cleaned or "plan"


def phase_branch_name(plan_name: str, phase: int) -> str:
    """Build a deterministic phase branch name."""
    return f"{_normalize_plan_name(plan_name)}_phase-{phase}"


def parent_branch(
    plan_name: str,
    base_branch: str,
    phase: int,
    phase_order: list[int] | None = None,
) -> str:
    """Resolve parent branch for a phase branch.

    When *phase_order* is provided the parent is the branch for the
    preceding entry in that list — not ``phase - 1``.  This handles
    non-contiguous phase numbering correctly.
    """
    if phase_order:
        try:
            idx = phase_order.index(phase)
        except ValueError:
            idx = 0
        if idx <= 0:
            return base_branch
        return phase_branch_name(plan_name, phase_order[idx - 1])
    # Legacy contiguous fallback
    if phase <= 1:
        return base_branch
    return phase_branch_name(plan_name, phase - 1)


def reverse_merge_plan(
    plan_name: str,
    total_phases: int,
    base_branch: str,
    phase_order: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Create deterministic reverse-merge operations for finalize.

    When *phase_order* is provided the merge sequence walks the actual
    phase list in reverse rather than assuming ``range(total_phases, 0, -1)``.
    """
    phases = list(phase_order) if phase_order else list(range(1, total_phases + 1))
    if not phases:
        return []

    ops: list[dict[str, Any]] = []
    for i in range(len(phases) - 1, -1, -1):
        phase = phases[i]
        source = phase_branch_name(plan_name, phase)
        target = base_branch if i == 0 else phase_branch_name(plan_name, phases[i - 1])
        ops.append(
            {
                "name": f"checkout-{target}",
                "cmd": ["git", "checkout", target],
            }
        )
        ops.append(
            {
                "name": f"merge-{source}-into-{target}",
                "cmd": ["git", "merge", "--no-ff", source],
            }
        )
    return ops


def execute_git_ops(
    ops: list[dict[str, Any]],
    apply: bool = False,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Execute planned git operations or return dry-run plan."""
    repo_dir = Path(repo_root) if repo_root is not None else None
    result: dict[str, Any] = {
        "applied": apply,
        "planned_ops": ops,
        "executed_ops": [],
    }
    if not apply:
        return result

    executed_ops: list[dict[str, Any]] = []
    for op in ops:
        cmd = op["cmd"]
        proc = subprocess.run(
            cmd,
            cwd=str(repo_dir) if repo_dir is not None else None,
            check=False,
            capture_output=True,
            text=True,
        )
        executed = {
            "name": op.get("name", ""),
            "cmd": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
        executed_ops.append(executed)
        if proc.returncode != 0:
            result["executed_ops"] = executed_ops
            result["failed_op"] = executed
            raise RuntimeError(
                f"git op failed ({executed['name']}): {' '.join(cmd)}\n{proc.stderr}"
            )

    result["executed_ops"] = executed_ops
    return result
