"""Code-mirror freshness: which mirrors are older than their source.

A mirror is stale when its ``source_file`` was committed after the mirror's
``generated_at``, has uncommitted edits newer than it, or no longer exists.
The check uses git history only; it adds nothing to the frozen mirror schema.
Outside a git repository nothing is reported.

``generated_at`` must record when the mirror was refreshed. A deterministic
timestamp older than the latest commit (a fixed ``SOURCE_DATE_EPOCH``, say)
makes every changed source look stale.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import frontmatter as fm

from akms.layout import local_knowledge_dir

logger = logging.getLogger(__name__)


def stale_mirrors(repo_root: str | Path) -> list[dict[str, Any]]:
    """Return one record per stale code mirror under ``repo_root``'s knowledge directory.

    Each record has ``node_id``, ``source_file``, ``generated_at``, ``reason``
    (``committed_after``, ``modified_after`` or ``source_missing``) and, where it
    applies, ``changed_at``.
    """
    root = Path(repo_root).resolve()
    mirrors = _mirrors(local_knowledge_dir(root) / "code-mirror")
    if not mirrors:
        return []
    top = _git_toplevel(root)
    if top is None:
        return []

    located: list[tuple[dict[str, Any], str | None]] = []
    for mirror in mirrors:
        located.append((mirror, _locate(mirror["source_file"], root, top)))
    tracked = sorted({path for _, path in located if path is not None})
    since = min(mirror["generated_at"] for mirror in mirrors)
    committed = _last_commit_times(top, tracked, since)
    dirty = _dirty(top, tracked)

    stale: list[dict[str, Any]] = []
    for mirror, path in located:
        record = {
            "node_id": mirror["node_id"],
            "source_file": mirror["source_file"],
            "generated_at": mirror["generated_at"].isoformat(),
        }
        if path is None:
            stale.append({**record, "reason": "source_missing"})
            continue
        commit_time = committed.get(path)
        if commit_time is not None and commit_time > mirror["generated_at"]:
            stale.append(
                {
                    **record,
                    "reason": "committed_after",
                    "changed_at": commit_time.isoformat(),
                }
            )
            continue
        if path in dirty:
            modified = datetime.fromtimestamp(
                (top / path).stat().st_mtime, tz=timezone.utc
            )
            if modified > mirror["generated_at"]:
                stale.append(
                    {
                        **record,
                        "reason": "modified_after",
                        "changed_at": modified.isoformat(),
                    }
                )
    return sorted(stale, key=lambda item: item["source_file"])


def _mirrors(mirror_root: Path) -> list[dict[str, Any]]:
    """``node_id``, ``source_file`` and aware ``generated_at`` of each mirror file."""
    if not mirror_root.is_dir():
        return []
    found: list[dict[str, Any]] = []
    for path in sorted(mirror_root.rglob("*.md")):
        try:
            meta = fm.loads(path.read_text(encoding="utf-8")).metadata
        except Exception:  # unreadable files are reported by build_graph
            continue
        source = meta.get("source_file")
        generated = _aware(meta.get("generated_at"))
        if not isinstance(source, str) or generated is None:
            continue
        found.append(
            {
                "node_id": str(meta.get("id", path.stem)),
                "source_file": source,
                "generated_at": generated,
            }
        )
    return found


def _aware(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _locate(source_file: str, root: Path, top: Path) -> str | None:
    """``source_file`` as a path relative to the git top level, or None if missing.

    Mirrors name sources relative to the exported repository. That is usually
    ``root``; when the knowledge directory sits below the repository (an AKMS
    root such as ``dev/``), it is the git top level.
    """
    for base in (root, top):
        candidate = base / source_file
        if candidate.is_file():
            try:
                return candidate.resolve().relative_to(top).as_posix()
            except ValueError:
                return None
    return None


def _git(top: Path, *arguments: str) -> bytes | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(top), "-c", "core.quotepath=false", *arguments],
            capture_output=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("mirror freshness check skipped: %s", exc)
        return None
    if completed.returncode != 0:
        logger.warning(
            "mirror freshness check skipped: git %s failed: %s",
            arguments[0],
            completed.stderr.decode("utf-8", errors="replace").strip(),
        )
        return None
    return completed.stdout


def _git_toplevel(root: Path) -> Path | None:
    output = _git(root, "rev-parse", "--show-toplevel")
    return Path(output.decode().strip()) if output else None


def _last_commit_times(
    top: Path, paths: list[str], since: datetime
) -> dict[str, datetime]:
    """Latest commit time per path, among commits since ``since``."""
    if not paths:
        return {}
    # Each commit prints a marked date line, then the paths it touched.
    output = _git(
        top,
        "log",
        f"--since={since.isoformat()}",
        "--format=\x01%cI",
        "--name-only",
        "--",
        *paths,
    )
    latest: dict[str, datetime] = {}
    if not output:
        return latest
    wanted = set(paths)
    when: datetime | None = None
    for line in output.decode("utf-8", errors="replace").splitlines():
        if line.startswith("\x01"):
            when = _aware(line[1:])
        elif when is not None and line in wanted and line not in latest:
            latest[line] = when
    return latest


def _dirty(top: Path, paths: list[str]) -> set[str]:
    """Paths with uncommitted changes in the worktree or index."""
    if not paths:
        return set()
    output = _git(top, "status", "--porcelain", "-z", "--", *paths)
    if not output:
        return set()
    dirty: set[str] = set()
    entries = iter(output.decode("utf-8", errors="replace").split("\0"))
    for entry in entries:
        if len(entry) < 4:
            continue
        dirty.add(entry[3:])
        if "R" in entry[:2] or "C" in entry[:2]:
            next(entries, None)  # the rename or copy source follows, unprefixed
    return dirty
