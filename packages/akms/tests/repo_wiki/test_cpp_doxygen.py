"""C++ via Doxygen: reference resolution, visibility, version tracking and fallback.

Tests that need the ``doxygen`` binary skip when it is absent; the reference
resolution tests drive the pure helpers and run everywhere.
"""

from __future__ import annotations

import shutil
import unittest.mock as mock
from pathlib import Path

import pytest

from akms.repo_wiki.extract.cpp_doxygen import (
    _resolve_references,
    _strip_namespace_prefix,
)
from akms.repo_wiki.graph import build_symbol_graph
from akms.repo_wiki.manifest import UNKNOWN_TOOL_VERSION, tool_version_or_unknown
from akms.repo_wiki.models import (
    Language,
    ParsedModule,
    SourceFile,
    SourceSpan,
    Symbol,
    SymbolKind,
)


def _sym(symbol_id: str, name: str, qualname: str, kind: SymbolKind) -> Symbol:
    return Symbol(
        symbol_id=symbol_id,
        path="cpp/vec.cpp",
        module="vec",
        name=name,
        qualname=qualname,
        kind=kind,
        parent_id=None,
        start_line=1,
        end_line=1,
        signature=None,
        docstring=None,
        span=SourceSpan(path="cpp/vec.cpp", start_line=1, end_line=1),
        language=Language.CPP,
    )


def test_resolve_references_keeps_method_drops_field() -> None:
    """Dst kind method is kept; dst kind constant (data member) is dropped."""
    length = _sym("length_id", "length", "length", "function")
    dot = _sym("dot_id", "dot", "Vec3::dot", "method")
    x = _sym("x_id", "x", "Vec3::x", "constant")
    by_refid = {"length_ref": length, "dot_ref": dot, "x_ref": x}
    pending = [("length_ref", "dot_ref"), ("length_ref", "x_ref")]

    _resolve_references(by_refid, pending)

    assert length.calls == ["Vec3::dot"]
    # Field-access target produced no call entry.
    assert "Vec3::x" not in length.calls
    assert "x" not in length.calls


def test_resolve_references_dedupes_and_sorts() -> None:
    """Repeated/unordered references collapse to a sorted, deduped calls list."""
    caller = _sym("caller_id", "caller", "caller", "function")
    dot = _sym("dot_id", "dot", "Vec3::dot", "method")
    add = _sym("add_id", "add", "Vec3::add", "method")
    by_refid = {"caller_ref": caller, "dot_ref": dot, "add_ref": add}
    pending = [
        ("caller_ref", "dot_ref"),
        ("caller_ref", "add_ref"),
        ("caller_ref", "dot_ref"),  # duplicate
    ]

    _resolve_references(by_refid, pending)

    assert caller.calls == ["Vec3::add", "Vec3::dot"]


def test_calls_resolve_confident_in_graph() -> None:
    """A calls=[Vec3::dot] symbol yields a CONFIDENT edge with dst_id; none to x."""
    length = _sym("length_id", "length", "length", "function")
    length.calls = ["Vec3::dot"]
    dot = _sym("dot_id", "dot", "Vec3::dot", "method")
    x = _sym("x_id", "x", "Vec3::x", "constant")
    source_file = SourceFile(
        path="cpp/vec.cpp",
        abs_path="/abs/cpp/vec.cpp",
        language=Language.CPP.value,
        size_bytes=0,
        content_hash="",
    )
    pm = ParsedModule(
        source_file=source_file,
        module="vec",
        docstring=None,
        imports=[],
        symbols=[length, dot, x],
    )

    graph = build_symbol_graph([pm])
    call_edges = [e for e in graph["edges"] if e.get("type") == "calls"]

    assert len(call_edges) == 1
    edge = call_edges[0]
    assert edge["resolution"] == "CONFIDENT"
    assert edge["dst_id"] == "dot_id"
    assert edge["dst_name"] == "Vec3::dot"
    # No edge ever targets the data member x.
    assert all(e.get("dst_name") != "Vec3::x" for e in call_edges)


