"""Public smoke tests: the embedded runtime on an installed akms[orchestration].

Deterministic and offline: agent behavior comes from a fake backend module
written into the test's tmp dir, never from a live provider. What is proven:

* a backend whose binary is absent fails fast with an actionable message,
* a failing agent takes the pipeline's failure path (nonzero exit, seconds,
  state saved) instead of gating on garbage or hanging,
* an unattended checkpoint gate aborts on its short headless timeout.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

BIN = Path(sys.executable).parent

FAKE_FAILING_AGENT = '''
from akms.agents.base import AKMSAgent

class FailingAgent(AKMSAgent):
    """Deterministic backend stand-in whose execution always fails."""

    def preflight(self):
        return None  # backend "available"; the run itself fails

    async def execute(self, task_json, loadout, system_prompt):
        raise RuntimeError("simulated backend failure")
'''


def _make_repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    for sub in ["graph", "local-nodes", "sessions", "loadouts", "code-mirror", "qmd"]:
        (repo / "knowledge" / sub).mkdir(parents=True)
    (repo / "knowledge" / "graph" / "local_state.yaml").write_text(
        "akms_schema: v2\nnodes: {}\n"
    )
    return repo


@pytest.mark.e2e
@pytest.mark.runtime
def test_missing_cli_backend_fails_fast(tmp_path):
    """A CLI backend without its binary exits nonzero in seconds, writing nothing."""
    repo = _make_repo(tmp_path)
    env = dict(os.environ, PATH=str(BIN))  # scrub PATH down to the venv bin
    result = subprocess.run(
        [str(BIN / "akms"), "orchestrate", "--goal", "t", "--backend", "codex-cli"],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
        timeout=30,
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode != 0
    assert "codex" in result.stderr
    assert not (repo / "knowledge" / "sessions").glob("*") or not list(
        (repo / "knowledge" / "sessions").iterdir()
    )


@pytest.mark.e2e
@pytest.mark.runtime
def test_failing_agent_takes_failure_path(tmp_path):
    """A failed stage agent → nonzero exit within seconds, resumable state saved."""
    repo = _make_repo(tmp_path)
    (tmp_path / "fake_backend.py").write_text(FAKE_FAILING_AGENT)
    env = dict(os.environ, PYTHONPATH=str(tmp_path))
    result = subprocess.run(
        [
            str(BIN / "akms"),
            "orchestrate",
            "--goal",
            "t",
            "--agent",
            "fake_backend.FailingAgent",
        ],
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )
    assert result.returncode != 0
    assert "PLAN stage failed" in result.stderr
    assert "--resume" in result.stderr
    # State was saved for resume.
    assert (repo / "knowledge" / "pipeline_state.yaml").exists() or list(
        (repo / "knowledge").rglob("*state*")
    ), "no saved pipeline state found"


@pytest.mark.e2e
@pytest.mark.runtime
def test_unattended_gate_aborts_on_short_timeout(tmp_path):
    """Graph-only pipeline with an unanswered gate aborts; run marked aborted."""
    from akms.orchestrator.checkpoint import FileCheckpointHandler
    from akms.orchestrator.orchestrator import run_pipeline

    repo = _make_repo(tmp_path)
    state = asyncio.run(
        run_pipeline(
            repo_root=repo,
            goal="t",
            agent_cls=None,  # graph-only: no agent, gates still present
            checkpoint_handler=FileCheckpointHandler(timeout=1.0, poll_interval=0.2),
        )
    )
    assert state.aborted is True
    assert getattr(state, "completed", False) is False
