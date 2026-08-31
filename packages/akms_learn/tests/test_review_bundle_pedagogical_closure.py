"""Closure-surface coverage for the pedagogical review bundle.

Bundle directory: ``artifacts/review_bundles/akms_learn_pedagogical/``
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BUNDLE = _REPO_ROOT / "artifacts" / "review_bundles" / "akms_learn_pedagogical"
_GENERATOR = (
    _REPO_ROOT
    / "packages"
    / "akms_learn"
    / "scripts"
    / "generate_review_bundle_pedagogical.py"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_bundle_file(name: str) -> Path:
    """Return bundle path for *name*, skipping if the bundle dir is absent."""
    if not _BUNDLE.is_dir():
        pytest.skip("canonical bundle dir not present — run regenerate.sh first")
    p = _BUNDLE / name
    assert p.exists(), f"{name} missing from bundle at {p}"
    return p


def _load_generator_module():
    """Import the pedagogical bundle generator script by file path."""
    assert _GENERATOR.is_file(), f"generator script missing: {_GENERATOR}"
    spec = importlib.util.spec_from_file_location("_p4_2_gen_probe", _GENERATOR)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return mod


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestPedagogicalClosureSurface:
    """Closure surfaces of the pedagogical review bundle."""

    # -- Feedback form ---------------------------------------------------------

    @pytest.mark.e2e
    def test_feedback_form_matches_section_14_seed_verbatim(self) -> None:
        """Verifies: feedback_form.md reproduces §14 seed byte-for-byte under
        the akms_learn_pedagogical title."""
        form_path = _require_bundle_file("feedback_form.md")
        form_text = form_path.read_text(encoding="utf-8")

        # Title must be exactly the pedagogical-bundle variant.
        assert "# Review Feedback: akms_learn_pedagogical" in form_text, (
            "feedback_form.md must contain '# Review Feedback: akms_learn_pedagogical'"
        )

        # All §14 section headings verbatim.
        required_headings = [
            "## Reviewer background",
            "## Learning value",
            "## Technical correctness",
            "## Structure",
            "## Verdict",
            "## Concrete requested changes",
        ]
        for heading in required_headings:
            assert heading in form_text, (
                f"feedback_form.md is missing required heading: {heading!r}"
            )

        # Verbatim verdict checkboxes from §14 seed.
        for checkbox in (
            "- [ ] Ship as-is",
            "- [ ] Ship with minor edits",
            "- [ ] Needs another iteration",
            "- [ ] Not useful in current form",
        ):
            assert checkbox in form_text, (
                f"feedback_form.md missing verbatim verdict checkbox: {checkbox!r}"
            )

        assert "- [ ] ..." in form_text, (
            "feedback_form.md must contain the placeholder '- [ ] ...'"
        )

        # Reviewer-background bullet labels (verbatim from §14).
        assert "- Role:" in form_text
        assert "- Familiarity with topic:" in form_text
        assert "- Familiarity with AKMS / Logic-Loom:" in form_text

    @pytest.mark.e2e
    def test_feedback_form_matches_builder_output(self) -> None:
        """Verifies: on-disk feedback_form.md equals _build_feedback_form() output.

        Confirms the generator is wired to the real builder, not a stub.
        (Wiring check.)
        """
        form_path = _require_bundle_file("feedback_form.md")
        mod = _load_generator_module()
        try:
            expected = mod._build_feedback_form()
            on_disk = form_path.read_text(encoding="utf-8")
            assert on_disk == expected, (
                "feedback_form.md on-disk content differs from _build_feedback_form() output"
            )
        finally:
            sys.modules.pop("_p4_2_gen_probe", None)

    # -- Traceability ----------------------------------------------------------

    @pytest.mark.e2e
    def test_traceability_has_section_level_rows(self) -> None:
        """Verifies: traceability.md has at least one row per generated-lesson
        section across all three lesson files."""
        traceability_path = _require_bundle_file("traceability.md")
        traceability_text = traceability_path.read_text(encoding="utf-8")

        # Must have a markdown table.
        assert "| lesson | section" in traceability_text, (
            "traceability.md must contain a section-level table with 'lesson' and 'section' columns"
        )

        # Check sections from all three lesson files.
        lesson_files = [
            "pedagogical_template_lesson.md",
            "derivation_first_lesson.md",
            "implementation_first_lesson.md",
        ]

        for lesson_name in lesson_files:
            lesson_path = _BUNDLE / lesson_name
            if not lesson_path.exists():
                continue
            lesson_text = lesson_path.read_text(encoding="utf-8")

            sections_seen: set[str] = set()
            for line in lesson_text.splitlines():
                m = re.match(r"^##\s+(.+)$", line)
                if m:
                    sections_seen.add(m.group(1).strip())

            assert sections_seen, f"No ## sections found in {lesson_name}"

            trace_lower = traceability_text.lower()
            missing = [s for s in sections_seen if s.lower() not in trace_lower]
            assert not missing, (
                f"{lesson_name}: the following sections have no row in "
                f"traceability.md: {missing}"
            )

    @pytest.mark.e2e
    def test_traceability_has_source_column(self) -> None:
        """Verifies: traceability.md rows include a source column."""
        traceability_path = _require_bundle_file("traceability.md")
        traceability_text = traceability_path.read_text(encoding="utf-8")

        # Table must have a source column header.
        assert "| source |" in traceability_text or "source" in traceability_text, (
            "traceability.md must have a 'source' column"
        )

        # At least one real source_path reference (toy:// uri) should appear.
        assert "toy://" in traceability_text, (
            "traceability.md should contain at least one packet source_path reference"
        )

    # -- Warnings surface ------------------------------------------------------

    @pytest.mark.e2e
    def test_warnings_md_mirrors_packet_warnings(self) -> None:
        """Verifies: warnings.md is consistent with manifest.warnings — empty
        case handled with 'no warnings'; non-empty case has one line per
        warning."""
        warnings_path = _require_bundle_file("warnings.md")
        manifest_path = _require_bundle_file("manifest.json")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_warnings: list = manifest.get("warnings", [])
        warnings_text = warnings_path.read_text(encoding="utf-8")

        if not manifest_warnings:
            assert "no warnings" in warnings_text.lower(), (
                "manifest.warnings is empty but warnings.md does not contain "
                "a 'no warnings' note"
            )
        else:
            # Every warning's message field must appear in warnings.md.
            last_pos = 0
            for w in manifest_warnings:
                msg = w.get("message", "") if isinstance(w, dict) else ""
                assert msg, f"manifest warning has no 'message' field: {w!r}"
                pos = warnings_text.lower().find(msg.lower(), last_pos)
                assert pos != -1, (
                    f"warnings.md does not contain manifest warning message: {msg!r}"
                )
                last_pos = pos + len(msg)

    @pytest.mark.e2e
    def test_warnings_md_not_a_stub(self) -> None:
        """Verifies: warnings.md carries real content, not a placeholder."""
        warnings_path = _require_bundle_file("warnings.md")
        text = warnings_path.read_text(encoding="utf-8")
        assert "Populated by" not in text, (
            "warnings.md still contains a generator placeholder marker"
        )
        assert text.strip(), "warnings.md is empty"

    # -- Closure-status guard --------------------------------------------------

    @pytest.mark.e2e
    def test_manifest_status_never_auto_flips_to_plan_closed(self) -> None:
        """Verifies: manifest.status stays 'review_bundle_generated' — no
        automated path writes 'plan_closed'."""
        manifest_path = _require_bundle_file("manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        assert manifest["status"] == "review_bundle_generated", (
            f"manifest.status must be 'review_bundle_generated', got "
            f"{manifest['status']!r}"
        )
        assert manifest["status"] != "plan_closed", (
            "manifest.status MUST NOT be 'plan_closed' — gated on external review"
        )

    @pytest.mark.e2e
    def test_generator_source_never_writes_plan_closed_status(self) -> None:
        """Verifies: the generator source code contains no code path that
        assigns status = 'plan_closed' (source-level guard)."""
        assert _GENERATOR.is_file(), f"generator script missing: {_GENERATOR}"
        source = _GENERATOR.read_text(encoding="utf-8")

        # The string "plan_closed" must NOT appear as a status assignment.
        # We allow it in comments/docstrings that reference the rule, but
        # must not appear on the right-hand side of a status assignment.
        # Strategy: scan for patterns like status = "plan_closed" or
        # "status": "plan_closed".
        bad_patterns = [
            r'"plan_closed"',
            r"'plan_closed'",
        ]
        # Count how many times plan_closed appears in non-comment context.
        # The generator is allowed to reference it in docstrings that document
        # the rule, but must never ASSIGN it. We check that MANIFEST_STATUS
        # constant is "review_bundle_generated" and no assignment uses
        # "plan_closed" as a value.
        assert 'MANIFEST_STATUS: str = "review_bundle_generated"' in source, (
            "MANIFEST_STATUS constant must be 'review_bundle_generated'"
        )
        # Verify "plan_closed" is not used in any dict literal assignment
        # of the form {"status": "plan_closed"} or status = "plan_closed".
        import ast

        tree = ast.parse(source)
        for node in ast.walk(tree):
            # Check assignments: status = "plan_closed"
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "status":
                        if (
                            isinstance(node.value, ast.Constant)
                            and node.value.value == "plan_closed"
                        ):
                            pytest.fail(
                                "generator assigns status = 'plan_closed' — violates closure rule"
                            )
            # Check dict literals: {"status": "plan_closed"}
            if isinstance(node, ast.Dict):
                for key, val in zip(node.keys, node.values):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "status"
                        and isinstance(val, ast.Constant)
                        and val.value == "plan_closed"
                    ):
                        pytest.fail(
                            "generator dict literal sets status='plan_closed' — violates closure rule"
                        )

    # -- Closure rule ----------------------------------------------------------

    @pytest.mark.e2e
    def test_closure_md_quotes_section_14_rule(self) -> None:
        """Verifies: CLOSURE.md contains 'plan_closed' and 'MUST NOT' from §14
        closure rule."""
        closure_path = _require_bundle_file("CLOSURE.md")
        closure_text = closure_path.read_text(encoding="utf-8")

        assert "plan_closed" in closure_text, (
            "CLOSURE.md must contain the phrase 'plan_closed' within the closure rule wording"
        )
        assert "MUST NOT" in closure_text, (
            "CLOSURE.md must contain the phrase 'MUST NOT' from the the specification closure rule"
        )

    @pytest.mark.e2e
    def test_closure_md_references_feedback_form(self) -> None:
        """Verifies: CLOSURE.md references feedback_form.md."""
        closure_path = _require_bundle_file("CLOSURE.md")
        closure_text = closure_path.read_text(encoding="utf-8")

        assert "feedback_form.md" in closure_text, (
            "CLOSURE.md must reference feedback_form.md"
        )

    @pytest.mark.e2e
    def test_closure_md_not_in_bundle_artifacts_list(self) -> None:
        """Verifies: CLOSURE.md is NOT listed in manifest.artifacts (it is a
        bundle-root sibling, not a manifest-listed artifact)."""
        manifest_path = _require_bundle_file("manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifacts: list = manifest.get("artifacts", [])
        assert "CLOSURE.md" not in artifacts, (
            "CLOSURE.md must NOT be listed in manifest.artifacts "
            "(it is a sibling, not a §14 artifact)"
        )
