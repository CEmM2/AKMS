"""Shared test fixtures for AKMS tests.

All tests use temporary directories for both global vault and repo knowledge.
No global state is touched.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def tmp_vault(tmp_path: Path) -> Path:
    """Create a temporary global vault directory."""
    vault = tmp_path / "global_vault" / "nodes"
    vault.mkdir(parents=True)
    return vault


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """Create a temporary repo with knowledge/ directory structure."""
    repo = tmp_path / "repo"
    repo.mkdir()
    knowledge = repo / "knowledge"
    for subdir in [
        "graph",
        "local-nodes",
        "sessions",
        "loadouts",
        "code-mirror",
        "qmd",
    ]:
        (knowledge / subdir).mkdir(parents=True)

    # Write empty local_state.yaml
    overlay_path = knowledge / "graph" / "local_state.yaml"
    overlay_path.write_text(
        yaml.dump(
            {
                "akms_schema": "v2",
                "repo_id": "test-repo",
                "nodes": {},
                "local_edges": [],
                "session_nodes": {},
                "suppressed_edges": [],
            }
        )
    )

    return repo


@pytest.fixture(autouse=True)
def set_vault_env(tmp_vault: Path, monkeypatch: pytest.MonkeyPatch):
    """Point AKMS_GLOBAL_VAULT to the temp vault for all tests."""
    monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(tmp_vault))


def write_node_md(path: Path, frontmatter: dict, content: str = "") -> Path:
    """Write a .md file with YAML frontmatter."""
    import frontmatter as fm

    post = fm.Post(content)
    post.metadata = frontmatter
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        fm.dump(post, f)
    return path


# ── Fixture factory helpers ──────────────────────────────────────────


def make_global_node(
    vault: Path,
    *,
    id: str = "test-node",
    title: str = "Test Node",
    domain: str = "test-domain",
    tags: list[str] | None = None,
    status: str = "established",
    confidence: float = 0.90,
    source: str = "human",
    edges: list[dict] | None = None,
    confidence_floor: float | None = None,
    content: str = "Test content.",
    **kwargs,
) -> Path:
    """Create a global node .md file in the vault."""
    fm = {
        "id": id,
        "title": title,
        "domain": domain,
        "tags": tags or ["test"],
        "status": status,
        "confidence": confidence,
        "source": source,
        "edges": edges or [],
        "akms_schema": "v2",
    }
    if confidence_floor is not None:
        fm["confidence_floor"] = confidence_floor
    fm.update(kwargs)
    return write_node_md(vault / f"{id}.md", fm, content)


def make_local_node(
    repo: Path,
    *,
    id: str = "local-test",
    title: str = "Local Test Node",
    domain: str = "test-domain",
    tags: list[str] | None = None,
    status: str = "tentative",
    confidence: float = 0.70,
    source: str = "agent",
    content: str = "Agent-drafted content.",
    **kwargs,
) -> Path:
    """Create a local node .md file in repo knowledge/local-nodes/."""
    fm = {
        "id": id,
        "title": title,
        "domain": domain,
        "tags": tags or ["local-test"],
        "status": status,
        "confidence": confidence,
        "source": source,
        "edges": [],
        "akms_schema": "v2",
    }
    fm.update(kwargs)
    return write_node_md(repo / "knowledge" / "local-nodes" / f"{id}.md", fm, content)


def make_mirror_node(
    repo: Path,
    *,
    id: str = "mirror-test-module",
    title: str = "Code Mirror: test/module.py",
    source_file: str = "test/module.py",
    content_ref: str = "code-mirror/test/module.md",
    phase: int = 1,
    content: str = "# Mirror content",
) -> Path:
    """Create a code-mirror node .md file."""
    fm = {
        "id": id,
        "title": title,
        "domain": "code-mirror",
        "status": "established",
        "confidence": 1.0,
        "source": "generated",
        "auto_update": True,
        "content_ref": content_ref,
        "source_file": source_file,
        "generated_at": "2026-03-01T10:00:00",
        "generated_by_phase": phase,
        "akms_schema": "v2",
    }
    return write_node_md(repo / "knowledge" / "code-mirror" / f"{id}.md", fm, content)


def make_ctx(
    tmp_repo: Path,
    tmp_vault: Path | None = None,
    agent_cls=None,
    model: str | None = None,
    spec_path: str = "",
):
    """Build a PipelineContext for handler tests."""
    from akms.orchestrator.orchestrator import PipelineContext
    from akms.schema.models import PropagationConfig

    return PipelineContext(
        repo_root=tmp_repo,
        global_vault=tmp_vault,
        config=PropagationConfig(),
        agent_cls=agent_cls,
        model=model,
        spec_path=spec_path,
    )


def make_state(**kwargs):
    """Build a fresh PipelineState."""
    from akms.orchestrator.stages import PipelineState

    return PipelineState(**kwargs)


def set_overlay(
    repo: Path,
    *,
    nodes: dict | None = None,
    local_edges: list[dict] | None = None,
    session_nodes: dict | None = None,
) -> Path:
    """Write/update local_state.yaml overlay."""
    overlay_path = repo / "knowledge" / "graph" / "local_state.yaml"
    data = {
        "akms_schema": "v2",
        "repo_id": "test-repo",
        "nodes": nodes or {},
        "local_edges": local_edges or [],
        "session_nodes": session_nodes or {},
        "suppressed_edges": [],
    }
    overlay_path.write_text(yaml.dump(data, default_flow_style=False))
    return overlay_path
