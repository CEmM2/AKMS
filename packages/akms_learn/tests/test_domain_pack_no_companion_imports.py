"""AST scan asserts zero companion imports.

The whole ``akms_learn`` runtime is data-only with respect to the three
computational-mechanics companion packages. Any top-level ``import
constkit`` / ``from mechdsl import x`` / etc. would silently couple the
core compiler to a real installation requirement and break the specification's
"no companion installed" closure condition (L425).

This test walks every ``.py`` file under
``packages/akms_learn/src/akms_learn/`` and rejects any
:class:`ast.Import` / :class:`ast.ImportFrom` node whose top-level module
name is in the forbidden set.

String literals that mention these names (in docstrings, descriptor
``package_name`` defaults, fixture loaders, log messages) are FINE and must
NOT be flagged — the scan is restricted to import-node attributes.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

_SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "akms_learn"

FORBIDDEN_COMPANIONS: frozenset[str] = frozenset(
    {"constkit", "mechdsl", "symbolic_fem_workbench"}
)


def _top_module(dotted: str) -> str:
    """Return the leftmost component of a dotted module path."""
    return dotted.split(".", 1)[0]


def _scan_imports(tree: ast.AST) -> list[tuple[int, str]]:
    """Return ``(lineno, dotted_name)`` for every import in *tree*.

    Only inspects :class:`ast.Import` (``import X``) and
    :class:`ast.ImportFrom` (``from X import Y``) nodes. Skips
    :class:`ast.ImportFrom` rows with ``module is None`` (relative imports
    of the form ``from . import x``), which can never reference a top-level
    companion package.
    """
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                hits.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            hits.append((node.lineno, node.module))
    return hits


@pytest.mark.integration
def test_no_companion_imports_in_src() -> None:
    """Zero forbidden imports in the entire akms_learn source tree."""
    assert _SRC_ROOT.is_dir(), f"src tree missing: {_SRC_ROOT!s}"

    py_files = sorted(_SRC_ROOT.rglob("*.py"))
    assert py_files, "No .py files discovered under src/akms_learn/"

    offenders: list[tuple[Path, int, str]] = []
    for py in py_files:
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for lineno, dotted in _scan_imports(tree):
            if _top_module(dotted) in FORBIDDEN_COMPANIONS:
                offenders.append((py, lineno, dotted))

    assert not offenders, (
        "Forbidden companion imports detected in src/akms_learn/ — "
        "Plan §22 / spec §4 invariant violated:\n"
        + "\n".join(f"  {p}:{ln}  ->  {name}" for p, ln, name in offenders)
    )


@pytest.mark.integration
def test_scan_is_restricted_to_import_nodes() -> None:
    """Self-test: a module with a forbidden NAME as a string literal but no
    actual import statements MUST NOT trigger the scan.

    Guards against false positives — the scan must look at
    :class:`ast.Import` / :class:`ast.ImportFrom` only, never at string
    contents or attribute accesses.
    """
    sample_source = (
        '"""docstring mentioning constkit, mechdsl, symbolic_fem_workbench"""\n'
        'package_names = ("constkit", "mechdsl", "symbolic_fem_workbench")\n'
        'msg = f"import {package_names[0]!r}"\n'
        "import os\n"
        "from pathlib import Path\n"
    )
    tree = ast.parse(sample_source)
    hits = _scan_imports(tree)
    flagged = [d for _, d in hits if _top_module(d) in FORBIDDEN_COMPANIONS]
    assert not flagged, (
        f"AST scan false-positive: flagged {flagged!r} on a sample that "
        "contains no real import of any forbidden companion."
    )
    # And sanity-check that real imports are picked up at all.
    assert any(d == "os" or d == "pathlib" for _, d in hits)


@pytest.mark.integration
def test_scan_detects_real_forbidden_import() -> None:
    """Self-test: an actual ``import constkit`` statement MUST be flagged.

    Confirms the scan isn't silently underreporting hits — the safety net
    works in both directions.
    """
    bad_source = (
        "import constkit\n"
        "from mechdsl import core\n"
        "from symbolic_fem_workbench.notebooks import demo\n"
    )
    tree = ast.parse(bad_source)
    hits = _scan_imports(tree)
    flagged = sorted({_top_module(d) for _, d in hits})
    assert flagged == sorted(FORBIDDEN_COMPANIONS), (
        f"AST scan failed to flag known-bad imports: got {flagged!r}"
    )
