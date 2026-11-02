"""Markdown rendering of symbol and module docs: on-demand source, language fences, compound sections."""

from __future__ import annotations

from pathlib import Path

import pytest

from akms.repo_wiki.hashing import sha256_text
from akms.repo_wiki.models import ParsedModule, SourceFile, SourceSpan, Symbol
from akms.repo_wiki.paths import read_source
from akms.repo_wiki.render_markdown import (
    render_symbol_section,
    write_module_doc,
    write_symbol_doc,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "multilang_repo"


FIXTURE_REL = "pkg/sample.py"


def _make_source_file(tmp_path: Path, rel_path: str) -> SourceFile:
    abs_path = tmp_path / rel_path
    return SourceFile(
        path=rel_path,
        abs_path=str(abs_path),
        language="python",
        size_bytes=abs_path.stat().st_size,
        content_hash="sha256:fixture",
    )


def _make_symbol(
    rel_path: str, start_line: int, end_line: int, kind: str = "function"
) -> Symbol:
    """Build a minimal Symbol with a real SourceSpan."""
    return Symbol(
        symbol_id="pkg.sample.my_func",
        path=rel_path,
        module="pkg.sample",
        name="my_func",
        qualname="my_func",
        kind=kind,
        parent_id=None,
        start_line=start_line,
        end_line=end_line,
        signature="def my_func(x: int) -> int:",
        docstring="Return x plus one.",
        span=SourceSpan(path=rel_path, start_line=start_line, end_line=end_line),
        calls=[],
    )


def _write_sample_module(tmp_path: Path, rel_path: str, content: str) -> None:
    """Write content to tmp_path/rel_path, creating parent dirs as needed."""
    dest = tmp_path / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")


def test_write_symbol_doc_contains_file_content(tmp_path: Path) -> None:
    """write_symbol_doc includes the actual source text from disk."""
    content = "def my_func(x: int) -> int:\n    return x + 1\n"
    rel = "pkg/sample.py"
    _write_sample_module(tmp_path, rel, content)

    symbol = _make_symbol(rel, start_line=1, end_line=2)
    output_dir = tmp_path / "out"
    doc_path = write_symbol_doc(symbol, output_dir, "abc123", "myrepo", None, tmp_path)

    rendered = doc_path.read_text(encoding="utf-8")
    assert "def my_func(x: int) -> int:" in rendered
    assert "return x + 1" in rendered


def test_write_symbol_doc_source_hash_matches_span_content(tmp_path: Path) -> None:
    """write_symbol_doc frontmatter source_hash equals sha256_text(read_source(span))."""
    content = "def my_func(x: int) -> int:\n    return x + 1\n"
    rel = "pkg/sample.py"
    _write_sample_module(tmp_path, rel, content)

    symbol = _make_symbol(rel, start_line=1, end_line=2)
    output_dir = tmp_path / "out"
    doc_path = write_symbol_doc(symbol, output_dir, "abc123", "myrepo", None, tmp_path)

    span = SourceSpan(path=rel, start_line=1, end_line=2)
    expected_hash = sha256_text(read_source(span, tmp_path))

    rendered = doc_path.read_text(encoding="utf-8")
    assert expected_hash in rendered


def test_write_module_doc_contains_symbol_source(tmp_path: Path) -> None:
    """write_module_doc's code structure section includes source from disk via render_symbol_section."""
    content = "def my_func(x: int) -> int:\n    return x + 1\n"
    rel = "pkg/sample.py"
    _write_sample_module(tmp_path, rel, content)

    symbol = _make_symbol(rel, start_line=1, end_line=2)
    source_file = _make_source_file(tmp_path, rel)
    parsed = ParsedModule(
        source_file=source_file,
        module="pkg.sample",
        docstring="A fixture module.",
        imports=["os"],
        symbols=[symbol],
    )

    output_dir = tmp_path / "out"
    doc_path = write_module_doc(parsed, output_dir, "abc123", "myrepo", tmp_path)

    rendered = doc_path.read_text(encoding="utf-8")
    assert "def my_func(x: int) -> int:" in rendered
    assert "return x + 1" in rendered


def test_render_symbol_section_contains_file_content(tmp_path: Path) -> None:
    """render_symbol_section includes actual file content via read_source."""
    content = "def my_func(x: int) -> int:\n    return x + 1\n"
    rel = "pkg/sample.py"
    _write_sample_module(tmp_path, rel, content)

    symbol = _make_symbol(rel, start_line=1, end_line=2)
    section_lines = render_symbol_section(symbol, "##", tmp_path)
    section_text = "\n".join(section_lines)

    assert "def my_func(x: int) -> int:" in section_text
    assert "return x + 1" in section_text


def test_symbol_doc_and_module_doc_show_same_source(tmp_path: Path) -> None:
    """Module-doc and symbol-doc render the same source text (single span reader)."""
    content = "def my_func(x: int) -> int:\n    return x + 1\n"
    rel = "pkg/sample.py"
    _write_sample_module(tmp_path, rel, content)

    symbol = _make_symbol(rel, start_line=1, end_line=2)
    source_file = _make_source_file(tmp_path, rel)
    parsed = ParsedModule(
        source_file=source_file,
        module="pkg.sample",
        docstring=None,
        imports=[],
        symbols=[symbol],
    )

    output_dir = tmp_path / "out"
    sym_doc = write_symbol_doc(symbol, output_dir, "abc123", "myrepo", None, tmp_path)
    mod_doc = write_module_doc(parsed, output_dir, "abc123", "myrepo", tmp_path)

    sym_rendered = sym_doc.read_text(encoding="utf-8")
    mod_rendered = mod_doc.read_text(encoding="utf-8")

    assert "def my_func(x: int) -> int:" in sym_rendered
    assert "def my_func(x: int) -> int:" in mod_rendered
    assert "return x + 1" in sym_rendered
    assert "return x + 1" in mod_rendered


def test_missing_source_raises_for_write_symbol_doc(tmp_path: Path) -> None:
    """write_symbol_doc raises FileNotFoundError when source is deleted after parse."""
    content = "def my_func(x: int) -> int:\n    return x + 1\n"
    rel = "pkg/sample.py"
    src_file = tmp_path / rel
    _write_sample_module(tmp_path, rel, content)

    symbol = _make_symbol(rel, start_line=1, end_line=2)

    src_file.unlink()
    assert not src_file.exists(), "Source file should be deleted before render"

    output_dir = tmp_path / "out"
    with pytest.raises(FileNotFoundError):
        write_symbol_doc(symbol, output_dir, "abc123", "myrepo", None, tmp_path)


def test_missing_source_raises_for_render_symbol_section(tmp_path: Path) -> None:
    """render_symbol_section raises FileNotFoundError when source is deleted after parse."""
    content = "def my_func(x: int) -> int:\n    return x + 1\n"
    rel = "pkg/sample.py"
    src_file = tmp_path / rel
    _write_sample_module(tmp_path, rel, content)

    symbol = _make_symbol(rel, start_line=1, end_line=2)

    src_file.unlink()

    with pytest.raises(FileNotFoundError):
        render_symbol_section(symbol, "##", tmp_path)


def test_missing_source_raises_for_write_module_doc(tmp_path: Path) -> None:
    """write_module_doc raises FileNotFoundError when source is deleted after parse."""
    content = "def my_func(x: int) -> int:\n    return x + 1\n"
    rel = "pkg/sample.py"
    src_file = tmp_path / rel
    _write_sample_module(tmp_path, rel, content)

    symbol = _make_symbol(rel, start_line=1, end_line=2)
    source_file = _make_source_file(tmp_path, rel)
    parsed = ParsedModule(
        source_file=source_file,
        module="pkg.sample",
        docstring=None,
        imports=[],
        symbols=[symbol],
    )

    src_file.unlink()

    output_dir = tmp_path / "out"
    with pytest.raises(FileNotFoundError):
        write_module_doc(parsed, output_dir, "abc123", "myrepo", tmp_path)


def test_multicompound_cpp_file_is_one_module_doc_with_sections(tmp_path):
    """A C++ file with multiple classes renders as one module doc with a section per class."""
    from akms.repo_wiki.extract.treesitter import CppExtractor
    from akms.repo_wiki.hashing import sha256_file
    from akms.repo_wiki.models import SourceFile

    cpp_path = FIXTURE / "cpp" / "vec.cpp"
    sf = SourceFile(
        "cpp/vec.cpp",
        str(cpp_path),
        "cpp",
        cpp_path.stat().st_size,
        sha256_file(cpp_path),
    )
    parsed = CppExtractor().extract(sf)

    doc = write_module_doc(parsed, tmp_path, "deadbeef", "multilang_repo", FIXTURE)
    assert doc.exists()
    assert list((tmp_path / "modules").glob("*.md")) == [doc]
    body = doc.read_text()
    assert "Vec3" in body and "Vec3::dot" in body  # section per compound
    assert "Sphere" in body


def test_fence_tag_per_language():
    """render_symbol_section fences with the tag keyed off symbol.language."""
    from akms.repo_wiki.extract.treesitter import (
        CppExtractor,
        JuliaExtractor,
        RustExtractor,
    )
    from akms.repo_wiki.extract.python_ast import PythonAstExtractor
    from akms.repo_wiki.hashing import sha256_file
    from akms.repo_wiki.models import SourceFile

    fixtures = {
        "rust": (RustExtractor(), "rust/shapes.rs"),
        "cpp": (CppExtractor(), "cpp/vec.cpp"),
        "julia": (JuliaExtractor(), "julia/geo.jl"),
        "python": (PythonAstExtractor(), "python/calc.py"),
    }
    all_tags = set(fixtures)
    for tag, (extractor, rel) in fixtures.items():
        abs_path = FIXTURE / rel
        sf = SourceFile(
            rel, str(abs_path), tag, abs_path.stat().st_size, sha256_file(abs_path)
        )
        parsed = extractor.extract(sf)
        sym = parsed.symbols[0]
        section = "\n".join(render_symbol_section(sym, "##", FIXTURE))
        assert f"```{tag}" in section, f"{tag}: missing fence in {section!r}"
        for other in all_tags - {tag}:
            assert f"```{other}" not in section


def test_python_tiny_fixture_renders_byte_identically(tmp_path):
    """Python rendering is unchanged — fences and frontmatter language stay 'python'."""
    from akms.repo_wiki.extract.python_ast import PythonAstExtractor
    from akms.repo_wiki.hashing import sha256_file
    from akms.repo_wiki.models import SourceFile

    py_path = FIXTURE / "python" / "calc.py"
    sf = SourceFile(
        "python/calc.py",
        str(py_path),
        "python",
        py_path.stat().st_size,
        sha256_file(py_path),
    )
    parsed = PythonAstExtractor().extract(sf)
    doc = write_module_doc(parsed, tmp_path, "deadbeef", "multilang_repo", FIXTURE)
    body = doc.read_text()
    assert "```python" in body
    assert "```rust" not in body and "```cpp" not in body
    assert "language: python" in body
