"""The bundled ``repo-wiki-code-intel`` skill ships, loads, is listed, and matches the CLI."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import yaml

from akms._resources import bundled_skills_path
from akms.repo_wiki.cli import build_parser
from akms.repo_wiki.impact import PUBLIC_ENTRY_CAP, RISK_THRESHOLDS

SKILL = "repo-wiki-code-intel"
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _PACKAGE_ROOT.parents[1]


def _frontmatter(text: str) -> dict:
    assert text.startswith("---\n")
    data = yaml.safe_load(text.split("---\n", 2)[1])
    assert isinstance(data, dict)
    return data


def test_skill_is_bundled_with_loadable_frontmatter() -> None:
    skill_dir = bundled_skills_path(SKILL)
    skill_md = skill_dir / "SKILL.md"
    assert skill_md.is_file()
    assert (skill_dir / "references" / "json_output.md").is_file()
    data = _frontmatter(skill_md.read_text(encoding="utf-8"))
    assert data["name"] == SKILL
    assert "impact" in data["description"] and "changes" in data["description"]
    assert "repo-wiki flows" in data["description"]


def test_skill_is_listed_like_the_other_bundled_skills() -> None:
    root = bundled_skills_path()
    listed = [p.name for p in sorted(root.iterdir()) if (p / "SKILL.md").is_file()]
    assert SKILL in listed
    readme = (root / "README.md").read_text(encoding="utf-8")
    docs = (_REPO_ROOT / "docs" / "getting-started" / "agent-skills.md").read_text(
        encoding="utf-8"
    )
    for skill in listed:
        assert f"`skills/{skill}/`" in readme, f"{skill} missing from skills README"
        assert f"`skills/{skill}/`" in docs, f"{skill} missing from agent-skills page"


def test_wheel_package_data_covers_the_skill() -> None:
    pyproject = tomllib.loads((_PACKAGE_ROOT / "pyproject.toml").read_text("utf-8"))
    patterns = pyproject["tool"]["setuptools"]["package-data"]["akms"]
    assert "_bundled/skills/**/*" in patterns


def test_skill_names_only_real_commands_and_flags() -> None:
    text = (bundled_skills_path(SKILL) / "SKILL.md").read_text(encoding="utf-8")
    parser = build_parser()
    sub = next(a for a in parser._actions if a.dest == "command")
    choices = sub.choices  # type: ignore[attr-defined]
    for command, rest in re.findall(
        r"repo-wiki (context|impact|changes|build|flows|flow)([^\n`]*)", text
    ):
        flags = re.findall(r"(--[a-z-]+)", rest)
        known = {
            opt for action in choices[command]._actions for opt in action.option_strings
        }
        for flag in flags:
            assert flag in known, f"`repo-wiki {command}` has no {flag}"


def test_skill_risk_table_matches_the_code() -> None:
    text = (bundled_skills_path(SKILL) / "SKILL.md").read_text(encoding="utf-8")
    for level, min_d1, min_modules in RISK_THRESHOLDS:
        row = next(
            line for line in text.splitlines() if line.startswith(f"| {level} |")
        )
        assert f"{min_d1}+" in row and f"{min_modules}+" in row, row
    assert PUBLIC_ENTRY_CAP == "HIGH" and "never to\nCRITICAL on its own" in text


def test_skill_points_agents_at_the_cli_only() -> None:
    skill_dir = bundled_skills_path(SKILL)
    for path in skill_dir.rglob("*.md"):
        text = path.read_text(encoding="utf-8")
        assert "mcp" not in text.lower(), path
        assert "git" + "nexus" not in text.lower(), path
