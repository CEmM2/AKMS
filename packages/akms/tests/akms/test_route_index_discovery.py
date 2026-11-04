"""Tests for task route-index discovery shared by review and ``akms status``."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from akms.task_context.routes import (
    TASK_ROUTE_INDEX_CANDIDATES,
    find_task_route_index,
)

# The candidate list as it stood before the failure-memory default was added.
# Every one of these must keep its position, so a repository resolves to the
# same file it resolved to before.
_EARLIER_CANDIDATES = tuple(
    f"{dirname}/{tail}"
    for dirname in (".knowledge", "knowledge")
    for tail in (
        "task-routes.yaml",
        "task-routes.yml",
        "task-routes.json",
        "graph/task-routes.yaml",
        "graph/task-routes.yml",
        "graph/task-routes.json",
        "routes/task-routes.yaml",
        "routes/task-routes.json",
        "failure-routes.yaml",
        "failure-routes.json",
    )
)


def _touch(repo: Path, relative: str) -> Path:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}\n", encoding="utf-8")
    return path


def test_earlier_candidates_keep_their_order():
    count = len(_EARLIER_CANDIDATES)
    assert TASK_ROUTE_INDEX_CANDIDATES[:count] == _EARLIER_CANDIDATES


def test_failure_memory_default_is_appended_for_both_directories():
    added = TASK_ROUTE_INDEX_CANDIDATES[len(_EARLIER_CANDIDATES) :]
    assert added == (
        ".knowledge/generated/failure_routes.json",
        "knowledge/generated/failure_routes.json",
    )


@pytest.mark.parametrize("dirname", [".knowledge", "knowledge"])
def test_finds_failure_memory_default_output(tmp_path, dirname):
    expected = _touch(tmp_path, f"{dirname}/generated/failure_routes.json")
    assert find_task_route_index(tmp_path) == expected


def test_earlier_candidate_wins_over_failure_memory_default(tmp_path):
    _touch(tmp_path, ".knowledge/generated/failure_routes.json")
    earlier = _touch(tmp_path, "knowledge/failure-routes.json")
    assert find_task_route_index(tmp_path) == earlier


def test_first_candidate_wins(tmp_path):
    _touch(tmp_path, "knowledge/task-routes.yaml")
    first = _touch(tmp_path, ".knowledge/task-routes.yaml")
    assert find_task_route_index(tmp_path) == first


def test_directory_is_not_a_route_index(tmp_path):
    (tmp_path / ".knowledge" / "task-routes.yaml").mkdir(parents=True)
    assert find_task_route_index(tmp_path) is None


def test_none_when_absent(tmp_path):
    assert find_task_route_index(tmp_path) is None


def test_orchestrator_uses_shared_discovery(tmp_path):
    from akms.orchestrator import orchestrator

    assert orchestrator._find_task_route_index is find_task_route_index
    expected = _touch(tmp_path, "knowledge/task-routes.yaml")
    assert orchestrator._find_task_route_index(tmp_path) == expected


def test_status_and_discovery_do_not_load_the_runtime():
    # ADR 0001: the route-index surface and the health report stay usable
    # without the embedded runtime. A fresh interpreter is the honest witness.
    script = (
        "import sys\n"
        "import akms.task_context.routes, akms.graph.graph_status\n"
        "loaded = sorted(m for m in sys.modules\n"
        "    if m.split('.')[:2] in (['akms', 'orchestrator'], ['akms', 'agents']))\n"
        "assert not loaded, loaded\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
