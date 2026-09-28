"""Public smoke test: the installed `akms-pick` serves with no inputs at all.

A fresh `uv tool install akms-nodes-gen` has no plan, no Zotero export and no
zsum vault. The picker must still start, and its status endpoint must say what
is missing. Building the FastAPI app is part of this: a route the installed
FastAPI rejects fails here rather than on a user's first run.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("akms_nodes_gen")

BIN = Path(sys.executable).parent


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.e2e
def test_picker_starts_empty_and_reports_missing_inputs(tmp_path):
    port = _free_port()
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("AKMS_", "PYTHON"))
    }
    env["HOME"] = str(tmp_path / "home")
    proc = subprocess.Popen(
        [str(BIN / "akms-pick"), "--no-browser", "--port", str(port)],
        cwd=tmp_path,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        status = None
        for _ in range(60):
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/status", timeout=2
                ) as response:
                    status = json.load(response)
                break
            except OSError:
                time.sleep(0.5)
        assert status is not None, (
            proc.communicate(timeout=5)[0] if proc.poll() else "no response"
        )
        levels = [notice["level"] for notice in status["notices"]]
        assert "error" in levels, status
        assert any("zsum" in notice["message"] for notice in status["notices"])
    finally:
        proc.terminate()
        proc.wait(timeout=10)
