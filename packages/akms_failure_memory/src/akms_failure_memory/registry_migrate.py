"""Split a schema 1 lesson file into a schema 2 directory registry."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from akms_failure_memory.annotations import (
    DIRECTORY_ANNOTATIONS_NAME,
    annotations_path,
    load_annotations,
)
from akms_failure_memory.compiler import (
    Compilation,
    assert_migrated_outputs_match,
    canonical_json_bytes,
    compilation_from_lessons,
    compile_registry,
    load_directory_registry,
    validate_registry_bytes,
)
from akms_failure_memory.config import ProjectConfig, load_project_config
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.locks import ProjectLock
from akms_failure_memory.record import _atomic_replace


def _destination(config: ProjectConfig, root: Path) -> tuple[str, Path]:
    old_rel = config.paths["registry"]
    new_rel = PurePosixPath(old_rel).with_suffix("").as_posix()
    if not new_rel or new_rel == old_rel:
        raise FailureMemoryError(
            "Cannot derive a directory path from the schema 1 registry",
            code="registry_schema",
        )
    if any(part in {"", ".", ".."} for part in PurePosixPath(new_rel).parts):
        raise FailureMemoryError(
            "Migration destination escapes repository root",
            code="path_escape",
        )
    destination = root.joinpath(*PurePosixPath(new_rel).parts)
    if not destination.parent.resolve(strict=False).is_relative_to(root):
        raise FailureMemoryError(
            "Migration destination escapes repository root",
            code="path_escape",
        )
    return new_rel, destination


def _read_v1(registry_path: Path, config: ProjectConfig) -> dict[str, Any]:
    if registry_path.is_dir() or not registry_path.is_file():
        raise FailureMemoryError(
            "registry migrate --to 2 requires a schema 1 file registry",
            code="registry_schema",
        )
    try:
        raw_bytes = registry_path.read_bytes()
    except OSError as exc:
        raise FailureMemoryError(
            f"Cannot read registry {registry_path}: {exc}", code="registry_load"
        ) from exc
    validate_registry_bytes(raw_bytes, registry_path, config)
    try:
        raw = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise FailureMemoryError(
            f"Cannot load registry {registry_path}: {exc}", code="registry_load"
        ) from exc
    return raw


def write_directory_registry(
    directory: Path, *, field_spec: Any, lessons: list[Any]
) -> None:
    """Write ``_registry.json`` and one unchanged lesson object per file."""
    if not isinstance(field_spec, dict):
        raise FailureMemoryError(
            "Registry field types are invalid", code="registry_schema"
        )
    directory.mkdir(parents=True, exist_ok=False)
    _atomic_replace(
        directory / "_registry.json",
        canonical_json_bytes({"schema_version": 2, "_field_spec": field_spec}),
    )
    seen: set[str] = set()
    for lesson in lessons:
        if not isinstance(lesson, dict) or not isinstance(lesson.get("id"), str):
            raise FailureMemoryError(
                "Registry field types are invalid", code="registry_schema"
            )
        lesson_id = lesson["id"]
        if lesson_id in seen:
            raise FailureMemoryError(
                f"Duplicate lesson ID {lesson_id}", code="duplicate_id"
            )
        seen.add(lesson_id)
        lesson_path = directory / f"{lesson_id}.json"
        if lesson_path.parent != directory:
            raise FailureMemoryError(
                f"Malformed lesson ID {lesson_id!r}", code="registry_id"
            )
        _atomic_replace(lesson_path, canonical_json_bytes(lesson))


def _rewrite_config_text(text: str, *, old_registry: str, new_registry: str) -> str:
    if "\n" in new_registry or '"' in new_registry or "'" in new_registry:
        raise FailureMemoryError(
            f"Cannot store registry path {new_registry!r}",
            code="invalid_config",
        )
    version_re = re.compile(r"^([ \t]*)registry_schema_version[ \t]*=[ \t]*1[ \t]*$")
    registry_re = re.compile(
        rf'^([ \t]*)registry[ \t]*=[ \t]*(["\']){re.escape(old_registry)}\2[ \t]*$'
    )
    lines = text.splitlines(keepends=True)
    bodies: list[str] = []
    endings: list[str] = []
    for line in lines:
        if line.endswith("\r\n"):
            endings.append("\r\n")
            bodies.append(line[:-2])
        elif line.endswith("\n"):
            endings.append("\n")
            bodies.append(line[:-1])
        else:
            endings.append("")
            bodies.append(line)
    version_at = [
        index for index, body in enumerate(bodies) if version_re.fullmatch(body)
    ]
    registry_at = [
        index for index, body in enumerate(bodies) if registry_re.fullmatch(body)
    ]
    if len(version_at) != 1 or len(registry_at) != 1:
        raise FailureMemoryError(
            "Cannot update project config: registry_schema_version and registry "
            "must each be one simple assignment",
            code="invalid_config",
        )
    version_match = version_re.fullmatch(bodies[version_at[0]])
    registry_match = registry_re.fullmatch(bodies[registry_at[0]])
    if version_match is None or registry_match is None:
        raise FailureMemoryError(
            "Cannot update project config: registry_schema_version and registry "
            "must each be one simple assignment",
            code="invalid_config",
        )
    bodies[version_at[0]] = f"{version_match.group(1)}registry_schema_version = 2"
    quote = registry_match.group(2)
    bodies[registry_at[0]] = (
        f"{registry_match.group(1)}registry = {quote}{new_registry}{quote}"
    )
    return "".join(body + ending for body, ending in zip(bodies, endings, strict=True))


def _annotations_to_carry(
    config: ProjectConfig, registry_path: Path, before: Compilation, new_rel: str
) -> str | None:
    """Validate the schema 1 annotations sidecar and name its schema 2 copy."""
    annotations = load_annotations(
        config, registry_path, [node.lesson_id for node in before.nodes]
    )
    if annotations.sha256 is None:
        return None
    return (PurePosixPath(new_rel) / DIRECTORY_ANNOTATIONS_NAME).as_posix()


def _compare_staged(
    config: ProjectConfig,
    root: Path,
    *,
    field_spec: Any,
    lessons: list[Any],
    before: Compilation,
) -> str:
    temporary = Path(tempfile.mkdtemp(prefix="failure-memory-migrate-"))
    try:
        if temporary.resolve().is_relative_to(root):
            raise FailureMemoryError(
                "Refusing to stage a migration check inside the repository",
                code="path_escape",
            )
        staged = temporary / "registry"
        write_directory_registry(staged, field_spec=field_spec, lessons=lessons)
        loaded, digest = load_directory_registry(staged, config)
        after = compilation_from_lessons(
            config,
            root,
            loaded,
            digest,
            source_schema_version=2,
        )
        assert_migrated_outputs_match(before, after, config)
        return digest
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def migrate_registry(
    *,
    config_path: str | Path,
    repository_root: str | Path,
    to: str,
    check: bool = False,
) -> dict[str, Any]:
    """Split a schema 1 file into a schema 2 directory.

    ``check`` compiles both forms outside the repository and writes nothing.
    A real migration leaves the original file in place.
    """
    if to != "2":
        raise FailureMemoryError(
            "registry migrate --to accepts only 2",
            code="usage",
        )
    config = load_project_config(config_path)
    root = Path(repository_root).resolve(strict=True)
    if config.validation["registry_schema_version"] != 1:
        raise FailureMemoryError(
            "registry migrate --to 2 requires a schema 1 file registry",
            code="registry_schema",
        )
    registry_path = config.resolve(root, "registry")
    old_rel = config.paths["registry"]
    new_rel, destination = _destination(config, root)
    if destination.exists() or destination.is_symlink():
        raise FailureMemoryError(
            f"Migration destination already exists: {new_rel}",
            code="file_exists",
        )
    if check:
        before = compile_registry(config, root)
        carried = _annotations_to_carry(config, registry_path, before, new_rel)
        raw = _read_v1(registry_path, config)
        digest = _compare_staged(
            config,
            root,
            field_spec=raw["_field_spec"],
            lessons=list(raw["lessons"]),
            before=before,
        )
        return {
            "status": "checked",
            "registry": old_rel,
            "would_write": new_rel,
            "registry_schema_version": 1,
            "source_sha256": before.source_sha256,
            "migrated_source_sha256": digest,
            "lesson_count": len(before.nodes),
            "previous_registry": old_rel,
            "annotations": carried,
        }
    lock_path = config.resolve(root, "lock")
    with ProjectLock(
        lock_path, timeout_seconds=float(config.toolchain["timeout_seconds"])
    ):
        before = compile_registry(config, root)
        carried = _annotations_to_carry(config, registry_path, before, new_rel)
        raw = _read_v1(registry_path, config)
        prior_registry = registry_path.read_bytes()
        _compare_staged(
            config,
            root,
            field_spec=raw["_field_spec"],
            lessons=list(raw["lessons"]),
            before=before,
        )
        if destination.exists() or destination.is_symlink():
            raise FailureMemoryError(
                f"Migration destination already exists: {new_rel}",
                code="file_exists",
            )
        prior_config = config.source_path.read_bytes()
        published = False
        config_written = False
        staging_root: Path | None = None
        try:
            # Publish only a complete directory. A failure while writing
            # lesson files must not leave a destination that the next
            # attempt rejects as already existing.
            staging_root = Path(
                tempfile.mkdtemp(
                    prefix=".failure-memory-migrate-",
                    dir=destination.parent,
                )
            )
            staged = staging_root / "registry"
            write_directory_registry(
                staged,
                field_spec=raw["_field_spec"],
                lessons=list(raw["lessons"]),
            )
            if carried is not None:
                # Copied, not moved: like the registry file, the schema 1
                # sidecar stays where it was.
                _atomic_replace(
                    staged / DIRECTORY_ANNOTATIONS_NAME,
                    annotations_path(config, registry_path).read_bytes(),
                )
            if destination.exists() or destination.is_symlink():
                raise FailureMemoryError(
                    f"Migration destination already exists: {new_rel}",
                    code="file_exists",
                )
            staged.replace(destination)
            published = True
            rewritten = _rewrite_config_text(
                prior_config.decode("utf-8"),
                old_registry=old_rel,
                new_registry=new_rel,
            )
            _atomic_replace(config.source_path, rewritten.encode("utf-8"))
            config_written = True
            migrated = load_project_config(config.source_path)
            after = compile_registry(migrated, root)
            assert_migrated_outputs_match(before, after, config)
            if registry_path.read_bytes() != prior_registry:
                raise FailureMemoryError(
                    "Migration changed the schema 1 registry file",
                    code="migration_delta",
                )
        except Exception:
            if config_written:
                _atomic_replace(config.source_path, prior_config)
            if published and (destination.exists() or destination.is_symlink()):
                shutil.rmtree(destination)
            raise
        finally:
            if staging_root is not None and staging_root.exists():
                shutil.rmtree(staging_root)
    return {
        "status": "migrated",
        "registry": new_rel,
        "previous_registry": old_rel,
        "registry_schema_version": 2,
        "source_sha256": after.source_sha256,
        "previous_source_sha256": before.source_sha256,
        "lesson_count": len(after.nodes),
        "annotations": carried,
    }


__all__ = ["migrate_registry", "write_directory_registry"]
