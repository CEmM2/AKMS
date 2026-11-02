"""Canonical symbol IDs ``<language>:<relpath>::<qualname>`` (forward-slash relpath)."""

from __future__ import annotations

from akms.repo_wiki.models import Language


def build_symbol_id(language: Language, relpath: str, qualname: str) -> str:
    """Build ``<language>:<relpath>::<qualname>``; backslashes in ``relpath`` become ``/``."""
    normalized_relpath = relpath.replace("\\", "/")
    return f"{language.value}:{normalized_relpath}::{qualname}"
