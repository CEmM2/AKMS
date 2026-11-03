"""Configuration-driven deterministic lesson compiler and exact-route generator."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

import yaml
from akms.task_context.routes import parse_route_index

from akms_failure_memory.annotations import (
    DIRECTORY_ANNOTATIONS_NAME,
    LessonAnnotations,
    load_annotations,
)
from akms_failure_memory.config import ProjectConfig, load_project_config
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.lesson_ids import lesson_id_sort_key
from akms_failure_memory.lesson_index import (
    build_lesson_index,
    is_generated_index,
    lesson_index_paths,
    record_title,
    render_lesson_index_markdown,
    serialize_lesson_index,
)
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
    lessons: tuple[dict[str, Any], ...] = field(default=())


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


_V2_META_NAME = "_registry.json"


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize one registry JSON object without reordering its keys."""
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _json_object(data: bytes, source: Path) -> dict[str, Any]:
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FailureMemoryError(
            f"Cannot load registry {source}: {exc}", code="registry_load"
        ) from exc
    if not isinstance(raw, dict):
        raise FailureMemoryError(
            f"Registry file {source.name} must be a JSON object",
            code="registry_schema",
        )
    return raw


def _directory_digest(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def load_directory_registry(
    directory: Path, config: ProjectConfig
) -> tuple[tuple[dict[str, Any], ...], str]:
    """Load a schema 2 directory and return its lessons plus the v2 digest.

    ``_registry.json`` must declare schema version 2. Callers select this
    loader; the project config may still say version 1 while a migration
    check is compiling the staged directory.
    """
    if directory.is_symlink() or not directory.is_dir():
        raise FailureMemoryError(
            f"Registry schema 2 requires a directory: {directory}",
            code="registry_schema",
        )
    try:
        entries = list(directory.iterdir())
    except OSError as exc:
        raise FailureMemoryError(
            f"Cannot read registry {directory}: {exc}", code="registry_load"
        ) from exc
    id_pattern = re.compile(str(config.validation["id_pattern"]))
    accepted: list[Path] = []
    lesson_paths: list[Path] = []
    for entry in entries:
        name = entry.name
        if entry.is_symlink() or not entry.is_file():
            raise FailureMemoryError(
                f"Registry contains stray path {name}",
                code="registry_schema",
            )
        if name == _V2_META_NAME:
            accepted.append(entry)
            continue
        if name == DIRECTORY_ANNOTATIONS_NAME:
            # The review sidecar is not a lesson and not part of the digest:
            # annotating a lesson must not move its generated node.
            continue
        if not name.endswith(".json"):
            raise FailureMemoryError(
                f"Registry contains stray path {name}",
                code="registry_schema",
            )
        stem = name[: -len(".json")]
        if id_pattern.fullmatch(stem) is None:
            raise FailureMemoryError(
                f"Malformed lesson ID {stem!r}", code="registry_id"
            )
        accepted.append(entry)
        lesson_paths.append(entry)
    if not any(path.name == _V2_META_NAME for path in accepted):
        raise FailureMemoryError(
            "Registry is missing _registry.json",
            code="registry_schema",
        )
    meta_path = directory / _V2_META_NAME
    meta = _json_object(meta_path.read_bytes(), meta_path)
    if set(meta) != {"schema_version", "_field_spec"}:
        raise FailureMemoryError(
            "Directory registry _registry.json must contain only "
            "schema_version and _field_spec",
            code="registry_schema",
        )
    schema_version = meta["schema_version"]
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != 2
    ):
        raise FailureMemoryError(
            "Unsupported registry schema_version", code="registry_schema"
        )
    if not isinstance(meta["_field_spec"], dict):
        raise FailureMemoryError(
            "Registry field types are invalid", code="registry_schema"
        )
    parsed: list[dict[str, Any]] = []
    stems: list[str] = []
    for path in lesson_paths:
        parsed.append(_json_object(path.read_bytes(), path))
        stems.append(path.name[: -len(".json")])
    lessons = validate_lesson_records(parsed, config)
    for stem, lesson in zip(stems, lessons, strict=True):
        if stem != lesson["id"]:
            raise FailureMemoryError(
                f"Lesson file {stem}.json does not match id {lesson['id']!r}",
                code="registry_id",
            )
    ordered = tuple(sorted(lessons, key=lambda item: lesson_id_sort_key(item["id"])))
    return ordered, _directory_digest(accepted)


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


