"""Generated doc filenames are filesystem-safe, collision-free and stable across rebuilds."""

from __future__ import annotations

import json
from pathlib import Path

from akms.repo_wiki.models import ParsedModule, SourceFile, SourceSpan, Symbol
from akms.repo_wiki.paths import safe_doc_name
from akms.repo_wiki.render_markdown import write_module_doc, write_symbol_doc
from akms.repo_wiki.summarize import write_summary_doc

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _write_src(tmp_path: Path, rel: str, content: str) -> None:
    dest = tmp_path / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")


def _make_symbol(
    symbol_id: str, rel_path: str, start_line: int = 1, end_line: int = 2
) -> Symbol:
    """Build a minimal Symbol with a new-style ID (`python:<relpath>::<qualname>`)."""
    qualname = symbol_id.split("::", 1)[1] if "::" in symbol_id else symbol_id
    name = qualname.split(".")[-1]
    return Symbol(
        symbol_id=symbol_id,
        path=rel_path,
        module=rel_path.replace("/", ".").rsplit(".py", 1)[0],
        name=name,
        qualname=qualname,
        kind="function",
        parent_id=None,
        start_line=start_line,
        end_line=end_line,
        signature=f"def {name}(x):",
        docstring="A fixture function.",
        calls=[],
        span=SourceSpan(path=rel_path, start_line=start_line, end_line=end_line),
    )


def _make_parsed_module(
    symbol: Symbol, module: str, rel_path: str, content_hash: str = "sha256:fixture"
) -> ParsedModule:
    sf = SourceFile(
        path=rel_path,
        abs_path=rel_path,
        language="python",
        size_bytes=0,
        content_hash=content_hash,
    )
    return ParsedModule(
        source_file=sf,
        module=module,
        docstring=None,
        imports=[],
        symbols=[symbol],
    )


def test_render_markdown_symbol_filenames_safe(tmp_path):
    """render_markdown generates filenames via safe_doc_name for symbol IDs."""
    sym_id = "python:src/pkg/core.py::MyClass.method"
    rel = "src/pkg/core.py"
    content = "def method(self):\n    pass\n"
    _write_src(tmp_path, rel, content)

    symbol = _make_symbol(sym_id, rel, start_line=1, end_line=2)
    output_dir = tmp_path / "out"

    doc_path = write_symbol_doc(symbol, output_dir, "abc123", "myrepo", None, tmp_path)

    fname = doc_path.name
    assert "::" not in fname, f"Raw '::' in filename: {fname!r}"
    assert "/" not in fname, f"Raw '/' in filename: {fname!r}"

    expected_name = safe_doc_name(sym_id) + ".md"
    assert fname == expected_name, f"Expected filename {expected_name!r}, got {fname!r}"


def test_render_markdown_module_filenames_safe(tmp_path):
    """render_markdown generates safe module filenames."""
    rel = "src/pkg/utils.py"
    content = "def helper(x):\n    return x\n"
    _write_src(tmp_path, rel, content)

    sym_id = "python:src/pkg/utils.py::helper"
    symbol = _make_symbol(sym_id, rel, start_line=1, end_line=2)
    module = "src.pkg.utils"
    parsed = _make_parsed_module(symbol, module, rel)
    output_dir = tmp_path / "out"

    doc_path = write_module_doc(parsed, output_dir, "abc123", "myrepo", tmp_path)

    fname = doc_path.name
    assert "::" not in fname, f"Raw '::' in module filename: {fname!r}"
    assert "/" not in fname, f"Raw '/' in module filename: {fname!r}"

    expected_name = safe_doc_name(module) + ".md"
    assert fname == expected_name, (
        f"Expected module filename {expected_name!r}, got {fname!r}"
    )


def test_summarize_symbol_filenames_safe(tmp_path):
    """Summarize generates filenames via safe_doc_name for symbol IDs."""
    sym_id = "python:deep/nested/module.py::OuterClass.inner_method"
    rel = "deep/nested/module.py"
    content = "def inner_method(self):\n    pass\n"
    _write_src(tmp_path, rel, content)

    symbol = _make_symbol(sym_id, rel, start_line=1, end_line=2)
    output_dir = tmp_path / "out"
    source_hash = "sha256:" + "a" * 64

    summary_path = write_summary_doc(
        symbol, "A generated summary.", output_dir, source_hash
    )

    fname = summary_path.name
    assert "::" not in fname, f"Raw '::' in summary filename: {fname!r}"
    assert "/" not in fname, f"Raw '/' in summary filename: {fname!r}"

    expected_stem = safe_doc_name(sym_id)
    assert fname == f"{expected_stem}.summary.md", (
        f"Expected summary filename {expected_stem}.summary.md, got {fname!r}"
    )


