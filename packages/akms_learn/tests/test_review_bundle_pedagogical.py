"""Pedagogical review-bundle generator coverage.

Covers:

* All 8 required artifacts + manifest.json + regenerate.sh present
  and non-empty.
* manifest.json carries the minimum schema with
  status='review_bundle_generated'.
* learning_modes_used lists the four pedagogical modes verbatim.
* Regenerating into a fresh dir produces byte-stable output
  (excluding LSP ``created_at``).
* At least two granularity variants are produced from the same
  fixture slice.
* HTML preview is self-contained (no ``<link>``/``<script>``
  external resources, no timestamps).
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

# Make the package-level scripts/ dir importable so we exercise the same
# generator entry point the regenerate.sh script invokes.
_PKG_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_PKG_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_PKG_SCRIPTS))

from generate_review_bundle_pedagogical import (  # noqa: E402
    BUNDLE_ARTIFACTS,
    LEARNING_MODES,
    MANIFEST_STATUS,
    PLAN_ID,
    generate_review_bundle_pedagogical,
)


# Same stripping recipe as test_review_bundle.py — the LSP's
# ``created_at`` field is the single permitted source of inter-run drift.
_TS_RE_JSON = re.compile(rb'"created_at"\s*:\s*"[^"]*"')


def _strip_timestamps(payload: bytes) -> bytes:
    return _TS_RE_JSON.sub(b'"created_at":"<STRIPPED>"', payload)


def _sha256_stripped(path: Path) -> str:
    return hashlib.sha256(_strip_timestamps(path.read_bytes())).hexdigest()


# Exactly the 9 keys from the specification (L335-L344) — no paraphrase.
_REQUIRED_MANIFEST_KEYS = (
    "plan_id",
    "status",
    "generator",
    "generator_version",
    "command",
    "learning_modes_used",
    "artifacts",
    "warnings",
    "unavailable_capabilities",
)


class TestPedagogicalReviewBundle:
    """Pedagogical review-bundle generation."""

    @pytest.mark.e2e
    def test_required_artifacts_present_and_non_empty(self, tmp_path: Path) -> None:
        """All 8 artifacts + manifest.json + regenerate.sh exist
        under the generated bundle dir and are non-empty.
        """
        out_dir = tmp_path / "bundle"
        generate_review_bundle_pedagogical(out_dir, work_dir=tmp_path / "work")

        for name in BUNDLE_ARTIFACTS:
            p = out_dir / name
            assert p.is_file(), f"missing bundle artifact: {name}"
            assert p.stat().st_size > 0, f"bundle artifact is empty: {name}"

        manifest_path = out_dir / "manifest.json"
        assert manifest_path.is_file(), "manifest.json missing"
        assert manifest_path.stat().st_size > 0, "manifest.json is empty"

        regen_path = out_dir / "regenerate.sh"
        assert regen_path.is_file(), "regenerate.sh missing"
        assert regen_path.stat().st_size > 0, "regenerate.sh is empty"

    @pytest.mark.e2e
    def test_manifest_minimum_schema(self, tmp_path: Path) -> None:
        """manifest.json contains the minimum schema with
        status='review_bundle_generated'.
        """
        out_dir = tmp_path / "bundle"
        generate_review_bundle_pedagogical(out_dir, work_dir=tmp_path / "work")

        manifest = json.loads((out_dir / "manifest.json").read_text("utf-8"))

        for key in _REQUIRED_MANIFEST_KEYS:
            assert key in manifest, f"manifest missing required key: {key!r}"

        # Status string MUST be exactly 'review_bundle_generated'.
        assert manifest["status"] == MANIFEST_STATUS == "review_bundle_generated"

        # Closure-rule guard: never auto-flipped to plan_closed at this stage.
        assert manifest["status"] != "plan_closed"

        # Plan id matches the canonical slug.
        assert manifest["plan_id"] == PLAN_ID == "akms_learn_pedagogical"

        # Generator identity.
        assert manifest["generator"] == "akms-learn"
        assert manifest["generator_version"] == "0.1.0"

        # Command string is the canonical regenerate invocation.
        assert "regenerate.sh" in manifest["command"]
        assert PLAN_ID in manifest["command"]

        # artifacts field lists the 8 §14 filenames, in §14 order.
        assert manifest["artifacts"] == list(BUNDLE_ARTIFACTS)

        # unavailable_capabilities is empty — every required pedagogical mode
        # is implemented.
        assert manifest["unavailable_capabilities"] == []

    @pytest.mark.e2e
    def test_learning_modes_used_lists_four_plan2_modes(self, tmp_path: Path) -> None:
        """manifest.learning_modes_used lists the four pedagogical modes
        verbatim, in §14 order.
        """
        out_dir = tmp_path / "bundle"
        generate_review_bundle_pedagogical(out_dir, work_dir=tmp_path / "work")

        manifest = json.loads((out_dir / "manifest.json").read_text("utf-8"))

        assert manifest["learning_modes_used"] == [
            "pedagogical_template",
            "derivation_first",
            "implementation_first",
            "multi_granularity",
        ]
        #   # Defensive: the generator constant must match the bundle-schema wording.
        assert list(LEARNING_MODES) == manifest["learning_modes_used"]

    @pytest.mark.e2e
    def test_regenerate_byte_stable_after_timestamp_strip(self, tmp_path: Path) -> None:
        """Running the generator into two fresh dirs yields
        byte-identical artifacts after stripping the LSP ``created_at``
        timestamp field.
        """
        out_a = tmp_path / "bundle_a"
        out_b = tmp_path / "bundle_b"
        generate_review_bundle_pedagogical(out_a, work_dir=tmp_path / "work_a")
        generate_review_bundle_pedagogical(out_b, work_dir=tmp_path / "work_b")

        files_a = sorted(p.relative_to(out_a) for p in out_a.rglob("*") if p.is_file())
        files_b = sorted(p.relative_to(out_b) for p in out_b.rglob("*") if p.is_file())
        assert files_a == files_b, (
            f"artifact set drift:\n  A: {files_a!r}\n  B: {files_b!r}"
        )

        mismatches: list[tuple[str, str, str]] = []
        for rel in files_a:
            ha = _sha256_stripped(out_a / rel)
            hb = _sha256_stripped(out_b / rel)
            if ha != hb:
                mismatches.append((str(rel), ha, hb))
        assert not mismatches, (
            "Non-timestamp content drifted across runs:\n  "
            + "\n  ".join(f"{r}: {a} != {b}" for r, a, b in mismatches)
        )

    @pytest.mark.e2e
    def test_multi_granularity_produces_at_least_two_variants(
        self, tmp_path: Path
    ) -> None:
        """multi_granularity mode produces ≥ 2 variants from the
        same fixture slice.

        Verified through the canonical ``source_packet.json``: its
        ``modes.multi_granularity`` payload MUST carry ≥ 2 keyed variants
        (one per granularity value).
        """
        out_dir = tmp_path / "bundle"
        generate_review_bundle_pedagogical(out_dir, work_dir=tmp_path / "work")

        payload = json.loads((out_dir / "source_packet.json").read_text("utf-8"))
        multi = payload["modes"]["multi_granularity"]
        assert isinstance(multi, dict), (
            "multi_granularity payload must be keyed by granularity variant"
        )
        assert len(multi) >= 2, (
            f"multi_granularity must emit ≥ 2 variants, got {len(multi)}"
        )

        # Each variant's request.granularity field must match its key.
        for variant_key, packet_payload in multi.items():
            req_gran = packet_payload["request"]["granularity"]
            assert req_gran == variant_key, (
                f"variant key {variant_key!r} disagrees with "
                f"request.granularity={req_gran!r}"
            )

        # The implementation_first lesson also surfaces both variants
        # in an appendix so reviewers can compare side-by-side.
        impl = (out_dir / "implementation_first_lesson.md").read_text("utf-8")
        assert "overview" in impl
        assert "deep_dive" in impl

    @pytest.mark.e2e
    def test_html_preview_self_contained(self, tmp_path: Path) -> None:
        """generated_preview.html has no external <link>/<script>
        resources and no timestamp strings.
        """
        out_dir = tmp_path / "bundle"
        generate_review_bundle_pedagogical(out_dir, work_dir=tmp_path / "work")

        html = (out_dir / "generated_preview.html").read_text("utf-8")

        # No external resource references at all (inline <style> is fine,
        # external <link> stylesheets and <script> tags are forbidden).
        assert "<link" not in html.lower(), "HTML preview must not <link> external CSS"
        assert "<script" not in html.lower(), (
            "HTML preview must not <script> external JS"
        )

        # No timestamp-like strings: ISO-8601 dates or HH:MM[:SS] clocks.
        ts_re = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{2}:\d{2}(:\d{2})?\b")
        m = ts_re.search(html)
        assert m is None, (
            f"HTML preview must contain no timestamp strings; found {m.group(0)!r}"
        )
