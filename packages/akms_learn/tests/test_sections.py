"""Package-level tests for Section extraction.

Tests cover:
  * All approved sections present → dict fully populated, line_range set.
  * Missing 'Pitfalls' → None key + one LearningWarning(code='missing_section').
  * Zero matching headings → fallback 'body' section, provenance intact.
  * source_path and line_range on every SectionView (embedded in the other cases).
  * Case-insensitive heading matching (LEARNING GOAL → Learning goal).
"""

import pytest

from akms_learn.models import LearningNodeView
from akms_learn.sections import (
    APPROVED_SECTIONS,
    SectionView,
    extract_sections,
    merge_sections_into_node_view,
)


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------

_SOURCE = "test_node.md"

# Markdown with ALL 9 approved headings, one line of content each.
_ALL_SECTIONS_MD = """\
# Topic Title
Some intro text.

## Learning goal
Learn how things work.

## Prerequisites
Basic knowledge.

## Concept map
A visual map.

## Main path
Step by step.

## Implementation
Code here.

## Derivation
Math proof.

## Pitfalls
Watch out!

## Self-check
Quiz yourself.

## References
See also.
"""


# Markdown missing only the 'Pitfalls' heading.
_MISSING_PITFALLS_MD = """\
## Learning goal
Goals here.

## Prerequisites
Pre here.

## Concept map
Map here.

## Main path
Path here.

## Implementation
Impl here.

## Derivation
Deriv here.

## Self-check
Check here.

## References
Refs here.
"""


# Markdown with zero approved headings.
_NO_HEADINGS_MD = """\
This is free-form text with no approved headings.
It has two lines.
"""


