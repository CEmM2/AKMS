"""Static execution flows: entry detection, traversal caps, cycles, determinism, staleness.

The ``flows_repo`` fixture has::

    console script tool (and tool-alias) -> pkg.app.main -> build, middle -> leaf
    pkg/app.py __main__ block            -> main
    cli: cmd_go (set_defaults(func=...)) -> wide -> one..five; hello (@app.command())
    roots: chain_a -> chain_b -> chain_c -> chain_d -> leaf; spin -> loop_a <-> loop_b;
           only_tested (called from tests only)
    stray -> helper (two definitions, never imported: HEURISTIC name only)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from akms.repo_wiki.cli import main
from akms.repo_wiki.code_graph import CodeGraph, load_code_graph
from akms.repo_wiki.config import load_config, validate_config
from akms.repo_wiki.flows import (
    FLOWS_FILE_SCHEMA,
    compute_flows,
    dump_flows,
    flow_id,
    flows_settings,
    load_flows,
    read_console_scripts,
)

from .test_build_render_graph_summary import copy_fixture

FIXTURES = Path(__file__).resolve().parent / "fixtures"
APP = "python:pkg/app.py::"
CORE = "python:pkg/core.py::"


def write_config(repo: Path, text: str) -> None:
    (repo / ".repo_wiki").mkdir(exist_ok=True)
    (repo / ".repo_wiki" / "config.yaml").write_text(text, encoding="utf-8")


def build(repo: Path, capsys: pytest.CaptureFixture[str], *args: str) -> None:
    assert (
        main(["--repo-root", str(repo), "build", "--no-summaries", "--no-index", *args])
        == 0
    )
    capsys.readouterr()


def flows_path(repo: Path) -> Path:
    return repo / ".repo_wiki" / "generated" / "flows.json"


def read_flows(repo: Path) -> dict:
    return json.loads(flows_path(repo).read_text(encoding="utf-8"))


def by_entry(payload: dict) -> dict[str, dict]:
    return {flow["entry"]: flow for flow in payload["flows"]}


def step_ids(flow: dict) -> list[str]:
    return [step["id"] for step in flow["steps"]]


@pytest.fixture()
def repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    copy_fixture(FIXTURES / "flows_repo", tmp_path)
    build(tmp_path, capsys)
    return tmp_path


def recompute(repo: Path, **overrides: object) -> dict:
    config = load_config(repo)
    settings = flows_settings(config)
    for key, value in overrides.items():
        if key == "entries":
            settings["entries"] = {**settings["entries"], **value}  # type: ignore[dict-item]
        else:
            settings[key] = value
    loaded = load_code_graph(repo, config=config)
    scripts = read_console_scripts(repo, loaded.graph.paths())
    return compute_flows(loaded.graph, settings, scripts, graph_sha256=None)


# ------------------------------------------------------------------ entries


def test_build_writes_flows_next_to_the_graph(repo: Path) -> None:
    payload = read_flows(repo)
    assert payload["schema"] == FLOWS_FILE_SCHEMA
    assert payload["graph_sha256"].startswith("sha256:")
    kinds = {flow["entry"]: flow["kind"] for flow in payload["flows"]}
    assert kinds == {
        APP + "main": "console_script",
        "pkg.app": "script",
        APP + "cmd_go": "cli",
        APP + "hello": "cli",
        CORE + "chain_a": "root",
        CORE + "only_tested": "root",
        CORE + "spin": "root",
    }
    assert payload["summary"]["by_kind"] == {
        "cli": 2,
        "console_script": 1,
        "root": 3,
        "script": 1,
    }


def test_console_script_entry_keeps_its_name_and_aliases(repo: Path) -> None:
    flow = by_entry(read_flows(repo))[APP + "main"]
    assert flow["name"] == "tool"
    assert flow["aliases"] == ["tool-alias"]
    assert flow["detail"] == "pkg.app:main"
    assert flow["id"] == flow_id(APP + "main")
    assert step_ids(flow) == [
        APP + "main",
        APP + "build",
        CORE + "middle",
        CORE + "leaf",
    ]
    assert flow["terminals"] == [APP + "build", CORE + "leaf"]
    assert flow["truncated"] is False


def test_main_block_flow_starts_at_the_module(repo: Path) -> None:
    flow = by_entry(read_flows(repo))["pkg.app"]
    assert flow["name"] == "pkg.app:__main__"
    assert flow["steps"][0] == {"id": "pkg.app", "depth": 0, "via": None}
    assert flow["steps"][1]["id"] == APP + "main"
    assert flow["steps"][1]["via"] == "pkg.app"


def test_cli_entries_from_decorators_and_set_defaults(repo: Path) -> None:
    flows = by_entry(read_flows(repo))
    assert flows[APP + "hello"]["detail"] == "@app.command"
    assert flows[APP + "cmd_go"]["detail"] == "set_defaults(func=cmd_go)"


def test_roots_skip_private_called_and_callee_less_symbols(repo: Path) -> None:
    roots = {f["entry"] for f in read_flows(repo)["flows"] if f["kind"] == "root"}
    assert CORE + "_private_root" not in roots  # private
    assert CORE + "middle" not in roots  # called
    assert CORE + "two" not in roots  # calls nothing
    assert "python:pkg/loose.py::stray" not in roots  # only a HEURISTIC callee
    assert CORE + "only_tested" in roots  # callers in tests do not count


def test_tests_are_entries_only_when_enabled(repo: Path) -> None:
    assert not [f for f in read_flows(repo)["flows"] if f["kind"] == "test"]
    payload = recompute(repo, entries={"tests": True})
    tests = sorted(f["entry"] for f in payload["flows"] if f["kind"] == "test")
    assert tests == [
        "python:tests/test_core.py::TestMiddle.test_middle",
        "python:tests/test_core.py::test_leaf",
        "python:tests/test_core.py::test_only",
    ]


def test_entry_rules_can_be_switched_off(repo: Path) -> None:
    payload = recompute(
        repo,
        entries={"roots": False, "cli": False, "scripts": False},
    )
    assert [f["kind"] for f in payload["flows"]] == ["console_script"]
    custom = recompute(repo, cli_decorators=["nothing.*"])
    assert by_entry(custom)[APP + "hello"]["kind"] == "root"  # uncalled, so a root


# ---------------------------------------------------------------- traversal


def test_depth_cap_marks_the_cut_step(repo: Path) -> None:
    flow = by_entry(recompute(repo, max_depth=2))[CORE + "chain_a"]
    assert step_ids(flow) == [CORE + "chain_a", CORE + "chain_b", CORE + "chain_c"]
    cut = flow["steps"][-1]
    assert (cut["cut"], cut["omitted"]) == ("depth", 1)
    assert flow["truncated"] and flow["truncated_reasons"] == ["depth"]


def test_fanout_cap_keeps_branching_callees_first(repo: Path) -> None:
    flow = by_entry(recompute(repo, max_fanout=2))[APP + "cmd_go"]
    wide = next(s for s in flow["steps"] if s["id"] == CORE + "wide")
    assert wide["cut"] == "fanout" and wide["omitted"] == 3
    assert wide["omitted_ids"] == [CORE + "four", CORE + "three", CORE + "two"]
    followed = [s["id"] for s in flow["steps"] if s.get("via") == CORE + "wide"]
    assert followed == [CORE + "five", CORE + "one"]  # one calls on; five is first
    assert flow["truncated_reasons"] == ["fanout"]


def test_step_cap_stops_the_whole_flow(repo: Path) -> None:
    flow = by_entry(recompute(repo, max_steps=3))[CORE + "chain_a"]
    assert len(flow["steps"]) == 3
    assert flow["steps"][-1]["cut"] == "steps"
    assert flow["truncated_reasons"] == ["steps"]


def test_cycles_are_recorded_and_not_followed_twice(repo: Path) -> None:
    flow = by_entry(read_flows(repo))[CORE + "spin"]
    assert step_ids(flow) == [CORE + "spin", CORE + "loop_a", CORE + "loop_b"]
    assert flow["cycles"] == [[CORE + "loop_b", CORE + "loop_a"]]
    assert flow["terminals"] == []
    assert flow["truncated"] is False


def test_heuristic_links_are_opt_in_and_flagged(repo: Path) -> None:
    assert all(f["heuristic_steps"] == 0 for f in read_flows(repo)["flows"])
    flow = by_entry(recompute(repo, include_heuristic=True))[
        "python:pkg/loose.py::stray"
    ]
    assert flow["kind"] == "root"
    heuristic = [s for s in flow["steps"] if s.get("resolution") == "HEURISTIC"]
    assert [s["id"] for s in heuristic] == [
        "python:pkg/helpers_a.py::helper",
        "python:pkg/helpers_b.py::helper",
    ]
    assert flow["heuristic_steps"] == 2
    assert {s["basis"] for s in heuristic} == {"name"}


def test_steps_carry_resolution_basis_and_provenance(repo: Path) -> None:
    flow = by_entry(read_flows(repo))[APP + "main"]
    middle = next(s for s in flow["steps"] if s["id"] == CORE + "middle")
    assert middle == {
        "id": CORE + "middle",
        "depth": 1,
        "via": APP + "main",
        "resolution": "CONFIDENT",
        "basis": "import",
        "provenance": "static",
    }


def test_max_flows_keeps_named_entries_and_counts_the_rest(repo: Path) -> None:
    payload = recompute(repo, max_flows=5)
    kinds = [f["kind"] for f in payload["flows"]]
    assert kinds.count("root") == 1 and len(kinds) == 5
    assert payload["summary"]["omitted_flows"] == {"root": 2}
    # Opt-in tests rank last, so turning them on never pushes out a default flow.
    crowded = recompute(repo, max_flows=7, entries={"tests": True})
    assert "test" not in [f["kind"] for f in crowded["flows"]]
    assert crowded["summary"]["omitted_flows"] == {"test": 3}


# -------------------------------------------------------------- determinism


def test_flows_file_is_byte_identical_across_builds(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first = flows_path(repo).read_bytes()
    build(repo, capsys, "--force")
    assert flows_path(repo).read_bytes() == first
    build(repo, capsys, "--changed-only")
    assert flows_path(repo).read_bytes() == first
    payload = json.loads(first)
    assert dump_flows(payload).encode("utf-8") == first
    assert first.endswith(b"}\n")


def test_flows_are_a_pure_function_of_the_graph(repo: Path) -> None:
    data = json.loads(
        (repo / ".repo_wiki/generated/symbol_graph.json").read_text("utf-8")
    )
    settings = flows_settings(load_config(repo))
    scripts = read_console_scripts(repo, CodeGraph.from_symbol_graph(data).paths())
    one = compute_flows(
        CodeGraph.from_symbol_graph(data), settings, scripts, graph_sha256="x"
    )
    two = compute_flows(
        CodeGraph.from_symbol_graph(data), settings, scripts, graph_sha256="x"
    )
    assert dump_flows(one) == dump_flows(two)


def test_graph_without_optional_fields_still_yields_flows(repo: Path) -> None:
    """A v1 graph from before provenance and the entry facts: roots still work."""
    data = json.loads(
        (repo / ".repo_wiki/generated/symbol_graph.json").read_text("utf-8")
    )
    for node in data["nodes"].values():
        for key in ("main_calls", "cli_handlers", "decorators", "receivers"):
            node.pop(key, None)
    for edge in data["edges"]:
        edge.pop("provenance", None)
    payload = compute_flows(
        CodeGraph.from_symbol_graph(data),
        flows_settings(load_config(repo)),
        [],
        graph_sha256=None,
    )
    kinds = {f["entry"]: f["kind"] for f in payload["flows"]}
    assert "pkg.app" not in kinds  # no main_calls recorded
    assert kinds[APP + "main"] == "root"
    assert all(
        s.get("provenance", "static") == "static"
        for f in payload["flows"]
        for s in f["steps"]
    )


# ---------------------------------------------------------------- staleness


def _index(repo: Path):
    config = load_config(repo)
    loaded = load_code_graph(repo, config=config)
    return load_flows(repo, config, loaded.graph, loaded.path)


def test_reader_uses_the_file_when_it_matches(repo: Path) -> None:
    index = _index(repo)
    assert index.source == "file" and index.reason is None


def test_reader_recomputes_when_graph_hash_differs(repo: Path) -> None:
    payload = read_flows(repo)
    payload["graph_sha256"] = "sha256:" + "0" * 64
    flows_path(repo).write_text(json.dumps(payload), encoding="utf-8")
    index = _index(repo)
    assert index.source == "computed"
    assert "graph changed" in str(index.reason)
    assert len(index.flows) == len(payload["flows"])
    # Nothing is written by a reader.
    assert json.loads(flows_path(repo).read_text("utf-8"))["graph_sha256"].endswith(
        "0" * 64
    )


def test_reader_recomputes_when_settings_change(repo: Path) -> None:
    write_config(repo, "flows:\n  max_depth: 1\n")
    index = _index(repo)
    assert index.source == "computed"
    assert "settings" in str(index.reason)
    assert all(f["depth"] <= 1 for f in index.flows)


def test_reader_recomputes_when_the_file_is_missing_or_broken(repo: Path) -> None:
    flows_path(repo).write_text("{not json", encoding="utf-8")
    assert _index(repo).reason == "unreadable"
    flows_path(repo).unlink()
    index = _index(repo)
    assert (index.source, index.reason) == ("computed", "missing")


def test_disabled_flows_are_not_written(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_config(repo, "flows:\n  enabled: false\n")
    build(repo, capsys)
    assert not flows_path(repo).exists()


# ------------------------------------------------------------------- config


@pytest.mark.parametrize(
    ("flows", "message"),
    [
        ({"max_depth": 0}, "flows.max_depth"),
        ({"max_steps": "many"}, "flows.max_steps"),
        ({"max_fanout": True}, "flows.max_fanout"),
        ({"include_heuristic": "yes"}, "flows.include_heuristic"),
        ({"entries": {"everything": True}}, "unknown rule"),
        ({"entries": {"tests": 1}}, "flows.entries.tests"),
        ({"cli_decorators": "*.command"}, "flows.cli_decorators"),
        ({"surprise": 1}, "unknown key"),
    ],
)
def test_flows_config_is_validated(tmp_path: Path, flows: dict, message: str) -> None:
    config = load_config(tmp_path)
    config["flows"] = {**config["flows"], **flows}  # type: ignore[dict-item]
    with pytest.raises(ValueError, match=message):
        validate_config(config)
