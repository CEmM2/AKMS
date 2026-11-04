"""Versioned on-disk ``ParsedModule`` IR cache (relative paths only); bad entries isolated."""

from __future__ import annotations

import json
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from akms.repo_wiki.models import ParsedModule, SourceFile

# 3: Python IR gained receivers, table_refs and dispatch_tables.
CACHE_SCHEMA_VERSION = 3
CACHE_DIR = ".repo_wiki/ir_cache"
_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CacheDiagnostics:
    """Counters describing IR-cache outcomes for a single build."""

    hits: int = 0
    misses: int = 0
    writes: int = 0
    invalidations: int = 0
    corruptions: int = 0
    removals: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "writes": self.writes,
            "invalidations": self.invalidations,
            "corruptions": self.corruptions,
            "removals": self.removals,
            "notes": list(self.notes),
        }


@dataclass(slots=True)
class CacheRecord:
    """One validated IR-cache entry for a source file."""

    source_path: str
    source_hash: str
    language: str
    backend: str
    backend_version: str
    cache_schema_version: int
    parsed_module: ParsedModule

    def to_dict(self) -> dict[str, object]:
        module_payload = dict(self.parsed_module.to_dict())
        # Never persist absolute paths; rehydrate from repo_root on load.
        source_raw = module_payload.get("source_file")
        source_file: dict[str, object] = (
            dict(source_raw) if isinstance(source_raw, dict) else {}
        )
        source_file["abs_path"] = self.source_path
        module_payload["source_file"] = source_file
        return {
            "cache_schema_version": self.cache_schema_version,
            "source_path": self.source_path,
            "source_hash": self.source_hash,
            "language": self.language,
            "backend": self.backend,
            "backend_version": self.backend_version,
            "parsed_module": module_payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object], repo_root: Path) -> "CacheRecord":
        module_raw = data.get("parsed_module")
        if not isinstance(module_raw, dict):
            raise ValueError("cache record missing parsed_module object")
        module = ParsedModule.from_dict(module_raw, repo_root=repo_root)
        return cls(
            source_path=str(data["source_path"]),
            source_hash=str(data["source_hash"]),
            language=str(data["language"]),
            backend=str(data["backend"]),
            backend_version=str(data["backend_version"]),
            cache_schema_version=int(data["cache_schema_version"]),  # type: ignore[arg-type]
            parsed_module=module,
        )


def cache_root(repo_root: Path) -> Path:
    return repo_root / CACHE_DIR


def _normalized_rel_path(source_path: str) -> Path:
    """Return a relative path safe under the cache root (rejects absolute paths and ``..``)."""
    rel = source_path.replace("\\", "/").strip()
    if not rel or rel == ".":
        raise ValueError(f"invalid empty source path for ir_cache: {source_path!r}")
    path = Path(rel)
    if path.is_absolute() or getattr(path, "drive", ""):
        raise ValueError(
            f"absolute source path not allowed in ir_cache: {source_path!r}"
        )
    parts = path.parts
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"source path escapes ir_cache root: {source_path!r}")
    return Path(*parts)


def cache_path_for(repo_root: Path, source_path: str) -> Path:
    """Return the collision-free cache file for a source: its relative path plus ``.json``."""
    rel = _normalized_rel_path(source_path)
    return cache_root(repo_root) / Path(*rel.parts[:-1], rel.parts[-1] + ".json")


def legacy_flat_cache_path(repo_root: Path, source_path: str) -> Path:
    """Legacy flat cache path (``/`` -> ``__``), kept only for migration on load."""
    safe = source_path.replace("\\", "/").replace("/", "__")
    safe = "".join(ch if ch.isalnum() or ch in "._-@" else "_" for ch in safe)
    return cache_root(repo_root) / f"{safe}.json"


def _cleanup_empty_cache_parents(start: Path, stop_at: Path) -> None:
    """Remove empty directories from *start* up to (but not including) *stop_at*."""

    try:
        stop = stop_at.resolve()
        current = start.resolve()
    except OSError:
        return
    while current != stop:
        try:
            if stop not in current.parents:
                break
        except (ValueError, OSError):
            break
        try:
            next(current.iterdir())
            break  # non-empty
        except StopIteration:
            pass
        except OSError:
            break
        parent = current.parent
        try:
            current.rmdir()
        except OSError:
            break
        current = parent


def _delete_legacy_flat(repo_root: Path, source_path: str) -> None:
    """Best-effort removal of a legacy flat cache file for *source_path*."""

    try:
        nested = cache_path_for(repo_root, source_path)
        legacy = legacy_flat_cache_path(repo_root, source_path)
    except ValueError:
        return
    if legacy == nested:
        return
    try:
        if legacy.is_file():
            legacy.unlink()
    except OSError:
        pass


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
        temporary.replace(path)
    except Exception:
        if temporary is not None and temporary.exists():
            temporary.unlink(missing_ok=True)
        raise


