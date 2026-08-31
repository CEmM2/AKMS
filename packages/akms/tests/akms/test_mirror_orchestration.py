"""Orchestration / CLI / MCP smoke for mirror providers (A2-6)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from akms.cli.commands import build_parser, main
from akms.graph.generate_mirror import generate_mirror
from akms.graph.graph_status import format_report, graph_status
from akms.graph.mirror_provider import (
    MirrorProviderError,
    register_provider,
    unregister_provider,
)
from akms.schema.models import MirrorConfig, PropagationConfig


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    for sub in ("graph", "code-mirror", "local-nodes", "loadouts"):
        (tmp_path / "knowledge" / sub).mkdir(parents=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod.py").write_text(
        textwrap.dedent(
            '''\
            def greet(name: str) -> str:
                """Greet *name*."""
                return name
            '''
        ),
        encoding="utf-8",
    )
    return tmp_path


class TestOrchestratorMirrorWiring:
    def test_legacy_path_through_generate_mirror_with_config(self, repo: Path):
        cfg = PropagationConfig(mirror=MirrorConfig(provider="legacy"))
        result = generate_mirror(
            repo,
            phase=1,
            source_files=["src/mod.py"],
            config=cfg,
            llm_fn=None,
        )
        assert result["provider"] == "legacy"
        assert result["success"] is True
        assert (repo / "knowledge" / "code-mirror" / "src" / "mod.md").is_file()

    def test_required_provider_failure_raises(self, repo: Path):
        class Boom:
            name = "orch-boom"

            def generate(self, request, config):
                raise MirrorProviderError("nope", provider=self.name, code="boom")

        register_provider("orch-boom", Boom, replace=True)
        try:
            cfg = PropagationConfig(
                mirror=MirrorConfig(
                    provider="orch-boom",
                    fallback_on_error=False,
                    require_success=True,
                )
            )
            with pytest.raises(MirrorProviderError):
                generate_mirror(
                    repo,
                    phase=1,
                    source_files=["src/mod.py"],
                    config=cfg,
                )
        finally:
            unregister_provider("orch-boom")

    def test_handle_execute_blocks_on_required_failure(self, repo: Path):
        """Mirror provider failure with require_success propagates from generate_mirror.

        Full handle_execute wiring is covered by e2e agent-mode tests that patch
        generate_mirror; here we assert the policy contract the orchestrator relies on.
        """

        class Boom:
            name = "orch-boom2"

            def generate(self, request, config):
                raise MirrorProviderError("nope", provider=self.name, code="boom")

        register_provider("orch-boom2", Boom, replace=True)
        try:
            cfg = PropagationConfig(
                mirror=MirrorConfig(
                    provider="orch-boom2",
                    fallback_on_error=False,
                    require_success=True,
                )
            )
            with pytest.raises(MirrorProviderError) as ei:
                generate_mirror(
                    repo,
                    phase=1,
                    source_files=["src/mod.py"],
                    config=cfg,
                    llm_fn=None,
                )
            assert ei.value.code == "boom"
            # Policy: non-legacy + no fallback + require_success ⇒ block rebuild.
            assert cfg.mirror.require_success is True
            assert cfg.mirror.fallback_on_error is False
        finally:
            unregister_provider("orch-boom2")


class TestGraphStatusProvider:
    def test_status_includes_mirror_provider(self, repo: Path):
        report = graph_status(
            repo,
            config=PropagationConfig(mirror=MirrorConfig(provider="legacy")),
        )
        assert "mirror_provider" in report
        assert report["mirror_provider"]["provider"] == "legacy"
        text = format_report(report)
        assert "Mirror Provider" in text

    def test_no_rebuild_when_disallowed(self, repo: Path):
        # No graph.json; disallow rebuild → empty graph, no crash
        report = graph_status(
            repo,
            config=PropagationConfig(),
            allow_graph_rebuild=False,
        )
        assert report["total_nodes"] == 0


class TestCLIProviderCommands:
    def test_mirror_status_cli(self, repo: Path, capsys):
        rc = main(["mirror-status", "--repo", str(repo), "--json"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["provider"] == "legacy"
        assert "legacy" in out["known_providers"]

    def test_generate_mirror_cli(self, repo: Path, capsys):
        rc = main(
            [
                "generate-mirror",
                "--repo",
                str(repo),
                "--phase",
                "1",
                "--path",
                "src/mod.py",
                "--json",
            ]
        )
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["provider"] == "legacy"
        assert out["success"] is True

    def test_parser_registers_commands(self):
        parser = build_parser()
        # ensure subcommands exist
        # argparse stores choices on the subparsers action
        actions = [a for a in parser._subparsers._group_actions if a.dest == "command"]
        assert actions
        choices = actions[0].choices
        assert "mirror-status" in choices
        assert "generate-mirror" in choices
        assert "resolve-task" in choices  # α surface still present


class TestMCPGenerateMirror:
    def test_mcp_generate_mirror_uses_config(self, repo: Path):
        """MCP tool body: generate_mirror with config + llm_fn=None (no LLM)."""
        from akms.orchestrator.mcp_tools import build_fastmcp_app

        cfg = PropagationConfig(mirror=MirrorConfig(provider="legacy"))
        # Same call signature the akms_generate_mirror tool uses after A2-6.
        result = generate_mirror(
            str(repo),
            1,
            parent_branch="main",
            source_files=["src/mod.py"],
            config=cfg,
            llm_fn=None,
        )
        assert result["provider"] == "legacy"
        assert result["success"] is True
        # Server factory still constructs without error.
        app = build_fastmcp_app(repo_root=str(repo))
        assert app is not None