def validate_lesson_records(
    items: list[Any], config: ProjectConfig
) -> tuple[dict[str, Any], ...]:
    """Validate lesson objects. Shared by the v1 file and the v2 directory."""
    lessons: list[dict[str, Any]] = []
    seen: set[str] = set()
    id_pattern = re.compile(str(config.validation["id_pattern"]))
    for index, item in enumerate(items):
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


def validate_registry_bytes(
    data: bytes, source: Path, config: ProjectConfig
) -> tuple[dict[str, Any], ...]:
    """Validate the canonical append-only v1 registry without mutating it."""
    registry = _decode_registry(data, source, config)
    return validate_lesson_records(registry["lessons"], config)


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


def _title(lesson: dict[str, Any], config: ProjectConfig) -> str:
    # Without a lesson-index contract the title stays the line hint, which is
    # what every compiled pack and committed node was built with.
    if config.lesson_index_version is None:
        return f"{lesson['id']}: {lesson['location']['line_hint']}"
    title = record_title(lesson)
    return f"{lesson['id']}: {title}" if title else lesson["id"]


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
        "title": _title(lesson, config),
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
            for related in sorted(lesson["related"], key=lesson_id_sort_key)
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
        f"# {_title(lesson, config)}",
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
    for lesson in sorted(lessons, key=lambda item: lesson_id_sort_key(item["id"])):
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


def _config_for_schema(config: ProjectConfig, schema_version: int) -> ProjectConfig:
    if schema_version == config.validation["registry_schema_version"]:
        return config
    validation = dict(config.validation)
    validation["registry_schema_version"] = schema_version
    return replace(config, validation=MappingProxyType(validation))


def compilation_from_lessons(
    config: ProjectConfig,
    repository_root: str | Path,
    lessons: tuple[dict[str, Any], ...],
    source_sha256: str,
    *,
    source_schema_version: int | None = None,
) -> Compilation:
    """Compile already-loaded lessons. ``source_schema_version`` overrides config."""
    version = (
        int(config.validation["registry_schema_version"])
        if source_schema_version is None
        else source_schema_version
    )
    effective = _config_for_schema(config, version)
    root = Path(repository_root).resolve(strict=True)
    ordered = tuple(sorted(lessons, key=lambda item: lesson_id_sort_key(item["id"])))
    nodes = tuple(
        CompiledNode(
            lesson_id=lesson["id"],
            node_id=_node_id(effective, lesson["id"]),
            frontmatter=_frontmatter(lesson, effective),
            content=_content(lesson, source_sha256, effective),
        )
        for lesson in ordered
    )
    canonical, warnings = _compile_routes(lessons, source_sha256, effective, root)
    if effective.validation["missing_path_policy"] == "error" and warnings:
        raise FailureMemoryError(
            "Configured current paths are missing",
            code="missing_path",
            details={"paths": [item["path"] for item in warnings]},
        )
    return Compilation(
        source_sha256=source_sha256,
        source_schema_version=int(effective.validation["registry_schema_version"]),
        nodes=nodes,
        canonical_routes=canonical,
        adapted_routes=adapt_routes(canonical, effective),
        warnings=warnings,
        lessons=ordered,
    )


