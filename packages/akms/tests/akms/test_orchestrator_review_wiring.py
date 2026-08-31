"""Tests for orchestrator handle_review → resolve_reviewer_context wiring.

Hermetic: no network, no real LLM. Verifies soft-fail without routes and
post-diff required loadouts when a route index is present.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from akms.agents.base import AKMSAgent
from akms.graph.build_graph import build_graph
from akms.orchestrator.orchestrator import _git_files_modified, handle_review
from akms.orchestrator.wave_dispatch import TaskResult
from tests.akms.conftest import (
    make_ctx,
    make_global_node,
    make_mirror_node,
    make_state,
)


def _write_routes(path: Path, by_path: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "v1",
                "source_hash": "sha256:orchestrator-review-wiring",
                "by_path": by_path,
                "by_symbol": {},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _mock_dispatch_factory(captured: list):
    async def _mock_dispatch(tasks, agent_cls, config, repo_root, model_override=None):
        captured.extend(tasks)
        results = []
        for task in tasks:
            task_id = task["task_id"]
            out_dir = Path(repo_root) / "knowledge" / "sessions"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{task_id}.md"
            memory_data = {
                "nodes_used": [],
                "pitfalls_discovered": [],
                "new_knowledge": [],
                "nodes_missing": [],
                "lessons": {"worked": [], "failed": []},
            }
            out_path.write_text(
                "---\n" + yaml.safe_dump(memory_data, sort_keys=False) + "---\n",
                encoding="utf-8",
            )
            results.append(
                TaskResult(
                    task_id=task_id,
                    status="complete",
                    memory_path=str(out_path),
                    error="",
                )
            )
        return results

    return _mock_dispatch


def _diff_result(paths: list[str], error: str | None = None) -> SimpleNamespace:
    """Model successful-empty and failed git-diff collection distinctly."""
    return SimpleNamespace(paths=paths, error=error)


class TestGitDiffCollectionStatus:
    def test_successful_empty_diff_is_not_a_collection_error(
        self, tmp_repo, monkeypatch
    ):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout=""),
        )

        result = _git_files_modified(tmp_repo, "phase-1")

        assert result.paths == ()
        assert result.error is None

    def test_failed_diff_retains_its_error(self, tmp_repo, monkeypatch):
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda *a, **k: subprocess.CompletedProcess(
                a[0], 128, stdout="", stderr="unknown revision"
            ),
        )

        result = _git_files_modified(tmp_repo, "phase-1")

        assert result.paths == ()
        assert "exit status 128" in result.error
        assert "unknown revision" in result.error


class TestHandleReviewSoftFailWithoutRoutes:
    def test_missing_route_index_falls_back_to_tag_loadouts(
        self,
        tmp_vault,
        tmp_repo,
        monkeypatch,
    ):
        make_global_node(tmp_vault, id="node-a", tags=["solver"])
        build_graph(tmp_repo, global_vault=tmp_vault)

        captured: list = []
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.dispatch_phase",
            _mock_dispatch_factory(captured),
        )
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator._git_files_modified",
            lambda *a, **k: _diff_result(
                [], "git diff phase-1 failed with exit status 128"
            ),
        )

        state = make_state(
            goal="test",
            current_phase=1,
            tasks=[
                {
                    "task_id": "T1",
                    "phase": 1,
                    "scope": ["src/solver.py"],
                    "akms_tags": ["solver"],
                }
            ],
        )
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=AKMSAgent)

        stage_output, akms_status, warnings = asyncio.run(handle_review(state, ctx))

        assert "2/2" in stage_output or "reviews=2" in akms_status
        assert any("no task route index" in w for w in warnings)
        assert any("actual diff collection failed" in w for w in warnings)
        assert "required_resolution=0" in akms_status
        assert len(captured) == 2
        roles = {t["agent_role"] for t in captured}
        assert roles == {"code_reviewer", "physics_reviewer"}
        for task in captured:
            assert task["resolution_source"] == "advisory_tags"
            assert Path(task["loadout_path"]).exists()
            # Soft-fail path must not require a manifest.
            assert "manifest_path" not in task or not task.get("manifest_path")


class TestHandleReviewRequiredDiffWiring:
    def test_route_index_uses_post_diff_required_lessons(
        self,
        tmp_vault,
        tmp_repo,
        monkeypatch,
    ):
        make_global_node(
            tmp_vault,
            id="lesson-solver",
            tags=["solver", "failure"],
            domain="computational-mechanics",
            content="# Solver\n\n## Summary\n\nCheck residuals.\n",
            confidence=0.95,
        )
        make_global_node(
            tmp_vault,
            id="lesson-integrator",
            tags=["integrator", "failure"],
            domain="computational-mechanics",
            content="# Integrator\n\n## Summary\n\nConserve energy.\n",
            confidence=0.95,
        )
        make_mirror_node(
            tmp_repo,
            id="mirror-solver",
            source_file="src/solver.py",
            content_ref="code-mirror/mirror-solver.md",
        )
        make_mirror_node(
            tmp_repo,
            id="mirror-integrator",
            source_file="src/integrator.py",
            content_ref="code-mirror/mirror-integrator.md",
        )
        build_graph(tmp_repo, global_vault=tmp_vault)

        _write_routes(
            tmp_repo / "knowledge" / "task-routes.yaml",
            {
                "src/solver.py": [
                    {
                        "node_id": "lesson-solver",
                        "reason": "Exact route for solver",
                        "provenance": "fixture",
                    }
                ],
                "src/integrator.py": [
                    {
                        "node_id": "lesson-integrator",
                        "reason": "Exact route for integrator (post-diff)",
                        "provenance": "fixture",
                    }
                ],
            },
        )

        # Diff includes a file outside original scope → post_diff_only.
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator._git_files_modified",
            lambda *a, **k: _diff_result(["src/solver.py", "src/integrator.py"]),
        )

        captured: list = []
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.dispatch_phase",
            _mock_dispatch_factory(captured),
        )

        state = make_state(
            goal="test",
            current_phase=1,
            tasks=[
                {
                    "task_id": "T1",
                    "phase": 1,
                    "title": "Implement solver",
                    "scope": ["src/solver.py"],
                    "deliverables": ["src/solver.py"],
                    "akms_tags": ["solver"],
                }
            ],
        )
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=AKMSAgent)

        stage_output, akms_status, warnings = asyncio.run(handle_review(state, ctx))

        assert "required_resolution=2" in akms_status
        assert any("post_diff_only_required" in w for w in warnings)
        assert len(captured) == 2

        code = next(t for t in captured if t["agent_role"] == "code_reviewer")
        physics = next(t for t in captured if t["agent_role"] == "physics_reviewer")

        assert code["resolution_source"] == "required_diff"
        assert physics["resolution_source"] == "required_diff"
        # Roles remain distinct (different fingerprints / loadout paths).
        assert code["loadout_path"] != physics["loadout_path"]
        assert code.get("resolution_fingerprint") != physics.get(
            "resolution_fingerprint"
        )

        assert "lesson-integrator" in code["post_diff_only_required"]
        assert "lesson-solver" in code["post_diff_required"]
        assert "lesson-solver" in code["pre_task_required"]
        assert code["empty_diff_fallback"] is False

        loadout = Path(code["loadout_path"]).read_text(encoding="utf-8")
        assert "## Required Knowledge" in loadout
        assert "lesson-integrator" in loadout
        assert "Exact route for integrator" in loadout
        assert Path(code["manifest_path"]).exists()

    def test_empty_diff_fallback_still_writes_role_loadouts(
        self,
        tmp_vault,
        tmp_repo,
        monkeypatch,
    ):
        make_global_node(
            tmp_vault,
            id="lesson-solver",
            tags=["solver"],
            domain="computational-mechanics",
            confidence=0.95,
        )
        make_mirror_node(
            tmp_repo,
            id="mirror-solver",
            source_file="src/solver.py",
            content_ref="code-mirror/mirror-solver.md",
        )
        build_graph(tmp_repo, global_vault=tmp_vault)
        _write_routes(
            tmp_repo / "knowledge" / "task-routes.yaml",
            {
                "src/solver.py": [
                    {
                        "node_id": "lesson-solver",
                        "reason": "Exact route for solver",
                        "provenance": "fixture",
                    }
                ],
            },
        )

        monkeypatch.setattr(
            "akms.orchestrator.orchestrator._git_files_modified",
            lambda *a, **k: _diff_result([]),  # successful empty diff
        )
        captured: list = []
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.dispatch_phase",
            _mock_dispatch_factory(captured),
        )

        state = make_state(
            goal="test",
            current_phase=1,
            tasks=[
                {
                    "task_id": "T1",
                    "phase": 1,
                    "scope": ["src/solver.py"],
                    "akms_tags": ["solver"],
                }
            ],
        )
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=AKMSAgent)
        _, akms_status, _ = asyncio.run(handle_review(state, ctx))

        assert "required_resolution=2" in akms_status
        assert "changed_files=0" in akms_status
        for task in captured:
            assert task["resolution_source"] == "required_diff"
            assert task["empty_diff_fallback"] is True
            assert task["post_diff_only_required"] == []
            assert "lesson-solver" in task["post_diff_required"]
            assert Path(task["loadout_path"]).exists()

    def test_diff_collection_failure_blocks_adopted_route_review(
        self,
        tmp_vault,
        tmp_repo,
        monkeypatch,
    ):
        make_global_node(tmp_vault, id="lesson-solver", tags=["solver"])
        make_mirror_node(
            tmp_repo,
            id="mirror-solver",
            source_file="src/solver.py",
            content_ref="code-mirror/mirror-solver.md",
        )
        build_graph(tmp_repo, global_vault=tmp_vault)
        _write_routes(
            tmp_repo / "knowledge" / "task-routes.yaml",
            {
                "src/solver.py": [
                    {
                        "node_id": "lesson-solver",
                        "reason": "Exact route for solver",
                        "provenance": "fixture",
                    }
                ],
            },
        )
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator._git_files_modified",
            lambda *a, **k: _diff_result(
                [], "git diff phase-1 failed with exit status 128"
            ),
        )
        captured: list = []
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.dispatch_phase",
            _mock_dispatch_factory(captured),
        )

        state = make_state(
            goal="test",
            current_phase=1,
            tasks=[
                {
                    "task_id": "T1",
                    "phase": 1,
                    "scope": ["src/solver.py"],
                    "akms_tags": ["solver"],
                }
            ],
        )
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=AKMSAgent)

        with pytest.raises(RuntimeError, match="could not collect actual diff"):
            asyncio.run(handle_review(state, ctx))

        assert captured == []

    def test_resolution_failure_blocks_adopted_route_review(
        self,
        tmp_vault,
        tmp_repo,
        monkeypatch,
    ):
        make_global_node(tmp_vault, id="advisory-solver", tags=["solver"])
        make_mirror_node(
            tmp_repo,
            id="mirror-solver",
            source_file="src/solver.py",
            content_ref="code-mirror/mirror-solver.md",
        )
        build_graph(tmp_repo, global_vault=tmp_vault)
        _write_routes(
            tmp_repo / "knowledge" / "task-routes.yaml",
            {
                "src/solver.py": [
                    {
                        "node_id": "missing-required-lesson",
                        "reason": "Route must fail closed when unavailable",
                        "provenance": "fixture",
                    }
                ],
            },
        )
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator._git_files_modified",
            lambda *a, **k: _diff_result(["src/solver.py"]),
        )
        captured: list = []
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.dispatch_phase",
            _mock_dispatch_factory(captured),
        )
        state = make_state(
            goal="test",
            current_phase=1,
            tasks=[
                {
                    "task_id": "T1",
                    "phase": 1,
                    "scope": ["src/solver.py"],
                    "akms_tags": ["solver"],
                }
            ],
        )
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=AKMSAgent)

        with pytest.raises(
            RuntimeError, match="resolution failed for adopted route index"
        ):
            asyncio.run(handle_review(state, ctx))

        assert captured == []
