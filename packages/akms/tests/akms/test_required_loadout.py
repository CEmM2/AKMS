"""Tests for required-aware loadout rendering.

Covers:
  - Legacy output unchanged when optional task-knowledge args are omitted
  - Required / coactivated / advisory sections and reason display
  - Resolution fingerprint header linkage
  - Required content never truncated by advisory token budget
  - Structural pitfall warnings render when qmd is unavailable
"""

from __future__ import annotations

import json
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
    """Mirrors in the knowledge directory: routing mode loads the ``## Summary``,
    exported or built from the symbol index, and full mode the whole body."""

    _INDEX = json.dumps(
        [
            {
                "symbol_id": "python:src/foo.py::foo",
                "kind": "module",
                "start_line": 1,
                "end_line": 4,
            },
            {
                "symbol_id": "python:src/foo.py::bar",
                "kind": "function",
                "start_line": 2,
                "end_line": 3,
                "signature": "def bar(x)",
                "parent_id": "python:src/foo.py::foo",
            },
        ],
        indent=2,
    )
    # _BODY is a format string.
    _ESCAPED = _INDEX.replace("{", "{{").replace("}", "}}")
    _BODY = (
        "# <code>src/foo.py</code>\n\n_Mirror generated: t · phase 1_\n\n"
        "{summary}## Symbol Index\n\n```json\n" + _ESCAPED + "\n```\n\n"
        "## Complete Source\n\n```python\nSOURCEBODY\n## Summary\n\nfrom source\n```\n"
    )
    _SECTION = "## Summary\n\nFoo does things.\n\nFunctions: `bar()`\n\n"
    _DERIVED = "**Summary:** Functions: `bar(x)`\n"

    @staticmethod
    def _underived(**loadout):
        """A config with the built summary off, plus ``loadout`` settings."""
        config = PropagationConfig()
        config.loadout.derive_mirror_summary = False
        for name, value in loadout.items():
            setattr(config.loadout, name, value)
        return config

    def _render(
        self, tmp_path, monkeypatch, *, summary, mode, selection=None, config=None
    ):
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
            config=config,
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

    def test_mirror_without_the_section_gets_one_from_its_index(
        self, tmp_path, monkeypatch
    ):
        """A "## Summary" line in the source text is not the section."""
        content = self._render(
            tmp_path, monkeypatch, summary=False, mode=LoadoutMode.ROUTING
        )
        assert self._DERIVED in content
        assert "from source" not in content
        assert "SOURCEBODY" not in content

    def test_an_exported_section_wins_over_the_index(self, tmp_path, monkeypatch):
        content = self._render(
            tmp_path, monkeypatch, summary=True, mode=LoadoutMode.ROUTING
        )
        assert "**Summary:** Foo does things. Functions: `bar()`\n" in content
        assert self._DERIVED not in content

    def test_with_the_setting_off_the_mirror_renders_as_before(
        self, tmp_path, monkeypatch
    ):
        content = self._render(
            tmp_path,
            monkeypatch,
            summary=False,
            mode=LoadoutMode.ROUTING,
            config=self._underived(),
        )
        assert "**Summary:** (no content available)" in content
        assert "from source" not in content

    def test_an_index_that_does_not_parse_renders_as_before(
        self, tmp_path, monkeypatch
    ):
        self._BODY = self._BODY.replace(self._ESCAPED, "not json")
        content = self._render(
            tmp_path, monkeypatch, summary=False, mode=LoadoutMode.ROUTING
        )
        assert "**Summary:** (no content available)" in content

    def test_full_mode_inlines_the_mirror(self, tmp_path, monkeypatch):
        content = self._render(
            tmp_path, monkeypatch, summary=False, mode=LoadoutMode.FULL
        )
        assert "SOURCEBODY" in content
        assert "(content not available — read from path)" not in content

    def test_routing_mode_does_not_inline_the_mirror(self, tmp_path, monkeypatch):
        content = self._render(
            tmp_path, monkeypatch, summary=False, mode=LoadoutMode.ROUTING
        )
        assert "SOURCEBODY" not in content

    def test_full_mode_guard_downgrades_a_loaded_mirror(self, tmp_path, monkeypatch):
        """Downgraded, a mirror reads as in routing mode: its section only."""
        config = PropagationConfig()
        config.loadout.full_mode_max_tokens = 1
        for summary, config, expected in (
            (True, config, "**Summary:** Foo does things. Functions: `bar()`\n"),
            (False, config, self._DERIVED),
            (
                False,
                self._underived(full_mode_max_tokens=1),
                "**Summary:** (no content available)",
            ),
        ):
            content = self._render(
                tmp_path,
                monkeypatch,
                summary=summary,
                mode=LoadoutMode.FULL,
                config=config,
            )
            assert "**Downgraded:**" in content
            assert expected in content
            assert "SOURCEBODY" not in content
            assert "from source" not in content

    def test_coactivated_mirror_in_full_mode(self, tmp_path, monkeypatch):
        """Summary priority uses the section or the index; with neither it is full."""
        self._BODY = self._BODY.replace("## Summary\n\nfrom source\n", "")
        for summary, config, inlined in (
            (True, None, False),
            (False, None, False),
            (False, self._underived(), True),
        ):
            content = self._render(
                tmp_path,
                monkeypatch,
                summary=summary,
                mode=LoadoutMode.FULL,
                selection=SelectionClass.COACTIVATED,
                config=config,
            )
            assert ("SOURCEBODY" in content) is inlined
            assert (self._DERIVED in content) is (not summary and config is None)

    def test_path_line_opens_from_the_repository_root(self, tmp_path, monkeypatch):
        for mode in (LoadoutMode.ROUTING, LoadoutMode.FULL):
            content = self._render(tmp_path, monkeypatch, summary=True, mode=mode)
            assert "**Path:** `.knowledge/code-mirror/src/foo.md`" in content

    def test_mirror_found_from_the_repository_root_is_unchanged(
        self, tmp_path, monkeypatch
    ):
        """A ref that already resolves loads as before, in either mode."""
        monkeypatch.chdir(tmp_path)
        root_copy = tmp_path / "code-mirror/src/foo.md"
        root_copy.parent.mkdir(parents=True)
        root_copy.write_text(
            "---\nid: mirror-src-foo\n---\nROOTBODY\n", encoding="utf-8"
        )
        content = self._render(
            tmp_path, monkeypatch, summary=True, mode=LoadoutMode.FULL
        )
        assert "ROOTBODY" in content
        assert "SOURCEBODY" not in content
        assert "**Path:** `code-mirror/src/foo.md`" in content

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


