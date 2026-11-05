"""Tests for required-aware loadout rendering.

Covers:
  - Legacy output unchanged when optional task-knowledge args are omitted
  - Required / coactivated / advisory sections and reason display
  - Resolution fingerprint header linkage
  - Required content never truncated by advisory token budget
  - Structural pitfall warnings render when qmd is unavailable
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import networkx as nx
import pytest
import yaml

from akms.graph.build_graph import build_graph
from akms.graph.generate_loadout import generate_loadout
from akms.graph.query_subgraph import query_subgraph
from akms.schema.models import (
    AgentRole,
    LoadoutMode,
    PropagationConfig,
    ReadingPriority,
)
from akms.task_context.manifest import create_resolution_manifest
from akms.task_context.query import (
    NodeSelection,
    SelectionClass,
    TaskKnowledgeQueryResult,
)
from akms.task_context.resolve import ResolvedSeeds, TaskSeeds
from tests.akms.conftest import make_global_node, set_overlay


@pytest.fixture(autouse=True)
def _default_qmd_available(monkeypatch):
    """Keep qmd-enabled behavior by default; opt out explicitly where needed."""
    monkeypatch.setattr(
        "akms.graph.generate_loadout.shutil.which", lambda _: "/usr/bin/qmd"
    )


def _parse_header(content: str) -> dict:
    lines = content.split("\n")
    assert lines[0] == "---"
    end_idx = lines.index("---", 1)
    return yaml.safe_load("\n".join(lines[1:end_idx]))


def _task_knowledge(
    *entries: tuple[str, SelectionClass, tuple[str, ...], dict],
) -> TaskKnowledgeQueryResult:
    selections = tuple(
        NodeSelection(
            node_id=node_id,
            selection_class=selection_class,
            node_data=node_data,
            reasons=reasons,
        )
        for node_id, selection_class, reasons, node_data in entries
    )
    return TaskKnowledgeQueryResult(selections=selections)


def _resolved_for(
    required: tuple[str, ...], reasons: dict[str, tuple[str, ...]]
) -> ResolvedSeeds:
    return ResolvedSeeds(
        required_route_node_ids=required,
        reasons=reasons,
    )


# ═══════════════════════════════════════════════════════════════════════
#  Legacy compatibility
# ═══════════════════════════════════════════════════════════════════════


class TestLegacyLoadoutCompatibility:
    """Omitting new optional args must preserve the historical layout."""

    def test_legacy_snapshot_without_task_knowledge(
        self, tmp_vault, tmp_repo, monkeypatch
    ):
        """Byte-stable structure when task_knowledge / resolution_manifest omitted."""
        # Freeze wall-clock so consecutive renders are identical.
        monkeypatch.setattr(
            "akms.graph.generate_loadout.datetime",
            SimpleNamespace(now=lambda: datetime(2026, 1, 1, 12, 0, 0)),
        )
        make_global_node(tmp_vault, id="n1", tags=["taichi"], confidence=0.9)
        make_global_node(tmp_vault, id="n2", tags=["taichi"], confidence=0.8)
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        nodes = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)

        kwargs = dict(
            G=G,
            ranked_nodes=nodes,
            task_id="TSK-LEGACY",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.ROUTING,
        )
        a = generate_loadout(**kwargs)
        b = generate_loadout(**kwargs, task_knowledge=None, resolution_manifest=None)

        assert a == b
        assert "## Required Knowledge" not in a
        assert "resolution_fingerprint" not in a
        assert "## Domain Knowledge" in a
        header = _parse_header(a)
        assert "required_node_count" not in header
        assert header["akms_schema"] == "v2"

    def test_legacy_domain_knowledge_table_columns(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="n1", tags=["taichi"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        nodes = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)
        content = generate_loadout(
            G,
            nodes,
            task_id="TSK-COLS",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
        )
        assert "| # | Node | Domain | Confidence | Origin | Read Mode |" in content
        assert "| Class |" not in content


# ═══════════════════════════════════════════════════════════════════════
#  Required-aware rendering
# ═══════════════════════════════════════════════════════════════════════


class TestRequiredAwareLoadout:
    def test_required_sections_and_reasons(self, tmp_vault, tmp_repo):
        make_global_node(
            tmp_vault,
            id="req-a",
            tags=["failure"],
            content="# Required\n\n## Summary\n\nMust load this lesson.\n",
        )
        make_global_node(
            tmp_vault,
            id="co-a",
            tags=["failure"],
            content="# Coactivated\n\n## Summary\n\nCompanion node.\n",
        )
        make_global_node(
            tmp_vault,
            id="adv-a",
            tags=["topic"],
            content="# Advisory\n\n## Summary\n\nNice to have.\n",
        )
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        tk = _task_knowledge(
            (
                "req-a",
                SelectionClass.REQUIRED,
                ("exact route for 'src/a.py'",),
                dict(G.nodes["req-a"]),
            ),
            (
                "co-a",
                SelectionClass.COACTIVATED,
                ("load_with from required node 'req-a'",),
                dict(G.nodes["co-a"]),
            ),
            (
                "adv-a",
                SelectionClass.ADVISORY,
                ("advisory tag query: topic",),
                dict(G.nodes["adv-a"]),
            ),
        )
        content = generate_loadout(
            G,
            [],
            task_id="TSK-REQ",
            phase=2,
            graph_version="graph-v1",
            seed_tags=["topic"],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.ROUTING,
            task_knowledge=tk,
        )

        assert content.index("## Required Knowledge") < content.index(
            "## Coactivated Knowledge"
        )
        assert content.index("## Coactivated Knowledge") < content.index(
            "## Domain Knowledge"
        )
        assert "exact route for 'src/a.py'" in content
        assert "load_with from required node 'req-a'" in content
        assert "**Selection class:** required" in content
        assert "**Selection class:** coactivated" in content
        assert "**Selection class:** advisory" in content

        header = _parse_header(content)
        assert header["required_node_count"] == 1
        assert header["coactivated_node_count"] == 1
        assert header["advisory_node_count"] == 1
        assert header["required_nodes"] == ["req-a"]
        assert header["coactivated_nodes"] == ["co-a"]

    def test_resolution_fingerprint_in_header(self, tmp_vault, tmp_repo):
        make_global_node(tmp_vault, id="req-a", tags=["failure"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        reasons = {"req-a": ("exact route for 'src/a.py'",)}
        tk = _task_knowledge(
            (
                "req-a",
                SelectionClass.REQUIRED,
                reasons["req-a"],
                dict(G.nodes["req-a"]),
            ),
        )
        task = TaskSeeds(
            scope=("src/a.py",),
            title="Required loadout",
            objective="Prove fingerprint linkage",
            advisory_tags=("failure",),
        )
        manifest = create_resolution_manifest(
            task=task,
            resolved_seeds=_resolved_for(("req-a",), reasons),
            query_result=tk,
            agent_role=AgentRole.IMPLEMENTER,
            graph_version="graph-v1",
            route_index_hash="route-v1",
            generated_at=datetime(2026, 8, 11, 0, 0, tzinfo=UTC),
        )
        content = generate_loadout(
            G,
            [],
            task_id="TSK-FP",
            phase=1,
            graph_version="graph-v1",
            seed_tags=["failure"],
            agent_role=AgentRole.IMPLEMENTER,
            task_knowledge=tk,
            resolution_manifest=manifest,
        )
        header = _parse_header(content)
        assert header["resolution_fingerprint"] == manifest.fingerprint
        assert len(header["resolution_fingerprint"]) == 64

    def test_oversized_advisory_cannot_truncate_required(self, tmp_vault, tmp_repo):
        """Required full content stays intact even when advisory exceeds budget."""
        required_body = "REQUIRED-BODY-" + ("R" * 400)
        advisory_body = "ADVISORY-BODY-" + ("A" * 8000)
        make_global_node(
            tmp_vault,
            id="req-big",
            tags=["failure"],
            content=f"# Required\n\n{required_body}\n",
        )
        make_global_node(
            tmp_vault,
            id="adv-big",
            tags=["topic"],
            content=f"# Advisory\n\n{advisory_body}\n",
        )
        # Point content_ref at vault files so _load_node_content can read them.
        req_path = tmp_vault / "req-big.md"
        adv_path = tmp_vault / "adv-big.md"
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        G.nodes["req-big"]["content_ref"] = str(req_path)
        G.nodes["adv-big"]["content_ref"] = str(adv_path)

        tk = _task_knowledge(
            (
                "req-big",
                SelectionClass.REQUIRED,
                ("must load",),
                dict(G.nodes["req-big"]),
            ),
            (
                "adv-big",
                SelectionClass.ADVISORY,
                ("advisory tag query: topic",),
                dict(G.nodes["adv-big"]),
            ),
        )
        config = PropagationConfig()
        # Tiny budget forces advisory truncation if the budget gate is applied.
        config.loadout.max_loadout_tokens = 50

        content = generate_loadout(
            G,
            [],
            task_id="TSK-BUDGET",
            phase=1,
            graph_version="graph-v1",
            seed_tags=["topic"],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.FULL,
            config=config,
            task_knowledge=tk,
            repo_root=tmp_repo,
        )

        assert required_body in content
        # Advisory may be truncated; required must not carry the truncation marker.
        required_section = content.split("## Domain Knowledge")[0]
        assert "[... truncated to fit token budget]" not in required_section
        assert "REQUIRED-BODY-" in required_section

    def test_type_errors_for_wrong_optional_types(self, tmp_vault, tmp_repo):
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        with pytest.raises(TypeError, match="task_knowledge"):
            generate_loadout(
                G,
                [],
                task_id="TSK-ERR",
                phase=1,
                graph_version="g",
                seed_tags=[],
                agent_role=AgentRole.IMPLEMENTER,
                task_knowledge={"not": "a result"},  # type: ignore[arg-type]
            )
        with pytest.raises(TypeError, match="resolution_manifest"):
            generate_loadout(
                G,
                [],
                task_id="TSK-ERR",
                phase=1,
                graph_version="g",
                seed_tags=[],
                agent_role=AgentRole.IMPLEMENTER,
                resolution_manifest={"fingerprint": "x"},  # type: ignore[arg-type]
            )


# ═══════════════════════════════════════════════════════════════════════
#  Structural pitfall warnings without qmd
# ═══════════════════════════════════════════════════════════════════════


class TestCoactivatedReadingPriority:
    """Coactivated nodes render as ``loadout.coactivated_reading_priority``."""

    def _render(self, tmp_path, monkeypatch, co_body, config=None) -> str:
        monkeypatch.setattr("akms.graph.generate_loadout.shutil.which", lambda _: None)
        bodies = {"req-a": "# Required\n\nREQBODY\n", "co-a": co_body}
        G = nx.DiGraph()
        for node_id, body in bodies.items():
            (tmp_path / f"{node_id}.md").write_text(
                f"---\nid: {node_id}\n---\n{body}", encoding="utf-8"
            )
            G.add_node(
                node_id,
                title=node_id,
                confidence=0.9,
                reading_priority="full",
                content_ref=f"{node_id}.md",
            )
        tk = _task_knowledge(
            ("req-a", SelectionClass.REQUIRED, ("route",), dict(G.nodes["req-a"])),
            (
                "co-a",
                SelectionClass.COACTIVATED,
                ("load_with from required node 'req-a'",),
                dict(G.nodes["co-a"]),
            ),
        )
        return generate_loadout(
            G,
            [],
            task_id="TSK-CO",
            phase=1,
            graph_version="graph-v1",
            seed_tags=[],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.FULL,
            config=config,
            task_knowledge=tk,
            repo_root=tmp_path,
        )

    _WITH_SUMMARY = "# Co\n\n## Summary\n\nCompanion gist.\n\n## Body\n\nCOBODY\n"

    def test_default_renders_coactivated_summary(self, tmp_path, monkeypatch):
        content = self._render(tmp_path, monkeypatch, self._WITH_SUMMARY)
        assert "REQBODY" in content
        assert "**Summary:** Companion gist." in content
        assert "COBODY" not in content

    def test_coactivated_without_summary_section_renders_full(
        self, tmp_path, monkeypatch
    ):
        content = self._render(tmp_path, monkeypatch, "# Co\n\nCOBODY\n")
        assert "COBODY" in content

    def test_full_setting_restores_full_coactivated_content(
        self, tmp_path, monkeypatch
    ):
        config = PropagationConfig()
        config.loadout.coactivated_reading_priority = ReadingPriority.FULL
        content = self._render(tmp_path, monkeypatch, self._WITH_SUMMARY, config)
        assert "COBODY" in content


class TestMirrorSummaryInRoutingMode:
    """Routing mode loads an exported mirror's ``## Summary``."""

    _BODY = (
        "# <code>src/foo.py</code>\n\n_Mirror generated: t · phase 1_\n\n"
        "{summary}## Symbol Index\n\n```json\n[]\n```\n\n"
        "## Complete Source\n\n```python\nSOURCEBODY\n## Summary\n\nfrom source\n```\n"
    )
    _SECTION = "## Summary\n\nFoo does things.\n\nFunctions: `bar()`\n\n"

    def _render(self, tmp_path, monkeypatch, *, summary, mode, selection=None):
        monkeypatch.setattr("akms.graph.generate_loadout.shutil.which", lambda _: None)
        mirror = tmp_path / ".knowledge/code-mirror/src/foo.md"
        mirror.parent.mkdir(parents=True, exist_ok=True)
        mirror.write_text(
            "---\nid: mirror-src-foo\n---\n"
            + self._BODY.format(summary=self._SECTION if summary else ""),
            encoding="utf-8",
        )
        data = {
            "title": "Code Mirror: src/foo.py",
            "confidence": 1.0,
            "node_origin": "code-mirror",
            "content_ref": "code-mirror/src/foo.md",
        }
        G = nx.DiGraph()
        G.add_node("mirror-src-foo", **data)
        return generate_loadout(
            G,
            [],
            task_id="TSK-MIRROR",
            phase=1,
            graph_version="graph-v1",
            seed_tags=[],
            agent_role=AgentRole.IMPLEMENTER,
            mode=mode,
            task_knowledge=_task_knowledge(
                (
                    "mirror-src-foo",
                    selection or SelectionClass.REQUIRED,
                    ("route",),
                    data,
                ),
            ),
            repo_root=tmp_path,
        )

    def test_routing_mode_loads_the_section(self, tmp_path, monkeypatch):
        content = self._render(
            tmp_path, monkeypatch, summary=True, mode=LoadoutMode.ROUTING
        )
        assert "**Summary:** Foo does things. Functions: `bar()`\n" in content
        assert "SOURCEBODY" not in content

    def test_coactivated_mirror_loads_the_section(self, tmp_path, monkeypatch):
        content = self._render(
            tmp_path,
            monkeypatch,
            summary=True,
            mode=LoadoutMode.ROUTING,
            selection=SelectionClass.COACTIVATED,
        )
        assert "**Summary:** Foo does things. Functions: `bar()`\n" in content
        assert "SOURCEBODY" not in content

    def test_mirror_without_the_section_renders_as_before(self, tmp_path, monkeypatch):
        """A "## Summary" line in the source text is not the section."""
        content = self._render(
            tmp_path, monkeypatch, summary=False, mode=LoadoutMode.ROUTING
        )
        assert "**Summary:** (no content available)" in content
        assert "from source" not in content

    def test_full_mode_does_not_start_inlining_mirrors(self, tmp_path, monkeypatch):
        content = self._render(
            tmp_path, monkeypatch, summary=True, mode=LoadoutMode.FULL
        )
        assert "(content not available — read from path)" in content
        assert "SOURCEBODY" not in content

    def test_legacy_knowledge_directory_is_found(self, tmp_path, monkeypatch):
        (tmp_path / "knowledge").mkdir()
        monkeypatch.setattr("akms.graph.generate_loadout.shutil.which", lambda _: None)
        mirror = tmp_path / "knowledge/code-mirror/src/foo.md"
        mirror.parent.mkdir(parents=True)
        mirror.write_text(
            "---\nid: mirror-src-foo\n---\n" + self._BODY.format(summary=self._SECTION),
            encoding="utf-8",
        )
        data = {
            "title": "t",
            "confidence": 1.0,
            "node_origin": "code-mirror",
            "content_ref": "code-mirror/src/foo.md",
        }
        G = nx.DiGraph()
        G.add_node("mirror-src-foo", **data)
        content = generate_loadout(
            G,
            [],
            task_id="TSK-MIRROR",
            phase=1,
            graph_version="graph-v1",
            seed_tags=[],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.ROUTING,
            task_knowledge=_task_knowledge(
                ("mirror-src-foo", SelectionClass.REQUIRED, ("route",), data),
            ),
            repo_root=tmp_path,
        )
        assert "**Summary:** Foo does things." in content

    def test_lesson_without_content_is_not_looked_up(self, tmp_path, monkeypatch):
        monkeypatch.setattr("akms.graph.generate_loadout.shutil.which", lambda _: None)
        lesson = tmp_path / ".knowledge/code-mirror/l.md"
        lesson.parent.mkdir(parents=True)
        lesson.write_text(
            "---\nid: l\n---\n## Summary\n\nNot for a lesson.\n", encoding="utf-8"
        )
        data = {
            "title": "t",
            "confidence": 1.0,
            "node_origin": "local",
            "content_ref": "code-mirror/l.md",
        }
        G = nx.DiGraph()
        G.add_node("l", **data)
        content = generate_loadout(
            G,
            [],
            task_id="TSK-MIRROR",
            phase=1,
            graph_version="graph-v1",
            seed_tags=[],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.ROUTING,
            task_knowledge=_task_knowledge(
                ("l", SelectionClass.REQUIRED, ("route",), data)
            ),
            repo_root=tmp_path,
        )
        assert "Not for a lesson" not in content


