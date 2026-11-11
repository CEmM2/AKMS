"""Symbol graph edges: schema, per-edge resolution (confident, heuristic, unresolved) and determinism."""

from __future__ import annotations

import pytest

from akms.repo_wiki.graph import (
    Resolution,
    _make_edge,
    build_symbol_graph,
    edge_provenance,
)
from akms.repo_wiki.models import Language, ParsedModule, SourceFile, SourceSpan, Symbol


def _source_file(path: str = "pkg/a.py") -> SourceFile:
    return SourceFile(
        path=path,
        abs_path=f"/repo/{path}",
        language="python",
        size_bytes=100,
        content_hash="abc123",
    )


def _span(path: str = "pkg/a.py", start: int = 1, end: int = 10) -> SourceSpan:
    return SourceSpan(path=path, start_line=start, end_line=end)


def _symbol(
    symbol_id: str,
    name: str,
    qualname: str,
    path: str = "pkg/a.py",
    kind: str = "function",
    parent_id: str | None = None,
    bases: list[str] | None = None,
    calls: list[str] | None = None,
) -> Symbol:
    return Symbol(
        symbol_id=symbol_id,
        path=path,
        module=f"python:{path}",
        name=name,
        qualname=qualname,
        kind=kind,  # type: ignore[arg-type]
        parent_id=parent_id,
        start_line=1,
        end_line=10,
        signature=None,
        docstring=None,
        span=_span(path),
        language=Language.PYTHON,
        bases=bases or [],
        calls=calls or [],
    )


def _module(path: str, symbols: list[Symbol]) -> ParsedModule:
    return ParsedModule(
        source_file=_source_file(path),
        module=f"python:{path}",
        docstring=None,
        imports=[],
        symbols=symbols,
    )


def _edges_by_type_and_name(graph: dict, edge_type: str, dst_name: str) -> list[dict]:
    return [
        e
        for e in graph["edges"]
        if e["type"] == edge_type and e["dst_name"] == dst_name
    ]


def test_every_edge_carries_resolution_dst_name_and_dst_id():
    """Edges always have a valid resolution, a non-empty dst_name and a dst_id key."""
    caller = _symbol(
        "python:pkg/mod.py::Greeter.greet",
        "greet",
        "Greeter.greet",
        path="pkg/mod.py",
        calls=["helper"],
    )
    callee = _symbol("python:pkg/mod.py::helper", "helper", "helper", path="pkg/mod.py")
    graph = build_symbol_graph([_module("pkg/mod.py", [caller, callee])])

    valid = {resolution.value for resolution in Resolution}
    assert graph["edges"]
    for edge in graph["edges"]:
        assert edge["resolution"] in valid
        assert isinstance(edge["dst_name"], str) and edge["dst_name"]
        assert "dst_id" in edge
        assert edge["dst_id"] is None or isinstance(edge["dst_id"], str)


def test_structural_edges_are_confident_with_a_destination():
    """defined_in and belongs_to edges point at known nodes and are confident."""
    caller = _symbol(
        "python:pkg/mod.py::Greeter.greet", "greet", "Greeter.greet", path="pkg/mod.py"
    )
    graph = build_symbol_graph([_module("pkg/mod.py", [caller])])

    structural = [
        edge for edge in graph["edges"] if edge["type"] in {"defined_in", "belongs_to"}
    ]
    assert structural
    for edge in structural:
        assert edge["resolution"] == Resolution.CONFIDENT.value
        assert edge["dst_id"] is not None


def test_unique_target_name_resolves_confident():
    """A call or inherits target with exactly one match is CONFIDENT, with dst_id and no dst_candidates."""
    target = _symbol(
        "python:pkg/a.py::unique_fn", "unique_fn", "unique_fn", path="pkg/a.py"
    )
    caller = _symbol(
        "python:pkg/b.py::caller",
        "caller",
        "caller",
        path="pkg/b.py",
        calls=["unique_fn"],
    )
    graph = build_symbol_graph(
        [_module("pkg/a.py", [target]), _module("pkg/b.py", [caller])]
    )

    call_edges = _edges_by_type_and_name(graph, "calls", "unique_fn")
    assert len(call_edges) == 1
    edge = call_edges[0]
    assert edge["resolution"] == Resolution.CONFIDENT.value
    assert edge["dst_id"] == "python:pkg/a.py::unique_fn"
    assert "dst_candidates" not in edge

    base = _symbol(
        "python:pkg/a.py::Base", "Base", "Base", path="pkg/a.py", kind="class"
    )
    sub = _symbol(
        "python:pkg/b.py::Sub",
        "Sub",
        "Sub",
        path="pkg/b.py",
        kind="class",
        bases=["Base"],
    )
    graph2 = build_symbol_graph(
        [_module("pkg/a.py", [base]), _module("pkg/b.py", [sub])]
    )
    inh_edges = _edges_by_type_and_name(graph2, "inherits", "Base")
    assert len(inh_edges) == 1
    assert inh_edges[0]["resolution"] == Resolution.CONFIDENT.value
    assert inh_edges[0]["dst_id"] == "python:pkg/a.py::Base"
    assert "dst_candidates" not in inh_edges[0]


