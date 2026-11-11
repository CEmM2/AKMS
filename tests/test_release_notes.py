"""The release page takes its notes from one CHANGELOG.md section."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "release_notes", ROOT / "scripts" / "release_notes.py"
)
assert _spec is not None and _spec.loader is not None
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
release_notes = _module.release_notes

CHANGELOG = (
    "# Changelog\n\nIntro.\n\n"
    "## [0.4.0] — 2026-11-11\n\n### Added\n- New thing.\n\n### Fixed\n- A fix.\n\n"
    "## [0.3.2] — 2026-10-06\n\n### Fixed\n- Older fix.\n\n"
    "## [0.3.0] — 2026-08-31\n"
)


def test_the_notes_are_one_section_without_its_heading():
    assert release_notes(CHANGELOG, "0.4.0") == (
        "### Added\n- New thing.\n\n### Fixed\n- A fix.\n"
    )
    assert release_notes(CHANGELOG, "0.3.2") == "### Fixed\n- Older fix.\n"


@pytest.mark.parametrize("version", ["0.4", "0.4.01", "0.3.1", "0.3.0"])
def test_a_missing_or_empty_section_is_an_error(version):
    with pytest.raises(ValueError):
        release_notes(CHANGELOG, version)


def test_the_current_version_has_notes_that_fit_a_release_page():
    import tomllib

    version = tomllib.loads(
        (ROOT / "packages" / "akms" / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    notes = release_notes((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), version)
    # GitHub refuses a release body over 125,000 characters.
    assert 0 < len(notes) < 125_000