def write_cache_record(
    repo_root: Path,
    *,
    source: SourceFile,
    backend: str,
    backend_version: str,
    parsed: ParsedModule,
    diagnostics: CacheDiagnostics | None = None,
) -> Path:
    """Persist a complete ``ParsedModule`` for *source* and return the cache path."""

    record = CacheRecord(
        source_path=source.path,
        source_hash=source.content_hash,
        language=source.language,
        backend=backend,
        backend_version=backend_version,
        cache_schema_version=CACHE_SCHEMA_VERSION,
        parsed_module=parsed,
    )
    path = cache_path_for(repo_root, source.path)
    _atomic_write_json(path, record.to_dict())
    _delete_legacy_flat(repo_root, source.path)
    if diagnostics is not None:
        diagnostics.writes += 1
    return path


def _read_cache_file(
    path: Path,
    repo_root: Path,
    source_path: str,
    diagnostics: CacheDiagnostics | None,
) -> CacheRecord | None:
    """Parse a cache file into a ``CacheRecord``, or isolate corrupt content."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("cache root is not an object")
        return CacheRecord.from_dict(raw, repo_root)
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
        KeyError,
    ) as exc:
        _isolate_corrupt(path, diagnostics, source_path, str(exc))
        return None


def _validate_record_identity(
    record: CacheRecord,
    *,
    source: SourceFile,
    backend: str,
    backend_version: str,
    require_hash_match: bool,
    diagnostics: CacheDiagnostics | None,
) -> bool:
    """Return True when *record* is usable for the requested identity checks."""

    if record.cache_schema_version != CACHE_SCHEMA_VERSION:
        if diagnostics is not None:
            diagnostics.invalidations += 1
            diagnostics.notes.append(
                f"ir_cache: schema mismatch for {source.path} "
                f"(have {record.cache_schema_version}, want {CACHE_SCHEMA_VERSION})"
            )
        return False
    if record.source_path != source.path:
        if diagnostics is not None:
            diagnostics.invalidations += 1
            diagnostics.notes.append(f"ir_cache: path mismatch for {source.path}")
        return False
    if require_hash_match and record.source_hash != source.content_hash:
        if diagnostics is not None:
            diagnostics.invalidations += 1
        return False
    if record.language != source.language:
        if diagnostics is not None:
            diagnostics.invalidations += 1
            diagnostics.notes.append(
                f"ir_cache: language mismatch for {source.path} "
                f"(have {record.language}, want {source.language})"
            )
        return False
    if record.backend != backend or record.backend_version != backend_version:
        if diagnostics is not None:
            diagnostics.invalidations += 1
            diagnostics.notes.append(
                f"ir_cache: backend mismatch for {source.path} "
                f"(have {record.backend}@{record.backend_version}, "
                f"want {backend}@{backend_version})"
            )
        return False
    return True


def _rehydrate_module(
    record: CacheRecord, source: SourceFile, repo_root: Path
) -> ParsedModule:
    """Attach current-repo abs_path / size while preserving cached IR contents."""

    module = record.parsed_module
    module.source_file.abs_path = str((repo_root / source.path).resolve())
    module.source_file.path = source.path
    # Keep the record's content_hash when the source has diverged (parse-fail retention).
    if record.source_hash == source.content_hash:
        module.source_file.content_hash = source.content_hash
        module.source_file.size_bytes = source.size_bytes
    return module


def load_cache_record(
    repo_root: Path,
    *,
    source: SourceFile,
    backend: str,
    backend_version: str,
    diagnostics: CacheDiagnostics | None = None,
) -> ParsedModule | None:
    """Load a valid cache record for *source*, or ``None`` if missing/invalid.

    Corrupt files are renamed with a ``.corrupt`` suffix; a valid legacy flat entry is migrated.
    """

    path = cache_path_for(repo_root, source.path)
    from_legacy = False
    if not path.is_file():
        legacy = legacy_flat_cache_path(repo_root, source.path)
        if legacy.is_file() and legacy != path:
            path = legacy
            from_legacy = True
        else:
            if diagnostics is not None:
                diagnostics.misses += 1
            return None

    record = _read_cache_file(path, repo_root, source.path, diagnostics)
    if record is None:
        return None

    if not _validate_record_identity(
        record,
        source=source,
        backend=backend,
        backend_version=backend_version,
        require_hash_match=True,
        diagnostics=diagnostics,
    ):
        return None

    module = _rehydrate_module(record, source, repo_root)
    if from_legacy:
        try:
            write_cache_record(
                repo_root,
                source=source,
                backend=backend,
                backend_version=backend_version,
                parsed=module,
                diagnostics=None,  # migration is not a logical "write" for build stats
            )
            _delete_legacy_flat(repo_root, source.path)
            if diagnostics is not None:
                diagnostics.notes.append(
                    f"ir_cache: migrated legacy flat cache for {source.path}"
                )
        except OSError as exc:
            _logger.warning(
                "ir_cache: failed to migrate legacy cache for %s: %s", source.path, exc
            )
    if diagnostics is not None:
        diagnostics.hits += 1
    return module


def load_prior_cache_module(
    repo_root: Path,
    *,
    source: SourceFile,
    backend: str,
    backend_version: str,
    diagnostics: CacheDiagnostics | None = None,
) -> ParsedModule | None:
    """Load a prior IR for *source* ignoring content-hash mismatch (for parse failures).

    Returns ``None`` if missing, corrupt, mismatched or carrying parse errors; not a cache hit.
    """

    path = cache_path_for(repo_root, source.path)
    if not path.is_file():
        legacy = legacy_flat_cache_path(repo_root, source.path)
        if legacy.is_file() and legacy != path:
            path = legacy
        else:
            return None

    record = _read_cache_file(path, repo_root, source.path, diagnostics)
    if record is None:
        return None
    if not _validate_record_identity(
        record,
        source=source,
        backend=backend,
        backend_version=backend_version,
        require_hash_match=False,
        diagnostics=None,  # hash-ignore path: don't treat mismatch as invalidation
    ):
        return None
    if record.parsed_module.errors:
        return None
    return _rehydrate_module(record, source, repo_root)


def _isolate_corrupt(
    path: Path,
    diagnostics: CacheDiagnostics | None,
    source_path: str,
    detail: str,
) -> None:
    quarantine = path.with_suffix(path.suffix + ".corrupt")
    try:
        if quarantine.exists():
            quarantine.unlink()
        path.replace(quarantine)
    except OSError:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    _logger.warning("ir_cache: corrupt entry for %s: %s", source_path, detail)
    if diagnostics is not None:
        diagnostics.corruptions += 1
        diagnostics.misses += 1
        diagnostics.notes.append(
            f"ir_cache: corrupt entry isolated for {source_path}: {detail}"
        )


def remove_cache_record(
    repo_root: Path,
    source_path: str,
    *,
    diagnostics: CacheDiagnostics | None = None,
) -> bool:
    """Delete the cache file (and legacy flat entry) for *source_path*; True if removed."""

    removed = False
    try:
        path = cache_path_for(repo_root, source_path)
    except ValueError:
        return False
    if path.is_file():
        path.unlink()
        removed = True
        _cleanup_empty_cache_parents(path.parent, stop_at=cache_root(repo_root))
    try:
        legacy = legacy_flat_cache_path(repo_root, source_path)
    except ValueError:
        legacy = None
    if legacy is not None and legacy.is_file() and legacy != path:
        try:
            legacy.unlink()
            removed = True
        except OSError:
            pass
    if removed and diagnostics is not None:
        diagnostics.removals += 1
    return removed


def list_cached_source_paths(repo_root: Path) -> list[str]:
    """Return repository-relative source paths that have a cache file (unreadable files skipped)."""
    root = cache_root(repo_root)
    if not root.is_dir():
        return []
    paths: list[str] = []
    for path in sorted(root.rglob("*.json")):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            source_path = data.get("source_path")
            if isinstance(source_path, str):
                paths.append(source_path)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            AttributeError,
        ):
            continue
    return paths


def _normalize_backend_version(version: str | None) -> str:
    """Return a non-empty backend version string (stdlib-safe; no manifest import)."""

    if version is None:
        return "unknown"
    trimmed = version.strip()
    return trimmed if trimmed else "unknown"


def backend_identity(
    language: str,
    config: dict[str, Any],
    *,
    tool_version: str | None = None,
) -> tuple[str, str]:
    """Return ``(backend_name, backend_version)`` for cache keys; version defaults to "stdlib"."""
    from akms.repo_wiki.extract.registry import get_backend, resolve_backend_name

    name = resolve_backend_name(language, config) or "unknown"
    if tool_version is not None:
        return name, _normalize_backend_version(tool_version)
    backend = get_backend(language, config)
    probe = getattr(backend, "tool_version", None)
    if callable(probe):
        raw = probe()
        return name, _normalize_backend_version(raw if isinstance(raw, str) else None)
    return name, "stdlib"
