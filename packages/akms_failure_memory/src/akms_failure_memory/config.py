"""Strict loader for ``failure-memory-project/v1`` TOML configuration."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Mapping

from akms_failure_memory.errors import FailureMemoryError


SCHEMA_VERSION = "failure-memory-project/v1"
_POLICIES = frozenset({"committed", "disposable"})
_REQUIRED_TOP = frozenset(
    {
        "schema_version",
        "repository_id",
        "node_namespace",
        "domain",
        "subdomain",
        "paths",
        "generated",
        "validation",
        "taxonomy",
        "compatibility",
        "toolchain",
        "promotion",
    }
)
_PATH_KEYS = frozenset(
    {
        "registry",
        "generated_nodes",
        "local_nodes",
        "routes",
        "akms_repo_root",
        "graph",
        "provider_outputs",
        "lock",
    }
)
_GENERATED_KEYS = frozenset({"lessons", "routes", "mirror", "graph", "loadouts"})
_VALIDATION_KEYS = frozenset(
    {
        "registry_schema_version",
        "missing_path_policy",
        "id_pattern",
        "allowed_roots",
        "root_files",
        "location_file_separator",
    }
)
_TAXONOMY_KEYS = frozenset(
    {
        "area_prefix",
        "package_prefix",
        "module_prefix",
        "symbol_prefix",
        "found_by_prefix",
        "line_hint_prefix",
        "max_tokens",
        "max_tag_length",
    }
)
_COMPATIBILITY_KEYS = frozenset(
    {
        "compiler_version",
        "route_contract_version",
        "route_adapter_version",
        "generated_warning",
        "source_hash_prefix",
        "source_hash_suffix",
    }
)
_TOOLCHAIN_REQUIRED = frozenset(
    {
        "akms_version",
        "akms_schema_version",
        "repo2md_command",
        "repo2md_version",
        "repo2md_export_schema_version",
        "repo2md_fixture_sha256",
        "repo2md_commit",
        "repo2md_dirty_policy",
        "mirror_selection",
        "timeout_seconds",
    }
)
# `akms_public_api_sha256` is still written by `init` and still reported by
# preflight, but it is no longer required: it stopped gating anything when the
# public-API digest became an advisory rather than a hard failure.
_TOOLCHAIN_ALLOWED = _TOOLCHAIN_REQUIRED | {"repo2md_root", "akms_public_api_sha256"}
_PROMOTION_KEYS = frozenset({"mode", "owner"})


def _closed_table(
    raw: Any,
    *,
    name: str,
    required: frozenset[str],
    allowed: frozenset[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise FailureMemoryError(f"{name} must be a TOML table", code="invalid_config")
    allowed = allowed or required
    missing = sorted(required - raw.keys())
    extra = sorted(raw.keys() - allowed)
    if missing or extra:
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if extra:
            detail.append("unexpected " + ", ".join(extra))
        raise FailureMemoryError(
            f"Invalid {name}: {'; '.join(detail)}", code="invalid_config"
        )
    return dict(raw)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise FailureMemoryError(
            f"{field} must be a non-empty string", code="invalid_config"
        )
    return value


def _relative_path(value: Any, field: str) -> str:
    text = _text(value, field)
    if "\\" in text or text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise FailureMemoryError(
            f"{field} must be a repository-relative POSIX path", code="path_escape"
        )
    path = PurePosixPath(text)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise FailureMemoryError(
            f"{field} contains a forbidden path segment", code="path_escape"
        )
    return path.as_posix()


def _string_list(value: Any, field: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (nonempty and not value):
        raise FailureMemoryError(
            f"{field} must be a string array", code="invalid_config"
        )
    items = tuple(_text(item, field) for item in value)
    if len(items) != len(set(items)):
        raise FailureMemoryError(
            f"{field} must contain unique values", code="invalid_config"
        )
    return items


@dataclass(frozen=True)
class ProjectConfig:
    """Validated immutable project policy and its canonical fingerprint."""

    source_path: Path
    repository_id: str
    node_namespace: str
    domain: str
    subdomain: str
    paths: Mapping[str, str]
    generated: Mapping[str, str]
    validation: Mapping[str, Any]
    taxonomy: Mapping[str, Any]
    compatibility: Mapping[str, Any]
    toolchain: Mapping[str, Any]
    promotion: Mapping[str, Any]
    canonical_data: Mapping[str, Any]
    fingerprint: str

    def resolve(self, repository_root: str | Path, key: str) -> Path:
        if key not in self.paths:
            raise FailureMemoryError(
                f"Unknown configured path {key!r}", code="invalid_path_key"
            )
        root = Path(repository_root).resolve(strict=True)
        candidate = root.joinpath(*PurePosixPath(self.paths[key]).parts)
        resolved_parent = candidate.parent.resolve(strict=False)
        if not resolved_parent.is_relative_to(root):
            raise FailureMemoryError(
                f"Configured path {key!r} escapes repository root", code="path_escape"
            )
        if candidate.exists() and not candidate.resolve().is_relative_to(root):
            raise FailureMemoryError(
                f"Configured path {key!r} resolves outside repository root",
                code="path_escape",
            )
        return candidate

    def to_json_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.canonical_data, ensure_ascii=False))


def _validate_config(raw: dict[str, Any], source_path: Path) -> ProjectConfig:
    top = _closed_table(raw, name="configuration", required=_REQUIRED_TOP)
    if top["schema_version"] != SCHEMA_VERSION:
        raise FailureMemoryError(
            f"Unsupported project schema {top['schema_version']!r}",
            code="schema_version",
        )
    repository_id = _text(top["repository_id"], "repository_id")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", repository_id) is None:
        raise FailureMemoryError(
            "repository_id has invalid characters", code="invalid_config"
        )
    namespace = _text(top["node_namespace"], "node_namespace")
    if re.fullmatch(r"[a-z0-9][a-z0-9-]*", namespace) is None:
        raise FailureMemoryError(
            "node_namespace has invalid characters", code="invalid_config"
        )

    paths = _closed_table(top["paths"], name="paths", required=_PATH_KEYS)
    paths = {key: _relative_path(value, f"paths.{key}") for key, value in paths.items()}
    generated = _closed_table(
        top["generated"], name="generated", required=_GENERATED_KEYS
    )
    if any(value not in _POLICIES for value in generated.values()):
        raise FailureMemoryError(
            "generated policies must be committed or disposable", code="invalid_config"
        )

    validation = _closed_table(
        top["validation"], name="validation", required=_VALIDATION_KEYS
    )
    if validation["registry_schema_version"] != 1:
        raise FailureMemoryError(
            "registry_schema_version must be 1", code="schema_version"
        )
    if validation["missing_path_policy"] not in {"warn", "error"}:
        raise FailureMemoryError("invalid missing_path_policy", code="invalid_config")
    try:
        re.compile(_text(validation["id_pattern"], "validation.id_pattern"))
    except re.error as exc:
        raise FailureMemoryError(
            f"Invalid id_pattern: {exc}", code="invalid_config"
        ) from exc
    validation["allowed_roots"] = _string_list(
        validation["allowed_roots"], "validation.allowed_roots", nonempty=True
    )
    validation["root_files"] = _string_list(
        validation["root_files"], "validation.root_files"
    )
    _text(validation["location_file_separator"], "validation.location_file_separator")

    taxonomy = _closed_table(top["taxonomy"], name="taxonomy", required=_TAXONOMY_KEYS)
    for key in _TAXONOMY_KEYS - {"max_tokens", "max_tag_length"}:
        _text(taxonomy[key], f"taxonomy.{key}")
    if not isinstance(taxonomy["max_tokens"], int) or taxonomy["max_tokens"] < 1:
        raise FailureMemoryError(
            "taxonomy.max_tokens must be positive", code="invalid_config"
        )
    if (
        not isinstance(taxonomy["max_tag_length"], int)
        or taxonomy["max_tag_length"] < 16
    ):
        raise FailureMemoryError(
            "taxonomy.max_tag_length must be at least 16", code="invalid_config"
        )

    compatibility = _closed_table(
        top["compatibility"], name="compatibility", required=_COMPATIBILITY_KEYS
    )
    for key in _COMPATIBILITY_KEYS - {"source_hash_prefix", "source_hash_suffix"}:
        _text(compatibility[key], f"compatibility.{key}")
    if compatibility["route_contract_version"] != "failure-route-index/v1":
        raise FailureMemoryError("unsupported route contract", code="schema_version")

    toolchain = _closed_table(
        top["toolchain"],
        name="toolchain",
        required=_TOOLCHAIN_REQUIRED,
        allowed=_TOOLCHAIN_ALLOWED,
    )
    toolchain["repo2md_command"] = _string_list(
        toolchain["repo2md_command"], "toolchain.repo2md_command", nonempty=True
    )
    if "repo2md_root" in toolchain:
        toolchain["repo2md_root"] = _relative_path(
            toolchain["repo2md_root"], "toolchain.repo2md_root"
        )
    for digest_key in ("akms_public_api_sha256", "repo2md_fixture_sha256"):
        if digest_key not in toolchain:
            continue
        if re.fullmatch(r"[0-9a-f]{64}", str(toolchain[digest_key])) is None:
            raise FailureMemoryError(
                f"toolchain.{digest_key} is not SHA-256", code="invalid_config"
            )
    if re.fullmatch(r"[0-9a-f]{40}", str(toolchain["repo2md_commit"])) is None:
        raise FailureMemoryError(
            "toolchain.repo2md_commit is not a commit SHA", code="invalid_config"
        )
    if toolchain["akms_schema_version"] != "v2":
        raise FailureMemoryError("AKMS schema must remain v2", code="schema_version")
    if toolchain["repo2md_dirty_policy"] not in {"require-clean", "allow-dirty"}:
        raise FailureMemoryError("invalid repo2md_dirty_policy", code="invalid_config")
    if toolchain["mirror_selection"] not in {"full", "changed", "paths"}:
        raise FailureMemoryError("invalid mirror_selection", code="invalid_config")
    if (
        not isinstance(toolchain["timeout_seconds"], (int, float))
        or toolchain["timeout_seconds"] <= 0
    ):
        raise FailureMemoryError(
            "timeout_seconds must be positive", code="invalid_config"
        )

    promotion = _closed_table(
        top["promotion"], name="promotion", required=_PROMOTION_KEYS
    )
    if promotion["mode"] != "manual-human-approved":
        raise FailureMemoryError(
            "promotion must remain human-approved", code="invalid_config"
        )
    _text(promotion["owner"], "promotion.owner")

    canonical = {
        "schema_version": SCHEMA_VERSION,
        "repository_id": repository_id,
        "node_namespace": namespace,
        "domain": _text(top["domain"], "domain"),
        "subdomain": _text(top["subdomain"], "subdomain"),
        "paths": paths,
        "generated": generated,
        "validation": validation,
        "taxonomy": taxonomy,
        "compatibility": compatibility,
        "toolchain": toolchain,
        "promotion": promotion,
    }
    canonical_bytes = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return ProjectConfig(
        source_path=source_path,
        repository_id=repository_id,
        node_namespace=namespace,
        domain=canonical["domain"],
        subdomain=canonical["subdomain"],
        paths=MappingProxyType(paths),
        generated=MappingProxyType(generated),
        validation=MappingProxyType(validation),
        taxonomy=MappingProxyType(taxonomy),
        compatibility=MappingProxyType(compatibility),
        toolchain=MappingProxyType(toolchain),
        promotion=MappingProxyType(promotion),
        canonical_data=MappingProxyType(canonical),
        fingerprint=hashlib.sha256(canonical_bytes).hexdigest(),
    )


def load_project_config(path: str | Path) -> ProjectConfig:
    """Load a strict TOML configuration; duplicate keys fail in ``tomllib``."""
    source = Path(path)
    try:
        raw = tomllib.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise FailureMemoryError(
            f"Cannot load project configuration {source}: {exc}", code="config_load"
        ) from exc
    return _validate_config(raw, source.resolve())


__all__ = ["ProjectConfig", "SCHEMA_VERSION", "load_project_config"]
