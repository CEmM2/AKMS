from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from akms_failure_memory.ci import ci_check, release_source_digest
from akms_failure_memory.compiler import run_compiler
from akms_failure_memory.errors import FailureMemoryError


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PACKAGE_ROOT.parents[1]
FM_DOCS = REPO_ROOT / "docs/reference/failure-memory"
CONFIG_SOURCE = PACKAGE_ROOT / "tests/fixtures/project_configs/numerixweave.toml"
REGISTRY_SOURCE = (
    PACKAGE_ROOT / "tests/fixtures/numerixweave_phase1/source_registry.json"
)


def _project(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    registry = repo / "dev/lessons_from_failing.json"
    registry.parent.mkdir(parents=True)
    registry.write_bytes(REGISTRY_SOURCE.read_bytes())
    config = repo / "failure-memory.toml"
    config.write_bytes(CONFIG_SOURCE.read_bytes())
    vault = tmp_path / "vault"
    vault.mkdir()
    run_compiler(
        config_path=config,
        repository_root=repo,
        global_vault=vault,
        mode="write",
    )
    return repo, config


def test_ci_check_is_hermetic_and_detects_generated_drift(tmp_path: Path) -> None:
    repo, config = _project(tmp_path)
    result = ci_check(config_path=config, repository_root=repo)
    assert result["status"] == "ok"
    assert result["compatibility_fixture"]["failure_routes.json"] == (
        "8511ce591438117df146bb75e6e9eac88ef9251cbbf1bc160de20e36e3966171"
    )
    generated = (
        repo / "dev/knowledge/local-nodes/generated/failure-lessons/nw-failure-l900.md"
    )
    generated.write_text(generated.read_text() + "drift\n")
    with pytest.raises(FailureMemoryError, match="drift"):
        ci_check(config_path=config, repository_root=repo)


def test_docs_commands_and_policy_are_present() -> None:
    adoption = (FM_DOCS / "adoption.md").read_text()
    policy = (FM_DOCS / "operator-policy.md").read_text()
    for command in (
        "failure-memory init",
        "failure-memory add --interactive",
        "failure-memory add --from-json",
        "failure-memory refresh preflight",
        "failure-memory resolve",
        "failure-memory validate-fingerprint",
        "failure-memory ci-check",
    ):
        assert command in adoption
    assert "global AKMS vault as read-only" in policy
    assert "External publication" in policy


def test_akms_core_import_has_no_optional_package_dependency(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "packages/akms/src")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, akms; assert 'akms_failure_memory' not in sys.modules; print(akms.AKMS_SCHEMA_VERSION)",
        ],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "v2"


@pytest.mark.skipif(
    not (PACKAGE_ROOT / "release").exists(),
    reason=(
        "The curated public tree ships no release pin: the private pin "
        "describes the private release-candidate tree (different docs layout "
        "and supersession narrative) and cannot truthfully describe this one. "
        "A public pin is generated when a public release is actually cut."
    ),
)
def test_release_pin_is_closed_and_truthful() -> None:
    pin = json.loads(
        (PACKAGE_ROOT / "release/akms_failure_memory-0.3.0.json").read_text()
    )
    assert pin["package"] == "akms-failure-memory"
    assert pin["version"] == "0.3.0"
    assert pin["external_publication"]["status"] == "operator-action-required"
    assert len(pin["source_tree_sha256"]) == 64
    assert len(pin["wheel_sha256"]) == 64
    assert pin["source_tree_sha256"] == release_source_digest(PACKAGE_ROOT)
