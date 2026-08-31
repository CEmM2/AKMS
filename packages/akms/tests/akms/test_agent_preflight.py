"""Agent preflight: backends report missing requirements before the pipeline runs."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from akms.agents.base import AgentPreflightError, AKMSAgent
from akms.schema.models import PropagationConfig


def _agent(cls=AKMSAgent, tmp_path: Path = Path(".")) -> AKMSAgent:
    return cls(PropagationConfig(), repo_root=tmp_path)


class TestBasePreflight:
    def test_reports_missing_sdk(self, tmp_path, monkeypatch):
        import importlib.util

        monkeypatch.setattr(
            importlib.util, "find_spec", lambda name: None
        )
        reason = _agent(tmp_path=tmp_path).preflight()
        assert reason is not None
        assert "akms[agents]" in reason

    def test_silent_when_sdk_present(self, tmp_path, monkeypatch):
        import importlib.util

        monkeypatch.setattr(
            importlib.util, "find_spec", lambda name: object()
        )
        assert _agent(tmp_path=tmp_path).preflight() is None


class TestCliAgentPreflight:
    @pytest.mark.parametrize(
        ("module", "cls_name", "binary"),
        [
            ("akms.agents.cli_claude", "AKMSClaudeCliAgent", "claude"),
            ("akms.agents.cli_codex", "AKMSCodexCliAgent", "codex"),
        ],
    )
    def test_reports_missing_binary(self, tmp_path, monkeypatch, module, cls_name, binary):
        import importlib
        import shutil

        cls = getattr(importlib.import_module(module), cls_name)
        monkeypatch.setattr(shutil, "which", lambda name: None)
        reason = _agent(cls, tmp_path).preflight()
        assert reason is not None and binary in reason

    def test_silent_when_binary_present(self, tmp_path, monkeypatch):
        import shutil

        from akms.agents.cli_claude import AKMSClaudeCliAgent

        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/claude")
        assert _agent(AKMSClaudeCliAgent, tmp_path).preflight() is None


class TestPipelinePreflightGate:
    def test_pipeline_aborts_before_any_write(self, tmp_path, monkeypatch):
        """A failing preflight raises before the pipeline writes anything."""
        import importlib.util

        from akms.orchestrator.orchestrator import run_pipeline

        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
        repo = tmp_path / "repo"
        repo.mkdir()
        with pytest.raises(AgentPreflightError, match="akms\\[agents\\]"):
            asyncio.run(run_pipeline(repo_root=repo, goal="g"))
        assert list(repo.iterdir()) == [], "preflight failure must not write files"

    def test_duck_typed_agent_without_preflight_is_tolerated(self, tmp_path):
        """The extension seam accepts agent classes that lack preflight()."""

        class MinimalAgent:
            def __init__(self, config, repo_root, model=None):
                self.config = config

        from akms.orchestrator.orchestrator import run_pipeline

        repo = tmp_path / "repo"
        repo.mkdir()

        # The pipeline proceeds past preflight and fails later for unrelated
        # reasons (no knowledge tree) — the point is: no AttributeError.
        with pytest.raises(Exception) as excinfo:
            asyncio.run(run_pipeline(repo_root=repo, goal="g", agent_cls=MinimalAgent))
        assert excinfo.type is not AttributeError
