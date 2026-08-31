"""The bundled resource mirror must stay identical to its canonical sources.

Anything outside the package directory is absent from the built wheel. That is
why ``run_qmd.sh`` — which lived only at ``Packages/AKMS/seed/qmd/`` — never
shipped, leaving the three ``akms_search_*`` MCP tools inert in a wheel-only
install, and why the repo-root ``skills/`` tree could not reach anyone who ran
``pip install akms``.

``src/akms/_bundled/`` is a **mirror** of those canonical trees, declared as
package data so a wheel carries them. The canonical copies stay where they are:

    Packages/AKMS/seed/*   ->  src/akms/_bundled/*      (qmd, global_nodes, ...)
    skills/                ->  src/akms/_bundled/skills

Mirrors drift. This repo has already been bitten by that once, when a mirrored
predicate diverged from its original unnoticed. These tests make drift fail the
build instead of shipping silently.

To resync after editing a canonical tree, run ``scripts/sync_bundled.sh``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


_REPO_ROOT = Path(__file__).resolve().parents[4]
_BUNDLED = _REPO_ROOT / "Packages" / "AKMS" / "src" / "akms" / "_bundled"
_SEED = _REPO_ROOT / "Packages" / "AKMS" / "seed"

# The public repo ships no canonical trees to compare against: there is no
# repo-root ``skills/`` and no ``seed/``. ``src/akms/_bundled`` IS canonical
# here, so nothing can drift. The guard stays live in the private repo,
# where both sides of every mirror exist.
if not (_SEED.is_dir() and (_REPO_ROOT / "skills").is_dir()):
    pytest.skip(
        "mirror-drift guard requires the private two-tree layout; "
        "src/akms/_bundled is canonical in the public repo",
        allow_module_level=True,
    )

# (label, canonical path, mirrored path)
MIRRORS = [
    ("skills", _REPO_ROOT / "skills", _BUNDLED / "skills"),
    ("agents", _REPO_ROOT / "agents", _BUNDLED / "agents"),
    ("commands", _REPO_ROOT / "commands", _BUNDLED / "commands"),
    ("hooks", _REPO_ROOT / "hooks", _BUNDLED / "hooks"),
    ("seed/qmd", _SEED / "qmd", _BUNDLED / "qmd"),
    ("seed/global_nodes", _SEED / "global_nodes", _BUNDLED / "global_nodes"),
]

_RESYNC = "\n\nResync with:\n  bash scripts/sync_bundled.sh"


def _relative_files(root: Path) -> dict[str, Path]:
    """Map root-relative path -> absolute path, ignoring caches."""
    out: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.name == ".DS_Store":
            continue
        out[str(path.relative_to(root))] = path
    return out


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "label,canonical,mirrored", MIRRORS, ids=[m[0] for m in MIRRORS]
)
def test_mirror_trees_exist(label: str, canonical: Path, mirrored: Path) -> None:
    assert canonical.is_dir(), f"canonical {label} tree missing at {canonical}"
    assert mirrored.is_dir(), f"bundled {label} mirror missing at {mirrored}.{_RESYNC}"


@pytest.mark.parametrize(
    "label,canonical,mirrored", MIRRORS, ids=[m[0] for m in MIRRORS]
)
def test_mirror_has_same_file_set(label: str, canonical: Path, mirrored: Path) -> None:
    left = set(_relative_files(canonical))
    right = set(_relative_files(mirrored))

    missing = sorted(left - right)
    extra = sorted(right - left)

    assert not missing, (
        f"{len(missing)} file(s) in {label} are missing from the bundled mirror, "
        f"so a wheel install would not carry them: {missing}{_RESYNC}"
    )
    assert not extra, (
        f"{len(extra)} file(s) in the {label} mirror have no canonical "
        f"counterpart: {extra}{_RESYNC}"
    )


@pytest.mark.parametrize(
    "label,canonical,mirrored", MIRRORS, ids=[m[0] for m in MIRRORS]
)
def test_mirror_has_identical_content(
    label: str, canonical: Path, mirrored: Path
) -> None:
    left = _relative_files(canonical)
    right = _relative_files(mirrored)

    differing = [
        rel
        for rel, path in sorted(left.items())
        if rel in right and _digest(path) != _digest(right[rel])
    ]

    assert not differing, (
        f"{len(differing)} bundled {label} file(s) differ from canonical: "
        f"{differing}{_RESYNC}"
    )


def test_claude_md_kernel_is_mirrored() -> None:
    canonical = _SEED / "claude_md_kernel.md"
    mirrored = _BUNDLED / "claude_md_kernel.md"
    assert canonical.is_file(), f"canonical kernel missing at {canonical}"
    assert mirrored.is_file(), f"bundled kernel missing at {mirrored}.{_RESYNC}"
    assert _digest(canonical) == _digest(mirrored), (
        f"claude_md_kernel.md differs between canonical and mirror{_RESYNC}"
    )


def test_bundled_skills_reachable_through_resources_helper() -> None:
    """The accessor consumers are told to use must actually resolve."""
    from akms._resources import bundled_skills_path

    root = bundled_skills_path()
    assert root.exists(), f"bundled_skills_path() does not resolve: {root}"

    akms_skill = bundled_skills_path("akms") / "SKILL.md"
    assert akms_skill.exists(), f"akms SKILL.md not reachable at {akms_skill}"


def test_qmd_wrapper_resolves_from_the_bundled_mirror() -> None:
    """seed_qmd_path must prefer the packaged copy.

    If it falls back to the canonical ``Packages/AKMS/seed/`` path, the lookup
    is working only because a source tree happens to be present — which is
    exactly the condition that made search inert for wheel installs.
    """
    from akms._resources import seed_qmd_path

    wrapper = seed_qmd_path("run_qmd.sh")
    assert wrapper.exists(), f"run_qmd.sh not resolvable: {wrapper}"
    assert "_bundled" in wrapper.parts, (
        f"run_qmd.sh resolved to {wrapper}, outside the package. It must come "
        "from akms/_bundled/qmd/ so it ships in the wheel."
    )


def test_promoted_assets_carry_loadable_frontmatter() -> None:
    """Every published skill and agent must be loadable by name.

    digest-refiner shipped internally with NO frontmatter at all, so no agent
    runtime could load it; the published copy adds it. This asserts that class of
    defect cannot come back.
    """
    import yaml

    targets = sorted(
        [
            *(_REPO_ROOT / "skills").glob("*/SKILL.md"),
            *(_REPO_ROOT / "agents").glob("*.md"),
        ]
    )
    assert targets, "no promoted skills or agents found"

    for path in targets:
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(_REPO_ROOT)
        assert text.startswith("---\n"), f"{rel} has no YAML frontmatter"
        block = text.split("---\n", 2)[1]
        data = yaml.safe_load(block)
        assert isinstance(data, dict), f"{rel} frontmatter is not a mapping"
        assert data.get("name"), f"{rel} frontmatter has no name"
        assert data.get("description"), f"{rel} frontmatter has no description"


def test_published_assets_do_not_read_from_dot_claude() -> None:
    """A published copy must not READ from the stripped internal harness dirs.

    `.claude/`, `.codex/`, and `.agents/` are removed from every published copy, so
    a published asset that tells the agent to open a file under one of them is
    pointing at nothing.

    Two things are legitimate and are not flagged:

      * README files, whose whole job is to document installing INTO `.claude/`
        on the consumer's machine — that is a destination, not a source; and
      * provenance blockquotes naming the internal origin.
    """
    offenders: list[str] = []
    internal = (".claude/skills", ".claude/agents", ".claude/commands", ".claude/hooks")

    for root in ("skills", "agents", "commands", "hooks"):
        base = _REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in {".md", ".sh", ".py"}:
                continue
            if path.name == "README.md":
                # Install docs legitimately name .claude/ as the destination.
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for number, line in enumerate(text.splitlines(), 1):
                if not any(token in line for token in internal):
                    continue
                stripped = line.strip()
                # provenance blockquote
                if stripped.startswith(">"):
                    continue
                # install instruction: the internal path is the DESTINATION
                if any(
                    cmd in line
                    for cmd in ("mkdir ", "cp ", "cp -R", "rsync ", "install ")
                ):
                    continue
                offenders.append(f"{path.relative_to(_REPO_ROOT)}:{number}: {stripped}")

    assert not offenders, (
        "published assets read from stripped internal paths:\n" + "\n".join(offenders)
    )
