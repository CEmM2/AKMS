"""checkpoint.py — File-Based Checkpoint Interface (§3 of system design).

Checkpoints are blocking pause points where the developer reviews and approves
before the next stage begins. At each checkpoint, the orchestrator presents:

1. **Stage output** — the primary artifact (plan, task JSONs, PCD, review report)
2. **AKMS status** — new/modified nodes, confidence changes, pitfalls added
3. **Action menu** — stage-specific options (approve, reject, edit, abort)
4. **Warnings** — any graph health issues

The developer's response is one of:
- ``approve`` → proceed to next stage
- ``reject [reason]`` → re-run the stage with feedback
- ``edit`` → developer modifies artifacts directly, then approves
- ``abort`` → halt, preserve all state for resumption

**File-based protocol:**
- Orchestrator writes: ``knowledge/checkpoints/{stage}_{timestamp}.yaml``
- Developer writes:   ``knowledge/checkpoints/{stage}_{timestamp}_response.yaml``
"""

from __future__ import annotations

import logging
import sys
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from akms.orchestrator.stages import CHECKPOINT_ACTIONS, CheckpointAction, Stage

if TYPE_CHECKING:
    from akms.orchestrator.stages import PipelineState

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Checkpoint Data Models
# ═══════════════════════════════════════════════════════════════════════


class CheckpointData:
    """Data structure for a checkpoint file."""

    def __init__(
        self,
        stage: Stage,
        status: str = "awaiting_review",
        stage_output: str = "",
        akms_status: dict | None = None,
        actions: list[str] | None = None,
        warnings: list[str] | None = None,
        phase: int | None = None,
        timestamp: str | None = None,
    ):
        self.stage = stage
        self.status = status
        self.stage_output = stage_output
        self.akms_status = akms_status or {}
        self.actions = actions or list(CHECKPOINT_ACTIONS)
        self.warnings = warnings or []
        self.phase = phase
        self.timestamp = timestamp or datetime.now().isoformat()

    def to_dict(self) -> dict:
        """Serialize to a dict for YAML output."""
        data: dict[str, Any] = {
            "stage": self.stage.name.lower(),
            "status": self.status,
            "timestamp": self.timestamp,
            "stage_output": self.stage_output,
            "akms_status": self.akms_status,
            "actions": self.actions,
            "warnings": self.warnings,
        }
        if self.phase is not None:
            data["phase"] = self.phase
        return data


class CheckpointResponse:
    """Response from the developer."""

    def __init__(
        self,
        action: str | CheckpointAction,
        reason: str = "",
        edits: dict | None = None,
    ):
        if isinstance(action, CheckpointAction):
            self.action = action.value
        else:
            self.action = str(action)
        self.reason = reason
        self.edits = edits or {}

    @classmethod
    def from_dict(cls, data: dict) -> CheckpointResponse:
        return cls(
            action=data.get("action", ""),
            reason=data.get("reason", ""),
            edits=data.get("edits", {}),
        )

    def is_approve(self) -> bool:
        return self.action == CheckpointAction.APPROVE.value

    def is_reject(self) -> bool:
        return self.action == CheckpointAction.REJECT.value

    def is_edit(self) -> bool:
        return self.action == CheckpointAction.EDIT.value

    def is_abort(self) -> bool:
        return self.action == CheckpointAction.ABORT.value


# ═══════════════════════════════════════════════════════════════════════
#  Checkpoint I/O
# ═══════════════════════════════════════════════════════════════════════


def _checkpoint_dir(repo_root: Path) -> Path:
    """Get the checkpoints directory."""
    d = repo_root / "knowledge" / "checkpoints"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _checkpoint_filename(stage: Stage, timestamp: str, phase: int | None = None) -> str:
    """Generate a checkpoint filename."""
    ts = timestamp.replace(":", "-").replace(".", "-")
    if phase is not None:
        return f"{stage.name.lower()}_phase{phase}_{ts}"
    return f"{stage.name.lower()}_{ts}"


