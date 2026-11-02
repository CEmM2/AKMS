import json
import subprocess
from pathlib import Path

import pytest

from akms.repo_wiki.cli import main
from akms.repo_wiki.config import default_config, init_repo_wiki
from akms.repo_wiki.extract.python_ast import parse_python_file
from akms.repo_wiki.manifest import build_repo
from akms.repo_wiki.models import Language, SourceFile, SourceSpan, Symbol
from akms.repo_wiki.summarize import (
    DisabledSummaryProvider,
    LocalSummaryProvider,
    RemoteSummaryProvider,
    generate_summaries,
    local_symbol_summary,
    provider_from_config,
)
from .test_build_render_graph_summary import copy_fixture

FIXTURES = Path(__file__).resolve().parent / "fixtures"

TINY_REPO = Path(__file__).parent / "fixtures" / "tiny_repo"


def _parse_tiny_core():
    path = TINY_REPO / "pkg" / "core.py"
    return parse_python_file(
        SourceFile(
            "pkg/core.py", str(path), "python", path.stat().st_size, "sha256:core"
        )
    )


def _symbol_of(language: Language, kind: str, qualname: str) -> Symbol:
    return Symbol(
        symbol_id=f"{language.value}:x::{qualname}",
        path="x",
        module="x",
        name=qualname.split("::")[-1].split(".")[-1],
        qualname=qualname,
        kind=kind,  # type: ignore[arg-type]
        parent_id=None,
        start_line=1,
        end_line=2,
        signature=None,
        docstring=None,
        span=SourceSpan(path="x", start_line=1, end_line=2),
        language=language,
    )


def make_symbol() -> Symbol:
    return Symbol(
        symbol_id="pkg.core.helper",
        path="pkg/core.py",
        module="pkg.core",
        name="helper",
        qualname="helper",
        kind="function",
        parent_id=None,
        start_line=17,
        end_line=18,
        signature="def helper(name: str) -> str",
        docstring="Return a greeting.",
        calls=["str.upper"],
        span=SourceSpan(path="pkg/core.py", start_line=17, end_line=18),
    )


def test_summary_providers_default_to_local_and_can_be_disabled():
    config = default_config(Path("repo"))
    assert isinstance(provider_from_config(config), LocalSummaryProvider)
    config["summaries"]["enabled"] = False
    provider = provider_from_config(config)
    assert isinstance(provider, DisabledSummaryProvider)
    assert provider.summarize_symbol(make_symbol()) is None


def test_remote_provider_blocks_source_upload_without_explicit_permission():
    provider = RemoteSummaryProvider("openai", allow_source_code_upload=False)
    with pytest.raises(ValueError):
        provider.summarize_symbol(make_symbol())


