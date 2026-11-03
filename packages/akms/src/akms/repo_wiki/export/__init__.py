"""Filesystem orchestration for deterministic AKMS mirror exports."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from copy import deepcopy
from pathlib import Path, PurePosixPath

from akms.repo_wiki.config import load_config
from akms.repo_wiki.export.akms import (
    DEFAULT_KNOWLEDGE_DIR,
    ErrorRecord,
    ExportResult,
    RemovedRecord,
    SelectedRecord,
    SkippedRecord,
    WrittenRecord,
    atomic_write_text,
    build_mirror_document,
    canonical_generated_at,
    mirror_content_ref,
    mirror_document_path,
    mirror_node_id,
    normalize_source_path,
    render_mirror_markdown,
    validate_knowledge_dir,
)
from akms.repo_wiki.extract.registry import extract_files
from akms.repo_wiki.hashing import sha256_text
from akms.repo_wiki.locking import (
    OUTPUT_LOCK_FILENAME,
    OUTPUT_LOCK_PREFIX,
    LockError,
    RepoLocalLock,
    output_lock_path,
)
from akms.repo_wiki.models import Language, SkippedFile, SourceFile
from akms.repo_wiki.scanner import (
    LANGUAGE_BY_SUFFIX,
    LANGUAGE_INCLUDE_GLOBS,
    scan_repository,
)
from akms.repo_wiki.simple_yaml import load_yaml

__all__ = ["export_akms"]


def export_akms(
    *,
    repo_root: Path,
    output_root: Path,
    phase: int,
    generated_at: str,
    changed_only: bool = False,
    prune: bool = False,
    source_paths: Sequence[str] | None = None,
    git_base: str | None = None,
    git_head: str | None = None,
    acquire_lock: bool = True,
    force_lock: bool = False,
    knowledge_dir: str = DEFAULT_KNOWLEDGE_DIR,
    strict_parse: bool = False,
) -> ExportResult:
    """Export eligible sources into an AKMS mirror tree; all rendering precedes the first write.

    Mirrors go to ``<output_root>/<knowledge_dir>/code-mirror/``. Pruning runs only
    after every write succeeds; ``force_lock`` never steals a live lock.

    A source that fails to parse is recorded in ``skipped`` with reason
    ``parse_error``; its existing mirror is kept (and never pruned) and the
    remaining sources are exported. With ``strict_parse`` a parse failure is an
    error instead, and nothing is written.
    """

    root = repo_root.resolve()
    output = output_root.resolve()
    timestamp = canonical_generated_at(generated_at)
    if isinstance(phase, bool) or phase < 1:
        raise ValueError(f"phase must be a positive integer, got {phase!r}")
    if not root.is_dir():
        raise ValueError(f"repository root is not a directory: {root}")
    if output.exists() and not output.is_dir():
        raise ValueError(f"output path is not a directory: {output}")
    if source_paths is not None and git_base is not None:
        raise ValueError("source_paths and git_base selection are mutually exclusive")
    if git_head is not None and git_base is None:
        raise ValueError("git_head requires git_base")
    validate_knowledge_dir(knowledge_dir)

    lock: RepoLocalLock | None = None
    if acquire_lock:
        lock = RepoLocalLock(
            root,
            force=force_lock,
            purpose="export-akms",
            lock_file=output_lock_path(output),
        )
        try:
            lock.acquire()
        except LockError:
            raise
        except OSError as exc:
            raise LockError(f"failed to acquire export lock: {exc}") from exc

    try:
        return _export_akms_locked(
            root=root,
            output=output,
            phase=phase,
            timestamp=timestamp,
            changed_only=changed_only,
            prune=prune,
            source_paths=source_paths,
            git_base=git_base,
            git_head=git_head,
            knowledge_dir=knowledge_dir,
            strict_parse=strict_parse,
        )
    finally:
        if lock is not None:
            lock.release()


def _export_akms_locked(
    *,
    root: Path,
    output: Path,
    phase: int,
    timestamp: str,
    changed_only: bool,
    prune: bool,
    source_paths: Sequence[str] | None,
    git_base: str | None,
    git_head: str | None,
    knowledge_dir: str,
    strict_parse: bool = False,
) -> ExportResult:
    result = ExportResult(phase=phase, generated_at=timestamp)
    selection_meta: dict[str, object]
    path_filter: set[str] | None

    try:
        path_filter, selection_meta, deleted = _resolve_selection(
            root,
            source_paths=source_paths,
            git_base=git_base,
            git_head=git_head,
            exporter_owned=_exporter_owned_paths(root, output, knowledge_dir),
        )
    except (OSError, ValueError) as exc:
        result.selection = {
            "mode": "git_diff"
            if git_base is not None
            else ("paths" if source_paths is not None else "full"),
            "error": str(exc),
        }
        result.errors.append(ErrorRecord(None, None, "selection", str(exc)))
        return result

    result.selection = selection_meta
    partial_selection = path_filter is not None
    if prune and partial_selection:
        message = "prune is only safe for full export; refuse prune with path or git-diff selection"
        result.errors.append(ErrorRecord(None, None, "validation", message))
        return result

    config = _config_excluding_output(root, output, knowledge_dir)
    sources, scanner_skips = scan_repository(root, config)
    _record_undecodable_source_errors(root, scanner_skips, result)

    if path_filter is not None:
        available = {source.path for source in sources}
        selection_mode = str(selection_meta.get("mode") or "")
        # Explicit --path lists fail closed on bad paths; git-diff selection ignores non-sources.
        if selection_mode == "paths":
            missing = sorted(path_filter - available)
            # A selected path that is gone from disk is a deleted source: its
            # mirror is removed below. Only a path that still exists, or never
            # had a mirror, is an error.
            gone = {
                path
                for path in missing
                if not (root / path).exists()
                and _owned_mirrors_of(output, path, knowledge_dir)
            }
            deleted |= gone
            for missing_path in (path for path in missing if path not in gone):
                result.errors.append(
                    ErrorRecord(
                        missing_path,
                        None,
                        "selection",
                        "selected source path is not an eligible repository source",
                    )
                )
        sources = [source for source in sources if source.path in path_filter]

    supported: list[SourceFile] = []
    source_text: dict[str, str] = {}
    for source in sources:
        if source.language not in {language.value for language in Language}:
            result.skipped.append(
                SkippedRecord(
                    source_path=source.path,
                    language=source.language,
                    source_hash=source.content_hash,
                    reason="unsupported_language",
                )
            )
            continue
        try:
            text = _read_source_text(Path(source.abs_path))
        except (OSError, UnicodeDecodeError) as exc:
            result.errors.append(
                ErrorRecord(source.path, source.language, "decode", str(exc))
            )
            continue
        if sha256_text(text) != source.content_hash:
            result.errors.append(
                ErrorRecord(
                    source.path,
                    source.language,
                    "validation",
                    "source bytes changed after scanning",
                )
            )
            continue
        supported.append(source)
        source_text[source.path] = text
        result.selected.append(
            SelectedRecord(
                source_path=source.path,
                language=source.language,
                source_hash=source.content_hash,
            )
        )

    if any(error.stage == "selection" for error in result.errors):
        return result

    try:
        extraction = extract_files(supported, config)
    except Exception as exc:
        result.errors.append(ErrorRecord(None, None, "parse", str(exc)))
        return result
    staged: list[tuple[SourceFile, str, str, Path]] = []
    expected_paths: set[str] = set()
    render_failed = bool(result.errors)

    for source in supported:
        parsed = extraction.parsed_modules.get(source.path)
        if parsed is None:
            if not strict_parse:
                _skip_unparsable(
                    result, source, expected_paths, knowledge_dir=knowledge_dir
                )
                continue
            result.errors.append(
                ErrorRecord(
                    source.path,
                    source.language,
                    "parse",
                    "no configured extractor produced a parsed module",
                )
            )
            render_failed = True
            continue
        # Project backends may return placeholder file metadata; the scanner record is canonical.
        parsed.source_file = source
        if parsed.errors:
            if not strict_parse and all(
                error.stage == "parse" for error in parsed.errors
            ):
                _skip_unparsable(
                    result, source, expected_paths, knowledge_dir=knowledge_dir
                )
                continue
            for error in parsed.errors:
                location = f" at line {error.line}" if error.line is not None else ""
                result.errors.append(
                    ErrorRecord(
                        source.path,
                        source.language,
                        error.stage,
                        f"{error.message}{location}",
                    )
                )
            render_failed = True
            continue
        try:
            document = build_mirror_document(
                source_path=source.path,
                language=source.language,
                source_hash=source.content_hash,
                phase=phase,
                generated_at=timestamp,
                knowledge_dir=knowledge_dir,
            )
            markdown = render_mirror_markdown(
                parsed, source_text[source.path], document
            )
        except Exception as exc:
            result.errors.append(
                ErrorRecord(source.path, source.language, "render", str(exc))
            )
            render_failed = True
            continue

        target = output / document.generated_path
        expected_paths.add(document.generated_path)
        try:
            unchanged = (
                changed_only
                and target.is_file()
                and target.read_bytes() == markdown.encode("utf-8")
            )
        except OSError as exc:
            result.errors.append(
                ErrorRecord(source.path, source.language, "validation", str(exc))
            )
            render_failed = True
            continue
        if unchanged:
            result.skipped.append(
                SkippedRecord(
                    source_path=source.path,
                    language=source.language,
                    source_hash=source.content_hash,
                    reason="unchanged",
                )
            )
        else:
            staged.append((source, markdown, document.generated_path, target))

    if render_failed:
        return result

    for source, markdown, generated_path, target in staged:
        try:
            atomic_write_text(target, markdown)
        except Exception as exc:
            result.errors.append(
                ErrorRecord(source.path, source.language, "write", str(exc))
            )
            continue
        result.written.append(
            WrittenRecord(
                source_path=source.path,
                language=source.language,
                source_hash=source.content_hash,
                node_id=mirror_node_id(source.path, source.language),
                content_ref=mirror_content_ref(source.path, source.language),
                generated_path=generated_path,
            )
        )

    if deleted and not result.errors:
        _remove_deleted_source_mirrors(output, sorted(deleted), result, knowledge_dir)
    if prune and not result.errors:
        _prune_stale_mirrors(output, expected_paths, result, knowledge_dir)
    return result


def _skip_unparsable(
    result: ExportResult,
    source: SourceFile,
    expected_paths: set[str],
    *,
    knowledge_dir: str,
) -> None:
    """Record a source that did not parse; keep its existing mirror and exempt it from pruning."""

    result.skipped.append(
        SkippedRecord(
            source_path=source.path,
            language=source.language,
            source_hash=source.content_hash,
            reason="parse_error",
        )
    )
    expected_paths.add(
        mirror_document_path(source.path, source.language, knowledge_dir)
    )


def _resolve_selection(
    repo_root: Path,
    *,
    source_paths: Sequence[str] | None,
    git_base: str | None,
    git_head: str | None,
    exporter_owned: Callable[[str], bool] = lambda _path: False,
) -> tuple[set[str] | None, dict[str, object], set[str]]:
    """Return ``(path_filter, selection_metadata, deleted_sources)``.

    A ``None`` filter means full export. ``deleted_sources`` are sources the
    git selection saw deleted or renamed away; their mirrors are removed.
    """

    if source_paths is not None:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in source_paths:
            path = normalize_source_path(str(raw))
            if path not in seen:
                seen.add(path)
                normalized.append(path)
        if not normalized:
            raise ValueError("source_paths selection requires at least one path")
        return (
            set(normalized),
            {
                "mode": "paths",
                "requested_paths": normalized,
                "dirty_worktree": None,
                "git_base": None,
                "git_head": None,
            },
            set(),
        )

    if git_base is not None:
        return _git_diff_paths(
            repo_root, base=git_base, head=git_head, exporter_owned=exporter_owned
        )

    return (
        None,
        {
            "mode": "full",
            "requested_paths": None,
            "dirty_worktree": None,
            "git_base": None,
            "git_head": None,
        },
        set(),
    )


def _git_diff_paths(
    repo_root: Path,
    *,
    base: str,
    head: str | None,
    exporter_owned: Callable[[str], bool] = lambda _path: False,
) -> tuple[set[str], dict[str, object], set[str]]:
    """Select repository-relative paths changed between git refs / worktree.

    Against the worktree, untracked files that git does not ignore count as
    changed: a new source is mirrored before it is added. Sources deleted or
    renamed away are returned separately so their mirrors can be removed.
    """

    _require_git_repo(repo_root)
    _require_git_ref(repo_root, base)
    dirty = _worktree_is_dirty(repo_root)

    # -z + core.quotepath=false: default git quoting mangles non-ASCII names (caf\303\251.py).
    if head is not None:
        _require_git_ref(repo_root, head)
        if dirty:
            raise ValueError(
                "git two-ref selection refuses a dirty worktree; "
                "commit, stash, or omit --git-head to diff against the worktree"
            )
        revisions = [f"{base}...{head}"]
        head_label: str | None = head
    else:
        revisions = [base]
        head_label = None

    paths = _git_paths(
        repo_root, ["diff", "-z", "--name-only", "--diff-filter=ACMR", *revisions]
    )
    deleted = _git_paths(
        repo_root,
        ["diff", "-z", "--name-only", "--no-renames", "--diff-filter=D", *revisions],
    )
    if head is None:
        untracked = _git_paths(
            repo_root, ["ls-files", "-z", "--others", "--exclude-standard"]
        )
        paths |= {path for path in untracked if not exporter_owned(path)}
    deleted -= paths

    return (
        paths,
        {
            "mode": "git_diff",
            "requested_paths": sorted(paths),
            "dirty_worktree": dirty,
            "git_base": base,
            "git_head": head_label,
        },
        deleted,
    )


def _exporter_owned_paths(
    repo_root: Path, output_root: Path, knowledge_dir: str
) -> Callable[[str], bool]:
    """Match the exporter's own lock files and mirror tree, as repo-relative paths."""

    try:
        mirror_root = (
            (output_root / knowledge_dir / "code-mirror")
            .relative_to(repo_root)
            .as_posix()
        )
    except ValueError:
        mirror_root = None

    def owned(path: str) -> bool:
        name = PurePosixPath(path).name
        if name == OUTPUT_LOCK_FILENAME or (
            name.startswith(OUTPUT_LOCK_PREFIX) and name.endswith(".lock")
        ):
            return True
        return mirror_root is not None and (
            path == mirror_root or path.startswith(f"{mirror_root}/")
        )

    return owned


