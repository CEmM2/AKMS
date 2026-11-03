"""Move a failure-memory project's knowledge from ``knowledge/`` to ``.knowledge/``."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from akms.layout import (
    DEFAULT_KNOWLEDGE_DIRNAME,
    LEGACY_KNOWLEDGE_DIRNAME,
    KnowledgeLayoutError,
    migrate_knowledge_layout,
    plan_knowledge_migration,
)

from akms_failure_memory.compiler import run_compiler
from akms_failure_memory.config import ProjectConfig, load_project_config
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.locks import ProjectLock
from akms_failure_memory.record import _atomic_replace


def _moved(value: str, old: str, new: str) -> str | None:
    """``value`` re-rooted from ``old`` to ``new``, or None when it is outside ``old``."""
    if value == old:
        return new
    if value.startswith(f"{old}/"):
        return f"{new}{value[len(old) :]}"
    return None


def _config_edits(config: ProjectConfig, old: str, new: str) -> list[dict[str, str]]:
    edits = [
        {"key": f"paths.{key}", "before": value, "after": moved}
        for key, value in sorted(config.paths.items())
        if (moved := _moved(value, old, new)) is not None
    ]
    warning = str(config.compatibility["generated_warning"])
    rewritten = re.sub(rf"(?<![\w.-]){re.escape(old)}/", f"{new}/", warning)
    if rewritten != warning:
        edits.append(
            {
                "key": "compatibility.generated_warning",
                "before": warning,
                "after": rewritten,
            }
        )
    return edits


def _rewrite_config_text(text: str, edits: list[dict[str, str]]) -> str:
    """Replace each edited value in its one simple ``key = "value"`` assignment."""
    for edit in edits:
        key = edit["key"].rsplit(".", 1)[1]
        if any(mark in edit["after"] for mark in ('"', "'", "\n")):
            raise FailureMemoryError(
                f"Cannot store {edit['key']} value {edit['after']!r}",
                code="invalid_config",
            )
        pattern = re.compile(
            rf'^([ \t]*{re.escape(key)}[ \t]*=[ \t]*)(["\']){re.escape(edit["before"])}\2',
            re.MULTILINE,
        )
        matches = pattern.findall(text)
        if len(matches) != 1:
            raise FailureMemoryError(
                f"Cannot update project config: {edit['key']} must be one simple "
                "assignment",
                code="invalid_config",
            )
        text = pattern.sub(
            lambda m: f"{m.group(1)}{m.group(2)}{edit['after']}{m.group(2)}", text
        )
    return text


def _validated(text: str, source: Path) -> None:
    """Load ``text`` as a project config without touching ``source``."""
    with tempfile.TemporaryDirectory(prefix=".failure-memory-layout-") as staging:
        candidate = Path(staging) / source.name
        candidate.write_text(text, encoding="utf-8")
        load_project_config(candidate)


def resolve_config_path(config_path: Path, repository_root: Path) -> Path:
    """The default config path, or its ``knowledge/`` counterpart when only that exists."""
    if config_path.exists():
        return config_path
    try:
        relative = config_path.resolve().relative_to(repository_root.resolve())
    except ValueError:
        return config_path
    parts = relative.parts
    if parts and parts[0] == DEFAULT_KNOWLEDGE_DIRNAME:
        legacy = repository_root.joinpath(LEGACY_KNOWLEDGE_DIRNAME, *parts[1:])
        if legacy.exists():
            return legacy
    return config_path


def migrate_layout(
    *,
    config_path: str | Path,
    repository_root: str | Path,
    global_vault: str | Path | None = None,
    check: bool = False,
) -> dict[str, Any]:
    """Move the project's AKMS knowledge directory and update its configuration.

    The directory under ``akms_repo_root`` moves with ``akms.layout``'s
    migration. Configured paths inside it, and ``generated_warning``, follow
    it; so does the configuration file when it lives there. Its fingerprint
    changes once. With ``global_vault``, generated lessons are recompiled;
    otherwise ``next`` names the command to run. ``check`` changes nothing.
    """
    root = Path(repository_root).resolve(strict=True)
    config_file = resolve_config_path(Path(config_path), root)
    config = load_project_config(config_file)
    akms_root = config.resolve(root, "akms_repo_root")
    old = (akms_root / LEGACY_KNOWLEDGE_DIRNAME).relative_to(root).as_posix()
    new = (PurePosixPath(old).parent / DEFAULT_KNOWLEDGE_DIRNAME).as_posix()
    try:
        plan = plan_knowledge_migration(akms_root)
    except KnowledgeLayoutError as exc:
        raise FailureMemoryError(str(exc), code=f"layout_{exc.code}") from exc
    edits = _config_edits(config, old, new)
    source = config.source_path
    moved_config = _moved(source.relative_to(root).as_posix(), old, new)
    config_after = root / moved_config if moved_config else source
    rewritten = _rewrite_config_text(source.read_text(encoding="utf-8"), edits)
    _validated(rewritten, source)

    report: dict[str, Any] = {
        "layout": plan.to_dict(),
        "config": config_after.relative_to(root).as_posix(),
        "config_edits": edits,
    }
    if plan.status == "already_migrated" and not edits:
        return {"status": "already_migrated", **report}
    if check:
        return {"status": "checked", **report}

    lock_path = config.resolve(root, "lock")
    lock = ProjectLock(
        lock_path, timeout_seconds=float(config.toolchain["timeout_seconds"])
    )
    with lock:
        if plan.status == "planned":
            try:
                plan = migrate_knowledge_layout(akms_root)
            except KnowledgeLayoutError as exc:
                raise FailureMemoryError(str(exc), code=f"layout_{exc.code}") from exc
            # The held lock file moved with the directory; release it there.
            moved_lock = _moved(lock_path.relative_to(root).as_posix(), old, new)
            if moved_lock:
                lock.path = root / moved_lock
        if edits:
            _atomic_replace(config_after, rewritten.encode("utf-8"))
    report["layout"] = plan.to_dict()

    if global_vault is None:
        return {
            "status": "migrated",
            **report,
            "next": (
                f"failure-memory compile --config {report['config']} "
                "--global-vault <vault>"
            ),
        }
    compiled = run_compiler(
        config_path=config_after,
        repository_root=root,
        global_vault=global_vault,
        mode="write",
    )
    return {"status": "migrated", **report, "compile": compiled.get("status")}


__all__ = ["migrate_layout", "resolve_config_path"]
