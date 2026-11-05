"""Package metadata, dependency direction, and an installed-wheel smoke test."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from importlib.metadata import version as dist_version
from pathlib import Path

import pytest

import akms_records

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PACKAGE_ROOT / "src" / "akms_records"


def test_version_matches_distribution():
    assert akms_records.__version__ == dist_version("akms-records")


def test_does_not_import_akms_or_failure_memory():
    """Only the bridge names akms, and only inside a function."""
    pattern = re.compile(
        r"^\s*(?:import|from)\s+(akms|akms_failure_memory)(?:\.|\s|$)", re.M
    )
    offenders = [
        path.name
        for path in SOURCE.rglob("*.py")
        if path.name != "bridge.py" and pattern.search(path.read_text("utf-8"))
    ]
    assert offenders == []
    top_level = re.compile(r"^(?:import|from)\s+(?:akms|frontmatter)(?:\.|\s|$)", re.M)
    assert not top_level.search((SOURCE / "bridge.py").read_text("utf-8"))


def test_importing_the_package_and_its_cli_loads_no_akms():
    code = (
        "import sys, akms_records, akms_records.bridge, akms_records.cli, "
        "akms_records.failure_memory\n"
        "bad = [m for m in sys.modules if m.split('.')[0] in "
        "('akms', 'akms_failure_memory', 'frontmatter')]\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def test_windows_probe_does_not_use_os_kill(monkeypatch):
    from akms_records import procs

    if sys.platform == "win32":

        def forbidden(pid: int, sig: int) -> None:
            raise AssertionError("os.kill would send a console control event")

        monkeypatch.setattr(os, "kill", forbidden)
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait()
    assert procs.pid_alive(os.getpid()) is True
    assert procs.pid_alive(finished.pid) is False
    assert procs.pid_alive(0) is False


def test_installed_wheel_runs_without_akms(tmp_path):
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed")
    dist = tmp_path / "dist"
    build = subprocess.run(
        [uv, "build", "--package", "akms-records", "--wheel", "--out-dir", str(dist)],
        cwd=PACKAGE_ROOT.parents[1],
        capture_output=True,
        text=True,
    )
    assert build.returncode == 0, build.stderr
    wheel = next(dist.glob("akms_records-*.whl"))
    venv = tmp_path / "venv"
    subprocess.run(
        [uv, "venv", "-q", "--python", sys.executable, str(venv)], check=True
    )
    bindir = venv / ("Scripts" if os.name == "nt" else "bin")
    python = bindir / ("python.exe" if os.name == "nt" else "python")
    install = subprocess.run(
        [uv, "pip", "install", "-q", "--python", str(python), str(wheel)],
        capture_output=True,
        text=True,
    )
    assert install.returncode == 0, install.stderr
    script = bindir / ("akms-records.exe" if os.name == "nt" else "akms-records")
    env = {
        k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "VIRTUAL_ENV")
    }
    helped = subprocess.run(
        [str(script), "--help"], capture_output=True, text=True, env=env
    )
    assert helped.returncode == 0 and "akms-records" in helped.stdout
    probe = subprocess.run(
        [
            str(python),
            "-c",
            "import importlib.util as u; print(u.find_spec('akms') is None)",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert probe.stdout.strip() == "True"
    templates = subprocess.run(
        [str(script), "schema", "templates"], capture_output=True, text=True, env=env
    )
    assert templates.returncode == 0 and "decision" in templates.stdout