class TestFullModeGuard:
    """``loadout.full_mode_max_tokens`` bounds inline required code mirrors."""

    @pytest.fixture(autouse=True)
    def _frozen_clock(self, monkeypatch):
        monkeypatch.setattr("akms.graph.generate_loadout.shutil.which", lambda _: None)
        monkeypatch.setattr(
            "akms.graph.generate_loadout.datetime",
            SimpleNamespace(now=lambda: datetime(2026, 1, 1, 12, 0, 0)),
        )

    def _render(
        self,
        tmp_path,
        nodes,
        *,
        max_tokens=100,
        mode=LoadoutMode.FULL,
        max_loadout_tokens=None,
    ) -> str:
        """Render ``(id, class, origin, body_chars)`` nodes; 4 chars is 1 token."""
        G = nx.DiGraph()
        entries = []
        for node_id, selection_class, origin, chars in nodes:
            marker = f"BODY-{node_id}-"
            body = marker + "x" * max(0, chars - len(marker))
            (tmp_path / f"{node_id}.md").write_text(
                f"---\nid: {node_id}\n---\n{body}\n", encoding="utf-8"
            )
            G.add_node(
                node_id,
                title=node_id,
                confidence=0.9,
                node_origin=origin,
                content_ref=f"{node_id}.md",
            )
            entries.append((node_id, selection_class, ("why",), dict(G.nodes[node_id])))
        config = PropagationConfig()
        config.loadout.full_mode_max_tokens = max_tokens
        if max_loadout_tokens is not None:
            config.loadout.max_loadout_tokens = max_loadout_tokens
        return generate_loadout(
            G,
            [],
            task_id="TSK-GUARD",
            phase=1,
            graph_version="graph-v1",
            seed_tags=[],
            agent_role=AgentRole.IMPLEMENTER,
            mode=mode,
            config=config,
            task_knowledge=_task_knowledge(*entries),
            repo_root=tmp_path,
        )

    _REQUIRED = SelectionClass.REQUIRED

    def test_default_budget_is_set_and_validated(self):
        config = PropagationConfig()
        assert config.loadout.full_mode_max_tokens == 40000
        assert (
            PropagationConfig.model_validate(
                {"loadout": {"full_mode_max_tokens": None}}
            ).loadout.full_mode_max_tokens
            is None
        )
        with pytest.raises(ValueError, match="full_mode_max_tokens"):
            PropagationConfig.model_validate({"loadout": {"full_mode_max_tokens": 0}})

    @pytest.mark.parametrize("max_tokens", [100, 40000, None])
    def test_loadout_within_budget_is_byte_identical_to_guard_off(
        self, tmp_path, max_tokens
    ):
        nodes = [
            ("mirror-a", self._REQUIRED, "code-mirror", 160),
            ("mirror-b", self._REQUIRED, "code-mirror", 160),
            ("zz-lesson", self._REQUIRED, "local", 80),
        ]
        guarded = self._render(tmp_path, nodes, max_tokens=max_tokens)
        unguarded = self._render(tmp_path, nodes, max_tokens=None)
        assert guarded == unguarded
        assert "full_mode_guard" not in guarded
        assert "**Downgraded:**" not in guarded

    def test_budget_exactly_met_does_not_fire(self, tmp_path):
        content = self._render(
            tmp_path,
            [("mirror-a", self._REQUIRED, "code-mirror", 400)],
            max_tokens=100,
        )
        assert "BODY-mirror-a-" in content
        assert "full_mode_guard" not in content

    def test_remaining_mirrors_become_summary_and_path_never_dropped(self, tmp_path):
        content = self._render(
            tmp_path,
            [
                ("mirror-a", self._REQUIRED, "code-mirror", 240),
                ("mirror-b", self._REQUIRED, "code-mirror", 240),
                ("mirror-c", self._REQUIRED, "code-mirror", 240),
            ],
            max_tokens=100,
        )
        header = _parse_header(content)
        assert header["required_nodes"] == ["mirror-a", "mirror-b", "mirror-c"]
        assert header["full_mode_guard"] == {
            "downgraded_nodes": ["mirror-b", "mirror-c"],
            "max_tokens": 100,
            "unguarded_inline_tokens": 180,
        }
        assert "**Full-mode budget exceeded:**" in content
        assert "Code mirrors served as summary and path only: 2" in content

        def block(node_id: str) -> str:
            start = content.index(f"### `{node_id}`")
            end = content.find("\n### `", start + 1)
            return content[start:end] if end != -1 else content[start:]

        assert "**Downgraded:**" not in block("mirror-a")
        assert "**Summary:**" not in block("mirror-a")
        for node_id in ("mirror-b", "mirror-c"):
            detail = block(node_id)
            assert "**Downgraded:** over `loadout.full_mode_max_tokens`" in detail
            assert "~60 tokens in full" in detail
            assert f"**Path:** `{node_id}.md`" in detail
            assert "**Summary:** BODY-" in detail
        assert "| `mirror-b` | required |  | 0.90 | code-mirror | routing |" in content

    def test_overflow_is_a_latch_so_a_later_small_mirror_is_downgraded_too(
        self, tmp_path
    ):
        content = self._render(
            tmp_path,
            [
                ("mirror-a", self._REQUIRED, "code-mirror", 800),
                ("mirror-b", self._REQUIRED, "code-mirror", 8),
            ],
            max_tokens=100,
        )
        assert _parse_header(content)["full_mode_guard"]["downgraded_nodes"] == [
            "mirror-a",
            "mirror-b",
        ]

    def test_required_lessons_stay_inline_and_are_charged_first(self, tmp_path):
        """A lesson sorting after the mirrors still gets the budget before them."""
        content = self._render(
            tmp_path,
            [
                ("mirror-a", self._REQUIRED, "code-mirror", 240),
                ("zz-lesson", self._REQUIRED, "local", 240),
            ],
            max_tokens=100,
        )
        assert "BODY-zz-lesson-" + "x" * 200 in content
        assert _parse_header(content)["full_mode_guard"]["downgraded_nodes"] == [
            "mirror-a"
        ]

    def test_lessons_over_budget_alone_stay_inline(self, tmp_path):
        content = self._render(
            tmp_path,
            [
                ("mirror-a", self._REQUIRED, "code-mirror", 40),
                ("zz-lesson", self._REQUIRED, "local", 800),
            ],
            max_tokens=100,
        )
        assert "BODY-zz-lesson-" + "x" * 700 in content
        assert _parse_header(content)["full_mode_guard"]["downgraded_nodes"] == [
            "mirror-a"
        ]

    def test_only_non_mirror_content_over_budget_reports_nothing(self, tmp_path):
        content = self._render(
            tmp_path,
            [("zz-lesson", self._REQUIRED, "local", 800)],
            max_tokens=100,
        )
        assert "BODY-zz-lesson-" in content
        assert "full_mode_guard" not in content

    def test_downgraded_mirrors_leave_room_for_advisory_content(self, tmp_path):
        content = self._render(
            tmp_path,
            [
                ("mirror-a", self._REQUIRED, "code-mirror", 4000),
                ("adv-a", SelectionClass.ADVISORY, "local", 200),
            ],
            max_tokens=100,
            max_loadout_tokens=500,
        )
        assert "[... truncated to fit token budget]" not in content
        assert "BODY-adv-a-" in content

    def test_routing_mode_is_untouched(self, tmp_path):
        nodes = [("mirror-a", self._REQUIRED, "code-mirror", 4000)]
        routed = self._render(tmp_path, nodes, max_tokens=1, mode=LoadoutMode.ROUTING)
        assert routed == self._render(
            tmp_path, nodes, max_tokens=None, mode=LoadoutMode.ROUTING
        )
        assert "full_mode_guard" not in routed

    def test_output_is_deterministic(self, tmp_path):
        nodes = [
            ("mirror-b", self._REQUIRED, "code-mirror", 240),
            ("mirror-a", self._REQUIRED, "code-mirror", 240),
        ]
        first = self._render(tmp_path, nodes, max_tokens=100)
        assert first == self._render(tmp_path, list(reversed(nodes)), max_tokens=100)
        assert _parse_header(first)["full_mode_guard"]["downgraded_nodes"] == [
            "mirror-b"
        ]

    def test_coactivated_mirror_without_summary_is_guarded(self, tmp_path):
        """FR-L10c renders it in full, so it counts as inline content too."""
        content = self._render(
            tmp_path,
            [("mirror-a", SelectionClass.COACTIVATED, "code-mirror", 800)],
            max_tokens=100,
        )
        assert _parse_header(content)["full_mode_guard"]["downgraded_nodes"] == [
            "mirror-a"
        ]

    def test_legacy_loadout_has_no_guard(self, tmp_path):
        """Without task knowledge every node already honours max_loadout_tokens."""
        (tmp_path / "mirror-a.md").write_text(
            "---\nid: mirror-a\n---\n" + "x" * 8000 + "\n", encoding="utf-8"
        )
        data = {
            "title": "mirror-a",
            "confidence": 0.9,
            "node_origin": "code-mirror",
            "content_ref": "mirror-a.md",
        }
        G = nx.DiGraph()
        G.add_node("mirror-a", **data)
        config = PropagationConfig()
        config.loadout.full_mode_max_tokens = 1
        content = generate_loadout(
            G,
            [("mirror-a", data)],
            task_id="TSK-LEGACY",
            phase=1,
            graph_version="graph-v1",
            seed_tags=[],
            agent_role=AgentRole.IMPLEMENTER,
            mode=LoadoutMode.FULL,
            config=config,
            repo_root=tmp_path,
        )
        assert "full_mode_guard" not in content
        assert "x" * 1000 in content


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
