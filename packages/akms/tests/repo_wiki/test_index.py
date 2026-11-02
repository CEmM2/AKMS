import json
from pathlib import Path

from akms.repo_wiki.cli import main
from akms.repo_wiki.index import (
    SQLiteIndexBackend,
    discover_index_documents,
    fts_query,
    search_index,
    update_index,
)
from .test_build_render_graph_summary import copy_fixture

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_index_exact_symbol_path_metadata_and_no_vectors(tmp_path: Path):
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-index"]) == 0

    summary = update_index(tmp_path, force=True)
    assert summary.indexed > 0

    symbol_results = search_index(tmp_path, "Greeter.greet")
    assert symbol_results[0].symbol_id == "python:pkg/core.py::Greeter.greet"
    assert symbol_results[0].kind == "method"
    assert symbol_results[0].path == "pkg/core.py"
    assert symbol_results[0].module == "pkg.core"
    assert symbol_results[0].start_line > 0
    assert symbol_results[0].end_line >= symbol_results[0].start_line
    assert symbol_results[0].repo_commit
    assert symbol_results[0].content_hash.startswith("sha256:")

    path_results = search_index(tmp_path, "pkg/core.py")
    assert any(
        result.doc_type == "module" and result.path == "pkg/core.py"
        for result in path_results
    )

    backend = SQLiteIndexBackend(tmp_path / ".repo_wiki/index/repo_wiki.sqlite3")
    try:
        no_vector_results = backend.search("helper")
    finally:
        backend.close()
    assert any(
        result.symbol_id == "python:pkg/core.py::helper" for result in no_vector_results
    )


def test_index_overlays_deletion_and_metadata_filters(tmp_path: Path):
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-index"]) == 0
    overlay = tmp_path / ".repo_wiki/overlays/architecture.md"
    overlay.write_text(
        "---\ndoc_type: overlay\nauthor: human\ntopic: architecture\n---\n"
        "# Architecture\n\nGreeting flow uses Greeter.\n",
        encoding="utf-8",
    )

    update_index(tmp_path, force=True)
    assert (
        search_index(tmp_path, "Greeting flow", filters={"doc_type": "overlay"})[
            0
        ].doc_type
        == "overlay"
    )
    assert (
        search_index(
            tmp_path, "helper", filters={"symbol_id": "python:pkg/core.py::helper"}
        )[0].symbol_id
        == "python:pkg/core.py::helper"
    )
    assert (
        search_index(tmp_path, "helper", filters={"module": "pkg.core"})[0].module
        == "pkg.core"
    )
    assert (
        search_index(tmp_path, "helper", filters={"kind": "function"})[0].kind
        == "function"
    )
    assert search_index(tmp_path, "pkg/core.py", filters={"path": "pkg/core.py"})

    symbol_doc = tmp_path / ".repo_wiki/generated/symbols/python_pkg.core.py__helper.md"
    symbol_doc.unlink()
    update_index(tmp_path, changed_only=True)
    assert not search_index(
        tmp_path,
        "python:pkg/core.py::helper",
        filters={"symbol_id": "python:pkg/core.py::helper", "doc_type": "symbol"},
    )


def test_index_frontmatter_uses_yaml_subset_and_natural_language_phrase_query(
    tmp_path: Path,
):
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-index"]) == 0
    overlay = tmp_path / ".repo_wiki/overlays/architecture.md"
    overlay.write_text(
        "---\n"
        "doc_type: 'overlay'\n"
        "author: human\n"
        "tags:\n"
        "  - greeting\n"
        "---\n"
        "# Architecture\n\nFriendly greeting? Greeter flow uses helper.\n",
        encoding="utf-8",
    )

    update_index(tmp_path, force=True)

    assert '"Friendly greeting"' in fts_query("Friendly greeting?")
    results = search_index(
        tmp_path, "Friendly greeting?", filters={"doc_type": "overlay"}
    )
    assert results[0].doc_type == "overlay"


def test_index_skips_generated_docs_for_excluded_source_paths(tmp_path: Path):
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-index"]) == 0
    generated = tmp_path / ".repo_wiki/generated/symbols/secret.md"
    generated.write_text(
        "---\ndoc_type: symbol\npath: .env\nsymbol_id: secret\nkind: constant\n"
        "repo_commit: abc\n---\n# secret\nTOKEN\n",
        encoding="utf-8",
    )

    docs = discover_index_documents(tmp_path)
    assert all(doc.path != ".env" for doc in docs)
    update_index(tmp_path, force=True)
    assert not search_index(tmp_path, "TOKEN")

    manifest = json.loads((tmp_path / ".repo_wiki/manifest.json").read_text())
    assert manifest["repo"]["index_status"] == "skipped"
