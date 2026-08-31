"""Project initialization, doctor, migration reporting, and wrapper generation."""

from __future__ import annotations

import json
import os
import re
import shlex
import tempfile
from argparse import Namespace
from pathlib import Path
from typing import Any

from akms_failure_memory.config import load_project_config
from akms_failure_memory.errors import FailureMemoryError


_AKMS_PUBLIC_API_SHA256 = (
    "3a79a11312376a5f203013c87d37b2a695fab895ffa6d47decd2c0ad95f7b828"
)
_REPO2MD_FIXTURE_SHA256 = (
    "5d2e398b7baab7045615ccb0e935c2baeae154d21fb4a29ba5498f06687d2d6b"
)
_REPO2MD_COMMIT = "478be35c76325ab1ccea48b69a5ea25b095952a6"


def _atomic_create(
    path: Path, content: bytes, *, force: bool = False, mode: int = 0o644
) -> None:
    if path.exists() and not force:
        raise FailureMemoryError(
            f"Refusing to overwrite existing file {path}", code="file_exists"
        )
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
        os.chmod(temporary, mode)
        if path.exists() and not force:
            raise FailureMemoryError(
                f"Refusing to overwrite existing file {path}", code="file_exists"
            )
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _identifier(value: str, *, namespace: bool = False) -> str:
    pattern = r"[a-z0-9][a-z0-9-]*" if namespace else r"[A-Za-z0-9][A-Za-z0-9_.-]*"
    if re.fullmatch(pattern, value) is None:
        raise FailureMemoryError(
            f"Invalid project identifier {value!r}", code="invalid_config"
        )
    return value


def render_project_config(repository_id: str, node_namespace: str) -> bytes:
    """Render the minimal generic layout; consumer-specific choices stay explicit."""
    repository_id = _identifier(repository_id)
    node_namespace = _identifier(node_namespace, namespace=True)
    text = f'''schema_version = "failure-memory-project/v1"
repository_id = "{repository_id}"
node_namespace = "{node_namespace}"
domain = "{repository_id.lower()}"
subdomain = "failure-memory"

[paths]
registry = ".failure-memory/lessons.json"
generated_nodes = ".failure-memory/runtime/knowledge/local-nodes/failure-lessons"
local_nodes = ".failure-memory/runtime/knowledge/local-nodes"
routes = ".failure-memory/generated/routes.json"
akms_repo_root = ".failure-memory/runtime"
graph = ".failure-memory/runtime/knowledge/graph/graph.json"
provider_outputs = ".failure-memory/runtime/provider"
lock = ".failure-memory/.lock"

[generated]
lessons = "disposable"
routes = "disposable"
mirror = "disposable"
graph = "disposable"
loadouts = "disposable"

[validation]
registry_schema_version = 1
missing_path_policy = "warn"
id_pattern = "^L[0-9]{{3}}$"
allowed_roots = ["src", "tests", "docs", "tools", ".github"]
root_files = ["README.md", "pyproject.toml"]
location_file_separator = " and "

[taxonomy]
area_prefix = "area"
package_prefix = "package"
module_prefix = "module"
symbol_prefix = "symbol"
found_by_prefix = "found-by"
line_hint_prefix = "line-hint"
max_tokens = 8
max_tag_length = 80

[compatibility]
compiler_version = "failure-memory-compiler/v1"
route_contract_version = "failure-route-index/v1"
route_adapter_version = "failure-memory-to-akms-task-route/v1"
generated_warning = "<!-- GENERATED: edit .failure-memory/lessons.json -->"
source_hash_prefix = "<!-- source_sha256: "
source_hash_suffix = " -->"

[toolchain]
akms_version = "0.6.1"
akms_schema_version = "v2"
akms_public_api_sha256 = "{_AKMS_PUBLIC_API_SHA256}"
repo2md_command = ["repo-wiki"]
repo2md_version = "0.2.0"
repo2md_export_schema_version = 1
repo2md_fixture_sha256 = "{_REPO2MD_FIXTURE_SHA256}"
repo2md_commit = "{_REPO2MD_COMMIT}"
repo2md_dirty_policy = "require-clean"
mirror_selection = "full"
timeout_seconds = 120

[promotion]
mode = "manual-human-approved"
owner = "{repository_id} maintainers"
'''
    return text.encode("utf-8")


