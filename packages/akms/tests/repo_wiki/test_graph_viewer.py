import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from akms.repo_wiki.cli import build_parser, main
from akms.repo_wiki.graph_viewer import GraphStore, load_graph, make_handler
from .test_build_render_graph_summary import copy_fixture

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _edge(source, target, edge_type="calls", resolution="CONFIDENT"):
    return {
        "source": source,
        "target": target,
        "type": edge_type,
        "resolution": resolution,
    }


@pytest.fixture
def store():
    # a -> b -> c -> d chain, a hub h with many leaves, one heuristic import edge
    edges = [
        _edge("a", "b"),
        _edge("b", "c"),
        _edge("c", "d"),
        _edge("a", "b", "imports", "HEURISTIC"),
        _edge("h", "l1"),
        _edge("h", "l2"),
        _edge("h", "l3", "inherits", "UNRESOLVED"),
        {"source": "", "target": "x"},
        "junk",
    ]
    return GraphStore(edges)


def _ids(result):
    return {n["id"] for n in result["nodes"]}


def test_store_counts_and_skips_malformed_edges(store):
    meta = store.meta()
    assert meta["edge_count"] == 7
    assert meta["edge_types"] == ["calls", "imports", "inherits"]
    assert meta["resolutions"] == ["CONFIDENT", "HEURISTIC", "UNRESOLVED"]
    assert store.degree["h"] == 3


def test_type_and_resolution_filters(store):
    assert _ids(store.graph(edge_type="inherits")) == {"h", "l3"}
    assert _ids(store.graph(resolution="HEURISTIC")) == {"a", "b"}
    assert store.graph(edge_type="imports", resolution="UNRESOLVED")["links"] == []


def test_focus_depth_and_direction(store):
    assert _ids(store.graph(focus="b", depth=0)) == {"b"}
    assert _ids(store.graph(focus="b", depth=1)) == {"a", "b", "c"}
    assert _ids(store.graph(focus="b", depth=2)) == {"a", "b", "c", "d"}
    assert _ids(store.graph(focus="b", depth=2, direction="out")) == {"b", "c", "d"}
    assert _ids(store.graph(focus="b", depth=2, direction="in")) == {"a", "b"}
    result = store.graph(focus="H", depth=1)
    assert result["focus_resolved"] == "h"
    assert store.graph(focus="nope")["focus_resolved"] is None


def test_focus_depth_respects_edge_filters(store):
    assert _ids(store.graph(focus="a", depth=3, edge_type="imports")) == {"a", "b"}


def test_degree_filters(store):
    assert _ids(store.graph(min_degree=3)) == set()
    assert "d" not in _ids(store.graph(min_degree=2))
    assert "h" not in _ids(store.graph(max_degree=2))


def test_limit_keeps_highest_degree_nodes(store):
    result = store.graph(limit=2)
    assert result["truncated"] is True
    assert len(result["nodes"]) <= 2
    assert store.graph(limit=0)["truncated"] is False


def test_search_nodes_orders_by_degree(store):
    found = [n["id"] for n in store.search_nodes("L", 10)["nodes"]]
    assert found == ["l1", "l2", "l3"]
    assert store.search_nodes("  ", 10) == {"nodes": []}


def test_load_graph_reads_build_output(tmp_path: Path):
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-index"]) == 0
    graph_path = tmp_path / ".repo_wiki/generated/symbol_graph.json"
    built = json.loads(graph_path.read_text())
    loaded = load_graph(graph_path)
    assert len(loaded.raw_edges) == len(built["edges"])
    assert {"defined_in", "belongs_to"} <= set(loaded.edge_types)
    assert loaded.graph(edge_type="defined_in")["links"]


def test_load_graph_rejects_wrong_shape(tmp_path: Path):
    bad = tmp_path / "g.json"
    bad.write_text("[]")
    with pytest.raises(ValueError, match="edges"):
        load_graph(bad)
    bad.write_text("{nope")
    with pytest.raises(ValueError, match="not valid JSON"):
        load_graph(bad)


def test_http_handler_serves_meta_and_graph(store):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(store))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_address[1]}"
        meta = json.load(urllib.request.urlopen(f"{base}/api/meta", timeout=5))
        assert meta["edge_count"] == 7
        graph = json.load(
            urllib.request.urlopen(f"{base}/api/graph?focus=b&depth=1", timeout=5)
        )
        assert {n["id"] for n in graph["nodes"]} == {"a", "b", "c"}
        html = urllib.request.urlopen(f"{base}/", timeout=5).read().decode()
        assert "Symbol Graph Viewer" in html
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_cli_graph_parser_defaults():
    args = build_parser().parse_args(["graph"])
    assert (args.input, args.host, args.port, args.no_browser) == (
        None,
        "127.0.0.1",
        8765,
        False,
    )
    args = build_parser().parse_args(["graph", "g.json", "--port", "9", "--no-browser"])
    assert (args.input, args.port, args.no_browser) == ("g.json", 9, True)


def test_cli_graph_help(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["graph", "--help"])
    assert exc.value.code == 0
    assert "--no-browser" in capsys.readouterr().out


def test_cli_graph_missing_file_points_to_build(tmp_path: Path, capsys):
    assert main(["--repo-root", str(tmp_path), "graph", "--no-browser"]) == 1
    err = capsys.readouterr().err
    assert "repo-wiki build" in err
    assert "symbol_graph.json" in err
