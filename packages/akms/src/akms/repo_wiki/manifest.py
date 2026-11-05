"""Manifest persistence and build orchestration."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from akms.repo_wiki.config import init_repo_wiki, load_config
from akms.repo_wiki.errors import BuildError
from akms.repo_wiki.graph import build_symbol_graph, write_symbol_graph
from akms.repo_wiki.hashing import sha256_text
from akms.repo_wiki.index import update_index
from akms.repo_wiki.extract.base import ProjectExtractor
from akms.repo_wiki.extract.registry import (
    extract_files,
    get_backend,
    resolve_backend_name,
)
from akms.repo_wiki.ir_cache import (
    CacheDiagnostics,
    backend_identity,
    load_cache_record,
    load_prior_cache_module,
    remove_cache_record,
    write_cache_record,
)
from akms.repo_wiki.models import (
    BuildSummary,
    Language,
    Manifest,
    ManifestFile,
    ParsedModule,
    SourceFile,
)
from akms.repo_wiki.paths import module_name_from_path, read_source, safe_doc_name
from akms.repo_wiki.render_markdown import (
    repo_commit,
    write_module_doc,
    write_repo_map,
    write_symbol_doc,
)
from akms.repo_wiki.scanner import scan_repository
from akms.repo_wiki.summarize import prepare_summaries, prune_summary_cache
from akms.repo_wiki.symbol_ids import build_symbol_id

MANIFEST_PATH = ".repo_wiki/manifest.json"
BUILD_ERRORS_PATH = ".repo_wiki/build_errors.json"

# Manifests without ``schema_version`` (or with 1) are v1 and migrated on load.
SCHEMA_VERSION = 2

# ``Manifest.repo`` key for project-backend state {language: {set_hash, tool_version}}.
LANGUAGES_KEY = "languages"

BACKEND_NOTES_KEY = "backend_notes"

# Sentinel for an unprobeable tool version (keeps set hashes reproducible).
UNKNOWN_TOOL_VERSION = "unknown"

_logger = logging.getLogger(__name__)


def tool_version_or_unknown(version: str | None) -> str:
    """Return the trimmed ``version``, or the ``unknown`` sentinel when None or empty."""
    if version is None:
        return UNKNOWN_TOOL_VERSION
    trimmed = version.strip()
    return trimmed if trimmed else UNKNOWN_TOOL_VERSION


def compute_set_hash(file_hashes: Iterable[str], tool_version: str) -> str:
    """Order-independent ``sha256:`` hash of input file hashes plus the tool version."""
    unique_sorted = sorted(set(file_hashes))
    payload = "\n".join([tool_version, *unique_sorted])
    return sha256_text(payload)


def project_backend_needs_rerun(
    stored: dict[str, Any] | None,
    file_hashes: Iterable[str],
    tool_version: str,
) -> bool:
    """True when *stored* is None or the recomputed set hash differs."""
    if not stored:
        return True
    current = compute_set_hash(file_hashes, tool_version)
    return stored.get("set_hash") != current


def get_language_state(manifest: Manifest) -> dict[str, Any]:
    """Return the per-language project-backend state map (empty dict when absent)."""
    section = manifest.repo.get(LANGUAGES_KEY)
    return cast(dict[str, Any], section) if isinstance(section, dict) else {}


def set_language_state(
    manifest: Manifest, language: str, *, set_hash: str, tool_version: str
) -> None:
    """Record the set hash and tool version for *language* in ``manifest.repo[LANGUAGES_KEY]``."""
    section = manifest.repo.get(LANGUAGES_KEY)
    if not isinstance(section, dict):
        section = {}
        manifest.repo[LANGUAGES_KEY] = section
    section[language] = {"set_hash": set_hash, "tool_version": tool_version}


def get_backend_notes(manifest: Manifest) -> list[str]:
    """Return the backend notes stored in the manifest (empty list when absent)."""
    section = manifest.repo.get(BACKEND_NOTES_KEY)
    if isinstance(section, list):
        return [str(note) for note in section]
    return []


def _migrate_v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Return a new v2 manifest dict from a v1 one: symbol IDs and ``doc`` names are regenerated.

    Unmatched IDs are logged at WARNING and kept; the next full extraction resyncs them.
    """
    migrated: dict[str, Any] = dict(data)
    files_in = cast(dict[str, Any], data.get("files", {}))
    files_out: dict[str, Any] = {}
    for relpath, file_entry in files_in.items():
        entry = dict(file_entry)
        # Only Python symbols exist in v1; keep any other language but skip ID rewriting.
        is_python = str(entry.get("language", "python")) == "python"
        module_dotted = module_name_from_path(relpath)
        old_symbols = cast(dict[str, Any], entry.get("symbols", {}) or {})
        new_symbols: dict[str, Any] = {}
        # Relative "doc" paths differ from build paths; unused and overwritten on build.
        for old_id, sym in old_symbols.items():
            new_sym = dict(sym)
            if is_python and old_id.startswith(f"{module_dotted}."):
                qualname = old_id[len(module_dotted) + 1 :]
                new_id = build_symbol_id(Language.PYTHON, relpath, qualname)
                new_sym["doc"] = f"symbols/{safe_doc_name(new_id)}.md"
            elif is_python and old_id == module_dotted:
                qualname = module_dotted
                new_id = build_symbol_id(Language.PYTHON, relpath, qualname)
                new_sym["doc"] = f"symbols/{safe_doc_name(new_id)}.md"
            else:
                _logger.warning(
                    "manifest migration: could not derive qualname for v1 "
                    "symbol id %r in %r (module=%r); leaving ID unchanged",
                    old_id,
                    relpath,
                    module_dotted,
                )
                new_id = old_id
            new_symbols[new_id] = new_sym
        entry["symbols"] = new_symbols
        files_out[relpath] = entry
    migrated["files"] = files_out
    migrated["schema_version"] = SCHEMA_VERSION
    return migrated


