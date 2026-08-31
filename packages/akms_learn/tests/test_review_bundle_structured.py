"""Structured-modes review-bundle generator coverage.

Covers:

* All 8 required artifacts + manifest.json + regenerate.sh present
  and non-empty.
* AST canary — the generator module imports the real compiler /
  exporter path (``akms_learn.compiler`` + the toy fixtures), not
  hand-written content.
* manifest.json carries the nine schema keys with deterministic
  ordering; ``learning_modes_used`` lists the four structured modes
  verbatim.
* manifest.status == 'review_bundle_generated' (never 'plan_closed').
* The LLM-gated modes are recorded in
  manifest.unavailable_capabilities and the bundle still validates (no
  missing required artifact).

Also verifies byte-stability across two runs (modulo LSP ``created_at``).
"""

from __future__ import annotations

import ast
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

from generate_review_bundle_structured import (  # noqa: E402
    BUNDLE_ARTIFACTS,
    LEARNING_MODES,
    MANIFEST_STATUS,
    PLAN_ID,
    generate_review_bundle_structured,
)

_GENERATOR_PATH = _PKG_SCRIPTS / "generate_review_bundle_structured.py"


# Same stripping recipe as test_review_bundle_pedagogical.py — the LSP's
# ``created_at`` field is the single permitted source of inter-run drift.
_TS_RE_JSON = re.compile(rb'"created_at"\s*:\s*"[^"]*"')


def _strip_timestamps(payload: bytes) -> bytes:
    return _TS_RE_JSON.sub(b'"created_at":"<STRIPPED>"', payload)


def _sha256_stripped(path: Path) -> str:
    return hashlib.sha256(_strip_timestamps(path.read_bytes())).hexdigest()


# Exactly the 9 keys from the specification (L323-L334) — no paraphrase.
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


