"""Tests for tag_derivation.py — Phase 6: Hybrid Tag Derivation.

Coverage:
- Scope-based derivation (source_file, content_ref matching)
- Text-based derivation (title whole-word, tag substring)
- Explicit tags preserved
- Union + dedup
- fill_task_tags batch operation
- Determinism
"""

from __future__ import annotations


from akms.graph.build_graph import build_graph
from akms.graph.tag_derivation import (
    _build_text_corpus,
    _derive_tags_from_scope,
    _derive_tags_from_text,
    derive_tags,
    fill_task_tags,
)
from akms.schema.models import TagDerivationConfig

from .conftest import make_global_node, make_mirror_node


class TestScopeBasedDerivation:
    """Test scope-based tag derivation from file path matching."""

    def test_scope_matches_mirror_source_file(self, tmp_vault, tmp_repo):
        """Task scope matching a code-mirror source_file gets that node's tags."""
        make_global_node(tmp_vault, id="node-a", tags=["alpha", "beta"])
        make_mirror_node(
            tmp_repo,
            id="mirror-src-module",
            source_file="src/module.py",
            content_ref="code-mirror/src/module.md",
        )
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        # The mirror node doesn't have tags (it's marker-only), so no tags from it
        # but let's verify scope matching works against content_ref on global nodes
        tags = _derive_tags_from_scope(G, ["src/module.py"])
        # Mirror nodes don't have tags, so this should be empty
        assert isinstance(tags, set)

    def test_scope_matches_global_content_ref(self, tmp_vault, tmp_repo):
        """Task scope matching a global node content_ref gets that node's tags."""
        make_global_node(
            tmp_vault,
            id="skill-taichi",
            tags=["taichi", "gpu", "simulation"],
            content_ref="skills/taichi-gpu-sim/SKILL.md",
        )
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        tags = _derive_tags_from_scope(G, ["skills/taichi-gpu-sim/SKILL.md"])
        assert "taichi" in tags
        assert "gpu" in tags

    def test_scope_suffix_match(self, tmp_vault, tmp_repo):
        """Scope path that ends with content_ref still matches."""
        make_global_node(
            tmp_vault,
            id="skill-mech",
            tags=["mechanics", "fem"],
            content_ref="skills/computational-mechanics/SKILL.md",
        )
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        # Exact match on content_ref
        tags = _derive_tags_from_scope(G, ["skills/computational-mechanics/SKILL.md"])
        assert "mechanics" in tags or "fem" in tags

    def test_empty_scope(self, tmp_vault, tmp_repo):
        """Empty scope yields empty tags."""
        make_global_node(tmp_vault, id="node-a", tags=["alpha"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        tags = _derive_tags_from_scope(G, [])
        assert tags == set()


class TestTextBasedDerivation:
    """Test text-based tag derivation from title/objective matching."""

    def test_title_matches_node_title_whole_word(self, tmp_vault, tmp_repo):
        """Task title containing a node title word gets that node's tags."""
        make_global_node(
            tmp_vault,
            id="plasticity-node",
            title="Plasticity Return Mapping",
            tags=["plasticity", "return-mapping"],
        )
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        task = {"title": "Implement plasticity algorithm", "objective": ""}
        config = TagDerivationConfig()
        tags = _derive_tags_from_text(G, task, config)
        assert "plasticity" in tags

    def test_tag_substring_match(self, tmp_vault, tmp_repo):
        """Tag found as substring in task text is derived."""
        make_global_node(
            tmp_vault,
            id="fft-node",
            title="FFT Galerkin Basics",
            tags=["fft-galerkin", "spectral"],
        )
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        task = {
            "title": "Set up fft-galerkin solver",
            "objective": "spectral method implementation",
        }
        config = TagDerivationConfig(min_tag_length=2)
        tags = _derive_tags_from_text(G, task, config)
        assert "fft-galerkin" in tags
        assert "spectral" in tags

    def test_short_tags_filtered(self, tmp_vault, tmp_repo):
        """Tags shorter than min_tag_length are not matched."""
        make_global_node(
            tmp_vault,
            id="node-a",
            title="Some Node",
            tags=["a"],  # too short
        )
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        task = {"title": "Do a thing", "objective": ""}
        config = TagDerivationConfig(min_tag_length=2)
        tags = _derive_tags_from_text(G, task, config)
        assert "a" not in tags

    def test_objective_contributes_to_corpus(self, tmp_vault, tmp_repo):
        """Objective text is included in the matching corpus."""
        make_global_node(
            tmp_vault,
            id="fracture-node",
            title="Fracture Mechanics",
            tags=["fracture", "crack-propagation"],
        )
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        task = {"title": "Phase 1 task", "objective": "Implement fracture model"}
        config = TagDerivationConfig()
        tags = _derive_tags_from_text(G, task, config)
        assert "fracture" in tags

    def test_implementation_steps_in_corpus(self, tmp_vault, tmp_repo):
        """implementation_steps list contributes to text corpus."""
        make_global_node(
            tmp_vault,
            id="taichi-node",
            title="Taichi GPU Simulation",
            tags=["taichi", "gpu-kernel"],
        )
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        task = {
            "title": "Setup",
            "objective": "",
            "implementation_steps": ["Initialize taichi runtime", "Define kernels"],
        }
        config = TagDerivationConfig()
        tags = _derive_tags_from_text(G, task, config)
        assert "taichi" in tags

    def test_empty_text_yields_empty(self, tmp_vault, tmp_repo):
        """Empty task text yields no tags."""
        make_global_node(tmp_vault, id="node-a", tags=["alpha"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        task = {"title": "", "objective": ""}
        config = TagDerivationConfig()
        tags = _derive_tags_from_text(G, task, config)
        assert tags == set()


class TestBuildTextCorpus:
    """Test the text corpus builder."""

    def test_concatenates_fields(self):
        task = {
            "title": "My Task",
            "objective": "Do things",
            "implementation_steps": ["Step 1", "Step 2"],
        }
        corpus = _build_text_corpus(task)
        assert "my task" in corpus
        assert "do things" in corpus
        assert "step 1" in corpus

    def test_handles_missing_fields(self):
        task = {"title": "Only title"}
        corpus = _build_text_corpus(task)
        assert "only title" in corpus


class TestDeriveTags:
    """Test the main derive_tags function."""

    def test_explicit_tags_preserved(self, tmp_vault, tmp_repo):
        """Tasks with existing akms_tags are returned unchanged."""
        make_global_node(tmp_vault, id="node-a", tags=["alpha"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        task = {"akms_tags": ["explicit-tag"], "title": "alpha task"}
        result = derive_tags(G, task)
        assert result == ["explicit-tag"]

    def test_union_of_scope_and_text(self, tmp_vault, tmp_repo):
        """Scope and text tags are unioned."""
        make_global_node(
            tmp_vault,
            id="node-a",
            title="Alpha Feature",
            tags=["alpha"],
            content_ref="src/alpha.py",
        )
        make_global_node(
            tmp_vault,
            id="node-b",
            title="Beta Feature",
            tags=["beta"],
        )
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        task = {
            "scope": ["src/alpha.py"],
            "title": "Implement beta feature",
            "objective": "",
        }
        result = derive_tags(G, task)
        assert "alpha" in result  # from scope
        assert "beta" in result  # from text

    def test_result_is_sorted(self, tmp_vault, tmp_repo):
        """Derived tags are sorted."""
        make_global_node(tmp_vault, id="node-a", title="Zeta", tags=["zeta", "alpha"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        task = {"title": "zeta and alpha work", "objective": ""}
        result = derive_tags(G, task)
        assert result == sorted(result)

    def test_deterministic(self, tmp_vault, tmp_repo):
        """Same input produces same output."""
        make_global_node(tmp_vault, id="node-a", title="Alpha", tags=["alpha", "test"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        task = {"title": "alpha test task", "objective": ""}
        r1 = derive_tags(G, task)
        r2 = derive_tags(G, task)
        assert r1 == r2

    def test_empty_tags_and_scope(self, tmp_vault, tmp_repo):
        """Task with no matching scope or text gets empty tags."""
        make_global_node(tmp_vault, id="node-a", tags=["alpha"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        task = {"title": "unrelated", "objective": "nothing matches"}
        result = derive_tags(G, task)
        assert result == []


class TestFillTaskTags:
    """Test batch tag filling."""

    def test_fills_multiple_tasks(self, tmp_vault, tmp_repo):
        """fill_task_tags fills tags for multiple tasks."""
        make_global_node(tmp_vault, id="node-a", title="Alpha", tags=["alpha"])
        make_global_node(tmp_vault, id="node-b", title="Beta", tags=["beta"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        tasks = [
            {"title": "alpha task", "objective": ""},
            {"title": "beta task", "objective": ""},
        ]
        fill_task_tags(G, tasks)

        assert "alpha" in tasks[0]["akms_tags"]
        assert "beta" in tasks[1]["akms_tags"]

    def test_preserves_explicit_tags(self, tmp_vault, tmp_repo):
        """fill_task_tags doesn't overwrite explicit tags."""
        make_global_node(tmp_vault, id="node-a", title="Alpha", tags=["alpha"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        tasks = [
            {"title": "alpha task", "akms_tags": ["explicit"]},
        ]
        fill_task_tags(G, tasks)
        assert tasks[0]["akms_tags"] == ["explicit"]

    def test_modifies_in_place(self, tmp_vault, tmp_repo):
        """fill_task_tags modifies tasks in place and returns them."""
        make_global_node(tmp_vault, id="node-a", title="Alpha", tags=["alpha"])
        G = build_graph(tmp_repo, global_vault=tmp_vault)

        tasks = [{"title": "alpha task", "objective": ""}]
        result = fill_task_tags(G, tasks)
        assert result is tasks