class TestSections:
    """Tests for Section extraction with provenance fallback.

    AC covered: 1, 2, 3, 4, 5.
    """

    @pytest.mark.unit
    def test_extract_sections_all_present(self):
        """Document with every approved section yields dict with all keys populated."""
        sections, warnings = extract_sections(_ALL_SECTIONS_MD, _SOURCE, "node-all")

        # All 9 canonical keys must be present.
        assert set(sections.keys()) == set(APPROVED_SECTIONS)

        # Every value must be a SectionView with non-empty content.
        for name in APPROVED_SECTIONS:
            view = sections[name]
            assert isinstance(view, SectionView), f"{name!r} should be a SectionView"
            assert view.content.strip(), f"{name!r} content should be non-empty"
            assert view.source_path == _SOURCE
            start, end = view.line_range
            assert start >= 1, f"{name!r} line_range start must be ≥ 1"
            assert end >= start, f"{name!r} line_range end must be ≥ start"

        # No missing-section warnings expected.
        missing = [w for w in warnings if w.code == "missing_section"]
        assert missing == [], f"Unexpected missing-section warnings: {missing}"

    @pytest.mark.unit
    def test_extract_sections_missing_emits_warning(self):
        """Missing 'Pitfalls' section returns None for the key and emits one LearningWarning."""
        sections, warnings = extract_sections(
            _MISSING_PITFALLS_MD, _SOURCE, "node-missing"
        )

        # Pitfalls key must be present but None.
        assert "Pitfalls" in sections
        assert sections["Pitfalls"] is None

        # Exactly one missing_section warning for Pitfalls.
        pitfall_warnings = [
            w
            for w in warnings
            if w.code == "missing_section"
            and w.source_ref is not None
            and w.source_ref.endswith("#Pitfalls")
        ]
        assert len(pitfall_warnings) == 1, (
            f"Expected exactly 1 Pitfalls missing-section warning, got: {pitfall_warnings}"
        )

        # All other approved sections should be populated.
        for name in APPROVED_SECTIONS:
            if name == "Pitfalls":
                continue
            assert isinstance(sections[name], SectionView), (
                f"{name!r} should be a SectionView"
            )

    @pytest.mark.unit
    def test_extract_sections_fallback_body(self):
        """Zero matching headings triggers fallback 'body' section, preserving provenance."""
        sections, warnings = extract_sections(_NO_HEADINGS_MD, _SOURCE, "node-free")

        # Only the 'body' key should be present.
        assert list(sections.keys()) == ["body"], (
            f"Expected only 'body' key, got: {list(sections.keys())}"
        )

        body = sections["body"]
        assert isinstance(body, SectionView)
        assert body.source_path == _SOURCE
        assert body.name == "body"

        # Content should be the full document.
        assert body.content == _NO_HEADINGS_MD

        # line_range should start at 1 and end at total_lines.
        total_lines = len(_NO_HEADINGS_MD.splitlines())
        assert body.line_range == (1, total_lines)

        # At least one fallback warning must be present.
        fallback_warnings = [w for w in warnings if w.code == "section_fallback_body"]
        assert len(fallback_warnings) >= 1

    @pytest.mark.unit
    def test_section_line_ranges_correct(self):
        """source_path and line_range are present on every SectionView with correct 1-indexed positions."""
        # Craft a 20-line markdown where heading positions are known.
        # Line 1:  # Intro (non-approved)
        # Line 2:  (blank)
        # Line 3:  ## Learning goal     ← approved, content on lines 4–5
        # Line 4:  content line A
        # Line 5:  content line B
        # Line 6:  ## Prerequisites     ← approved, content on lines 7–8
        # Line 7:  content line C
        # Line 8:  (blank)
        # Lines 9–18: fill with non-approved text / blank lines
        # Line 19: ## Self-check        ← approved, content on line 20
        # Line 20: last content line
        md = (
            "# Intro\n"  # L1
            "\n"  # L2
            "## Learning goal\n"  # L3  heading
            "content line A\n"  # L4
            "content line B\n"  # L5
            "## Prerequisites\n"  # L6  heading
            "content line C\n"  # L7
            "\n"  # L8
            "line 9\n"  # L9
            "line 10\n"  # L10
            "line 11\n"  # L11
            "line 12\n"  # L12
            "line 13\n"  # L13
            "line 14\n"  # L14
            "line 15\n"  # L15
            "line 16\n"  # L16
            "line 17\n"  # L17
            "line 18\n"  # L18
            "## Self-check\n"  # L19  heading
            "last content line"  # L20
        )
        assert len(md.splitlines()) == 20, "Fixture must be exactly 20 lines"

        sections, _ = extract_sections(md, _SOURCE, "node-lineno")

        # Learning goal: content on lines 4–5 (heading on L3, next heading on L6)
        lg = sections.get("Learning goal")
        assert isinstance(lg, SectionView), "Learning goal should be found"
        assert lg.line_range == (4, 5), f"Expected (4, 5), got {lg.line_range}"

        # Prerequisites: content on lines 7–18 (heading on L6, next heading on L19)
        pr = sections.get("Prerequisites")
        assert isinstance(pr, SectionView), "Prerequisites should be found"
        assert pr.line_range == (7, 18), f"Expected (7, 18), got {pr.line_range}"

        # Self-check: content on line 20 to EOF (heading on L19)
        sc = sections.get("Self-check")
        assert isinstance(sc, SectionView), "Self-check should be found"
        assert sc.line_range == (20, 20), f"Expected (20, 20), got {sc.line_range}"

    @pytest.mark.unit
    def test_extract_sections_case_insensitive(self):
        """Heading matching is case-insensitive across all approved headings."""
        # Use upper-case heading text.
        md = "## LEARNING GOAL\nsome content\n"
        sections, warnings = extract_sections(md, _SOURCE, "node-case")

        # Should match as 'Learning goal' (canonical spelling).
        assert "Learning goal" in sections
        lg = sections["Learning goal"]
        assert isinstance(lg, SectionView), (
            "LEARNING GOAL should map to SectionView under canonical key"
        )
        assert lg.content.strip() == "some content"

        # No missing-section warning for Learning goal.
        missing_lg = [
            w
            for w in warnings
            if w.code == "missing_section"
            and w.source_ref is not None
            and w.source_ref.endswith("#Learning goal")
        ]
        assert missing_lg == [], (
            f"Learning goal should not emit a missing warning: {missing_lg}"
        )

    @pytest.mark.unit
    def test_merge_sections_writes_to_included_sections_field(self):
        """``merge_sections_into_node_view`` must update ``included_sections``.

        Regression test from PR #50 review: the helper previously checked
        ``hasattr(node_view, "sections")`` and assigned to ``node_view.sections``,
        but :class:`LearningNodeView` exposes ``included_sections`` (dict-shaped),
        not ``sections``. The mismatched name meant the field was never
        populated on a real model — the dict round-tripped but never
        attached. Pins the correct field name.
        """
        sections_dict, _ = extract_sections(_ALL_SECTIONS_MD, _SOURCE, "node-merge")

        node = LearningNodeView(
            node_id="node-merge",
            source_path=_SOURCE,
            line_range=(1, 20),
            title="Demo",
        )

        returned = merge_sections_into_node_view(node, sections_dict)

        # The helper still returns the serialised dict.
        assert isinstance(returned, dict)
        assert set(returned.keys()) == set(APPROVED_SECTIONS)

        # And it actually attaches to ``included_sections`` on the real model.
        assert node.included_sections, (
            "merge_sections_into_node_view must populate included_sections"
        )
        assert set(node.included_sections.keys()) == set(APPROVED_SECTIONS)
        # 'Learning goal' is present in _ALL_SECTIONS_MD, so it should be a dict
        # (serialised SectionView), not None.
        assert isinstance(node.included_sections["Learning goal"], dict)
        assert node.included_sections["Learning goal"]["name"] == "Learning goal"


