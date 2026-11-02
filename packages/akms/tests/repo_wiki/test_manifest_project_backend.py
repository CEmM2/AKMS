"""Project-backend set-hash gating in build_repo."""

from __future__ import annotations

from pathlib import Path

import pytest

from akms.repo_wiki.extract import registry
from akms.repo_wiki.extract.base import ProjectExtractor
from akms.repo_wiki.manifest import (
    LANGUAGES_KEY,
    UNKNOWN_TOOL_VERSION,
    build_repo,
    compute_set_hash,
    get_language_state,
    load_manifest,
    project_backend_needs_rerun,
    save_manifest,
    set_language_state,
    tool_version_or_unknown,
)
from akms.repo_wiki.models import (
    Language,
    Manifest,
    ManifestFile,
    ParsedModule,
    SourceFile,
    SourceSpan,
    Symbol,
)
from akms.repo_wiki.paths import module_name_from_path
from akms.repo_wiki.symbol_ids import build_symbol_id

_CONFIG = """\
scanner:
  max_file_size_kb: 1024
generation:
  output_dir: .repo_wiki/generated
summaries:
  provider: local
  enabled: false
languages:
  python:
    enabled: false
  cpp:
    enabled: true
    backend: fake
"""


class _FakeProjectExtractor(ProjectExtractor):
    """Always-available project backend that records each ``extract_project``."""

    language = Language.CPP

    def __init__(self, version: str) -> None:
        self.version = version
        self.calls: list[list[str]] = []

    def is_available(self) -> bool:
        return True

    def tool_version(self) -> str:
        return self.version

    def extract_project(self, root: str, files: list[str]) -> dict[str, ParsedModule]:
        self.calls.append(list(files))
        modules: dict[str, ParsedModule] = {}
        for rel in files:
            mod_name = module_name_from_path(rel)
            sym = Symbol(
                symbol_id=build_symbol_id(Language.CPP, rel, mod_name),
                path=rel,
                module=mod_name,
                name=mod_name,
                qualname=mod_name,
                kind="module",
                parent_id=None,
                start_line=1,
                end_line=1,
                signature=None,
                docstring=None,
                span=SourceSpan(path=rel, start_line=1, end_line=1),
                language=Language.CPP,
            )
            abs_path = str(Path(root) / rel)
            source = SourceFile(
                path=rel,
                abs_path=abs_path,
                language=Language.CPP.value,
                size_bytes=0,
                content_hash="",
            )
            modules[rel] = ParsedModule(
                source_file=source,
                module=mod_name,
                docstring=None,
                imports=[],
                symbols=[sym],
                errors=[],
            )
        return modules


@pytest.fixture
def fake_cpp_backend(monkeypatch: pytest.MonkeyPatch) -> _FakeProjectExtractor:
    """Register a fake always-available cpp/fake ProjectExtractor for one test."""
    backend = _FakeProjectExtractor("1.0.0")
    backends = dict(registry._BACKENDS)
    backends[("cpp", "fake")] = backend
    monkeypatch.setattr(registry, "_BACKENDS", backends)
    return backend


def _write_repo(tmp_path: Path) -> None:
    (tmp_path / ".repo_wiki").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".repo_wiki" / "config.yaml").write_text(_CONFIG, encoding="utf-8")
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "a.cpp").write_text("int a() { return 1; }\n", encoding="utf-8")
    (tmp_path / "src" / "b.cpp").write_text("int b() { return 2; }\n", encoding="utf-8")


@pytest.mark.unit
def test_project_backend_records_language_state(
    tmp_path: Path, fake_cpp_backend: _FakeProjectExtractor
) -> None:
    """Build 1 records LANGUAGES_KEY['cpp'] with a set_hash + tool_version."""
    _write_repo(tmp_path)
    build_repo(tmp_path, no_index=True, no_summaries=True)

    state = load_manifest(tmp_path).repo.get(LANGUAGES_KEY)
    assert isinstance(state, dict)
    cpp = state.get("cpp")
    assert isinstance(cpp, dict)
    assert cpp["tool_version"] == "1.0.0"
    assert cpp["set_hash"].startswith("sha256:")
    assert fake_cpp_backend.calls  # backend ran on build 1


@pytest.mark.unit
def test_unchanged_inputs_and_version_skip_reextraction(
    tmp_path: Path, fake_cpp_backend: _FakeProjectExtractor
) -> None:
    """Second changed_only build with unchanged inputs + version skips the backend."""
    _write_repo(tmp_path)
    build_repo(tmp_path, no_index=True, no_summaries=True)
    first_calls = len(fake_cpp_backend.calls)
    assert first_calls == 1

    build_repo(tmp_path, changed_only=True, no_index=True, no_summaries=True)
    assert len(fake_cpp_backend.calls) == first_calls  # not re-run


