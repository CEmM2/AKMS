"""Incremental build behaviour and time budgets on the larger perf fixture."""

from __future__ import annotations

import json
import time
from pathlib import Path

from akms.repo_wiki.cli import main
from .test_build_render_graph_summary import copy_fixture

PERF_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "perf_repo"

# Generous enough for slow CI runners, tight enough to catch a 10x regression.
FULL_BUILD_BUDGET_SECONDS = 30.0
INCREMENTAL_BUILD_BUDGET_SECONDS = 5.0


def _build_json(root: Path, capsys, *flags: str) -> dict[str, object]:
    capsys.readouterr()
    code = main(
        [
            "--repo-root",
            str(root),
            "build",
            "--no-summaries",
            "--no-index",
            "--json",
            *flags,
        ]
    )
    assert code == 0
    return json.loads(capsys.readouterr().out)


def test_changed_only_build_parses_only_edited_files(tmp_path: Path, capsys):
    """A no-op incremental build parses nothing; editing one file parses exactly that file."""
    copy_fixture(PERF_FIXTURE, tmp_path)

    assert int(_build_json(tmp_path, capsys)["parsed"]) >= 50
    assert int(_build_json(tmp_path, capsys, "--changed-only")["parsed"]) == 0

    target = tmp_path / "pkg" / "mod_07.py"
    target.write_text(
        target.read_text(encoding="utf-8") + "\n\n# edited\n", encoding="utf-8"
    )
    assert int(_build_json(tmp_path, capsys, "--changed-only")["parsed"]) == 1


def test_full_and_incremental_builds_stay_within_time_budget(tmp_path: Path, capsys):
    """A full build and a no-op incremental build finish within their budgets."""
    copy_fixture(PERF_FIXTURE, tmp_path)

    started = time.perf_counter()
    _build_json(tmp_path, capsys)
    assert time.perf_counter() - started < FULL_BUILD_BUDGET_SECONDS

    started = time.perf_counter()
    _build_json(tmp_path, capsys, "--changed-only")
    assert time.perf_counter() - started < INCREMENTAL_BUILD_BUDGET_SECONDS
