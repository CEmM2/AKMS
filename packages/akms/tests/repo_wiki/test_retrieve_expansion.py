"""Context expansion honours edge resolution and the expand_heuristic_edges flag."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from akms.repo_wiki.index import SearchResult
from akms.repo_wiki.retrieve import (
    _edge_is_allowed,
    add_reverse_symbol_neighbors,
    add_symbol_neighbors,
    expand_context,
)


def _sr(
    doc_id: str,
    symbol_id: str = "",
    path: str = "pkg/a.py",
    module: str = "python:pkg/a.py",
    doc_type: str = "symbol",
    score: float = 1.0,
) -> SearchResult:
    """Minimal SearchResult factory."""
    return SearchResult(
        doc_id=doc_id,
        doc_type=doc_type,
        path=path,
        content="",
        score=score,
        module=module,
        symbol_id=symbol_id,
        kind="function",
        start_line=1,
        end_line=5,
    )


def _make_edge(
    source: str,
    target: str,
    edge_type: str,
    resolution: str,
    dst_name: str = "",
    dst_id: str | None = None,
    dst_candidates: list[str] | None = None,
) -> dict:
    edge: dict = {
        "source": source,
        "target": target,
        "type": edge_type,
        "resolution": resolution,
        "dst_name": dst_name or target,
        "dst_id": dst_id,
    }
    if dst_candidates is not None:
        edge["dst_candidates"] = dst_candidates
    return edge


def _graph_with_edges(edges: list[dict]) -> dict:
    return {"nodes": {}, "edges": edges}


def _write_graph(tmp_path: Path, graph: dict) -> None:
    out = tmp_path / ".repo_wiki" / "generated" / "symbol_graph.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(graph), encoding="utf-8")


def _base_config(overrides: dict | None = None) -> dict:
    cfg: dict = {
        "retrieval": {
            "top_k_initial": 30,
            "top_k_reranked": 8,
            "expand_parent": True,
            "expand_children": True,
            "expand_callees": True,
            "expand_callers": True,
            "include_tests": False,
        }
    }
    if overrides:
        cfg["retrieval"].update(overrides)
    return cfg


class TestEdgeIsAllowed:
    """Direct unit tests for the _edge_is_allowed helper."""

    def test_confident_always_allowed(self):
        edge = _make_edge("A", "B", "calls", "CONFIDENT")
        assert _edge_is_allowed(edge, expand_heuristic_edges=True) is True
        assert _edge_is_allowed(edge, expand_heuristic_edges=False) is True

    def test_heuristic_allowed_when_flag_true(self):
        edge = _make_edge("A", "B", "calls", "HEURISTIC")
        assert _edge_is_allowed(edge, expand_heuristic_edges=True) is True

    def test_heuristic_blocked_when_flag_false(self):
        edge = _make_edge("A", "B", "calls", "HEURISTIC")
        assert _edge_is_allowed(edge, expand_heuristic_edges=False) is False

    def test_unresolved_always_blocked(self):
        edge = _make_edge("A", "B", "calls", "UNRESOLVED")
        assert _edge_is_allowed(edge, expand_heuristic_edges=True) is False
        assert _edge_is_allowed(edge, expand_heuristic_edges=False) is False

    def test_missing_resolution_treated_as_confident(self):
        """Legacy edges without a resolution key are treated as CONFIDENT."""
        edge = {"source": "A", "target": "B", "type": "calls"}
        assert _edge_is_allowed(edge, expand_heuristic_edges=True) is True
        assert _edge_is_allowed(edge, expand_heuristic_edges=False) is True


class TestNeighborHelpers:
    """Tests that the neighbor helpers skip/include edges by resolution."""

    def _search_side_effect(self, found_id: str):
        """Return a side_effect that yields a result for `found_id`."""

        def side_effect(repo_root, query, *, limit, filters=None):
            if filters and filters.get("symbol_id") == found_id:
                return [_sr(found_id, symbol_id=found_id)]
            return []

        return side_effect

    def test_add_symbol_neighbors_skips_unresolved(self, tmp_path):
        graph = _graph_with_edges(
            [
                _make_edge(
                    "python:pkg/a.py::caller",
                    "ghost_fn",
                    "calls",
                    "UNRESOLVED",
                    dst_name="ghost_fn",
                    dst_id=None,
                ),
            ]
        )
        blocks: list = []
        seen: set = set()
        with patch("akms.repo_wiki.retrieve.search_index", return_value=[]):
            add_symbol_neighbors(
                tmp_path,
                blocks,
                seen,
                graph,
                "python:pkg/a.py::caller",
                "calls",
                "callee",
                expand_heuristic_edges=True,
            )
        assert blocks == []

    def test_add_symbol_neighbors_includes_confident(self, tmp_path):
        callee_id = "python:pkg/b.py::helper"
        graph = _graph_with_edges(
            [
                _make_edge(
                    "python:pkg/a.py::caller",
                    callee_id,
                    "calls",
                    "CONFIDENT",
                    dst_name="helper",
                    dst_id=callee_id,
                ),
            ]
        )
        blocks: list = []
        seen: set = set()
        with patch(
            "akms.repo_wiki.retrieve.search_index",
            side_effect=self._search_side_effect(callee_id),
        ):
            add_symbol_neighbors(
                tmp_path,
                blocks,
                seen,
                graph,
                "python:pkg/a.py::caller",
                "calls",
                "callee",
                expand_heuristic_edges=True,
            )
        assert len(blocks) == 1
        assert blocks[0].result.symbol_id == callee_id
        assert blocks[0].role == "callee"

    def test_add_symbol_neighbors_heuristic_included_when_flag_true(self, tmp_path):
        callee_id = "python:pkg/a.py::C.greet"
        graph = _graph_with_edges(
            [
                _make_edge(
                    "python:pkg/c.py::run",
                    callee_id,
                    "calls",
                    "HEURISTIC",
                    dst_name="greet",
                    dst_id=callee_id,
                    dst_candidates=[callee_id, "python:pkg/b.py::D.greet"],
                ),
            ]
        )
        blocks: list = []
        seen: set = set()
        with patch(
            "akms.repo_wiki.retrieve.search_index",
            side_effect=self._search_side_effect(callee_id),
        ):
            add_symbol_neighbors(
                tmp_path,
                blocks,
                seen,
                graph,
                "python:pkg/c.py::run",
                "calls",
                "callee",
                expand_heuristic_edges=True,
            )
        assert len(blocks) == 1

    def test_add_symbol_neighbors_heuristic_skipped_when_flag_false(self, tmp_path):
        callee_id = "python:pkg/a.py::C.greet"
        graph = _graph_with_edges(
            [
                _make_edge(
                    "python:pkg/c.py::run",
                    callee_id,
                    "calls",
                    "HEURISTIC",
                    dst_name="greet",
                    dst_id=callee_id,
                    dst_candidates=[callee_id, "python:pkg/b.py::D.greet"],
                ),
            ]
        )
        blocks: list = []
        seen: set = set()
        with patch("akms.repo_wiki.retrieve.search_index", return_value=[]):
            add_symbol_neighbors(
                tmp_path,
                blocks,
                seen,
                graph,
                "python:pkg/c.py::run",
                "calls",
                "callee",
                expand_heuristic_edges=False,
            )
        assert blocks == []

    def test_add_reverse_symbol_neighbors_skips_unresolved(self, tmp_path):
        graph = _graph_with_edges(
            [
                _make_edge(
                    "ghost_caller",
                    "python:pkg/a.py::foo",
                    "calls",
                    "UNRESOLVED",
                    dst_name="foo",
                    dst_id=None,
                ),
            ]
        )
        blocks: list = []
        seen: set = set()
        with patch("akms.repo_wiki.retrieve.search_index", return_value=[]):
            add_reverse_symbol_neighbors(
                tmp_path,
                blocks,
                seen,
                graph,
                "python:pkg/a.py::foo",
                "calls",
                "caller",
                expand_heuristic_edges=True,
            )
        assert blocks == []


class TestP34:
    """Graph-driven expansion respects resolution priority."""

    @pytest.mark.unit
    def test_expand_context_prefers_confident_edges_first(self, tmp_path: Path):
        """Confident neighbours appear in the context before heuristic ones."""
        confident_id = "python:pkg/b.py::unique_helper"
        heuristic_id = "python:pkg/a.py::C.greet"

        source_id = "python:pkg/c.py::caller"
        graph = _graph_with_edges(
            [
                _make_edge(
                    source_id,
                    confident_id,
                    "calls",
                    "CONFIDENT",
                    dst_name="unique_helper",
                    dst_id=confident_id,
                ),
                _make_edge(
                    source_id,
                    heuristic_id,
                    "calls",
                    "HEURISTIC",
                    dst_name="greet",
                    dst_id=heuristic_id,
                    dst_candidates=[heuristic_id, "python:pkg/b.py::D.greet"],
                ),
            ]
        )

        result = _sr(
            source_id, symbol_id=source_id, path="pkg/c.py", module="python:pkg/c.py"
        )

        call_count = 0

        def fake_search(repo_root, query, *, limit, filters=None):
            nonlocal call_count
            call_count += 1
            if filters:
                sid = filters.get("symbol_id", "")
                if sid == confident_id:
                    return [_sr(confident_id, symbol_id=confident_id)]
                if sid == heuristic_id:
                    return [_sr(heuristic_id, symbol_id=heuristic_id)]
            return []

        _write_graph(tmp_path, graph)
        config = _base_config()

        with patch("akms.repo_wiki.retrieve.search_index", side_effect=fake_search):
            blocks = expand_context(
                tmp_path, [result], config, expand_heuristic_edges=True
            )

        callee_ids = [b.result.symbol_id for b in blocks if b.role == "callee"]
        assert confident_id in callee_ids
        assert heuristic_id in callee_ids
        assert callee_ids.index(confident_id) < callee_ids.index(heuristic_id)

    @pytest.mark.unit
    def test_expand_context_respects_expand_heuristic_edges_true(self, tmp_path: Path):
        """With expand_heuristic_edges on, neighbours reached via heuristic edges are included."""
        source_id = "python:pkg/c.py::caller"
        heuristic_id = "python:pkg/a.py::C.greet"
        graph = _graph_with_edges(
            [
                _make_edge(
                    source_id,
                    heuristic_id,
                    "calls",
                    "HEURISTIC",
                    dst_name="greet",
                    dst_id=heuristic_id,
                    dst_candidates=[heuristic_id, "python:pkg/b.py::D.greet"],
                ),
            ]
        )

        def fake_search(repo_root, query, *, limit, filters=None):
            if filters and filters.get("symbol_id") == heuristic_id:
                return [_sr(heuristic_id, symbol_id=heuristic_id)]
            return []

        _write_graph(tmp_path, graph)
        config = _base_config()
        result = _sr(
            source_id, symbol_id=source_id, path="pkg/c.py", module="python:pkg/c.py"
        )

        with patch("akms.repo_wiki.retrieve.search_index", side_effect=fake_search):
            blocks = expand_context(
                tmp_path, [result], config, expand_heuristic_edges=True
            )

        callee_ids = [b.result.symbol_id for b in blocks if b.role == "callee"]
        assert heuristic_id in callee_ids

    @pytest.mark.unit
    def test_expand_context_skips_heuristic_edges_when_flag_false(self, tmp_path: Path):
        """With expand_heuristic_edges off, neighbours reached via heuristic edges are skipped."""
        source_id = "python:pkg/c.py::caller"
        heuristic_id = "python:pkg/a.py::C.greet"
        graph = _graph_with_edges(
            [
                _make_edge(
                    source_id,
                    heuristic_id,
                    "calls",
                    "HEURISTIC",
                    dst_name="greet",
                    dst_id=heuristic_id,
                    dst_candidates=[heuristic_id, "python:pkg/b.py::D.greet"],
                ),
            ]
        )

        def fake_search(repo_root, query, *, limit, filters=None):
            if filters and filters.get("symbol_id") == heuristic_id:
                return [_sr(heuristic_id, symbol_id=heuristic_id)]
            return []

        _write_graph(tmp_path, graph)
        config = _base_config()
        result = _sr(
            source_id, symbol_id=source_id, path="pkg/c.py", module="python:pkg/c.py"
        )

        with patch("akms.repo_wiki.retrieve.search_index", side_effect=fake_search):
            blocks = expand_context(
                tmp_path, [result], config, expand_heuristic_edges=False
            )

        callee_ids = [b.result.symbol_id for b in blocks if b.role == "callee"]
        assert heuristic_id not in callee_ids

    @pytest.mark.unit
    def test_expand_context_skips_unresolved_edges_by_default(self, tmp_path: Path):
        """Unresolved edges are not traversed during expansion."""
        source_id = "python:pkg/a.py::caller"
        graph = _graph_with_edges(
            [
                _make_edge(
                    source_id,
                    "ghost_fn",
                    "calls",
                    "UNRESOLVED",
                    dst_name="ghost_fn",
                    dst_id=None,
                ),
            ]
        )

        call_count = 0

        def fake_search(repo_root, query, *, limit, filters=None):
            nonlocal call_count
            call_count += 1
            return []

        _write_graph(tmp_path, graph)
        config = _base_config()
        result = _sr(source_id, symbol_id=source_id)

        with patch("akms.repo_wiki.retrieve.search_index", side_effect=fake_search):
            blocks = expand_context(
                tmp_path, [result], config, expand_heuristic_edges=True
            )

        callee_blocks = [b for b in blocks if b.role == "callee"]
        assert callee_blocks == []

    @pytest.mark.regression
    def test_expand_context_with_mixed_resolutions_fixture(self, tmp_path: Path):
        """Expansion over a mixed graph: heuristic edges to ambiguous names, a confident edge to a unique helper."""
        source_id = "python:pkg/c.py::run"
        confident_id = "python:pkg/b.py::unique_helper"
        heuristic_id = "python:pkg/a.py::A.__init__"
        heuristic_id2 = "python:pkg/b.py::B.__init__"

        graph = _graph_with_edges(
            [
                _make_edge(
                    source_id,
                    confident_id,
                    "calls",
                    "CONFIDENT",
                    dst_name="unique_helper",
                    dst_id=confident_id,
                ),
                _make_edge(
                    source_id,
                    heuristic_id,
                    "calls",
                    "HEURISTIC",
                    dst_name="__init__",
                    dst_id=heuristic_id,
                    dst_candidates=[heuristic_id, heuristic_id2],
                ),
                _make_edge(
                    source_id,
                    "ghost_fn",
                    "calls",
                    "UNRESOLVED",
                    dst_name="ghost_fn",
                    dst_id=None,
                ),
            ]
        )

        def fake_search(repo_root, query, *, limit, filters=None):
            if filters:
                sid = filters.get("symbol_id", "")
                if sid == confident_id:
                    return [_sr(confident_id, symbol_id=confident_id)]
                if sid == heuristic_id:
                    return [_sr(heuristic_id, symbol_id=heuristic_id)]
            return []

        _write_graph(tmp_path, graph)
        config = _base_config()
        result = _sr(
            source_id, symbol_id=source_id, path="pkg/c.py", module="python:pkg/c.py"
        )

        with patch("akms.repo_wiki.retrieve.search_index", side_effect=fake_search):
            blocks_with = expand_context(
                tmp_path, [result], config, expand_heuristic_edges=True
            )

        callee_ids_with = [
            b.result.symbol_id for b in blocks_with if b.role == "callee"
        ]
        assert confident_id in callee_ids_with, "CONFIDENT callee must be included"
        assert heuristic_id in callee_ids_with, (
            "HEURISTIC callee must be included when flag True"
        )
        assert "ghost_fn" not in callee_ids_with

        with patch("akms.repo_wiki.retrieve.search_index", side_effect=fake_search):
            blocks_without = expand_context(
                tmp_path, [result], config, expand_heuristic_edges=False
            )

        callee_ids_without = [
            b.result.symbol_id for b in blocks_without if b.role == "callee"
        ]
        assert confident_id in callee_ids_without, "CONFIDENT callee must still appear"
        assert heuristic_id not in callee_ids_without, (
            "HEURISTIC callee must be excluded when flag False"
        )

    @pytest.mark.unit
    def test_expand_heuristic_edges_flag_defaults_to_true(self, tmp_path: Path):
        """Heuristic edges are followed when the flag is not passed."""
        source_id = "python:pkg/c.py::caller"
        heuristic_id = "python:pkg/a.py::C.greet"
        graph = _graph_with_edges(
            [
                _make_edge(
                    source_id,
                    heuristic_id,
                    "calls",
                    "HEURISTIC",
                    dst_name="greet",
                    dst_id=heuristic_id,
                    dst_candidates=[heuristic_id, "python:pkg/b.py::D.greet"],
                ),
            ]
        )

        def fake_search(repo_root, query, *, limit, filters=None):
            if filters and filters.get("symbol_id") == heuristic_id:
                return [_sr(heuristic_id, symbol_id=heuristic_id)]
            return []

        _write_graph(tmp_path, graph)
        config = _base_config()
        result = _sr(
            source_id, symbol_id=source_id, path="pkg/c.py", module="python:pkg/c.py"
        )

        with patch("akms.repo_wiki.retrieve.search_index", side_effect=fake_search):
            blocks = expand_context(tmp_path, [result], config)

        callee_ids = [b.result.symbol_id for b in blocks if b.role == "callee"]
        assert heuristic_id in callee_ids, (
            "HEURISTIC edge must be followed by default (expand_heuristic_edges=True)"
        )
