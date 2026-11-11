"""Inferred links: typed local receivers and literal dispatch tables (``provenance: inferred``).

A local bound to a repository class (``x = C()`` or ``x: C = ...``) makes ``x.m()`` a link to
``C.m``: CONFIDENT when exactly one target remains, HEURISTIC otherwise. A function that
indexes a module-level dict of callables gets a HEURISTIC link to every value, never a
CONFIDENT one.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from akms.repo_wiki.cli import main
from akms.repo_wiki.code_graph import CONFIDENT, HEURISTIC, CodeGraph, load_code_graph
from akms.repo_wiki.extract.python_ast import (
    extract_dispatch_tables,
    extract_receivers,
    extract_table_refs,
    parse_python_file,
)
from akms.repo_wiki.graph import build_symbol_graph
from akms.repo_wiki.models import ParsedModule, SourceFile, Symbol

MODELS = """\
class Base:
    def ping(self):
        return 1


class Store(Base):
    def save(self, item):
        return item


class Archive:
    def save(self, item):
        return item
"""

USES = """\
import argparse
from typing import Optional

from pkg.models import Archive, Store


def one():
    store = Store()
    return store.save(1)


def inherited():
    store = Store()
    return store.ping()


def annotated():
    box: Optional["Store"] = None
    return box.save(2)


def either(flag):
    target = Store()
    if flag:
        target = Archive()
    return target.save(3)


def outside():
    parser = argparse.ArgumentParser()
    return parser.add_argument("x")


def outer():
    store = Store()

    def inner():
        return store.save(4)

    return inner()
"""

TABLES = """\
from pkg.models import Archive


def load(path):
    return path


def dump(path):
    return path


HANDLERS = {"load": load, "dump": dump, "archive": Archive}
NOT_A_TABLE = {"a": 1, "b": 2}
SINGLE = {"load": load}


def run(kind, path):
    return HANDLERS[kind](path)


def maybe(kind, path):
    handler = HANDLERS.get(kind)
    return handler(path) if handler else None
"""

HOLDERS = """\
from typing import Optional

from pkg.models import Archive, Store


def param(store: Store):
    return store.save(1)


def optional_param(box: Optional["Store"] = None):
    return box.save(2)


def union_param(box: "Store | None"):
    return box.save(3)


def two_params(a: Store, b):
    return a.ping(), b.save(4)


class Holder:
    shared: Archive

    def __init__(self, given: Store, other):
        self.made = Store()
        self.given = given
        self.other = other
        self.noted: Archive = other

    def use(self):
        return self.made.save(1), self.given.ping(), self.noted.save(2)

    def untyped(self):
        return self.other.save(3)

    @classmethod
    def klass(cls):
        return cls.shared.save(4)


class Child(Holder):
    def again(self):
        return self.made.save(5)


class Mixed:
    def __init__(self, flag):
        self.either = Store()
        if flag:
            self.either = Archive()

    def go(self):
        return self.either.save(6)
"""

REMOTE = """\
from pkg.tables import HANDLERS


def remote(kind):
    return HANDLERS[kind]("x")
