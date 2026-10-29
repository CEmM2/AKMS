"""ProjectLock's owner-liveness probe on POSIX and Windows.

On Windows ``os.kill(pid, 0)`` is not a probe: signal 0 is ``CTRL_C_EVENT``,
so it sends Ctrl-C to every process on the console and never reports a dead
owner. These tests pin the alive/dead answers on both platforms and, on
Windows, that probing raises no console control event.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys

import pytest

from akms_failure_memory.locks import ProjectLock

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows probe")
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX probe")


def _finished_pid() -> int:
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid


@pytest.mark.parametrize("pid", [0, -1])
def test_non_positive_pid_is_dead(pid: int) -> None:
    assert ProjectLock._pid_alive(pid) is False


def test_own_pid_is_alive() -> None:
    assert ProjectLock._pid_alive(os.getpid()) is True


def test_finished_child_is_dead() -> None:
    assert ProjectLock._pid_alive(_finished_pid()) is False


@posix_only
def test_posix_probe_sends_signal_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: calls.append((pid, sig)))
    assert ProjectLock._pid_alive(12345) is True
    assert calls == [(12345, 0)]


@windows_only
def test_windows_probe_never_calls_os_kill(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(pid: int, sig: int) -> None:
        raise AssertionError(f"os.kill({pid}, {sig}) would send a console event")

    monkeypatch.setattr(os, "kill", forbidden)
    assert ProjectLock._pid_alive(os.getpid()) is True
    assert ProjectLock._pid_alive(_finished_pid()) is False


@windows_only
def test_windows_unknown_pid_is_dead() -> None:
    # Windows PIDs are multiples of 4, so an odd value can never be live.
    assert ProjectLock._pid_alive(0x7FFFFFFD) is False


@windows_only
def test_windows_probing_raises_no_console_interrupt() -> None:
    received: list[int] = []
    previous = signal.signal(
        signal.SIGINT, lambda signum, frame: received.append(signum)
    )
    try:
        for _ in range(100):
            ProjectLock._pid_alive(os.getpid())
            ProjectLock._pid_alive(0x7FFFFFFD)
    finally:
        signal.signal(signal.SIGINT, previous)
    assert received == []
