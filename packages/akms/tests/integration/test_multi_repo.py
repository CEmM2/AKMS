"""Pipeline-level multi-repo isolation tests.

Verifies that two pipelines running against separate repos do not
contaminate each other, and that the global vault remains read-only
throughout both pipeline executions (FR-O01 invariant).

Acceptance criteria:
[0] Two repos can init_pipeline independently
[1] Pipeline state in repo A does not affect repo B
[2] Global vault has zero writes from either pipeline (FR-O01)
[3] Local state files are repo-specific
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest
import yaml

from akms.orchestrator.orchestrator import PipelineContext, handle_init
from akms.orchestrator.stages import PipelineState
from akms.schema.models import PropagationConfig


# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════


def _make_repo(base: Path, name: str) -> Path:
    """Create a minimal repo directory layout for pipeline tests."""
    repo = base / name
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
    (knowledge / "graph" / "local_state.yaml").write_text(
        yaml.dump(
            {
                "akms_schema": "v2",
                "repo_id": name,
                "nodes": {},
                "local_edges": [],
                "session_nodes": {},
                "suppressed_edges": [],
            }
        )
    )
    return repo


def _make_global_vault(base: Path) -> Path:
    """Create a minimal (empty) shared global vault."""
    vault = base / "shared_vault" / "nodes"
    vault.mkdir(parents=True)
    return vault


def _snapshot_vault(vault: Path) -> dict[str, str]:
    """Return a {relative_path: sha256} map for every file in vault."""
    snapshot: dict[str, str] = {}
    for path in vault.rglob("*"):
        if path.is_file():
            rel = str(path.relative_to(vault))
            snapshot[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return snapshot


# ═══════════════════════════════════════════════════════════════════════
#  Tests
# ═══════════════════════════════════════════════════════════════════════


class TestMultiRepoIsolationPipeline:
    """Pipeline-level multi-repo isolation tests.

    Acceptance criteria:
    [0] Two repos can init_pipeline independently
    [1] Pipeline state in repo A does not affect repo B
    [2] Global vault has zero writes from either pipeline (FR-O01)
    [3] Local state files are repo-specific
    """

    @pytest.mark.integration
    def test_two_repos_init_independently(self, tmp_path):
        """Verifies: Two repos can run handle_init without cross-contamination.
        Acceptance criterion: Two repos can init_pipeline independently
        Passes when: Both repos produce independent graph state.
        """
        repo_a = _make_repo(tmp_path, "repo_a")
        repo_b = _make_repo(tmp_path, "repo_b")
        vault = _make_global_vault(tmp_path)

        config = PropagationConfig()
        ctx_a = PipelineContext(
            repo_root=repo_a,
            global_vault=vault,
            config=config,
            agent_cls=None,
            model=None,
        )
        ctx_b = PipelineContext(
            repo_root=repo_b,
            global_vault=vault,
            config=config,
            agent_cls=None,
            model=None,
        )

        state_a = PipelineState(goal="repo A goal")
        state_b = PipelineState(goal="repo B goal")

        # Run handle_init for both repos independently
        out_a, _, _ = asyncio.run(handle_init(state_a, ctx_a))
        out_b, _, _ = asyncio.run(handle_init(state_b, ctx_b))

        # Both handlers return a non-empty status string
        assert isinstance(out_a, str) and out_a
        assert isinstance(out_b, str) and out_b

        # Each repo produced its own graph.json
        graph_a = repo_a / "knowledge" / "graph" / "graph.json"
        graph_b = repo_b / "knowledge" / "graph" / "graph.json"
        assert graph_a.exists(), "Repo A did not produce graph.json"
        assert graph_b.exists(), "Repo B did not produce graph.json"

        # The two graph files are independent files (different paths)
        assert graph_a.resolve() != graph_b.resolve()

    @pytest.mark.integration
    def test_pipeline_state_isolated_per_repo(self, tmp_path):
        """Verifies: Pipeline state in repo A does not affect repo B.
        Acceptance criterion: Pipeline state isolated per repo
        Passes when: PipelineState.load from each repo returns independent state.
        """
        repo_a = _make_repo(tmp_path, "repo_a")
        repo_b = _make_repo(tmp_path, "repo_b")
        vault = _make_global_vault(tmp_path)

        config = PropagationConfig()

        # Run handle_init for repo A only — saves state into repo A
        PipelineContext(
            repo_root=repo_a,
            global_vault=vault,
            config=config,
            agent_cls=None,
            model=None,
        )
        state_a = PipelineState(goal="goal for A", plan_name="plan-a")
        state_a.save(repo_a)

        # Explicitly do NOT touch repo B state at all
        # handle_init for B with a different goal
        ctx_b = PipelineContext(
            repo_root=repo_b,
            global_vault=vault,
            config=config,
            agent_cls=None,
            model=None,
        )
        state_b = PipelineState(goal="goal for B", plan_name="plan-b")
        state_b.save(repo_b)
        asyncio.run(handle_init(state_b, ctx_b))

        # Load persisted state from each repo independently
        loaded_a = PipelineState.load(repo_a)
        loaded_b = PipelineState.load(repo_b)

        assert loaded_a is not None, "Repo A has no saved pipeline state"
        assert loaded_b is not None, "Repo B has no saved pipeline state"

        # Goals are independent — B's goal did not overwrite A's
        assert loaded_a.goal == "goal for A"
        assert loaded_b.goal == "goal for B"

        # plan_name is isolated per repo
        assert loaded_a.plan_name == "plan-a"
        assert loaded_b.plan_name == "plan-b"

        # Repo B's pipeline_state.json does not live inside repo A
        state_file_a = repo_a / "knowledge" / "graph" / "pipeline_state.json"
        state_file_b = repo_b / "knowledge" / "graph" / "pipeline_state.json"
        assert state_file_a.exists()
        assert state_file_b.exists()
        assert state_file_a.resolve() != state_file_b.resolve()

    @pytest.mark.integration
    def test_global_vault_read_only_during_pipeline(self, tmp_path):
        """Verifies: Global vault has zero writes from either pipeline.
        Acceptance criterion: Global vault read-only (FR-O01)
        Passes when: All files in global vault are byte-identical before and after pipeline run.
        """
        repo_a = _make_repo(tmp_path, "repo_a")
        repo_b = _make_repo(tmp_path, "repo_b")
        vault = _make_global_vault(tmp_path)

        config = PropagationConfig()

        # Snapshot vault state before any pipeline activity
        snapshot_before = _snapshot_vault(vault)

        # Run handle_init for both repos (graph-only mode — no LLM calls)
        ctx_a = PipelineContext(
            repo_root=repo_a,
            global_vault=vault,
            config=config,
            agent_cls=None,
            model=None,
        )
        ctx_b = PipelineContext(
            repo_root=repo_b,
            global_vault=vault,
            config=config,
            agent_cls=None,
            model=None,
        )

        state_a = PipelineState(goal="vault check A")
        state_b = PipelineState(goal="vault check B")

        asyncio.run(handle_init(state_a, ctx_a))
        asyncio.run(handle_init(state_b, ctx_b))

        # Snapshot vault state after pipeline activity
        snapshot_after = _snapshot_vault(vault)

        # FR-O01: global vault must be byte-identical — no files added, removed, or modified
        assert snapshot_before == snapshot_after, (
            f"Global vault was mutated during pipeline execution.\n"
            f"Before: {sorted(snapshot_before)}\n"
            f"After:  {sorted(snapshot_after)}"
        )

        # Additionally assert that writes only happened inside the repos, not in the vault
        new_files_in_vault = set(snapshot_after) - set(snapshot_before)
        assert not new_files_in_vault, (
            f"New files written to global vault (FR-O01 violation): {new_files_in_vault}"
        )