def _is_v1(data: dict[str, Any]) -> bool:
    """Return True if the on-disk manifest predates the v2 schema."""
    version = data.get("schema_version")
    if version is None:
        return True
    try:
        return int(version) < SCHEMA_VERSION
    except (TypeError, ValueError):
        # Unparseable version: treat as v1 so migration normalises schema_version on write.
        return True


def load_manifest(repo_root: Path) -> Manifest:
    path = repo_root / MANIFEST_PATH
    if not path.exists():
        return Manifest({"name": repo_root.name, "last_commit": "unknown"}, {})
    data = json.loads(path.read_text(encoding="utf-8"))
    if _is_v1(data):
        data = _migrate_v1_to_v2(data)
    files = {
        rel: ManifestFile(
            language=item["language"],
            hash=item["hash"],
            module_doc=item.get("module_doc"),
            symbols=item.get("symbols", {}),
            summary_hash=item.get("summary_hash"),
            index_hash=item.get("index_hash"),
        )
        for rel, item in data.get("files", {}).items()
    }
    return Manifest(data.get("repo", {}), files)


def save_manifest(repo_root: Path, manifest: Manifest) -> Path:
    path = repo_root / MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = manifest.to_dict()
    payload["schema_version"] = SCHEMA_VERSION
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def write_errors(repo_root: Path, errors: list[BuildError]) -> Path:
    path = repo_root / BUILD_ERRORS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([error.to_dict() for error in errors], indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return path


def _project_languages_to_extract(
    manifest: Manifest,
    project_languages: dict[str, list[SourceFile]],
    config: dict[str, Any],
    *,
    changed_only: bool,
    force: bool,
) -> tuple[set[str], dict[str, dict[str, str]]]:
    """Decide which project-backed languages must re-extract this build.

    Returns the languages and, for those, the fresh ``{"set_hash", "tool_version"}`` to persist.
    """
    rerun: set[str] = set()
    state: dict[str, dict[str, str]] = {}
    stored_all = get_language_state(manifest)
    for language, files in project_languages.items():
        backend = get_backend(language, config)
        probe = getattr(backend, "tool_version", None)
        raw_version = probe() if callable(probe) else None
        current_version = tool_version_or_unknown(
            raw_version if isinstance(raw_version, str) else None
        )
        file_hashes = [source.content_hash for source in files]
        set_hash = compute_set_hash(file_hashes, current_version)
        needs = project_backend_needs_rerun(
            stored_all.get(language), file_hashes, current_version
        )
        if changed_only and not force and not needs:
            continue
        rerun.add(language)
        state[language] = {"set_hash": set_hash, "tool_version": current_version}
    return rerun, state


@dataclass(slots=True)
class ReconciliationPlan:
    """Removals after comparing the scan with the manifest/cache (repo-relative paths)."""

    deleted_sources: list[str] = field(default_factory=list)
    stale_symbol_docs: list[str] = field(default_factory=list)
    stale_module_docs: list[str] = field(default_factory=list)
    stale_summary_docs: list[str] = field(default_factory=list)
    cache_sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "deleted_sources": list(self.deleted_sources),
            "stale_symbol_docs": list(self.stale_symbol_docs),
            "stale_module_docs": list(self.stale_module_docs),
            "stale_summary_docs": list(self.stale_summary_docs),
            "cache_sources": list(self.cache_sources),
        }


