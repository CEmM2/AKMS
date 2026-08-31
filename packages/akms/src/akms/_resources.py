"""akms._resources — shared helper for locating bundled AKMS resources.

Addresses PR#18 review comment C4 (and PR#20 C5/C6): every call site was
re-deriving the path to ``seed/qmd/run_qmd.sh`` via hand-rolled
``Path(__file__).parents[N]`` indices, with at least one site using the
wrong index and every site fragile to the installed-vs-editable layout.

This module centralizes the lookup. Callers do::

    from akms._resources import seed_qmd_path
    wrapper = seed_qmd_path("run_qmd.sh")

``seed_qmd_path`` returns the first path that exists, trying:

  1. ``importlib.resources`` under ``akms._bundled.qmd``. The seed tree is
     MIRRORED into ``src/akms/_bundled/`` and declared as package data, so
     this branch resolves in BOTH the installed-wheel and editable-dev
     layouts. This is the normal path.
  2. ``<package-root>/seed/qmd/<name>`` via ``Path(__file__).parents[2]``
     where package-root is ``Packages/AKMS`` — the canonical source tree that
     the mirror is generated from (see ``scripts/sync_bundled.sh``). Retained
     so a checkout whose mirror is stale, or a vendored tree, still resolves.
  3. Explicit ``repo_root`` candidates provided by the caller — useful
     when the MCP server was spawned with a repo_root that already
     points inside ``Packages/AKMS``.

If nothing resolves, returns the package-root fallback path anyway so
the caller can surface a clear "file not found" error rather than a
``TypeError`` on ``None``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


def _package_root() -> Path:
    """Resolve Packages/AKMS/ from this module's location.

    ``akms/_resources.py`` is at ``Packages/AKMS/src/akms/_resources.py``
    so ``parents[2]`` is ``Packages/AKMS/`` (the package root that
    contains both ``src/`` and ``seed/``).
    """
    return Path(__file__).resolve().parents[2]


def _importlib_bundled(name: str, subdir: str) -> Path | None:
    """Try to resolve a bundled file via importlib.resources.

    Resolves against the ``akms`` package anchor, so ``_bundled`` need not
    be an importable package — it only has to be present as package data.
    Returns None if the file is absent, which means the mirror is missing or
    stale; the caller then falls back to the canonical tree.
    """
    try:
        from importlib.resources import files  # type: ignore[attr-defined]
    except ImportError:
        return None
    try:
        anchor = files("akms").joinpath("_bundled", subdir, name)
    except (ModuleNotFoundError, FileNotFoundError):
        return None
    # ``files(...)`` returns a ``Traversable``; only materialize if it
    # points at a real on-disk file.
    try:
        as_path = Path(str(anchor))
    except TypeError:
        return None
    return as_path if as_path.exists() else None


def seed_qmd_path(
    name: str,
    repo_root_candidates: Iterable[Path] | None = None,
) -> Path:
    """Return the absolute path to ``seed/qmd/<name>``.

    Precedence:
      1. ``importlib.resources`` (installed-wheel future layout).
      2. Caller-supplied ``repo_root_candidates`` — paths to check for
         ``<candidate>/seed/qmd/<name>``.
      3. Package-root fallback: ``<Packages/AKMS>/seed/qmd/<name>``.

    The returned path is **not** guaranteed to exist; call ``.exists()``
    before shelling out. This keeps the helper side-effect-free and
    lets callers emit context-specific error messages.
    """
    bundled = _importlib_bundled(name, "qmd")
    if bundled is not None:
        return bundled

    if repo_root_candidates:
        for base in repo_root_candidates:
            candidate = Path(base) / "seed" / "qmd" / name
            if candidate.exists():
                return candidate

    return _package_root() / "seed" / "qmd" / name


def bundled_path(*parts: str) -> Path:
    """Return the absolute path to a file under ``akms/_bundled/``.

    Same precedence as :func:`seed_qmd_path`: the packaged location first,
    then the pre-relocation ``Packages/AKMS/seed/`` layout.

    The returned path is **not** guaranteed to exist — check ``.exists()``
    so callers can emit their own error message.
    """
    if not parts:
        raise ValueError("bundled_path() requires at least one path segment")
    *subdirs, name = parts
    if subdirs:
        bundled = _importlib_bundled(name, str(Path(*subdirs)))
        if bundled is not None:
            return bundled
    else:
        try:
            from importlib.resources import files  # type: ignore[attr-defined]

            candidate = Path(str(files("akms").joinpath("_bundled", name)))
            if candidate.exists():
                return candidate
        except (ImportError, ModuleNotFoundError, FileNotFoundError, TypeError):
            pass
    legacy = _package_root() / "seed" / Path(*parts)
    if legacy.exists():
        return legacy
    return _package_root() / "src" / "akms" / "_bundled" / Path(*parts)


def bundled_skills_path(name: str | None = None) -> Path:
    """Return the path to the bundled agent skills shipped with the package.

    ``bundled_skills_path()`` gives the skills root; ``bundled_skills_path("akms")``
    gives one skill directory. Consumers copy these into their agent's skills
    directory::

        from akms._resources import bundled_skills_path
        shutil.copytree(bundled_skills_path("akms"), ".claude/skills/akms")

    The repo-root ``skills/`` tree is the canonical copy; this one is mirrored
    into the package so ``pip install akms`` delivers it. A test asserts the
    two stay identical.
    """
    try:
        from importlib.resources import files  # type: ignore[attr-defined]

        anchor = files("akms").joinpath("_bundled", "skills")
        if name:
            anchor = anchor.joinpath(name)
        candidate = Path(str(anchor))
        if candidate.exists():
            return candidate
    except (ImportError, ModuleNotFoundError, FileNotFoundError, TypeError):
        pass
    base = _package_root() / "src" / "akms" / "_bundled" / "skills"
    return base / name if name else base