# Nodes_Vault node template: numbered headings + synonym wording that must
# resolve onto the canonical APPROVED_SECTIONS via enumerator-strip + aliases.
_VAULT_TEMPLATE_MD = """\
## Summary
One-line overview.

## 1. Core Concept
The conceptual idea.

## 2. Mathematical Formulation
The governing equations.

## 3. Algorithmic Implementation
The pseudo-code.

## 4. Known Pitfalls
The gotchas.

## 5. References
The bibliography.
"""


class TestVaultHeadingResolution:
    """Numbered/synonym headings (Nodes_Vault template) resolve to canonicals."""

    @pytest.mark.unit
    def test_enumerator_prefixed_heading_matches(self):
        sections, _ = extract_sections(
            "## 3. Algorithmic Implementation\nfused kernel\n", _SOURCE, "n"
        )
        impl = sections.get("Implementation")
        assert isinstance(impl, SectionView)
        assert impl.content.strip() == "fused kernel"

    @pytest.mark.unit
    def test_synonym_alias_matches(self):
        sections, _ = extract_sections(
            "## Known Pitfalls\nmind the sign\n", _SOURCE, "n"
        )
        pit = sections.get("Pitfalls")
        assert isinstance(pit, SectionView)
        assert pit.content.strip() == "mind the sign"

    @pytest.mark.unit
    def test_core_concept_and_formulation_concatenate_into_derivation(self):
        """Two source headings mapping to Derivation concatenate in doc order."""
        md = (
            "## 1. Core Concept\nconcept body\n\n"
            "## 2. Mathematical Formulation\nformula body\n"
        )
        sections, _ = extract_sections(md, _SOURCE, "n")
        deriv = sections.get("Derivation")
        assert isinstance(deriv, SectionView)
        assert "concept body" in deriv.content
        assert "formula body" in deriv.content
        # Document order preserved: concept precedes formula.
        assert deriv.content.index("concept body") < deriv.content.index("formula body")

    @pytest.mark.unit
    def test_full_vault_template_populates_teaching_sections(self):
        sections, warnings = extract_sections(_VAULT_TEMPLATE_MD, _SOURCE, "vault")
        for name in ("Derivation", "Implementation", "Pitfalls", "References"):
            assert isinstance(sections.get(name), SectionView), f"{name} should resolve"
        # No whole-document fallback was triggered.
        assert not any(w.code == "section_fallback_body" for w in warnings)

    @pytest.mark.unit
    def test_canonical_spelling_still_wins_over_alias(self):
        """An exact canonical heading is unaffected by the alias layer."""
        sections, _ = extract_sections("## Implementation\ncanonical\n", _SOURCE, "n")
        assert sections["Implementation"].content.strip() == "canonical"
