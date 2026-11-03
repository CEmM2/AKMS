"""Deterministic lesson index: area -> package -> module -> lesson cards.

A card is the short form of one lesson: its title, trigger, mechanism and
prevention plus reference IDs and reviewed categories. The full record stays
in the registry and is fetched on demand; a card never replaces it.

The index is a pure function of the lessons, the annotations sidecar and the
configured namespace. It carries no timestamps, every list has a fixed order,
and the JSON form is serialized with sorted keys, so rebuilding unchanged
inputs reproduces it byte for byte.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
from typing import Any

from akms_failure_memory.annotations import LessonAnnotations
from akms_failure_memory.config import LESSON_INDEX_VERSIONS, ProjectConfig
from akms_failure_memory.lesson_ids import lesson_id_sort_key


INDEX_JSON_NAME = "lesson_index.json"
INDEX_MARKDOWN_NAME = "lesson_index.md"
TITLE_MAX_LENGTH = 96
_FINGERPRINT_PREFIX = "<!-- lesson_index_sha256: "
_REFERENCE_KEYS = ("commit", "issue", "pr", "plan")
# A sentence ends at . ! or ? followed by whitespace and a capital, digit,
# quote or bracket, so "e.g. the" and "module.py" do not end one.
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9`'\"(\[])")
# Clause breaks strong enough for a title. Commas and colons are not: they
# split "When the cache is warm, ..." and "Two causes: ..." in the wrong place.
_CLAUSE_END = re.compile(r"\s*;\s*|\s+(?:--|–|—)\s+")


def _normalize(text: str) -> str:
    return " ".join(text.split())


def split_first_sentence(text: str) -> tuple[str, str]:
    """Split ``text`` into its first sentence and the rest.

    The first sentence has its whitespace collapsed; the rest keeps the
    original line breaks, without surrounding whitespace.
    """
    stripped = text.strip()
    end = _SENTENCE_END.search(stripped)
    if end is None:
        return _normalize(stripped), ""
    return _normalize(stripped[: end.start()]), stripped[end.end() :]


def first_sentence(text: str) -> str:
    """Return the first sentence of ``text`` with whitespace collapsed."""
    return split_first_sentence(text)[0]


def _first_clause(text: str) -> str:
    clause = _CLAUSE_END.split(first_sentence(text), maxsplit=1)[0]
    return clause.rstrip(" .")


def _cap(text: str, limit: int = TITLE_MAX_LENGTH) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 3]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:-") + "..."


def record_title(lesson: Mapping[str, Any]) -> str:
    """Title a lesson from its record, without the ID.

    The first clause of ``root_cause``, falling back to ``symptom`` and then to
    ``location.line_hint``, capped at ``TITLE_MAX_LENGTH`` characters. The empty
    string means the record has none of the three.
    """
    for source in (
        lesson["root_cause"],
        lesson["symptom"],
        lesson["location"]["line_hint"],
    ):
        clause = _first_clause(source)
        if clause:
            return _cap(clause)
    return ""


def lesson_index_paths(config: ProjectConfig) -> tuple[str, str]:
    """Repository-relative JSON and Markdown paths, beside the route index.

    Not beside the generated nodes: AKMS reads every Markdown file under the
    local-nodes root as a node.
    """
    parent = PurePosixPath(config.paths["routes"]).parent
    return (
        (parent / INDEX_JSON_NAME).as_posix(),
        (parent / INDEX_MARKDOWN_NAME).as_posix(),
    )


def _card(
    lesson: Mapping[str, Any], node_id: str, annotations: LessonAnnotations
) -> dict[str, Any]:
    annotation = annotations.for_lesson(lesson["id"])
    references = lesson["references"]
    return {
        "id": lesson["id"],
        "node_id": node_id,
        "title": record_title(lesson),
        "trigger": _normalize(lesson["found_by"]["trigger"]),
        "mechanism": first_sentence(lesson["root_cause"]),
        "prevention": first_sentence(lesson["prevention"]),
        "references": {
            key: references[key] for key in _REFERENCE_KEYS if references[key]
        },
        "related": sorted(lesson["related"], key=lesson_id_sort_key),
        "categories": annotation["categories"],
        "superseded_by": annotation["superseded_by"],
    }


def _utf8(value: str) -> bytes:
    return value.encode("utf-8")


def _fingerprint(body: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_lesson_index(
    lessons: Iterable[Mapping[str, Any]],
    config: ProjectConfig,
    *,
    node_ids: Mapping[str, str],
    source_sha256: str,
    source_schema_version: int,
    annotations: LessonAnnotations,
) -> dict[str, Any]:
    """Group validated lessons into cards and fingerprint the result."""
    tree: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {}
    for lesson in sorted(lessons, key=lambda item: lesson_id_sort_key(item["id"])):
        location = lesson["location"]
        tree.setdefault(location["area"], {}).setdefault(
            location["package"], {}
        ).setdefault(location["module"], []).append(
            _card(lesson, node_ids[lesson["id"]], annotations)
        )
    areas = []
    package_count = module_count = lesson_count = 0
    for area in sorted(tree, key=_utf8):
        packages = []
        for package in sorted(tree[area], key=_utf8):
            modules = [
                {
                    "name": module,
                    "lessons": len(tree[area][package][module]),
                    "cards": tree[area][package][module],
                }
                for module in sorted(tree[area][package], key=_utf8)
            ]
            packages.append(
                {
                    "name": package,
                    "lessons": sum(item["lessons"] for item in modules),
                    "modules": modules,
                }
            )
            module_count += len(modules)
        package_count += len(packages)
        area_lessons = sum(item["lessons"] for item in packages)
        lesson_count += area_lessons
        areas.append({"name": area, "lessons": area_lessons, "packages": packages})
    body: dict[str, Any] = {
        "contract_version": config.lesson_index_version or LESSON_INDEX_VERSIONS[-1],
        "inputs": {
            "source_schema_version": source_schema_version,
            "source_sha256": source_sha256,
            "annotations_sha256": annotations.sha256,
        },
        "counts": {
            "areas": len(areas),
            "packages": package_count,
            "modules": module_count,
            "lessons": lesson_count,
        },
        "areas": areas,
    }
    return {**body, "fingerprint": _fingerprint(body)}


def serialize_lesson_index(index: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _group_name(name: str) -> str:
    return f"`{name}`" if name else "(none)"


def render_lesson_index_markdown(
    index: Mapping[str, Any], config: ProjectConfig
) -> bytes:
    """Render the index for people. The JSON form is the machine contract."""
    counts = index["counts"]
    lines = [
        str(config.compatibility["generated_warning"]),
        f"{_FINGERPRINT_PREFIX}{index['fingerprint']} -->",
        "",
        "# Lesson index",
        "",
        f"{counts['lessons']} lessons in {counts['areas']} areas, "
        f"{counts['packages']} packages and {counts['modules']} modules. "
        "Run `failure-memory index --expand <ID>` for a full record.",
    ]
    for area in index["areas"]:
        lines.extend(("", f"## Area {_group_name(area['name'])}"))
        for package in area["packages"]:
            lines.extend(("", f"### Package {_group_name(package['name'])}"))
            for module in package["modules"]:
                lines.extend(("", f"#### Module {_group_name(module['name'])}", ""))
                for card in module["cards"]:
                    heading = (
                        f"{card['id']}: {card['title']}"
                        if card["title"]
                        else card["id"]
                    )
                    lines.append(f"- **{heading}**")
                    for label, value in (
                        ("Trigger", card["trigger"]),
                        ("Mechanism", card["mechanism"]),
                        ("Prevention", card["prevention"]),
                        ("Categories", ", ".join(card["categories"])),
                        ("Superseded by", card["superseded_by"] or ""),
                        ("Related", ", ".join(card["related"])),
                        (
                            "References",
                            "; ".join(
                                f"{key} {value}"
                                for key, value in card["references"].items()
                            ),
                        ),
                    ):
                        if value:
                            lines.append(f"  - {label}: {_normalize(value)}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def is_generated_index(path_name: str, data: bytes, config: ProjectConfig) -> bool:
    """Whether bytes found at an index path were written by this compiler."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if path_name == INDEX_MARKDOWN_NAME:
        return (
            text.startswith(str(config.compatibility["generated_warning"]))
            and _FINGERPRINT_PREFIX in text
        )
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(raw, dict) and str(raw.get("contract_version", "")).startswith(
        "failure-lesson-index/"
    )


__all__ = [
    "INDEX_JSON_NAME",
    "INDEX_MARKDOWN_NAME",
    "TITLE_MAX_LENGTH",
    "build_lesson_index",
    "first_sentence",
    "is_generated_index",
    "lesson_index_paths",
    "record_title",
    "render_lesson_index_markdown",
    "serialize_lesson_index",
    "split_first_sentence",
]
