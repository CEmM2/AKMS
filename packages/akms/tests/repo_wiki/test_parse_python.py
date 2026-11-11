from pathlib import Path

from akms.repo_wiki.cli import main
from akms.repo_wiki.extract.python_ast import PythonAstExtractor, parse_python_file
from akms.repo_wiki.models import SourceFile, SourceSpan, Symbol

FIXTURES = Path(__file__).resolve().parent / "fixtures"

SAMPLE = (FIXTURES / "parse_repo/pkg/sample.py").resolve()


def _parse_sample():
    return parse_python_file(
        SourceFile(
            "pkg/sample.py", str(SAMPLE), "python", SAMPLE.stat().st_size, "sha256:file"
        )
    )


def test_parser_extracts_symbols_imports_calls_and_nested_functions():
    path = (FIXTURES / "parse_repo/pkg/sample.py").resolve()
    parsed = parse_python_file(
        SourceFile(
            "pkg/sample.py", str(path), "python", path.stat().st_size, "sha256:file"
        )
    )
    ids = {symbol.symbol_id for symbol in parsed.symbols}
    assert "python:pkg/sample.py::CONSTANT" in ids
    assert "python:pkg/sample.py::Child" in ids
    assert "python:pkg/sample.py::Child.run" in ids
    assert "python:pkg/sample.py::Child.run.nested" in ids
    run = next(
        symbol
        for symbol in parsed.symbols
        if symbol.symbol_id == "python:pkg/sample.py::Child.run"
    )
    assert run.kind == "method"
    assert "decorated" in run.decorators
    assert "nested" in run.calls
    assert parsed.imports == ["os", "pathlib.Path"]


def test_parser_returns_build_error_for_syntax_error(tmp_path: Path):
    bad = tmp_path / "bad.py"
    bad.write_text("def broken(:\n", encoding="utf-8")
    parsed = parse_python_file(
        SourceFile("bad.py", str(bad), "python", bad.stat().st_size, "sha256:x")
    )
    assert parsed.errors
    assert parsed.symbols == []


def test_every_symbol_carries_a_span_matching_its_line_numbers():
    """Each symbol has a span on its own file whose lines equal the symbol's lines."""
    parsed = _parse_sample()
    assert parsed.symbols
    for symbol in parsed.symbols:
        assert isinstance(symbol.span, SourceSpan)
        assert symbol.span.path == "pkg/sample.py"
        assert symbol.span.start_line == symbol.start_line
        assert symbol.span.end_line == symbol.end_line


def test_known_symbol_spans_cover_their_definitions():
    """Spans of well-known fixture symbols match the definition line ranges."""
    by_id = {symbol.symbol_id: symbol.span for symbol in _parse_sample().symbols}
    expected = {
        "python:pkg/sample.py::CONSTANT": (6, 6),
        "python:pkg/sample.py::decorated": (9, 10),
        "python:pkg/sample.py::Base": (13, 14),
        "python:pkg/sample.py::Child": (17, 27),
        "python:pkg/sample.py::Child.run": (21, 27),
        "python:pkg/sample.py::Child.run.nested": (24, 25),
    }
    for symbol_id, (start, end) in expected.items():
        assert (by_id[symbol_id].start_line, by_id[symbol_id].end_line) == (start, end)


def test_extractor_class_matches_parse_function():
    """PythonAstExtractor.extract yields the same module as parse_python_file."""
    source_file = SourceFile(
        "pkg/sample.py", str(SAMPLE), "python", SAMPLE.stat().st_size, "sha256:file"
    )
    assert (
        PythonAstExtractor().extract(source_file).to_dict()
        == parse_python_file(source_file).to_dict()
    )


def test_cli_parse_json_lists_symbols(capsys):
    """The parse command prints the file's symbols as JSON."""
    assert (
        main(
            [
                "--repo-root",
                str(FIXTURES / "parse_repo"),
                "parse",
                "pkg/sample.py",
                "--json",
            ]
        )
        == 0
    )
    assert "python:pkg/sample.py::Child.run" in capsys.readouterr().out


def test_import_bindings_record_aliases_and_resolve_relative_imports(tmp_path: Path):
    init = tmp_path / "__init__.py"
    init.write_text(
        "import os.path\nimport json as js\nfrom .core import Greeter\n"
        "from ..up import thing as other\nfrom . import sibling\nfrom x import *\n"
        "def f():\n    import inner\n"
    )
    parsed = parse_python_file(
        SourceFile(
            "a/pkg/__init__.py", str(init), "python", init.stat().st_size, "sha256:x"
        )
    )
    assert parsed.import_bindings == {
        "Greeter": "a.pkg.core.Greeter",
        "js": "json",
        "os": "os",
        "other": "a.up.thing",
        "sibling": "a.pkg.sibling",
    }


ALIAS_SOURCE = """
import top as module_level


def uses():
    from pkg.cli import main as run_cli
    import pkg.tools as tools
    from pkg.plain import not_aliased
    import os.path as op
    if run_cli:
        with open("x") as stream:
            from pkg.deep import inner as deep_inner
    try:
        from . import sibling as near
        from ..up import thing as far
        from .... import too_high as lost
    except ImportError:
        import fallback as near

    def nested():
        from pkg.nested import helper as nested_helper

    class Local:
        from pkg.klass import member as class_member


async def uses_async():
    from pkg.cli import main as run_async
"""


def _parse_aliases(tmp_path: Path, relative: str = "pkg/sub/mod.py"):
    target = tmp_path / "mod.py"
    target.write_text(ALIAS_SOURCE, encoding="utf-8")
    parsed = parse_python_file(
        SourceFile(relative, str(target), "python", target.stat().st_size, "sha256:x")
    )
    return {symbol.qualname: symbol for symbol in parsed.symbols}


def test_function_level_aliases_are_recorded_in_their_own_scope(tmp_path: Path):
    symbols = _parse_aliases(tmp_path)
    assert symbols["uses"].import_aliases == {
        "deep_inner": "pkg.deep.inner",
        "far": "pkg.up.thing",
        "near": "fallback",
        "op": "os.path",
        "run_cli": "pkg.cli.main",
        "tools": "pkg.tools",
    }
    assert "not_aliased" not in symbols["uses"].import_aliases
    assert "lost" not in symbols["uses"].import_aliases
    assert symbols["uses.nested"].import_aliases == {
        "nested_helper": "pkg.nested.helper"
    }
    assert symbols["uses_async"].import_aliases == {"run_async": "pkg.cli.main"}
    assert symbols["uses.Local"].import_aliases == {}


def test_relative_alias_in_a_package_init_is_relative_to_that_package(tmp_path: Path):
    symbols = _parse_aliases(tmp_path, "pkg/sub/__init__.py")
    assert symbols["uses"].import_aliases["far"] == "pkg.up.thing"


def test_import_aliases_round_trip_and_stay_out_of_empty_payloads(tmp_path: Path):
    symbols = _parse_aliases(tmp_path)
    data = symbols["uses"].to_dict()
    assert Symbol.from_dict(data).import_aliases == symbols["uses"].import_aliases
    assert "import_aliases" not in symbols["uses.Local"].to_dict()
    assert Symbol.from_dict(symbols["uses.Local"].to_dict()).import_aliases == {}
