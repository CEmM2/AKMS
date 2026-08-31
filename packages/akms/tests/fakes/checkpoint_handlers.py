"""Test-only checkpoint handlers for E2E and integration tests."""

from __future__ import annotations

from akms.orchestrator.checkpoint import CheckpointHandler
from akms.orchestrator.stages import CheckpointAction


class AutoApproveCheckpointHandler(CheckpointHandler):
    """Auto-approves all checkpoints. Records which stages were seen."""

    def __init__(self):
        self.checkpoints_seen: list[str] = []

    def present(self, state, stage_output, akms_status, warnings, repo_root):
        self.checkpoints_seen.append(state.current_stage.name)
        return CheckpointAction.APPROVE


class AbortThenApproveHandler(CheckpointHandler):
    """Aborts on first checkpoint, approves all subsequent ones."""

    def __init__(self):
        self.call_count = 0

    def present(self, state, stage_output, akms_status, warnings, repo_root):
        self.call_count += 1
        if self.call_count == 1:
            return CheckpointAction.ABORT
        return CheckpointAction.APPROVE


class RecordingCheckpointHandler(CheckpointHandler):
    """Records checkpoint presentations and replays a fixed action sequence.

    Useful for migration tests that need to verify checkpoint flow without
    file I/O or terminal interaction.
    """

    def __init__(self, actions: list[CheckpointAction]):
        self._actions = list(actions)
        self.presentations: list[dict] = []

    def present(self, state, stage_output, akms_status, warnings, repo_root):
        self.presentations.append(
            {
                "stage": state.current_stage.name,
                "phase": state.current_phase,
                "output_preview": stage_output[:200],
                "warnings": warnings,
            }
        )
        if self._actions:
            return self._actions.pop(0)
        return CheckpointAction.ABORT
