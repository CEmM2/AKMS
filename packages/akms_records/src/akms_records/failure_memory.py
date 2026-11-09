"""A read-only importer of ``akms-failure-memory`` registries.

``akms-records import --from-failure-memory <config>`` reads a project's lessons
into records of the built-in schema ``failure-lesson/v1``. It reads the project
config and the registry and writes nothing on that side: no lock, no generated
file, no sidecar. The registry stays the authority, and failure-memory goes on
routing its lessons by path; a record is a searchable copy.

**Own reader.** This module parses the documented formats itself instead of
importing ``akms_failure_memory``, which needs ``akms``. That keeps this package
free of a dependency, on the minimal install too, and a parity test holds the
reader to failure-memory's own loader. A lesson field the schema does not know
is refused rather than dropped, so what is imported is always the whole lesson.
An extra top-level key on the registry file (a note a project keeps beside
``lessons``) is ignored.

**Forms.** Schema 1 is one JSON file with ``schema_version``, ``_field_spec`` and
``lessons``. Schema 2 is a directory with ``_registry.json`` and one
``<id>.json`` per lesson. Review annotations sit beside the lessons
and are not lesson fields, so they are not read.

**Mapping.** The payload is the lesson, unchanged. ``source_refs`` hold
``{"kind": "failure-lesson", "ref": "<lesson id>", "note": "<repository id>"}``,
which is how a later import finds the record. ``origin.kind`` is ``import`` and
``review_state`` is ``unreviewed``: an import is no evidence of a review.

**Re-running.** The same lesson with the same content writes nothing. A changed
lesson is an amend, ``unreviewed`` again because the review was of other text.
A lesson removed upstream is reported and left alone: a missing lesson may be a
checkout of another branch, and retracting is a decision for a person. A record
that was retracted, superseded or erased stays that way; an erased one is
recognized from its deterministic ID, without the erasure log holding content.
"""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from akms_records.canonical import digest
from akms_records.citations import (
    FAILURE_LESSON_REF,
    is_failure_lesson,
    lesson_digest,
    lesson_schema,
)
from akms_records.envelope import MAX_SUMMARY, MAX_TAG, check_actor
from akms_records.errors import NotFound, RecordsError, ReplayError
from akms_records.ids import RECORD_ID_RE, record_id_for
from akms_records.schemas import RegisteredSchema, validate_instance

if TYPE_CHECKING:
    from akms_records.store import RecordStore

CONFIG_FORMAT = "failure-memory-project/v1"
SOURCE_KIND = "failure-lesson"
IMPORT_ACTOR = "failure-memory-import"
REGISTRY_META = "_registry.json"
ANNOTATIONS = "_annotations.json"
REGISTRY_V1_KEYS = {"schema_version", "_field_spec", "lessons"}
REGISTRY_V2_KEYS = {"schema_version", "_field_spec"}
ERASED_ID_ATTEMPTS = 4
_TAG_UNSAFE = re.compile(r"[^A-Za-z0-9._:/+-]+")


def _config_error(message: str) -> RecordsError:
    return RecordsError(message, code="failure_memory_config")


def _registry_error(message: str) -> RecordsError:
    return RecordsError(message, code="failure_memory_registry")


@dataclass(frozen=True)
class LessonSet:
    """The lessons of one project, in registry order."""

    repository_id: str
    registry: Path
    schema_version: int
    lessons: tuple[dict[str, Any], ...]


