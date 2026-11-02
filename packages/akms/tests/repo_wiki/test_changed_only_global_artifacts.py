"""Global artifacts come from the complete IR, not just the changed files."""

from __future__ import annotations

import json
from pathlib import Path

from akms.repo_wiki.config import init_repo_wiki
from akms.repo_wiki.manifest import build_repo


def _py(repo: Path, rel: str, body: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _cross_file_repo(tmp_path: Path) -> Path:
    init_repo_wiki(tmp_path)
    _py(
        tmp_path,
        "pkg/lib.py",
        '"""lib."""\n\ndef helper() -> int:\n    return 7\n',
    )
    _py(
        tmp_path,
        "pkg/app.py",
        '"""app."""\nfrom pkg.lib import helper\n\ndef run() -> int:\n    return helper()\n',
    )
    return tmp_path


def test_full_versus_incremental_byte_comparison(tmp_path: Path) -> None:
    repo = _cross_file_repo(tmp_path)
    build_repo(repo, no_index=True, no_summaries=True)
    generated = repo / ".repo_wiki" / "generated"
    map_before = (generated / "repo_map.md").read_bytes()
    graph_before = (generated / "symbol_graph.json").read_bytes()

    # Edit only app.py (add a new symbol so globals actually change); lib stays cached.
    _py(
        tmp_path,
        "pkg/app.py",
        '"""app."""\nfrom pkg.lib import helper\n\ndef run() -> int:\n    return helper()\n\ndef extra() -> int:\n    return 0\n',
    )
    build_repo(repo, changed_only=True, no_index=True, no_summaries=True)
    map_inc = (generated / "repo_map.md").read_bytes()
    graph_inc = (generated / "symbol_graph.json").read_bytes()
    assert map_inc != map_before or graph_inc != graph_before
    assert b"extra" in graph_inc

    # Force a full rebuild of the same tree; globals must match incremental.
    build_repo(repo, force=True, no_index=True, no_summaries=True)
    assert (generated / "repo_map.md").read_bytes() == map_inc
    assert (generated / "symbol_graph.json").read_bytes() == graph_inc


def test_cross_file_edges_survive_unchanged_file_caching(tmp_path: Path) -> None:
    repo = _cross_file_repo(tmp_path)
    build_repo(repo, no_index=True, no_summaries=True)

    # Change only the caller; callee file is served from IR cache.
    _py(
        tmp_path,
        "pkg/app.py",
        '"""app v2."""\nfrom pkg.lib import helper\n\ndef run() -> int:\n    return helper()\n',
    )
    summary = build_repo(repo, changed_only=True, no_index=True, no_summaries=True)
    assert summary.cache_hits >= 1

    graph = json.loads(
        (repo / ".repo_wiki" / "generated" / "symbol_graph.json").read_text(
            encoding="utf-8"
        )
    )
    assert "python:pkg/lib.py::helper" in graph["nodes"]
    assert "python:pkg/app.py::run" in graph["nodes"]
    assert any(
        edge.get("type") == "calls"
        and edge.get("source") == "python:pkg/app.py::run"
        and edge.get("target") == "python:pkg/lib.py::helper"
        for edge in graph["edges"]
    )


def test_repeated_noop_changed_only_is_byte_stable_and_duplicate_free(
    tmp_path: Path,
) -> None:
    repo = _cross_file_repo(tmp_path)
    build_repo(repo, no_index=True, no_summaries=True)
    generated = repo / ".repo_wiki" / "generated"
    map_bytes = (generated / "repo_map.md").read_bytes()
    graph_bytes = (generated / "symbol_graph.json").read_bytes()

    for _ in range(3):
        build_repo(repo, changed_only=True, no_index=True, no_summaries=True)
        assert (generated / "repo_map.md").read_bytes() == map_bytes
        assert (generated / "symbol_graph.json").read_bytes() == graph_bytes

    graph = json.loads(graph_bytes.decode("utf-8"))
    node_ids = list(graph["nodes"])
    assert len(node_ids) == len(set(node_ids))
    edge_keys = [
        (e.get("source"), e.get("target"), e.get("type"), e.get("dst_name"))
        for e in graph["edges"]
    ]
    assert len(edge_keys) == len(set(edge_keys))
