"""Where a repository keeps its local AKMS knowledge."""

from __future__ import annotations

from pathlib import Path

# New projects store lessons, the graph, and generated outputs here.
DEFAULT_KNOWLEDGE_DIRNAME = ".knowledge"
# Checkouts that already use the older directory keep it.
LEGACY_KNOWLEDGE_DIRNAME = "knowledge"


def local_knowledge_dir(repo_root: str | Path) -> Path:
    """Return the local knowledge directory for ``repo_root``.

    The default is ``<repo>/.knowledge``. A repository that already has
    ``<repo>/knowledge`` and does not yet have ``.knowledge`` keeps that
    older directory, so existing checkouts resolve unchanged.
    """
    root = Path(repo_root)
    dotted = root / DEFAULT_KNOWLEDGE_DIRNAME
    legacy = root / LEGACY_KNOWLEDGE_DIRNAME
    if dotted.is_dir():
        return dotted
    if legacy.is_dir():
        return legacy
    return dotted
