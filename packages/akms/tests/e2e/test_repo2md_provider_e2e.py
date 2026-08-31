"""Opt-in real repo2md subprocess → mirror → graph E2E (A2-7).

Skipped unless ``AKMS_REPO2MD_E2E=1``. Uses the pinned repo2md fixture source
tree and a real ``repo-wiki`` executable. Does not require resolve-task from
A2-α; uses public ``build_graph`` + ``query_subgraph`` / loadout APIs.

Environment:
  AKMS_REPO2MD_E2E=1
  AKMS_REPO2MD_ROOT  optional path to repo2md checkout
  AKMS_REPO2MD_COMMAND  optional argv0 for repo-wiki
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from akms.graph.build_graph import build_graph
from akms.graph.generate_mirror import generate_mirror
from akms.schema.models import MirrorConfig, PropagationConfig

pytestmark = pytest.mark.e2e

_E2E = os.environ.get("AKMS_REPO2MD_E2E", "") == "1"
_REPO2MD_ROOT = Path(
    os.environ.get(
        "AKMS_REPO2MD_ROOT",
        "/opt/example/repo2md",
    )
)
_FIXTURE_SOURCE = _REPO2MD_ROOT / "tests" / "fixtures" / "akms_export" / "source_repo"
_CMD = os.environ.get("AKMS_REPO2MD_COMMAND") or shutil.which("repo-wiki") or "repo-wiki"


def _ready() -> bool:
    return _E2E and _FIXTURE_SOURCE.is_dir() and shutil.which(str(_CMD).split()[0] if False else _CMD)


@pytest.mark.skipif(not _E2E, reason="AKMS_REPO2MD_E2E!=1 (opt-in real repo2md E2E)")
@pytest.mark.skipif(
    not _FIXTURE_SOURCE.is_dir(),
    reason=f"repo2md fixture source missing: {_FIXTURE_SOURCE}",
)
class TestRealRepo2mdE2E:
    def test_subprocess_mirror_then_graph(self, tmp_path: Path):
        # Copy fixture source into an isolated repo root.
        repo = tmp_path / "proj"
        shutil.copytree(_FIXTURE_SOURCE, repo)
        for sub in ("knowledge/code-mirror", "knowledge/graph", "knowledge/local-nodes"):
            (repo / sub).mkdir(parents=True, exist_ok=True)

        cfg = PropagationConfig(
            mirror=MirrorConfig(
                provider="repo2md",
                command=[_CMD],
                timeout_seconds=60,
                fallback_on_error=False,
                require_success=True,
                selection_mode="full",
                expected_export_schema_version=1,
                expected_akms_schema_version="v2",
            )
        )

        # Deterministic timestamp for the exporter.
        os.environ.setdefault("SOURCE_DATE_EPOCH", "0")
        result = generate_mirror(
            repo,
            phase=1,
            config=cfg,
            source_files=None,  # full selection via config
            llm_fn=None,
        )
        assert result["success"] is True
        assert result["provider"] == "repo2md"
        assert len(result["mirrors"]) >= 1
        # Mirrors land under knowledge/code-mirror
        mirrors = list((repo / "knowledge" / "code-mirror").rglob("*.md"))
        assert mirrors, "expected mirror markdown files on disk"

        # Graph build must accept all mirrors (frozen v2).
        G = build_graph(repo, config=cfg)
        mirror_nodes = [
            n for n, d in G.nodes(data=True) if d.get("node_origin") == "code-mirror"
        ]
        assert mirror_nodes, "expected code-mirror nodes in compiled graph"

        #   # Public query surface (the resolve-task CLI may arrive separately).
        from akms.graph.query_subgraph import query_subgraph

        ranked = query_subgraph(G, [], "implementer", config=cfg)
        assert isinstance(ranked, list)
        # At least one mirror node id is present for exact seed matching.
        assert any(
            d.get("node_origin") == "code-mirror" or n.startswith("mirror-")
            for n, d in G.nodes(data=True)
        )