class TestStructuralPitfallWarnings:
    def test_pitfalls_render_when_qmd_unavailable(
        self, tmp_vault, tmp_repo, monkeypatch
    ):
        monkeypatch.setattr("akms.graph.generate_loadout.shutil.which", lambda _: None)
        make_global_node(tmp_vault, id="n1", tags=["taichi"])
        make_global_node(tmp_vault, id="n2", tags=["taichi"])
        set_overlay(
            tmp_repo,
            local_edges=[
                {
                    "from": "n1",
                    "to": "n2",
                    "type": "pitfall",
                    "weight": 0.8,
                    "note": "Watch for race conditions",
                }
            ],
        )
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        nodes = query_subgraph(G, ["taichi"], AgentRole.IMPLEMENTER)

        content = generate_loadout(
            G,
            nodes,
            task_id="TSK-PIT",
            phase=1,
            graph_version="abc123",
            seed_tags=["taichi"],
            agent_role=AgentRole.IMPLEMENTER,
        )

        assert "qmd_available: false" in content
        assert "## Pitfall Warnings" in content
        assert "race conditions" in content
        # Reading order remains gated in legacy mode when qmd is absent.
        assert "## Suggested Reading Order" not in content

    def test_required_aware_emits_reading_order_without_qmd(
        self,
        tmp_vault,
        tmp_repo,
        monkeypatch,
    ):
        monkeypatch.setattr("akms.graph.generate_loadout.shutil.which", lambda _: None)
        make_global_node(tmp_vault, id="req-a", tags=["failure"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)
        tk = _task_knowledge(
            (
                "req-a",
                SelectionClass.REQUIRED,
                ("exact route",),
                dict(G.nodes["req-a"]),
            ),
        )
        content = generate_loadout(
            G,
            [],
            task_id="TSK-RO",
            phase=1,
            graph_version="g",
            seed_tags=["failure"],
            agent_role=AgentRole.IMPLEMENTER,
            task_knowledge=tk,
        )
        assert "## Suggested Reading Order" in content
        assert "`req-a`" in content
