"""Moving a repository's knowledge from ``knowledge/`` to ``.knowledge/``."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from akms.cli.commands import main
from akms.graph.graph_status import format_report, graph_status
from akms.layout import (
    KnowledgeLayoutError,
    ignored_legacy_dir,
    migrate_knowledge_layout,
    plan_knowledge_migration,
)


def _legacy(repo: Path) -> Path:
    knowledge = repo / "knowledge"
    (knowledge / "local-nodes").mkdir(parents=True)
    (knowledge / "local-nodes" / "a.md").write_text("node\n", encoding="utf-8")
    (knowledge / "graph" / ".qmd_cache").mkdir(parents=True)
    (knowledge / "graph" / "graph.json").write_text("{}\n", encoding="utf-8")
    (knowledge / "graph" / ".qmd_cache" / "q.json").write_text("{}", encoding="utf-8")
    return knowledge


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


def _commit_all(repo: Path) -> None:
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


class TestPlan:
    def test_check_changes_nothing(self, tmp_path: Path):
        _legacy(tmp_path)

        plan = migrate_knowledge_layout(tmp_path, check=True)

        assert plan.status == "planned"
        assert plan.move == "rename"
        assert plan.removed == [
            ".knowledge/graph/graph.json",
            ".knowledge/graph/.qmd_cache",
        ]
        assert (tmp_path / "knowledge").is_dir()
        assert not (tmp_path / ".knowledge").exists()

    def test_no_legacy_directory_is_an_error(self, tmp_path: Path):
        with pytest.raises(KnowledgeLayoutError) as error:
            plan_knowledge_migration(tmp_path)
        assert error.value.code == "no_legacy_dir"

    def test_already_migrated(self, tmp_path: Path):
        (tmp_path / ".knowledge").mkdir()
        assert plan_knowledge_migration(tmp_path).status == "already_migrated"

    def test_both_directories_present_is_refused(self, tmp_path: Path):
        _legacy(tmp_path)
        (tmp_path / ".knowledge").mkdir()
        (tmp_path / ".knowledge" / "x.md").write_text("x\n", encoding="utf-8")

        with pytest.raises(KnowledgeLayoutError) as error:
            plan_knowledge_migration(tmp_path)
        assert error.value.code == "both_present"

    def test_symlinked_legacy_directory_is_refused(self, tmp_path: Path):
        real = tmp_path / "elsewhere"
        real.mkdir()
        (tmp_path / "knowledge").symlink_to(real, target_is_directory=True)

        with pytest.raises(KnowledgeLayoutError) as error:
            plan_knowledge_migration(tmp_path)
        assert error.value.code == "symlink"


class TestMigrate:
    def test_moves_and_drops_compiled_outputs(self, tmp_path: Path):
        _legacy(tmp_path)

        result = migrate_knowledge_layout(tmp_path)

        assert result.status == "migrated"
        assert not (tmp_path / "knowledge").exists()
        assert (tmp_path / ".knowledge/local-nodes/a.md").read_text() == "node\n"
        assert not (tmp_path / ".knowledge/graph/graph.json").exists()
        assert list((tmp_path / ".knowledge/graph/.qmd_cache").iterdir()) == []

    def test_an_empty_dot_knowledge_is_replaced(self, tmp_path: Path):
        _legacy(tmp_path)
        (tmp_path / ".knowledge").mkdir()

        assert migrate_knowledge_layout(tmp_path).status == "migrated"
        assert (tmp_path / ".knowledge/local-nodes/a.md").is_file()

    def test_tracked_directory_moves_with_git_history(self, tmp_path: Path):
        _legacy(tmp_path)
        (tmp_path / "knowledge" / "sessions").mkdir()
        (tmp_path / "knowledge" / "sessions" / "s.md").write_text(
            "s\n", encoding="utf-8"
        )
        (tmp_path / ".gitignore").write_text("knowledge/sessions/\n", encoding="utf-8")
        _commit_all(tmp_path)

        result = migrate_knowledge_layout(tmp_path)

        assert result.move == "git-mv"
        status = _git(tmp_path, "status", "--porcelain")
        assert "R  knowledge/local-nodes/a.md -> .knowledge/local-nodes/a.md" in status
        # Untracked, ignored content moves with the directory.
        assert (tmp_path / ".knowledge/sessions/s.md").is_file()

    def test_rewrites_anchored_ignore_and_attribute_lines(self, tmp_path: Path):
        _legacy(tmp_path)
        (tmp_path / ".gitignore").write_text(
            "# local\nknowledge/sessions/\n/knowledge/graph/graph.json\n"
            "!knowledge/graph/local_state.yaml\n**/knowledge/tmp/\nother/\n",
            encoding="utf-8",
        )
        (tmp_path / ".gitattributes").write_text(
            "knowledge/local-nodes/generated/** linguist-generated -diff\n",
            encoding="utf-8",
        )
        _commit_all(tmp_path)

        result = migrate_knowledge_layout(tmp_path)

        assert (tmp_path / ".gitignore").read_text(encoding="utf-8") == (
            "# local\n.knowledge/sessions/\n/.knowledge/graph/graph.json\n"
            "!.knowledge/graph/local_state.yaml\n**/knowledge/tmp/\nother/\n"
        )
        assert (tmp_path / ".gitattributes").read_text(encoding="utf-8") == (
            ".knowledge/local-nodes/generated/** linguist-generated -diff\n"
        )
        # A pattern not anchored on the directory is reported, not rewritten.
        assert [(m.file, m.line) for m in result.mentions] == [(".gitignore", 5)]

    def test_reports_other_tracked_mentions(self, tmp_path: Path):
        _legacy(tmp_path)
        (tmp_path / "CLAUDE.md").write_text(
            "Nodes live in knowledge/local-nodes/.\nNot .knowledge/ or my_knowledge/.\n",
            encoding="utf-8",
        )
        _commit_all(tmp_path)

        result = migrate_knowledge_layout(tmp_path)

        assert [(m.file, m.line) for m in result.mentions] == [("CLAUDE.md", 1)]
        assert "knowledge/local-nodes" in (tmp_path / "CLAUDE.md").read_text()

    def test_failure_part_way_restores_everything(self, tmp_path: Path, monkeypatch):
        _legacy(tmp_path)
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("knowledge/sessions/\n", encoding="utf-8")
        real_unlink = Path.unlink

        def failing_unlink(self, *args, **kwargs):
            if self.name == "graph.json":
                raise OSError("injected")
            return real_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", failing_unlink)
        with pytest.raises(OSError, match="injected"):
            migrate_knowledge_layout(tmp_path)

        assert (tmp_path / "knowledge/local-nodes/a.md").is_file()
        assert not (tmp_path / ".knowledge").exists()
        assert gitignore.read_text(encoding="utf-8") == "knowledge/sessions/\n"


class TestStatusAndCli:
    def test_status_warns_when_dot_knowledge_hides_knowledge(self, tmp_path: Path):
        _legacy(tmp_path)
        (tmp_path / ".knowledge").mkdir()
        vault = tmp_path / "vault"
        vault.mkdir()

        assert ignored_legacy_dir(tmp_path) == tmp_path / "knowledge"
        report = graph_status(tmp_path, global_vault=vault)
        assert len(report["layout_warnings"]) == 1
        assert "## Knowledge Layout: 1" in format_report(report)

    def test_status_is_quiet_for_one_directory(self, tmp_path: Path):
        _legacy(tmp_path)
        vault = tmp_path / "vault"
        vault.mkdir()

        report = graph_status(tmp_path, global_vault=vault)
        assert report["layout_warnings"] == []
        assert "Knowledge Layout" not in format_report(report)

    def test_cli_check_then_migrate(self, tmp_path: Path, capsys):
        _legacy(tmp_path)

        assert main(["migrate-layout", "--repo", str(tmp_path), "--check"]) == 0
        assert capsys.readouterr().out.startswith(
            "Would move knowledge/ to .knowledge/"
        )
        assert main(["migrate-layout", "--repo", str(tmp_path), "--json"]) == 0
        assert json.loads(capsys.readouterr().out)["status"] == "migrated"
        assert (tmp_path / ".knowledge").is_dir()

    def test_cli_reports_a_refusal(self, tmp_path: Path, capsys):
        assert main(["migrate-layout", "--repo", str(tmp_path)]) == 1
        assert "No knowledge/ directory" in capsys.readouterr().err