def test_ambiguous_target_name_resolves_heuristic_with_candidates():
    """A target matching several symbols is HEURISTIC: dst_id is the sorted-first match and dst_candidates lists all."""
    m1 = _symbol("python:pkg/a.py::C.greet", "greet", "C.greet", path="pkg/a.py")
    m2 = _symbol("python:pkg/b.py::D.greet", "greet", "D.greet", path="pkg/b.py")
    caller = _symbol(
        "python:pkg/c.py::run",
        "run",
        "run",
        path="pkg/c.py",
        calls=["greet"],
    )
    graph = build_symbol_graph(
        [
            _module("pkg/a.py", [m1]),
            _module("pkg/b.py", [m2]),
            _module("pkg/c.py", [caller]),
        ]
    )

    call_edges = _edges_by_type_and_name(graph, "calls", "greet")
    assert len(call_edges) == 1
    edge = call_edges[0]
    assert edge["resolution"] == Resolution.HEURISTIC.value

    ids = ["python:pkg/a.py::C.greet", "python:pkg/b.py::D.greet"]
    assert "dst_candidates" in edge
    assert sorted(edge["dst_candidates"]) == sorted(ids)
    assert len(edge["dst_candidates"]) == 2
    assert edge["dst_id"] == sorted(ids)[0]
    assert edge["dst_id"] == edge["dst_candidates"][0]


def test_unknown_target_name_resolves_unresolved():
    """A target with no match is UNRESOLVED: no dst_id, no dst_candidates, dst_name preserved."""
    caller = _symbol(
        "python:pkg/a.py::caller",
        "caller",
        "caller",
        path="pkg/a.py",
        calls=["ghost_fn"],
    )
    graph = build_symbol_graph([_module("pkg/a.py", [caller])])

    call_edges = _edges_by_type_and_name(graph, "calls", "ghost_fn")
    assert len(call_edges) == 1
    edge = call_edges[0]
    assert edge["resolution"] == Resolution.UNRESOLVED.value
    assert edge["dst_id"] is None
    assert edge["dst_name"] == "ghost_fn"
    assert "dst_candidates" not in edge


def test_per_edge_resolution_determinism_same_fixture_identical_across_rebuilds():
    """Rebuilding the graph from the same modules yields identical edges, including the heuristic pick."""
    m1 = _symbol("python:pkg/a.py::C.greet", "greet", "C.greet", path="pkg/a.py")
    m2 = _symbol("python:pkg/b.py::D.greet", "greet", "D.greet", path="pkg/b.py")
    uniq = _symbol("python:pkg/a.py::solo", "solo", "solo", path="pkg/a.py")
    base = _symbol(
        "python:pkg/a.py::Base", "Base", "Base", path="pkg/a.py", kind="class"
    )
    sub = _symbol(
        "python:pkg/c.py::Sub",
        "Sub",
        "Sub",
        path="pkg/c.py",
        kind="class",
        bases=["Base"],
        calls=["greet", "solo", "ghost"],
    )
    modules = [
        _module("pkg/a.py", [m1, uniq, base]),
        _module("pkg/b.py", [m2]),
        _module("pkg/c.py", [sub]),
    ]

    g1 = build_symbol_graph(modules)
    g2 = build_symbol_graph(modules)

    def projection(graph: dict) -> list[tuple]:
        return [
            (
                e["source"],
                e["type"],
                e["target"],
                e["dst_name"],
                e["dst_id"],
                e["resolution"],
                tuple(e.get("dst_candidates") or ()),
            )
            for e in graph["edges"]
        ]

    assert projection(g1) == projection(g2)

    heur = _edges_by_type_and_name(g1, "calls", "greet")[0]
    assert heur["resolution"] == Resolution.HEURISTIC.value
    assert heur["dst_id"] == "python:pkg/a.py::C.greet"


