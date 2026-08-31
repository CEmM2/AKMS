from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

import akms_failure_memory
from akms_failure_memory.config import load_project_config
from akms_failure_memory.errors import FailureMemoryError


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PACKAGE_ROOT / "tests/fixtures/project_configs"


def test_package_metadata_and_dependency_direction() -> None:
    assert akms_failure_memory.__version__ == "0.3.0"
    assert not any(name.startswith("repo2md") for name in sys.modules)
    assert not any(name.lower().startswith("numerix") for name in sys.modules)


def test_akms_core_has_no_reverse_dependency() -> None:
    core = PACKAGE_ROOT.parent / "AKMS/src/akms"
    offenders = [
        path
        for path in core.rglob("*.py")
        if "akms_failure_memory" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_config_load_is_canonical_and_project_distinct() -> None:
    first = load_project_config(FIXTURES / "numerixweave.toml")
    repeated = load_project_config(FIXTURES / "numerixweave.toml")
    second = load_project_config(FIXTURES / "second_project.toml")
    assert first.fingerprint == repeated.fingerprint
    assert first.fingerprint != second.fingerprint
    assert first.node_namespace != second.node_namespace


def test_duplicate_toml_key_fails(tmp_path: Path) -> None:
    config = tmp_path / "bad.toml"
    config.write_text(
        'schema_version = "failure-memory-project/v1"\n'
        'schema_version = "failure-memory-project/v1"\n',
        encoding="utf-8",
    )
    with pytest.raises(FailureMemoryError, match="Cannot load"):
        load_project_config(config)


def test_path_escape_and_symlink_escape_fail(tmp_path: Path) -> None:
    config = load_project_config(FIXTURES / "second_project.toml")
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    (repo / ".failure-memory").symlink_to(outside, target_is_directory=True)
    with pytest.raises(FailureMemoryError, match="escapes repository root"):
        config.resolve(repo, "registry")


def test_cli_help_version_and_json_error() -> None:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(PACKAGE_ROOT / "src"), str(PACKAGE_ROOT.parent / "AKMS/src")]
    )
    version = subprocess.run(
        [sys.executable, "-m", "akms_failure_memory.cli", "--version"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert version.returncode == 0
    assert version.stdout.strip() == "failure-memory 0.3.0"
    help_result = subprocess.run(
        [sys.executable, "-m", "akms_failure_memory.cli", "--help"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert help_result.returncode == 0
    assert "resolve" in help_result.stdout
    error = subprocess.run(
        [
            sys.executable,
            "-m",
            "akms_failure_memory.cli",
            "--json-errors",
            "validate",
            "--config",
            "missing.toml",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert error.returncode == 2
    assert '"status": "error"' in error.stdout