def _git_paths(repo_root: Path, arguments: list[str]) -> set[str]:
    """Run a NUL-separated git path listing and normalize the result."""

    # -z + core.quotepath=false: default git quoting mangles non-ASCII names (caf\303\251.py).
    argv = ["git", "-C", str(repo_root), "-c", "core.quotepath=false", *arguments]
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        argv,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = (
            (completed.stderr or completed.stdout or b"git selection failed")
            .decode("utf-8", errors="replace")
            .strip()
        )
        raise ValueError(f"git selection failed: {detail}")

    paths: set[str] = set()
    for raw_bytes in completed.stdout.split(b"\0"):
        if not raw_bytes:
            continue
        try:
            raw = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            # Non-UTF-8 git paths are not portable identities; ignore them rather than rewrite.
            continue
        try:
            paths.add(normalize_source_path(raw))
        except ValueError:
            continue
    return paths


def _require_git_repo(repo_root: Path) -> None:
    completed = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo_root), "rev-parse", "--is-inside-work-tree"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 or completed.stdout.strip() != "true":
        raise ValueError(f"repository root is not a git work tree: {repo_root}")


def _require_git_ref(repo_root: Path, ref: str) -> None:
    if not ref or ref.startswith("-"):
        raise ValueError(f"invalid git ref: {ref!r}")
    completed = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo_root), "rev-parse", "--verify", f"{ref}^{{commit}}"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown ref").strip()
        raise ValueError(f"missing or invalid git ref {ref!r}: {detail}")


