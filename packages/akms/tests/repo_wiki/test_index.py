import json
import sqlite3
from pathlib import Path

import pytest

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


ERASED_TOKEN = "zqxerasedtoken8841"


def _index_bytes(root: Path) -> list[tuple[str, bytes]]:
    index_dir = root / ".repo_wiki" / "index"
    return [
        (path.name, path.read_bytes())
        for path in sorted(index_dir.rglob("*"))
        if path.is_file()
    ]


def _seed_erasure_repo(root: Path) -> Path:
    (root / "src").mkdir()
    (root / "src" / "app.py").write_text('"""App."""\n\nVALUE = 1\n')
    leak = root / "src" / "leak.py"
    leak.write_text(
        f'"""Module {ERASED_TOKEN}."""\n\n\n'
        f'def leaked():\n    """Return {ERASED_TOKEN}."""\n'
        f'    return "{ERASED_TOKEN}"\n'
    )
    return leak


def _assert_erased_after_rebuild(root: Path, remove) -> None:
    assert main(["--repo-root", str(root), "build", "--no-summaries"]) == 0
    # Guard against a vacuous pass: the token really was indexed.
    assert any(ERASED_TOKEN.encode() in data for _, data in _index_bytes(root))

    remove()
    assert main(["--repo-root", str(root), "build", "--no-summaries"]) == 0
    assert search_index(root, "VALUE")
    assert not search_index(root, ERASED_TOKEN)
    after = _index_bytes(root)
    assert after
    for name, data in after:
        assert ERASED_TOKEN.encode() not in data, name


@pytest.mark.parametrize("how", ["delete", "exclude"])
def test_index_leaves_no_bytes_of_removed_documents(tmp_path: Path, how: str):
    """A document dropped from the index is erased from every file on disk."""
    leak = _seed_erasure_repo(tmp_path)

    def remove() -> None:
        if how == "delete":
            leak.unlink()
        else:
            (tmp_path / ".repo_wiki" / "config.yaml").write_text(
                "scanner:\n  exclude:\n    - src/leak.py\n", encoding="utf-8"
            )

    _assert_erased_after_rebuild(tmp_path, remove)


def test_index_erasure_without_fts5_secure_delete(tmp_path: Path, monkeypatch):
    """Where FTS5 lacks secure-delete (SQLite < 3.42), optimize and VACUUM erase."""
    monkeypatch.setattr(
        SQLiteIndexBackend, "_enable_fts_secure_delete", lambda self: False
    )
    leak = _seed_erasure_repo(tmp_path)
    _assert_erased_after_rebuild(tmp_path, leak.unlink)


def test_index_connection_runs_with_secure_delete(tmp_path: Path):
    backend = SQLiteIndexBackend(tmp_path / ".repo_wiki/index/repo_wiki.sqlite3")
    try:
        assert backend.connection.execute("PRAGMA secure_delete").fetchone()[0] == 1
        assert backend.fts_secure_delete is (sqlite3.sqlite_version_info >= (3, 42))
    finally:
        backend.close()


def test_index_written_without_secure_delete_is_scrubbed_on_first_open(
    tmp_path: Path, monkeypatch
):
    """An index an older version wrote keeps deleted text until it is reopened."""
    with monkeypatch.context() as legacy:
        # Behave like the earlier backend: no secure delete, no one-time scrub.
        original_connect = sqlite3.connect

        def connect(*args, **kwargs):
            connection = original_connect(*args, **kwargs)
            connection.execute("PRAGMA secure_delete=OFF")
            return connection

        legacy.setattr(sqlite3, "connect", connect)
        legacy.setattr(SQLiteIndexBackend, "__init__", _legacy_init)
        legacy.setattr(SQLiteIndexBackend, "_erase_removed_text", lambda self: None)
        leak = _seed_erasure_repo(tmp_path)
        assert main(["--repo-root", str(tmp_path), "build", "--no-summaries"]) == 0
        leak.unlink()
        assert main(["--repo-root", str(tmp_path), "build", "--no-summaries"]) == 0
        # The residue this test is about really is there.
        assert any(ERASED_TOKEN.encode() in data for _, data in _index_bytes(tmp_path))

    assert main(["--repo-root", str(tmp_path), "index"]) == 0
    for name, data in _index_bytes(tmp_path):
        assert ERASED_TOKEN.encode() not in data, name
    assert search_index(tmp_path, "VALUE")


def _legacy_init(self, path: Path) -> None:
    from akms.repo_wiki.paths import ensure_parent

    self.path = path
    ensure_parent(path)
    self.connection = sqlite3.connect(path)
    self.connection.row_factory = sqlite3.Row
    self._init_schema()
    self.fts_secure_delete = False
