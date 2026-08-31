"""Deterministic task-knowledge resolution service (CLI + MCP shared core).

This module is the single implementation behind ``akms resolve-task`` and the
optional ``akms_resolve_task`` MCP tool. It is intentionally offline: no LLM
calls, no network I/O. Graph and route inputs are loaded from the local
filesystem only.

Public entry points:

* :func:`resolve_task` — full resolve → loadout + manifest write
* :func:`load_task_mapping` — validate and load a task JSON mapping
* :func:`ResolveTaskResult` — stable machine-readable result contract
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import networkx as nx

from akms.graph.build_graph import build_graph, load_graph
from akms.graph.generate_loadout import generate_loadout
from akms.graph.qmd_cache import compute_graph_version
from akms.schema.models import AgentRole, LoadoutMode, PropagationConfig
from akms.schema.validators import parse_propagation_config
from akms.task_context.manifest import (
    RESOLUTION_RESOLVER_VERSION,
    ResolutionManifest,
    create_resolution_manifest,
    write_resolution_manifest,
)
from akms.task_context.models import TaskRouteIndex
from akms.task_context.query import (
    RequiredNodeUnavailableError,
    TaskKnowledgeQueryResult,
    query_task_knowledge,
)
from akms.task_context.resolve import ResolvedSeeds, TaskSeeds, resolve_task_seeds
from akms.task_context.routes import parse_route_index, validate_route_index_nodes

logger = logging.getLogger(__name__)

ResolveStatus = Literal["ok", "error"]

_ROLE_VALUES = frozenset(role.value for role in AgentRole)


@dataclass(frozen=True)
class ResolveTaskResult:
    """Stable machine-readable resolution result.

    Serialised to JSON with sorted keys for CLI stdout and MCP tool returns.
    """

    status: ResolveStatus
    loadout_path: str | None = None
    manifest_path: str | None = None
    fingerprint: str | None = None
    graph_version: str | None = None
    route_index_hash: str | None = None
    required_count: int = 0
    coactivated_count: int = 0
    advisory_count: int = 0
    node_count: int = 0
    role: str | None = None
    task_id: str | None = None
    phase: int | None = None
    mode: str | None = None
    changed_paths: tuple[str, ...] = ()
    error: str | None = None
    error_code: str | None = None
    # Non-serialised convenience handles for in-process callers.
    query_result: TaskKnowledgeQueryResult | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    manifest: ResolutionManifest | None = field(
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
        """Return a JSON-serialisable dict (excludes non-serial fields)."""
        payload = {
            "advisory_count": self.advisory_count,
            "changed_paths": list(self.changed_paths),
            "coactivated_count": self.coactivated_count,
            "error": self.error,
            "error_code": self.error_code,
            "fingerprint": self.fingerprint,
            "graph_version": self.graph_version,
            "loadout_path": self.loadout_path,
            "manifest_path": self.manifest_path,
            "mode": self.mode,
            "node_count": self.node_count,
            "phase": self.phase,
            "required_count": self.required_count,
            "role": self.role,
            "route_index_hash": self.route_index_hash,
            "status": self.status,
            "task_id": self.task_id,
        }
        # Drop None values only for optional error fields to keep the success
        # contract compact while remaining stable for consumers that check keys.
        return {
            key: value
            for key, value in payload.items()
            if value is not None
            or key
            in {
                "advisory_count",
                "changed_paths",
                "coactivated_count",
                "node_count",
                "required_count",
                "status",
            }
        }


class ResolveTaskError(ValueError):
    """Input or resolution failure with a stable machine-readable code."""

    def __init__(self, message: str, *, code: str = "resolve_error"):
        self.code = code
        super().__init__(message)


def _as_role(value: AgentRole | str) -> str:
    if isinstance(value, AgentRole):
        return value.value
    text = str(value).strip()
    if text not in _ROLE_VALUES:
        raise ResolveTaskError(
            f"Invalid agent role {text!r}; expected one of "
            + ", ".join(sorted(_ROLE_VALUES)),
            code="invalid_role",
        )
    return text


def _require_sequence(
    value: object,
    *,
    field_name: str,
) -> tuple[str, ...]:
    """Reject bare strings so a single path cannot be treated as a char sequence.

    Phase 1 canonicalisation rule: changed paths must be a sequence of strings,
    never a lone string (which would iterate character-by-character).
    """
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise ResolveTaskError(
            f"{field_name} must be a sequence of path strings, not a bare string",
            code="invalid_changed_paths",
        )
    if not isinstance(value, Sequence):
        raise ResolveTaskError(
            f"{field_name} must be a sequence of path strings",
            code="invalid_changed_paths",
        )
    paths: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ResolveTaskError(
                f"{field_name} entries must be strings",
                code="invalid_changed_paths",
            )
        text = item.strip()
        if text:
            paths.append(text)
    return tuple(paths)


def load_task_mapping(source: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    """Load and lightly validate a task JSON mapping."""
    if isinstance(source, Mapping):
        task = dict(source)
    else:
        path = Path(source)
        if not path.exists():
            raise ResolveTaskError(
                f"Task JSON not found: {path}",
                code="task_not_found",
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ResolveTaskError(
                f"Task JSON is not valid JSON: {exc}",
                code="invalid_task_json",
            ) from exc
        if not isinstance(payload, Mapping):
            raise ResolveTaskError(
                "Task JSON root must be an object",
                code="invalid_task_json",
            )
        task = dict(payload)

    task_id = str(task.get("task_id") or task.get("id") or "").strip()
    if not task_id:
        raise ResolveTaskError(
            "Task JSON requires a non-empty 'task_id' (or 'id') field",
            code="invalid_task_json",
        )
    if task_id in {".", ".."} or "/" in task_id or "\\" in task_id:
        raise ResolveTaskError(
            "task_id must be a non-empty identifier without path separators",
            code="invalid_task_id",
        )
    task["task_id"] = task_id
    return task


def load_changed_paths_manifest(
    source: Mapping[str, Any] | Sequence[str] | str | Path | None,
) -> tuple[str, ...]:
    """Load an explicit changed-path list from JSON or an in-memory sequence.

    Accepted shapes:
    * ``["src/a.py", "src/b.py"]``
    * ``{"changed_paths": [...]}`` / ``{"changed_files": [...]}`` / ``{"paths": [...]}``
    """
    if source is None:
        return ()
    if isinstance(source, (str, bytes)) and not isinstance(source, Path):
        # File path or raw string — if it looks like a path that exists, load it.
        path = Path(source)
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ResolveTaskError(
                    f"Changed-paths JSON is not valid JSON: {exc}",
                    code="invalid_changed_paths",
                ) from exc
            return load_changed_paths_manifest(payload)
        raise ResolveTaskError(
            "changed_paths must be a sequence or a JSON file path; "
            "a bare string is not a valid single-path input",
            code="invalid_changed_paths",
        )
    if isinstance(source, Path):
        if not source.exists():
            raise ResolveTaskError(
                f"Changed-paths file not found: {source}",
                code="invalid_changed_paths",
            )
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ResolveTaskError(
                f"Changed-paths JSON is not valid JSON: {exc}",
                code="invalid_changed_paths",
            ) from exc
        return load_changed_paths_manifest(payload)
    if isinstance(source, Mapping):
        for key in ("changed_paths", "changed_files", "paths"):
            if key in source:
                return _require_sequence(source[key], field_name=key)
        raise ResolveTaskError(
            "Changed-paths object requires 'changed_paths', 'changed_files', or 'paths'",
            code="invalid_changed_paths",
        )
    return _require_sequence(source, field_name="changed_paths")


def resolve_git_changed_paths(
    repo_root: str | Path,
    *,
    base: str,
    head: str = "HEAD",
) -> tuple[str, ...]:
    """Return repository-relative paths changed between ``base`` and ``head``.

    Uses ``git diff --name-only``. Failures raise :class:`ResolveTaskError`
    (callers that want soft fallback should catch it).
    """
    root = Path(repo_root)
    base_text = str(base).strip()
    head_text = str(head).strip() or "HEAD"
    if not base_text:
        raise ResolveTaskError("base revision must not be empty", code="invalid_diff")
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_text}...{head_text}"],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=30,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ResolveTaskError(
            "git is not available to resolve base/head changed paths",
            code="git_unavailable",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ResolveTaskError(
            "git diff timed out while resolving changed paths",
            code="git_timeout",
        ) from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ResolveTaskError(
            f"git diff failed for {base_text}...{head_text}: {detail}",
            code="git_diff_failed",
        )
    paths = tuple(
        sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})
    )
    return paths


def _load_propagation_config(
    repo_root: Path,
    config: PropagationConfig | None,
) -> PropagationConfig:
    if config is not None:
        return config
    config_path = repo_root / "knowledge" / "graph" / "propagation_config.yaml"
    if config_path.exists():
        return parse_propagation_config(config_path)
    return PropagationConfig()


def _load_graph(
    repo_root: Path,
    graph_path: str | Path | None,
    config: PropagationConfig,
) -> tuple[nx.DiGraph, Path]:
    default = repo_root / "knowledge" / "graph" / "graph.json"
    path = Path(graph_path) if graph_path is not None else default
    if not path.is_absolute():
        path = repo_root / path
    if path.exists():
        return load_graph(path), path
    if graph_path is not None:
        raise ResolveTaskError(
            f"Graph file not found: {path}",
            code="graph_not_found",
        )
    graph = build_graph(repo_root, output_path=path, config=config)
    return graph, path


def _route_index_hash(route_index: TaskRouteIndex) -> str:
    """Fingerprint the canonical route index for the resolution manifest."""
    # Prefer the declared source_hash when it already looks like a digest;
    # always also bind the canonical JSON so empty/stub hashes cannot collide.
    digest = hashlib.sha256(route_index.canonical_json().encode("utf-8")).hexdigest()
    return digest


def _default_paths(
    repo_root: Path,
    *,
    task_id: str,
    phase: int,
    role: str,
    loadout_path: str | Path | None,
    manifest_path: str | Path | None,
) -> tuple[Path, Path]:
    loadouts_dir = repo_root / "knowledge" / "loadouts"
    manifests_dir = repo_root / "knowledge" / "resolution-manifests"
    if loadout_path is not None:
        out_loadout = Path(loadout_path)
        if not out_loadout.is_absolute():
            out_loadout = repo_root / out_loadout
    else:
        out_loadout = loadouts_dir / f"{phase}-{task_id}-{role}-loadout.md"

    if manifest_path is not None:
        out_manifest = Path(manifest_path)
        if not out_manifest.is_absolute():
            out_manifest = repo_root / out_manifest
    else:
        out_manifest = manifests_dir / f"{phase}-{task_id}-{role}-manifest.json"
    return out_loadout, out_manifest


def resolve_task(
    *,
    repo_root: str | Path,
    task: Mapping[str, Any] | str | Path,
    route_index: TaskRouteIndex | Mapping[str, Any] | str | Path,
    agent_role: AgentRole | str = AgentRole.IMPLEMENTER,
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
) -> ResolveTaskResult:
    """Resolve exact + advisory task knowledge and write loadout + manifest.

    Parameters
    ----------
    repo_root:
        Repository root used for graph, loadout, and content resolution.
    task:
        Task JSON mapping or path to a task JSON file.
    route_index:
        Parsed :class:`TaskRouteIndex`, mapping, or path to a route index file.
    agent_role:
        Role profile for advisory query filters.
    changed_paths:
        Explicit sequence of repository-relative paths (or a JSON file /
        mapping containing such a sequence). A bare path string is rejected.
    base, head:
        Optional git revisions. When ``base`` is set, changed paths are taken
        from ``git diff --name-only base...head`` (``head`` defaults to HEAD).
        Mutually exclusive with a non-empty ``changed_paths`` input.
    graph_path:
        Optional compiled graph path (default ``knowledge/graph/graph.json``).
    loadout_path, manifest_path:
        Optional output paths (relative paths resolve against ``repo_root``).
    mode:
        Loadout content mode (``routing`` or ``full``).
    write_artifacts:
        When False, compute results in memory without writing files (tests).

    Returns
    -------
    ResolveTaskResult
        Stable counts, paths, fingerprint, and status. On recoverable input
        validation failure this still returns ``status="error"`` rather than
        raising, so CLI/MCP adapters can print pure JSON.
    """
    try:
        root = Path(repo_root).resolve()
        if not root.exists():
            raise ResolveTaskError(
                f"Repository root does not exist: {root}",
                code="repo_not_found",
            )

        task_mapping = load_task_mapping(task)
        task_id = str(task_mapping["task_id"])
        role = _as_role(agent_role)
        resolved_phase = int(
            phase if phase is not None else task_mapping.get("phase") or 1
        )
        if resolved_phase < 0:
            raise ResolveTaskError("phase must be non-negative", code="invalid_phase")

        # ── Changed paths ────────────────────────────────────────────
        explicit_paths = load_changed_paths_manifest(changed_paths)
        if base is not None and explicit_paths:
            raise ResolveTaskError(
                "Provide either base/head or changed_paths, not both",
                code="ambiguous_diff_inputs",
            )
        if base is not None:
            effective_paths = resolve_git_changed_paths(
                root,
                base=base,
                head=head or "HEAD",
            )
        else:
            effective_paths = explicit_paths

        # ── Graph + config ───────────────────────────────────────────
        prop_config = _load_propagation_config(root, config)
        graph, graph_file = _load_graph(root, graph_path, prop_config)
        graph_version = compute_graph_version(graph_file)

        # ── Route index ──────────────────────────────────────────────
        parsed_routes = parse_route_index(route_index, graph=graph)
        validate_route_index_nodes(parsed_routes, graph)
        route_hash = _route_index_hash(parsed_routes)

        # ── Seed resolution + query ──────────────────────────────────
        seeds = TaskSeeds.from_task(task_mapping, changed_files=effective_paths)
        resolved = resolve_task_seeds(
            graph,
            seeds,
            route_index=parsed_routes,
            changed_files=None,  # already folded into seeds
        )
        query_result = query_task_knowledge(
            graph,
            resolved,
            role,
            config=prop_config,
            max_depth=max_depth,
        )
        # changed_files already folded into ``seeds``; do not pass them again
        # or the fingerprint boundary would double-count.
        manifest = create_resolution_manifest(
            task=seeds,
            resolved_seeds=resolved,
            query_result=query_result,
            agent_role=role,
            graph_version=graph_version,
            route_index_hash=route_hash,
        )

        out_loadout, out_manifest = _default_paths(
            root,
            task_id=task_id,
            phase=resolved_phase,
            role=role,
            loadout_path=loadout_path,
            manifest_path=manifest_path,
        )

        mode_str = mode.value if isinstance(mode, LoadoutMode) else str(mode)

        if write_artifacts:
            write_resolution_manifest(out_manifest, manifest)
            generate_loadout(
                G=graph,
                ranked_nodes=[],
                task_id=task_id,
                phase=resolved_phase,
                graph_version=graph_version,
                seed_tags=list(resolved.advisory_tags),
                agent_role=role,
                mode=mode_str,
                available_context=available_context,
                config=prop_config,
                output_path=out_loadout,
                repo_root=root,
                task_knowledge=query_result,
                resolution_manifest=manifest,
            )

        return ResolveTaskResult(
            status="ok",
            loadout_path=str(out_loadout) if write_artifacts else None,
            manifest_path=str(out_manifest) if write_artifacts else None,
            fingerprint=manifest.fingerprint,
            graph_version=graph_version,
            route_index_hash=route_hash,
            required_count=len(query_result.required_node_ids),
            coactivated_count=len(query_result.coactivated_node_ids),
            advisory_count=len(query_result.advisory_node_ids),
            node_count=len(query_result.selections),
            role=role,
            task_id=task_id,
            phase=resolved_phase,
            mode=mode_str,
            changed_paths=effective_paths,
            query_result=query_result,
            manifest=manifest,
            resolved_seeds=resolved,
        )
    except ResolveTaskError as exc:
        logger.debug("resolve_task input error: %s", exc)
        return ResolveTaskResult(
            status="error",
            error=str(exc),
            error_code=exc.code,
        )
    except RequiredNodeUnavailableError as exc:
        logger.debug("resolve_task required-node failure: %s", exc)
        return ResolveTaskResult(
            status="error",
            error=str(exc),
            error_code="required_node_unavailable",
        )
    except Exception as exc:
        # Fail closed with a structured error rather than leaking traces to JSON.
        logger.exception("resolve_task failed")
        return ResolveTaskResult(
            status="error",
            error=str(exc),
            error_code="resolve_error",
        )


# Re-export for type checkers / callers that want the dict form without importing
# dataclasses machinery.
def resolve_task_as_dict(**kwargs: Any) -> dict[str, Any]:
    """Convenience wrapper returning :meth:`ResolveTaskResult.to_json_dict`."""
    return resolve_task(**kwargs).to_json_dict()


__all__ = [
    "ResolveStatus",
    "ResolveTaskError",
    "ResolveTaskResult",
    "load_changed_paths_manifest",
    "load_task_mapping",
    "resolve_git_changed_paths",
    "resolve_task",
    "resolve_task_as_dict",
    "RESOLUTION_RESOLVER_VERSION",
]