def test_generate_summaries_writes_a_summary_and_symbol_doc_per_symbol(tmp_path: Path):
    """Every summarised symbol gets a summary file and a symbol doc under the output directory."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "core.py").write_text(
        (TINY_REPO / "pkg" / "core.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    config = default_config(tmp_path)

    count = generate_summaries([_parse_tiny_core()], tmp_path, config)

    assert count > 0
    out_dir = tmp_path / ".repo_wiki" / "generated"
    assert len(list((out_dir / "summaries").glob("*.summary.md"))) == count
    assert len(list((out_dir / "symbols").glob("*.md"))) == count


def test_generate_summaries_fails_clearly_when_source_is_missing(tmp_path: Path):
    """A span whose file is gone raises FileNotFoundError naming it, rather than summarising nothing."""
    (tmp_path / "pkg").mkdir()
    with pytest.raises(FileNotFoundError, match="Source file not found.*core.py"):
        generate_summaries([_parse_tiny_core()], tmp_path, default_config(tmp_path))


def test_local_symbol_summary_names_symbol_path_and_lines():
    """The local summary mentions the qualname, file path and start line."""
    symbol = make_symbol()
    summary = local_symbol_summary(symbol)
    assert symbol.qualname in summary
    assert symbol.path in summary
    assert str(symbol.start_line) in summary


def test_local_summary_uses_struct_wording_for_rust_types():
    """A Rust class-kind symbol is described as a struct."""
    summary = local_symbol_summary(_symbol_of(Language.RUST, "class", "Circle"))
    assert "defines a struct" in summary
    assert "defines a class" not in summary


def test_local_summary_uses_class_wording_for_cpp_types():
    """A C++ class-kind symbol is described as a class."""
    assert "defines a class" in local_symbol_summary(
        _symbol_of(Language.CPP, "class", "Vec3")
    )


def test_local_summary_wording_for_python_kinds():
    """Python symbols keep the original wording per kind."""
    expected = {
        ("class", "Foo"): "defines a class",
        ("function", "helper"): "defines a function",
        ("method", "Foo.run"): "defines a method",
        ("constant", "CONST"): "defines a top-level constant",
    }
    for (kind, qualname), phrase in expected.items():
        assert phrase in local_symbol_summary(
            _symbol_of(Language.PYTHON, kind, qualname)
        )


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _commit(repo: Path, message: str) -> None:
    _git(repo, "add", "pkg")
    _git(repo, "commit", "-m", message)


def _two_file_repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "repo2md-tests@example.invalid")
    _git(tmp_path, "config", "user.name", "repo2md tests")
    init_repo_wiki(tmp_path)
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "app.py").write_text(
        'def main():\n    """Application entry point."""\n    return 1\n',
        encoding="utf-8",
    )
    (package / "lib.py").write_text(
        'def helper():\n    """Helper."""\n    return 2\n',
        encoding="utf-8",
    )
    _commit(tmp_path, "initial")
    return tmp_path


def _symbol_doc(repo: Path, module: str, symbol: str) -> Path:
    return (
        repo
        / ".repo_wiki"
        / "generated"
        / "symbols"
        / f"python_pkg.{module}.py__{symbol}.md"
    )


def _summary_section(path: Path) -> bytes:
    marker = b"## Generated Summary\n"
    tail = path.read_bytes().split(marker, 1)[1]
    return tail.split(b"\n## Calls\n", 1)[0]


def test_commit_advancing_incremental_retains_cached_summaries(
    tmp_path: Path, monkeypatch
) -> None:
    repo = _two_file_repo(tmp_path)
    calls: list[str] = []
    original = LocalSummaryProvider.summarize_symbol

    def counted(self: LocalSummaryProvider, symbol):
        calls.append(symbol.symbol_id)
        return original(self, symbol)

    monkeypatch.setattr(LocalSummaryProvider, "summarize_symbol", counted)

    full = build_repo(repo, no_index=True)
    assert full.generated_summaries == 2
    assert len(calls) == 2
    lib_doc = _symbol_doc(repo, "lib", "helper")
    expected_lib_summary = _summary_section(lib_doc)
    assert b"`helper` defines a function" in expected_lib_summary

    (repo / "pkg" / "app.py").write_text(
        'def main():\n    """Application entry point."""\n    return 3\n',
        encoding="utf-8",
    )
    _commit(repo, "change app")
    incremental = build_repo(repo, changed_only=True, no_index=True)
    assert incremental.generated_summaries == 1
    assert len(calls) == 3
    assert _summary_section(lib_doc) == expected_lib_summary

    repeated = build_repo(repo, changed_only=True, no_index=True)
    assert repeated.generated_summaries == 0
    assert len(calls) == 3
    assert _summary_section(lib_doc) == expected_lib_summary

    lib_doc.write_bytes(
        lib_doc.read_bytes().replace(
            expected_lib_summary, b"_Summary not generated yet._"
        )
    )
    restored = build_repo(repo, force=True, no_index=True)
    assert restored.generated_summaries == 0
    assert len(calls) == 3
    assert _summary_section(lib_doc) == expected_lib_summary


def test_no_summaries_incremental_preserves_unchanged_cached_summary(
    tmp_path: Path, monkeypatch
) -> None:
    repo = _two_file_repo(tmp_path)
    calls: list[str] = []
    original = LocalSummaryProvider.summarize_symbol

    def counted(self: LocalSummaryProvider, symbol):
        calls.append(symbol.symbol_id)
        return original(self, symbol)

    monkeypatch.setattr(LocalSummaryProvider, "summarize_symbol", counted)

    full = build_repo(repo, no_index=True)
    assert full.generated_summaries == 2
    lib_doc = _symbol_doc(repo, "lib", "helper")
    expected_lib_summary = _summary_section(lib_doc)

    (repo / "pkg" / "app.py").write_text(
        'def main():\n    """Application entry point."""\n    return 4\n',
        encoding="utf-8",
    )
    _commit(repo, "change app without summaries")
    incremental = build_repo(repo, changed_only=True, no_index=True, no_summaries=True)
    assert incremental.generated_summaries == 0
    assert len(calls) == 2
    assert _summary_section(lib_doc) == expected_lib_summary


def test_summarize_reuses_cache_and_supports_symbol_filter(tmp_path: Path):
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "summarize", "--force"]) == 0
    cache_path = tmp_path / ".repo_wiki" / "cache" / "llm_summaries.json"
    first_cache = json.loads(cache_path.read_text())
    assert "python:pkg/core.py::Greeter.greet" in first_cache
    assert main(["--repo-root", str(tmp_path), "summarize", "--changed-only"]) == 0
    assert json.loads(cache_path.read_text()) == first_cache
    assert (
        main(
            [
                "--repo-root",
                str(tmp_path),
                "summarize",
                "--force",
                "--symbol",
                "python:pkg/core.py::helper",
            ]
        )
        == 0
    )
    assert (
        tmp_path
        / ".repo_wiki"
        / "generated"
        / "summaries"
        / "python_pkg.core.py__helper.summary.md"
    ).exists()
