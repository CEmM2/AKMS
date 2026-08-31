"""Tests for reviewer resolution from the actual diff.

Covers:
  - Pre-task vs post-diff required discovery
  - Empty-diff fallback to task scope
  - Multi-file task-local diff
  - Role-specific advisory profiles
  - Bare changed-path string rejection
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from akms.graph.build_graph import build_graph
from akms.schema.models import AgentRole
from akms.task_context.review import resolve_reviewer_context
from tests.akms.conftest import make_global_node, make_mirror_node


def _write_task(path: Path, **overrides) -> Path:
    task = {
        "task_id": "TSK-REV",
        "phase": 2,
        "title": "Reviewer resolution fixture",
        "objective": "Prove post-diff required discovery.",
        "scope": ["src/solver.py"],
        "deliverables": ["src/solver.py"],
        "akms_tags": ["solver"],
        "implementation_steps": ["Implement", "Review"],
        "symbols": [],
    }
    task.update(overrides)
    path.write_text(json.dumps(task, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_routes(path: Path, by_path: dict[str, list[dict]]) -> Path:
    payload = {
        "schema_version": "v1",
        "source_hash": "sha256:review-fixture",
        "by_path": by_path,
        "by_symbol": {},
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    return path


def _prepare_review_repo(tmp_vault: Path, tmp_repo: Path) -> None:
    # Required lessons for two different production files.
    make_global_node(
        tmp_vault,
        id="lesson-solver",
        tags=["solver", "failure"],
        domain="computational-mechanics",
        content="# Solver lesson\n\n## Summary\n\nCheck residuals.\n",
        confidence=0.95,
    )
    make_global_node(
        tmp_vault,
        id="lesson-integrator",
        tags=["integrator", "failure"],
        domain="computational-mechanics",
        content="# Integrator lesson\n\n## Summary\n\nConserve energy.\n",
        confidence=0.95,
    )
    make_global_node(
        tmp_vault,
        id="lesson-unrelated",
        tags=["unrelated"],
        domain="computational-mechanics",
        content="# Unrelated\n\n## Summary\n\nNot for this task.\n",
        confidence=0.95,
    )
    # Role-distinct advisory: code-mirror domain is often filtered for physics.
    make_global_node(
        tmp_vault,
        id="advisory-code",
        tags=["solver"],
        domain="code-quality",
        content="# Code advisory\n\n## Summary\n\nLint patterns.\n",
        confidence=0.9,
    )
    make_global_node(
        tmp_vault,
        id="advisory-physics",
        tags=["solver"],
        domain="computational-mechanics",
        content="# Physics advisory\n\n## Summary\n\nEnergy norms.\n",
        confidence=0.9,
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
    make_mirror_node(
        tmp_repo,
        id="mirror-unrelated",
        source_file="src/unrelated_phase_file.py",
        content_ref="code-mirror/mirror-unrelated.md",
    )
    build_graph(tmp_repo, global_vault=tmp_vault)


def _routes_two_files(path: Path) -> Path:
    return _write_routes(
        path,
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
                    "reason": "Exact route for integrator (post-diff only)",
                    "provenance": "fixture",
                }
            ],
            "src/unrelated_phase_file.py": [
                {
                    "node_id": "lesson-unrelated",
                    "reason": "Phase-wide unrelated file",
                    "provenance": "fixture",
                }
            ],
        },
    )


class TestPostDiffDiscovery:
    def test_post_diff_only_required_from_new_file(self, tmp_vault, tmp_repo):
        """A production file absent from original scope but present in the
        diff triggers its required lessons and is reported as post-diff-only.
        """
        _prepare_review_repo(tmp_vault, tmp_repo)
        task_path = _write_task(tmp_repo / "task.json")
        routes_path = _routes_two_files(tmp_repo / "routes.yaml")

        result = resolve_reviewer_context(
            repo_root=tmp_repo,
            task=task_path,
            route_index=routes_path,
            agent_role=AgentRole.CODE_REVIEWER,
            changed_paths=["src/solver.py", "src/integrator.py"],
        )

        assert result.status == "ok", result.error
        assert result.empty_diff_fallback is False
        assert "lesson-solver" in result.pre_task_required
        assert "lesson-integrator" not in result.pre_task_required
        assert "lesson-integrator" in result.post_diff_required
        # Post-diff-only includes the new required route *and* its exact mirror.
        assert "lesson-integrator" in result.post_diff_only_required
        assert "mirror-integrator" in result.post_diff_only_required
        assert "lesson-solver" not in result.post_diff_only_required
        assert result.loadout_path and Path(result.loadout_path).exists()
        loadout = Path(result.loadout_path).read_text(encoding="utf-8")
        assert "lesson-integrator" in loadout
        assert "Exact route for integrator" in loadout

    def test_phase_wide_unrelated_not_attributed(self, tmp_vault, tmp_repo):
        """Phase-wide unrelated changes must not become task-review required."""
        _prepare_review_repo(tmp_vault, tmp_repo)
        task_path = _write_task(tmp_repo / "task.json")
        routes_path = _routes_two_files(tmp_repo / "routes.yaml")

        result = resolve_reviewer_context(
            repo_root=tmp_repo,
            task=task_path,
            route_index=routes_path,
            agent_role=AgentRole.CODE_REVIEWER,
            changed_paths=["src/solver.py"],
        )

        assert result.status == "ok", result.error
        assert "lesson-unrelated" not in result.post_diff_required
        assert "lesson-unrelated" not in result.post_diff_only_required
        assert "lesson-solver" in result.post_diff_required


class TestEmptyAndMultiFileDiff:
    def test_empty_diff_falls_back_to_task_scope(self, tmp_vault, tmp_repo):
        _prepare_review_repo(tmp_vault, tmp_repo)
        task_path = _write_task(tmp_repo / "task.json")
        routes_path = _routes_two_files(tmp_repo / "routes.yaml")

        result = resolve_reviewer_context(
            repo_root=tmp_repo,
            task=task_path,
            route_index=routes_path,
            agent_role=AgentRole.CODE_REVIEWER,
            changed_paths=[],
        )

        assert result.status == "ok", result.error
        assert result.empty_diff_fallback is True
        assert result.changed_paths == ()
        assert "lesson-solver" in result.post_diff_required
        assert "lesson-integrator" not in result.post_diff_required
        assert result.post_diff_only_required == ()
        assert result.loadout_path and Path(result.loadout_path).exists()

    def test_multi_file_diff_deduplicates_routes(self, tmp_vault, tmp_repo):
        _prepare_review_repo(tmp_vault, tmp_repo)
        # Scope already includes solver; multi-file adds integrator twice.
        task_path = _write_task(tmp_repo / "task.json")
        routes_path = _routes_two_files(tmp_repo / "routes.yaml")

        result = resolve_reviewer_context(
            repo_root=tmp_repo,
            task=task_path,
            route_index=routes_path,
            agent_role=AgentRole.PHYSICS_REVIEWER,
            changed_paths=[
                "src/solver.py",
                "src/integrator.py",
                "src/integrator.py",  # duplicate path
            ],
        )

        assert result.status == "ok", result.error
        assert set(result.post_diff_required) >= {
            "lesson-solver",
            "lesson-integrator",
        }
        # Deduped required list (tuple of unique ids).
        assert len(result.post_diff_required) == len(set(result.post_diff_required))
        assert "lesson-integrator" in result.post_diff_only_required


class TestRoleSpecific:
    def test_code_and_physics_roles_remain_distinct(self, tmp_vault, tmp_repo):
        _prepare_review_repo(tmp_vault, tmp_repo)
        task_path = _write_task(tmp_repo / "task.json")
        routes_path = _routes_two_files(tmp_repo / "routes.yaml")

        code = resolve_reviewer_context(
            repo_root=tmp_repo,
            task=task_path,
            route_index=routes_path,
            agent_role=AgentRole.CODE_REVIEWER,
            changed_paths=["src/solver.py"],
            write_artifacts=True,
        )
        physics = resolve_reviewer_context(
            repo_root=tmp_repo,
            task=task_path,
            route_index=routes_path,
            agent_role=AgentRole.PHYSICS_REVIEWER,
            changed_paths=["src/solver.py"],
            write_artifacts=True,
        )

        assert code.status == "ok", code.error
        assert physics.status == "ok", physics.error
        assert code.role == "code_reviewer"
        assert physics.role == "physics_reviewer"
        # Required set from exact routes is role-independent.
        assert code.post_diff_required == physics.post_diff_required
        # Fingerprints differ because role is part of the retrieval boundary.
        assert code.fingerprint != physics.fingerprint
        assert code.loadout_path != physics.loadout_path
        assert Path(code.loadout_path).exists()
        assert Path(physics.loadout_path).exists()
        code_header = Path(code.loadout_path).read_text(encoding="utf-8")
        physics_header = Path(physics.loadout_path).read_text(encoding="utf-8")
        assert "agent_role: code_reviewer" in code_header
        assert "agent_role: physics_reviewer" in physics_header

    def test_implementer_role_rejected(self, tmp_vault, tmp_repo):
        _prepare_review_repo(tmp_vault, tmp_repo)
        task_path = _write_task(tmp_repo / "task.json")
        routes_path = _routes_two_files(tmp_repo / "routes.yaml")

        result = resolve_reviewer_context(
            repo_root=tmp_repo,
            task=task_path,
            route_index=routes_path,
            agent_role=AgentRole.IMPLEMENTER,
            changed_paths=["src/solver.py"],
        )
        assert result.status == "error"
        assert result.error_code == "invalid_role"

    def test_bare_string_changed_path_rejected(self, tmp_vault, tmp_repo):
        _prepare_review_repo(tmp_vault, tmp_repo)
        task_path = _write_task(tmp_repo / "task.json")
        routes_path = _routes_two_files(tmp_repo / "routes.yaml")

        result = resolve_reviewer_context(
            repo_root=tmp_repo,
            task=task_path,
            route_index=routes_path,
            agent_role="code_reviewer",
            changed_paths="src/solver.py",  # type: ignore[arg-type]
        )
        assert result.status == "error"
        assert result.error_code == "invalid_changed_paths"
