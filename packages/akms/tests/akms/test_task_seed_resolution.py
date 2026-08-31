"""Tests for deterministic exact task-seed resolution."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import networkx as nx
import pytest

from akms.graph.tag_derivation import derive_tags
from akms.task_context.models import RouteRecord, TaskRouteIndex
from akms.task_context.resolve import (
    TaskPathSpec,
    TaskSeeds,
    canonicalize_task_path_specs,
    resolve_task_seeds,
)


def _graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_node(
        "mirror-exact",
        domain="code-mirror",
        source_file="src/solver.py",
    )
    graph.add_node(
        "mirror-prefix-collision",
        domain="code-mirror",
        source_file="src/solver.py.bak",
    )
    graph.add_node(
        "mirror-directory",
        domain="code-mirror",
        source_file="src/pkg/model.py",
    )
    graph.add_node(
        "mirror-glob",
        domain="code-mirror",
        source_file="tests/unit/test_model.py",
    )
    graph.add_node(
        "mirror-changed",
        domain="code-mirror",
        source_file="src/changed.py",
    )
    graph.add_node(
        "mirror-readme",
        domain="code-mirror",
        source_file="README.md",
    )
    graph.add_node(
        "mirror-docs",
        domain="code-mirror",
        source_file="docs/design.rst",
    )
    graph.add_node("route-exact")
    graph.add_node("route-directory")
    graph.add_node("route-glob")
    graph.add_node("route-changed")
    graph.add_node("route-readme")
    graph.add_node("route-docs")
    return graph


def _route_index() -> TaskRouteIndex:
    def record(node_id: str, reason: str) -> tuple[RouteRecord, ...]:
        return (
            RouteRecord(
                node_id=node_id,
                reason=reason,
                provenance="knowledge/task-routes.yaml",
            ),
        )

    return TaskRouteIndex(
        schema_version="v1",
        source_hash="sha256:test",
        by_path={
            "src/solver.py": record("route-exact", "solver implementation route"),
            "src/pkg/model.py": record("route-directory", "package route"),
            "tests/unit/test_model.py": record("route-glob", "unit-test route"),
            "src/changed.py": record("route-changed", "changed-file route"),
            "README.md": record("route-readme", "readme route"),
            "docs/design.rst": record("route-docs", "documentation route"),
        },
    )


@pytest.mark.unit
def test_tagless_code_mirror_selected_by_exact_source_file():
    resolved = resolve_task_seeds(
        _graph(),
        TaskSeeds(scope=("src/solver.py",)),
    )

    assert resolved.exact_mirror_node_ids == ("mirror-exact",)
    assert resolved.reasons["mirror-exact"] == (
        "mirror source_file 'src/solver.py' matched exact scope 'src/solver.py'",
    )


@pytest.mark.unit
def test_exact_directory_glob_and_changed_file_inputs_resolve_nodes():
    resolved = resolve_task_seeds(
        _graph(),
        TaskSeeds(
            scope=(
                "src/pkg/",
                "tests/**/*.py",
            ),
            deliverables=("src/solver.py", "Exact task-seed resolver"),
            changed_files=("src/changed.py",),
        ),
        route_index=_route_index(),
    )

    assert resolved.exact_mirror_node_ids == (
        "mirror-changed",
        "mirror-directory",
        "mirror-exact",
        "mirror-glob",
    )
    assert resolved.required_route_node_ids == (
        "route-changed",
        "route-directory",
        "route-exact",
        "route-glob",
    )
    assert all(resolved.reasons[node_id] for node_id in resolved.all_exact_node_ids)


@pytest.mark.unit
def test_public_path_spec_contract_preserves_resolution_behavior():
    seeds = TaskSeeds(
        scope=("src\\pkg\\", "tests/**/*.py"),
        deliverables=("src/solver.py", "Human-readable deliverable"),
        changed_files=(r"src\literal*.py",),
    )

    assert canonicalize_task_path_specs(seeds) == (
        TaskPathSpec(
            value="src/literal*.py",
            kind="exact",
            source="changed_file",
        ),
        TaskPathSpec(
            value="src/solver.py",
            kind="exact",
            source="deliverable",
        ),
        TaskPathSpec(
            value="src/pkg",
            kind="directory",
            source="scope",
        ),
        TaskPathSpec(
            value="tests/**/*.py",
            kind="glob",
            source="scope",
        ),
    )

    resolved = resolve_task_seeds(_graph(), seeds, route_index=_route_index())
    assert resolved.exact_mirror_node_ids == (
        "mirror-directory",
        "mirror-exact",
        "mirror-glob",
    )
    assert resolved.required_route_node_ids == (
        "route-directory",
        "route-exact",
        "route-glob",
    )


@pytest.mark.unit
def test_prefix_collision_paths_do_not_match():
    resolved = resolve_task_seeds(
        _graph(),
        TaskSeeds(scope=("src/solver.py",)),
        route_index=_route_index(),
    )

    assert "mirror-prefix-collision" not in resolved.exact_mirror_node_ids
    assert resolved.required_route_node_ids == ("route-exact",)


@pytest.mark.unit
def test_empty_and_documentation_only_tasks_return_empty_exact_seeds():
    empty = resolve_task_seeds(_graph(), TaskSeeds(), route_index=_route_index())
    documentation_only = resolve_task_seeds(
        _graph(),
        TaskSeeds(scope=("README.md", "docs/design.rst")),
        route_index=_route_index(),
    )

    for resolved in (empty, documentation_only):
        assert resolved.exact_mirror_node_ids == ()
        assert resolved.required_route_node_ids == ()
        assert resolved.reasons == {}


@pytest.mark.unit
def test_import_and_resolution_do_not_import_litellm_or_attempt_network():
    package_src = Path(__file__).parents[2] / "src"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            (str(package_src), environment.get("PYTHONPATH")),
        )
    )
    script = textwrap.dedent(
        """
        import importlib.abc
        import socket
        import sys

        attempts = []
        original_connect = socket.socket.connect

        def blocked_connect(self, address):
            attempts.append(address)
            raise AssertionError(f"network attempt: {address!r}")

        class BlockLiteLLM(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "litellm" or fullname.startswith("litellm."):
                    raise AssertionError(f"LiteLLM import: {fullname}")
                return None

        socket.socket.connect = blocked_connect
        sys.meta_path.insert(0, BlockLiteLLM())

        import networkx as nx
        from akms.task_context.resolve import TaskSeeds, resolve_task_seeds

        resolved = resolve_task_seeds(nx.DiGraph(), TaskSeeds())
        assert resolved.all_exact_node_ids == ()
        assert "litellm" not in sys.modules
        assert attempts == []
        socket.socket.connect = original_connect
        """
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr


@pytest.mark.unit
def test_advisory_tags_and_reasons_are_deduplicated_and_sorted():
    graph = _graph()
    graph.add_node("concept", title="Plasticity Solver", tags=["solver", "plasticity"])
    seeds = TaskSeeds(
        scope=("src/solver.py", "src/solver.py"),
        advisory_tags=("zeta", "alpha", "alpha"),
    )

    resolved = resolve_task_seeds(graph, seeds)

    assert resolved.advisory_tags == ("alpha", "zeta")
    assert resolved.exact_mirror_node_ids == ("mirror-exact",)
    assert resolved.reasons["mirror-exact"] == (
        "mirror source_file 'src/solver.py' matched exact scope 'src/solver.py'",
    )


@pytest.mark.unit
def test_from_task_preserves_legacy_derive_tags_snapshot():
    graph = nx.DiGraph()
    graph.add_node(
        "alpha",
        title="Alpha Feature",
        tags=["zeta", "alpha"],
        content_ref="src/alpha.py",
    )
    task = {
        "scope": ["src/alpha.py"],
        "title": "Implement alpha feature",
        "objective": "",
        "akms_tags": [],
    }

    legacy = derive_tags(graph, task)
    resolved = resolve_task_seeds(graph, TaskSeeds.from_task(task))

    assert legacy == ["alpha", "zeta"]
    assert list(resolved.advisory_tags) == legacy