def _empty_registry() -> bytes:
    value = {
        "schema_version": 1,
        "_field_spec": {
            "id": "Stable append-only lesson identifier.",
            "location": "Repository location for the failure.",
            "found_by": "Discovery mechanism and trigger.",
            "related": "Related lesson identifiers.",
        },
        "lessons": [],
    }
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def init_project(
    *,
    repository_root: str | Path,
    config_path: str | Path,
    repository_id: str | None = None,
    node_namespace: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    root = Path(repository_root).resolve(strict=True)
    configured = Path(config_path)
    destination = configured if configured.is_absolute() else root / configured
    if not destination.parent.resolve(strict=False).is_relative_to(root):
        raise FailureMemoryError(
            "Configuration path escapes repository root", code="path_escape"
        )
    identity = repository_id or root.name
    namespace = (
        node_namespace
        or re.sub(r"[^a-z0-9]+", "-", identity.lower()).strip("-") + "-failure"
    )
    config_bytes = render_project_config(identity, namespace)
    if destination.exists() and not force:
        raise FailureMemoryError(
            f"Refusing to overwrite existing file {destination}", code="file_exists"
        )
    _atomic_create(destination, config_bytes, force=force)
    config = load_project_config(destination)
    registry = config.resolve(root, "registry")
    try:
        _atomic_create(registry, _empty_registry(), force=force)
    except Exception:
        if not force and destination.exists():
            destination.unlink()
        raise
    return {
        "status": "initialized",
        "config": destination.relative_to(root).as_posix(),
        "registry": registry.relative_to(root).as_posix(),
        "repository_id": config.repository_id,
        "node_namespace": config.node_namespace,
        "config_fingerprint": config.fingerprint,
    }


def doctor(*, config_path: str | Path, repository_root: str | Path) -> dict[str, Any]:
    root = Path(repository_root).resolve(strict=True)
    config = load_project_config(config_path)
    checks = []
    for key in config.paths:
        path = config.resolve(root, key)
        checks.append(
            {
                "check": f"path:{key}",
                "status": "ok",
                "path": path.relative_to(root).as_posix(),
            }
        )
    registry = config.resolve(root, "registry")
    checks.append(
        {"check": "registry", "status": "ok" if registry.is_file() else "missing"}
    )
    status = "ok" if all(item["status"] == "ok" for item in checks) else "error"
    return {
        "status": status,
        "checks": checks,
        "config_fingerprint": config.fingerprint,
    }


def migration_check(
    *, config_path: str | Path, repository_root: str | Path
) -> dict[str, Any]:
    root = Path(repository_root).resolve(strict=True)
    config = load_project_config(config_path)
    legacy_shape = (
        config.paths["registry"] == "dev/lessons_from_failing.json"
        and config.paths["generated_nodes"]
        == "dev/knowledge/local-nodes/generated/failure-lessons"
        and config.paths["routes"] == "dev/knowledge/generated/failure_routes.json"
    )
    return {
        "status": "recognized" if legacy_shape else "generic",
        "layout": "phase1-compatible" if legacy_shape else "configured",
        "registry_exists": config.resolve(root, "registry").is_file(),
        "rewrite_performed": False,
        "moves_required": [],
    }


def generate_wrapper(
    *,
    config_path: str | Path,
    repository_root: str | Path,
    output: str | Path,
    force: bool = False,
) -> dict[str, Any]:
    root = Path(repository_root).resolve(strict=True)
    config = Path(config_path).resolve(strict=True)
    destination = Path(output) if Path(output).is_absolute() else root / output
    if not destination.parent.resolve(strict=False).is_relative_to(root):
        raise FailureMemoryError(
            "Wrapper output escapes repository root", code="path_escape"
        )
    try:
        display_config = config.relative_to(root).as_posix()
    except ValueError as exc:
        raise FailureMemoryError(
            "Configuration must be inside repository root", code="path_escape"
        ) from exc
    body = (
        f'#!/bin/sh\nset -eu\nexec failure-memory "$@" --config {shlex.quote(display_config)}\n'
    ).encode("utf-8")
    _atomic_create(destination, body, force=force, mode=0o755)
    return {"status": "written", "wrapper": destination.relative_to(root).as_posix()}


def run_project_command(command: str, args: Namespace) -> dict[str, Any]:
    if command == "init":
        return init_project(
            repository_root=args.repo,
            config_path=args.config,
            repository_id=args.repository_id,
            node_namespace=args.node_namespace,
            force=args.force,
        )
    if command == "doctor":
        return doctor(config_path=args.config, repository_root=args.repo)
    if command == "migrate-check":
        return migration_check(config_path=args.config, repository_root=args.repo)
    if command == "generate-wrapper":
        return generate_wrapper(
            config_path=args.config,
            repository_root=args.repo,
            output=args.output,
            force=args.force,
        )
    raise FailureMemoryError(f"Unknown project command {command!r}", code="usage")


__all__ = [
    "doctor",
    "generate_wrapper",
    "init_project",
    "migration_check",
    "render_project_config",
    "run_project_command",
]