def test_strip_namespace_prefix_keeps_class_nesting() -> None:
    """Namespaces are stripped; class nesting is preserved (matches tree-sitter)."""
    namespaces = frozenset({"geo", "geo::detail"})

    # Single class in a namespace -> bare class name (fixture-parity, unchanged).
    assert _strip_namespace_prefix("geo::Vec3", namespaces) == "Vec3"
    # Nested class in a namespace -> namespace dropped, class nesting kept.
    assert _strip_namespace_prefix("geo::Outer::Inner", namespaces) == "Outer::Inner"
    # Longest namespace prefix wins over a shorter one.
    assert _strip_namespace_prefix("geo::detail::Impl", namespaces) == "Impl"
    # Class outside any namespace is returned unchanged (nesting intact).
    assert _strip_namespace_prefix("Outer::Inner", namespaces) == "Outer::Inner"
    # No namespaces at all: identity.
    assert _strip_namespace_prefix("Vec3", frozenset()) == "Vec3"


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "multilang_repo"
requires_doxygen = pytest.mark.skipif(
    shutil.which("doxygen") is None, reason="doxygen not on PATH"
)


def _by_qual(parsed):
    return {symbol.qualname: symbol for symbol in parsed.symbols}


def test_is_available_matches_which():
    """is_available() reflects shutil.which('doxygen')."""
    from akms.repo_wiki.extract.cpp_doxygen import DoxygenCppExtractor

    assert DoxygenCppExtractor().is_available() is (shutil.which("doxygen") is not None)


@requires_doxygen
def test_extract_project_yields_cpp_parsed_modules():
    """extract_project returns ParsedModules keyed by repo-relative path with symbols."""
    from akms.repo_wiki.extract.cpp_doxygen import DoxygenCppExtractor

    produced = DoxygenCppExtractor().extract_project(str(FIXTURE), ["cpp/vec.cpp"])
    assert "cpp/vec.cpp" in produced
    quals = {s.qualname for s in produced["cpp/vec.cpp"].symbols}
    assert "Vec3" in quals


@requires_doxygen
def test_working_dir_is_cleaned_up(tmp_path, monkeypatch):
    """The throwaway doxygen working dir is removed after the build."""
    import tempfile

    from akms.repo_wiki.extract.cpp_doxygen import DoxygenCppExtractor

    created: list[str] = []
    real_tmp = tempfile.TemporaryDirectory

    class _Tracking(real_tmp):  # type: ignore[misc,valid-type]
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            created.append(self.name)

    monkeypatch.setattr(tempfile, "TemporaryDirectory", _Tracking)
    DoxygenCppExtractor().extract_project(str(FIXTURE), ["cpp/vec.cpp"])
    assert created, "expected a TemporaryDirectory to be used"
    assert not any(Path(p).exists() for p in created)


@requires_doxygen
def test_vec3_data_members_are_public():
    """x/y/z carry visibility 'public' in metadata."""
    from akms.repo_wiki.extract.cpp_doxygen import DoxygenCppExtractor

    produced = DoxygenCppExtractor().extract_project(str(FIXTURE), ["cpp/vec.cpp"])
    syms = _by_qual(produced["cpp/vec.cpp"])
    for member in ("Vec3::x", "Vec3::y", "Vec3::z"):
        assert member in syms, f"missing {member}"
        assert syms[member].metadata.get("visibility") == "public"


@requires_doxygen
def test_visibility_distinct_for_mixed_accessors(tmp_path):
    """A class with public + private members yields distinct visibilities."""
    from akms.repo_wiki.extract.cpp_doxygen import DoxygenCppExtractor

    src = (
        "class Mixed {\n"
        "public:\n    int pub_method() const { return secret; }\n"
        "private:\n    int secret;\n"
        "};\n"
    )
    (tmp_path / "mixed.cpp").write_text(src, encoding="utf-8")
    produced = DoxygenCppExtractor().extract_project(str(tmp_path), ["mixed.cpp"])
    syms = _by_qual(produced["mixed.cpp"])
    vis = {q: s.metadata.get("visibility") for q, s in syms.items()}
    assert vis.get("Mixed::pub_method") == "public"
    assert vis.get("Mixed::secret") == "private"


@requires_doxygen
def test_visibility_rendered_in_symbol_frontmatter(tmp_path, monkeypatch):
    """Non-empty metadata surfaces in symbol-doc frontmatter; Python docs unchanged."""
    from akms.repo_wiki.extract.cpp_doxygen import DoxygenCppExtractor
    from akms.repo_wiki.render_markdown import write_symbol_doc

    produced = DoxygenCppExtractor().extract_project(str(FIXTURE), ["cpp/vec.cpp"])
    syms = _by_qual(produced["cpp/vec.cpp"])
    sym = syms["Vec3::x"]
    monkeypatch.chdir(FIXTURE)
    out = write_symbol_doc(sym, tmp_path, "deadbeef", "multilang", None, FIXTURE)
    assert "visibility: public" in out.read_text()