def _infer_generation_output_dir(manifest: Manifest) -> str:
    """Best-effort generation output dir from existing manifest document paths."""

    for entry in manifest.files.values():
        if entry.module_doc:
            normalized = entry.module_doc.replace("\\", "/")
            marker = "/modules/"
            if marker in normalized:
                return normalized.split(marker, 1)[0]
        for meta in entry.symbols.values():
            doc = meta.get("doc")
            if isinstance(doc, str) and doc:
                normalized = doc.replace("\\", "/")
                marker = "/symbols/"
                if marker in normalized:
                    return normalized.split(marker, 1)[0]
    return ".repo_wiki/generated"


def _summary_doc_path(output_dir: str, symbol_id: str) -> str:
    """Return the repo-root-relative summary path for *symbol_id* (see ``write_summary_doc``)."""
    return f"{output_dir.rstrip('/')}/summaries/{safe_doc_name(symbol_id)}.summary.md"


def plan_reconciliation(
    manifest: Manifest,
    current_sources: dict[str, SourceFile],
    *,
    complete_modules: dict[str, ParsedModule] | None = None,
    repo_root: Path | None = None,
    output_dir: str | None = None,
) -> ReconciliationPlan:
    """Compute files to remove to match the current source tree; no filesystem access."""
    plan = ReconciliationPlan()
    generation_dir = output_dir or _infer_generation_output_dir(manifest)
    for path in sorted(manifest.files):
        if path not in current_sources:
            plan.deleted_sources.append(path)
            plan.cache_sources.append(path)
            entry = manifest.files[path]
            if entry.module_doc:
                plan.stale_module_docs.append(entry.module_doc)
            for symbol_id, meta in entry.symbols.items():
                doc = meta.get("doc")
                if isinstance(doc, str) and doc:
                    plan.stale_symbol_docs.append(doc)
                plan.stale_summary_docs.append(
                    _summary_doc_path(generation_dir, symbol_id)
                )

    if complete_modules is not None:
        for path, parsed in sorted(complete_modules.items()):
            previous = manifest.files.get(path)
            if previous is None:
                continue
            current_ids = {symbol.symbol_id for symbol in parsed.symbols}
            for symbol_id, meta in previous.symbols.items():
                if symbol_id in current_ids:
                    continue
                doc = meta.get("doc")
                if isinstance(doc, str) and doc:
                    plan.stale_symbol_docs.append(doc)
                plan.stale_summary_docs.append(
                    _summary_doc_path(generation_dir, symbol_id)
                )
            if previous.module_doc and parsed.module and "/" in previous.module_doc:
                prefix = previous.module_doc.rsplit("/", 1)[0]
                expected = f"{prefix}/{safe_doc_name(parsed.module)}.md"
                if previous.module_doc != expected:
                    plan.stale_module_docs.append(previous.module_doc)

    plan.deleted_sources = sorted(set(plan.deleted_sources))
    plan.cache_sources = sorted(set(plan.cache_sources))
    plan.stale_symbol_docs = sorted(set(plan.stale_symbol_docs))
    plan.stale_module_docs = sorted(set(plan.stale_module_docs))
    plan.stale_summary_docs = sorted(set(plan.stale_summary_docs))
    return plan