"""


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/models.py", MODELS)
    _write(tmp_path, "pkg/uses.py", USES)
    _write(tmp_path, "pkg/tables.py", TABLES)
    _write(tmp_path, "pkg/remote.py", REMOTE)
    _write(tmp_path, "pkg/holders.py", HOLDERS)
    assert (
        main(["--repo-root", str(tmp_path), "build", "--no-summaries", "--no-index"])
        == 0
    )
    capsys.readouterr()
    return tmp_path


def _calls(graph: CodeGraph, source: str) -> dict[str, tuple[str, str, str]]:
    return {
        e.target: (e.resolution, e.basis, e.provenance)
        for e in graph.out_edges.get(source, [])
        if e.type == "calls"
    }


USES_ID = "python:pkg/uses.py::"
MODELS_ID = "python:pkg/models.py::"
TABLES_ID = "python:pkg/tables.py::"

# ---------------------------------------------------------------- extraction


def _function(source: str) -> ast.FunctionDef:
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.FunctionDef)
    return node


def test_receivers_record_only_names_used_as_call_receivers() -> None:
    node = _function(
        "def f():\n"
        "    a = Store()\n"
        "    b = make()\n"
        "    c = Unused()\n"
        "    d: 'mod.Thing' = build()\n"
        "    e: Thing | None = None\n"
        "    self = Weird()\n"
        "    a.save(); b.run(); d.go(); e.stop(); self.x()\n"
    )
    calls = ["a.save", "b.run", "d.go", "e.stop", "self.x", "Store", "make"]
    assert extract_receivers(node, calls) == {
        "a": ["Store"],
        "b": ["make"],
        "d": ["mod.Thing"],
        "e": ["Thing"],
    }


def test_table_refs_record_subscripts_and_get_of_known_names() -> None:
    node = _function("def f(k):\n    T[k]()\n    U.get(k)\n    V[k] = 1\n    W[k]\n")
    assert extract_table_refs(node, frozenset({"T", "U", "V"})) == ["T", "U"]
    assert extract_table_refs(node, frozenset()) == []


def test_dispatch_tables_are_detected_by_shape_not_name() -> None:
    tree = ast.parse(
        "from x import ext\n"
        "def a(): ...\n"
        "class B: ...\n"
        "routes = {'a': a, 'b': B, 3: ext.run}\n"
        "ONE = {'a': a}\n"
        "DATA = {'a': 1, 'b': 2}\n"
        "MIXED = {'a': a, 'b': unknown}\n"
        "SPREAD = {'a': a, **routes}\n"
        "CALLS = {'a': a(), 'b': B}\n"
    )
    assert extract_dispatch_tables(tree, {"ext": "x.ext"}) == {
        "routes": ["B", "a", "ext.run"]
    }


def test_new_ir_fields_round_trip_and_are_omitted_when_empty(repo: Path) -> None:
    source = SourceFile(
        "pkg/tables.py",
        str(repo / "pkg/tables.py"),
        "python",
        1,
        "h",
    )
    parsed = parse_python_file(source)
    assert parsed.dispatch_tables == {"HANDLERS": ["Archive", "dump", "load"]}
    data = parsed.to_dict()
    assert ParsedModule.from_dict(data).dispatch_tables == parsed.dispatch_tables
    run = next(s for s in parsed.symbols if s.name == "run")
    assert run.table_refs == ["HANDLERS"]
    assert Symbol.from_dict(run.to_dict()).table_refs == ["HANDLERS"]
    load = next(s for s in parsed.symbols if s.name == "load")
    assert "table_refs" not in load.to_dict() and "receivers" not in load.to_dict()
    bare = ParsedModule(source, "pkg.x", None, [], [])
    assert "dispatch_tables" not in bare.to_dict()


def test_graph_nodes_carry_the_facts_only_when_present(repo: Path) -> None:
    graph = json.loads(
        (repo / ".repo_wiki/generated/symbol_graph.json").read_text("utf-8")
    )
    nodes = graph["nodes"]
    assert nodes["pkg.tables"]["dispatch"] == {"HANDLERS": ["Archive", "dump", "load"]}
    assert "dispatch" not in nodes["pkg.uses"]
    assert nodes[USES_ID + "one"]["receivers"] == {"store": ["Store"]}
    assert nodes[TABLES_ID + "run"]["table_refs"] == ["HANDLERS"]
    assert "receivers" not in nodes[TABLES_ID + "load"]
    # The on-disk edges are unchanged: inferred links are made when the graph is loaded.
    assert all("provenance" not in edge for edge in graph["edges"])


# ---------------------------------------------------------------- resolution


def test_typed_local_receiver_links_confidently_to_the_one_method(repo: Path) -> None:
    graph = load_code_graph(repo).graph
    assert _calls(graph, USES_ID + "one")[MODELS_ID + "Store.save"] == (
        CONFIDENT,
        "receiver",
        "inferred",
    )
    # Base classes are walked; annotations (Optional, strings) count as a binding.
    assert _calls(graph, USES_ID + "inherited")[MODELS_ID + "Base.ping"][:2] == (
        CONFIDENT,
        "receiver",
    )
    assert _calls(graph, USES_ID + "annotated")[MODELS_ID + "Store.save"][:2] == (
        CONFIDENT,
        "receiver",
    )
    # A closure sees the enclosing function's binding.
    assert _calls(graph, USES_ID + "outer.inner")[MODELS_ID + "Store.save"][:2] == (
        CONFIDENT,
        "receiver",
    )


def test_receiver_bound_to_several_classes_stays_heuristic(repo: Path) -> None:
    graph = load_code_graph(repo).graph
    calls = _calls(graph, USES_ID + "either")
    assert calls[MODELS_ID + "Store.save"] == (HEURISTIC, "receiver", "inferred")
    assert calls[MODELS_ID + "Archive.save"] == (HEURISTIC, "receiver", "inferred")
    edge = next(
        e
        for e in graph.out_edges[USES_ID + "either"]
        if e.target == MODELS_ID + "Store.save"
    )
    assert edge.candidates == (MODELS_ID + "Archive.save", MODELS_ID + "Store.save")


def test_receiver_of_an_external_class_is_external_not_a_name_match(
    repo: Path,
) -> None:
    graph = load_code_graph(repo).graph
    assert not [t for t in _calls(graph, USES_ID + "outside") if "add_argument" in t]
    external = [u.name for u in graph.unresolved[USES_ID + "outside"] if u.external]
    assert "parser.add_argument" in external


def test_dispatch_table_gives_heuristic_links_to_every_value(repo: Path) -> None:
    graph = load_code_graph(repo).graph
    for source in ("run", "maybe"):
        calls = _calls(graph, TABLES_ID + source)
        expected = {
            TABLES_ID + "load",
            TABLES_ID + "dump",
            MODELS_ID + "Archive",
        }
        assert expected <= set(calls), source
        for target in expected:
            assert calls[target] == (HEURISTIC, "dispatch", "inferred")
    # An imported table resolves in the module that defines it.
    remote = _calls(graph, "python:pkg/remote.py::remote")
    assert remote[TABLES_ID + "load"] == (HEURISTIC, "dispatch", "inferred")
    # Dispatch links are never CONFIDENT and so never move the risk level.
    assert all(
        e.resolution == HEURISTIC
        for edges in graph.out_edges.values()
        for e in edges
        if e.basis == "dispatch"
    )


def test_dispatch_links_count_only_as_possible_in_impact(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--repo-root", str(repo), "impact", "load", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    d1 = payload["levels"][0]
    assert not d1["confident"]
    assert {e["id"] for e in d1["possible"]} >= {TABLES_ID + "run", TABLES_ID + "maybe"}
    assert payload["summary"]["risk"] == "LOW"


def test_graph_without_the_facts_falls_back_to_attribute_links() -> None:
    """An older graph (no receivers field) keeps the plain attribute rule."""
    parsed = [
        ParsedModule(
            SourceFile("m.py", "/r/m.py", "python", 1, "h"),
            "m",
            None,
            [],
            [
                _sym("m.py", "Store", "class"),
                _sym("m.py", "Store.save", "method", parent="python:m.py::Store"),
                _sym("m.py", "Other", "class"),
                _sym("m.py", "Other.save", "method", parent="python:m.py::Other"),
                _sym("m.py", "use", "function", calls=["Store", "s.save"]),
            ],
        )
    ]
    data = build_symbol_graph(parsed)
    graph = CodeGraph.from_symbol_graph(data).finalize()
    calls = _calls(graph, "python:m.py::use")
    assert calls["python:m.py::Store.save"] == (HEURISTIC, "attribute", "static")
    parsed[0].symbols[-1].receivers = {"s": ["Store"]}
    graph = CodeGraph.from_symbol_graph(build_symbol_graph(parsed)).finalize()
    calls = _calls(graph, "python:m.py::use")
    assert calls["python:m.py::Store.save"] == (CONFIDENT, "receiver", "inferred")
    assert "python:m.py::Other.save" not in calls


def _sym(
    path: str,
    qualname: str,
    kind: str,
    *,
    parent: str | None = None,
    calls: list[str] | None = None,
) -> Symbol:
    from akms.repo_wiki.models import SourceSpan

    return Symbol(
        symbol_id=f"python:{path}::{qualname}",
        path=path,
        module="m",
        name=qualname.rsplit(".", 1)[-1],
        qualname=qualname,
        kind=kind,  # type: ignore[arg-type]
        parent_id=parent,
        start_line=1,
        end_line=2,
        signature=None,
        docstring=None,
        span=SourceSpan(path, 1, 2),
        calls=calls or [],
    )


HOLD = "python:pkg/holders.py::"


def test_annotated_parameters_type_their_receivers(repo: Path) -> None:
    graph = load_code_graph(repo).graph
    for source, method in (
        ("param", "Store.save"),
        ("optional_param", "Store.save"),
        ("union_param", "Store.save"),
        ("two_params", "Base.ping"),
    ):
        calls = _calls(graph, HOLD + source)
        assert calls[MODELS_ID + method] == (CONFIDENT, "receiver", "inferred"), source
    # An unannotated parameter keeps the attribute rule.
    assert (
        _calls(graph, HOLD + "two_params")[MODELS_ID + "Archive.save"][1] == "attribute"
    )


def test_self_attributes_bound_in_init_or_the_class_body(repo: Path) -> None:
    graph = load_code_graph(repo).graph
    use = _calls(graph, HOLD + "Holder.use")
    assert use[MODELS_ID + "Store.save"] == (CONFIDENT, "receiver", "inferred")
    assert use[MODELS_ID + "Base.ping"][:2] == (CONFIDENT, "receiver")  # self.given
    assert use[MODELS_ID + "Archive.save"][:2] == (CONFIDENT, "receiver")  # self.noted
    klass = _calls(graph, HOLD + "Holder.klass")  # cls.shared: Archive
    assert klass[MODELS_ID + "Archive.save"][:2] == (CONFIDENT, "receiver")
    # Inherited from the base class's __init__.
    again = _calls(graph, HOLD + "Child.again")
    assert again[MODELS_ID + "Store.save"][:2] == (CONFIDENT, "receiver")
    # self.other = other (no annotation): still only a name match.
    untyped = _calls(graph, HOLD + "Holder.untyped")
    assert {basis for _, basis, _ in untyped.values()} == {"attribute"}


def test_attribute_bound_to_two_classes_stays_heuristic(repo: Path) -> None:
    graph = load_code_graph(repo).graph
    go = _calls(graph, HOLD + "Mixed.go")
    assert go[MODELS_ID + "Store.save"] == (HEURISTIC, "receiver", "inferred")
    assert go[MODELS_ID + "Archive.save"] == (HEURISTIC, "receiver", "inferred")


def test_class_nodes_record_attribute_bindings(repo: Path) -> None:
    graph = json.loads(
        (repo / ".repo_wiki/generated/symbol_graph.json").read_text("utf-8")
    )
    nodes = graph["nodes"]
    assert nodes[HOLD + "Holder"]["receivers"] == {
        "given": ["Store"],
        "made": ["Store"],
        "noted": ["Archive"],
        "shared": ["Archive"],
    }
    assert nodes[HOLD + "Mixed"]["receivers"] == {"either": ["Archive", "Store"]}
    assert nodes[HOLD + "param"]["receivers"] == {"store": ["Store"]}