# ------------------------------------------------------------------ reading
def _read_config(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except OSError as exc:
        raise _config_error(f"cannot read {path}: {exc.strerror}") from None
    except tomllib.TOMLDecodeError as exc:
        raise _config_error(f"{path} is not valid TOML: {exc}") from None
    if raw.get("schema_version") != CONFIG_FORMAT:
        raise _config_error(f"{path} is not a {CONFIG_FORMAT} configuration")
    return raw


def _registry_path(raw: dict[str, Any], root: Path) -> Path:
    paths = raw.get("paths")
    text = paths.get("registry") if isinstance(paths, dict) else None
    if not isinstance(text, str) or not text:
        raise _config_error("paths.registry must be a non-empty string")
    if "\\" in text or text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        raise _config_error("paths.registry must be a repository-relative POSIX path")
    parts = PurePosixPath(text).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise _config_error("paths.registry contains a forbidden path segment")
    candidate = root.joinpath(*parts)
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise _config_error("paths.registry resolves outside the repository")
    return candidate


def _json_object(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_bytes().decode("utf-8"))
    except OSError as exc:
        raise _registry_error(f"cannot read {path}: {exc.strerror}") from None
    except (UnicodeDecodeError, ValueError) as exc:
        raise _registry_error(f"{path} is not valid JSON: {exc}") from None
    if not isinstance(raw, dict):
        raise _registry_error(f"{path} must hold a JSON object")
    return raw


def _read_v1(path: Path) -> list[Any]:
    if not path.is_file():
        raise _registry_error(f"registry schema 1 needs a file: {path}")
    raw = _json_object(path)
    if not REGISTRY_V1_KEYS <= set(raw) or not isinstance(raw.get("lessons"), list):
        raise _registry_error(
            "a schema 1 registry needs schema_version, _field_spec and a lessons list"
        )
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise _registry_error(f"{path} does not declare registry schema 1")
    return raw["lessons"]


def _read_v2(path: Path) -> list[Any]:
    if path.is_symlink() or not path.is_dir():
        raise _registry_error(f"registry schema 2 needs a directory: {path}")
    entries = sorted(path.iterdir(), key=lambda entry: entry.name)
    lessons: list[Any] = []
    meta_seen = False
    for entry in entries:
        name = entry.name
        if entry.is_symlink() or not entry.is_file():
            raise _registry_error(f"the registry holds a stray path: {name}")
        if name == ANNOTATIONS:
            continue
        if name == REGISTRY_META:
            meta_seen = True
            meta = _json_object(entry)
            if not REGISTRY_V2_KEYS <= set(meta) or (
                type(meta.get("schema_version")) is not int
                or meta.get("schema_version") != 2
            ):
                raise _registry_error(f"{name} does not declare registry schema 2")
            continue
        if not name.endswith(".json"):
            raise _registry_error(f"the registry holds a stray path: {name}")
        lesson = _json_object(entry)
        if lesson.get("id") != name[: -len(".json")]:
            raise _registry_error(f"{name} does not hold the lesson of that ID")
        lessons.append(lesson)
    if not meta_seen:
        raise _registry_error(f"{path} has no {REGISTRY_META}")
    return lessons


def load_lessons(config: str | Path, repo: str | Path) -> LessonSet:
    """Read a project's lessons. Reads only: it opens no file for writing."""
    config_path, root = Path(config), Path(repo)
    raw = _read_config(config_path)
    repository_id = raw.get("repository_id")
    if not isinstance(repository_id, str) or not repository_id:
        raise _config_error("repository_id must be a non-empty string")
    validation = raw.get("validation")
    if not isinstance(validation, dict):
        raise _config_error("the configuration has no [validation] table")
    version = validation.get("registry_schema_version")
    if type(version) is not int or version not in (1, 2):
        raise _config_error("validation.registry_schema_version must be 1 or 2")
    pattern = validation.get("id_pattern")
    if not isinstance(pattern, str):
        raise _config_error("validation.id_pattern must be a string")
    try:
        id_pattern = re.compile(pattern)
    except re.error as exc:
        raise _config_error(f"validation.id_pattern is not usable: {exc}") from None
    registry = _registry_path(raw, root)
    items = _read_v1(registry) if version == 1 else _read_v2(registry)
    seen: set[str] = set()
    for index, lesson in enumerate(items):
        lesson_id = lesson.get("id") if isinstance(lesson, dict) else None
        if not isinstance(lesson_id, str) or not id_pattern.fullmatch(lesson_id):
            raise _registry_error(f"lesson {index} has a malformed ID: {lesson_id!r}")
        if lesson_id in seen:
            raise _registry_error(f"duplicate lesson ID {lesson_id}")
        seen.add(lesson_id)
    return LessonSet(repository_id, registry, version, tuple(items))


# ------------------------------------------------------------------ mapping
def ensure_lesson_schema(store: RecordStore) -> tuple[RegisteredSchema, bool]:
    """Register the built-in schema in ``store`` if absent; ``True`` if it was."""
    new = False
    try:
        found = store.schemas.get(FAILURE_LESSON_REF)
    except NotFound:
        outcome = store.register_schema(lesson_schema(), actor=IMPORT_ACTOR)
        found, new = outcome.schema, outcome.new
    if found.schema_sha256 != lesson_digest():
        raise RecordsError(
            f"{FAILURE_LESSON_REF} in this store differs from the built-in schema",
            code="reserved_schema",
        )
    return found, new


def _summary(lesson: dict[str, Any]) -> str:
    text = " ".join(f"{lesson['id']}: {lesson['symptom']}".split()).rstrip(": ")
    return text if len(text) <= MAX_SUMMARY else text[: MAX_SUMMARY - 1] + "…"


def _tags(lesson: dict[str, Any]) -> list[str]:
    tags = [SOURCE_KIND]
    for key in ("area", "package", "module"):
        value = _TAG_UNSAFE.sub("-", lesson["location"][key]).strip("-._:/+")
        if value:
            tag = f"{key}:{value}"[:MAX_TAG]
            if tag not in tags:
                tags.append(tag)
    return tags


def lesson_document(lesson: dict[str, Any], repository_id: str) -> dict[str, Any]:
    """The record document of one lesson."""
    return {
        "schema_ref": FAILURE_LESSON_REF,
        "payload": lesson,
        "summary": _summary(lesson),
        "tags": _tags(lesson),
        "source_refs": [
            {"kind": SOURCE_KIND, "ref": lesson["id"], "note": repository_id}
        ],
        "origin": {"kind": "import", "actor_id": IMPORT_ACTOR},
        "review_state": "unreviewed",
    }


def _create_event_id(repository_id: str, lesson_id: str) -> str:
    raw = f"{repository_id}\0{lesson_id}".encode("utf-8")
    return "failure-memory-" + hashlib.sha256(raw).hexdigest()[:32]


def _amend_event_id(repository_id: str, lesson: dict[str, Any]) -> str:
    raw = f"{repository_id}\0{lesson['id']}\0{digest(lesson)}".encode("utf-8")
    return "failure-memory-" + hashlib.sha256(raw).hexdigest()[:32]


def _erased_days(erased: set[str]) -> set[date]:
    days: set[date] = set()
    for record_id in erased:
        match = RECORD_ID_RE.fullmatch(record_id)
        if match:
            year, month, day = (int(match.group(n)) for n in (1, 2, 3))
            try:
                days.add(date(year, month, day))
            except ValueError:
                continue
    return days


def _erased_lesson(event_id: str, erased: set[str], days: set[date]) -> str | None:
    """The erased record that was created from this event ID, if there is one."""
    for day in days:
        for attempt in range(ERASED_ID_ATTEMPTS):
            candidate = record_id_for(day, event_id, attempt)
            if candidate in erased:
                return candidate
    return None


def _existing(
    store: RecordStore, repository_id: str
) -> tuple[dict[str, str], list[str], list[str]]:
    """Lesson ID to record ID, the extra records, and the records that do not replay."""
    found: dict[str, str] = {}
    duplicates: list[str] = []
    unreadable: list[str] = []
    for item in store.iter_records():
        if isinstance(item, ReplayError):
            unreadable.append(item.record_id)
            continue
        if not is_failure_lesson(item.schema_ref):
            continue
        for ref in item.source_refs:
            if ref.get("kind") == SOURCE_KIND and ref.get("note") == repository_id:
                if ref["ref"] in found:
                    duplicates.append(item.record_id)
                else:
                    found[ref["ref"]] = item.record_id
                break
    return found, sorted(duplicates), sorted(unreadable)


# ------------------------------------------------------------------- import
def import_failure_memory(
    store: RecordStore,
    config: str | Path,
    *,
    repo: str | Path,
    actor: str,
) -> dict[str, Any]:
    """Import a project's lessons into ``store``; see the module docstring.

    Every lesson is checked against the schema before the first write, so a
    registry with one bad lesson changes nothing.
    """
    check_actor(actor)
    lessons = load_lessons(config, repo)
    schema = lesson_schema()
    for lesson in lessons.lessons:
        try:
            validate_instance(schema, lesson, ref=FAILURE_LESSON_REF)
        except RecordsError as exc:
            raise RecordsError(
                f"lesson {lesson['id']} does not fit {FAILURE_LESSON_REF}: {exc}",
                code="failure_memory_registry",
                details=exc.details,
            ) from None
    _, registered = ensure_lesson_schema(store)
    existing, duplicates, unreadable = _existing(store, lessons.repository_id)
    erased = store.erased_ids()
    days = _erased_days(erased)
    created: list[dict[str, str]] = []
    amended: list[dict[str, str]] = []
    unchanged: list[str] = []
    inactive: list[dict[str, str]] = []
    erased_rows: list[dict[str, str]] = []
    for lesson in lessons.lessons:
        lesson_id = lesson["id"]
        document = lesson_document(lesson, lessons.repository_id)
        record_id = existing.get(lesson_id)
        if record_id is None:
            event_id = _create_event_id(lessons.repository_id, lesson_id)
            gone = _erased_lesson(event_id, erased, days)
            if gone is not None:
                erased_rows.append({"lesson": lesson_id, "record_id": gone})
                continue
            result = store.create(document, actor=actor, event_id=event_id)
            created.append({"lesson": lesson_id, "record_id": result.record_id})
            continue
        record = store.get(record_id)
        if record.payload == lesson:
            unchanged.append(lesson_id)
        elif record.lifecycle != "active":
            inactive.append(
                {
                    "lesson": lesson_id,
                    "record_id": record_id,
                    "lifecycle": record.lifecycle,
                }
            )
        else:
            result = store.amend(
                record_id,
                {
                    "payload": lesson,
                    "summary": document["summary"],
                    "tags": document["tags"],
                    "review_state": "unreviewed",
                },
                expected_revision=record.revision,
                actor=actor,
                event_id=_amend_event_id(lessons.repository_id, lesson),
            )
            amended.append(
                {
                    "lesson": lesson_id,
                    "record_id": record_id,
                    "revision": str(result.revision),
                }
            )
    present = {lesson["id"] for lesson in lessons.lessons}
    removed = [
        {"lesson": lesson_id, "record_id": record_id}
        for lesson_id, record_id in sorted(existing.items())
        if lesson_id not in present
    ]
    return {
        "status": "ok",
        "source": {
            "repository_id": lessons.repository_id,
            "registry": str(lessons.registry),
            "registry_schema_version": lessons.schema_version,
        },
        "schema_ref": FAILURE_LESSON_REF,
        "schema_registered": registered,
        "lessons": len(lessons.lessons),
        "created": created,
        "amended": amended,
        "unchanged": unchanged,
        "removed_upstream": removed,
        "skipped": {"erased": erased_rows, "inactive": inactive},
        "duplicate_records": duplicates,
        "unreadable_records": unreadable,
    }


__all__ = [
    "IMPORT_ACTOR",
    "LessonSet",
    "SOURCE_KIND",
    "ensure_lesson_schema",
    "import_failure_memory",
    "lesson_document",
    "load_lessons",
]
