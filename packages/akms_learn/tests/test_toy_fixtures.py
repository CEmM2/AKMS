"""Tests for the toy fixture domain packs.

Verifies:
* each fixture is a valid AKMS graph slice consumable by
  ``compile_learning_source`` end-to-end.
* no node id, title, tag, or section content uses
  computational-mechanics jargon — the modes must work on any domain pack.
* ``toy_executable_bridge`` carries at least one ``implements`` edge.
* ``toy_workbench`` carries at least one node with a Derivation
  section (approved-heading vocabulary).

Plus a source-text vocabulary canary on the fixture module itself.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from akms_learn import LearningRequest, compile_learning_source
from akms_learn.compiler import STAGES
from akms_learn.graph_import import GraphSlice
from akms_learn.toy_fixtures import (
    RESERVED_DOMAIN_TERMS,
    all_toy_fixtures,
    fixture_graph_toy_concept_kit,
    fixture_graph_toy_executable_bridge,
    fixture_graph_toy_workbench,
)


def _make_request(**overrides) -> LearningRequest:
    """Build a minimal LearningRequest for compiling a toy fixture."""
    defaults = dict(
        topic="toy widget pipeline",
        goal="Exercise the toy domain pack end-to-end.",
        audience="engineer",
        depth="implementation",
        generation_option="deterministic_outline",
        seed_tags=[],
        exporters=[],
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


# ---------------------------------------------------------------------------
# Fixtures are valid GraphSlices and compile end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFixtureStructure:
    """Each fixture returns a non-empty GraphSlice with consistent metadata."""

    @pytest.mark.parametrize(
        "factory",
        [
            fixture_graph_toy_concept_kit,
            fixture_graph_toy_workbench,
            fixture_graph_toy_executable_bridge,
        ],
    )
    def test_factory_returns_graph_slice(self, factory):
        slice_ = factory()
        assert isinstance(slice_, GraphSlice)
        assert len(slice_.nodes) >= 1, "fixture must produce ≥1 node"
        # Every node must carry a node_id (compiler invariant).
        for node in slice_.nodes:
            assert node.get("node_id"), f"missing node_id in {node!r}"
        # Metadata must record the family.
        assert "family" in slice_.metadata

    def test_all_toy_fixtures_helper_returns_three_families(self):
        fixtures = all_toy_fixtures()
        # Three original families plus the later toy_derivation_gap addition.
        # Assert the original three are present; the fourth is additive.
        required_families = {
            "toy_concept_kit",
            "toy_workbench",
            "toy_executable_bridge",
        }
        assert required_families.issubset(set(fixtures.keys())), (
            f"Missing required fixture families: "
            f"{required_families - set(fixtures.keys())}"
        )
        for slice_ in fixtures.values():
            assert isinstance(slice_, GraphSlice)


@pytest.mark.integration
class TestFixtureCompiles:
    """Each fixture is consumable by compile_learning_source."""

    @pytest.mark.parametrize(
        "factory,family",
        [
            (fixture_graph_toy_concept_kit, "toy_concept_kit"),
            (fixture_graph_toy_workbench, "toy_workbench"),
            (fixture_graph_toy_executable_bridge, "toy_executable_bridge"),
        ],
    )
    def test_compile_each_fixture_produces_valid_packet(self, factory, family):
        result = compile_learning_source(
            request=_make_request(),
            graph_slice=factory(),
        )
        assert result.packet is not None
        assert result.packet.body.nodes, f"compiled body for {family!r} has no nodes"
        # Stage log must be complete — compare to the canonical STAGES tuple
        # rather than a hard-coded count so adding/renaming a stage can't make
        # this assertion silently wrong.
        assert result.stage_log == list(STAGES)


# ---------------------------------------------------------------------------
# Generic-vocabulary lint
# ---------------------------------------------------------------------------


_RESERVED_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in RESERVED_DOMAIN_TERMS) + r")\b",
    flags=re.IGNORECASE,
)


def _scan_dict_strings(payload, hits: list[tuple[str, str]], path: str = "") -> None:
    """Recursively walk *payload* and record any string field hitting a reserved term."""
    if isinstance(payload, str):
        m = _RESERVED_RE.search(payload)
        if m:
            hits.append((path, m.group(0)))
    elif isinstance(payload, dict):
        for k, v in payload.items():
            _scan_dict_strings(v, hits, f"{path}.{k}")
    elif isinstance(payload, (list, tuple)):
        for idx, item in enumerate(payload):
            _scan_dict_strings(item, hits, f"{path}[{idx}]")


@pytest.mark.unit
class TestGenericVocabulary:
    """No fixture content uses reserved computational-mechanics jargon."""

    def test_fixture_payloads_contain_no_reserved_terms(self):
        hits: list[tuple[str, str]] = []
        for family, slice_ in all_toy_fixtures().items():
            _scan_dict_strings(list(slice_.nodes), hits, f"{family}.nodes")
            _scan_dict_strings(list(slice_.edges), hits, f"{family}.edges")
            _scan_dict_strings(slice_.metadata, hits, f"{family}.metadata")
        assert hits == [], (
            f"Toy fixtures must not use reserved domain terms; offenders: {hits}"
        )

    def test_fixture_module_source_text_contains_no_reserved_terms(self):
        """Source-text canary: the toy_fixtures module must read generically.

        The lint scans the module body *outside* triple-quoted docstrings —
        docstrings are allowed to mention the reserved terms to explain
        the lint contract. What matters is that no executable code or
        data literal carries a reserved term.
        """
        import akms_learn.toy_fixtures as toy_fixtures_mod

        module_path = Path(toy_fixtures_mod.__file__)
        text = module_path.read_text(encoding="utf-8")
        # Strip every triple-quoted string (docstrings) before scanning.
        sanitised = re.sub(r'"""[\s\S]*?"""', "<DOCSTRING>", text)
        # Strip the RESERVED_DOMAIN_TERMS literal block: from the
        # assignment header up to the closing-paren line. We match the
        # whole region by anchoring on the literal opening "(" line and
        # the bare ")" closing line (which terminates the tuple literal).
        sanitised = re.sub(
            r"RESERVED_DOMAIN_TERMS:[\s\S]*?\n\)",
            "<RESERVED_TUPLE>",
            sanitised,
            count=1,
        )
        # Strip ordinary "#" comments — they're allowed to mention
        # reserved terms when explaining the lint contract.
        sanitised = re.sub(r"#[^\n]*", "", sanitised)
        m = _RESERVED_RE.search(sanitised)
        assert m is None, (
            f"Reserved term {m.group(0)!r} found in toy_fixtures.py "
            f"outside the lint-definition block / docstrings — fixtures "
            f"must stay generic."
        )

    def test_node_ids_are_generic(self):
        for slice_ in all_toy_fixtures().values():
            for node in slice_.nodes:
                nid = node["node_id"]
                assert not _RESERVED_RE.search(nid), (
                    f"node_id {nid!r} uses a reserved term"
                )


# ---------------------------------------------------------------------------
# toy_executable_bridge has an implements edge
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecutableBridgeImplementsEdge:
    def test_bridge_has_implements_edge(self):
        slice_ = fixture_graph_toy_executable_bridge()
        implements_edges = [e for e in slice_.edges if e.get("type") == "implements"]
        assert implements_edges, (
            "toy_executable_bridge must contain ≥1 implements edge "
            "for CodeLinkView consumers."
        )
        # Endpoints must exist as node ids.
        node_ids = {n["node_id"] for n in slice_.nodes}
        for edge in implements_edges:
            assert edge["from"] in node_ids
            assert edge["to"] in node_ids

    def test_bridge_has_code_mirror_with_provenance(self):
        slice_ = fixture_graph_toy_executable_bridge()
        mirrors = [n for n in slice_.nodes if n.get("kind") == "code_mirror"]
        assert mirrors, (
            "toy_executable_bridge should include a code-mirror node "
            "(per the specification implementation_first source-pack provenance)."
        )
        # At least one mirror's provenance carries a source_pack/code_repo
        # field — even if code_path is 'unknown' (graceful warning path).
        assert any((m.get("provenance") or {}).get("code_repo") for m in mirrors)


# ---------------------------------------------------------------------------
# toy_workbench has a Derivation section
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWorkbenchDerivationSection:
    def test_workbench_node_has_derivation_section(self):
        slice_ = fixture_graph_toy_workbench()
        derivation_nodes = [
            n for n in slice_.nodes if "Derivation" in (n.get("extracted") or {})
        ]
        assert derivation_nodes, (
            "toy_workbench must include ≥1 node carrying a Derivation "
            "section so the derivation_first mode can exercise it."
        )
        # Derivation content must mention the toy step language.
        derivation_text = derivation_nodes[0]["extracted"]["Derivation"]
        assert "Step" in derivation_text or "step" in derivation_text

    def test_workbench_includes_assumption_or_selfcheck_section(self):
        """Workbench-style packs should carry assumption-like content.

        Plan §13 wording: "derivation-first mode SHOULD prove it can use
        assumptions/equations/derivation sections from any domain pack".
        We accept either an explicit Self-check or an "assume" mention
        inside Derivation as the generic equivalent.
        """
        slice_ = fixture_graph_toy_workbench()
        ok = False
        for node in slice_.nodes:
            extracted = node.get("extracted") or {}
            if "Self-check" in extracted:
                ok = True
                break
            if "assume" in extracted.get("Derivation", "").lower():
                ok = True
                break
        assert ok, "toy_workbench must carry an assumption or Self-check signal."
