"""Tree-sitter extractors for Rust, C++ and Julia: symbol kinds, qualname joiners and heuristic call edges."""

from __future__ import annotations

from pathlib import Path

from akms.repo_wiki.extract.base import Extractor
from akms.repo_wiki.models import Language, ParsedModule, SourceFile


def _sf(tmp_path: Path, name: str, text: str, language: str) -> SourceFile:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return SourceFile(name, str(path), language, path.stat().st_size, "sha256:x")


def _by_qual(pm) -> dict:
    return {s.qualname: s for s in pm.symbols}


def test_walker_produces_symbols_and_edges(tmp_path):
    """The generic walker (via a real subclass) yields symbols + heuristic call edges."""
    from akms.repo_wiki.extract.treesitter import RustExtractor, TreeSitterExtractor

    assert issubclass(RustExtractor, TreeSitterExtractor)
    assert isinstance(RustExtractor(), Extractor)

    src = (
        "pub struct Circle { r: f64 }\npub fn helper() -> Circle { Circle::new(1.0) }\n"
    )
    sf = _sf(tmp_path, "s.rs", src, "rust")
    pm = RustExtractor().extract(sf)

    assert isinstance(pm, ParsedModule)
    by_name = {s.qualname: s for s in pm.symbols}
    assert "Circle" in by_name and by_name["Circle"].kind == "class"
    assert "helper" in by_name and by_name["helper"].kind == "function"
    assert by_name["helper"].start_line == 2
    assert by_name["helper"].span.start_line == 2
    assert "Circle::new" in by_name["helper"].calls


def test_subclasses_override_node_tables_and_name_hooks(tmp_path):
    """A subclass-supplied node table changes which nodes become symbols."""
    from akms.repo_wiki.extract.treesitter import RustExtractor, TreeSitterExtractor

    class FunctionsOnlyRust(TreeSitterExtractor):
        language = Language.RUST
        extensions = (".rs",)
        joiner = "::"
        symbol_nodes = {"function_item": "function"}  # no struct/trait

        @staticmethod
        def _grammar():
            import tree_sitter_rust

            return tree_sitter_rust.language()

    src = "pub struct Circle { r: f64 }\npub fn helper() {}\n"
    sf = _sf(tmp_path, "s.rs", src, "rust")

    full = {s.qualname for s in RustExtractor().extract(sf).symbols}
    narrowed = {s.qualname for s in FunctionsOnlyRust().extract(sf).symbols}

    assert "Circle" in full  # default table picks up the struct
    assert "Circle" not in narrowed  # overridden table drops it
    assert "helper" in narrowed  # but still finds functions


def test_rust_qualname_joiner_is_double_colon(tmp_path):
    """RustExtractor uses '::' joiner; struct->class, impl method->method."""
    from akms.repo_wiki.extract.treesitter import RustExtractor

    src = (
        "pub struct Circle { r: f64 }\n"
        "impl Circle { pub fn new(r: f64) -> Circle { Circle { r } } }\n"
        "trait Shape { fn name(&self) -> String; }\n"
    )
    syms = _by_qual(RustExtractor().extract(_sf(tmp_path, "s.rs", src, "rust")))
    assert syms["Circle"].kind == "class"
    assert "Circle::new" in syms and syms["Circle::new"].kind == "method"
    assert syms["Circle::new"].language.value == "rust"
    assert syms["Shape"].kind == "class"  # trait maps onto class kind


def test_cpp_qualname_joiner_and_kinds(tmp_path):
    """CppExtractor uses '::' joiner; struct method qualifies as Type::method."""
    from akms.repo_wiki.extract.treesitter import CppExtractor

    src = (
        "namespace geo {\n"
        "struct Vec3 { double x; double dot(const Vec3& o) const { return x*o.x; } };\n"
        "double length(const Vec3& v) { return v.dot(v); }\n"
        "}\n"
    )
    syms = _by_qual(CppExtractor().extract(_sf(tmp_path, "v.cpp", src, "cpp")))
    assert syms["Vec3"].kind == "class"
    assert "Vec3::dot" in syms and syms["Vec3::dot"].kind == "method"
    assert "length" in syms and syms["length"].kind == "function"


def test_julia_kinds_and_module_qualnames(tmp_path):
    """JuliaExtractor uses '.' joiner; module->module, struct->class, fn->function."""
    from akms.repo_wiki.extract.treesitter import JuliaExtractor

    src = (
        "module Geo\n"
        "struct Circle\n    r::Float64\nend\n"
        "function area(c::Circle)\n    3.14 * c.r^2\nend\n"
        "end\n"
    )
    syms = _by_qual(JuliaExtractor().extract(_sf(tmp_path, "g.jl", src, "julia")))
    assert syms["Geo"].kind == "module"
    assert syms["Geo.Circle"].kind == "class"
    assert syms["Geo.area"].kind == "function"
    assert syms["Geo.area"].language.value == "julia"


def test_heuristic_callgraph_yields_per_language_edges(tmp_path):
    """The heuristic scan records intra-language call edges per language."""
    from akms.repo_wiki.extract.treesitter import CppExtractor, RustExtractor

    rust = "impl Circle { pub fn new() -> i32 { 0 } }\npub fn helper() -> i32 { Circle::new() }\n"
    rsyms = _by_qual(RustExtractor().extract(_sf(tmp_path, "s.rs", rust, "rust")))
    assert "Circle::new" in rsyms["helper"].calls

    cpp = (
        "struct Vec3 { double dot(const Vec3& o) const { return 0; } };\n"
        "double length(const Vec3& v) { return v.dot(v); }\n"
    )
    csyms = _by_qual(CppExtractor().extract(_sf(tmp_path, "v.cpp", cpp, "cpp")))
    assert "dot" in csyms["length"].calls
