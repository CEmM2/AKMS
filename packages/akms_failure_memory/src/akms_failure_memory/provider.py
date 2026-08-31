"""Harness-neutral deterministic failure-memory provider contract."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from akms.graph.build_graph import build_graph
from akms.task_context.resolve_task_service import resolve_task
from akms.task_context.review import resolve_reviewer_context

import akms
from akms_failure_memory.compiler import run_compiler
from akms_failure_memory.config import ProjectConfig, load_project_config
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.locks import ProjectLock
from akms_failure_memory.refresh import (
    _finalize_graph_payload,
    preflight,
)

REQUEST_SCHEMA_VERSION = "failure-memory-provider-request/v1"
RESULT_SCHEMA_VERSION = "failure-memory-provider-result/v1"
PROVIDER_VERSION = "failure-memory-provider/v1"
_REQUEST_FIELDS = frozenset(
    {
        "schema_version",
        "invocation_id",
        "repository_id",
        "baseline",
        "mode",
        "role",
        "declared_paths",
        "changed_paths",
        "base",
        "head",
        "refresh_policy",
        "output_dir",
        "task",
    }
)
_REQUIRED_REQUEST_FIELDS = frozenset(
    {
        "schema_version",
        "invocation_id",
        "repository_id",
        "baseline",
        "mode",
        "role",
        "declared_paths",
        "refresh_policy",
        "output_dir",
        "task",
    }
)
_IMPLEMENTER_ROLES = frozenset({"implementer"})
_REVIEWER_ROLES = frozenset({"code_reviewer", "physics_reviewer"})


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise FailureMemoryError(
            f"Cannot fingerprint {path}: {exc}", code="provider_input"
        ) from exc


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FailureMemoryError(
            f"{field} must be a non-empty string", code="provider_request"
        )
    return value.strip()


def _identifier(value: Any, field: str) -> str:
    text = _text(value, field)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", text) is None:
        raise FailureMemoryError(
            f"{field} is not a safe identifier", code="provider_request"
        )
    return text


def _path(value: Any, field: str) -> str:
    text = _text(value, field)
    if "\\" in text or text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise FailureMemoryError(
            f"{field} must be repository-relative", code="path_escape"
        )
    parsed = PurePosixPath(text)
    if any(part in {"", ".", ".."} for part in parsed.parts):
        raise FailureMemoryError(
            f"{field} contains a forbidden segment", code="path_escape"
        )
    return parsed.as_posix()


def _paths(value: Any, field: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise FailureMemoryError(
            f"{field} must be an array of paths", code="provider_request"
        )
    normalized = tuple(_path(item, field) for item in value)
    if len(normalized) != len(set(normalized)):
        raise FailureMemoryError(
            f"{field} must contain unique paths", code="provider_request"
        )
    return normalized


def load_provider_request(source: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Load and strictly validate one closed v1 provider request."""
    if isinstance(source, Mapping):
        raw = dict(source)
    else:
        try:
            raw = json.loads(Path(source).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FailureMemoryError(
                f"Cannot load provider request: {exc}", code="provider_request"
            ) from exc
    if not isinstance(raw, dict):
        raise FailureMemoryError(
            "Provider request root must be an object", code="provider_request"
        )
    missing = _REQUIRED_REQUEST_FIELDS - raw.keys()
    extra = raw.keys() - _REQUEST_FIELDS
    if missing or extra:
        raise FailureMemoryError(
            f"Invalid provider request fields; missing={sorted(missing)}, unexpected={sorted(extra)}",
            code="provider_request",
        )
    if raw["schema_version"] != REQUEST_SCHEMA_VERSION:
        raise FailureMemoryError(
            "Unsupported provider request schema", code="schema_version"
        )
    mode = _text(raw["mode"], "mode")
    if mode not in {"pre-task", "post-diff"}:
        raise FailureMemoryError(
            "mode must be pre-task or post-diff", code="provider_request"
        )
    role = _text(raw["role"], "role")
    if mode == "pre-task" and role not in _IMPLEMENTER_ROLES:
        raise FailureMemoryError(
            "pre-task mode requires implementer role", code="provider_request"
        )
    if mode == "post-diff" and role not in _REVIEWER_ROLES:
        raise FailureMemoryError(
            "post-diff mode requires a reviewer role", code="provider_request"
        )
    refresh_policy = _text(raw["refresh_policy"], "refresh_policy")
    if refresh_policy not in {"never", "require-current"}:
        raise FailureMemoryError(
            "refresh_policy must be never or require-current", code="provider_request"
        )
    changed = _paths(raw.get("changed_paths", []), "changed_paths")
    base = raw.get("base")
    head = raw.get("head")
    if base is not None:
        base = _text(base, "base")
    if head is not None:
        head = _text(head, "head")
    if changed and base is not None:
        raise FailureMemoryError(
            "Provide changed_paths or base/head, not both", code="provider_request"
        )
    task = raw["task"]
    if not isinstance(task, dict):
        raise FailureMemoryError("task must be an object", code="provider_request")
    normalized = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "invocation_id": _identifier(raw["invocation_id"], "invocation_id"),
        "repository_id": _identifier(raw["repository_id"], "repository_id"),
        "baseline": _text(raw["baseline"], "baseline"),
        "mode": mode,
        "role": role,
        "declared_paths": list(_paths(raw["declared_paths"], "declared_paths")),
        "changed_paths": list(changed),
        "base": base,
        "head": head,
        "refresh_policy": refresh_policy,
        "output_dir": _path(raw["output_dir"], "output_dir"),
        "task": json.loads(json.dumps(task, ensure_ascii=False)),
    }
    if not normalized["declared_paths"]:
        raise FailureMemoryError(
            "declared_paths must not be empty", code="provider_request"
        )
    return normalized


