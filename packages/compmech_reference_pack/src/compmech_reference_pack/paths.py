"""Filesystem accessors for the promoted compmech domain pack.

The domain pack and its source packs ship as package data under
``compmech_reference_pack/domain_pack/``. These helpers return concrete
``Path`` objects so the ``akms_learn`` descriptor loaders — and the
`CEmM2/Logic-Loom <https://github.com/CEmM2/Logic-Loom>`_ status route — can
read them without hardcoding the install layout.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path

__all__ = ["domain_pack_dir", "domain_pack_path", "source_pack_path"]


def domain_pack_dir() -> Path:
    """Absolute path to the packaged ``domain_pack/`` data directory."""
    return Path(str(resources.files("compmech_reference_pack") / "domain_pack"))


def domain_pack_path() -> Path:
    """Absolute path to the promoted ``domain_pack.yaml``."""
    return domain_pack_dir() / "domain_pack.yaml"


def source_pack_path(name: str) -> Path:
    """Absolute path to a source-pack yaml by stem (e.g. ``"mechdsl"``)."""
    return domain_pack_dir() / "source_packs" / f"{name}.yaml"