def _worktree_is_dirty(repo_root: Path) -> bool:
    """Whether the worktree has source-relevant changes (ignores ``.repo_wiki/``, export locks)."""

    completed = subprocess.run(  # noqa: S603
        ["git", "-C", str(repo_root), "status", "--porcelain", "-uall"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "git status failed").strip()
        raise ValueError(f"unable to determine worktree dirtiness: {detail}")
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        body = line[3:] if len(line) > 3 else line
        path = body.split(" -> ", 1)[-1].strip().replace("\\", "/")
        if path.startswith(".repo_wiki/") or path == ".repo_wiki":
            continue
        name = path.rsplit("/", 1)[-1]
        if name == ".repo2md-export.lock" or (
            name.startswith(".repo2md-export-") and name.endswith(".lock")
        ):
            continue
        return True
    return False


def _read_source_text(path: Path) -> str:
    """Read strict UTF-8 without universal-newline translation."""

    with path.open("r", encoding="utf-8", errors="strict", newline="") as handle:
        return handle.read()


def _config_excluding_output(
    repo_root: Path, output_root: Path, knowledge_dir: str
) -> dict[str, object]:
    config = deepcopy(load_config(repo_root))
    scanner = config.get("scanner")
    if isinstance(scanner, dict):
        included = [str(item) for item in scanner.get("include", [])]
        language_patterns: list[str] = []
        languages = config.get("languages")
        if isinstance(languages, dict):
            for language, patterns in LANGUAGE_INCLUDE_GLOBS.items():
                entry = languages.get(language)
                enabled = (
                    entry.get("enabled", False)
                    if isinstance(entry, dict)
                    else bool(entry)
                )
                if enabled:
                    language_patterns.extend(patterns)
        root_forms = [
            pattern[3:]
            for pattern in [*included, *language_patterns]
            if pattern.startswith("**/")
        ]
        scanner["include"] = list(dict.fromkeys([*included, *root_forms]))

    mirror_root = output_root / knowledge_dir / "code-mirror"
    try:
        relative = mirror_root.relative_to(repo_root).as_posix()
    except ValueError:
        return config
    if isinstance(scanner, dict):
        excluded = [str(item) for item in scanner.get("exclude", [])]
        scanner["exclude"] = [*excluded, f"{relative}/**"]
    return config


def _record_undecodable_source_errors(
    repo_root: Path,
    scanner_skips: list[SkippedFile],
    result: ExportResult,
) -> None:
    """Promote invalid UTF-8 code files from scanner skips to export errors."""

    supported = {language.value for language in Language}
    for skipped in scanner_skips:
        path_value = skipped.path
        if skipped.reason != "binary":
            continue
        language = LANGUAGE_BY_SUFFIX.get(Path(path_value).suffix.lower())
        if language not in supported:
            continue
        path = repo_root / path_value
        try:
            data = path.read_bytes()
        except OSError as exc:
            result.errors.append(ErrorRecord(path_value, language, "decode", str(exc)))
            continue
        if b"\x00" in data:
            continue
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            result.errors.append(ErrorRecord(path_value, language, "decode", str(exc)))


def _prune_stale_mirrors(
    output_root: Path,
    expected_paths: set[str],
    result: ExportResult,
    knowledge_dir: str,
) -> None:
    mirror_root = output_root / knowledge_dir / "code-mirror"
    if not mirror_root.is_dir():
        return
    for path in sorted(mirror_root.rglob("*.md")):
        generated_path = path.relative_to(output_root).as_posix()
        if generated_path in expected_paths:
            continue
        record = _owned_removed_record(path, generated_path, knowledge_dir)
        if record is None:
            continue
        try:
            path.unlink()
        except OSError as exc:
            result.errors.append(
                ErrorRecord(record.source_path, record.language, "prune", str(exc))
            )
            return
        result.removed.append(record)


def _owned_mirrors_of(
    output_root: Path, source_path: str, knowledge_dir: str
) -> list[tuple[Path, RemovedRecord]]:
    """Exporter-owned mirror documents for ``source_path``, one per language at most."""

    owned: list[tuple[Path, RemovedRecord]] = []
    for language in Language:
        generated_path = mirror_document_path(source_path, language, knowledge_dir)
        path = output_root / generated_path
        if not path.is_file():
            continue
        record = _owned_removed_record(path, generated_path, knowledge_dir)
        if record is not None and record.source_path == source_path:
            owned.append((path, record))
    return owned


def _remove_deleted_source_mirrors(
    output_root: Path,
    source_paths: list[str],
    result: ExportResult,
    knowledge_dir: str,
) -> None:
    """Remove the owned mirrors of sources that no longer exist."""

    for source_path in source_paths:
        for path, record in _owned_mirrors_of(output_root, source_path, knowledge_dir):
            try:
                path.unlink()
            except OSError as exc:
                result.errors.append(
                    ErrorRecord(record.source_path, record.language, "prune", str(exc))
                )
                return
            result.removed.append(record)


def _owned_removed_record(
    path: Path, generated_path: str, knowledge_dir: str
) -> RemovedRecord | None:
    try:
        markdown = _read_source_text(path)
        if not markdown.startswith("---\n"):
            return None
        raw_frontmatter, separator, _ = markdown[4:].partition("---\n")
        if not separator:
            return None
        metadata = load_yaml(raw_frontmatter)
        source_path = metadata.get("source_file")
        node_id = metadata.get("id")
        content_ref = metadata.get("content_ref")
        if (
            metadata.get("domain") != "code-mirror"
            or metadata.get("source") != "generated"
            or metadata.get("auto_update") is not True
            or metadata.get("akms_schema") != "v2"
        ):
            return None
        if (
            not isinstance(source_path, str)
            or not isinstance(node_id, str)
            or not isinstance(content_ref, str)
        ):
            return None
        matches = [
            language.value
            for language in Language
            if mirror_document_path(source_path, language, knowledge_dir)
            == generated_path
            and mirror_node_id(source_path, language) == node_id
            and mirror_content_ref(source_path, language) == content_ref
        ]
    except (OSError, TypeError, UnicodeDecodeError, ValueError):
        return None
    if len(matches) != 1:
        return None
    return RemovedRecord(
        source_path=source_path,
        language=matches[0],
        node_id=node_id,
        content_ref=content_ref,
        generated_path=generated_path,
    )