def _contained_output(
    config: ProjectConfig, root: Path, request: Mapping[str, Any]
) -> Path:
    provider_root = config.resolve(root, "provider_outputs")
    requested = root.joinpath(*PurePosixPath(str(request["output_dir"])).parts)
    requested_parent = requested.parent.resolve(strict=False)
    if not requested_parent.is_relative_to(root):
        raise FailureMemoryError(
            "Provider output escapes repository", code="path_escape"
        )
    if requested.resolve(strict=False) != provider_root.resolve(strict=False):
        raise FailureMemoryError(
            "output_dir must equal the configured provider output root",
            code="provider_request",
        )
    invocation = requested / str(request["invocation_id"])
    if invocation.exists() or invocation.is_symlink():
        raise FailureMemoryError(
            f"Provider invocation output already exists: {invocation}",
            code="provider_output_exists",
        )
    return invocation


def _task(request: Mapping[str, Any]) -> dict[str, Any]:
    task = dict(request["task"])
    task["scope"] = list(request["declared_paths"])
    task["deliverables"] = list(request["declared_paths"])
    task.pop("changed_files", None)
    return task


def _records(query_result: Any) -> list[dict[str, Any]]:
    if query_result is None:
        return []
    records = []
    for selection in query_result.selections:
        data = selection.node_data
        source_ref = data.get("source_file") or data.get("source") or data.get("path")
        content_ref = data.get("content_ref")
        records.append(
            {
                "node_id": selection.node_id,
                "selection_class": selection.selection_class.value,
                "reasons": list(selection.reasons),
                "source_ref": str(source_ref) if source_ref is not None else None,
                "content_ref": str(content_ref) if content_ref is not None else None,
            }
        )
    return records


