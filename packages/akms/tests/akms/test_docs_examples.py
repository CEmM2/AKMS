"""Regression guards for Python examples in the public documentation."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent


REPO_ROOT = Path(__file__).resolve().parents[4]
DOCS_ROOT = REPO_ROOT / "docs"
PUBLIC_IMPORT_RE = re.compile(r"^(?:from|import)\s+(?:akms|akms_learn)(?:[.\s,]|$)")


@dataclass(frozen=True)
class PythonFence:
    """A Python code fence and its source location."""

    path: Path
    line: int
    source: str


def _python_fences(path: Path) -> Iterator[PythonFence]:
    """Yield Python code fences from one Markdown file."""

    lines = path.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped not in {"```python", "```py"}:
            index += 1
            continue

        opening_line = index + 1
        index += 1
        body: list[str] = []
        while index < len(lines) and lines[index].strip() != "```":
            body.append(lines[index])
            index += 1

        if index == len(lines):
            raise AssertionError(
                f"{path.relative_to(REPO_ROOT)}:{opening_line}: unclosed Python fence"
            )

        yield PythonFence(
            path=path, line=opening_line + 1, source=dedent("\n".join(body))
        )
        index += 1


def _all_python_fences() -> Iterator[PythonFence]:
    """Yield Python fences from every Markdown file under docs/."""

    for path in sorted(DOCS_ROOT.rglob("*.md")):
        yield from _python_fences(path)


def _public_imports(fence: PythonFence) -> Iterator[tuple[int, str]]:
    """Yield complete AKMS import statements, including multiline imports."""

    lines = fence.source.splitlines()
    index = 0
    while index < len(lines):
        statement = lines[index].lstrip()
        if not PUBLIC_IMPORT_RE.match(statement):
            index += 1
            continue

        start_line = fence.line + index
        parts = [statement]
        balance = statement.count("(") - statement.count(")")
        while balance > 0 or parts[-1].rstrip().endswith("\\"):
            index += 1
            if index >= len(lines):
                break
            part = lines[index].strip()
            parts.append(part)
            balance += part.count("(") - part.count(")")

        yield start_line, "\n".join(parts)
        index += 1


def test_documented_akms_imports_execute() -> None:
    """Every documented AKMS import must resolve against installed packages."""

    checked = 0
    for fence in _all_python_fences():
        for line, statement in _public_imports(fence):
            location = f"{fence.path.relative_to(REPO_ROOT)}:{line}"
            exec(compile(statement, location, "exec"), {})
            checked += 1

    assert checked, "No documented akms or akms_learn imports were found"
