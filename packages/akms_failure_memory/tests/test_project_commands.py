from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from akms_failure_memory.compiler import run_compiler
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.project import (
    doctor,
    generate_wrapper,
    init_project,
    migration_check,
)
from akms_failure_memory.record import add_lesson


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
COMPAT_CONFIG = PACKAGE_ROOT / "tests/fixtures/project_configs/numerixweave.toml"
COMPAT_REGISTRY = (
    PACKAGE_ROOT / "tests/fixtures/numerixweave_phase1/source_registry.json"
)


def _request(repo: Path) -> Path:
    request = {
        "date_found": "2026-08-11",
        "date_found_precision": "exact",
        "date_fixed": "2026-08-11",
        "date_fixed_precision": "exact",
        "location": {
            "area": "tool",
            "package": "demo",
            "module": "demo",
            "file": "src/demo.py",
            "symbol": "run",
            "line_hint": "demo failure",
        },
        "found_by": {"type": "test", "trigger": "tests/test_demo.py::test_demo"},
        "symptom": "Failure.",
        "root_cause": "Cause.",
        "fix": "Fix.",
        "prevention": "tests/test_demo.py prevents recurrence.",
        "references": {"commit": "abc", "issue": "", "pr": "", "plan": ""},
        "related": [],
    }
    path = repo / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    return path


def test_fresh_init_record_compile_and_doctor(tmp_path: Path) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    result = init_project(
        repository_root=repo,
        config_path=".failure-memory/config.toml",
        repository_id="demo-repo",
        node_namespace="demo-failure",
    )
    config = repo / result["config"]
    vault = tmp_path / "global"
    vault.mkdir()
    for relative in ("src/demo.py", "tests/test_demo.py"):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    created = add_lesson(
        config_path=config,
        repository_root=repo,
        global_vault=vault,
        request_path=_request(repo),
    )
    assert created["record"]["id"] == "L001"
    assert (
        run_compiler(
            config_path=config, repository_root=repo, global_vault=vault, mode="check"
        )["status"]
        == "clean"
    )
    assert doctor(config_path=config, repository_root=repo)["status"] == "ok"


def test_init_and_wrapper_refuse_overwrite(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    result = init_project(repository_root=repo, config_path="config.toml")
    config = repo / result["config"]
    with pytest.raises(FailureMemoryError, match="Refusing to overwrite"):
        init_project(repository_root=repo, config_path="config.toml")
    wrapper = generate_wrapper(
        config_path=config, repository_root=repo, output="tools/failure-memory"
    )
    assert (repo / wrapper["wrapper"]).stat().st_mode & 0o111
    with pytest.raises(FailureMemoryError, match="Refusing to overwrite"):
        generate_wrapper(
            config_path=config, repository_root=repo, output="tools/failure-memory"
        )


def test_phase1_layout_is_report_only(tmp_path: Path) -> None:
    repo = tmp_path / "compat"
    registry = repo / "dev/lessons_from_failing.json"
    registry.parent.mkdir(parents=True)
    registry.write_bytes(COMPAT_REGISTRY.read_bytes())
    before = registry.read_bytes()
    result = migration_check(config_path=COMPAT_CONFIG, repository_root=repo)
    assert result["status"] == "recognized"
    assert result["rewrite_performed"] is False
    assert registry.read_bytes() == before


def test_wrapper_quotes_config_as_one_literal_argument(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    config_name = "config $(touch${IFS}PWNED) `touch PWNED2` ' quote.toml"
    init_project(repository_root=repo, config_path=config_name)
    generate_wrapper(
        config_path=repo / config_name,
        repository_root=repo,
        output="tools/failure-memory-wrapper",
    )
    executable = tmp_path / "bin/failure-memory"
    executable.parent.mkdir()
    executable.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURE"\n', encoding="utf-8"
    )
    executable.chmod(0o755)
    capture = tmp_path / "argv"
    environment = dict(os.environ)
    environment["PATH"] = f"{executable.parent}:{environment['PATH']}"
    environment["CAPTURE"] = str(capture)
    subprocess.run(
        [str(repo / "tools/failure-memory-wrapper"), "check"],
        cwd=repo,
        env=environment,
        check=True,
    )
    assert capture.read_text().splitlines() == ["check", "--config", config_name]
    assert not (repo / "PWNED").exists()
    assert not (repo / "PWNED2").exists()


def test_init_rejects_symlink_escape(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    (repo / ".failure-memory").symlink_to(outside, target_is_directory=True)
    with pytest.raises(FailureMemoryError, match="outside|escapes"):
        init_project(repository_root=repo, config_path=".failure-memory/config.toml")
