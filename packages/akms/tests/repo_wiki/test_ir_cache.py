"""Parsed-IR cache: hits and misses, corruption, invalidation and parity with full parsing."""

from __future__ import annotations

import json
from pathlib import Path

from akms.repo_wiki.config import init_repo_wiki
from akms.repo_wiki.extract.python_ast import parse_python_file
from akms.repo_wiki.hashing import sha256_text
from akms.repo_wiki.ir_cache import (
    CACHE_SCHEMA_VERSION,
    CacheDiagnostics,
    cache_path_for,
    load_cache_record,
    write_cache_record,
)
from akms.repo_wiki.manifest import build_repo
from akms.repo_wiki.models import SourceFile


def _write_python(repo: Path, rel: str, body: str) -> SourceFile:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    text = path.read_text(encoding="utf-8")
    return SourceFile(
        path=rel,
        abs_path=str(path.resolve()),
        language="python",
        size_bytes=path.stat().st_size,
        content_hash=sha256_text(text),
    )


def _tiny_repo(tmp_path: Path) -> Path:
    init_repo_wiki(tmp_path)
    _write_python(
        tmp_path,
        "pkg/a.py",
        '"""A."""\n\ndef foo() -> int:\n    return 1\n',
    )
    _write_python(
        tmp_path,
        "pkg/b.py",
        '"""B."""\nfrom pkg.a import foo\n\ndef bar() -> int:\n    return foo()\n',
    )
    return tmp_path


def test_cache_hit_and_miss(tmp_path: Path) -> None:
    repo = _tiny_repo(tmp_path)
    source = _write_python(
        repo, "pkg/a.py", '"""A."""\n\ndef foo() -> int:\n    return 1\n'
    )
    parsed = parse_python_file(source)
    diagnostics = CacheDiagnostics()
    write_cache_record(
        repo,
        source=source,
        backend="ast",
        backend_version="stdlib",
        parsed=parsed,
        diagnostics=diagnostics,
    )
    assert diagnostics.writes == 1

    hit = load_cache_record(
        repo,
        source=source,
        backend="ast",
        backend_version="stdlib",
        diagnostics=diagnostics,
    )
    assert hit is not None
    assert hit.module == parsed.module
    assert [s.symbol_id for s in hit.symbols] == [s.symbol_id for s in parsed.symbols]
    assert diagnostics.hits == 1

    other = _write_python(repo, "pkg/c.py", "def z():\n    return 0\n")
    miss_diag = CacheDiagnostics()
    assert (
        load_cache_record(
            repo,
            source=other,
            backend="ast",
            backend_version="stdlib",
            diagnostics=miss_diag,
        )
        is None
    )
    assert miss_diag.misses == 1


def test_corrupt_cache_isolation_and_reparse(tmp_path: Path) -> None:
    repo = _tiny_repo(tmp_path)
    build_repo(repo, no_index=True, no_summaries=True)
    source = SourceFile(
        path="pkg/a.py",
        abs_path=str((repo / "pkg" / "a.py").resolve()),
        language="python",
        size_bytes=(repo / "pkg" / "a.py").stat().st_size,
        content_hash=sha256_text((repo / "pkg" / "a.py").read_text(encoding="utf-8")),
    )
    path = cache_path_for(repo, source.path)
    assert path.is_file()
    path.write_text("{not-json", encoding="utf-8")

    diagnostics = CacheDiagnostics()
    assert (
        load_cache_record(
            repo,
            source=source,
            backend="ast",
            backend_version="stdlib",
            diagnostics=diagnostics,
        )
        is None
    )
    assert diagnostics.corruptions == 1
    assert path.with_suffix(path.suffix + ".corrupt").is_file()
    # Rebuild re-parses and rewrites a valid cache entry.
    summary = build_repo(repo, changed_only=True, no_index=True, no_summaries=True)
    assert (
        summary.cache_corruptions >= 1
        or summary.cache_misses >= 1
        or summary.cache_writes >= 1
    )
    reloaded = load_cache_record(
        repo, source=source, backend="ast", backend_version="stdlib"
    )
    assert reloaded is not None
    assert reloaded.symbols


def test_backend_and_backend_version_invalidation(tmp_path: Path) -> None:
    repo = _tiny_repo(tmp_path)
    source = _write_python(repo, "pkg/a.py", "def foo():\n    return 1\n")
    parsed = parse_python_file(source)
    write_cache_record(
        repo, source=source, backend="ast", backend_version="stdlib", parsed=parsed
    )
    diagnostics = CacheDiagnostics()
    assert (
        load_cache_record(
            repo,
            source=source,
            backend="treesitter",
            backend_version="stdlib",
            diagnostics=diagnostics,
        )
        is None
    )
    assert diagnostics.invalidations == 1

    diagnostics2 = CacheDiagnostics()
    assert (
        load_cache_record(
            repo,
            source=source,
            backend="ast",
            backend_version="2.0",
            diagnostics=diagnostics2,
        )
        is None
    )
    assert diagnostics2.invalidations == 1


