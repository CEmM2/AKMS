"""One canonical recorder for interactive, machine, and direct-edit workflows."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from akms_failure_memory.compiler import run_compiler, validate_registry_bytes
from akms_failure_memory.config import ProjectConfig, load_project_config
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.locks import ProjectLock


_REQUEST_KEYS = frozenset(
    {
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
        "notes",
    }
)
_REQUIRED_REQUEST_KEYS = _REQUEST_KEYS - {"notes"}


def _atomic_replace(path: Path, content: bytes) -> None:
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


def _load_request(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FailureMemoryError(
            f"Cannot load add request {path}: {exc}", code="record_request"
        ) from exc
    if not isinstance(value, dict):
        raise FailureMemoryError(
            "Add request must be a JSON object", code="record_request"
        )
    return value


def _interactive_request(input_fn: Callable[[str], str]) -> dict[str, Any]:
    def ask(label: str) -> str:
        return input_fn(f"{label}: ").strip()

    request: dict[str, Any] = {
        "date_found": ask("Date found (YYYY-MM-DD)"),
        "date_found_precision": ask("Date found precision (exact/approximate)"),
        "date_fixed": ask("Date fixed (YYYY-MM-DD)"),
        "date_fixed_precision": ask("Date fixed precision (exact/approximate)"),
        "location": {
            "area": ask("Location area"),
            "package": ask("Location package"),
            "module": ask("Location module"),
            "file": ask("Repository-relative file"),
            "symbol": ask("Symbol (optional)"),
            "line_hint": ask("Line/topic hint"),
        },
        "found_by": {"type": ask("Found by type"), "trigger": ask("Discovery trigger")},
        "symptom": ask("Symptom"),
        "root_cause": ask("Root cause"),
        "fix": ask("Fix"),
        "prevention": ask("Prevention"),
        "references": {
            "commit": ask("Commit"),
            "issue": ask("Issue"),
            "pr": ask("PR"),
            "plan": ask("Plan"),
        },
    }
    request["related"] = [
        item.strip()
        for item in ask("Related IDs (comma-separated)").split(",")
        if item.strip()
    ]
    notes = ask("Notes (optional)")
    if notes:
        request["notes"] = notes
    return request


def _validate_request_shape(request: dict[str, Any]) -> None:
    actual = set(request)
    if not _REQUIRED_REQUEST_KEYS.issubset(actual) or not actual.issubset(
        _REQUEST_KEYS
    ):
        raise FailureMemoryError(
            "Add request has missing or unexpected fields", code="record_request"
        )
    if "id" in request:
        raise FailureMemoryError(
            "Record IDs are allocated under the project lock", code="record_request"
        )


def _next_id(config: ProjectConfig, lessons: list[dict[str, Any]]) -> str:
    width_match = re.search(r"\{([0-9]+)\}", str(config.validation["id_pattern"]))
    width = int(width_match.group(1)) if width_match else 3
    numbers = [int(lesson["id"][1:]) for lesson in lessons]
    return f"L{(max(numbers, default=0) + 1):0{width}d}"


def _canonical_registry(registry: dict[str, Any]) -> bytes:
    return (json.dumps(registry, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def add_lesson(
    *,
    config_path: str | Path,
    repository_root: str | Path,
    global_vault: str | Path,
    request_path: str | Path | None = None,
    interactive: bool = False,
    input_fn: Callable[[str], str] = input,
) -> dict[str, Any]:
    """Allocate, validate, atomically publish, and compile one canonical record."""
    if interactive == (request_path is not None):
        raise FailureMemoryError(
            "Choose exactly one of interactive or request_path", code="record_request"
        )
    config = load_project_config(config_path)
    root = Path(repository_root).resolve(strict=True)
    registry_path = config.resolve(root, "registry")
    lock_path = config.resolve(root, "lock")
    request = (
        _interactive_request(input_fn)
        if interactive
        else _load_request(Path(request_path))
    )
    _validate_request_shape(request)
    with ProjectLock(
        lock_path, timeout_seconds=float(config.toolchain["timeout_seconds"])
    ):
        try:
            prior = registry_path.read_bytes()
            registry = json.loads(prior.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise FailureMemoryError(
                f"Cannot load canonical registry: {exc}", code="registry_load"
            ) from exc
        lesson = {"id": _next_id(config, registry["lessons"]), **request}
        candidate = dict(registry)
        candidate["lessons"] = [*registry["lessons"], lesson]
        candidate_bytes = _canonical_registry(candidate)
        validate_registry_bytes(candidate_bytes, registry_path, config)
        _atomic_replace(registry_path, candidate_bytes)
        try:
            compilation = run_compiler(
                config_path=config_path,
                repository_root=root,
                global_vault=global_vault,
                mode="write",
            )
        except Exception:
            _atomic_replace(registry_path, prior)
            raise
    return {
        "status": "created",
        "schema_version": "failure-memory-registry/v1",
        "record": lesson,
        "source_sha256": compilation["source_sha256"],
        "affected_outputs": compilation["written"],
        "promotion": "not-performed",
    }


__all__ = ["add_lesson"]
