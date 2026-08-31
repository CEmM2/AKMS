"""Tests for deterministic task route-index parsing and validation."""

from __future__ import annotations

import json

import networkx as nx
import pytest

from akms.task_context.models import TASK_ROUTE_INDEX_SCHEMA_VERSION
from akms.task_context.routes import (
    RouteIndexValidationError,
    normalize_repository_path,
    parse_route_index,
    validate_route_index_nodes,
)


def _route(
    node_id: str,
    *,
    reason: str = "exact source route",
    provenance: str = "knowledge/task-routes.yaml",
) -> dict[str, str]:
    return {
        "node_id": node_id,
        "reason": reason,
        "provenance": provenance,
    }


def _index_data() -> dict[str, object]:
    return {
        "schema_version": TASK_ROUTE_INDEX_SCHEMA_VERSION,
        "source_hash": "sha256:fixture",
        "by_path": {
            "src/solver.py": [
                _route("solver-basics"),
                _route("solver-pitfalls", reason="known failure mode"),
            ],
        },
        "by_symbol": {
            "Solver.step": [
                _route("solver-update", provenance="knowledge/symbol-routes.yaml"),
            ],
        },
    }


@pytest.mark.unit
def test_valid_route_index_parses_and_has_stable_canonical_form():
    index = parse_route_index(_index_data())

    assert index.schema_version == TASK_ROUTE_INDEX_SCHEMA_VERSION
    assert list(index.by_path) == ["src/solver.py"]
    assert list(index.by_symbol) == ["Solver.step"]
    assert index.canonical_data() == json.loads(index.canonical_json())
    assert (
        index.canonical_json()
        == parse_route_index(index.canonical_data()).canonical_json()
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("/absolute/source.py", "invalid_path"),
        ("../outside.py", "invalid_path"),
        ("C:\\repo\\source.py", "invalid_path"),
        ("", "invalid_path"),
    ],
)
def test_malformed_paths_fail_with_located_errors(path: str, code: str):
    data = _index_data()
    data["by_path"] = {path: [_route("solver-basics")]}

    with pytest.raises(RouteIndexValidationError) as exc_info:
        parse_route_index(data)

    issue = exc_info.value.issues[0]
    assert issue.code == code
    assert issue.location[:1] == ("by_path",)
    assert path in issue.location


@pytest.mark.unit
def test_duplicate_and_conflicting_records_fail_with_route_locations():
    duplicate = _index_data()
    duplicate["by_path"] = {
        "src/solver.py": [_route("solver-basics"), _route("solver-basics")]
    }
    with pytest.raises(RouteIndexValidationError) as duplicate_error:
        parse_route_index(duplicate)

    assert duplicate_error.value.issues[0].code == "duplicate_node_record"
    assert duplicate_error.value.issues[0].location == (
        "by_path",
        "src/solver.py",
        1,
    )

    conflicting = _index_data()
    conflicting["by_symbol"] = {
        "Solver.step": [
            _route("solver-update"),
            _route("solver-update", reason="different reason"),
        ]
    }
    with pytest.raises(RouteIndexValidationError) as conflict_error:
        parse_route_index(conflicting)

    assert conflict_error.value.issues[0].code == "conflicting_node_record"
    assert conflict_error.value.issues[0].location == (
        "by_symbol",
        "Solver.step",
        1,
    )


@pytest.mark.unit
def test_graph_bound_validation_rejects_missing_nodes_with_locations():
    index = parse_route_index(_index_data())
    graph = nx.DiGraph()
    graph.add_nodes_from(["solver-basics", "solver-update"])

    with pytest.raises(RouteIndexValidationError) as exc_info:
        validate_route_index_nodes(index, graph)

    assert exc_info.value.errors() == [
        {
            "code": "missing_graph_node",
            "location": ["by_path", "src/solver.py", 1, "node_id"],
            "message": "Route references nonexistent graph node 'solver-pitfalls'",
            "node_id": "solver-pitfalls",
        }
    ]


