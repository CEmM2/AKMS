"""Dependency-free integrity protocol for record-derived Markdown projections.

This is a freshness check, not authentication. A producer must validate its own
record store before recording a snapshot; core deliberately knows no schemas.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any

HEADER = "<!-- akms-records-projection/v1 "
FOOTER = "<!-- /akms-records-projection -->"
_EVENT = re.compile(r"[0-9]{6}\.json\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class ProjectionError(ValueError):
    """Invalid or unavailable projection; messages never contain source data."""


@dataclass(frozen=True)
class ProjectionBlock:
    start: int
    end: int
    body: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ProjectionGuard:
    managed: bool
    current: bool
    content: str
    reason: str = ""


def source_snapshot(
    directory: Path, *, max_revision: int | None = None, prefix: bool = False
) -> str:
    """Hash numbered events, rejecting symlinks and unstable event listings.

    By default max_revision requires the exact head. Producers may explicitly
    check a historical prefix while sealing their own subsequent link event.
    Prefix checks never establish current freshness.
    """
    try:
        directory = Path(directory)
        names = sorted(p.name for p in directory.iterdir() if _EVENT.fullmatch(p.name))
        if prefix and max_revision is None:
            raise ProjectionError("Prefix snapshot requires a revision")
        selected = names[:max_revision] if prefix else names
        if not selected or (
            max_revision is not None
            and selected != [f"{i:06d}.json" for i in range(1, max_revision + 1)]
        ):
            raise ProjectionError("Source snapshot unavailable or changed")
        digest = hashlib.sha256()
        for name in selected:
            path = directory / name
            if path.is_symlink():
                raise ProjectionError("Source snapshot unavailable or changed")
            fd = os.open(
                path,
                os.O_RDONLY
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_NONBLOCK", 0),
            )
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode):
                    raise ProjectionError("Source snapshot unavailable or changed")
                data = stream.read()
                after = os.fstat(stream.fileno())
            if (before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ) or path.stat().st_ino != before.st_ino:
                raise ProjectionError("Source snapshot unavailable or changed")
            digest.update(
                name.encode("ascii")
                + b"\0"
                + str(len(data)).encode("ascii")
                + b"\0"
                + data
            )
        if names != sorted(
            p.name for p in directory.iterdir() if _EVENT.fullmatch(p.name)
        ):
            raise ProjectionError("Source snapshot unavailable or changed")
        return digest.hexdigest()
    except (OSError, ValueError):
        raise ProjectionError("Source snapshot unavailable or changed") from None


def collection_snapshot(directory: Path, *, excluded_path: str) -> str:
    """Hash a collection's numbered event streams, including its membership.

    This deliberately has no schema or topic semantics: any other stream's
    change invalidates the witness. Exclude only the projecting record itself,
    whose separate source fingerprint already guards its events.
    """
    excluded = Path(excluded_path)
    if (
        not excluded_path
        or excluded.is_absolute()
        or ".." in excluded.parts
        or not excluded.parts
    ):
        raise ProjectionError("Invalid collection exclusion")
    directory = Path(directory)

    def streams() -> list[str]:
        return sorted(
            {
                p.parent.relative_to(directory).as_posix()
                for p in directory.rglob("*.json")
                if _EVENT.fullmatch(p.name)
                and not p.relative_to(directory).is_relative_to(excluded)
            }
        )

    try:
        if not directory.is_dir():
            raise ProjectionError("Collection source unavailable")
        names = streams()
        digest = hashlib.sha256()
        for name in names:
            path = directory / name
            # A symlinked event directory cannot substitute another stream.
            if any(
                parent.is_symlink()
                for parent in (path, *path.parents)
                if parent != directory and parent.is_relative_to(directory)
            ):
                raise ProjectionError("Collection source unavailable")
            digest.update(
                name.encode("utf-8")
                + b"\0"
                + source_snapshot(path).encode("ascii")
                + b"\0"
            )
        if names != streams():
            raise ProjectionError("Collection changed")
        return digest.hexdigest()
    except (OSError, ValueError):
        raise ProjectionError("Collection source unavailable or changed") from None


def _outside_lines(text: str):
    """Yield offset/line pairs outside CommonMark backtick and tilde fences."""
    fence: tuple[str, int] | None = None
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", stripped)
        if fence is not None:
            if (
                match
                and match[1][0] == fence[0]
                and len(match[1]) >= fence[1]
                and not match[2].strip()
            ):
                fence = None
        elif match and not (match[1][0] == "`" and "`" in match[2]):
            fence = (match[1][0], len(match[1]))
        else:
            yield offset, line
        offset += len(line)


def _validate_metadata(meta: Any) -> None:
    if not isinstance(meta, dict) or set(meta) - {
        "scope",
        "source_revision",
        "source_title",
        "dependencies",
        "collection",
    } != {
        "record_id",
        "revision",
        "source_dir",
        "source_sha256",
        "body_sha256",
    }:
        raise ProjectionError("Invalid projection metadata")
    collection = meta.get("collection")
    if collection is not None:
        if not isinstance(collection, dict) or set(collection) != {
            "source_dir",
            "source_sha256",
            "excluded_path",
        }:
            raise ProjectionError("Invalid collection metadata")
        excluded = collection["excluded_path"]
        if (
            not isinstance(excluded, str)
            or not excluded
            or not Path(excluded).parts
            or Path(excluded).is_absolute()
            or ".." in Path(excluded).parts
        ):
            raise ProjectionError("Invalid collection exclusion")
        _validate_metadata(
            {
                "record_id": "collection",
                "revision": 1,
                "body_sha256": "0" * 64,
                "source_dir": collection["source_dir"],
                "source_sha256": collection["source_sha256"],
            }
        )
    if "dependencies" in meta:
        if not isinstance(meta["dependencies"], list):
            raise ProjectionError("Invalid projection dependencies")
        for dependency in meta["dependencies"]:
            if not isinstance(dependency, dict) or set(dependency) != {
                "record_id",
                "revision",
                "source_dir",
                "source_sha256",
            }:
                raise ProjectionError("Invalid projection dependency")
            _validate_metadata({**dependency, "body_sha256": "0" * 64})
    if "source_title" in meta and not isinstance(meta["source_title"], str):
        raise ProjectionError("Invalid projection metadata")
    if "scope" in meta and not isinstance(meta["scope"], str):
        raise ProjectionError("Invalid projection metadata")
    if "source_revision" in meta and (
        type(meta["source_revision"]) is not int or meta["source_revision"] < 1
    ):
        raise ProjectionError("Invalid projection metadata")
    locator = meta["source_dir"]
    if (
        not isinstance(meta["record_id"], str)
        or not meta["record_id"]
        or type(meta["revision"]) is not int
        or meta["revision"] < 1
        or not isinstance(locator, dict)
        or set(locator) != {"base", "path"}
        or locator["base"] not in {"repo", "absolute"}
        or not isinstance(locator["path"], str)
        or not locator["path"]
        or any(
            not isinstance(meta[k], str) or not _DIGEST.fullmatch(meta[k])
            for k in ("source_sha256", "body_sha256")
        )
    ):
        raise ProjectionError("Invalid projection metadata")
    path = Path(locator["path"])
    if (
        "\0" in locator["path"]
        or (locator["base"] == "repo" and (path.is_absolute() or ".." in path.parts))
        or (locator["base"] == "absolute" and not path.is_absolute())
    ):
        raise ProjectionError("Invalid projection source locator")


def parse_projections(text: str) -> list[ProjectionBlock]:
    """Parse and validate every managed block, including body integrity."""
    blocks: list[ProjectionBlock] = []
    pending = None
    ids: set[str] = set()
    for offset, line in _outside_lines(text):
        value = line.rstrip("\r\n")
        if (
            "<!-- akms-records-projection" not in value
            and "<!-- /akms-records-projection" not in value
        ):
            continue
        if value.startswith(HEADER) and value.endswith(" -->") and pending is None:
            try:
                meta = json.loads(value[len(HEADER) : -4])
                _validate_metadata(meta)
            except (ValueError, TypeError, KeyError):
                raise ProjectionError("Invalid projection metadata") from None
            if meta["record_id"] in ids:
                raise ProjectionError("Duplicate projection")
            ids.add(meta["record_id"])
            pending = (offset, offset + len(line), meta)
        elif value == FOOTER and pending is not None:
            start, body_start, meta = pending
            body = text[body_start:offset]
            if hashlib.sha256(body.encode("utf-8")).hexdigest() != meta["body_sha256"]:
                raise ProjectionError("Projection body was edited")
            blocks.append(ProjectionBlock(start, offset + len(line), body, meta))
            pending = None
        else:
            raise ProjectionError("Malformed projection markers")
    if pending is not None:
        raise ProjectionError("Unclosed projection")
    return blocks


def render_projection(
    body: str,
    *,
    record_id: str,
    revision: int,
    source_dir: dict[str, str],
    source_sha256: str,
    scope: str | None = None,
    source_revision: int | None = None,
    source_title: str | None = None,
    dependencies: list[dict[str, Any]] | None = None,
    collection: dict[str, Any] | None = None,
) -> str:
    """Wrap body with an integrity marker; normalize its trailing newline."""
    if not body.endswith("\n"):
        body += "\n"
    meta = dict(
        dependencies=dependencies if dependencies is not None else [],
        collection=collection,
        record_id=record_id,
        revision=revision,
        source_dir=source_dir,
        source_sha256=source_sha256,
        body_sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
    )
    if source_title is not None:
        meta["source_title"] = source_title
    if source_revision is not None:
        meta["source_revision"] = source_revision
    if scope is not None:
        meta["scope"] = scope
    _validate_metadata(meta)
    rendered = (
        HEADER
        + json.dumps(meta, sort_keys=True, ensure_ascii=True)
        + " -->\n"
        + body
        + FOOTER
        + "\n"
    )
    if len(parse_projections(rendered)) != 1:
        raise ProjectionError("Invalid projection body")
    return rendered


def replace_projection(text: str, record_id: str, replacement: str) -> str:
    """Replace one intact block without touching surrounding authored text."""
    blocks = parse_projections(text)
    replacements = parse_projections(replacement)
    if replacement and (
        len(replacements) != 1 or replacements[0].metadata["record_id"] != record_id
    ):
        raise ProjectionError("Invalid replacement projection")
    matches = [b for b in blocks if b.metadata["record_id"] == record_id]
    if len(matches) != 1:
        raise ProjectionError("Projection not found")
    block = matches[0]
    return text[: block.start] + replacement + text[block.end :]


def guard_projection_content(text: str, repo_root: Path | None) -> ProjectionGuard:
    """Hide the whole node if any projection is invalid, missing or stale."""
    try:
        blocks = parse_projections(text)
        unmanaged = text
        for block in reversed(blocks):
            unmanaged = unmanaged[: block.start] + unmanaged[block.end :]
        outside = "".join(line for _, line in _outside_lines(unmanaged))
        if "Promoted from a stored record" in outside and re.search(
            r"(?m)^\s*- record:", outside
        ):
            return ProjectionGuard(
                True, False, "", "legacy projection requires upgrade"
            )
        if not blocks:
            return ProjectionGuard(False, True, text)
        sources = []
        for block in blocks:
            if (
                "dependencies" not in block.metadata
                or "collection" not in block.metadata
            ):
                return ProjectionGuard(
                    True, False, "", "dependency metadata requires upgrade"
                )
            sources.extend([block.metadata, *block.metadata["dependencies"]])
            collection = block.metadata["collection"]
            if collection is not None:
                locator = collection["source_dir"]
                directory = Path(locator["path"])
                if locator["base"] == "repo":
                    if repo_root is None:
                        raise ProjectionError("Collection source unavailable")
                    root = repo_root.resolve()
                    directory = (root / directory).resolve()
                    if not directory.is_relative_to(root):
                        raise ProjectionError("Invalid collection source locator")
                if (
                    collection_snapshot(
                        directory, excluded_path=collection["excluded_path"]
                    )
                    != collection["source_sha256"]
                ):
                    return ProjectionGuard(True, False, "", "collection changed")
        for metadata in sources:
            locator = metadata["source_dir"]
            directory = Path(locator["path"])
            if locator["base"] == "repo":
                if repo_root is None:
                    raise ProjectionError("Projection source unavailable")
                root = repo_root.resolve()
                directory = (root / directory).resolve()
                if not directory.is_relative_to(root):
                    raise ProjectionError("Invalid projection source locator")
            if (
                source_snapshot(
                    directory,
                    max_revision=metadata.get("source_revision", metadata["revision"]),
                )
                != metadata["source_sha256"]
            ):
                return ProjectionGuard(True, False, "", "source changed")
        for block in reversed(blocks):
            text = text[: block.start] + block.body + text[block.end :]
        return ProjectionGuard(True, True, text)
    except (ProjectionError, OSError, RuntimeError):
        return ProjectionGuard(
            True, False, "", "projection invalid or source unavailable"
        )


def has_record_projection(text: str) -> bool:
    """Identify provenance without opening its source (also malformed blocks)."""
    outside = "".join(line for _, line in _outside_lines(text))
    return (
        "<!-- akms-records-projection" in outside
        or "<!-- /akms-records-projection" in outside
        or (
            "Promoted from a stored record" in outside
            and re.search(r"(?m)^\s*- record:", outside) is not None
        )
    )
