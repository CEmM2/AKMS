"""Entry-point facts the Python extractor records for flows: ``__main__`` calls, argparse
handlers and decorator names, and how they reach the symbol graph and ``CodeGraph``."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from akms.repo_wiki.cli import main
from akms.repo_wiki.code_graph import CONFIDENT, load_code_graph
from akms.repo_wiki.extract.python_ast import extract_cli_handlers, extract_main_calls
from akms.repo_wiki.graph import decorator_names
from akms.repo_wiki.models import ParsedModule, SourceFile, Symbol


def test_main_calls_come_from_the_guard_either_way_round() -> None:
    tree = ast.parse(
        "import sys\n"
        "setup()\n"
        "def main(): run()\n"
        "if __name__ == '__main__':\n"
        "    sys.exit(main())\n"
        "if '__main__' == __name__:\n"
        "    other()\n"
        "if __name__ == 'pkg':\n"
        "    never()\n"
    )
    assert extract_main_calls(tree, is_main_module=False) == [
        "main",
        "other",
        "sys.exit",
    ]


def test_dunder_main_module_counts_every_module_level_call() -> None:
    tree = ast.parse(
        "from pkg.cli import main\ndef helper(): hidden()\nraise SystemExit(main())\n"
    )
    assert extract_main_calls(tree, is_main_module=True) == ["SystemExit", "main"]
    assert extract_main_calls(tree, is_main_module=False) == []


def test_cli_handlers_are_set_defaults_func_names() -> None:
    node = ast.parse(
        "def build():\n"
        "    sub.add_parser('a').set_defaults(func=cmd_a)\n"
        "    p.set_defaults(func=handlers.cmd_b, verbose=True)\n"
        "    p.set_defaults(func=lambda a: a)\n"
        "    p.other(func=cmd_c)\n"
    ).body[0]
    assert extract_cli_handlers(node) == ["cmd_a", "handlers.cmd_b"]


def test_decorator_names_drop_arguments_and_repeats() -> None:
    assert decorator_names(
        ["app.command('x')", "@click.option('--n', default=1)", "property", "property"]
    ) == ["app.command", "click.option", "property"]


def test_ir_round_trip_and_omission_when_empty() -> None:
    source = SourceFile("m.py", "/r/m.py", "python", 1, "h")
    parsed = ParsedModule(source, "m", None, [], [], main_calls=["main"])
    assert ParsedModule.from_dict(parsed.to_dict()).main_calls == ["main"]
    assert "main_calls" not in ParsedModule(source, "m", None, [], []).to_dict()
    data = {
        "symbol_id": "python:m.py::f",
        "path": "m.py",
        "module": "m",
        "name": "f",
        "qualname": "f",
        "kind": "function",
        "start_line": 1,
        "end_line": 2,
        "cli_handlers": ["cmd"],
    }
    assert Symbol.from_dict(data).cli_handlers == ["cmd"]
    assert (
        "cli_handlers" not in Symbol.from_dict({**data, "cli_handlers": []}).to_dict()
    )


@pytest.fixture()
def repo(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "tool.py").write_text(
        "import argparse\n\n\n"
        "def cmd_go(args):\n    return args\n\n\n"
        "def build():\n"
        "    parser = argparse.ArgumentParser()\n"
        "    parser.set_defaults(func=cmd_go)\n"
        "    return parser\n\n\n"
        "@app.command()\ndef hello():\n    return 1\n\n\n"
        "if __name__ == '__main__':\n    build()\n",
        encoding="utf-8",
    )
    assert (
        main(["--repo-root", str(tmp_path), "build", "--no-summaries", "--no-index"])
        == 0
    )
    capsys.readouterr()
    return tmp_path


def test_facts_reach_the_graph_file_and_code_graph(repo: Path) -> None:
    data = json.loads(
        (repo / ".repo_wiki/generated/symbol_graph.json").read_text("utf-8")
    )
    nodes = data["nodes"]
    assert nodes["pkg.tool"]["main_calls"] == ["build"]
    assert nodes["python:pkg/tool.py::build"]["cli_handlers"] == ["cmd_go"]
    assert nodes["python:pkg/tool.py::hello"]["decorators"] == ["app.command"]
    assert "decorators" not in nodes["python:pkg/tool.py::cmd_go"]
    graph = load_code_graph(repo).graph
    assert graph.main_calls == {"pkg.tool": ["build"]}
    assert graph.cli_handlers["python:pkg/tool.py::build"] == ["cmd_go"]
    assert graph.decorators["python:pkg/tool.py::hello"] == ["app.command"]
    # Resolving a reference adds no edge.
    edges = graph.resolve_reference("pkg.tool", "build")
    assert [(e.target, e.resolution) for e in edges] == [
        ("python:pkg/tool.py::build", CONFIDENT)
    ]
    assert not graph.in_edges.get("python:pkg/tool.py::cmd_go")
    assert graph.resolve_reference("pkg.tool", "argparse.ArgumentParser") == []
    assert graph.resolve_reference("no.such", "build") == []
