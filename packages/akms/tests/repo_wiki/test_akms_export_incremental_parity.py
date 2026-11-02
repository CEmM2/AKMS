"""Full and incremental AKMS exports (plus wiki global artifacts) produce identical output."""

from __future__ import annotations

import shutil
from pathlib import Path

from akms.repo_wiki.config import init_repo_wiki
from akms.repo_wiki.export import export_akms
from akms.repo_wiki.manifest import build_repo


FIXED_TS = "2026-05-24T12:00:00+00:00"
PHASE = 1


def _py(repo: Path, rel: str, body: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _seed(repo: Path) -> None:
    init_repo_wiki(repo)
    _py(repo, "src/alpha.py", "def alpha():\n    return 1\n")
    _py(
        repo,
        "src/beta.py",
        "from src.alpha import alpha\n\ndef beta():\n    return alpha()\n",
    )


def _mirror_bytes(root: Path) -> dict[str, bytes]:
    mirror = root / "knowledge" / "code-mirror"
    if not mirror.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(mirror.rglob("*.md"))
    }


def _wiki_global_bytes(repo: Path) -> dict[str, bytes]:
    generated = repo / ".repo_wiki" / "generated"
    out: dict[str, bytes] = {}
    for name in ("repo_map.md", "symbol_graph.json"):
        path = generated / name
        if path.is_file():
            out[name] = path.read_bytes()
    return out


def test_incremental_edit_sequence_parity(tmp_path: Path) -> None:
    """Add → modify → rename → delete → syntax error → recovery vs clean full export."""

    work = tmp_path / "work"
    work.mkdir()
    _seed(work)
    out = work / "akms_out"

    # Initial full export + wiki build.
    build_repo(work, no_index=True, no_summaries=True)
    export_akms(
        repo_root=work,
        output_root=out,
        phase=PHASE,
        generated_at=FIXED_TS,
        changed_only=False,
        prune=True,
    )

    # 1. Add
    _py(work, "src/gamma.py", "def gamma():\n    return 3\n")
    build_repo(work, changed_only=True, no_index=True, no_summaries=True)
    export_akms(
        repo_root=work,
        output_root=out,
        phase=PHASE,
        generated_at=FIXED_TS,
        changed_only=True,
        prune=True,
    )

    # 2. Modify
    _py(
        work,
        "src/beta.py",
        "from src.alpha import alpha\n\ndef beta():\n    return alpha() + 1\n",
    )
    build_repo(work, changed_only=True, no_index=True, no_summaries=True)
    export_akms(
        repo_root=work,
        output_root=out,
        phase=PHASE,
        generated_at=FIXED_TS,
        changed_only=True,
        prune=True,
    )

    # 3. Rename gamma → delta
    old = work / "src" / "gamma.py"
    new = work / "src" / "delta.py"
    new.write_bytes(old.read_bytes())
    old.unlink()
    build_repo(work, changed_only=True, no_index=True, no_summaries=True)
    export_akms(
        repo_root=work,
        output_root=out,
        phase=PHASE,
        generated_at=FIXED_TS,
        changed_only=True,
        prune=True,
    )

    # 4. Delete alpha (and leave beta broken call — still valid syntax)
    (work / "src" / "alpha.py").unlink()
    _py(work, "src/beta.py", "def beta():\n    return 0\n")
    build_repo(work, changed_only=True, no_index=True, no_summaries=True)
    export_akms(
        repo_root=work,
        output_root=out,
        phase=PHASE,
        generated_at=FIXED_TS,
        changed_only=True,
        prune=True,
    )

    # 5. Syntax error on delta — must not wipe prior valid mirror for other files
    _py(work, "src/delta.py", "def (\n")
    build_repo(work, changed_only=True, no_index=True, no_summaries=True)
    # Export may record parse errors for delta; other mirrors stay.
    export_akms(
        repo_root=work,
        output_root=out,
        phase=PHASE,
        generated_at=FIXED_TS,
        changed_only=True,
        prune=False,  # avoid prune while export has errors
    )

    # 6. Recovery
    _py(work, "src/delta.py", "def delta():\n    return 4\n")
    build_repo(work, changed_only=True, no_index=True, no_summaries=True)
    export_akms(
        repo_root=work,
        output_root=out,
        phase=PHASE,
        generated_at=FIXED_TS,
        changed_only=True,
        prune=True,
    )

    incremental_mirrors = _mirror_bytes(out)
    incremental_globals = _wiki_global_bytes(work)
    assert incremental_mirrors
    # Stale gamma / alpha mirrors must be gone.
    for path in incremental_mirrors:
        assert "gamma" not in path
        assert "/alpha.py" not in path and not path.endswith("alpha.py.md")

    # Clean full export of the same final tree into a fresh output root.
    fresh_out = tmp_path / "fresh_out"
    result = export_akms(
        repo_root=work,
        output_root=fresh_out,
        phase=PHASE,
        generated_at=FIXED_TS,
        changed_only=False,
        prune=True,
    )
    assert not result.errors
    full_mirrors = _mirror_bytes(fresh_out)
    assert full_mirrors == incremental_mirrors

    # Fresh full wiki rebuild in-place (same repo name) must match incremental globals.
    build_repo(work, force=True, no_index=True, no_summaries=True)
    assert _wiki_global_bytes(work) == incremental_globals


def test_parity_detects_dirty_only_global_truncation(tmp_path: Path) -> None:
    """Guardrail: if map/graph are rebuilt from only dirty modules, parity fails."""

    from akms.repo_wiki.graph import build_symbol_graph, write_symbol_graph
    from akms.repo_wiki.render_markdown import write_repo_map, repo_commit
    from akms.repo_wiki.extract.registry import extract_files
    from akms.repo_wiki.config import load_config
    from akms.repo_wiki.scanner import scan_repository

    repo = tmp_path / "repo"
    repo.mkdir()
    _seed(repo)
    build_repo(repo, no_index=True, no_summaries=True)

    # Intentionally truncate globals to a single dirty module (simulates the bug).
    _py(
        repo,
        "src/beta.py",
        "from src.alpha import alpha\n\ndef beta():\n    return 99\n",
    )
    config = load_config(repo)
    sources, _ = scan_repository(repo, config)
    dirty = [s for s in sources if s.path == "src/beta.py"]
    extraction = extract_files(dirty, config)
    only_dirty = [extraction.parsed_modules["src/beta.py"]]
    generated = repo / ".repo_wiki" / "generated"
    commit = repo_commit(repo)
    write_repo_map(only_dirty, generated, commit, repo.name, repo)
    write_symbol_graph(build_symbol_graph(only_dirty), generated / "symbol_graph.json")

    clone = tmp_path / "clone"
    shutil.copytree(repo, clone, ignore=shutil.ignore_patterns(".repo_wiki"))
    init_repo_wiki(clone)
    # Rewrite beta in clone the same way, then full build.
    _py(
        clone,
        "src/beta.py",
        "from src.alpha import alpha\n\ndef beta():\n    return 99\n",
    )
    build_repo(clone, no_index=True, no_summaries=True)

    assert _wiki_global_bytes(repo) != _wiki_global_bytes(clone)
