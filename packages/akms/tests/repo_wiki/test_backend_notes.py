"""Backend notes: recorded on build, persisted in the manifest and surfaced by stats and build JSON."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import akms.repo_wiki.manifest as manifest_mod
from akms.repo_wiki.cli import main
from akms.repo_wiki.extract.registry import ExtractionResult
from akms.repo_wiki.manifest import (
    BACKEND_NOTES_KEY,
    LANGUAGES_KEY,
    build_repo,
    get_backend_notes,
    get_language_state,
    load_manifest,
    save_manifest,
)
from akms.repo_wiki.models import BuildSummary, Manifest

_TINY_REPO = Path(__file__).resolve().parent / "fixtures" / "tiny_repo"


def _make_repo(tmp_path: Path) -> Path:
    """Mirror the tiny_repo Python tree into ``tmp_path`` with a minimal config."""
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    shutil.copy(_TINY_REPO / "pkg" / "__init__.py", pkg_dir / "__init__.py")
    shutil.copy(_TINY_REPO / "pkg" / "core.py", pkg_dir / "core.py")
    (tmp_path / "repo2md.yaml").write_text(
        "scanner:\n  include: ['pkg']\n  exclude: []\n"
        "generation:\n  output_dir: .repo_wiki/generated\n"
        "summaries:\n  enabled: false\n",
        encoding="utf-8",
    )
    return tmp_path


def test_build_summary_has_backend_notes_field():
    """BuildSummary carries a backend_notes: list[str] field defaulting to empty."""
    summary = BuildSummary()
    assert hasattr(summary, "backend_notes")
    assert summary.backend_notes == []
    assert isinstance(summary.backend_notes, list)

    summary2 = BuildSummary(
        backend_notes=["python: using ast backend (treesitter unavailable)"]
    )
    assert summary2.backend_notes == [
        "python: using ast backend (treesitter unavailable)"
    ]


def test_stats_prints_backend_notes(tmp_path, capsys):
    """The stats command renders backend_notes in human-readable form."""
    assert main(["--repo-root", str(tmp_path), "init"]) == 0
    capsys.readouterr()  # discard init output

    manifest = load_manifest(tmp_path)
    manifest.repo[BACKEND_NOTES_KEY] = [
        "python: ast fallback (treesitter unavailable)",
        "cpp: no backend available",
    ]
    save_manifest(tmp_path, manifest)

    ret = main(["--repo-root", str(tmp_path), "stats"])
    out = capsys.readouterr().out

    assert ret == 0
    assert "Backend notes:" in out
    assert "python: ast fallback (treesitter unavailable)" in out
    assert "cpp: no backend available" in out


def test_build_json_output_contains_backend_notes():
    """Build --json output includes a backend_notes key."""
    notes = ["python: using ast backend", "rust: treesitter fallback"]
    summary = BuildSummary(backend_notes=notes)
    d = summary.to_dict()

    assert "backend_notes" in d
    assert d["backend_notes"] == notes

    payload = json.loads(json.dumps(d))
    assert payload["backend_notes"] == notes


def test_stats_no_notes_section_when_empty(tmp_path, capsys):
    """Stats prints no 'Backend notes:' header when no notes are stored."""
    assert main(["--repo-root", str(tmp_path), "init"]) == 0
    capsys.readouterr()

    ret = main(["--repo-root", str(tmp_path), "stats"])
    out = capsys.readouterr().out

    assert ret == 0
    assert "Initialized: True" in out
    assert "Tracked files:" in out
    assert "Backend notes:" not in out


def test_get_backend_notes_accessor():
    """get_backend_notes() returns the notes list from manifest.repo."""
    manifest = Manifest(repo={BACKEND_NOTES_KEY: ["note-a", "note-b"]}, files={})
    notes = get_backend_notes(manifest)
    assert notes == ["note-a", "note-b"]

    # Returns empty list when key absent.
    manifest_empty = Manifest(repo={}, files={})
    assert get_backend_notes(manifest_empty) == []

    # Returns empty list when value is not a list.
    manifest_bad = Manifest(repo={BACKEND_NOTES_KEY: "not-a-list"}, files={})
    assert get_backend_notes(manifest_bad) == []


def test_backend_notes_and_languages_survive_build_cycle(tmp_path):
    """A rebuild keeps the persisted languages and backend-notes state."""
    _make_repo(tmp_path)

    # A Python-only repo produces no fallback notes, so backend_notes is an
    # empty list — but it must still be persisted, and any pre-existing
    # project-language state must survive the repo-key update.
    build_repo(tmp_path, no_summaries=True, no_index=True)
    manifest = load_manifest(tmp_path)

    assert BACKEND_NOTES_KEY in manifest.repo, "backend_notes key must be persisted."
    assert get_backend_notes(manifest) == []

    # Seed a project-language record, persist it, then run another build and
    # confirm the rebuild does not erase it.
    from akms.repo_wiki.manifest import (
        compute_set_hash,
        save_manifest,
        set_language_state,
    )

    set_language_state(
        manifest,
        "cpp",
        set_hash=compute_set_hash(["sha256:a"], "v1"),
        tool_version="v1",
    )
    save_manifest(tmp_path, manifest)

    build_repo(tmp_path, no_summaries=True, no_index=True)
    reloaded = load_manifest(tmp_path)

    assert LANGUAGES_KEY in reloaded.repo, "languages key must survive a build cycle."
    assert "cpp" in get_language_state(reloaded), (
        "Pre-existing project-language state must survive build_repo."
    )
    assert BACKEND_NOTES_KEY in reloaded.repo


def test_backend_notes_surface_when_registry_reports_them(tmp_path):
    """Registry notes flow onto summary.backend_notes and into the manifest."""
    _make_repo(tmp_path)

    real_extract = manifest_mod.extract_files

    def with_note(sources, config):
        res = real_extract(sources, config)
        return ExtractionResult(
            parsed_modules=res.parsed_modules,
            notes=[*res.notes, "demo: synthetic fallback note"],
            handled_languages=res.handled_languages,
        )

    with patch.object(manifest_mod, "extract_files", side_effect=with_note):
        summary = build_repo(tmp_path, no_summaries=True, no_index=True)

    assert "demo: synthetic fallback note" in summary.backend_notes
    manifest = load_manifest(tmp_path)
    assert "demo: synthetic fallback note" in get_backend_notes(manifest)
