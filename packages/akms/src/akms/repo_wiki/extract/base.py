"""Extractor ABCs: per-file ``Extractor`` and whole-project ``ProjectExtractor`` (internal)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from akms.repo_wiki.models import ParsedModule, SourceFile


class Extractor(ABC):
    """Per-file extractor contract: one source file → one ParsedModule."""

    @abstractmethod
    def extract(self, source_file: SourceFile) -> ParsedModule:
        """Parse *source_file* into a ``ParsedModule``; syntax errors fill ``errors``, not raise."""


class ProjectExtractor(ABC):
    """Whole-project extractor; if not ``is_available()`` the registry uses the per-file one."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return ``True`` iff the underlying tool is installed and runnable."""

    @abstractmethod
    def extract_project(
        self,
        root: str,
        files: list[str],
    ) -> dict[str, ParsedModule]:
        """Extract *files* under absolute *root*: relpath -> module; failures carry ``errors``."""