class TestStructuredReviewBundle:
    """Structured-modes review-bundle generation."""

    @pytest.mark.integration
    def test_required_artifacts_present_and_non_empty(self, tmp_path: Path) -> None:
        """All 8 artifacts + manifest.json + regenerate.sh exist
        under the generated bundle dir and are non-empty.
        """
        out_dir = tmp_path / "bundle"
        generate_review_bundle_structured(out_dir, work_dir=tmp_path / "work")

        assert len(BUNDLE_ARTIFACTS) == 8

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

        # CLOSURE.md / unavailable_capabilities.md are closure-gate
        # siblings — present alongside the bundle, but NOT among the eight
        # artifacts (verified by test_manifest_has_nine_keys_deterministic_order
        # / the dedicated closure tests).
        assert (out_dir / "CLOSURE.md").is_file()
        assert (out_dir / "unavailable_capabilities.md").is_file()
        assert "CLOSURE.md" not in BUNDLE_ARTIFACTS
        assert "unavailable_capabilities.md" not in BUNDLE_ARTIFACTS

    @pytest.mark.integration
    def test_generator_invokes_implemented_compiler_exporters(self) -> None:
        """AST canary — the generator imports the real implemented
        compiler / fixture modules (no hand-written artifact content).
        """
        tree = ast.parse(_GENERATOR_PATH.read_text("utf-8"))

        imported_modules: set[str] = set()
        imported_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)
                for alias in node.names:
                    imported_names.add(alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imported_modules.add(alias.name)

        # The generator drives the real compiler entry point.
        assert "akms_learn.compiler" in imported_modules
        assert "compile_learning_source" in imported_names

        # It compiles against the real toy fixtures (not literal content).
        assert "akms_learn.toy_fixtures" in imported_modules

        # It reads the implemented capabilities catalog to record unavailable
        # modes rather than hand-coding the list.
        assert "akms_learn.capabilities_catalog" in imported_modules
        assert "unavailable_capabilities" in imported_names

        #   # Closure-rule guard (bare-token form): the joined closed status
        #           # literal must never appear in the generator source. The CLOSURE.md
        #           # builder reintroduces the token at *runtime* by joining fragments, so
        #           # the literal still never appears in source — this check stays valid.
        #           # The assignment-aware AST canary lives in
        #           # test_review_bundle_structured_closure.py.
        src = _GENERATOR_PATH.read_text("utf-8")
        assert "plan_closed" not in src, (
            "generator source must never contain the joined plan_closed literal"
        )

    @pytest.mark.integration
    def test_manifest_has_nine_keys_deterministic_order(self, tmp_path: Path) -> None:
        """manifest.json contains the nine schema keys; the
        on-disk JSON is deterministically ordered (sort_keys); and
        ``learning_modes_used`` lists the four §15 modes verbatim.
        """
        out_dir = tmp_path / "bundle"
        generate_review_bundle_structured(out_dir, work_dir=tmp_path / "work")

        manifest_text = (out_dir / "manifest.json").read_text("utf-8")
        manifest = json.loads(manifest_text)

        for key in _REQUIRED_MANIFEST_KEYS:
            assert key in manifest, f"manifest missing required key: {key!r}"
        assert set(manifest.keys()) == set(_REQUIRED_MANIFEST_KEYS), (
            "manifest has unexpected keys"
        )

        # Deterministic on-disk ordering: sort_keys=True → alphabetical.
        on_disk_order = list(manifest.keys())
        assert on_disk_order == sorted(_REQUIRED_MANIFEST_KEYS)

        # Plan id matches the canonical slug.
        assert manifest["plan_id"] == PLAN_ID == "akms_learn_structured"

        # Generator identity.
        assert manifest["generator"] == "akms-learn"
        assert manifest["generator_version"] == "0.1.0"

        # Command string is the canonical regenerate invocation.
        assert "regenerate.sh" in manifest["command"]
        assert PLAN_ID in manifest["command"]

        # artifacts field lists the 8 §15 filenames, in §15 order.
        assert manifest["artifacts"] == list(BUNDLE_ARTIFACTS)

        # learning_modes_used lists the four §15 modes verbatim, in §15 order.
        assert manifest["learning_modes_used"] == [
            "notebook_source",
            "assessment_first",
            "llm_expanded_lesson",
            "adaptive_path",
        ]
        assert list(LEARNING_MODES) == manifest["learning_modes_used"]

    @pytest.mark.integration
    def test_manifest_status_is_review_bundle_generated(self, tmp_path: Path) -> None:
        """manifest.status == 'review_bundle_generated', never
        'plan_closed'.
        """
        out_dir = tmp_path / "bundle"
        generate_review_bundle_structured(out_dir, work_dir=tmp_path / "work")

        manifest = json.loads((out_dir / "manifest.json").read_text("utf-8"))

        assert manifest["status"] == MANIFEST_STATUS == "review_bundle_generated"
        assert manifest["status"] != "plan_closed"

    @pytest.mark.integration
    def test_unavailable_mode_recorded_bundle_still_validates(
        self, tmp_path: Path
    ) -> None:
        """The LLM-gated modes are recorded in
        manifest.unavailable_capabilities and the bundle still has every
        required artifact.
        """
        out_dir = tmp_path / "bundle"
        generate_review_bundle_structured(out_dir, work_dir=tmp_path / "work")

        manifest = json.loads((out_dir / "manifest.json").read_text("utf-8"))

        unavailable = manifest["unavailable_capabilities"]
        assert isinstance(unavailable, list)
        # In a clean checkout the ``llm`` extra is absent → both LLM-gated
        # modes are reported unavailable.
        unavail_caps = {entry["capability"] for entry in unavailable}
        assert {"llm_expanded", "adaptive_path"} <= unavail_caps, (
            f"expected LLM-gated modes in unavailable_capabilities, "
            f"got {sorted(unavail_caps)}"
        )
        for entry in unavailable:
            assert entry["missing_extra"] == "llm"

        # Despite the unavailable modes, every required artifact is present.
        for name in BUNDLE_ARTIFACTS:
            p = out_dir / name
            assert p.is_file() and p.stat().st_size > 0, (
                f"bundle invalid: missing/empty {name}"
            )

    @pytest.mark.integration
    def test_regenerate_byte_stable_after_timestamp_strip(self, tmp_path: Path) -> None:
        """Determinism: running the generator into two fresh dirs yields
        byte-identical artifacts after stripping the LSP ``created_at``
        timestamp field.
        """
        out_a = tmp_path / "bundle_a"
        out_b = tmp_path / "bundle_b"
        generate_review_bundle_structured(out_a, work_dir=tmp_path / "work_a")
        generate_review_bundle_structured(out_b, work_dir=tmp_path / "work_b")

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

    @pytest.mark.integration
    def test_html_preview_self_contained(self, tmp_path: Path) -> None:
        """The generated_preview.html has no external <link>/<script>
        resources (it is produced by the implemented HTML exporter).
        """
        out_dir = tmp_path / "bundle"
        generate_review_bundle_structured(out_dir, work_dir=tmp_path / "work")

        html = (out_dir / "generated_preview.html").read_text("utf-8")
        assert "<link" not in html.lower()
        assert "<script" not in html.lower()
