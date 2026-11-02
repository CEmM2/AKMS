"""Single dispatch point for extraction; returns parsed modules plus path-neutral backend notes."""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from akms.repo_wiki.extract.base import Extractor, ProjectExtractor
from akms.repo_wiki.extract.python_ast import PythonAstExtractor

if TYPE_CHECKING:
    from akms.repo_wiki.models import ParsedModule, SourceFile

DEFAULT_BACKENDS: dict[str, str] = {
    "python": "ast",
    "cpp": "treesitter",
    "rust": "treesitter",
    "julia": "treesitter",
}

_BACKENDS: dict[tuple[str, str], Extractor | ProjectExtractor] = {
    ("python", "ast"): PythonAstExtractor(),
}

_PER_FILE_FALLBACKS: dict[str, Extractor] = {
    "python": PythonAstExtractor(),
}


def _register_doxygen_backend() -> None:
    """Register Doxygen lazily (``cpp_doxygen`` imports ``manifest``, which imports us)."""

    from akms.repo_wiki.extract.cpp_doxygen import DoxygenCppExtractor

    _BACKENDS[("cpp", "doxygen")] = DoxygenCppExtractor()


def _register_treesitter_backends() -> None:
    """Register optional tree-sitter backends whose grammar wheels import cleanly."""

    from importlib import import_module

    for language, cls_name in (
        ("rust", "RustExtractor"),
        ("cpp", "CppExtractor"),
        ("julia", "JuliaExtractor"),
    ):
        try:
            module = import_module("akms.repo_wiki.extract.treesitter")
            backend = getattr(module, cls_name)()
            _BACKENDS[(language, "treesitter")] = backend
            # Also the fallback for `cpp.backend: doxygen`; empty slot if the grammar import fails.
            if language == "cpp":
                _PER_FILE_FALLBACKS["cpp"] = backend
        except (ImportError, ValueError, TypeError, OSError, RuntimeError):
            # Missing wheel or ABI mismatch: leave the slot empty (other errors must surface).
            continue


_register_doxygen_backend()
_register_treesitter_backends()


@dataclass(slots=True)
class ExtractionResult:
    """Registry run result: parsed modules, path-neutral ``notes``, and ``handled_languages``."""

    parsed_modules: dict[str, "ParsedModule"] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    handled_languages: set[str] = field(default_factory=set)


def resolve_backend_name(language: str, config: dict[str, object]) -> str | None:
    """Return the configured backend name for *language*, else the default (or ``None``)."""

    languages = config.get("languages")
    lang_cfg: dict[str, object] = {}
    if isinstance(languages, dict):
        entry = languages.get(language)
        if isinstance(entry, dict):
            lang_cfg = entry
    configured = lang_cfg.get("backend")
    if isinstance(configured, str):
        return configured
    return DEFAULT_BACKENDS.get(language)


def get_backend(
    language: str, config: dict[str, object]
) -> Extractor | ProjectExtractor | None:
    """Return the registered backend instance for *language* given *config*."""

    name = resolve_backend_name(language, config)
    if name is None:
        return None
    return _BACKENDS.get((language, name))


def extract_files(
    sources: list["SourceFile"], config: dict[str, object]
) -> ExtractionResult:
    """Dispatch *sources* by language; unavailable project backends fall back with a note."""

    result = ExtractionResult()

    by_language: dict[str, list[SourceFile]] = {}
    for source in sources:
        by_language.setdefault(source.language, []).append(source)

    for language, files in by_language.items():
        backend_name = resolve_backend_name(language, config)
        backend = _BACKENDS.get((language, backend_name)) if backend_name else None

        if isinstance(backend, ProjectExtractor):
            if backend.is_available():
                result.handled_languages.add(language)
                _run_project_backend(backend, files, result)
                continue
            result.notes.append(
                f"{language}: project backend '{backend_name}' unavailable, "
                "fell back to per-file extractor"
            )
            _run_per_file_fallback(language, files, result)
            continue

        if isinstance(backend, Extractor):
            result.handled_languages.add(language)
            for source in files:
                result.parsed_modules[source.path] = backend.extract(source)
            continue

        if language in _PER_FILE_FALLBACKS:
            result.notes.append(
                f"{language}: backend '{backend_name}' not registered, "
                "fell back to per-file extractor"
            )
            _run_per_file_fallback(language, files, result)
        else:
            # No backend and no fallback: record a note rather than silently dropping files.
            result.notes.append(
                f"{language}: backend '{backend_name}' not registered and no "
                f"per-file fallback available; skipped {len(files)} file(s)"
            )

    return result


def _run_project_backend(
    backend: ProjectExtractor,
    files: list["SourceFile"],
    result: ExtractionResult,
) -> None:
    """Invoke a project backend once over *files* and merge its output."""

    if not files:
        return
    root = _common_root(files)
    relpaths = [source.path for source in files]
    produced = backend.extract_project(root, relpaths)
    result.parsed_modules.update(produced)


def _run_per_file_fallback(
    language: str,
    files: list["SourceFile"],
    result: ExtractionResult,
) -> None:
    """Run the per-file fallback ``Extractor`` for *language* over *files*."""

    fallback = _PER_FILE_FALLBACKS.get(language)
    if fallback is None:
        return
    result.handled_languages.add(language)
    for source in files:
        result.parsed_modules[source.path] = fallback.extract(source)


def _common_root(files: list["SourceFile"]) -> str:
    """Best-effort repository root: ``abs_path`` with the relative ``path`` suffix stripped."""

    first = files[0]
    root = Path(first.abs_path)
    for _ in Path(first.path).parts:
        root = root.parent
    return str(root)
