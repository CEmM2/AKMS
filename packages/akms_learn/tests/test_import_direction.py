"""Authoritative one-way import direction tests for akms_learn.

Covers:
- Packages/AKMS source tree must NOT contain `import akms_learn` or
  `from akms_learn ...` statements.
- `akms_learn` is allowed to import `akms` (one-way direction).
- `importlib.metadata.distribution('akms-learn')` resolves.
"""

from __future__ import annotations

import ast
import importlib
import importlib.metadata
import subprocess
import sys
from pathlib import Path

import pytest

# Repo root is three levels above this test file:
#   packages/akms_learn/tests/test_import_direction.py
# -> packages/akms_learn/tests
# -> packages/akms_learn
# -> packages
# -> AKMS  (repo root has a top-level AKMS/ dir AND a Packages/ dir)
REPO_ROOT = Path(__file__).resolve().parents[3]
AKMS_CORE_SRC = REPO_ROOT / "packages" / "akms" / "src"


def _akms_learn_references(py_path: Path) -> list[str]:
    """Return offending import statement descriptions, if any."""
    try:
        source = py_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(source, filename=str(py_path))
    except SyntaxError:
        return []
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "akms_learn" or alias.name.startswith("akms_learn."):
                    offenders.append(f"{py_path}:{node.lineno} import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "akms_learn" or mod.startswith("akms_learn."):
                offenders.append(f"{py_path}:{node.lineno} from {mod}")
    return offenders


@pytest.mark.unit
def test_akms_core_does_not_import_akms_learn() -> None:
    """Scan Packages/AKMS/src/**/*.py; assert no akms_learn imports."""
    assert AKMS_CORE_SRC.is_dir(), f"Missing AKMS core source tree: {AKMS_CORE_SRC}"
    offenders: list[str] = []
    for py_file in AKMS_CORE_SRC.rglob("*.py"):
        offenders.extend(_akms_learn_references(py_file))
    assert not offenders, (
        "AKMS core must not import akms_learn (one-way direction violated):\n"
        + "\n".join(offenders)
    )


@pytest.mark.unit
def test_akms_learn_may_import_akms() -> None:
    """akms_learn -> akms is the allowed direction; verify it works."""
    # Importing akms_learn must succeed.
    akms_learn = importlib.import_module("akms_learn")
    assert akms_learn is not None
    # And importing akms from the same interpreter must not raise.
    proc = subprocess.run(
        [sys.executable, "-c", "import akms_learn; import akms; print('ok')"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"Importing akms_learn then akms failed:\nstdout={proc.stdout!r}\n"
        f"stderr={proc.stderr!r}"
    )
    assert "ok" in proc.stdout


@pytest.mark.unit
def test_package_metadata_resolves() -> None:
    """`importlib.metadata.distribution('akms-learn')` must resolve."""
    dist = importlib.metadata.distribution("akms-learn")
    # Distribution name normalization: PEP 503 canonical form.
    assert dist.metadata["Name"].lower().replace("_", "-") == "akms-learn"