def _input_fingerprints(config: ProjectConfig, root: Path) -> dict[str, str]:
    graph = config.resolve(root, "graph")
    routes = config.resolve(root, "routes")
    if not graph.is_file() or not routes.is_file():
        raise FailureMemoryError(
            "Provider requires current graph and routes", code="provider_input"
        )
    # NOTE: the AKMS public-API source digest is deliberately NOT an input here.
    # It hashes seventeen AKMS source files byte-for-byte, so any edit to one of
    # them -- including a comment or a docstring -- changed this fingerprint and
    # marked every existing publication stale, which also made the "frozen"
    # consumer-conformance pack move with unrelated AKMS source churn. Intentional
    # toolchain changes are already captured at a sane granularity by
    # `toolchain_sha256` below (akms_version + akms_schema_version) and by
    # PROVIDER_VERSION. Resolution inputs are the graph, the routes, and the
    # config -- not the bytes of the resolver.
    return {
        "config_sha256": config.fingerprint,
        "graph_sha256": _sha256_file(graph),
        "routes_sha256": _sha256_file(routes),
        "repo2md_fixture_sha256": str(config.toolchain["repo2md_fixture_sha256"]),
        "toolchain_sha256": hashlib.sha256(
            _canonical_json(
                {
                    "akms_version": akms.__version__,
                    "akms_schema_version": akms.AKMS_SCHEMA_VERSION,
                    "repo2md_version": config.toolchain["repo2md_version"],
                    "repo2md_commit": config.toolchain["repo2md_commit"],
                    "repo2md_export_schema_version": config.toolchain[
                        "repo2md_export_schema_version"
                    ],
                }
            )
        ).hexdigest(),
    }


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            temporary = Path(stream.name)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _require_current(config: ProjectConfig, root: Path) -> None:
    """Fail closed unless pinned tools and every deterministic input are current."""
    preflight(config=config, repository_root=root)
    vault_value = os.environ.get("AKMS_GLOBAL_VAULT")
    if not vault_value:
        raise FailureMemoryError(
            "require-current needs an explicit AKMS_GLOBAL_VAULT",
            code="provider_stale",
        )
    vault = Path(vault_value).expanduser().resolve(strict=True)
    compiler = run_compiler(
        config_path=config.source_path,
        repository_root=root,
        global_vault=vault,
        mode="check",
    )
    if compiler["status"] != "clean":
        raise FailureMemoryError(
            "Failure-memory compiler outputs are stale", code="provider_stale"
        )
    recorded_path = config.resolve(root, "graph")
    if not recorded_path.is_file():
        raise FailureMemoryError("AKMS graph is missing", code="provider_stale")
    with tempfile.TemporaryDirectory(prefix="failure-memory-graph-check-") as directory:
        candidate_path = Path(directory) / "graph.json"
        build_graph(
            config.resolve(root, "akms_repo_root"),
            global_vault=vault,
            output_path=candidate_path,
            strict=True,
        )
        try:
            recorded = json.loads(recorded_path.read_text(encoding="utf-8"))
            recorded_metadata = recorded["graph"]
            if not isinstance(recorded_metadata, dict):
                raise TypeError("graph metadata must be an object")
            recorded_generated_at = recorded_metadata["generated_at"]
            if not isinstance(recorded_generated_at, str):
                raise TypeError("generated_at must be text")
            candidate_data = json.loads(candidate_path.read_text(encoding="utf-8"))
            candidate = json.loads(
                _finalize_graph_payload(
                    candidate_data,
                    config=config,
                    generated_at=recorded_generated_at,
                )
            )
        except (
            FailureMemoryError,
            OSError,
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            raise FailureMemoryError(
                "Cannot validate the current AKMS graph", code="provider_stale"
            ) from exc
    if recorded != candidate:
        raise FailureMemoryError("AKMS graph is stale", code="provider_stale")


def _published_frontmatter(path: Path) -> dict[str, Any] | None:
    """Front matter of one published generated node file, or ``None`` if unreadable."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    if not text.startswith("---\n"):
        return None
    try:
        front = yaml.safe_load(text.split("---\n", 2)[1])
    except (IndexError, yaml.YAMLError):
        return None
    return front if isinstance(front, dict) else None


def _fields_agree(published: Any, graph_value: Any) -> bool:
    """Field-level agreement between published front matter and a graph node.

    Lists of strings compare as sets (the graph builder owns ordering); every
    other value must round-trip to identical canonical JSON. These are two
    projections of the same compiler output, so any difference means one of the
    two published artifacts changed after the other was produced.
    """
    if (
        isinstance(published, list)
        and isinstance(graph_value, list)
        and all(isinstance(item, str) for item in published)
        and all(isinstance(item, str) for item in graph_value)
    ):
        return set(published) == set(graph_value)
    try:
        return json.dumps(published, sort_keys=True) == json.dumps(
            graph_value, sort_keys=True
        )
    except (TypeError, ValueError):
        return False


def validate_publication(
    *, config_path: str | Path, repository_root: str | Path
) -> list[str]:
    """Package-owned deterministic validation of the published graph.

    Two published artifacts must agree: the graph and the generated project
    node files it was built from. This verifies what is there — it never
    re-derives the compiler's or the graph builder's rules — and it is the
    single definition both consumers inherit through ``validate_fingerprint``,
    so neither has to (and neither may) mirror a package predicate.

    Checks, all against this project's own namespace only:

    1. The graph carries this project's identity: ``graph.repo_id`` equals the
       configured ``repository_id``. Fingerprint reproducibility alone cannot
       see this — a graph published under a foreign identity reproduces
       consistently.
    2. The project-namespaced nodes in the graph are exactly the published
       generated node files — a graph node with no published file behind it is
       fabricated content, and a published file missing from the graph is the
       ordinary "nodes were recompiled but the graph was not rebuilt" state.
    3. Every field the two artifacts share agrees, and every ``load_with``
       target a published node names is present in the graph, because
       resolution will read that content and try to load those targets.

    Returns a list of human-readable problems; an empty list means the
    publication is internally consistent and carries this project's identity.
    """
    config = load_project_config(config_path)
    root = Path(repository_root).resolve(strict=True)
    graph_path = config.resolve(root, "graph")
    try:
        document = json.loads(graph_path.read_text(encoding="utf-8"))
        metadata = document["graph"]
        raw_nodes = document["nodes"]
        if not isinstance(metadata, dict) or not isinstance(raw_nodes, list):
            raise TypeError("graph document shape is invalid")
    except (OSError, UnicodeError, KeyError, TypeError, json.JSONDecodeError):
        return [f"published graph is unreadable: {config.paths['graph']}"]
    problems: list[str] = []
    if metadata.get("repo_id") != config.repository_id:
        problems.append(
            f"published graph repo_id {metadata.get('repo_id')!r} does not match "
            f"the configured repository_id {config.repository_id!r}"
        )
    graph_nodes = {
        node["id"]: node
        for node in raw_nodes
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }
    prefix = f"{config.node_namespace}-"
    generated = config.resolve(root, "generated_nodes")
    published_ids = (
        sorted(path.stem for path in generated.glob(f"{prefix}*.md"))
        if generated.is_dir()
        else []
    )
    graph_project_ids = sorted(
        node_id for node_id in graph_nodes if node_id.startswith(prefix)
    )
    for node_id in sorted(set(graph_project_ids) - set(published_ids)):
        problems.append(
            f"graph node {node_id} has no published generated node file behind it"
        )
    for node_id in sorted(set(published_ids) - set(graph_project_ids)):
        problems.append(
            f"published generated node {node_id} is missing from the graph"
        )
    for node_id in sorted(set(published_ids) & set(graph_project_ids)):
        front = _published_frontmatter(generated / f"{node_id}.md")
        if front is None:
            problems.append(
                f"published generated node {node_id} has unreadable front matter"
            )
            continue
        graph_node = graph_nodes[node_id]
        disagreeing = sorted(
            key
            for key in set(front) & set(graph_node)
            if not _fields_agree(front[key], graph_node[key])
        )
        if disagreeing:
            problems.append(
                f"graph node {node_id} disagrees with its published generated "
                f"file on: {', '.join(disagreeing)}"
            )
        for target in front.get("load_with") or []:
            if target not in graph_nodes:
                problems.append(
                    f"load_with target {target} named by published node "
                    f"{node_id} is missing from the graph"
                )
    return problems


def _resolve_provider_locked(
    *,
    config: ProjectConfig,
    root: Path,
    request: Mapping[str, Any],
    write_artifacts: bool,
) -> dict[str, Any]:
    invocation_dir = (
        _contained_output(config, root, request) if write_artifacts else None
    )
    paths = _input_fingerprints(config, root)
    task = _task(request)
    loadout = invocation_dir / "loadout.md" if invocation_dir else None
    manifest = invocation_dir / "resolution-manifest.json" if invocation_dir else None
    common = {
        "repo_root": config.resolve(root, "akms_repo_root"),
        "task": task,
        "route_index": config.resolve(root, "routes"),
        "agent_role": request["role"],
        "graph_path": config.resolve(root, "graph"),
        "loadout_path": loadout,
        "manifest_path": manifest,
        "mode": "routing",
        "write_artifacts": write_artifacts,
    }
    if request["mode"] == "pre-task":
        resolution = resolve_task(**common)
        query_result = resolution.query_result
        resolution_payload = resolution.to_json_dict()
        diagnostics: dict[str, Any] = {}
    else:
        resolution = resolve_reviewer_context(
            **common,
            changed_paths=request["changed_paths"],
            base=request["base"],
            head=request["head"],
        )
        query_result = resolution.query_result
        resolution_payload = resolution.to_json_dict()
        diagnostics = {
            "empty_diff_fallback": resolution.empty_diff_fallback,
            "post_diff_only_required": list(resolution.post_diff_only_required),
        }
    if resolution.status != "ok":
        raise FailureMemoryError(
            resolution.error or "AKMS resolution failed",
            code=resolution.error_code or "provider_resolve",
        )
    fingerprint_inputs = {
        "provider_version": PROVIDER_VERSION,
        "request": request,
        "resolution_fingerprint": resolution.fingerprint,
        "inputs": paths,
    }
    fingerprint = hashlib.sha256(_canonical_json(fingerprint_inputs)).hexdigest()
    result = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "status": "ok",
        "provider_version": PROVIDER_VERSION,
        "invocation_id": request["invocation_id"],
        "repository_id": request["repository_id"],
        "baseline": request["baseline"],
        "mode": request["mode"],
        "role": request["role"],
        "fingerprint": fingerprint,
        "resolution_fingerprint": resolution.fingerprint,
        "input_fingerprints": paths,
        "records": _records(query_result),
        "diagnostics": diagnostics,
        "resolution": resolution_payload,
        "artifacts": {
            "loadout": str(loadout.relative_to(root)) if loadout else None,
            "manifest": str(manifest.relative_to(root)) if manifest else None,
            "result": str((invocation_dir / "result.json").relative_to(root))
            if invocation_dir
            else None,
        },
    }
    if invocation_dir is not None:
        _atomic_write(invocation_dir / "result.json", _canonical_json(result))
    return result


def resolve_provider(
    *,
    config_path: str | Path,
    repository_root: str | Path,
    request_source: str | Path | Mapping[str, Any],
    write_artifacts: bool = True,
) -> dict[str, Any]:
    """Resolve one provider request using only pinned public AKMS services."""
    config = load_project_config(config_path)
    root = Path(repository_root).resolve(strict=True)
    request = load_provider_request(request_source)
    if request["repository_id"] != config.repository_id:
        raise FailureMemoryError(
            "repository_id does not match project config", code="provider_identity"
        )
    # write_artifacts is the caller's declaration of intent to mutate the
    # target repository (provider evidence outputs). A read-only caller
    # (write_artifacts=False -- e.g. a consumer's strictly read-only
    # surface) must not have lock acquisition itself create filesystem
    # structure; see ProjectLock.acquire and locks.py for the fail-closed
    # behavior when the lock's parent directory does not yet exist.
    with ProjectLock(
        config.resolve(root, "lock"),
        timeout_seconds=float(config.toolchain["timeout_seconds"]),
        create_parent_directories=write_artifacts,
    ):
        if request["refresh_policy"] == "require-current":
            _require_current(config, root)
        return _resolve_provider_locked(
            config=config,
            root=root,
            request=request,
            write_artifacts=write_artifacts,
        )


def validate_fingerprint(
    *,
    config_path: str | Path,
    repository_root: str | Path,
    request_source: str | Path | Mapping[str, Any],
    result_path: str | Path,
) -> dict[str, Any]:
    """Recompute a result fingerprint without writing provider artifacts.

    ``current`` requires BOTH that the recomputed fingerprint matches the
    recorded one AND that :func:`validate_publication` finds the published
    graph valid. Fingerprint reproducibility alone cannot notice a graph
    published under a foreign repository identity, or a graph whose
    project-namespaced nodes disagree with the published generated node files
    — a consistently-wrong graph reproduces consistently — so those states
    report ``stale`` (republish the graph), never ``current``.
    """
    try:
        prior = json.loads(Path(result_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FailureMemoryError(
            f"Cannot load provider result: {exc}", code="provider_result"
        ) from exc
    if (
        not isinstance(prior, dict)
        or prior.get("schema_version") != RESULT_SCHEMA_VERSION
    ):
        raise FailureMemoryError(
            "Unsupported provider result schema", code="provider_result"
        )
    current = resolve_provider(
        config_path=config_path,
        repository_root=repository_root,
        request_source=request_source,
        write_artifacts=False,
    )
    stale = prior.get("fingerprint") != current["fingerprint"] or bool(
        validate_publication(
            config_path=config_path, repository_root=repository_root
        )
    )
    return {
        "status": "stale" if stale else "current",
        "stale": stale,
        "recorded_fingerprint": prior.get("fingerprint"),
        "current_fingerprint": current["fingerprint"],
    }


def run_provider_command(command: str, args: Any) -> dict[str, Any]:
    if command == "resolve":
        return resolve_provider(
            config_path=args.config,
            repository_root=args.repo,
            request_source=args.request,
        )
    if command == "validate-fingerprint":
        return validate_fingerprint(
            config_path=args.config,
            repository_root=args.repo,
            request_source=args.request,
            result_path=args.result,
        )
    raise FailureMemoryError(f"Unknown provider command {command!r}", code="usage")


__all__ = [
    "PROVIDER_VERSION",
    "REQUEST_SCHEMA_VERSION",
    "RESULT_SCHEMA_VERSION",
    "load_provider_request",
    "resolve_provider",
    "run_provider_command",
    "validate_fingerprint",
    "validate_publication",
]
