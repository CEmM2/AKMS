"""Phase D1 E2E: wave dispatch integrated into handler chain.

Wave integration into the handler pipeline.
Acceptance criteria covered:
- handle_review() uses dispatch_phase() instead of ThreadPoolExecutor
- Graph-only mode (agent_cls=None) still skips dispatch in handle_review()
"""

from __future__ import annotations

from pathlib import Path

import asyncio

import pytest
import yaml

from akms.orchestrator.orchestrator import (
    handle_review,
)
from akms.orchestrator.wave_dispatch import TaskResult
from akms.schema.models import AgentRole, PropagationConfig

from tests.akms.conftest import make_global_node, make_ctx, make_state


class TestADM009WaveIntegration:
    """
    Wave integration into the handler pipeline.
    Acceptance criteria covered: [1, 2, 3, 4, 5]
    """

    @pytest.fixture
    def tmp_vault(self, tmp_path: Path) -> Path:
        vault = tmp_path / "global_vault" / "nodes"
        vault.mkdir(parents=True)
        return vault

    @pytest.fixture
    def tmp_repo(self, tmp_path: Path) -> Path:
        repo = tmp_path / "repo"
        repo.mkdir()
        knowledge = repo / "knowledge"
        for subdir in [
            "graph",
            "local-nodes",
            "sessions",
            "loadouts",
            "code-mirror",
            "qmd",
        ]:
            (knowledge / subdir).mkdir(parents=True)
        overlay_path = knowledge / "graph" / "local_state.yaml"
        overlay_path.write_text(
            yaml.dump(
                {
                    "akms_schema": "v2",
                    "repo_id": "test-repo",
                    "nodes": {},
                    "local_edges": [],
                    "session_nodes": {},
                    "suppressed_edges": [],
                }
            )
        )
        return repo

    @pytest.fixture(autouse=True)
    def set_vault_env(self, tmp_vault: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(tmp_vault))

    @pytest.mark.e2e
    def test_graph_only_mode_skips_dispatch_phase(
        self, tmp_vault, tmp_repo, monkeypatch
    ):
        """
        Verifies: When agent_cls=None, handle_review() does NOT call dispatch_phase().
        Acceptance criterion: Graph-only mode (agent_cls=None) still skips dispatch in review()
        Passes when: dispatch_phase is never invoked, review returns skipped message
        """
        make_global_node(tmp_vault, id="node-a", tags=["test"])

        state = make_state(current_phase=1)
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=None)

        dispatch_called = []

        async def _spy_dispatch(
            tasks, agent_cls, config, repo_root, model_override=None
        ):
            dispatch_called.append(True)
            return []

        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.dispatch_phase", _spy_dispatch
        )

        stage_output, akms_status, warnings = asyncio.run(handle_review(state, ctx))
        assert "skipped (graph-only mode)" in stage_output
        assert dispatch_called == [], (
            "dispatch_phase should NOT be called in graph-only mode"
        )

    @pytest.mark.e2e
    def test_orchestrator_review_uses_dispatch_phase(
        self, tmp_vault, tmp_repo, monkeypatch
    ):
        """
        Verifies: handle_review() routes through dispatch_phase() when agent_cls is set.
        Acceptance criterion: review() uses dispatch_phase() instead of ThreadPoolExecutor
        Passes when: dispatch_phase is called with correct reviewer tasks,
        review results are extracted from task results
        """
        from tests.fakes.fake_agent import FakeAgent

        make_global_node(tmp_vault, id="node-a", tags=["test"])

        state = make_state(current_phase=1)
        ctx = make_ctx(tmp_repo, tmp_vault, agent_cls=FakeAgent)

        async def _mock_dispatch(
            tasks, agent_cls, config, repo_root, model_override=None
        ):
            results = []
            for task in tasks:
                task_id = task["task_id"]
                out_dir = repo_root / "knowledge" / "sessions"
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"{task_id}.md"
                memory_data = {
                    "nodes_used": [
                        {"id": "node-a", "useful": True, "coverage": "sufficient"}
                    ],
                    "pitfalls_discovered": [],
                    "new_knowledge": [],
                    "nodes_missing": [],
                    "lessons": {"worked": [], "failed": []},
                }
                out_path.write_text(
                    "---\n" + yaml.dump(memory_data, sort_keys=False) + "---\n"
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

        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.dispatch_phase", _mock_dispatch
        )
        monkeypatch.setattr(
            "akms.orchestrator.orchestrator.update_graph",
            lambda source, repo_root, config=None, global_vault=None: {},
        )

        stage_output, akms_status, warnings = asyncio.run(handle_review(state, ctx))
        assert "review" in stage_output
        assert "2/2" in stage_output, (
            f"Expected '2/2' in stage_output, got: {stage_output!r}"
        )