def execute_reconciliation(
    repo_root: Path,
    manifest: Manifest,
    plan: ReconciliationPlan,
    *,
    dry_run: bool = False,
    diagnostics: CacheDiagnostics | None = None,
) -> ReconciliationPlan:
    """Apply *plan* to manifest, IR cache and docs (not if *dry_run*); after a good build."""
    if dry_run:
        return plan

    for path in plan.deleted_sources:
        manifest.files.pop(path, None)
    for source_path in plan.cache_sources:
        remove_cache_record(repo_root, source_path, diagnostics=diagnostics)
    for rel in [
        *plan.stale_module_docs,
        *plan.stale_symbol_docs,
        *plan.stale_summary_docs,
    ]:
        target = repo_root / rel
        if target.is_file():
            try:
                target.unlink()
            except OSError:
                _logger.warning("reconciliation: failed to remove %s", rel)
    return plan


def _apply_cache_diagnostics(
    summary: BuildSummary, diagnostics: CacheDiagnostics
) -> None:
    summary.cache_hits = diagnostics.hits
    summary.cache_misses = diagnostics.misses
    summary.cache_writes = diagnostics.writes
    summary.cache_invalidations = diagnostics.invalidations
    summary.cache_corruptions = diagnostics.corruptions
    summary.cache_removals = diagnostics.removals
    if diagnostics.notes:
        summary.backend_notes = [*summary.backend_notes, *diagnostics.notes]


def _generation_config(config: dict[str, object]) -> dict[str, object]:
    """Return the ``generation`` section as a typed dict (empty if missing/invalid)."""

    raw = config.get("generation")
    if isinstance(raw, dict):
        return cast(dict[str, object], raw)
    return {}


def _render_dirty_modules(
    dirty_modules: list[ParsedModule],
    repo_root: Path,
    config: dict[str, object],
    summaries: dict[str, str],
) -> tuple[list[Path], list[Path]]:
    """Render per-file module/symbol docs for *dirty_modules* in one pass."""

    generation = _generation_config(config)
    output_dir = repo_root / str(generation.get("output_dir", ".repo_wiki/generated"))
    commit = repo_commit(repo_root)
    module_docs: list[Path] = []
    symbol_docs: list[Path] = []
    if generation.get("generate_module_docs", True):
        for parsed in dirty_modules:
            module_docs.append(
                write_module_doc(parsed, output_dir, commit, repo_root.name, repo_root)
            )
    if generation.get("generate_symbol_docs", True):
        for parsed in dirty_modules:
            for symbol in parsed.symbols:
                symbol_docs.append(
                    write_symbol_doc(
                        symbol,
                        output_dir,
                        commit,
                        repo_root.name,
                        summaries.get(symbol.symbol_id),
                        repo_root,
                    )
                )
    return module_docs, symbol_docs


def _update_manifest_entry(
    manifest: Manifest,
    parsed: ParsedModule,
    config: dict[str, object],
    repo_root: Path,
) -> None:
    output_dir = str(config["generation"]["output_dir"])  # type: ignore[index]
    manifest.files[parsed.source_file.path] = ManifestFile(
        language=parsed.source_file.language,
        hash=parsed.source_file.content_hash,
        module_doc=f"{output_dir}/modules/{safe_doc_name(parsed.module)}.md",
        symbols={
            symbol.symbol_id: {
                "kind": symbol.kind,
                "hash": sha256_text(read_source(symbol.span, repo_root)),
                "doc": f"{output_dir}/symbols/{safe_doc_name(symbol.symbol_id)}.md",
                "start_line": symbol.start_line,
                "end_line": symbol.end_line,
            }
            for symbol in parsed.symbols
        },
    )


