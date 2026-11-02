"""End-to-end build, index and query over the multi-language fixture."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from akms.repo_wiki.cli import main
from akms.repo_wiki.config import config_path
from akms.repo_wiki.index import search_index
from .test_build_render_graph_summary import copy_fixture

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "multilang_repo"

_CONFIG_YAML = """\
languages:
  python:
    enabled: true
  rust:
    enabled: true
  cpp:
    enabled: true
    backend: doxygen
  julia:
    enabled: true
"""


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _language_of(symbol_id: str) -> str:
    return symbol_id.split(":", 1)[0]


def _build(tmp_path: Path) -> Path:
    copy_fixture(FIXTURE, tmp_path)
    assert main(["--repo-root", str(tmp_path), "init"]) == 0
    config_path(tmp_path).write_text(_CONFIG_YAML, encoding="utf-8")
    assert main(["--repo-root", str(tmp_path), "build"]) == 0
    return tmp_path / ".repo_wiki" / "generated"


def _graph(generated: Path) -> dict:
    return json.loads((generated / "symbol_graph.json").read_text())


class TestE2EMultilang:
    """End-to-end multi-language build/index/query."""

    @pytest.mark.integration
    def test_enabled_languages_produce_symbol_nodes(self, tmp_path):
        """Each enabled+available language contributes symbols to the graph."""
        generated = _build(tmp_path)
        graph = _graph(generated)
        languages = {_language_of(sid) for sid in graph["nodes"]}

        assert "python" in languages
        assert "cpp" in languages  # doxygen (external) or tree-sitter fallback
        if _has("tree_sitter_rust"):
            assert "rust" in languages
        if _has("tree_sitter_julia"):
            assert "julia" in languages

    @pytest.mark.integration
    def test_symbol_docs_written_per_language(self, tmp_path):
        """Symbol docs are generated on disk for the produced symbols."""
        generated = _build(tmp_path)
        symbol_docs = list((generated / "symbols").rglob("*.md"))
        assert symbol_docs, "no symbol docs generated"
        assert _graph(generated)["nodes"], "empty symbol graph"

    @pytest.mark.integration
    def test_edges_are_intra_language_only(self, tmp_path):
        """Name-resolved edges never link two different languages."""
        generated = _build(tmp_path)
        name_resolved = {"calls", "inherits"}
        cross = [
            e
            for e in _graph(generated)["edges"]
            if e["type"] in name_resolved
            and _language_of(str(e["source"])) != _language_of(str(e["target"]))
        ]
        assert not cross, f"cross-language calls/inherits edges present: {cross}"

    @pytest.mark.integration
    def test_cross_language_query_returns_two_languages(self, tmp_path):
        """A query naming a symbol present in two languages returns both."""
        _build(tmp_path)
        results = search_index(tmp_path, "helper")
        langs = {_language_of(r.symbol_id) for r in results if r.symbol_id}
        if _has("tree_sitter_rust"):
            assert {"python", "rust"} <= langs, f"got {langs}"
        else:
            assert "python" in langs

    @pytest.mark.integration
    def test_overlay_attaches_and_is_indexed(self, tmp_path):
        """A human-authored overlay is discoverable through the index."""
        _build(tmp_path)
        overlay = tmp_path / ".repo_wiki" / "overlays" / "note.md"
        overlay.write_text(
            "# Note\n\nThis overlay mentions zubzubzub as a unique marker.\n",
            encoding="utf-8",
        )
        assert main(["--repo-root", str(tmp_path), "index"]) == 0
        results = search_index(tmp_path, "zubzubzub")
        # The marker is unique to the overlay, so any hit proves the overlay was
        # indexed; require the matched doc to be the overlay note specifically.
        assert results, "overlay marker 'zubzubzub' was not indexed"
        assert any(
            "note" in r.doc_id.lower() or "zubzubzub" in (r.title or "").lower()
            for r in results
        ), f"overlay note not among results: {[r.doc_id for r in results]}"