@requires_doxygen
def test_length_calls_dot_and_not_fields():
    """Length records a call to Vec3::dot and no calls to data members x/y/z."""
    from akms.repo_wiki.extract.cpp_doxygen import DoxygenCppExtractor

    produced = DoxygenCppExtractor().extract_project(str(FIXTURE), ["cpp/vec.cpp"])
    syms = _by_qual(produced["cpp/vec.cpp"])
    assert "length" in syms
    calls = syms["length"].calls
    assert any(c.endswith("dot") for c in calls), f"expected dot in {calls}"
    for field in ("x", "y", "z", "Vec3::x", "Vec3::y", "Vec3::z"):
        assert field not in calls, f"spurious field-access edge to {field}"


@requires_doxygen
def test_call_resolves_confident_with_dst_id():
    """After graph resolution the length→Vec3::dot edge is CONFIDENT with dst_id."""
    from akms.repo_wiki.extract.cpp_doxygen import DoxygenCppExtractor
    from akms.repo_wiki.graph import build_symbol_graph

    produced = DoxygenCppExtractor().extract_project(str(FIXTURE), ["cpp/vec.cpp"])
    graph = build_symbol_graph(list(produced.values()))
    call_edges = [
        e
        for e in graph["edges"]
        if e.get("type") == "calls" and str(e.get("dst_name", "")).endswith("dot")
    ]
    assert call_edges, f"no length→dot calls edge found in {graph['edges']}"
    assert any(e["resolution"] == "CONFIDENT" and e.get("dst_id") for e in call_edges)


@requires_doxygen
def test_doxygen_version_in_symbol_frontmatter(tmp_path, monkeypatch):
    """A doxygen-built cpp symbol doc carries a doxygen_version frontmatter line."""
    from akms.repo_wiki.extract.cpp_doxygen import DoxygenCppExtractor
    from akms.repo_wiki.render_markdown import write_symbol_doc

    produced = DoxygenCppExtractor().extract_project(str(FIXTURE), ["cpp/vec.cpp"])
    sym = next(s for s in produced["cpp/vec.cpp"].symbols if s.qualname == "Vec3")
    monkeypatch.chdir(FIXTURE)
    out = write_symbol_doc(sym, tmp_path, "deadbeef", "multilang", None, FIXTURE)
    assert "doxygen_version:" in out.read_text()


def test_absent_doxygen_falls_back_to_treesitter_with_note():
    """cpp.backend=doxygen + doxygen unavailable → tree-sitter output + a recorded note."""
    pytest.importorskip("tree_sitter_cpp")

    from akms.repo_wiki.extract import registry
    from akms.repo_wiki.extract.cpp_doxygen import DoxygenCppExtractor
    from akms.repo_wiki.hashing import sha256_file
    from akms.repo_wiki.models import SourceFile

    cpp = FIXTURE / "cpp" / "vec.cpp"
    sources = [
        SourceFile("cpp/vec.cpp", str(cpp), "cpp", cpp.stat().st_size, sha256_file(cpp))
    ]
    config = {"languages": {"cpp": {"enabled": True, "backend": "doxygen"}}}

    backend = registry._BACKENDS.get(("cpp", "doxygen"))
    assert isinstance(backend, DoxygenCppExtractor), (
        "doxygen backend must be registered"
    )

    with mock.patch.object(DoxygenCppExtractor, "is_available", return_value=False):
        result = registry.extract_files(sources, config)

    cpp_modules = [
        pm for pm in result.parsed_modules.values() if pm.source_file.language == "cpp"
    ]
    assert any(pm.symbols for pm in cpp_modules), "fallback produced no cpp symbols"
    assert any("cpp" in note for note in result.notes), (
        f"no fallback note in {result.notes}"
    )


def test_version_probe_is_deterministic_when_absent():
    """The backend's version probe never crashes and falls back to 'unknown'."""
    from akms.repo_wiki.extract.cpp_doxygen import DoxygenCppExtractor

    version = DoxygenCppExtractor().tool_version()
    assert isinstance(version, str) and version
    assert (
        version == tool_version_or_unknown(version) or version == UNKNOWN_TOOL_VERSION
    )
