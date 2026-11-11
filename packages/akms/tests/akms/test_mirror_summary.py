"""A code mirror's summary built from the mirror itself."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from akms.graph.mirror_summary import _python_docstring, derive_mirror_summary
from akms.repo_wiki.export import export_akms

FIXTURE_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "repo_wiki"
    / "fixtures"
    / "akms_export"
    / "source_repo"
)
PACKAGE_SOURCE = Path(__file__).resolve().parents[2] / "src" / "akms" / "repo_wiki"


def _body(mirror: Path) -> str:
    return mirror.read_text(encoding="utf-8").split("---\n", 2)[2]


@pytest.mark.parametrize(
    "source", [FIXTURE_SOURCE, PACKAGE_SOURCE], ids=lambda p: p.name
)
def test_the_built_summary_is_the_one_the_exporter_writes(tmp_path, source):
    """Export with summaries on, remove each section, and build it again."""
    repo = tmp_path / "repo"
    shutil.copytree(source, repo, ignore=shutil.ignore_patterns("__pycache__"))
    (repo / ".repo_wiki").mkdir(exist_ok=True)
    (repo / ".repo_wiki" / "config.yaml").write_text(
        "export:\n  mirror_summary: true\n", encoding="utf-8"
    )
    result = export_akms(
        repo_root=repo,
        output_root=tmp_path / "out",
        phase=1,
        generated_at="2026-01-01T00:00:00+00:00",
        changed_only=False,
        prune=False,
    )
    assert not result.errors
    mirrors = sorted((tmp_path / "out").rglob("code-mirror/**/*.md"))
    assert mirrors
    for mirror in mirrors:
        body = _body(mirror)
        written = re.search(
            r"\n## Summary\n\n(.*?)\n\n## Symbol Index\n", body, re.DOTALL
        )
        assert written, mirror
        without = body.replace(f"## Summary\n\n{written[1]}\n\n", "", 1)
        assert derive_mirror_summary(without) == written[1], mirror
        # What the loadout generator passes: the body with outer space removed.
        assert derive_mirror_summary(without.strip()) == written[1], mirror


@pytest.mark.parametrize(
    "body",
    [
        "",
        "No index here.\n",
        "## Symbol Index\n\n```json\nnot json\n```\n",
        '## Symbol Index\n\n```json\n{"symbol_id": "x"}\n```\n',
        '## Symbol Index\n\n```json\n[{"kind": "function"}]\n```\n',
        '## Symbol Index\n\n```json\n[{"symbol_id": 1, "kind": "function"}]\n```\n',
        "## Symbol Index\n\n```json\n[1, 2]\n```\n",
    ],
)
def test_a_body_without_a_usable_index_has_no_built_summary(body):
    assert derive_mirror_summary(body) is None


@pytest.mark.parametrize(
    ("source", "docstring"),
    [
        ('"""One line."""\nimport os\n', "One line."),
        ('# comment\n\n"""After a comment."""\n', "After a comment."),
        ("'''First.\n\n    Indented more.\n'''\n", "First.\n\nIndented more."),
        ('"a" "b"\n', "ab"),
        ("import os\n'''Not first.'''\n", None),
        ('x = """Assigned."""\n', None),
        ('f"""Formatted."""\n', None),
        ('b"""Bytes."""\n', None),
        ('"""Never closed\n', None),
        ("", None),
    ],
)
def test_the_module_docstring_is_the_first_statement_only(source, docstring):
    assert _python_docstring(source) == docstring


def test_only_a_python_mirror_takes_its_docstring_from_the_source():
    index = (
        "## Symbol Index\n\n```json\n"
        '[{"symbol_id": "m::m", "kind": "module", "start_line": 1, "end_line": 1}]'
        "\n```\n\n## Complete Source\n\n```LANGUAGE\n"
        '"""Says hello."""\n```\n'
    )
    assert derive_mirror_summary(index.replace("LANGUAGE", "python")) == "Says hello."
    assert derive_mirror_summary(index.replace("LANGUAGE", "cpp")) == (
        "No module docstring and no public classes or functions."
    )
