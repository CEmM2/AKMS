"""Tests for AKMSLocalAgent (openai-agents against a local OpenAI-compatible endpoint).

The local model/client construction is verified by patching ``openai.AsyncOpenAI``
and ``agents.OpenAIChatCompletionsModel`` to capture kwargs (no network). The
Codex runner (``_codex_sdk_execute``) is patched so no live agent runs; the fake
writes a valid AgentMemory so the sealed ``run()`` lifecycle can validate it.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

import frontmatter
import pytest

import akms.agents.base_codex as base_codex
from akms.agents.local import AKMSLocalAgent
from akms.schema.models import PropagationConfig, TaskStatus


def _write_valid_agent_memory(repo_root: Path, task_id: str = "task-1") -> Path:
    sessions_dir = repo_root / "knowledge" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    output_path = sessions_dir / f"{task_id}.md"
    memory_dict = {
        "task_id": task_id,
        "task_description": "Test task",
        "phase_id": 1,
        "timestamp": datetime.now().isoformat(),
        "agent_model": "my-local-model",
        "loadout_used": "",
        "status": "complete",
        "commit": "abc123",
        "tests_passed": 1,
        "tests_total": 1,
        "completion_notes": "All done",
        "nodes_used": [],
        "nodes_missing": [],
        "lessons": {"worked": [], "failed": []},
        "pitfalls_discovered": [],
        "new_knowledge": [],
        "akms_schema": "v2",
    }
    post = frontmatter.Post(content="\n## Notes\n\nok\n", **memory_dict)
    with open(output_path, "wb") as f:
        frontmatter.dump(post, f)
    return output_path


def _task_json(task_id: str = "task-1") -> dict:
    return {"task_id": task_id, "phase": 1, "title": "Test task", "loadout_path": ""}


@pytest.fixture(autouse=True)
def _clear_base(monkeypatch):
    monkeypatch.delenv("AKMS_LLM_API_BASE", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)


@pytest.mark.unit
def test_requires_api_base_maps_to_failed_memory(tmp_repo):
    agent = AKMSLocalAgent(config=PropagationConfig(), repo_root=tmp_repo, model="m")
    memory = asyncio.run(agent.run(_task_json()))
    assert memory.status == TaskStatus.FAILED
    assert "AKMS_LLM_API_BASE" in memory.completion_notes


@pytest.mark.unit
def test_requires_explicit_model_maps_to_failed_memory(tmp_repo, monkeypatch):
    # Base set, but no explicit model → clear error (no Claude-default fallback).
    monkeypatch.setenv("AKMS_LLM_API_BASE", "http://localhost:1234/v1")
    agent = AKMSLocalAgent(config=PropagationConfig(), repo_root=tmp_repo)
    memory = asyncio.run(agent.run(_task_json()))
    assert memory.status == TaskStatus.FAILED
    assert "model" in memory.completion_notes.lower()


@pytest.mark.unit
def test_build_local_model_wires_base_url_and_model(tmp_repo, monkeypatch):
    import agents as agents_mod
    import openai as openai_mod

    captured: dict = {}

    def fake_async_openai(**kw):
        captured["client_kw"] = kw
        return "FAKE_CLIENT"

    def fake_model(**kw):
        captured["model_kw"] = kw
        return "FAKE_MODEL"

    monkeypatch.setenv("AKMS_LLM_API_BASE", "http://localhost:1234/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(openai_mod, "AsyncOpenAI", fake_async_openai)
    monkeypatch.setattr(agents_mod, "OpenAIChatCompletionsModel", fake_model)

    agent = AKMSLocalAgent(config=PropagationConfig(), repo_root=tmp_repo, model="my-local-model")
    model = agent._build_local_model()

    assert model == "FAKE_MODEL"
    assert captured["client_kw"]["base_url"] == "http://localhost:1234/v1"
    assert captured["client_kw"]["api_key"] == "sk-no-key-required"
    assert captured["model_kw"]["model"] == "my-local-model"
    assert captured["model_kw"]["openai_client"] == "FAKE_CLIENT"


@pytest.mark.unit
def test_execute_passes_local_model_to_runner(tmp_repo, monkeypatch):
    monkeypatch.setenv("AKMS_LLM_API_BASE", "http://localhost:1234/v1")
    captured: dict = {}

    async def fake_runner(user_message, loadout, system_prompt, model, repo_root, allowed_tools=None):
        captured["model"] = model
        captured["allowed_tools"] = allowed_tools
        _write_valid_agent_memory(Path(repo_root), "task-1")

    monkeypatch.setattr(base_codex, "_codex_sdk_execute", fake_runner)

    agent = AKMSLocalAgent(config=PropagationConfig(), repo_root=tmp_repo, model="my-local-model")
    memory = asyncio.run(agent.run({**_task_json(), "tools": ["file_edit"]}))

    assert memory.status == TaskStatus.COMPLETE
    # A real local model object was constructed and threaded to the runner
    # (no network on construction), not a bare model string.
    assert type(captured["model"]).__name__ == "OpenAIChatCompletionsModel"
    assert "Write" in captured["allowed_tools"]


@pytest.mark.unit
def test_backend_resolves_local():
    from akms.cli.commands import BACKENDS, _import_agent_class

    cls = _import_agent_class(BACKENDS["local"])
    assert cls is AKMSLocalAgent
