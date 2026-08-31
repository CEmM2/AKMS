"""Configuration-driven deterministic lesson compiler and exact-route generator."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from akms.task_context.routes import parse_route_index

from akms_failure_memory.config import ProjectConfig, load_project_config
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.locks import ProjectLock


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_SYMBOL_RE = re.compile(r"[A-Za-z0-9_@+.\[\]-]+")
_REASON_TEXT = {
    "location.file": "Exact repository path declared by location.file",
    "location.symbol": "Optional exact symbol route declared by location.symbol",
    "found_by.trigger": "Exact repository path extracted from found_by.trigger",
    "prevention": "Exact repository path extracted from prevention",
}
_LESSON_KEYS = frozenset(
    {
        "id",
        "date_found",
        "date_found_precision",
        "date_fixed",
        "date_fixed_precision",
        "location",
        "found_by",
        "symptom",
        "root_cause",
        "fix",
        "prevention",
        "references",
        "related",
    }
)
_LOCATION_KEYS = frozenset({"area", "package", "module", "file", "symbol", "line_hint"})
_FOUND_KEYS = frozenset({"type", "trigger"})
_REFERENCE_KEYS = frozenset({"commit", "issue", "pr", "plan"})


@dataclass(frozen=True)
class CompiledNode:
    lesson_id: str
    node_id: str
    frontmatter: dict[str, Any]
    content: str


@dataclass(frozen=True)
class Compilation:
    source_sha256: str
    source_schema_version: int
    nodes: tuple[CompiledNode, ...]
    canonical_routes: dict[str, Any]
    adapted_routes: dict[str, Any]
    warnings: tuple[dict[str, str], ...]


def _decode_registry(
    data: bytes, source: Path, config: ProjectConfig
) -> dict[str, Any]:
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FailureMemoryError(
            f"Cannot load registry {source}: {exc}", code="registry_load"
        ) from exc
    if not isinstance(raw, dict) or set(raw) != {
        "schema_version",
        "_field_spec",
        "lessons",
    }:
        raise FailureMemoryError(
            "Registry must contain only schema_version, _field_spec, lessons",
            code="registry_schema",
        )
    if raw["schema_version"] != config.validation["registry_schema_version"]:
        raise FailureMemoryError(
            "Unsupported registry schema_version", code="registry_schema"
        )
    if not isinstance(raw["_field_spec"], dict) or not isinstance(raw["lessons"], list):
        raise FailureMemoryError(
            "Registry field types are invalid", code="registry_schema"
        )
    return raw


def _closed(
    raw: Any,
    keys: frozenset[str],
    field: str,
    *,
    optional: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise FailureMemoryError(f"{field} must be an object", code="registry_schema")
    actual = set(raw)
    if not keys.issubset(actual) or not actual.issubset(keys | optional):
        raise FailureMemoryError(
            f"{field} has missing or unexpected fields", code="registry_schema"
        )
    return raw


def _scalar(raw: dict[str, Any], key: str, field: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise FailureMemoryError(
            f"{field}.{key} must be a string", code="registry_schema"
        )
    return value


def validate_registry_bytes(
    data: bytes, source: Path, config: ProjectConfig
) -> tuple[dict[str, Any], ...]:
    """Validate the canonical append-only v1 registry without mutating it."""
    registry = _decode_registry(data, source, config)
    lessons: list[dict[str, Any]] = []
    seen: set[str] = set()
    id_pattern = re.compile(str(config.validation["id_pattern"]))
    for index, item in enumerate(registry["lessons"]):
        lesson = _closed(
            item, _LESSON_KEYS, f"lessons[{index}]", optional=frozenset({"notes"})
        )
        lesson_id = _scalar(lesson, "id", f"lessons[{index}]")
        if id_pattern.fullmatch(lesson_id) is None:
            raise FailureMemoryError(
                f"Malformed lesson ID {lesson_id!r}", code="registry_id"
            )
        if lesson_id in seen:
            raise FailureMemoryError(
                f"Duplicate lesson ID {lesson_id}", code="duplicate_id"
            )
        seen.add(lesson_id)
        for key in ("date_found", "date_fixed"):
            if _DATE_RE.fullmatch(_scalar(lesson, key, lesson_id)) is None:
                raise FailureMemoryError(
                    f"{lesson_id}.{key} is not YYYY-MM-DD", code="registry_schema"
                )
        for key in ("date_found_precision", "date_fixed_precision"):
            if _scalar(lesson, key, lesson_id) not in {"exact", "approximate"}:
                raise FailureMemoryError(
                    f"{lesson_id}.{key} is invalid", code="registry_schema"
                )
        location = _closed(lesson["location"], _LOCATION_KEYS, f"{lesson_id}.location")
        for key in _LOCATION_KEYS:
            _scalar(location, key, f"{lesson_id}.location")
        if not location["file"]:
            raise FailureMemoryError(
                f"{lesson_id}.location.file is empty", code="registry_path"
            )
        if ";" in location["file"]:
            raise FailureMemoryError(
                f"{lesson_id}: location.file must not use ';' as a multi-path delimiter",
                code="registry_path",
            )
        found = _closed(lesson["found_by"], _FOUND_KEYS, f"{lesson_id}.found_by")
        references = _closed(
            lesson["references"], _REFERENCE_KEYS, f"{lesson_id}.references"
        )
        for key in _FOUND_KEYS:
            _scalar(found, key, f"{lesson_id}.found_by")
        for key in _REFERENCE_KEYS:
            _scalar(references, key, f"{lesson_id}.references")
        for key in ("symptom", "root_cause", "fix", "prevention"):
            _scalar(lesson, key, lesson_id)
        if "notes" in lesson:
            _scalar(lesson, "notes", lesson_id)
        related = lesson["related"]
        if not isinstance(related, list) or any(
            not isinstance(value, str) for value in related
        ):
            raise FailureMemoryError(
                f"{lesson_id}.related must be a string array", code="registry_schema"
            )
        if len(related) != len(set(related)):
            raise FailureMemoryError(
                f"{lesson_id}.related contains duplicates", code="registry_schema"
            )
        lessons.append(lesson)
    for lesson in lessons:
        for related in lesson["related"]:
            if related == lesson["id"]:
                raise FailureMemoryError(
                    f"{related} cannot load itself", code="related_id"
                )
            if related not in seen:
                raise FailureMemoryError(
                    f"{lesson['id']} references unknown related lesson ID {related}",
                    code="related_id",
                )
    return tuple(lessons)


def _node_id(config: ProjectConfig, lesson_id: str) -> str:
    return f"{config.node_namespace}-{lesson_id.lower()}"


def _tag(source: str, prefix: str, config: ProjectConfig) -> str | None:
    normalized = unicodedata.normalize("NFKD", source)
    characters = [
        character if character.isascii() else " "
        for character in normalized
        if not unicodedata.category(character).startswith("M")
    ]
    tokens = _TOKEN_RE.findall("".join(characters).lower())[
        : int(config.taxonomy["max_tokens"])
    ]
    if not tokens:
        return None
    raw = f"{prefix}-{'-'.join(tokens)}"
    maximum = int(config.taxonomy["max_tag_length"])
    if len(raw) <= maximum:
        return raw
    digest = hashlib.sha256(raw.encode()).hexdigest()[:12]
    keep = maximum - 13
    return f"{raw[:keep].rstrip('-')}-{digest}"


def _frontmatter(lesson: dict[str, Any], config: ProjectConfig) -> dict[str, Any]:
    taxonomy = config.taxonomy
    sources = (
        (lesson["location"]["area"], taxonomy["area_prefix"]),
        (lesson["location"]["package"], taxonomy["package_prefix"]),
        (lesson["location"]["module"], taxonomy["module_prefix"]),
        (lesson["location"]["symbol"], taxonomy["symbol_prefix"]),
        (lesson["found_by"]["type"], taxonomy["found_by_prefix"]),
        (lesson["location"]["line_hint"], taxonomy["line_hint_prefix"]),
    )
    tags = {
        tag for source, prefix in sources if (tag := _tag(source, str(prefix), config))
    }
    node_id = _node_id(config, lesson["id"])
    return {
        "id": node_id,
        "title": f"{lesson['id']}: {lesson['location']['line_hint']}",
        "domain": config.domain,
        "subdomain": config.subdomain,
        "tags": sorted(tags, key=lambda value: value.encode("utf-8")),
        "status": "established",
        "confidence": 0.99,
        "source": "human",
        "confidence_floor": 0.95,
        "edges": [],
        "load_with": [
            _node_id(config, related)
            for related in sorted(lesson["related"], key=lambda value: int(value[1:]))
        ],
        "context_size": "small",
        "reading_priority": "full",
        "content_ref": PurePosixPath(
            config.paths["generated_nodes"], f"{node_id}.md"
        ).as_posix(),
        "akms_schema": "v2",
    }


def _bullet(label: str, value: str) -> str:
    return f"- {label}: {value}" if value else f"- {label}:"


def _content(lesson: dict[str, Any], source_sha256: str, config: ProjectConfig) -> str:
    compatibility = config.compatibility
    lines = [
        compatibility["generated_warning"],
        f"{compatibility['source_hash_prefix']}{source_sha256}{compatibility['source_hash_suffix']}",
        "",
        f"# {lesson['id']}: {lesson['location']['line_hint']}",
        "",
        "## Identity",
        "",
        _bullet("Registry ID", lesson["id"]),
        "",
        "## Location",
        "",
        _bullet("Area", lesson["location"]["area"]),
        _bullet("Package", lesson["location"]["package"]),
        _bullet("Module", lesson["location"]["module"]),
        _bullet("File", lesson["location"]["file"]),
        _bullet("Symbol", lesson["location"]["symbol"]),
        _bullet("Line hint", lesson["location"]["line_hint"]),
        "",
        "## Discovery",
        "",
        _bullet("Type", lesson["found_by"]["type"]),
        _bullet("Trigger", lesson["found_by"]["trigger"]),
        "",
        "## Failure",
        "",
        "### Symptom",
        "",
        lesson["symptom"],
        "",
        "### Root cause",
        "",
        lesson["root_cause"],
        "",
        "### Fix",
        "",
        lesson["fix"],
        "",
        "### Prevention",
        "",
        lesson["prevention"],
        "",
        "## Timeline",
        "",
        f"- Found: {lesson['date_found']} ({lesson['date_found_precision']})",
        f"- Fixed: {lesson['date_fixed']} ({lesson['date_fixed_precision']})",
        "",
        "## References",
        "",
        _bullet("Commit", lesson["references"]["commit"]),
        _bullet("Issue", lesson["references"]["issue"]),
        _bullet("PR", lesson["references"]["pr"]),
        _bullet("Plan", lesson["references"]["plan"]),
    ]
    if "notes" in lesson:
        lines.extend(("", "## Notes", "", lesson["notes"]))
    return "\n".join(lines) + "\n"


def serialize_node(node: CompiledNode) -> bytes:
    frontmatter = "\n".join(
        f"{key}: {json.dumps(value, ensure_ascii=False, separators=(',', ':'))}"
        for key, value in node.frontmatter.items()
    )
    return f"---\n{frontmatter}\n---\n{node.content}".encode("utf-8")


def _path_pattern(config: ProjectConfig, *, separators: str = "/") -> re.Pattern[str]:
    roots = "|".join(re.escape(value) for value in config.validation["allowed_roots"])
    files = "|".join(re.escape(value) for value in config.validation["root_files"])
    slash = r"[/\\]" if separators == "both" else "/"
    segment = r"(?:(?!\.{1,2}(?:[/\\]|$))[A-Za-z0-9_@+.-]*[A-Za-z0-9_@+-])"
    rooted = rf"(?:{roots}){slash}{segment}(?:{slash}{segment})*"
    return re.compile(rf"^(?:{rooted}|(?:{files}))$")


def _expand_location_file(value: str, config: ProjectConfig) -> tuple[str, ...]:
    separator = str(config.validation["location_file_separator"])
    route = _path_pattern(config)
    parts = value.split(separator)
    if not parts or route.fullmatch(parts[0]) is None:
        raise FailureMemoryError(
            f"Invalid location.file repository path: {value!r}", code="registry_path"
        )
    resolved = [parts[0]]
    continuation = re.compile(r"^(?!\.{1,2}$)[A-Za-z0-9_@+.-]*[A-Za-z0-9_@+-]$")
    for part in parts[1:]:
        candidate = (
            part
            if route.fullmatch(part)
            else (PurePosixPath(resolved[-1]).parent / part).as_posix()
        )
        if continuation.fullmatch(part) is None and route.fullmatch(part) is None:
            raise FailureMemoryError(
                f"Invalid location.file repository path: {value!r}",
                code="registry_path",
            )
        if route.fullmatch(candidate) is None:
            raise FailureMemoryError(
                f"Invalid location.file repository path: {value!r}",
                code="registry_path",
            )
        resolved.append(candidate)
    return tuple(resolved)


def _prose_pattern(config: ProjectConfig) -> re.Pattern[str]:
    roots = "|".join(re.escape(value) for value in config.validation["allowed_roots"])
    files = "|".join(re.escape(value) for value in config.validation["root_files"])
    segment = r"(?:(?!\.{1,2}(?:[/\\]|$))[A-Za-z0-9_@+.-]*[A-Za-z0-9_@+-])"
    path = rf"(?:(?:{roots})[/\\]{segment}(?:[/\\]{segment})*|(?:{files}))"
    return re.compile(
        rf"(?:^|[\s`'\x22(\[{{<,;])((?:\.[/\\])?{path}(?:::[A-Za-z0-9_@+.\[\]-]+)*)(?=$|[\s`'\x22)\]}}>;,]|\.(?=$|\s))"
    )


def _extract_prose_paths(
    prose: str, config: ProjectConfig
) -> tuple[tuple[str, str], ...]:
    route = _path_pattern(config)
    extracted: list[tuple[str, str]] = []
    for match in _prose_pattern(config).finditer(prose):
        matched = match.group(1)
        normalized = matched[2:] if matched.startswith(("./", ".\\")) else matched
        normalized = normalized.split("::", 1)[0].replace("\\", "/")
        if route.fullmatch(normalized) is None:
            raise FailureMemoryError(
                f"Strict path extractor produced invalid route {normalized!r}",
                code="registry_path",
            )
        extracted.append((normalized, matched))
    return tuple(extracted)


def _route_records(
    routes: dict[str, dict[str, set[tuple[str, str]]]],
) -> dict[str, list[dict[str, Any]]]:
    rendered: dict[str, list[dict[str, Any]]] = {}
    for route_key in sorted(routes, key=lambda value: value.encode("utf-8")):
        selections = []
        for node_id in sorted(
            routes[route_key], key=lambda value: value.encode("utf-8")
        ):
            reasons = sorted(
                routes[route_key][node_id],
                key=lambda item: (item[0].encode(), item[1].encode()),
            )
            selections.append(
                {
                    "node_id": node_id,
                    "reasons": [
                        {"source_field": source_field, "matched_text": matched_text}
                        for source_field, matched_text in reasons
                    ],
                }
            )
        rendered[route_key] = selections
    return rendered


def _add(
    routes: dict[str, dict[str, set[tuple[str, str]]]],
    path: str,
    node_id: str,
    source: str,
    matched: str,
) -> None:
    routes.setdefault(path, {}).setdefault(node_id, set()).add((source, matched))


def _compile_routes(
    lessons: tuple[dict[str, Any], ...],
    source_sha256: str,
    config: ProjectConfig,
    repository_root: Path,
) -> tuple[dict[str, Any], tuple[dict[str, str], ...]]:
    by_path: dict[str, dict[str, set[tuple[str, str]]]] = {}
    by_symbol: dict[str, dict[str, set[tuple[str, str]]]] = {}
    for lesson in sorted(lessons, key=lambda item: int(item["id"][1:])):
        node_id = _node_id(config, lesson["id"])
        paths = _expand_location_file(lesson["location"]["file"], config)
        for path in paths:
            _add(by_path, path, node_id, "location.file", path)
            symbol = lesson["location"]["symbol"]
            if (
                symbol
                and _SYMBOL_RE.fullmatch(symbol)
                and repository_root.joinpath(*PurePosixPath(path).parts).is_file()
            ):
                _add(by_symbol, f"{path}::{symbol}", node_id, "location.symbol", symbol)
        for source_field, prose in (
            ("found_by.trigger", lesson["found_by"]["trigger"]),
            ("prevention", lesson["prevention"]),
        ):
            for path, matched in _extract_prose_paths(prose, config):
                _add(by_path, path, node_id, source_field, matched)
    canonical = {
        "contract_version": config.compatibility["route_contract_version"],
        "compiler_version": config.compatibility["compiler_version"],
        "source_schema_version": int(config.validation["registry_schema_version"]),
        "source_sha256": source_sha256,
        "match_semantics": "exact-repository-relative-path",
        "by_path": _route_records(by_path),
        "by_symbol": _route_records(by_symbol),
    }
    node_to_lesson = {
        _node_id(config, lesson["id"]): lesson["id"] for lesson in lessons
    }
    warnings = []
    for path, selections in canonical["by_path"].items():
        if repository_root.joinpath(*PurePosixPath(path).parts).exists():
            continue
        for selection in selections:
            warnings.append(
                {
                    "severity": "warning",
                    "code": "missing-historical-path",
                    "lesson_id": node_to_lesson[selection["node_id"]],
                    "path": path,
                    "message": "Historical source path does not exist in this checkout; the exact route is retained.",
                }
            )

    def warning_key(item: dict[str, str]) -> tuple[bytes, ...]:
        return tuple(
            item[key].encode("utf-8")
            for key in ("severity", "code", "lesson_id", "path", "message")
        )

    return canonical, tuple(sorted(warnings, key=warning_key))


def adapt_routes(canonical: dict[str, Any], config: ProjectConfig) -> dict[str, Any]:
    def adapt(
        records: dict[str, list[dict[str, Any]]],
    ) -> dict[str, list[dict[str, Any]]]:
        result = {}
        for route_key, selections in records.items():
            result[route_key] = []
            for selection in selections:
                source_fields = sorted(
                    {reason["source_field"] for reason in selection["reasons"]},
                    key=lambda value: value.encode(),
                )
                reason = "; ".join(
                    _REASON_TEXT[field] if index == 0 else _REASON_TEXT[field].lower()
                    for index, field in enumerate(source_fields)
                )
                result[route_key].append(
                    {
                        "node_id": selection["node_id"],
                        "reason": reason,
                        "provenance": {
                            "adapter_version": config.compatibility[
                                "route_adapter_version"
                            ],
                            "canonical_contract_version": canonical["contract_version"],
                            "compiler_version": canonical["compiler_version"],
                            "source_schema_version": canonical["source_schema_version"],
                            "source_sha256": canonical["source_sha256"],
                            "match_semantics": canonical["match_semantics"],
                            "reasons": [dict(value) for value in selection["reasons"]],
                        },
                    }
                )
        return result

    adapted = {
        "schema_version": "v1",
        "source_hash": f"sha256:{canonical['source_sha256']}",
        "by_path": adapt(canonical["by_path"]),
        "by_symbol": adapt(canonical["by_symbol"]),
    }
    parse_route_index(adapted)
    return adapted


def serialize_routes(adapted: dict[str, Any]) -> bytes:
    return (json.dumps(adapted, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def compile_registry(config: ProjectConfig, repository_root: str | Path) -> Compilation:
    root = Path(repository_root).resolve(strict=True)
    registry_path = config.resolve(root, "registry")
    try:
        source = registry_path.read_bytes()
    except OSError as exc:
        raise FailureMemoryError(
            f"Cannot read registry {registry_path}: {exc}", code="registry_load"
        ) from exc
    lessons = validate_registry_bytes(source, registry_path, config)
    source_sha256 = hashlib.sha256(source).hexdigest()
    nodes = tuple(
        CompiledNode(
            lesson_id=lesson["id"],
            node_id=_node_id(config, lesson["id"]),
            frontmatter=_frontmatter(lesson, config),
            content=_content(lesson, source_sha256, config),
        )
        for lesson in sorted(lessons, key=lambda item: int(item["id"][1:]))
    )
    canonical, warnings = _compile_routes(lessons, source_sha256, config, root)
    if config.validation["missing_path_policy"] == "error" and warnings:
        raise FailureMemoryError(
            "Configured current paths are missing",
            code="missing_path",
            details={"paths": [item["path"] for item in warnings]},
        )
    return Compilation(
        source_sha256=source_sha256,
        source_schema_version=int(config.validation["registry_schema_version"]),
        nodes=nodes,
        canonical_routes=canonical,
        adapted_routes=adapt_routes(canonical, config),
        warnings=warnings,
    )


def _target(root: Path, relative: str) -> Path:
    resolved_root = root.resolve(strict=True)
    candidate = resolved_root
    parts = PurePosixPath(relative).parts
    for index, part in enumerate(parts):
        candidate = candidate / part
        if candidate.is_symlink():
            raise FailureMemoryError(
                f"Output path {relative!r} contains symlink component {candidate}",
                code="path_escape",
            )
        resolved = candidate.resolve(strict=False)
        if not resolved.is_relative_to(resolved_root):
            raise FailureMemoryError(
                f"Output path {relative!r} escapes output root", code="path_escape"
            )
        if index < len(parts) - 1 and candidate.exists() and not candidate.is_dir():
            raise FailureMemoryError(
                f"Output path component is not a directory: {candidate}",
                code="path_escape",
            )
    return candidate


def _atomic_replace(root: Path, path: Path, content: bytes) -> None:
    relative = path.relative_to(root).as_posix()
    safe_path = _target(root, relative)
    if safe_path != path or (path.exists() and not path.is_file()):
        raise FailureMemoryError(
            f"Refusing unsafe output target {path}", code="path_escape"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    _target(root, relative)
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


def _publish_transaction(
    root: Path,
    expected: dict[Path, bytes],
    publish: list[Path],
    stale: list[Path],
) -> None:
    touched = sorted(set(publish + stale), key=lambda path: path.as_posix().encode())
    prior: dict[Path, bytes | None] = {}
    for path in touched:
        relative = path.relative_to(root).as_posix()
        _target(root, relative)
        if path.exists() and not path.is_file():
            raise FailureMemoryError(
                f"Refusing non-file output target {path}", code="path_escape"
            )
        prior[path] = path.read_bytes() if path.exists() else None
    try:
        for path in publish:
            _atomic_replace(root, path, expected[path])
        for path in stale:
            _target(root, path.relative_to(root).as_posix())
            path.unlink()
    except BaseException as original:
        rollback_errors: list[str] = []
        for path in reversed(touched):
            content = prior[path]
            try:
                if content is None:
                    if path.exists():
                        _target(root, path.relative_to(root).as_posix())
                        if not path.is_file():
                            raise FailureMemoryError(
                                f"Rollback target is not a file: {path}",
                                code="publication_rollback",
                            )
                        path.unlink()
                else:
                    _atomic_replace(root, path, content)
            except BaseException as rollback_error:
                rollback_errors.append(f"{path}: {rollback_error}")
        if rollback_errors:
            raise FailureMemoryError(
                "Publication failed and rollback was incomplete: "
                + "; ".join(rollback_errors),
                code="publication_rollback",
            ) from original
        raise


def _frontmatter_id(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    if not text.startswith("---\n"):
        return None
    try:
        raw = text.split("---\n", 2)[1]
        value = yaml.safe_load(raw)
    except (IndexError, yaml.YAMLError):
        return None
    return (
        value.get("id")
        if isinstance(value, dict) and isinstance(value.get("id"), str)
        else None
    )


def _validate_collisions(
    compilation: Compilation, generated: Path, local_nodes: Path, global_vault: Path
) -> None:
    if generated == local_nodes or not generated.is_relative_to(local_nodes):
        raise FailureMemoryError(
            "Generated nodes must be strictly beneath local-nodes root",
            code="path_escape",
        )
    output_ids = {node.node_id for node in compilation.nodes}
    collisions = []
    for origin, root in (("global", global_vault), ("local", local_nodes)):
        if root.exists() and not root.is_dir():
            raise FailureMemoryError(
                f"{origin} vault is not a directory", code="vault_invalid"
            )
        for path in sorted(root.glob("**/*.md")) if root.exists() else ():
            if origin == "local" and path.is_relative_to(generated):
                continue
            node_id = _frontmatter_id(path)
            if node_id in output_ids:
                collisions.append(
                    f"{node_id} in {origin}:{path.relative_to(root).as_posix()}"
                )
    if collisions:
        raise FailureMemoryError(
            "Output ID collision(s): " + "; ".join(collisions), code="node_collision"
        )


def run_compiler(
    *,
    config_path: str | Path,
    repository_root: str | Path,
    global_vault: str | Path | None = None,
    output_root: str | Path | None = None,
    mode: str = "write",
) -> dict[str, Any]:
    """Validate, compare, and atomically publish configured deterministic outputs."""
    if mode not in {"write", "check", "validate", "dry-run"}:
        raise FailureMemoryError(f"Unsupported compiler mode {mode!r}", code="usage")
    config = load_project_config(config_path)
    repo = Path(repository_root).resolve(strict=True)
    raw_destination = Path(output_root).expanduser() if output_root else repo
    if raw_destination.is_symlink():
        raise FailureMemoryError(
            "Output root must not be a symlink", code="path_escape"
        )
    destination_root = raw_destination.resolve(strict=False)
    # Only mode="write" may create filesystem structure. validate/check/
    # dry-run are read-only compiler modes and must create nothing --
    # including destination_root itself and the lock's parent directory
    # (create_parent_directories below) -- even when the caller passes an
    # explicit output_root that does not yet exist. The comparison logic
    # below already handles a nonexistent destination_root/generated
    # directory correctly (Path.exists() is False, everything reports as
    # "added"/missing), so no destination_root.is_dir() guard is needed.
    if mode == "write":
        destination_root.mkdir(parents=True, exist_ok=True)
    with ProjectLock(
        config.resolve(repo, "lock"),
        timeout_seconds=float(config.toolchain["timeout_seconds"]),
        create_parent_directories=(mode == "write"),
    ):
        compilation = compile_registry(config, repo)
        if mode == "validate":
            return {
                "status": "valid",
                "mode": mode,
                "source_sha256": compilation.source_sha256,
                "counts": {
                    "lessons": len(compilation.nodes),
                    "path_routes": len(compilation.canonical_routes["by_path"]),
                    "warnings": len(compilation.warnings),
                },
                "warnings": list(compilation.warnings),
                "config_fingerprint": config.fingerprint,
            }
        generated = _target(destination_root, config.paths["generated_nodes"])
        local_nodes = _target(destination_root, config.paths["local_nodes"])
        routes = _target(destination_root, config.paths["routes"])
        if global_vault is None:
            raise FailureMemoryError(
                "An explicit read-only global vault is required",
                code="global_vault_required",
            )
        _validate_collisions(
            compilation, generated, local_nodes, Path(global_vault).resolve()
        )
        expected = {
            generated / f"{node.node_id}.md": serialize_node(node)
            for node in compilation.nodes
        }
        expected[routes] = serialize_routes(compilation.adapted_routes)
        added, changed = [], []
        for path, content in expected.items():
            if not path.exists():
                added.append(path)
            elif path.read_bytes() != content:
                changed.append(path)
        expected_nodes = {path for path in expected if path.parent == generated}
        stale = (
            [
                path
                for path in generated.glob(f"{config.node_namespace}-*.md")
                if path not in expected_nodes
                and _frontmatter_id(path) == path.stem
                and config.compatibility["generated_warning"]
                in path.read_text(encoding="utf-8")
            ]
            if generated.is_dir()
            else []
        )

        def key(path: Path) -> bytes:
            return path.as_posix().encode("utf-8")

        added, changed, stale = map(
            lambda values: sorted(values, key=key), (added, changed, stale)
        )
        if mode == "write":
            _publish_transaction(destination_root, expected, added + changed, stale)
        drift = bool(added or changed or stale)

        def display(values: list[Path]) -> list[str]:
            return [path.relative_to(destination_root).as_posix() for path in values]

        status = (
            "drift"
            if mode == "check" and drift
            else "clean"
            if mode == "check"
            else "dry-run"
            if mode == "dry-run"
            else "written"
        )
        return {
            "status": status,
            "mode": mode,
            "source_sha256": compilation.source_sha256,
            "counts": {
                "lessons": len(compilation.nodes),
                "path_routes": len(compilation.canonical_routes["by_path"]),
                "added": len(added),
                "changed": len(changed),
                "stale": len(stale),
                "warnings": len(compilation.warnings),
            },
            "added": display(added),
            "changed": display(changed),
            "stale": display(stale),
            "written": display(added + changed) if mode == "write" else [],
            "warnings": list(compilation.warnings),
            "config_fingerprint": config.fingerprint,
        }


__all__ = [
    "Compilation",
    "CompiledNode",
    "adapt_routes",
    "compile_registry",
    "run_compiler",
    "serialize_node",
    "serialize_routes",
    "validate_registry_bytes",
]