def write_checkpoint(
    repo_root: Path,
    data: CheckpointData,
) -> Path:
    """Write a checkpoint YAML file.

    Args:
        repo_root: Repository root path.
        data: Checkpoint data to write.

    Returns:
        Path to the written checkpoint file.
    """
    cp_dir = _checkpoint_dir(repo_root)
    base = _checkpoint_filename(data.stage, data.timestamp, data.phase)
    cp_path = cp_dir / f"{base}.yaml"

    with open(cp_path, "w") as f:
        yaml.dump(data.to_dict(), f, default_flow_style=False, sort_keys=False)

    logger.info("Checkpoint written: %s", cp_path)
    return cp_path


def read_checkpoint_response(
    checkpoint_path: Path,
    timeout: float | None = None,
    poll_interval: float = 1.0,
) -> CheckpointResponse | None:
    """Read a checkpoint response file.

    The response file name is derived from the checkpoint path by appending
    ``_response``. Optionally polls for the file if ``timeout`` is set.

    Args:
        checkpoint_path: Path to the checkpoint YAML.
        timeout: Seconds to wait for response (None = no wait, just check).
        poll_interval: Seconds between polls.

    Returns:
        CheckpointResponse if found, None if timeout/not found.
    """
    response_path = checkpoint_path.with_name(checkpoint_path.stem + "_response.yaml")

    if timeout is None:
        if response_path.exists():
            with open(response_path) as f:
                data = yaml.safe_load(f)
            return CheckpointResponse.from_dict(data or {})
        return None

    deadline = time.time() + timeout
    while time.time() < deadline:
        if response_path.exists():
            with open(response_path) as f:
                data = yaml.safe_load(f)
            logger.info("Checkpoint response received: %s", response_path)
            return CheckpointResponse.from_dict(data or {})
        time.sleep(poll_interval)

    logger.warning("Checkpoint response timeout after %.1fs", timeout)
    return None


def write_checkpoint_response(
    checkpoint_path: Path,
    action: str,
    reason: str = "",
    edits: dict | None = None,
) -> Path:
    """Write a checkpoint response file (for testing / CLI).

    Args:
        checkpoint_path: Path to the original checkpoint YAML.
        action: One of: approve, reject, edit, abort.
        reason: Required for reject.
        edits: Optional edits dict.

    Returns:
        Path to the written response file.
    """
    response_path = checkpoint_path.with_name(checkpoint_path.stem + "_response.yaml")
    data: dict[str, Any] = {"action": action}
    if reason:
        data["reason"] = reason
    if edits:
        data["edits"] = edits

    with open(response_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False)

    logger.info("Checkpoint response written: %s → %s", action, response_path)
    return response_path


def list_checkpoints(repo_root: Path) -> list[dict]:
    """List all checkpoint files in the repository.

    Returns:
        List of dicts with keys: path, stage, status, timestamp, has_response.
    """
    cp_dir = _checkpoint_dir(repo_root)
    results = []

    for cp_file in sorted(cp_dir.glob("*.yaml")):
        if cp_file.stem.endswith("_response"):
            continue

        try:
            with open(cp_file) as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            continue

        response_path = cp_file.with_name(cp_file.stem + "_response.yaml")

        results.append(
            {
                "path": str(cp_file),
                "stage": data.get("stage", "unknown"),
                "status": data.get("status", "unknown"),
                "timestamp": data.get("timestamp", ""),
                "has_response": response_path.exists(),
            }
        )

    return results


# ═══════════════════════════════════════════════════════════════════════
#  Checkpoint Handler Abstractions
# ═══════════════════════════════════════════════════════════════════════


class CheckpointHandler(ABC):
    """Abstract base class for checkpoint presentation strategies.

    Implementations decide how to present a checkpoint to the developer
    (file-based polling, terminal prompt, auto-approve, etc.) and return
    a CheckpointAction indicating the developer's decision.
    """

    @abstractmethod
    def present(
        self,
        state: "PipelineState",
        stage_output: str,
        akms_status: str,
        warnings: list[str],
        repo_root: Path,
    ) -> CheckpointAction:
        """Present a checkpoint and return the developer's action.

        Args:
            state: Current pipeline state (stage, phase).
            stage_output: Primary artifact text for review.
            akms_status: AKMS status summary string.
            warnings: List of warning messages to display.
            repo_root: Repository root path.

        Returns:
            CheckpointAction indicating developer decision.
        """
        ...