def test_cache_schema_invalidation(tmp_path: Path) -> None:
    repo = _tiny_repo(tmp_path)
    source = _write_python(repo, "pkg/a.py", "def foo():\n    return 1\n")
    parsed = parse_python_file(source)
    path = write_cache_record(
        repo, source=source, backend="ast", backend_version="stdlib", parsed=parsed
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    data["cache_schema_version"] = CACHE_SCHEMA_VERSION + 99
    path.write_text(json.dumps(data), encoding="utf-8")

    diagnostics = CacheDiagnostics()
    assert (
        load_cache_record(
            repo,
            source=source,
            backend="ast",
            backend_version="stdlib",
            diagnostics=diagnostics,
        )
        is None
    )
    assert diagnostics.invalidations == 1


def test_full_parse_versus_cache_reconstruction_parity(tmp_path: Path) -> None:
    repo = _tiny_repo(tmp_path)
    full = build_repo(repo, no_index=True, no_summaries=True)
    assert full.parsed >= 2
    assert full.cache_writes >= 2

    generated = repo / ".repo_wiki" / "generated"
    map_full = (generated / "repo_map.md").read_bytes()
    graph_full = (generated / "symbol_graph.json").read_bytes()

    # Touch nothing; changed-only must reconstruct from cache and match.
    incremental = build_repo(repo, changed_only=True, no_index=True, no_summaries=True)
    assert incremental.cache_hits >= 2
    assert (generated / "repo_map.md").read_bytes() == map_full
    assert (generated / "symbol_graph.json").read_bytes() == graph_full


def test_remove_cache_record_prunes_empty_parents(tmp_path: Path) -> None:
    from akms.repo_wiki.ir_cache import cache_path_for, cache_root, remove_cache_record

    repo = _tiny_repo(tmp_path)
    source = _write_python(repo, "deep/nested/mod.py", "def z():\n    return 0\n")
    parsed = parse_python_file(source)
    write_cache_record(
        repo, source=source, backend="ast", backend_version="stdlib", parsed=parsed
    )
    path = cache_path_for(repo, source.path)
    assert path.is_file()
    assert (cache_root(repo) / "deep" / "nested").is_dir()

    assert remove_cache_record(repo, source.path) is True
    assert not path.exists()
    assert not (cache_root(repo) / "deep").exists()
    assert cache_root(repo).is_dir()  # root itself must remain


def test_legacy_flat_cache_migrates_to_nested_on_load(tmp_path: Path) -> None:
    from akms.repo_wiki.ir_cache import (
        cache_path_for,
        legacy_flat_cache_path,
        load_cache_record,
        write_cache_record,
    )

    repo = _tiny_repo(tmp_path)
    source = _write_python(repo, "pkg/a.py", "def foo():\n    return 1\n")
    parsed = parse_python_file(source)
    # Simulate a pre-migration flat entry only.
    nested = cache_path_for(repo, source.path)
    flat = legacy_flat_cache_path(repo, source.path)
    write_cache_record(
        repo, source=source, backend="ast", backend_version="stdlib", parsed=parsed
    )
    # Move nested → flat and delete nested.
    flat.parent.mkdir(parents=True, exist_ok=True)
    flat.write_bytes(nested.read_bytes())
    nested.unlink()
    assert flat.is_file()
    assert not nested.exists()

    diagnostics = CacheDiagnostics()
    hit = load_cache_record(
        repo,
        source=source,
        backend="ast",
        backend_version="stdlib",
        diagnostics=diagnostics,
    )
    assert hit is not None
    assert hit.module == parsed.module
    assert nested.is_file()
    assert not flat.exists()
    assert diagnostics.hits == 1
    assert any("migrated legacy flat cache" in n for n in diagnostics.notes)


def test_cache_paths_are_collision_free_for_similar_names(tmp_path: Path) -> None:
    """Distinct source paths must never share an IR-cache file."""
    from akms.repo_wiki.ir_cache import cache_path_for

    repo = tmp_path
    spaced = "pkg/weird name.py"
    underscored = "pkg/weird_name.py"
    nested = "a/b.py"
    flat_encoded = "a__b.py"
    assert cache_path_for(repo, spaced) != cache_path_for(repo, underscored)
    assert cache_path_for(repo, nested) != cache_path_for(repo, flat_encoded)

    init_repo_wiki(repo)
    _write_python(repo, spaced, "def spaced():\n    return 1\n")
    _write_python(repo, underscored, "def underscored():\n    return 2\n")
    build_repo(repo, no_index=True, no_summaries=True)
    assert cache_path_for(repo, spaced).is_file()
    assert cache_path_for(repo, underscored).is_file()

    first = build_repo(repo, changed_only=True, no_index=True, no_summaries=True)
    second = build_repo(repo, changed_only=True, no_index=True, no_summaries=True)
    # Both files must be stable cache hits — no thrashing invalidations.
    assert first.cache_hits >= 2
    assert second.cache_hits >= 2
    assert first.cache_invalidations == 0
    assert second.cache_invalidations == 0
    assert first.cache_writes == 0
    assert second.cache_writes == 0