def build_repo(
    repo_root: Path,
    *,
    changed_only: bool = False,
    force: bool = False,
    no_summaries: bool = False,
    no_index: bool = False,
    summary_symbol: str | None = None,
    dry_run_reconcile: bool = False,
) -> BuildSummary:
    """Build the local wiki; global artifacts are always rebuilt from the complete IR."""
    init_repo_wiki(repo_root)
    config = load_config(repo_root)
    manifest = load_manifest(repo_root)
    sources, skipped = scan_repository(repo_root, config)
    summary = BuildSummary(scanned=len(sources), skipped=len(skipped))
    diagnostics = CacheDiagnostics()

    routable: list[SourceFile] = []
    project_languages: dict[str, list[SourceFile]] = {}
    for source in sources:
        if resolve_backend_name(source.language, config) is None:
            continue
        routable.append(source)
        if isinstance(get_backend(source.language, config), ProjectExtractor):
            project_languages.setdefault(source.language, []).append(source)

    rerun_project_languages, project_state = _project_languages_to_extract(
        manifest, project_languages, config, changed_only=changed_only, force=force
    )

    backend_ids: dict[str, tuple[str, str]] = {}
    for source in routable:
        if source.language in backend_ids:
            continue
        if source.language in project_state:
            backend_ids[source.language] = (
                resolve_backend_name(source.language, config) or "unknown",
                project_state[source.language]["tool_version"],
            )
        else:
            backend_ids[source.language] = backend_identity(source.language, config)

    to_extract: list[SourceFile] = []
    cached_modules: dict[str, ParsedModule] = {}
    # Project backends are subset-sensitive: a cache miss forces a full re-extract of the language.
    project_full_rerun: set[str] = set()
    for source in routable:
        backend_name, backend_version = backend_ids[source.language]
        if source.language in project_languages:
            if source.language in rerun_project_languages:
                to_extract.append(source)
            else:
                cached = load_cache_record(
                    repo_root,
                    source=source,
                    backend=backend_name,
                    backend_version=backend_version,
                    diagnostics=diagnostics,
                )
                if cached is not None and not cached.errors:
                    cached_modules[source.path] = cached
                else:
                    project_full_rerun.add(source.language)
                    if source.language not in project_state:
                        file_hashes = [
                            s.content_hash for s in project_languages[source.language]
                        ]
                        project_state[source.language] = {
                            "set_hash": compute_set_hash(file_hashes, backend_version),
                            "tool_version": backend_version,
                        }
            continue

        previous = manifest.files.get(source.path)
        unchanged = previous is not None and previous.hash == source.content_hash
        if changed_only and unchanged and not force:
            cached = load_cache_record(
                repo_root,
                source=source,
                backend=backend_name,
                backend_version=backend_version,
                diagnostics=diagnostics,
            )
            if cached is not None and not cached.errors:
                cached_modules[source.path] = cached
                continue
            to_extract.append(source)
            continue
        to_extract.append(source)

    if project_full_rerun:
        to_extract_paths = {source.path for source in to_extract}
        for language in sorted(project_full_rerun):
            for source in project_languages[language]:
                cached_modules.pop(source.path, None)
                if source.path not in to_extract_paths:
                    to_extract.append(source)
                    to_extract_paths.add(source.path)
            diagnostics.notes.append(
                f"ir_cache: project backend partial cache miss for {language}; "
                "re-extracting full language file set"
            )

    result = extract_files(to_extract, config)
    summary.backend_notes = list(result.notes)
    scanner_by_path = {source.path: source for source in routable}

    # Keep parse failures separate: a failing file never overwrites its prior valid outputs.
    dirty_success: list[ParsedModule] = []
    dirty_failed_paths: set[str] = set()
    for source in to_extract:
        parsed = result.parsed_modules.get(source.path)
        if parsed is None:
            dirty_failed_paths.add(source.path)
            continue
        summary.errors.extend(parsed.errors)
        if parsed.errors:
            dirty_failed_paths.add(source.path)
            continue
        canonical = scanner_by_path.get(source.path, source)
        parsed.source_file = canonical
        dirty_success.append(parsed)

    summary.parsed = len(dirty_success)

    for language, fresh in project_state.items():
        if language in rerun_project_languages or any(
            p.source_file.language == language for p in dirty_success
        ):
            set_language_state(
                manifest,
                language,
                set_hash=fresh["set_hash"],
                tool_version=fresh["tool_version"],
            )

    complete_by_path: dict[str, ParsedModule] = dict(cached_modules)
    for parsed in dirty_success:
        complete_by_path[parsed.source_file.path] = parsed
    for path in sorted(dirty_failed_paths):
        if path in complete_by_path:
            continue
        source = scanner_by_path.get(path)
        if source is None:
            continue
        backend_name, backend_version = backend_ids[source.language]
        prior = load_prior_cache_module(
            repo_root,
            source=source,
            backend=backend_name,
            backend_version=backend_version,
            diagnostics=diagnostics,
        )
        if prior is not None:
            complete_by_path[path] = prior
            diagnostics.notes.append(
                f"ir_cache: retained prior IR for map/graph after parse failure: {path}"
            )
    complete_modules = [
        complete_by_path[source.path]
        for source in routable
        if source.path in complete_by_path
    ]

    for parsed in dirty_success:
        backend_name, backend_version = backend_ids[parsed.source_file.language]
        write_cache_record(
            repo_root,
            source=parsed.source_file,
            backend=backend_name,
            backend_version=backend_version,
            parsed=parsed,
            diagnostics=diagnostics,
        )

    generation = _generation_config(config)
    output_dir = repo_root / str(generation.get("output_dir", ".repo_wiki/generated"))
    commit = repo_commit(repo_root)

    # Frontmatter records the commit: a new commit refreshes all valid cached modules.
    previous_commit = str(manifest.repo.get("last_commit", ""))
    modules_to_render = dirty_success
    if changed_only and previous_commit != commit:
        modules_to_render = [
            parsed
            for parsed in complete_modules
            if parsed.source_file.path not in dirty_failed_paths
        ]
    summaries_enabled = bool(config["summaries"]["enabled"])  # type: ignore[index]
    prepared_summaries = prepare_summaries(
        modules_to_render,
        repo_root,
        config,
        generate_missing=not no_summaries and summaries_enabled,
        write_summary_docs=not no_summaries and summaries_enabled,
        symbol_id=summary_symbol,
    )
    module_docs, symbol_docs = _render_dirty_modules(
        modules_to_render,
        repo_root,
        config,
        prepared_summaries.by_symbol_id,
    )
    summary.generated_module_docs = len(module_docs)
    summary.generated_symbol_docs = len(symbol_docs)
    summary.generated_summaries = prepared_summaries.generated

    if complete_modules and generation.get("generate_repo_map", True):
        write_repo_map(complete_modules, output_dir, commit, repo_root.name, repo_root)
    if complete_modules:
        graph = build_symbol_graph(complete_modules)
        write_symbol_graph(graph, output_dir / "symbol_graph.json")

    current_by_path = {source.path: source for source in routable}
    modules_for_prune = {
        path: module
        for path, module in complete_by_path.items()
        if path not in dirty_failed_paths
    }
    # Plan BEFORE updating manifest entries so removed-symbol detection sees the previous symbols.
    generation_output = str(generation.get("output_dir", ".repo_wiki/generated"))
    plan = plan_reconciliation(
        manifest,
        current_by_path,
        complete_modules=modules_for_prune,
        repo_root=repo_root,
        output_dir=generation_output,
    )

    for parsed in dirty_success:
        _update_manifest_entry(manifest, parsed, config, repo_root)

    if dry_run_reconcile:
        summary.backend_notes = [
            *summary.backend_notes,
            f"reconciliation dry-run: {json.dumps(plan.to_dict(), sort_keys=True)}",
        ]
    else:
        execute_reconciliation(
            repo_root, manifest, plan, dry_run=False, diagnostics=diagnostics
        )
        live_symbol_ids = {
            symbol_id
            for entry in manifest.files.values()
            for symbol_id in entry.symbols
        }
        try:
            prune_summary_cache(repo_root, live_symbol_ids)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ) as exc:
            _logger.warning("summary cache prune failed: %s", exc)

    # Index after reconciliation, so pages of deleted sources are already gone.
    index_summary = None if no_index else update_index(repo_root, force=force)

    manifest.repo.update(
        {
            "name": repo_root.name,
            "last_commit": commit,
            "index_status": "skipped" if no_index else "indexed",
            "indexed": 0 if index_summary is None else index_summary.indexed,
            "index_deleted": 0 if index_summary is None else index_summary.deleted,
        }
    )
    _apply_cache_diagnostics(summary, diagnostics)
    manifest.repo[BACKEND_NOTES_KEY] = summary.backend_notes
    save_manifest(repo_root, manifest)
    write_errors(repo_root, summary.errors)
    return summary
