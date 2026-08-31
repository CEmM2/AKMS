"""Tests for akms._resources.

PR18-T3: shared helper for locating bundled ``seed/`` files. Replaces the
ad-hoc ``Path(__file__).parents[N]`` and ``_repo.parent`` chains that were
scattered through ``mcp_tools.py`` and ``generate_loadout.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from akms._resources import _package_root, seed_qmd_path


class TestPackageRoot:
    def test_package_root_contains_bundled_and_src(self):
        """Package root must be the directory holding ``src/`` and its bundled tree."""
        root = _package_root()
        assert (root / "src" / "akms").is_dir(), (
            f"Expected src/akms under {root}; if _package_root drifted it will "
            "point somewhere else, breaking every importer."
        )
        assert (root / "src" / "akms" / "_bundled").is_dir(), (
            f"Expected src/akms/_bundled under {root}; the resource helper "
            "resolves bundled resources there. (The pre-relocation ``seed/`` "
            "tree is not shipped in the public repo.)"
        )


class TestSeedQmdPath:
    def test_falls_back_to_package_root(self):
        """With no importlib bundle and no candidates, the helper resolves to
        the package-root ``seed/qmd/`` directory."""
        resolved = seed_qmd_path("run_qmd.sh")
        assert resolved.exists(), (
            f"Fallback path must exist: {resolved}. Check that seed/qmd/"
            "run_qmd.sh is present in Packages/AKMS/."
        )
        assert resolved.name == "run_qmd.sh"
        assert resolved.parent.name == "qmd"

    def test_repo_root_candidate_wins_when_file_present(self, tmp_path):
        """A caller-supplied repo_root candidate wins over the package-root
        fallback when it actually contains the file."""
        fake_repo = tmp_path / "repo"
        (fake_repo / "seed" / "qmd").mkdir(parents=True)
        custom = fake_repo / "seed" / "qmd" / "custom.sh"
        custom.write_text("# stub\n")

        resolved = seed_qmd_path("custom.sh", repo_root_candidates=[fake_repo])
        assert resolved == custom

    def test_nonexistent_name_returns_fallback_path_anyway(self):
        """The helper is side-effect-free: it returns a Path even when the
        resolved file does not exist, so callers can surface a clear error."""
        resolved = seed_qmd_path("does-not-exist.sh")
        assert not resolved.exists()
        assert resolved.parent.name == "qmd"

    def test_missing_candidate_directory_is_skipped(self, tmp_path):
        """A candidate that doesn't contain the file is skipped — the helper
        keeps walking until it reaches the package-root fallback."""
        missing = tmp_path / "nope"
        resolved = seed_qmd_path(
            "run_qmd.sh",
            repo_root_candidates=[missing],
        )
        # Falls through to the package root.
        assert resolved.exists()
        assert "Packages/AKMS" in str(resolved) or "AKMS" in str(resolved)
