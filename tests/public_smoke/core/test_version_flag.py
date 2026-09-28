"""Public smoke test: ``akms --version`` against the installed package.

Host adapters probe ``akms --version`` before ``--help`` to decide whether
they can enforce a supported-version range; until the command existed they
had to report an unknown version. The contract is ``akms <version>`` on
stdout with exit status 0, where the version is the installed distribution's
metadata rather than a literal that can drift from ``pyproject.toml``.
"""

from __future__ import annotations

import re
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

BIN = Path(sys.executable).parent


def test_version_flag_reports_distribution_version() -> None:
    result = subprocess.run(
        [str(BIN / "akms"), "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    reported = result.stdout.strip()
    assert reported == f"akms {version('akms')}"
    assert re.fullmatch(r"akms \d+\.\d+\.\d+\S*", reported), reported
