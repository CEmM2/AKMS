"""Extractor contracts and registry backend selection, project-backend fallback and dispatch."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

import akms.repo_wiki.manifest as manifest_mod
from akms.repo_wiki.extract.base import Extractor, ProjectExtractor
from akms.repo_wiki.extract.python_ast import PythonAstExtractor
from akms.repo_wiki.extract.registry import (
    DEFAULT_BACKENDS,
    extract_files,
    resolve_backend_name,
)
from akms.repo_wiki.manifest import build_repo
from akms.repo_wiki.models import ParsedModule, SourceFile

FIXTURES = Path(__file__).resolve().parent / "fixtures"
FIXTURE = FIXTURES / "multilang_repo"
_TINY_REPO = FIXTURES / "tiny_repo"


FILES = {
    "python": FIXTURE / "python" / "calc.py",
    "rust": FIXTURE / "rust" / "shapes.rs",
    "cpp": FIXTURE / "cpp" / "vec.cpp",
    "julia": FIXTURE / "julia" / "geo.jl",
}


def _make_repo(tmp_path: Path) -> Path:
    """Mirror the tiny_repo Python tree into ``tmp_path`` with a minimal config."""
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    shutil.copy(_TINY_REPO / "pkg" / "__init__.py", pkg_dir / "__init__.py")
    shutil.copy(_TINY_REPO / "pkg" / "core.py", pkg_dir / "core.py")
    (tmp_path / "repo2md.yaml").write_text(
        "scanner:\n  include: ['pkg']\n  exclude: []\n"
        "generation:\n  output_dir: .repo_wiki/generated\n"
        "summaries:\n  enabled: false\n",
        encoding="utf-8",
    )
    return tmp_path


def _make_python_file(
    tmp_path, name: str = "mod.py", body: str = "def f():\n    return 1\n"
) -> SourceFile:
    """Create a real on-disk Python file and return its SourceFile."""
    abs_path = tmp_path / name
    abs_path.write_text(body, encoding="utf-8")
    return SourceFile(
        path=name,
        abs_path=str(abs_path),
        language="python",
        size_bytes=len(body),
        content_hash="deadbeef",
    )


class _FakeProjectExtractor(ProjectExtractor):
    """A toggleable ProjectExtractor for exercising the project path + fallback."""

    def __init__(self, available: bool) -> None:
        self.available = available
        self.extract_project_calls: list[tuple[str, list[str]]] = []

    def is_available(self) -> bool:
        return self.available

    def extract_project(self, root: str, files: list[str]) -> dict[str, ParsedModule]:
        self.extract_project_calls.append((root, list(files)))
        return {
            rel: ParsedModule(
                source_file=SourceFile(rel, f"{root}/{rel}", "python", 0, "x"),
                module=rel,
                docstring="from-project-backend",
                imports=[],
                symbols=[],
                errors=[],
            )
            for rel in files
        }


def test_registry_selects_configured_backend(tmp_path):
    """The registry honours config.languages.<lang>.backend (defaults python=ast)."""
    config = {"languages": {"python": {"enabled": True, "backend": "ast"}}}
    assert resolve_backend_name("python", config) == "ast"

    source = _make_python_file(tmp_path)
    result = extract_files([source], config)

    assert source.path in result.parsed_modules
    parsed = result.parsed_modules[source.path]
    # The real PythonAstExtractor produced the module (a symbol was extracted).
    assert any(sym.name == "f" for sym in parsed.symbols)
    assert result.notes == []


def test_registry_defaults_when_config_absent(tmp_path):
    """Documented defaults apply (python=ast, cpp/rust/julia=treesitter)."""
    empty_config: dict[str, object] = {}
    assert resolve_backend_name("python", empty_config) == "ast"
    assert resolve_backend_name("cpp", empty_config) == "treesitter"
    assert resolve_backend_name("rust", empty_config) == "treesitter"
    assert resolve_backend_name("julia", empty_config) == "treesitter"
    assert DEFAULT_BACKENDS["python"] == "ast"

    # python still extracts with no languages config present.
    source = _make_python_file(tmp_path)
    result = extract_files([source], empty_config)
    assert source.path in result.parsed_modules


def test_unavailable_project_backend_falls_back_to_per_file(tmp_path, monkeypatch):
    """A ProjectExtractor with is_available()==False triggers per-file fallback."""
    from akms.repo_wiki.extract import registry

    fake = _FakeProjectExtractor(available=False)
    monkeypatch.setitem(registry._BACKENDS, ("python", "fakeproject"), fake)
    config = {"languages": {"python": {"backend": "fakeproject"}}}

    source = _make_python_file(tmp_path)
    result = extract_files([source], config)

    # extract_project must NOT have been called (it was unavailable).
    assert fake.extract_project_calls == []
    # Output still produced, and it came from the per-file PythonAstExtractor.
    assert source.path in result.parsed_modules
    parsed = result.parsed_modules[source.path]
    assert any(sym.name == "f" for sym in parsed.symbols)
    assert parsed.docstring != "from-project-backend"


def test_fallback_records_backend_note(tmp_path, monkeypatch):
    """Every fallback writes a BuildSummary.backend_notes entry."""
    from akms.repo_wiki.extract import registry

    fake = _FakeProjectExtractor(available=False)
    monkeypatch.setitem(registry._BACKENDS, ("python", "fakeproject"), fake)
    config = {"languages": {"python": {"backend": "fakeproject"}}}

    source = _make_python_file(tmp_path)
    result = extract_files([source], config)

    assert len(result.notes) == 1
    note = result.notes[0]
    assert "python" in note
    assert "fakeproject" in note
    assert "fell back" in note
    # Path-neutral: no absolute path / temp dir leakage in the note text.
    assert str(tmp_path) not in note
    assert source.abs_path not in note


def test_handled_languages_reflects_actual_run(tmp_path, monkeypatch):
    """handled_languages exposes the languages actually dispatched."""
    from akms.repo_wiki.extract import registry

    # An available project backend handles the language directly.
    fake = _FakeProjectExtractor(available=True)
    monkeypatch.setitem(registry._BACKENDS, ("python", "fakeproject"), fake)
    config = {"languages": {"python": {"backend": "fakeproject"}}}

    source = _make_python_file(tmp_path)
    result = extract_files([source], config)

    assert result.handled_languages == {"python"}
    assert fake.extract_project_calls  # the project backend actually ran
    assert result.parsed_modules[source.path].docstring == "from-project-backend"


def test_handled_languages_empty_for_unregistered_language(tmp_path):
    """A language with no registered backend and no fallback is not 'handled'."""
    source = SourceFile("a.faux", str(tmp_path / "a.faux"), "fauxlang", 0, "x")
    result = extract_files([source], {})
    assert result.handled_languages == set()
    assert "a.faux" not in result.parsed_modules


def test_unregistered_no_fallback_emits_path_neutral_skip_note(tmp_path):
    """An unregistered backend with no per-file fallback emits exactly one path-neutral skip note."""
    # A synthetic language and backend keep this independent of the backends
    # registered for real languages.
    config = {"languages": {"fauxlang": {"backend": "fauxbackend"}}}
    source = SourceFile("a.faux", str(tmp_path / "a.faux"), "fauxlang", 0, "x")
    result = extract_files([source], config)

    # Unhandled: stays out of handled_languages and parsed_modules.
    assert result.handled_languages == set()
    assert "a.faux" not in result.parsed_modules

    # Exactly one skip note, naming the language, backend, and count.
    assert len(result.notes) == 1
    note = result.notes[0]
    assert "fauxlang" in note
    assert "fauxbackend" in note
    assert "1 file" in note
    # Path-neutral: no temp dir / absolute path / file name leakage.
    assert str(tmp_path) not in note
    assert source.abs_path not in note
    assert "a.faux" not in note


def test_incomplete_extractor_subclass_cannot_instantiate():
    """A subclass that does not implement extract() cannot be instantiated."""

    class IncompleteExtractor(Extractor):
        # Deliberately omits the required extract() method.
        pass

    with pytest.raises(TypeError):
        IncompleteExtractor()  # type: ignore[abstract]


def test_complete_extractor_subclass_instantiates():
    """A subclass implementing extract() instantiates, and PythonAstExtractor is one."""

    class DummyExtractor(Extractor):
        def extract(self, source_file: SourceFile) -> ParsedModule:  # type: ignore[override]
            raise NotImplementedError("dummy — never called in this test")

    instance = DummyExtractor()
    assert isinstance(instance, Extractor)
    assert callable(instance.extract)

    assert issubclass(PythonAstExtractor, Extractor), (
        "PythonAstExtractor must subclass Extractor"
    )
    py_extractor = PythonAstExtractor()
    assert isinstance(py_extractor, Extractor), (
        "PythonAstExtractor instance must pass isinstance(_, Extractor)"
    )


def test_project_extractor_requires_is_available():
    """ProjectExtractor declares is_available() and extract_project() as abstract."""

    class MissingIsAvailable(ProjectExtractor):
        # Implements extract_project but NOT is_available — must raise.
        def extract_project(
            self, root: str, files: list[str]
        ) -> dict[str, ParsedModule]:
            return {}

    with pytest.raises(TypeError):
        MissingIsAvailable()  # type: ignore[abstract]


def test_project_extractor_requires_extract_project():
    """extract_project(root, files) -> dict[relpath, ParsedModule] is part of the contract."""

    class MissingExtractProject(ProjectExtractor):
        # Implements is_available but NOT extract_project — must raise.
        def is_available(self) -> bool:
            return True

    with pytest.raises(TypeError):
        MissingExtractProject()  # type: ignore[abstract]


def test_subclasses_registered_in_registry():
    """The three backends are registered under (lang, 'treesitter')."""
    from akms.repo_wiki.extract import registry
    from akms.repo_wiki.extract.treesitter import (
        CppExtractor,
        JuliaExtractor,
        RustExtractor,
    )

    assert isinstance(registry._BACKENDS[("rust", "treesitter")], RustExtractor)
    assert isinstance(registry._BACKENDS[("cpp", "treesitter")], CppExtractor)
    assert isinstance(registry._BACKENDS[("julia", "treesitter")], JuliaExtractor)


def test_fixture_builds_cleanly_through_registry():
    """Building the fixture through the registry yields per-language symbols."""
    from akms.repo_wiki.extract.registry import extract_files
    from akms.repo_wiki.hashing import sha256_file
    from akms.repo_wiki.models import SourceFile

    config = {"languages": {"rust": True, "cpp": True, "julia": True}}
    sources = [
        SourceFile(
            f"{lang}/{path.name}",
            str(path),
            lang,
            path.stat().st_size,
            sha256_file(path),
        )
        for lang, path in FILES.items()
    ]
    result = extract_files(sources, config)
    langs_with_symbols = {
        pm.source_file.language for pm in result.parsed_modules.values() if pm.symbols
    }
    assert {"python", "rust", "cpp", "julia"} <= langs_with_symbols, (
        f"missing language symbols; got {langs_with_symbols}; notes={result.notes}"
    )


def test_build_repo_dispatches_python_through_registry(tmp_path):
    """build_repo invokes the registry dispatch path for Python, not parse_python_file directly."""
    _make_repo(tmp_path)

    # Spy on the registry entry point used by build_repo, delegating to the
    # real implementation so the build still produces genuine output.
    real_extract = manifest_mod.extract_files
    calls: list[list] = []

    def spy(sources, config):
        calls.append(list(sources))
        return real_extract(sources, config)

    with patch.object(manifest_mod, "extract_files", side_effect=spy) as spied:
        summary = build_repo(tmp_path, no_summaries=True, no_index=True)

    assert spied.called, "build_repo must dispatch Python through extract_files."
    assert summary.parsed > 0
    # The spy received the Python sources (and only routable languages).
    dispatched = calls[0]
    assert dispatched, "extract_files must receive at least one source."
    assert all(s.language == "python" for s in dispatched)
