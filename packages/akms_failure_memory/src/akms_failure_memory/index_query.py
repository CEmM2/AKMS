"""Read-only retrieval over the lesson index: groups, then cards, then a record.

``failure-memory index`` with no selector lists the area -> package -> module
groups and their lesson counts. Any of ``--area``, ``--package``, ``--module``
or ``--grep`` returns the cards inside the matching groups. ``--expand <ID>``
returns that lesson's full registry record and annotations. Every lesson is
therefore two expansions from the root.

The index is rebuilt in memory from the registry and the annotations sidecar,
so the answer is current even when the published sidecar is not; the result
says whether the sidecar on disk matches. Nothing is written and no lock is
taken: every writer publishes by atomic replacement.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

from akms_failure_memory.annotations import load_annotations
from akms_failure_memory.compiler import _load_registry, compile_lesson_index
from akms_failure_memory.config import load_project_config
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.lesson_index import lesson_index_paths, serialize_lesson_index


def _sidecar_status(root: Path, relative: str, expected: bytes) -> str:
    path = root.joinpath(*PurePosixPath(relative).parts)
    if path.is_symlink() or not path.is_file():
        return "absent"
    return "current" if path.read_bytes() == expected else "stale"


def _groups(index: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": area["name"],
            "lessons": area["lessons"],
            "packages": [
                {
                    "name": package["name"],
                    "lessons": package["lessons"],
                    "modules": [
                        {"name": module["name"], "lessons": module["lessons"]}
                        for module in package["modules"]
                    ],
                }
                for package in area["packages"]
            ],
        }
        for area in index["areas"]
    ]


def _haystack(card: dict[str, Any]) -> str:
    return "\n".join(
        [
            card["id"],
            card["node_id"],
            card["title"],
            card["trigger"],
            card["mechanism"],
            card["prevention"],
            *card["categories"],
            *card["related"],
            *card["references"].values(),
            card["superseded_by"] or "",
        ]
    )


def _select(
    index: dict[str, Any],
    *,
    area: str | None,
    package: str | None,
    module: str | None,
    pattern: re.Pattern[str] | None,
) -> tuple[list[dict[str, Any]], int]:
    selected = []
    matches = 0
    for area_group in index["areas"]:
        if area is not None and area_group["name"] != area:
            continue
        packages = []
        for package_group in area_group["packages"]:
            if package is not None and package_group["name"] != package:
                continue
            modules = []
            for module_group in package_group["modules"]:
                if module is not None and module_group["name"] != module:
                    continue
                cards = [
                    card
                    for card in module_group["cards"]
                    if pattern is None or pattern.search(_haystack(card))
                ]
                if cards:
                    modules.append(
                        {
                            "name": module_group["name"],
                            "lessons": len(cards),
                            "cards": cards,
                        }
                    )
            if modules:
                packages.append(
                    {
                        "name": package_group["name"],
                        "lessons": sum(item["lessons"] for item in modules),
                        "modules": modules,
                    }
                )
        if packages:
            lessons = sum(item["lessons"] for item in packages)
            matches += lessons
            selected.append(
                {"name": area_group["name"], "lessons": lessons, "packages": packages}
            )
    return selected, matches


def _find_card(
    index: dict[str, Any], lesson_id: str
) -> tuple[dict[str, Any], dict[str, str]]:
    for area in index["areas"]:
        for package in area["packages"]:
            for module in package["modules"]:
                for card in module["cards"]:
                    if card["id"] == lesson_id:
                        return card, {
                            "area": area["name"],
                            "package": package["name"],
                            "module": module["name"],
                        }
    raise FailureMemoryError(f"Unknown lesson ID {lesson_id}", code="unknown_lesson")


def query_lesson_index(
    *,
    config_path: str | Path,
    repository_root: str | Path,
    area: str | None = None,
    package: str | None = None,
    module: str | None = None,
    grep: str | None = None,
    expand: str | None = None,
) -> dict[str, Any]:
    """Answer one index step without writing anything."""
    selectors = (area, package, module, grep)
    if expand is not None and any(value is not None for value in selectors):
        raise FailureMemoryError(
            "--expand cannot be combined with --area, --package, --module or --grep",
            code="usage",
        )
    pattern = None
    if grep is not None:
        try:
            pattern = re.compile(grep, re.IGNORECASE | re.MULTILINE)
        except re.error as exc:
            raise FailureMemoryError(
                f"Invalid --grep pattern: {exc}", code="usage"
            ) from exc
    config = load_project_config(config_path)
    root = Path(repository_root).resolve(strict=True)
    registry_path = config.resolve(root, "registry")
    lessons, source_sha256 = _load_registry(config, registry_path)
    annotations = load_annotations(
        config, registry_path, [lesson["id"] for lesson in lessons]
    )
    index = compile_lesson_index(
        lessons, config, source_sha256=source_sha256, annotations=annotations
    )
    index_json, _ = lesson_index_paths(config)
    common = {
        "status": "ok",
        "fingerprint": index["fingerprint"],
        "sidecar": {
            "path": index_json,
            "status": _sidecar_status(root, index_json, serialize_lesson_index(index))
            if config.lesson_index_version is not None
            else "disabled",
        },
        "config_fingerprint": config.fingerprint,
    }
    if expand is not None:
        card, location = _find_card(index, expand)
        record = next(lesson for lesson in lessons if lesson["id"] == expand)
        return {
            **common,
            "level": "record",
            "location": location,
            "card": card,
            "record": record,
            "annotations": annotations.for_lesson(expand),
        }
    if all(value is None for value in selectors):
        return {
            **common,
            "level": "groups",
            "counts": index["counts"],
            "areas": _groups(index),
        }
    selected, matches = _select(
        index, area=area, package=package, module=module, pattern=pattern
    )
    return {**common, "level": "cards", "matches": matches, "areas": selected}


__all__ = ["query_lesson_index"]