def _load_registry(
    config: ProjectConfig, registry_path: Path
) -> tuple[tuple[dict[str, Any], ...], str]:
    version = config.validation["registry_schema_version"]
    if version == 1:
        if registry_path.is_dir():
            raise FailureMemoryError(
                "Registry schema 1 requires a file, not a directory",
                code="registry_schema",
            )
        try:
            source = registry_path.read_bytes()
        except OSError as exc:
            raise FailureMemoryError(
                f"Cannot read registry {registry_path}: {exc}", code="registry_load"
            ) from exc
        lessons = validate_registry_bytes(source, registry_path, config)
        return lessons, hashlib.sha256(source).hexdigest()
    if version == 2:
        if registry_path.is_symlink() or registry_path.is_file():
            raise FailureMemoryError(
                "Registry schema 2 requires a directory, not a file",
                code="registry_schema",
            )
        if not registry_path.is_dir():
            raise FailureMemoryError(
                f"Cannot read registry {registry_path}: not a directory",
                code="registry_load",
            )
        return load_directory_registry(registry_path, config)
    raise FailureMemoryError(
        "registry_schema_version must be 1 or 2",
        code="schema_version",
    )


def compile_registry(config: ProjectConfig, repository_root: str | Path) -> Compilation:
    root = Path(repository_root).resolve(strict=True)
    registry_path = config.resolve(root, "registry")
    lessons, source_sha256 = _load_registry(config, registry_path)
    return compilation_from_lessons(config, root, lessons, source_sha256)


def compile_lesson_index(
    lessons: tuple[dict[str, Any], ...],
    config: ProjectConfig,
    *,
    source_sha256: str,
    annotations: LessonAnnotations,
) -> dict[str, Any]:
    """Build the lesson index for validated lessons and annotations."""
    return build_lesson_index(
        lessons,
        config,
        node_ids={lesson["id"]: _node_id(config, lesson["id"]) for lesson in lessons},
        source_sha256=source_sha256,
        source_schema_version=int(config.validation["registry_schema_version"]),
        annotations=annotations,
    )


def _route_signature(routes: dict[str, Any], *, adapted: bool) -> dict[str, Any]:
    cloned = json.loads(json.dumps(routes))
    if adapted:
        cloned["source_hash"] = None
        for table in ("by_path", "by_symbol"):
            for selections in cloned[table].values():
                for selection in selections:
                    provenance = selection["provenance"]
                    provenance["source_sha256"] = None
                    provenance["source_schema_version"] = None
        return cloned
    cloned["source_sha256"] = None
    cloned["source_schema_version"] = None
    return cloned


