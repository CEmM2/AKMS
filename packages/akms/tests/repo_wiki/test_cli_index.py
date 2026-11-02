import json
from pathlib import Path

from akms.repo_wiki.cli import main
from akms.repo_wiki.index import search_index
from .test_build_render_graph_summary import copy_fixture

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_cli_index_changed_only_force_and_query_json(tmp_path: Path, capsys):
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-index"]) == 0
    capsys.readouterr()

    assert main(["--repo-root", str(tmp_path), "index", "--force", "--json"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["indexed"] > 0

    assert (
        main(["--repo-root", str(tmp_path), "index", "--changed-only", "--json"]) == 0
    )
    second = json.loads(capsys.readouterr().out)
    assert second["skipped_unchanged"] >= first["indexed"]

    assert (
        main(["--repo-root", str(tmp_path), "index", "--query", "Greeter.greet"]) == 0
    )
    queried = json.loads(capsys.readouterr().out)
    assert queried["results"][0]["symbol_id"] == "python:pkg/core.py::Greeter.greet"


def test_cli_index_deletes_removed_documents(tmp_path: Path, capsys):
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-index"]) == 0
    assert main(["--repo-root", str(tmp_path), "index", "--force", "--json"]) == 0
    capsys.readouterr()
    assert search_index(
        tmp_path, "helper", filters={"symbol_id": "python:pkg/core.py::helper"}
    )

    (tmp_path / ".repo_wiki/generated/symbols/python_pkg.core.py__helper.md").unlink()
    assert (
        main(["--repo-root", str(tmp_path), "index", "--changed-only", "--json"]) == 0
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["deleted"] >= 1
    assert not search_index(
        tmp_path,
        "python:pkg/core.py::helper",
        filters={"symbol_id": "python:pkg/core.py::helper", "doc_type": "symbol"},
    )
