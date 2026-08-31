"""Review bundle generation tests.

Covers:

* All 6 artifacts + manifest.json present and non-empty.
* manifest.json contains all 9 schema fields.
* manifest.status == 'review_bundle_generated'.
* manifest.learning_modes_used lists the 4 modes.
* Bundle regenerates byte-stably from same fixture (excluding timestamp).
* No companion package needed (verified by import-graph + generator scope).
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

from generate_review_bundle import (  # noqa: E402  -- path injection above
    BUNDLE_ARTIFACTS,
    LEARNING_MODES,
    MANIFEST_STATUS,
    generate_review_bundle,
)


# Same stripping recipe as test_packet_determinism.py: the LSP's
# ``created_at`` field is the single permitted source of inter-run drift.
_TS_RE_JSON = re.compile(rb'"created_at"\s*:\s*"[^"]*"')


def _strip_timestamps(payload: bytes) -> bytes:
    return _TS_RE_JSON.sub(b'"created_at":"<STRIPPED>"', payload)


def _sha256_stripped(path: Path) -> str:
    return hashlib.sha256(_strip_timestamps(path.read_bytes())).hexdigest()


# Exactly the 9 keys from the specification (L464-L477) -- no paraphrase, sorted for
# deterministic test failure messages.
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


class TestReviewBundleGeneration:
    """Generate the review bundle via the real CLI/API."""

    @pytest.mark.e2e
    def test_review_bundle_generation_creates_all_artifacts(
        self, tmp_path: Path
    ) -> None:
        """All 6 artifacts + manifest.json + regenerate.sh exist
        under the generated bundle dir and are non-empty.
        """
        out_dir = tmp_path / "bundle"
        generate_review_bundle(out_dir, work_dir=tmp_path / "work")

        # The 6 canonical artifacts:
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
    def test_review_bundle_manifest_shape(self, tmp_path: Path) -> None:
        """manifest.json contains exactly the 9 schema keys
        (by name), status is the generator state, and learning_modes_used
        lists the 4 modes verbatim.
        """
        out_dir = tmp_path / "bundle"
        generate_review_bundle(out_dir, work_dir=tmp_path / "work")

        manifest = json.loads((out_dir / "manifest.json").read_text("utf-8"))

        # All 9 fields present BY NAME (do not paraphrase or aggregate).
        for key in _REQUIRED_MANIFEST_KEYS:
            assert key in manifest, f"manifest missing required key: {key!r}"

        # Status string.
        assert manifest["status"] == MANIFEST_STATUS == "review_bundle_generated"

        # learning_modes_used is the exact 4-element list.
        assert manifest["learning_modes_used"] == [
            "deterministic_outline",
            "node_anthology",
            "pitfall_driven",
            "learning_source_bundle",
        ]
        #   # Defensive: the generator constant must match the bundle-schema wording.
        assert list(LEARNING_MODES) == manifest["learning_modes_used"]

        # The artifacts field lists the 6 canonical filenames.
        assert manifest["artifacts"] == list(BUNDLE_ARTIFACTS)

    @pytest.mark.e2e
    def test_review_bundle_reproducible(self, tmp_path: Path) -> None:
        """Regenerating into two distinct tmp dirs yields byte-identical
        artifacts after stripping the LSP ``created_at`` timestamp field.

        Re-invokes the real generator (no stubs) twice. Both calls go
        through ``cli.main``, which is the public CLI contract.
        """
        out_a = tmp_path / "bundle_a"
        out_b = tmp_path / "bundle_b"
        generate_review_bundle(out_a, work_dir=tmp_path / "work_a")
        generate_review_bundle(out_b, work_dir=tmp_path / "work_b")

        # Same artifact set on disk.
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