def assert_migrated_outputs_match(
    before: Compilation, after: Compilation, config: ProjectConfig
) -> None:
    """Node bodies and routes may change only the digest and schema version."""
    if before.source_schema_version != 1 or after.source_schema_version != 2:
        raise FailureMemoryError(
            "Migration comparison expected schema versions 1 and 2",
            code="migration_delta",
        )
    if [node.lesson_id for node in before.nodes] != [
        node.lesson_id for node in after.nodes
    ]:
        raise FailureMemoryError(
            "Migration changed lesson identity or order",
            code="migration_delta",
        )
    prefix = str(config.compatibility["source_hash_prefix"])
    suffix = str(config.compatibility["source_hash_suffix"])
    expected_before = f"{prefix}{before.source_sha256}{suffix}"
    expected_after = f"{prefix}{after.source_sha256}{suffix}"
    for left, right in zip(before.nodes, after.nodes, strict=True):
        if left.node_id != right.node_id or left.frontmatter != right.frontmatter:
            raise FailureMemoryError(
                f"Migration changed node {left.lesson_id} beyond the source digest",
                code="migration_delta",
            )
        left_lines = left.content.splitlines()
        right_lines = right.content.splitlines()
        if before.source_sha256 == after.source_sha256:
            changed = left.content != right.content
        else:
            diffs = [
                (old, new)
                for old, new in zip(left_lines, right_lines, strict=False)
                if old != new
            ]
            changed = len(left_lines) != len(right_lines) or diffs != [
                (expected_before, expected_after)
            ]
        if changed:
            raise FailureMemoryError(
                f"Migration changed lesson body {left.lesson_id} beyond the source digest",
                code="migration_delta",
            )
    if before.canonical_routes["source_schema_version"] != 1:
        raise FailureMemoryError(
            "Schema 1 routes did not record source_schema_version 1",
            code="migration_delta",
        )
    if after.canonical_routes["source_schema_version"] != 2:
        raise FailureMemoryError(
            "Schema 2 routes did not record source_schema_version 2",
            code="migration_delta",
        )
    if before.canonical_routes["source_sha256"] != before.source_sha256:
        raise FailureMemoryError(
            "Schema 1 canonical routes do not embed the registry digest",
            code="migration_delta",
        )
    if after.canonical_routes["source_sha256"] != after.source_sha256:
        raise FailureMemoryError(
            "Schema 2 canonical routes do not embed the registry digest",
            code="migration_delta",
        )
    if _route_signature(before.canonical_routes, adapted=False) != _route_signature(
        after.canonical_routes, adapted=False
    ):
        raise FailureMemoryError(
            "Migration changed canonical routes beyond the source digest "
            "and schema version",
            code="migration_delta",
        )
    if before.adapted_routes["source_hash"] != f"sha256:{before.source_sha256}":
        raise FailureMemoryError(
            "Schema 1 adapted routes do not embed the registry digest",
            code="migration_delta",
        )
    if after.adapted_routes["source_hash"] != f"sha256:{after.source_sha256}":
        raise FailureMemoryError(
            "Schema 2 adapted routes do not embed the registry digest",
            code="migration_delta",
        )

    def provenance_rows(routes: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for table in ("by_path", "by_symbol"):
            for selections in routes[table].values():
                for selection in selections:
                    rows.append(selection["provenance"])
        return rows

    before_rows = provenance_rows(before.adapted_routes)
    after_rows = provenance_rows(after.adapted_routes)
    if len(before_rows) != len(after_rows):
        raise FailureMemoryError(
            "Migration changed adapted route provenance",
            code="migration_delta",
        )
    for left_row, right_row in zip(before_rows, after_rows, strict=True):
        if left_row["source_schema_version"] != 1 or left_row["source_sha256"] != (
            before.source_sha256
        ):
            raise FailureMemoryError(
                "Schema 1 provenance does not embed the registry digest",
                code="migration_delta",
            )
        if right_row["source_schema_version"] != 2 or right_row["source_sha256"] != (
            after.source_sha256
        ):
            raise FailureMemoryError(
                "Schema 2 provenance does not embed the registry digest",
                code="migration_delta",
            )
    if _route_signature(before.adapted_routes, adapted=True) != _route_signature(
        after.adapted_routes, adapted=True
    ):
        raise FailureMemoryError(
            "Migration changed adapted routes beyond the source digest "
            "and schema version",
            code="migration_delta",
        )
    if before.warnings != after.warnings:
        raise FailureMemoryError(
            "Migration changed compiler warnings",
            code="migration_delta",
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
        # The sidecar is validated in every mode, also without an index, so a
        # bad annotation fails `validate` rather than a later index read.
        annotations = load_annotations(
            config,
            config.resolve(repo, "registry"),
            [node.lesson_id for node in compilation.nodes],
        )
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
        index_paths = [
            _target(destination_root, relative)
            for relative in lesson_index_paths(config)
        ]
        stale_index: list[Path] = []
        if config.lesson_index_version is not None:
            if routes in index_paths or any(
                path.is_relative_to(local_nodes) for path in index_paths
            ):
                raise FailureMemoryError(
                    "The lesson index must not replace the route index or live "
                    "under the local-nodes root",
                    code="path_escape",
                )
            index = compile_lesson_index(
                compilation.lessons,
                config,
                source_sha256=compilation.source_sha256,
                annotations=annotations,
            )
            index_json, index_markdown = index_paths
            expected[index_json] = serialize_lesson_index(index)
            expected[index_markdown] = render_lesson_index_markdown(index, config)
        else:
            # A project that turned the index off keeps no stale copy of it.
            stale_index = [
                path
                for path in index_paths
                if path.is_file()
                and not path.is_symlink()
                and is_generated_index(path.name, path.read_bytes(), config)
            ]
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
        ) + stale_index

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
    "assert_migrated_outputs_match",
    "canonical_json_bytes",
    "compilation_from_lessons",
    "compile_lesson_index",
    "compile_registry",
    "load_directory_registry",
    "run_compiler",
    "serialize_node",
    "serialize_routes",
    "validate_lesson_records",
    "validate_registry_bytes",
]
