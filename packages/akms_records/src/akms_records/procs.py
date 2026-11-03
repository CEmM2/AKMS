"""Process liveness for temp-file cleanup.

A writer names its temp file after its process ID. Cleanup removes a temp file
only when that process is gone (or the file is older than a bound that covers
PID reuse). This assumes every writer runs on the same host; stores on shared
or network drives are not supported.
"""

from __future__ import annotations

import os
import sys

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
_ERROR_ACCESS_DENIED = 5


def _windows_pid_alive(pid: int) -> bool:
    """Liveness probe for Windows that sends no signal.

    ``os.kill(pid, 0)`` is not a probe on Windows: signal 0 is
    ``signal.CTRL_C_EVENT``, so CPython calls ``GenerateConsoleCtrlEvent``,
    which delivers Ctrl-C to every process on the caller's console (the caller
    included) and "succeeds" whether or not ``pid`` exists. This opens the
    process with query rights and reads its exit code instead.
    """
    # Also narrows ctypes' Windows-only API (WinDLL, get_last_error) for type checkers.
    if sys.platform != "win32":
        raise OSError("the Windows liveness probe only runs on Windows")
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    )
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        # Access denied: the process exists but may not be queried, the same
        # "alive" answer PermissionError gives on POSIX. Anything else
        # (ERROR_INVALID_PARAMETER) means there is no such process.
        return ctypes.get_last_error() == _ERROR_ACCESS_DENIED
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return True  # cannot tell; never delete a live writer's file
        return code.value == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def pid_alive(pid: int) -> bool:
    """Whether process ``pid`` is running on this host."""
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if sys.platform == "win32":
        return _windows_pid_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


__all__ = ["pid_alive"]