def test_filename_collision_resistance_relpath_vs_qualname(tmp_path):
    """safe_doc_name resists collisions for IDs differing only by relpath."""
    id_a = "python:a/m.py::F"
    id_b = "python:b/m.py::F"

    fname_a = safe_doc_name(id_a) + ".md"
    fname_b = safe_doc_name(id_b) + ".md"

    assert fname_a != fname_b, (
        f"Collision: both {id_a!r} and {id_b!r} map to the same filename {fname_a!r}"
    )

    for fname in (fname_a, fname_b):
        assert "::" not in fname, f"Raw '::' in filename: {fname!r}"
        assert "/" not in fname, f"Raw '/' in filename: {fname!r}"

    assert fname_a == "python_a.m.py__F.md", (
        f"Unexpected mapping for {id_a!r}: {fname_a!r}"
    )
    assert fname_b == "python_b.m.py__F.md", (
        f"Unexpected mapping for {id_b!r}: {fname_b!r}"
    )


def test_rebuild_stability_render_symbols(tmp_path):
    """Multiple render passes produce identical symbol filenames."""
    sym_id = "python:pkg/core.py::Greeter.greet"
    rel = "pkg/core.py"
    content = "def greet(self):\n    return 'hi'\n"
    _write_src(tmp_path, rel, content)

    symbol = _make_symbol(sym_id, rel, start_line=1, end_line=2)
    output_dir = tmp_path / "out"

    path1 = write_symbol_doc(symbol, output_dir, "abc123", "myrepo", None, tmp_path)
    path2 = write_symbol_doc(symbol, output_dir, "abc123", "myrepo", None, tmp_path)

    assert path1 == path2, f"First render produced {path1!r}, second produced {path2!r}"
    assert path1.read_bytes() == path2.read_bytes(), (
        "Same render inputs produced different file content across two passes"
    )


def test_rebuild_stability_summarize(tmp_path):
    """Multiple summarize passes produce identical summary filenames."""
    sym_id = "python:pkg/core.py::Greeter.greet"
    rel = "pkg/core.py"
    symbol = _make_symbol(sym_id, rel, start_line=1, end_line=2)
    output_dir = tmp_path / "out"
    source_hash = "sha256:" + "b" * 64
    summary_text = "This function greets the user."

    path1 = write_summary_doc(symbol, summary_text, output_dir, source_hash)
    path2 = write_summary_doc(symbol, summary_text, output_dir, source_hash)

    assert path1 == path2, (
        f"First summarize produced {path1!r}, second produced {path2!r}"
    )
    assert path1.read_bytes() == path2.read_bytes(), (
        "Same summarize inputs produced different file content across two passes"
    )


def test_manifest_build_doc_paths_safe(tmp_path):
    """manifest.py build_repo writes safe `doc` paths (no raw `::` or `/`)."""
    from akms.repo_wiki.cli import main

    fixture_src = FIXTURES / "tiny_repo"
    for src_file in fixture_src.rglob("*"):
        rel = src_file.relative_to(fixture_src)
        dest = tmp_path / rel
        if src_file.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src_file.read_bytes())

    assert main(["--repo-root", str(tmp_path), "build", "--no-index"]) == 0

    manifest_path = tmp_path / ".repo_wiki" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    for relpath, file_entry in manifest["files"].items():
        for sym_id, sym_entry in file_entry.get("symbols", {}).items():
            doc = sym_entry.get("doc", "")
            doc_basename = doc.split("/")[-1] if "/" in doc else doc
            assert "::" not in doc_basename, (
                f"Raw '::' in manifest doc basename for {sym_id!r}: {doc!r}"
            )
            # The doc path itself may contain '/' as a directory separator,
            # but the filename component (after removing the output_dir prefix)
            # must not contain '/' — it should be a single filename segment.
            # Check the last component only.
            assert doc_basename == safe_doc_name(sym_id) + ".md", (
                f"manifest doc for {sym_id!r}: basename={doc_basename!r}, "
                f"expected {safe_doc_name(sym_id) + '.md'!r}"
            )