class FileCheckpointHandler(CheckpointHandler):
    """Checkpoint handler that writes a YAML file and polls for a response file.

    Follows the write_checkpoint / read_checkpoint_response protocol.
    Returns ABORT on timeout, REJECT on unrecognised action string.

    Timeout policy: pass an explicit ``timeout`` for asynchronous file-based
    approval (a human answering from another terminal — the design use case
    for this handler). When ``timeout`` is left at its default (``None``),
    the wait adapts to the environment: an interactive run (stdin is a TTY)
    waits :data:`INTERACTIVE_TIMEOUT` seconds, while a non-interactive run
    (CI, cron, piped stdin) waits only :data:`HEADLESS_TIMEOUT` seconds —
    an unattended process must fail visibly within a minute, not block for
    an hour on a gate nothing will ever answer. Either way, the wait is
    announced on stderr with the exact response path and accepted actions.
    """

    #: Auto-policy wait when stdin is a TTY (a human is plausibly present).
    INTERACTIVE_TIMEOUT: float = 3600.0
    #: Auto-policy wait for non-interactive runs.
    HEADLESS_TIMEOUT: float = 60.0

    def __init__(self, timeout: float | None = None, poll_interval: float = 1.0):
        self.timeout = timeout
        self.poll_interval = poll_interval

    def _effective_timeout(self) -> float:
        if self.timeout is not None:
            return self.timeout
        try:
            interactive = sys.stdin.isatty()
        except (ValueError, OSError):  # stdin closed or detached
            interactive = False
        return self.INTERACTIVE_TIMEOUT if interactive else self.HEADLESS_TIMEOUT

    def present(
        self,
        state: "PipelineState",
        stage_output: str,
        akms_status: str,
        warnings: list[str],
        repo_root: Path,
    ) -> CheckpointAction:
        cp_data = CheckpointData(
            stage=state.current_stage,
            phase=state.current_phase if state.current_phase > 0 else None,
            stage_output=stage_output,
            akms_status={"status": akms_status},
            warnings=warnings,
        )
        cp_path = write_checkpoint(repo_root, cp_data)
        timeout = self._effective_timeout()
        response_path = cp_path.with_name(cp_path.stem + "_response.yaml")
        print(
            f"Checkpoint gate: {state.current_stage.name}. Waiting up to "
            f"{timeout:.0f}s for {response_path}\n"
            "  (respond with an 'action: approve|reject|edit|abort' YAML; "
            "pass an explicit timeout to FileCheckpointHandler for "
            "long-running asynchronous approval)",
            file=sys.stderr,
        )
        response = read_checkpoint_response(
            cp_path, timeout=timeout, poll_interval=self.poll_interval
        )
        if response is None:
            print(
                f"No checkpoint response within {timeout:.0f}s — aborting. "
                "State is saved; resume with --resume.",
                file=sys.stderr,
            )
            logger.warning("Checkpoint timeout — treating as abort")
            return CheckpointAction.ABORT
        try:
            return CheckpointAction(response.action)
        except ValueError:
            logger.warning("Unknown action '%s' — treating as reject", response.action)
            return CheckpointAction.REJECT


class TerminalCheckpointHandler(CheckpointHandler):
    """Checkpoint handler that uses print() / input() for interactive review.

    Suitable for local developer workflows where the orchestrator runs in
    a terminal session (per addendum §3.3.1, deviation D3).
    """

    def present(
        self,
        state: "PipelineState",
        stage_output: str,
        akms_status: str,
        warnings: list[str],
        repo_root: Path,
    ) -> CheckpointAction:
        print(f"\n{'=' * 60}")
        print(f"  CHECKPOINT: {state.current_stage.name} (phase {state.current_phase})")
        print(f"{'=' * 60}")
        print(f"\n--- Stage Output ---\n{stage_output}")
        print(f"\n--- AKMS Status ---\n{akms_status}")
        if warnings:
            print("\n--- Warnings ---")
            for w in warnings:
                print(f"  !  {w}")
        print("\nActions: [a]pprove  [r]eject  [e]dit  [x]abort")
        while True:
            choice = input("> ").strip().lower()
            if choice in ("a", "approve"):
                return CheckpointAction.APPROVE
            elif choice in ("r", "reject"):
                return CheckpointAction.REJECT
            elif choice in ("e", "edit"):
                return CheckpointAction.EDIT
            elif choice in ("x", "abort"):
                return CheckpointAction.ABORT
            print("Invalid choice. Try again.")
