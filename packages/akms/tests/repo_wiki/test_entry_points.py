"""The three ways to run repo-wiki: the console script, ``akms wiki`` and ``-m``."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from akms.cli.commands import main as akms_main

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCAN_REPO = FIXTURES / "scan_repo"


def _scanned(stdout: str) -> list[str]:
    return [entry["path"] for entry in json.loads(stdout)["files"]]


@pytest.mark.integration
def test_akms_wiki_maps_repo_to_repo_root(capsys):
    assert akms_main(["--repo", str(SCAN_REPO), "wiki", "scan", "--json"]) == 0

    assert _scanned(capsys.readouterr().out) == ["src/app.py"]


@pytest.mark.integration
def test_akms_wiki_repo_root_after_wiki_wins(tmp_path: Path, capsys):
    argv = ["--repo", str(tmp_path), "wiki", "--repo-root", str(SCAN_REPO)]

    assert akms_main([*argv, "scan", "--json"]) == 0

    assert _scanned(capsys.readouterr().out) == ["src/app.py"]


@pytest.mark.integration
def test_akms_wiki_passes_help_through(capsys):
    with pytest.raises(SystemExit) as exit_info:
        akms_main(["wiki", "--help"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out.startswith("usage: repo-wiki")


@pytest.mark.integration
def test_python_dash_m_runs_repo_wiki():
    completed = subprocess.run(
        [sys.executable, "-m", "akms.repo_wiki", "--repo-root", str(SCAN_REPO)]
        + ["scan", "--json"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert _scanned(completed.stdout) == ["src/app.py"]
