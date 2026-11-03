"""Versioned review annotations kept beside the lesson registry.

Lesson records are canonical and closed: their schema does not change. What a
reviewer later learns about a lesson -- its failure-mechanism categories,
which lessons contradict it, where it does not apply, what supersedes it --
lives in one sidecar instead:

* schema 1 (one file, ``lessons.json``): ``lessons.annotations.json`` next to it;
* schema 2 (a directory): ``_annotations.json`` inside it.

The sidecar is optional. It never changes a generated node or route, and it is
not part of the registry digest; the lesson index records its own digest.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any

from akms_failure_memory.config import ProjectConfig
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.lesson_ids import lesson_id_sort_key


ANNOTATIONS_SCHEMA_VERSION = "failure-lesson-annotations/v1"
DIRECTORY_ANNOTATIONS_NAME = "_annotations.json"
_TOP_KEYS = frozenset({"schema_version", "categories", "lessons"})
_ENTRY_KEYS = frozenset(
    {"categories", "contradicts", "exceptions", "superseded_by", "applicability"}
)
_CATEGORY_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


@dataclass(frozen=True)
class LessonAnnotations:
    """Validated annotations. ``sha256`` is ``None`` when no sidecar exists."""

    sha256: str | None = None
    categories: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    lessons: Mapping[str, Mapping[str, Any]] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def for_lesson(self, lesson_id: str) -> dict[str, Any]:
        """Return one lesson's annotations with every key present."""
        entry = self.lessons.get(lesson_id, {})
        return {
            "categories": list(entry.get("categories", ())),
            "contradicts": list(entry.get("contradicts", ())),
            "exceptions": list(entry.get("exceptions", ())),
            "superseded_by": entry.get("superseded_by"),
            "applicability": entry.get("applicability"),
        }


def annotations_path(config: ProjectConfig, registry_path: Path) -> Path:
    """Locate the sidecar for the configured registry form."""
    if config.validation["registry_schema_version"] == 2:
        return registry_path / DIRECTORY_ANNOTATIONS_NAME
    return registry_path.with_name(f"{registry_path.stem}.annotations.json")


def _schema_error(message: str) -> FailureMemoryError:
    return FailureMemoryError(message, code="annotations_schema")


def _strings(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise _schema_error(f"{field_name} must be an array of non-empty strings")
    if len(value) != len(set(value)):
        raise _schema_error(f"{field_name} contains duplicates")
    return list(value)


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise _schema_error(f"{field_name} must be a non-empty string")
    return value


def _known(lesson_id: str, target: str, known: set[str], field_name: str) -> None:
    if target == lesson_id:
        raise FailureMemoryError(
            f"{field_name} of {lesson_id} names the lesson itself",
            code="annotation_id",
        )
    if target not in known:
        raise FailureMemoryError(
            f"{field_name} of {lesson_id} names unknown lesson ID {target}",
            code="annotation_id",
        )


def validate_annotations(
    raw: Any, lesson_ids: Iterable[str], *, sha256: str | None = None
) -> LessonAnnotations:
    """Validate a decoded sidecar against the registry's lesson IDs."""
    known = set(lesson_ids)
    if not isinstance(raw, dict) or set(raw) != _TOP_KEYS:
        raise _schema_error(
            "Annotations must contain only schema_version, categories, lessons"
        )
    if raw["schema_version"] != ANNOTATIONS_SCHEMA_VERSION:
        raise _schema_error(
            f"Unsupported annotations schema_version {raw['schema_version']!r}"
        )
    if not isinstance(raw["categories"], dict):
        raise _schema_error("Annotations categories must be an object")
    categories: dict[str, str] = {}
    for name, description in raw["categories"].items():
        if _CATEGORY_RE.fullmatch(name) is None:
            raise _schema_error(f"Malformed annotation category {name!r}")
        categories[name] = _text(description, f"categories.{name}")
    if not isinstance(raw["lessons"], dict):
        raise _schema_error("Annotations lessons must be an object")
    unknown = [lesson_id for lesson_id in raw["lessons"] if lesson_id not in known]
    if unknown:
        raise FailureMemoryError(
            f"Annotations name unknown lesson ID {unknown[0]}",
            code="annotation_id",
        )
    lessons: dict[str, Mapping[str, Any]] = {}
    for lesson_id in sorted(raw["lessons"], key=lesson_id_sort_key):
        entry = raw["lessons"][lesson_id]
        if not isinstance(entry, dict) or not set(entry) <= _ENTRY_KEYS:
            raise _schema_error(f"Annotations for {lesson_id} have unexpected fields")
        normalized: dict[str, Any] = {}
        if "categories" in entry:
            names = _strings(entry["categories"], f"{lesson_id}.categories")
            undeclared = sorted(name for name in names if name not in categories)
            if undeclared:
                raise _schema_error(
                    f"{lesson_id} uses undeclared categories: {', '.join(undeclared)}"
                )
            normalized["categories"] = tuple(
                sorted(names, key=lambda value: value.encode("utf-8"))
            )
        if "contradicts" in entry:
            targets = _strings(entry["contradicts"], f"{lesson_id}.contradicts")
            for target in targets:
                _known(lesson_id, target, known, "contradicts")
            normalized["contradicts"] = tuple(sorted(targets, key=lesson_id_sort_key))
        if "exceptions" in entry:
            # Order is the reviewer's; exceptions read as a list of caveats.
            normalized["exceptions"] = tuple(
                _strings(entry["exceptions"], f"{lesson_id}.exceptions")
            )
        if "superseded_by" in entry:
            target = _text(entry["superseded_by"], f"{lesson_id}.superseded_by")
            _known(lesson_id, target, known, "superseded_by")
            normalized["superseded_by"] = target
        if "applicability" in entry:
            normalized["applicability"] = _text(
                entry["applicability"], f"{lesson_id}.applicability"
            )
        lessons[lesson_id] = MappingProxyType(normalized)
    for start in lessons:
        seen = {start}
        current = lessons[start].get("superseded_by")
        while current is not None:
            if current in seen:
                raise FailureMemoryError(
                    f"Supersession cycle through {start}", code="annotation_id"
                )
            seen.add(current)
            current = lessons.get(current, {}).get("superseded_by")
    return LessonAnnotations(
        sha256=sha256,
        categories=MappingProxyType(
            dict(sorted(categories.items(), key=lambda item: item[0].encode("utf-8")))
        ),
        lessons=MappingProxyType(lessons),
    )


def load_annotations(
    config: ProjectConfig, registry_path: Path, lesson_ids: Iterable[str]
) -> LessonAnnotations:
    """Load and validate the sidecar; an absent sidecar is empty, not an error."""
    path = annotations_path(config, registry_path)
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise _schema_error(f"Annotations sidecar is not a regular file: {path}")
    if not path.exists():
        return LessonAnnotations()
    try:
        data = path.read_bytes()
        raw = json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FailureMemoryError(
            f"Cannot load annotations {path}: {exc}", code="annotations_load"
        ) from exc
    return validate_annotations(
        raw, lesson_ids, sha256=hashlib.sha256(data).hexdigest()
    )


__all__ = [
    "ANNOTATIONS_SCHEMA_VERSION",
    "DIRECTORY_ANNOTATIONS_NAME",
    "LessonAnnotations",
    "annotations_path",
    "load_annotations",
    "validate_annotations",
]
