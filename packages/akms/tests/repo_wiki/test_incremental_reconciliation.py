"""Incremental builds reconcile deletions, renames, removed symbols, parse failures and dry runs."""

from __future__ import annotations

import json
from pathlib import Path

from akms.repo_wiki.config import init_repo_wiki
from akms.repo_wiki.hashing import sha256_text
from akms.repo_wiki.ir_cache import cache_path_for
from akms.repo_wiki.manifest import (
    build_repo,
    load_manifest,
    plan_reconciliation,
    execute_reconciliation,
)
from akms.repo_wiki.models import SourceFile


def _py(repo: Path, rel: str, body: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _init_two_files(tmp_path: Path) -> Path:
    init_repo_wiki(tmp_path)
    _py(tmp_path, "pkg/keep.py", "def keep():\n    return 1\n")
    _py(tmp_path, "pkg/gone.py", "def gone():\n    return 2\n")
    build_repo(tmp_path, no_index=True, no_summaries=True)
    return tmp_path


def test_deleted_source_reconciliation(tmp_path: Path) -> None:
    repo = _init_two_files(tmp_path)
    generated = repo / ".repo_wiki" / "generated"
    assert (generated / "modules" / "pkg.gone.md").is_file()
    (repo / "pkg" / "gone.py").unlink()

    build_repo(repo, changed_only=True, no_index=True, no_summaries=True)
    manifest = load_manifest(repo)
    assert "pkg/gone.py" not in manifest.files
    assert "pkg/keep.py" in manifest.files
    assert not (generated / "modules" / "pkg.gone.md").exists()
    assert not cache_path_for(repo, "pkg/gone.py").exists()


def test_rename_as_delete_plus_add(tmp_path: Path) -> None:
    repo = _init_two_files(tmp_path)
    old = repo / "pkg" / "gone.py"
    new = repo / "pkg" / "renamed.py"
    new.write_bytes(old.read_bytes())
    old.unlink()

    build_repo(repo, changed_only=True, no_index=True, no_summaries=True)
    manifest = load_manifest(repo)
    assert "pkg/gone.py" not in manifest.files
    assert "pkg/renamed.py" in manifest.files
    generated = repo / ".repo_wiki" / "generated"
    assert not (generated / "modules" / "pkg.gone.md").exists()
    assert (generated / "modules" / "pkg.renamed.md").is_file()


def test_removed_symbol_cleanup(tmp_path: Path) -> None:
    init_repo_wiki(tmp_path)
    _py(
        tmp_path,
        "pkg/mod.py",
        "def alpha():\n    return 1\n\ndef beta():\n    return 2\n",
    )
    build_repo(tmp_path, no_index=True, no_summaries=True)
    manifest = load_manifest(tmp_path)
    symbol_ids = list(manifest.files["pkg/mod.py"].symbols)
    assert len(symbol_ids) == 2
    beta_id = next(sid for sid in symbol_ids if sid.endswith("::beta"))
    beta_doc = Path(tmp_path) / str(
        manifest.files["pkg/mod.py"].symbols[beta_id]["doc"]
    )
    assert beta_doc.is_file()

    _py(tmp_path, "pkg/mod.py", "def alpha():\n    return 1\n")
    build_repo(tmp_path, changed_only=True, no_index=True, no_summaries=True)
    manifest = load_manifest(tmp_path)
    assert beta_id not in manifest.files["pkg/mod.py"].symbols
    assert not beta_doc.exists()


def test_parse_failure_preserves_prior_valid_outputs(tmp_path: Path) -> None:
    init_repo_wiki(tmp_path)
    _py(tmp_path, "pkg/mod.py", "def ok():\n    return 1\n")
    build_repo(tmp_path, no_index=True, no_summaries=True)
    generated = tmp_path / ".repo_wiki" / "generated"
    module_doc = generated / "modules" / "pkg.mod.md"
    assert module_doc.is_file()
    before = module_doc.read_bytes()
    manifest_before = json.loads(
        (tmp_path / ".repo_wiki" / "manifest.json").read_text()
    )

    _py(tmp_path, "pkg/mod.py", "def (\n")  # syntax error
    summary = build_repo(tmp_path, changed_only=True, no_index=True, no_summaries=True)
    assert summary.errors
    assert module_doc.read_bytes() == before
    manifest_after = json.loads((tmp_path / ".repo_wiki" / "manifest.json").read_text())
    assert (
        manifest_after["files"]["pkg/mod.py"]["symbols"]
        == manifest_before["files"]["pkg/mod.py"]["symbols"]
    )


def test_parse_failure_retains_prior_ir_in_map_and_graph(tmp_path: Path) -> None:
    """Dirty parse-fail must keep prior symbols in repo_map / symbol_graph."""
    init_repo_wiki(tmp_path)
    _py(tmp_path, "pkg/keep.py", "def keep():\n    return 1\n")
    _py(tmp_path, "pkg/mod.py", "def alpha():\n    return 1\n")
    build_repo(tmp_path, no_index=True, no_summaries=True)
    generated = tmp_path / ".repo_wiki" / "generated"
    graph_before = json.loads(
        (generated / "symbol_graph.json").read_text(encoding="utf-8")
    )
    assert "python:pkg/mod.py::alpha" in graph_before["nodes"]
    module_doc = generated / "modules" / "pkg.mod.md"
    module_bytes = module_doc.read_bytes()

    _py(tmp_path, "pkg/mod.py", "def (\n")  # syntax error on previously-good file
    summary = build_repo(tmp_path, changed_only=True, no_index=True, no_summaries=True)
    assert summary.errors
    assert summary.parsed == 0  # fresh extract successes only
    assert module_doc.read_bytes() == module_bytes

    map_after = (generated / "repo_map.md").read_text(encoding="utf-8")
    graph_after = json.loads(
        (generated / "symbol_graph.json").read_text(encoding="utf-8")
    )
    # repo_map lists modules (not individual symbol names); prior module must remain.
    assert "pkg.mod" in map_after
    assert "pkg/mod.py" in map_after
    assert "python:pkg/mod.py::alpha" in graph_after["nodes"]
    assert "python:pkg/keep.py::keep" in graph_after["nodes"]
    assert any(
        "retained prior IR for map/graph after parse failure" in note
        for note in summary.backend_notes
    )


def test_summary_docs_pruned_on_delete_and_symbol_removal(tmp_path: Path) -> None:
    """No generated document, summaries included, survives removal of its source."""

    init_repo_wiki(tmp_path)
    _py(
        tmp_path,
        "pkg/mod.py",
        "def alpha():\n    return 1\n\ndef beta():\n    return 2\n",
    )
    _py(tmp_path, "pkg/gone.py", "def gone():\n    return 3\n")
    build_repo(tmp_path, no_index=True, no_summaries=False)
    summaries = tmp_path / ".repo_wiki" / "generated" / "summaries"
    before = {p.name for p in summaries.glob("*.summary.md")}
    assert any("beta" in name for name in before)
    assert any("gone" in name for name in before)

    _py(tmp_path, "pkg/mod.py", "def alpha():\n    return 1\n")
    (tmp_path / "pkg" / "gone.py").unlink()
    build_repo(tmp_path, changed_only=True, no_index=True, no_summaries=False)
    after = {p.name for p in summaries.glob("*.summary.md")}
    assert any("alpha" in name for name in after)
    assert not any("beta" in name for name in after)
    assert not any("gone" in name for name in after)


def test_summary_json_cache_pruned_for_removed_symbols(tmp_path: Path) -> None:
    """LLM summary JSON cache must drop keys for deleted/removed symbols."""
    from akms.repo_wiki.summarize import CACHE_PATH, load_summary_cache

    init_repo_wiki(tmp_path)
    _py(
        tmp_path,
        "pkg/mod.py",
        "def alpha():\n    return 1\n\ndef beta():\n    return 2\n",
    )
    _py(tmp_path, "pkg/gone.py", "def gone():\n    return 3\n")
    build_repo(tmp_path, no_index=True, no_summaries=False)
    cache_before = load_summary_cache(tmp_path)
    assert any("beta" in key for key in cache_before)
    assert any("gone" in key for key in cache_before)

    _py(tmp_path, "pkg/mod.py", "def alpha():\n    return 1\n")
    (tmp_path / "pkg" / "gone.py").unlink()
    build_repo(tmp_path, changed_only=True, no_index=True, no_summaries=False)
    cache_after = load_summary_cache(tmp_path)
    assert any("alpha" in key for key in cache_after)
    assert not any("beta" in key for key in cache_after)
    assert not any("gone" in key for key in cache_after)
    assert (tmp_path / CACHE_PATH).is_file()


def test_dry_run_reports_without_filesystem_mutation(tmp_path: Path) -> None:
    repo = _init_two_files(tmp_path)
    (repo / "pkg" / "gone.py").unlink()
    manifest = load_manifest(repo)
    current = {
        "pkg/keep.py": SourceFile(
            path="pkg/keep.py",
            abs_path=str((repo / "pkg" / "keep.py").resolve()),
            language="python",
            size_bytes=(repo / "pkg" / "keep.py").stat().st_size,
            content_hash=sha256_text(
                (repo / "pkg" / "keep.py").read_text(encoding="utf-8")
            ),
        )
    }
    plan = plan_reconciliation(manifest, current)
    assert "pkg/gone.py" in plan.deleted_sources
    module_doc = repo / ".repo_wiki" / "generated" / "modules" / "pkg.gone.md"
    assert module_doc.is_file()

    execute_reconciliation(repo, manifest, plan, dry_run=True)
    assert module_doc.is_file()
    assert "pkg/gone.py" in load_manifest(repo).files

    summary = build_repo(
        repo,
        changed_only=True,
        no_index=True,
        no_summaries=True,
        dry_run_reconcile=True,
    )
    assert any("reconciliation dry-run" in note for note in summary.backend_notes)
    # Dry-run path through build_repo should also leave the deleted file's docs.
    assert module_doc.is_file()