def test_per_edge_resolution_only_not_global_best_guess():
    """Each edge is resolved on its own; no global fallback rewrites unresolved edges."""
    target = _symbol(
        "python:pkg/a.py::known_fn", "known_fn", "known_fn", path="pkg/a.py"
    )
    caller = _symbol(
        "python:pkg/b.py::caller",
        "caller",
        "caller",
        path="pkg/b.py",
        calls=["known_fn", "ghost_fn"],
    )
    m1 = _symbol("python:pkg/a.py::dup", "dup", "C.dup", path="pkg/a.py")
    m2 = _symbol("python:pkg/c.py::dup", "dup", "D.dup", path="pkg/c.py")
    caller2 = _symbol(
        "python:pkg/b.py::caller2",
        "caller2",
        "caller2",
        path="pkg/b.py",
        calls=["dup"],
    )
    graph = build_symbol_graph(
        [
            _module("pkg/a.py", [target, m1]),
            _module("pkg/b.py", [caller, caller2]),
            _module("pkg/c.py", [m2]),
        ]
    )

    by_name = {e["dst_name"]: e for e in graph["edges"] if e["type"] == "calls"}

    assert by_name["known_fn"]["resolution"] == Resolution.CONFIDENT.value
    assert by_name["known_fn"]["dst_id"] == "python:pkg/a.py::known_fn"
    assert "dst_candidates" not in by_name["known_fn"]

    assert by_name["ghost_fn"]["resolution"] == Resolution.UNRESOLVED.value
    assert by_name["ghost_fn"]["dst_id"] is None

    assert by_name["dup"]["resolution"] == Resolution.HEURISTIC.value
    assert len(by_name["dup"]["dst_candidates"]) == 2

    outcomes = {by_name[n]["resolution"] for n in ("known_fn", "ghost_fn", "dup")}
    assert outcomes == {
        Resolution.CONFIDENT.value,
        Resolution.UNRESOLVED.value,
        Resolution.HEURISTIC.value,
    }


def test_multimap_handles_both_short_and_qual_names():
    """A call by full qualname resolves to that one symbol even when its short name is shared."""
    sym_a = _symbol(
        "python:pkg/a.py::Greeter.greet",
        name="greet",
        qualname="Greeter.greet",
        path="pkg/a.py",
    )
    sym_b = _symbol(
        "python:pkg/b.py::Helper.greet",
        name="greet",
        qualname="Helper.greet",
        path="pkg/b.py",
    )

    caller = _symbol(
        "python:pkg/c.py::run",
        name="run",
        qualname="run",
        path="pkg/c.py",
        calls=["Greeter.greet"],
    )

    modules = [
        _module("pkg/a.py", [sym_a]),
        _module("pkg/b.py", [sym_b]),
        _module("pkg/c.py", [caller]),
    ]
    graph = build_symbol_graph(modules)

    qual_edges = [
        e
        for e in graph["edges"]
        if e["type"] == "calls" and e["dst_name"] == "Greeter.greet"
    ]
    assert len(qual_edges) == 1
    assert qual_edges[0]["dst_id"] == "python:pkg/a.py::Greeter.greet"
    assert qual_edges[0]["resolution"] == Resolution.CONFIDENT.value


def test_edges_omit_provenance_when_static_so_graph_bytes_do_not_change():
    """Every edge built today is static: the optional field is not written."""
    caller = _symbol(
        "python:pkg/mod.py::caller", "caller", "caller", path="pkg/mod.py", calls=["f"]
    )
    callee = _symbol("python:pkg/mod.py::f", "f", "f", path="pkg/mod.py")
    graph = build_symbol_graph([_module("pkg/mod.py", [caller, callee])])
    assert all("provenance" not in edge for edge in graph["edges"])
    assert all(edge_provenance(edge) == "static" for edge in graph["edges"])
    assert "provenance" in graph["_comment"]


def test_non_static_provenance_is_written_and_unknown_values_rejected():
    edge = _make_edge(
        "a",
        "b",
        "calls",
        dst_name="b",
        dst_id="b",
        resolution=Resolution.HEURISTIC,
        dst_candidates=["b"],
        provenance="inferred",
    )
    assert edge["provenance"] == "inferred"
    assert edge_provenance(edge) == "inferred"
    assert edge_provenance({"provenance": "telepathy"}) == "static"
    assert edge_provenance({"provenance": 3}) == "static"
    with pytest.raises(ValueError, match="provenance"):
        _make_edge(
            "a",
            "b",
            "calls",
            dst_name="b",
            dst_id="b",
            resolution=Resolution.CONFIDENT,
            provenance="telepathy",
        )
