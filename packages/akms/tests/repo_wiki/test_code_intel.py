"""``context`` and ``impact``: lookup, depth grouping, heuristic split, risk and errors.

The ``intel_repo`` fixture has known chains::

    leaf <- middle <- run <- public_entry (exported from pkg/__init__) <- main (pkg/cli.py)
    leaf <- Store._write <- Store.save (self) <- persist (``store = Store()``: receiver)
    Store.save <~ persist_any (``store.save()`` on a parameter: attribute, 2 candidates)
    leaf <- via_module (``core.leaf`` through ``from pkg import core``)
    leaf <- test_leaf (tests/)
    middle <~ stray (bare name, never imported: name match only)
    parse: defined twice (ambiguous)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from akms.repo_wiki.cli import main
from akms.repo_wiki.code_graph import (
    CONFIDENT,
    HEURISTIC,
    CodeGraph,
    GraphUnavailableError,
    is_test_path,
    load_code_graph,
)
from akms.repo_wiki.extract.python_ast import parse_python_file
from akms.repo_wiki.impact import (
    PUBLIC_ENTRY_CAP,
    RISK_THRESHOLDS,
    SymbolLookupError,
    build_impact,
    resolve_symbol,
    risk_level,
)

from akms.repo_wiki.models import SourceFile

from .test_build_render_graph_summary import copy_fixture

FIXTURES = Path(__file__).resolve().parent / "fixtures"

LEAF = "python:pkg/core.py::leaf"
MIDDLE = "python:pkg/core.py::middle"


@pytest.fixture()
def repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    copy_fixture(FIXTURES / "intel_repo", tmp_path)
    assert (
        main(["--repo-root", str(tmp_path), "build", "--no-summaries", "--no-index"])
        == 0
    )
    capsys.readouterr()
    return tmp_path


def run_json(
    repo: Path, capsys: pytest.CaptureFixture[str], *args: str
) -> tuple[int, dict]:
    code = main(["--repo-root", str(repo), *args, "--json"])
    return code, json.loads(capsys.readouterr().out)


def ids(entries: list[dict]) -> list[str]:
    return [entry["id"] for entry in entries]


# ----------------------------------------------------------------- resolution


def test_python_calls_resolve_by_scope_import_and_self(repo: Path) -> None:
    graph = load_code_graph(repo).graph
    callers = {e.source: e for e in graph.in_edges[LEAF]}
    assert callers["python:pkg/core.py::middle"].basis == "local"
    assert callers["python:pkg/service.py::via_module"].basis == "import"
    assert callers["python:pkg/core.py::Store._write"].basis == "local"
    assert all(e.resolution == CONFIDENT for e in callers.values())
    save = {e.source: e for e in graph.in_edges["python:pkg/core.py::Store._write"]}
    assert save["python:pkg/core.py::Store.save"].basis == "self"


def test_constructor_call_reaches_init_and_external_calls_make_no_edge(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text(
        "import json\n\n\nclass Thing:\n    def __init__(self):\n        self.x = 1\n\n\n"
        "def make():\n    json.dumps({})\n    return Thing()\n",
        encoding="utf-8",
    )
    assert (
        main(["--repo-root", str(tmp_path), "build", "--no-summaries", "--no-index"])
        == 0
    )
    capsys.readouterr()
    graph = load_code_graph(tmp_path).graph
    targets = {e.target: e.basis for e in graph.out_edges["python:pkg/mod.py::make"]}
    assert targets == {
        "python:pkg/mod.py::Thing": "local",
        "python:pkg/mod.py::Thing.__init__": "constructor",
    }
    external = [
        u.name for u in graph.unresolved["python:pkg/mod.py::make"] if u.external
    ]
    assert external == ["json.dumps"]


def test_unknown_extra_edge_and_node_fields_are_ignored() -> None:
    graph = CodeGraph.from_symbol_graph(
        {
            "nodes": {
                "m": {"kind": "module", "path": "m.py", "start_line": 1, "flows": []},
                "python:m.py::a": {
                    "kind": "function",
                    "path": "m.py",
                    "start_line": 1,
                    "end_line": 2,
                },
                "python:m.py::b": {
                    "kind": "function",
                    "path": "m.py",
                    "start_line": 3,
                    "end_line": 4,
                },
            },
            "edges": [
                {
                    "source": "python:m.py::a",
                    "target": "python:m.py::b",
                    "type": "calls",
                    "dst_name": "b",
                    "resolution": "CONFIDENT",
                    "provenance": "runtime",
                },
                {"type": "flows", "source": "x", "target": "y", "anything": 1},
            ],
        }
    ).finalize()
    assert [e.target for e in graph.out_edges["python:m.py::a"]] == ["python:m.py::b"]


def test_edges_report_static_provenance_and_tolerate_its_absence(repo: Path) -> None:
    """symbol_graph v1 edges carry no ``provenance``; every loaded edge reads as static."""
    data = json.loads(
        (repo / ".repo_wiki" / "generated" / "symbol_graph.json").read_text("utf-8")
    )
    assert all("provenance" not in edge for edge in data["edges"])
    graph = load_code_graph(repo).graph
    edge = next(e for e in graph.in_edges[LEAF] if e.source == MIDDLE)
    assert edge.provenance == "static"
    assert edge.to_dict()["provenance"] == "static"


# ---------------------------------------------------------------------- lookup


def test_symbol_lookup_accepts_id_path_dotted_qualname_and_bare_name(
    repo: Path,
) -> None:
    graph = load_code_graph(repo).graph
    for query in (
        "python:pkg/core.py::Store.save",
        "pkg/core.py::Store.save",
        "pkg.core.Store.save",
        "Store.save",
        "core.Store.save",
    ):
        assert resolve_symbol(graph, query) == "python:pkg/core.py::Store.save", query
    assert resolve_symbol(graph, "leaf") == LEAF
    assert resolve_symbol(graph, "pkg.service") == "pkg.service"


def test_ambiguous_symbol_lists_candidates_and_exits_4(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    graph = load_code_graph(repo).graph
    with pytest.raises(SymbolLookupError) as info:
        resolve_symbol(graph, "parse")
    assert info.value.code == "ambiguous_symbol"
    assert ids(info.value.candidates) == [
        "python:other/helpers.py::parse",
        "python:pkg/core.py::parse",
    ]

    code, payload = run_json(repo, capsys, "impact", "parse")
    assert code == 4
    assert payload["schema"] == "repo-wiki/error/v1"
    assert payload["error"]["code"] == "ambiguous_symbol"
    assert len(payload["error"]["candidates"]) == 2


def test_unknown_symbol_exits_4(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, payload = run_json(repo, capsys, "context", "does_not_exist")
    assert code == 4
    assert payload["error"]["code"] == "unknown_symbol"
    assert payload["error"]["candidates"] == []


# --------------------------------------------------------------------- context


def test_context_reports_definition_callers_callees_and_module(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload = run_json(repo, capsys, "context", "middle")
    assert code == 0
    symbol = payload["symbol"]
    assert symbol["id"] == MIDDLE
    assert (symbol["path"], symbol["start_line"], symbol["end_line"]) == (
        "pkg/core.py",
        9,
        10,
    )
    assert symbol["signature"] == "def middle(value)"
    assert symbol["dotted_name"] == "pkg.core.middle"
    assert ids(payload["callers"]["confident"]) == ["python:pkg/service.py::run"]
    assert ids(payload["callers"]["possible"]) == ["python:other/helpers.py::stray"]
    assert payload["callers"]["possible"][0]["edge"]["resolution"] == HEURISTIC
    assert ids(payload["callees"]["confident"]) == [LEAF]
    assert payload["module"]["importers"] == ["pkg.service", "tests.test_core"]
    assert payload["resolution_counts"]["callers"] == {"CONFIDENT": 1, "HEURISTIC": 1}


def test_context_docstring_first_line_and_class_members(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, leaf = run_json(repo, capsys, "context", "leaf")
    assert leaf["symbol"]["docstring"] == "Return the value doubled."
    _, store = run_json(repo, capsys, "context", "Store")
    assert store["members"] == [
        "python:pkg/core.py::Store._write",
        "python:pkg/core.py::Store.save",
    ]
    assert ids(store["callers"]["confident"]) == ["python:pkg/service.py::persist"]


def test_context_text_output_marks_possible_links(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--repo-root", str(repo), "context", "middle"]) == 0
    out = capsys.readouterr().out
    assert "Callers: 1 confident, 1 possible" in out
    assert "? python:other/helpers.py::stray" in out
    assert "[HEURISTIC name]" in out


# ---------------------------------------------------------------------- impact


def _level(payload: dict, depth: int) -> dict:
    return next(level for level in payload["levels"] if level["depth"] == depth)


def test_upstream_impact_groups_dependents_by_depth(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload = run_json(repo, capsys, "impact", "leaf")
    assert code == 0
    assert payload["direction"] == "upstream" and payload["depth"] == 3
    d1, d2, d3 = (_level(payload, n) for n in (1, 2, 3))
    assert d1["label"] == "will break"
    assert d2["label"] == "likely affected"
    assert d3["label"] == "may need testing"
    assert ids(d1["confident"]) == [
        "python:pkg/core.py::Store._write",
        MIDDLE,
        "python:pkg/service.py::via_module",
        "python:tests/test_core.py::test_leaf",
    ]
    assert ids(d2["confident"]) == [
        "python:pkg/core.py::Store.save",
        "python:pkg/service.py::run",
    ]
    assert ids(d3["confident"]) == [
        "python:pkg/api.py::public_entry",
        "python:pkg/service.py::persist",
    ]
    persist = d3["confident"][1]
    assert persist["edge"]["basis"] == "receiver"
    assert persist["edge"]["provenance"] == "inferred"
    assert payload["affected_files"] == ["pkg/api.py", "pkg/core.py", "pkg/service.py"]
    assert payload["affected_test_files"] == ["tests/test_core.py"]


def test_heuristic_links_are_listed_apart_and_never_counted(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, payload = run_json(repo, capsys, "impact", "leaf")
    assert ids(_level(payload, 2)["possible"]) == ["python:other/helpers.py::stray"]
    assert ids(_level(payload, 3)["possible"]) == ["python:pkg/service.py::persist_any"]
    persist = _level(payload, 3)["possible"][0]
    assert persist["edge"]["resolution"] == HEURISTIC
    assert persist["edge"]["basis"] == "attribute"
    assert persist["edge"]["provenance"] == "static"
    assert persist["edge"]["candidates"] == [
        "python:other/helpers.py::Archive.save",
        "python:pkg/core.py::Store.save",
    ]
    assert payload["possible_files"] == ["other/helpers.py"]
    assert payload["summary"]["confident"] == 8
    assert payload["summary"]["possible"] == 2
    assert payload["summary"]["d1_confident"] == 3  # tests never count

    _, save = run_json(repo, capsys, "impact", "Store.save")
    assert ids(_level(save, 1)["confident"]) == ["python:pkg/service.py::persist"]
    assert ids(_level(save, 1)["possible"]) == ["python:pkg/service.py::persist_any"]


def test_depth_and_downstream_direction(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, deep = run_json(repo, capsys, "impact", "leaf", "--depth", "4")
    assert ids(_level(deep, 4)["confident"]) == ["python:pkg/cli.py::main"]
    assert _level(deep, 4)["label"] == "may need testing"

    _, down = run_json(repo, capsys, "impact", "main", "--direction", "downstream")
    assert down["summary"]["risk"] is None
    assert [ids(_level(down, n)["confident"]) for n in (1, 2, 3)] == [
        ["python:pkg/api.py::public_entry"],
        ["python:pkg/service.py::run"],
        [MIDDLE],
    ]
    assert _level(down, 1)["label"] == "direct dependency"

    code = main(["--repo-root", str(repo), "impact", "leaf", "--depth", "0"])
    assert code == 2


def test_exclude_tests_drops_test_code_from_the_walk(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, payload = run_json(repo, capsys, "impact", "leaf", "--exclude-tests")
    assert payload["include_tests"] is False
    assert "python:tests/test_core.py::test_leaf" not in ids(
        _level(payload, 1)["confident"]
    )
    assert payload["affected_test_files"] == []


def test_module_impact_walks_importers(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, payload = run_json(repo, capsys, "impact", "pkg.core")
    assert ids(_level(payload, 1)["confident"]) == ["pkg.service", "tests.test_core"]
    assert ids(_level(payload, 2)["confident"]) == ["pkg.api"]


# ------------------------------------------------------------------------ risk


def test_risk_table_levels_and_public_entry_bump() -> None:
    assert [row[0] for row in RISK_THRESHOLDS] == ["CRITICAL", "HIGH", "MEDIUM"]
    assert risk_level(0, 0, False) == "LOW"
    assert risk_level(2, 2, False) == "LOW"
    assert risk_level(3, 0, False) == "MEDIUM"
    assert risk_level(0, 3, False) == "MEDIUM"
    assert risk_level(10, 0, False) == "HIGH"
    assert risk_level(0, 6, False) == "HIGH"
    assert risk_level(25, 0, False) == "CRITICAL"
    assert risk_level(0, 12, False) == "CRITICAL"
    # A public entry point raises one step, but never to CRITICAL on its own.
    assert risk_level(0, 0, True) == "MEDIUM"
    assert risk_level(3, 0, True) == "HIGH"
    assert risk_level(10, 0, True) == PUBLIC_ENTRY_CAP == "HIGH"
    assert risk_level(25, 0, True) == "CRITICAL"


def test_risk_on_the_fixture(repo: Path) -> None:
    graph = load_code_graph(repo).graph
    leaf = build_impact(graph, LEAF)["summary"]
    # 3 direct non-test dependents -> MEDIUM, public_entry reached -> HIGH.
    assert (leaf["risk"], leaf["d1_confident"], leaf["modules_reached"]) == (
        "HIGH",
        3,
        2,
    )
    assert leaf["public_entry_points"] == ["python:pkg/api.py::public_entry"]
    stray = build_impact(graph, "python:other/helpers.py::stray")["summary"]
    assert stray["risk"] == "LOW"
    entry = build_impact(graph, "python:pkg/api.py::public_entry")["summary"]
    assert entry["risk"] == "MEDIUM"  # LOW counts, itself exported
    assert graph.public_entry_kind("python:pkg/cli.py::main") == "cli"


def test_test_paths() -> None:
    assert is_test_path("tests/test_core.py")
    assert is_test_path("pkg/test_x.py")
    assert is_test_path("pkg/x_test.py")
    assert is_test_path("conftest.py")
    assert not is_test_path("pkg/testing_tools.py")


# -------------------------------------------------------------------- freshness


def _touch_later(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    later = time.time() + 5
    os.utime(path, (later, later))


def test_missing_graph_exits_3_with_rebuild_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    copy_fixture(FIXTURES / "intel_repo", tmp_path)
    code, payload = run_json(tmp_path, capsys, "context", "leaf")
    assert code == 3
    assert payload["error"]["code"] == "graph_missing"
    assert (
        "build --changed-only --no-summaries --no-index" in payload["error"]["message"]
    )


def test_stale_graph_is_an_error_unless_allowed(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    core = repo / "pkg" / "core.py"
    _touch_later(
        core, core.read_text(encoding="utf-8") + "\n\ndef extra():\n    return 1\n"
    )
    _touch_later(repo / "pkg" / "new_mod.py", "def fresh():\n    return 2\n")
    code, payload = run_json(repo, capsys, "impact", "leaf")
    assert code == 3
    error = payload["error"]
    assert error["code"] == "graph_stale"
    assert error["details"]["changed"] == ["pkg/core.py"]
    assert error["details"]["added"] == ["pkg/new_mod.py"]
    assert "--allow-stale" in error["message"]
    with pytest.raises(GraphUnavailableError):
        load_code_graph(repo)

    code, payload = run_json(repo, capsys, "impact", "leaf", "--allow-stale")
    assert code == 0
    assert payload["graph"]["stale"] is True

    assert (
        main(
            [
                "--repo-root",
                str(repo),
                "build",
                "--changed-only",
                "--no-summaries",
                "--no-index",
            ]
        )
        == 0
    )
    capsys.readouterr()
    code, payload = run_json(repo, capsys, "impact", "leaf")
    assert code == 0 and payload["graph"]["stale"] is False


def test_touched_but_identical_file_is_not_stale(repo: Path) -> None:
    core = repo / "pkg" / "core.py"
    _touch_later(core, core.read_text(encoding="utf-8"))
    assert load_code_graph(repo).freshness.stale is False


def test_deleted_source_is_stale(repo: Path) -> None:
    (repo / "pkg" / "cli.py").unlink()
    with pytest.raises(GraphUnavailableError) as info:
        load_code_graph(repo)
    assert info.value.details["removed"] == ["pkg/cli.py"]


# ------------------------------------------------------------------ JSON shapes


LINK_KEYS = {
    "id",
    "kind",
    "name",
    "qualname",
    "path",
    "start_line",
    "end_line",
    "module",
    "is_test",
    "public_entry",
    "edge",
}


def test_context_json_shape_is_stable(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, payload = run_json(repo, capsys, "context", "middle")
    assert set(payload) == {
        "schema",
        "graph",
        "symbol",
        "callers",
        "callees",
        "unresolved_calls",
        "external_calls",
        "bases",
        "subclasses",
        "members",
        "module",
        "resolution_counts",
        "flows",
    }
    assert payload["schema"] == "repo-wiki/context/v1"
    assert set(payload["symbol"]) == (LINK_KEYS - {"edge"}) | {
        "signature",
        "docstring",
        "dotted_name",
        "parent",
    }
    assert set(payload["callers"]) == {"confident", "possible"}
    assert set(payload["callers"]["confident"][0]) == LINK_KEYS
    assert set(payload["callers"]["confident"][0]["edge"]) == {
        "type",
        "resolution",
        "basis",
        "name",
        "provenance",
    }
    assert set(payload["module"]) == {
        "id",
        "path",
        "imports",
        "external_imports",
        "importers",
    }
    assert set(payload["graph"]) == {
        "path",
        "built_commit",
        "stale",
        "changed",
        "added",
        "removed",
    }
    assert set(payload["resolution_counts"]["callees"]) == {
        "CONFIDENT",
        "HEURISTIC",
        "UNRESOLVED",
        "EXTERNAL",
    }


def test_impact_json_shape_is_stable(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, payload = run_json(repo, capsys, "impact", "leaf")
    assert set(payload) == {
        "schema",
        "graph",
        "target",
        "direction",
        "depth",
        "include_tests",
        "levels",
        "affected_files",
        "affected_test_files",
        "possible_files",
        "summary",
        "flows",
    }
    assert payload["schema"] == "repo-wiki/impact/v1"
    assert set(payload["levels"][0]) == {"depth", "label", "confident", "possible"}
    assert set(payload["levels"][0]["confident"][0]) == LINK_KEYS | {"depth", "via"}
    assert set(payload["summary"]) == {
        "confident",
        "possible",
        "risk",
        "risk_with_possible",
        "d1_confident",
        "modules_reached",
        "public_entry_points",
        "risk_reasons",
    }


# ------------------------------------------------------- function-level aliases


ALIAS_FILES = {
    "pkg/__init__.py": "",
    "pkg/target.py": (
        "def main():\n    return 1\n\n\ndef other():\n    return 2\n\n\n"
        "class Tool:\n    def run(self):\n        return 3\n"
    ),
    "pkg/caller.py": """
