import json
import re
from pathlib import Path

from akms.repo_wiki.cli import main
from .test_build_render_graph_summary import copy_fixture

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_cli_query_json_is_stable_and_preserves_citations(tmp_path: Path, capsys):
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-summaries"]) == 0
    capsys.readouterr()

    assert main(["--repo-root", str(tmp_path), "query", "Greeter.greet", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["query"]["kind"] == "symbol"
    assert payload["results"][0]["symbol_id"] == "python:pkg/core.py::Greeter.greet"
    assert payload["results"][0]["path"] == "pkg/core.py"
    assert payload["results"][0]["start_line"] > 0
    assert "context" in payload


def test_cli_query_show_context_and_no_answer_outputs_context(tmp_path: Path, capsys):
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-summaries"]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "--repo-root",
                str(tmp_path),
                "query",
                "Greeter.greet",
                "--show-context",
                "--no-answer",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Results:" in output
    assert "Context:" in output
    assert "python:pkg/core.py::Greeter.greet" in output
    assert "pkg/core.py:L" in output


def test_init_build_index_then_query_cites_source_lines(tmp_path: Path, capsys):
    """The full init, build, index, query sequence runs cleanly and the query cites path:Lx-Ly."""
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    for command in (["init"], ["build"], ["index"]):
        assert main(["--repo-root", str(tmp_path), *command]) == 0
    assert any((tmp_path / ".repo_wiki" / "generated").rglob("*.md"))
    assert (tmp_path / ".repo_wiki" / "index").exists()
    capsys.readouterr()

    assert (
        main(
            [
                "--repo-root",
                str(tmp_path),
                "query",
                "where",
                "is",
                "config",
                "loaded",
                "--show-context",
            ]
        )
        == 0
    )
    assert re.search(r"\S+:L\d+-L?\d+", capsys.readouterr().out)