@pytest.mark.unit
def test_tool_version_bump_triggers_reextraction(
    tmp_path: Path, fake_cpp_backend: _FakeProjectExtractor
) -> None:
    """Bumping the fake tool version forces re-extraction even with unchanged inputs."""
    _write_repo(tmp_path)
    build_repo(tmp_path, no_index=True, no_summaries=True)
    assert len(fake_cpp_backend.calls) == 1

    fake_cpp_backend.version = "2.0.0"
    build_repo(tmp_path, changed_only=True, no_index=True, no_summaries=True)
    assert len(fake_cpp_backend.calls) == 2  # re-run on version change

    state = load_manifest(tmp_path).repo.get(LANGUAGES_KEY)
    assert isinstance(state, dict)
    assert state["cpp"]["tool_version"] == "2.0.0"


@pytest.mark.unit
def test_partial_ir_cache_miss_reextracts_full_project_file_set(
    tmp_path: Path, fake_cpp_backend: _FakeProjectExtractor
) -> None:
    """Set-hash stable + one IR-cache miss must re-run extract_project on *all* files."""
    from akms.repo_wiki.ir_cache import cache_path_for

    _write_repo(tmp_path)
    build_repo(tmp_path, no_index=True, no_summaries=True)
    assert len(fake_cpp_backend.calls) == 1
    first_call = list(fake_cpp_backend.calls[0])
    assert set(first_call) == {"src/a.cpp", "src/b.cpp"}

    # Delete only one nested cache entry while set-hash remains stable.
    miss_path = cache_path_for(tmp_path, "src/b.cpp")
    assert miss_path.is_file()
    miss_path.unlink()

    summary = build_repo(tmp_path, changed_only=True, no_index=True, no_summaries=True)
    assert len(fake_cpp_backend.calls) == 2
    second_call = list(fake_cpp_backend.calls[1])
    assert set(second_call) == {"src/a.cpp", "src/b.cpp"}, (
        f"expected full language file set, got {second_call!r}"
    )
    assert any(
        "project backend partial cache miss" in note for note in summary.backend_notes
    )


def test_per_file_python_path_preserves_per_file_hash(tmp_path):
    """The per-file Python backend still keys on the per-file hash."""
    manifest = Manifest(
        {"name": "demo", "last_commit": "abc"},
        {"pkg/mod.py": ManifestFile(language="python", hash="sha256:deadbeef")},
    )
    save_manifest(tmp_path, manifest)
    loaded = load_manifest(tmp_path)

    assert "pkg/mod.py" in loaded.files
    assert loaded.files["pkg/mod.py"].hash == "sha256:deadbeef"
    assert loaded.files["pkg/mod.py"].language == "python"

    previous = loaded.files["pkg/mod.py"]
    assert (previous.hash == "sha256:deadbeef") is True  # unchanged
    assert (previous.hash == "sha256:0ther") is False  # changed -> re-extract

    assert get_language_state(loaded) == {}


def test_project_backend_set_hash_changes_when_input_file_changes():
    """The set hash over input file hashes changes when any input file changes."""
    version = "doxygen 1.9.8"
    base = compute_set_hash(["sha256:a", "sha256:b", "sha256:c"], version)

    reordered = compute_set_hash(["sha256:c", "sha256:a", "sha256:b"], version)
    assert reordered == base

    changed = compute_set_hash(["sha256:a", "sha256:b", "sha256:CHANGED"], version)
    assert changed != base

    stored = {"set_hash": base, "tool_version": version}
    assert (
        project_backend_needs_rerun(
            stored, ["sha256:a", "sha256:b", "sha256:c"], version
        )
        is False
    )
    assert (
        project_backend_needs_rerun(
            stored, ["sha256:a", "sha256:b", "sha256:CHANGED"], version
        )
        is True
    )
    assert project_backend_needs_rerun(None, ["sha256:a"], version) is True


def test_project_backend_rerun_on_tool_version_change(tmp_path):
    """The project backend re-runs when its recorded tool version string changes."""
    files = ["sha256:a", "sha256:b"]
    old_version = "doxygen 1.9.8"
    new_version = "doxygen 1.10.0"

    manifest = Manifest({"name": "demo", "last_commit": "abc"})
    set_language_state(
        manifest,
        "cpp",
        set_hash=compute_set_hash(files, old_version),
        tool_version=old_version,
    )
    save_manifest(tmp_path, manifest)
    loaded = load_manifest(tmp_path)

    stored = get_language_state(loaded)["cpp"]
    assert stored["tool_version"] == old_version

    assert project_backend_needs_rerun(stored, files, old_version) is False
    assert project_backend_needs_rerun(stored, files, new_version) is True


def test_tool_version_unknown_fallback_is_deterministic():
    """Tool-version retrieval failure yields a deterministic 'unknown' string."""
    assert UNKNOWN_TOOL_VERSION == "unknown"
    assert tool_version_or_unknown(None) == UNKNOWN_TOOL_VERSION
    assert tool_version_or_unknown(None) == UNKNOWN_TOOL_VERSION
    assert tool_version_or_unknown("") == UNKNOWN_TOOL_VERSION
    assert tool_version_or_unknown("   ") == UNKNOWN_TOOL_VERSION
    assert tool_version_or_unknown("  doxygen 1.9.8  ") == "doxygen 1.9.8"

    h1 = compute_set_hash(["sha256:a"], tool_version_or_unknown(None))
    h2 = compute_set_hash(["sha256:a"], UNKNOWN_TOOL_VERSION)
    assert h1 == h2
