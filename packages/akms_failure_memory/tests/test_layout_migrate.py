"""`failure-memory migrate-layout`: move a project's knowledge/ to .knowledge/."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from akms.graph.build_graph import build_graph

from akms_failure_memory.cli import main
from akms_failure_memory.compiler import run_compiler
from akms_failure_memory.config import load_project_config
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.layout_migrate import migrate_layout
from akms_failure_memory.project import render_project_config
from akms_failure_memory.record import add_lesson


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


def _legacy_project(tmp_path: Path, *, akms_root: str = ".") -> tuple[Path, Path, Path]:
    """A project laid out as `init` wrote it before `.knowledge/` was the default."""
    repo = tmp_path / "repo"
    repo.mkdir()
    knowledge = "knowledge" if akms_root == "." else f"{akms_root}/knowledge"
    text = render_project_config("demo-repo", "demo-failure").decode("utf-8")
    text = text.replace(".knowledge/", f"{knowledge}/")
    text = text.replace('akms_repo_root = "."', f'akms_repo_root = "{akms_root}"')
    config = repo / knowledge / "failure-memory.toml"
    config.parent.mkdir(parents=True)
    config.write_text(text, encoding="utf-8")
    registry = repo / knowledge / "lessons.json"
    registry.write_text(
        json.dumps({"schema_version": 1, "_field_spec": {}, "lessons": []}) + "\n",
        encoding="utf-8",
    )
    for relative in ("src/demo.py", "tests/test_demo.py"):
        (repo / relative).parent.mkdir(parents=True, exist_ok=True)
        (repo / relative).touch()
    vault = tmp_path / "vault"
    vault.mkdir()
    add_lesson(
        config_path=config,
        repository_root=repo,
        global_vault=vault,
        request_path=_request(repo),
    )
    return repo, config, vault


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def test_check_reports_the_plan_and_changes_nothing(tmp_path: Path) -> None:
    repo, config, _ = _legacy_project(tmp_path)

    result = migrate_layout(config_path=config, repository_root=repo, check=True)

    assert result["status"] == "checked"
    assert result["config"] == ".knowledge/failure-memory.toml"
    keys = {edit["key"] for edit in result["config_edits"]}
    assert {"paths.registry", "paths.graph", "compatibility.generated_warning"} <= keys
    assert (repo / "knowledge").is_dir()
    assert not (repo / ".knowledge").exists()


def test_migration_moves_rewrites_and_recompiles(tmp_path: Path) -> None:
    repo, config, vault = _legacy_project(tmp_path)
    before = (repo / "knowledge/lessons.json").read_bytes()

    result = migrate_layout(
        config_path=config, repository_root=repo, global_vault=vault
    )

    assert result["status"] == "migrated"
    assert result["compile"] == "written"
    assert not (repo / "knowledge").exists()
    assert (repo / ".knowledge/lessons.json").read_bytes() == before
    migrated = load_project_config(repo / ".knowledge/failure-memory.toml")
    assert all(
        value.startswith(".knowledge/")
        for key, value in migrated.paths.items()
        if key != "akms_repo_root"
    )
    assert "edit .knowledge/lessons.json" in migrated.compatibility["generated_warning"]
    # The lock moved with the directory and was released there.
    assert not (repo / ".knowledge/.failure-memory.lock").exists()
    assert (
        run_compiler(
            config_path=repo / ".knowledge/failure-memory.toml",
            repository_root=repo,
            global_vault=vault,
            mode="check",
        )["status"]
        == "clean"
    )
    graph = build_graph(repo, global_vault=vault)
    assert "demo-failure-l001" in graph


def test_without_a_vault_it_names_the_compile_step(tmp_path: Path) -> None:
    repo, config, _ = _legacy_project(tmp_path)

    result = migrate_layout(config_path=config, repository_root=repo)

    assert result["status"] == "migrated"
    assert result["next"].startswith(
        "failure-memory compile --config .knowledge/failure-memory.toml"
    )


def test_nested_akms_root_and_git_history(tmp_path: Path) -> None:
    repo, config, vault = _legacy_project(tmp_path, akms_root="dev")
    (repo / ".gitignore").write_text("dev/knowledge/graph/\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(
        repo,
        "-c",
        "user.email=t@example.invalid",
        "-c",
        "user.name=t",
        "commit",
        "-qm",
        "x",
    )

    result = migrate_layout(
        config_path=config, repository_root=repo, global_vault=vault
    )

    assert result["layout"]["move"] == "git-mv"
    assert result["config"] == "dev/.knowledge/failure-memory.toml"
    assert (repo / ".gitignore").read_text(
        encoding="utf-8"
    ) == "dev/.knowledge/graph/\n"
    status = _git(repo, "status", "--porcelain")
    assert "R  dev/knowledge/lessons.json -> dev/.knowledge/lessons.json" in status


def test_repairs_a_config_after_akms_moved_the_directory(tmp_path: Path) -> None:
    from akms.layout import migrate_knowledge_layout

    repo, config, vault = _legacy_project(tmp_path)
    migrate_knowledge_layout(repo)
    moved_config = repo / ".knowledge/failure-memory.toml"

    result = migrate_layout(
        config_path=moved_config, repository_root=repo, global_vault=vault
    )

    assert result["status"] == "migrated"
    assert result["layout"]["status"] == "already_migrated"
    assert (
        load_project_config(moved_config).paths["registry"] == ".knowledge/lessons.json"
    )


def test_a_migrated_project_is_left_alone(tmp_path: Path) -> None:
    repo, config, vault = _legacy_project(tmp_path)
    migrate_layout(config_path=config, repository_root=repo, global_vault=vault)

    result = migrate_layout(
        config_path=repo / ".knowledge/failure-memory.toml", repository_root=repo
    )

    assert result["status"] == "already_migrated"


def test_both_directories_present_is_refused(tmp_path: Path) -> None:
    repo, config, _ = _legacy_project(tmp_path)
    (repo / ".knowledge").mkdir()
    (repo / ".knowledge/stray.md").write_text("x\n", encoding="utf-8")

    with pytest.raises(FailureMemoryError) as error:
        migrate_layout(config_path=config, repository_root=repo)

    assert error.value.code == "layout_both_present"
    assert (repo / "knowledge/lessons.json").is_file()


def test_cli_falls_back_to_the_legacy_config_path(tmp_path: Path, capsys) -> None:
    repo, _, _ = _legacy_project(tmp_path)

    assert main(["migrate-layout", "--repo", str(repo), "--check"]) == 0

    assert json.loads(capsys.readouterr().out)["status"] == "checked"
