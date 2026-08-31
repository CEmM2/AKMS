"""Reviewer context resolution from the actual task-local diff (A2-3).

Generates role-specific reviewer loadouts from files actually changed by a
task, while reporting required lessons that appear only after the
implementation diff is known.

Design rules
------------
* Changed paths come from an explicit sequence **or** a base/head git pair.
  A bare single-path string is rejected (Phase 1 canonicalisation).
* Empty diffs fall back to task-derived scope without failure.
* Pre-task required nodes (scope/deliverables only) are compared with the
  post-diff required set so callers can surface newly mandatory lessons.
* Reviewer roles (``code_reviewer``, ``physics_reviewer``) stay distinct via
  the ordinary advisory query profile.
* No LLM or network I/O — all work is offline and deterministic.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from akms.schema.models import AgentRole, LoadoutMode, PropagationConfig
from akms.task_context.models import TaskRouteIndex
from akms.task_context.query import TaskKnowledgeQueryResult
from akms.task_context.resolve import ResolvedSeeds
from akms.task_context.resolve_task_service import (
    ResolveTaskError,
    ResolveTaskResult,
    load_changed_paths_manifest,
    load_task_mapping,
    resolve_git_changed_paths,
    resolve_task,
)

logger = logging.getLogger(__name__)

ReviewerRole = Literal["code_reviewer", "physics_reviewer"]

_REVIEWER_ROLES = frozenset({"code_reviewer", "physics_reviewer"})


@dataclass(frozen=True)
class ReviewResolutionResult:
    """Outcome of one reviewer resolution pass.

    ``post_diff_only_required`` lists required node IDs that the actual diff
    introduced beyond the pre-task (scope/deliverable) required set.
    """

    status: Literal["ok", "error"]
    role: str
    empty_diff_fallback: bool = False
    changed_paths: tuple[str, ...] = ()
    pre_task_required: tuple[str, ...] = ()
    post_diff_required: tuple[str, ...] = ()
    post_diff_only_required: tuple[str, ...] = ()
    coactivated_count: int = 0
    advisory_count: int = 0
    node_count: int = 0
    fingerprint: str | None = None
    loadout_path: str | None = None
    manifest_path: str | None = None
    graph_version: str | None = None
    route_index_hash: str | None = None
    task_id: str | None = None
    phase: int | None = None
    error: str | None = None
    error_code: str | None = None
    # In-process handles
    pre_task_result: ResolveTaskResult | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    post_diff_result: ResolveTaskResult | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    query_result: TaskKnowledgeQueryResult | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    resolved_seeds: ResolvedSeeds | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def to_json_dict(self) -> dict[str, Any]:
        payload = {
            "advisory_count": self.advisory_count,
            "changed_paths": list(self.changed_paths),
            "coactivated_count": self.coactivated_count,
            "empty_diff_fallback": self.empty_diff_fallback,
            "error": self.error,
            "error_code": self.error_code,
            "fingerprint": self.fingerprint,
            "graph_version": self.graph_version,
            "loadout_path": self.loadout_path,
            "manifest_path": self.manifest_path,
            "node_count": self.node_count,
            "phase": self.phase,
            "post_diff_only_required": list(self.post_diff_only_required),
            "post_diff_required": list(self.post_diff_required),
            "pre_task_required": list(self.pre_task_required),
            "role": self.role,
            "route_index_hash": self.route_index_hash,
            "status": self.status,
            "task_id": self.task_id,
        }
        return {
            key: value
            for key, value in payload.items()
            if value is not None
            or key
            in {
                "advisory_count",
                "changed_paths",
                "coactivated_count",
                "empty_diff_fallback",
                "node_count",
                "post_diff_only_required",
                "post_diff_required",
                "pre_task_required",
                "status",
            }
        }


def _as_reviewer_role(value: AgentRole | str) -> str:
    if isinstance(value, AgentRole):
        text = value.value
    else:
        text = str(value).strip()
    if text not in _REVIEWER_ROLES:
        raise ResolveTaskError(
            f"Reviewer role must be one of {sorted(_REVIEWER_ROLES)}; got {text!r}",
            code="invalid_role",
        )
    return text


def _required_ids(result: ResolveTaskResult) -> tuple[str, ...]:
    if result.query_result is None:
        return ()
    return result.query_result.required_node_ids


def resolve_changed_paths_for_review(
    *,
    repo_root: str | Path,
    changed_paths: Mapping[str, Any] | Sequence[str] | str | Path | None = None,
    base: str | None = None,
    head: str | None = None,
) -> tuple[str, ...]:
    """Resolve the task-local changed-path set for reviewer context.

    Raises :class:`ResolveTaskError` on invalid inputs (including bare strings).
    """
    explicit = load_changed_paths_manifest(changed_paths)
    if base is not None and explicit:
        raise ResolveTaskError(
            "Provide either base/head or changed_paths, not both",
            code="ambiguous_diff_inputs",
        )
    if base is not None:
        return resolve_git_changed_paths(
            repo_root,
            base=base,
            head=head or "HEAD",
        )
    return explicit


def resolve_reviewer_context(
    *,
    repo_root: str | Path,
    task: Mapping[str, Any] | str | Path,
    route_index: TaskRouteIndex | Mapping[str, Any] | str | Path,
    agent_role: AgentRole | str = AgentRole.CODE_REVIEWER,
    changed_paths: Mapping[str, Any] | Sequence[str] | str | Path | None = None,
    base: str | None = None,
    head: str | None = None,
    graph_path: str | Path | None = None,
    loadout_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
    mode: LoadoutMode | str = LoadoutMode.ROUTING,
    available_context: int = 0,
    max_depth: int = 2,
    phase: int | None = None,
    config: PropagationConfig | None = None,
    write_artifacts: bool = True,
) -> ReviewResolutionResult:
    """Resolve reviewer knowledge from the actual task-local diff.

    Parameters
    ----------
    agent_role:
        Must be ``code_reviewer`` or ``physics_reviewer``.
    changed_paths / base / head:
        Source of the actual implementation diff. Empty results fall back to
        the task's declared scope/deliverables without failure.
    write_artifacts:
        When True (default), write the post-diff reviewer loadout and
        resolution manifest. Pre-task resolution is always in-memory only.

    Returns
    -------
    ReviewResolutionResult
        Includes ``post_diff_only_required`` — required nodes introduced solely
        by the actual diff relative to the pre-task scope resolution.
    """
    try:
        role = _as_reviewer_role(agent_role)
        root = Path(repo_root).resolve()
        task_mapping = load_task_mapping(task)

        # ── Actual diff (or empty → fallback) ────────────────────────
        try:
            effective_paths = resolve_changed_paths_for_review(
                repo_root=root,
                changed_paths=changed_paths,
                base=base,
                head=head,
            )
        except ResolveTaskError as exc:
            return ReviewResolutionResult(
                status="error",
                role=role,
                error=str(exc),
                error_code=exc.code,
                task_id=str(task_mapping.get("task_id") or "") or None,
            )

        empty_diff = len(effective_paths) == 0

        # ── Pre-task required set (scope/deliverables only; no extra diff) ──
        # Strip any task-embedded changed_files so "pre-task" is pure declaration.
        pre_task_mapping = dict(task_mapping)
        pre_task_mapping.pop("changed_files", None)

        pre_result = resolve_task(
            repo_root=root,
            task=pre_task_mapping,
            route_index=route_index,
            agent_role=role,
            changed_paths=None,
            graph_path=graph_path,
            mode=mode,
            available_context=available_context,
            max_depth=max_depth,
            phase=phase,
            config=config,
            write_artifacts=False,
        )
        if pre_result.status != "ok":
            return ReviewResolutionResult(
                status="error",
                role=role,
                empty_diff_fallback=empty_diff,
                changed_paths=effective_paths,
                error=pre_result.error,
                error_code=pre_result.error_code,
                task_id=pre_result.task_id,
                phase=pre_result.phase,
                pre_task_result=pre_result,
            )
        pre_required = _required_ids(pre_result)

        post_changed = None if empty_diff else effective_paths
        post_result = resolve_task(
            repo_root=root,
            task=pre_task_mapping,
            route_index=route_index,
            agent_role=role,
            changed_paths=post_changed,
            graph_path=graph_path,
            loadout_path=loadout_path,
            manifest_path=manifest_path,
            mode=mode,
            available_context=available_context,
            max_depth=max_depth,
            phase=phase,
            config=config,
            write_artifacts=write_artifacts,
        )
        if post_result.status != "ok":
            return ReviewResolutionResult(
                status="error",
                role=role,
                empty_diff_fallback=empty_diff,
                changed_paths=effective_paths,
                pre_task_required=pre_required,
                error=post_result.error,
                error_code=post_result.error_code,
                task_id=post_result.task_id or pre_result.task_id,
                phase=post_result.phase or pre_result.phase,
                pre_task_result=pre_result,
                post_diff_result=post_result,
            )

        post_required = _required_ids(post_result)
        post_only = tuple(sorted(set(post_required) - set(pre_required)))

        return ReviewResolutionResult(
            status="ok",
            role=role,
            empty_diff_fallback=empty_diff,
            changed_paths=effective_paths,
            pre_task_required=pre_required,
            post_diff_required=post_required,
            post_diff_only_required=post_only,
            coactivated_count=post_result.coactivated_count,
            advisory_count=post_result.advisory_count,
            node_count=post_result.node_count,
            fingerprint=post_result.fingerprint,
            loadout_path=post_result.loadout_path,
            manifest_path=post_result.manifest_path,
            graph_version=post_result.graph_version,
            route_index_hash=post_result.route_index_hash,
            task_id=post_result.task_id,
            phase=post_result.phase,
            pre_task_result=pre_result,
            post_diff_result=post_result,
            query_result=post_result.query_result,
            resolved_seeds=post_result.resolved_seeds,
        )
    except ResolveTaskError as exc:
        return ReviewResolutionResult(
            status="error",
            role=str(agent_role),
            error=str(exc),
            error_code=exc.code,
        )
    except Exception as exc:
        logger.exception("resolve_reviewer_context failed")
        return ReviewResolutionResult(
            status="error",
            role=str(agent_role),
            error=str(exc),
            error_code="review_resolve_error",
        )


__all__ = [
    "ReviewResolutionResult",
    "ReviewerRole",
    "resolve_changed_paths_for_review",
    "resolve_reviewer_context",
]