@pytest.mark.unit
def test_windows_paths_normalize_to_repository_relative_posix_paths():
    data = _index_data()
    data["by_path"] = {
        ".\\src\\solver.py": [_route("solver-basics")],
        "tests\\unit\\test_solver.py": [_route("solver-tests")],
    }

    index = parse_route_index(data)

    assert list(index.by_path) == ["src/solver.py", "tests/unit/test_solver.py"]
    assert normalize_repository_path("src\\solver.py") == "src/solver.py"


@pytest.mark.unit
def test_input_ordering_does_not_change_canonical_output():
    first = _index_data()
    first["by_path"] = {
        "src/z.py": [_route("z-node"), _route("a-node")],
        "src/a.py": [_route("c-node")],
    }
    first["by_symbol"] = {
        "Z.run": [_route("z-symbol")],
        "A.run": [_route("a-symbol")],
    }

    second = _index_data()
    second["by_path"] = {
        "src/a.py": [_route("c-node")],
        "src\\z.py": [_route("a-node"), _route("z-node")],
    }
    second["by_symbol"] = {
        "A.run": [_route("a-symbol")],
        "Z.run": [_route("z-symbol")],
    }

    assert (
        parse_route_index(first).canonical_json()
        == parse_route_index(second).canonical_json()
    )


@pytest.mark.unit
@pytest.mark.parametrize("suffix", [".json", ".yaml"])
def test_file_parser_rejects_duplicate_mapping_keys(tmp_path, suffix: str):
    if suffix == ".json":
        content = """{
  "schema_version": "v1",
  "source_hash": "sha256:duplicate-key",
  "by_path": {
    "src/solver.py": [{"node_id": "first", "reason": "first", "provenance": "a"}],
    "src/solver.py": [{"node_id": "second", "reason": "second", "provenance": "b"}]
  }
}"""
    else:
        content = """\
schema_version: v1
source_hash: sha256:duplicate-key
by_path:
  src/solver.py:
    - {node_id: first, reason: first, provenance: a}
  src/solver.py:
    - {node_id: second, reason: second, provenance: b}
"""
    route_file = tmp_path / f"routes{suffix}"
    route_file.write_text(content, encoding="utf-8")

    with pytest.raises(RouteIndexValidationError) as exc_info:
        parse_route_index(route_file)

    assert exc_info.value.issues[0].code == "duplicate_mapping_key"
    assert "src/solver.py" in exc_info.value.issues[0].message


@pytest.mark.unit
def test_yaml_null_path_key_returns_structured_located_error(tmp_path):
    route_file = tmp_path / "routes.yaml"
    route_file.write_text(
        """\
schema_version: v1
source_hash: sha256:null-key
by_path:
  null:
    - {node_id: solver-basics, reason: exact, provenance: fixture}
""",
        encoding="utf-8",
    )

    with pytest.raises(RouteIndexValidationError) as exc_info:
        parse_route_index(route_file)

    assert exc_info.value.issues[0].code == "invalid_path"
    assert exc_info.value.issues[0].location == ("by_path", "<null>")


@pytest.mark.unit
def test_graph_validation_rejects_string_as_node_collection():
    data = _index_data()
    data["by_path"] = {"src/solver.py": [_route("solver-basics")]}
    data["by_symbol"] = {}
    index = parse_route_index(data)

    with pytest.raises(TypeError, match="not a string"):
        validate_route_index_nodes(index, "prefix-solver-basics-suffix")


@pytest.mark.unit
@pytest.mark.parametrize("nonfinite", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_provenance_is_rejected_before_canonical_json(nonfinite: float):
    data = _index_data()
    data["by_path"] = {
        "src/solver.py": [
            {
                "node_id": "solver-basics",
                "reason": "exact",
                "provenance": {"generator": {"score": nonfinite}},
            }
        ]
    }

    with pytest.raises(RouteIndexValidationError) as exc_info:
        parse_route_index(data)

    issue = exc_info.value.issues[0]
    assert issue.code == "schema_validation"
    assert issue.location[-1] == "provenance"
    assert "finite" in issue.message