import os.path


def run_cli():
    return "module-level, shadowed inside bare()"


def bare():
    from pkg.target import main as run_cli

    return run_cli()


def dotted():
    import pkg.target as target_module

    return target_module.other()


def from_module():
    from pkg import target as t

    return t.main()


def relative():
    from .target import main as near

    return near()


def external():
    import json as dumper

    return dumper.dumps({})


def missing():
    from pkg.target import gone as ghost

    return ghost()


def outer():
    from pkg.target import other as inherited

    def inner():
        return inherited()

    return inner


def sibling_a():
    from pkg.target import main as only_here

    return only_here()


def sibling_b():
    return only_here()


def not_imported_here():
    return run_cli()


def typed():
    from pkg.target import Tool as Renamed

    tool = Renamed()
    return tool.run()
""",
}
CALLER = "python:pkg/caller.py::"
TARGET = "python:pkg/target.py::"


@pytest.fixture()
def alias_repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    for relative, text in ALIAS_FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    assert (
        main(["--repo-root", str(tmp_path), "build", "--no-summaries", "--no-index"])
        == 0
    )
    capsys.readouterr()
    return tmp_path


def _call_targets(graph, name: str) -> dict[str, tuple[str, str]]:
    return {
        edge.target: (edge.resolution, edge.basis)
        for edge in graph.out_edges.get(f"{CALLER}{name}", [])
        if edge.type == "calls"
    }


@pytest.mark.parametrize(
    ("caller", "target"),
    [
        ("bare", "main"),
        ("dotted", "other"),
        ("from_module", "main"),
        ("relative", "main"),
        ("sibling_a", "main"),
    ],
)
def test_an_alias_resolves_like_a_module_level_import(
    alias_repo: Path, caller: str, target: str
) -> None:
    graph = load_code_graph(alias_repo).graph
    assert _call_targets(graph, caller) == {f"{TARGET}{target}": (CONFIDENT, "import")}


def test_an_alias_shadows_a_module_level_name_only_in_its_own_function(
    alias_repo: Path,
) -> None:
    graph = load_code_graph(alias_repo).graph
    assert f"{CALLER}run_cli" not in _call_targets(graph, "bare")
    assert _call_targets(graph, "not_imported_here") == {
        f"{CALLER}run_cli": (CONFIDENT, "local")
    }


def test_a_nested_function_sees_the_alias_of_its_enclosing_function(
    alias_repo: Path,
) -> None:
    graph = load_code_graph(alias_repo).graph
    assert _call_targets(graph, "outer.inner") == {
        f"{TARGET}other": (CONFIDENT, "import")
    }


def test_an_alias_does_not_leak_to_a_sibling_function(alias_repo: Path) -> None:
    graph = load_code_graph(alias_repo).graph
    assert _call_targets(graph, "sibling_b") == {}
    assert [u.name for u in graph.unresolved[f"{CALLER}sibling_b"]] == ["only_here"]


def test_an_external_or_missing_alias_target_makes_no_edge(alias_repo: Path) -> None:
    graph = load_code_graph(alias_repo).graph
    assert _call_targets(graph, "external") == {}
    assert [(u.name, u.external) for u in graph.unresolved[f"{CALLER}external"]] == [
        ("dumper.dumps", True)
    ]
    assert _call_targets(graph, "missing") == {}
    assert [u.attempted for u in graph.unresolved[f"{CALLER}missing"]] == [
        "pkg.target.gone"
    ]


def test_a_receiver_built_through_an_alias_resolves(alias_repo: Path) -> None:
    graph = load_code_graph(alias_repo).graph
    assert _call_targets(graph, "typed")[f"{TARGET}Tool.run"] == (
        CONFIDENT,
        "receiver",
    )


def test_aliases_are_the_same_from_the_file_and_from_a_fresh_parse(
    alias_repo: Path,
) -> None:
    loaded = load_code_graph(alias_repo).graph
    stored = json.loads(
        (alias_repo / ".repo_wiki/generated/symbol_graph.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["nodes"][f"{CALLER}bare"]["import_aliases"] == {
        "run_cli": "pkg.target.main"
    }
    assert "import_aliases" not in stored["nodes"][f"{CALLER}sibling_b"]
    path = alias_repo / "pkg/caller.py"
    parsed = parse_python_file(
        SourceFile("pkg/caller.py", str(path), "python", path.stat().st_size, "h")
    )
    fresh = CodeGraph.from_symbol_graph(stored)
    fresh.replace_file("pkg/caller.py", parsed)
    fresh.finalize()
    assert fresh.out_edges[f"{CALLER}bare"] == loaded.out_edges[f"{CALLER}bare"]


def test_a_graph_without_the_field_still_loads(alias_repo: Path) -> None:
    stored = json.loads(
        (alias_repo / ".repo_wiki/generated/symbol_graph.json").read_text(
            encoding="utf-8"
        )
    )
    for node in stored["nodes"].values():
        node.pop("import_aliases", None)
    graph = CodeGraph.from_symbol_graph(stored).finalize()
    assert _call_targets(graph, "sibling_a") == {}
