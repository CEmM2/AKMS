"""Run the embedded AKMS runtime end to end, deterministically and offline.

Usage (needs ``pip install "akms[orchestration]"`` or a workspace checkout)::

    python run_demo.py [workspace-dir]

Creates a throwaway workspace, runs the full orchestration pipeline with the
offline ``DemoAgent`` backend and an auto-approving checkpoint handler, and
exits 0 if the pipeline completes. Nothing leaves the machine.

To use a real backend instead, drop ``agent_cls``/``checkpoint_handler`` and
run ``akms orchestrate --goal "..." --backend claude`` in a real repository:
gates are then answered through ``knowledge/checkpoints/`` response files.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

from akms.orchestrator.checkpoint import CheckpointAction, CheckpointHandler
from akms.orchestrator.orchestrator import run_pipeline

from demo_backend import DemoAgent


class AutoApproveHandler(CheckpointHandler):
    """Approve every gate, printing what a human reviewer would have seen.

    Interactive runs should keep the default file-based handler; auto-approval
    belongs only in demos and tests, where the artifacts are known in advance.
    """

    def present(self, state, stage_output, akms_status, warnings, repo_root):
        print(f"  [gate] stage={state.current_stage.name} -> APPROVE ({len(warnings)} warnings)")
        return CheckpointAction.APPROVE


def make_workspace(root: Path) -> Path:
    if root.exists():
        shutil.rmtree(root)
    for sub in ["graph", "local-nodes", "sessions", "loadouts", "code-mirror", "qmd"]:
        (root / "knowledge" / sub).mkdir(parents=True)
    (root / "knowledge" / "graph" / "local_state.yaml").write_text(
        "akms_schema: v2\nnodes: {}\n"
    )
    return root


def main() -> int:
    workspace = make_workspace(
        Path(sys.argv[1]) if len(sys.argv) > 1 else Path("demo-workspace")
    )
    print(f"workspace: {workspace.resolve()}")
    state = asyncio.run(
        run_pipeline(
            repo_root=workspace,
            goal="Demonstrate the embedded runtime offline",
            agent_cls=DemoAgent,
            checkpoint_handler=AutoApproveHandler(),
        )
    )
    completed = getattr(state, "completed", False) and not state.aborted
    print(f"pipeline {'COMPLETED' if completed else 'DID NOT COMPLETE'} "
          f"(stage={state.current_stage.name}, aborted={state.aborted})")
    sessions = sorted((workspace / "knowledge" / "sessions").glob("*.md"))
    print(f"agent memories written: {[p.name for p in sessions]}")
    return 0 if completed else 1


if __name__ == "__main__":
    sys.exit(main())
