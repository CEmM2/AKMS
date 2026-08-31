"""FileCheckpointHandler: unattended runs terminate quickly, attended runs wait."""

from __future__ import annotations

import io


from akms.orchestrator.checkpoint import (
    CheckpointAction,
    FileCheckpointHandler,
    write_checkpoint_response,
)
from akms.orchestrator.stages import PipelineState, Stage


class TestTimeoutPolicy:
    def test_explicit_timeout_wins(self, monkeypatch):
        handler = FileCheckpointHandler(timeout=123.0)
        assert handler._effective_timeout() == 123.0

    def test_headless_default_is_short(self, monkeypatch):
        import sys

        monkeypatch.setattr(sys, "stdin", io.StringIO(""))  # not a tty
        handler = FileCheckpointHandler()
        assert handler._effective_timeout() == FileCheckpointHandler.HEADLESS_TIMEOUT

    def test_interactive_default_is_long(self, monkeypatch):
        import sys

        class FakeTty(io.StringIO):
            def isatty(self):
                return True

        monkeypatch.setattr(sys, "stdin", FakeTty())
        handler = FileCheckpointHandler()
        assert handler._effective_timeout() == FileCheckpointHandler.INTERACTIVE_TIMEOUT

    def test_closed_stdin_counts_as_headless(self, monkeypatch):
        import sys

        class Detached:
            def isatty(self):
                raise ValueError("I/O operation on closed file")

        monkeypatch.setattr(sys, "stdin", Detached())
        handler = FileCheckpointHandler()
        assert handler._effective_timeout() == FileCheckpointHandler.HEADLESS_TIMEOUT


class TestPresent:
    def _state(self) -> PipelineState:
        state = PipelineState(goal="g", plan_name="p")
        state.current_stage = Stage.PLAN
        return state

    def test_timeout_aborts_quickly_with_guidance(self, tmp_path, capsys):
        handler = FileCheckpointHandler(timeout=0.2, poll_interval=0.05)
        action = handler.present(self._state(), "out", "status", [], tmp_path)
        assert action == CheckpointAction.ABORT
        err = capsys.readouterr().err
        assert "_response.yaml" in err
        assert "--resume" in err

    def test_prewritten_response_is_honored(self, tmp_path):
        # Write the response as soon as the checkpoint file appears by
        # pre-creating it via the same naming scheme present() uses.
        import threading
        import time

        handler = FileCheckpointHandler(timeout=5.0, poll_interval=0.05)
        result: list[CheckpointAction] = []

        def respond():
            deadline = time.time() + 4
            while time.time() < deadline:
                cps = list((tmp_path / "knowledge" / "checkpoints").glob("*.yaml"))
                cps = [c for c in cps if not c.stem.endswith("_response")]
                if cps:
                    write_checkpoint_response(cps[0], "approve")
                    return
                time.sleep(0.05)

        t = threading.Thread(target=respond)
        t.start()
        result.append(handler.present(self._state(), "out", "status", [], tmp_path))
        t.join()
        assert result[0] == CheckpointAction.APPROVE
