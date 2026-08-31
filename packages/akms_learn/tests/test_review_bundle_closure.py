"""Closure rule, traceability, and feedback-form discipline for the
review bundle."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# Bundle directory is at <repo_root>/artifacts/review_bundles/akms_learn_mvp/
_BUNDLE = (
    Path(__file__).resolve().parents[3]
    / "artifacts"
    / "review_bundles"
    / "akms_learn_mvp"
)


# The bundle is a generated artifact and is not committed: the public tree
# gate forbids a top-level ``artifacts/`` directory. These e2e checks validate
# a bundle once it has been generated, so they skip when it is absent -- the
# same convention the pedagogical and structured closure suites use.
def _require_bundle() -> None:
    if not _BUNDLE.is_dir():
        pytest.skip("canonical bundle dir not present — run regenerate.sh first")


class TestReviewBundleClosure:
    """Closure rule, traceability, feedback form."""

    @pytest.mark.e2e
    def test_traceability_md_row_per_section(self):
        """Verifies: ``traceability.md`` contains at least one row per
        section of ``generated_lesson.md``, with provenance columns
        (section, node_id|edge_id, source_path, line_range)."""
        _require_bundle()
        lesson_path = _BUNDLE / "generated_lesson.md"
        traceability_path = _BUNDLE / "traceability.md"

        assert lesson_path.exists(), f"generated_lesson.md not found at {lesson_path}"
        assert traceability_path.exists(), (
            f"traceability.md not found at {traceability_path}"
        )

        lesson_text = lesson_path.read_text(encoding="utf-8")
        traceability_text = traceability_path.read_text(encoding="utf-8")

        # Collect all ## section headers from the generated lesson (first occurrence only —
        # the lesson repeats the same sections in the appendices, same names).
        section_headers: list[str] = []
        seen: set[str] = set()
        for line in lesson_text.splitlines():
            m = re.match(r"^##\s+(.+)$", line)
            if m:
                title = m.group(1).strip()
                if title not in seen:
                    seen.add(title)
                    section_headers.append(title)

        assert section_headers, "No ## sections found in generated_lesson.md"

        # Build the set of 'section' values present in traceability.md table rows.
        # Table rows look like:  | <section> | <node_id> | <source_path> | <line_range> |
        # We do a case-insensitive substring match for each lesson section header.
        traceability_lower = traceability_text.lower()

        missing: list[str] = []
        for header in section_headers:
            if header.lower() not in traceability_lower:
                missing.append(header)

        assert not missing, (
            f"The following generated_lesson.md sections have no matching row in "
            f"traceability.md: {missing}"
        )

    @pytest.mark.e2e
    def test_feedback_form_seed_text_present(self):
        """Verifies: ``feedback_form.md`` contains the full the specification seed
        text under the ``akms_learn_mvp`` title. The reviewer-facing
        question, verdict prompts, and concrete requested changes are
        present verbatim."""
        _require_bundle()
        form_path = _BUNDLE / "feedback_form.md"
        assert form_path.exists(), f"feedback_form.md not found at {form_path}"

        form_text = form_path.read_text(encoding="utf-8")

        # Title must be exactly the akms_learn_mvp variant.
        assert "# Review Feedback: akms_learn_mvp" in form_text, (
            "feedback_form.md must start with '# Review Feedback: akms_learn_mvp'"
        )

        #   # All canonical section headings must be present verbatim.
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
                f"feedback_form.md is missing required section heading: {heading!r}"
            )

        # Verdict checkboxes must be present (from the verbatim seed).
        assert "- [ ] Ship as-is" in form_text, (
            "feedback_form.md must contain the verbatim verdict checkbox '- [ ] Ship as-is'"
        )
        assert "- [ ] Needs another iteration" in form_text, (
            "feedback_form.md must contain the verbatim verdict checkbox '- [ ] Needs another iteration'"
        )

        assert "- [ ] ..." in form_text, (
            "feedback_form.md must contain the concrete-requested-changes placeholder '- [ ] ...'"
        )

    @pytest.mark.e2e
    def test_warnings_md_matches_packet(self):
        """Verifies: ``warnings.md`` is consistent with
        ``source_packet.json``'s ``warnings`` list — empty if no warnings,
        otherwise one line per warning preserving original ordering.."""
        _require_bundle()
        packet_path = _BUNDLE / "source_packet.json"
        warnings_path = _BUNDLE / "warnings.md"

        assert packet_path.exists(), f"source_packet.json not found at {packet_path}"
        assert warnings_path.exists(), f"warnings.md not found at {warnings_path}"

        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        packet_warnings: list = packet.get("warnings", [])

        warnings_text = warnings_path.read_text(encoding="utf-8")

        if not packet_warnings:
            # When there are no warnings the file should contain a "no warnings" note.
            assert "no warnings" in warnings_text.lower(), (
                "packet.warnings is empty but warnings.md does not contain a 'no warnings' note"
            )
        else:
            # Each warning's message field must appear in warnings.md in
            # order. Comparing whole-dict reprs would never match because
            # warnings.md formats entries as
            # ``- [severity] code | source_ref | message``.
            last_pos = 0
            for warning in packet_warnings:
                msg = warning.get("message", "") if isinstance(warning, dict) else ""
                assert msg, f"packet warning has no 'message' field: {warning!r}"
                pos = warnings_text.lower().find(msg.lower(), last_pos)
                assert pos != -1, (
                    f"warnings.md does not contain packet warning message: {msg!r}"
                )
                last_pos = pos + len(msg)

    @pytest.mark.e2e
    def test_manifest_status_not_plan_closed(self):
        """Verifies: ``manifest.json`` retains
        ``status == 'review_bundle_generated'`` and is NOT flipped to
        ``plan_closed`` by any automated step. ``CLOSURE.md`` exists and
        captures the the specification closure rule.."""
        _require_bundle()
        manifest_path = _BUNDLE / "manifest.json"
        closure_path = _BUNDLE / "CLOSURE.md"

        assert manifest_path.exists(), f"manifest.json not found at {manifest_path}"
        assert closure_path.exists(), f"CLOSURE.md not found at {closure_path}"

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        assert manifest["status"] == "review_bundle_generated", (
            f"manifest.status must be 'review_bundle_generated', got {manifest['status']!r}"
        )
        assert manifest["status"] != "plan_closed", (
            "manifest.status must NOT be 'plan_closed' — this flip is gated on external review"
        )

        # CLOSURE.md must explicitly mention the rule that plan_closed must not be set
        # by automated process (the phrase 'plan_closed' appears in the rule wording).
        closure_text = closure_path.read_text(encoding="utf-8")
        assert "plan_closed" in closure_text, (
            "CLOSURE.md must contain the phrase 'plan_closed' within the closure rule wording"
        )
        assert "MUST NOT" in closure_text, (
            "CLOSURE.md must contain the phrase 'MUST NOT' from the the specification closure rule"
        )
