from pathlib import Path

from akms.repo_wiki.cli import main
from akms.repo_wiki.retrieve import (
    code_terms,
    looks_like_symbol,
    normalize_query,
    retrieve,
)
from .test_build_render_graph_summary import copy_fixture

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_normalize_query_detects_symbol_path_and_natural_language():
    assert normalize_query("pkg.core.Greeter.greet").kind == "symbol"
    assert normalize_query("pkg/core.py").kind == "path"
    assert normalize_query("where is Greeter").kind == "where"
    assert normalize_query("friendly greeting behavior").kind == "natural_language"


def test_retrieve_symbol_natural_language_and_path_preserve_metadata(tmp_path: Path):
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-summaries"]) == 0

    symbol_pack = retrieve(tmp_path, "Greeter.greet", expand=False)
    assert symbol_pack.results[0].symbol_id == "python:pkg/core.py::Greeter.greet"
    assert symbol_pack.results[0].path == "pkg/core.py"
    assert symbol_pack.results[0].start_line > 0
    assert symbol_pack.results[0].end_line >= symbol_pack.results[0].start_line

    natural = retrieve(tmp_path, "friendly greeting", expand=False)
    assert any(result.path == "pkg/core.py" for result in natural.results)

    path_pack = retrieve(tmp_path, "pkg/core.py", expand=False)
    assert path_pack.results[0].doc_type == "module"
    assert path_pack.results[0].path == "pkg/core.py"


def test_retrieve_context_expansion_uses_graph_neighbors_and_overlays(tmp_path: Path):
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-summaries"]) == 0
    overlay = tmp_path / ".repo_wiki/overlays/architecture.md"
    overlay.write_text(
        "---\ndoc_type: overlay\n---\n# Architecture\n\nGreeter calls helper.\n"
    )
    assert main(["--repo-root", str(tmp_path), "index", "--force"]) == 0

    pack = retrieve(tmp_path, "Greeter.greet", expand=True)
    roles = {block.role for block in pack.context}
    ids = {block.result.symbol_id for block in pack.context}
    assert "module" in roles
    assert "callee" in roles
    assert "overlay" in roles
    assert "python:pkg/core.py::helper" in ids
    assert all(block.result.path for block in pack.context)


def test_retrieve_works_without_summaries_or_vectors(tmp_path: Path):
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-summaries"]) == 0
    assert not (tmp_path / ".repo_wiki/generated/summaries").exists()

    pack = retrieve(tmp_path, "helper", expand=False)
    assert any(
        result.symbol_id == "python:pkg/core.py::helper" for result in pack.results
    )


def test_namespaced_symbol_ids_are_symbol_queries():
    """Language-qualified and path-qualified ids are symbol queries, as are legacy dotted names."""
    assert looks_like_symbol("python:src/foo/bar.py::Foo.run")
    assert looks_like_symbol("src/foo/bar.py::Foo.run")
    assert looks_like_symbol("src.foo.bar.Foo.run")
    assert code_terms("python:src/foo/bar.py::Foo.run") == [
        "python:src/foo/bar.py::Foo.run"
    ]

    namespaced = normalize_query("python:src/foo/bar.py::Foo.run")
    assert namespaced.kind == "symbol"
    assert namespaced.text == "python:src/foo/bar.py::Foo.run"
    assert normalize_query("src/foo/bar.py::Foo.run").kind == "symbol"
    assert normalize_query("src.foo.bar.Foo.run").kind == "symbol"


def test_plain_english_is_not_a_symbol_query():
    """A sentence of plain words yields no code terms and stays natural language."""
    query = "how does the build process work"
    assert not looks_like_symbol(query)
    assert all(not looks_like_symbol(word) for word in query.split())
    assert code_terms(query) == []
    assert normalize_query(query).kind == "natural_language"


def test_url_with_double_colon_is_not_a_symbol_query():
    """A pasted URL containing '::' stays natural language."""
    url = "https://example.com/foo::bar"
    assert not looks_like_symbol(url)
    assert normalize_query(url).kind == "natural_language"
    assert code_terms(url) != [url]


def test_cpp_scope_token_is_a_symbol_query():
    """A bare C++ scope-resolution token such as std::vector reads as a symbol."""
    assert looks_like_symbol("std::vector")
    query = normalize_query("std::vector")
    assert query.kind == "symbol"
    assert query.text == "std::vector"


def _build_reexport_repo(tmp_path: Path) -> Path:
    """tiny_repo plus re-exports in pkg/__init__.py, a relay module and a src-layout package."""
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    (tmp_path / "pkg/__init__.py").write_text(
        "from .core import Greeter\n"
        "from pkg.core import helper as make_greeting\n"
        "from .relay import Greeter as Relayed\n"
    )
    (tmp_path / "pkg/relay.py").write_text("from .core import Greeter\n")
    (tmp_path / "src/srcpkg").mkdir(parents=True)
    (tmp_path / "src/srcpkg/__init__.py").write_text("")
    (tmp_path / "src/srcpkg/tool.py").write_text(
        "class Tool:\n    def run(self):\n        pass\n"
    )
    assert main(["--repo-root", str(tmp_path), "build", "--no-summaries"]) == 0
    return tmp_path


def _top(pack) -> tuple[str, str]:
    return pack.results[0].doc_id, pack.results[0].resolution


def test_dotted_query_resolves_through_the_longest_module_prefix(tmp_path: Path):
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-summaries"]) == 0

    pack = retrieve(tmp_path, "pkg.core.Greeter.greet", expand=False)
    assert _top(pack) == ("python:pkg/core.py::Greeter.greet", "module-prefix")
    assert _top(retrieve(tmp_path, "pkg.core", expand=False)) == ("pkg.core", "exact")


def test_dotted_query_resolves_a_src_layout_module_without_the_src_prefix(
    tmp_path: Path,
):
    repo = _build_reexport_repo(tmp_path)
    pack = retrieve(repo, "srcpkg.tool.Tool.run", expand=False)
    assert _top(pack) == ("python:src/srcpkg/tool.py::Tool.run", "module-prefix")


def test_dotted_query_follows_one_re_export_hop_including_as_aliases(tmp_path: Path):
    repo = _build_reexport_repo(tmp_path)
    pack = retrieve(repo, "pkg.Greeter.greet", expand=False)
    assert _top(pack) == ("python:pkg/core.py::Greeter.greet", "re-export")
    assert _top(retrieve(repo, "pkg.make_greeting", expand=False)) == (
        "python:pkg/core.py::helper",
        "re-export",
    )


def test_dotted_query_does_not_follow_a_two_hop_re_export_chain(tmp_path: Path):
    repo = _build_reexport_repo(tmp_path)
    pack = retrieve(repo, "pkg.Relayed.greet", expand=False)
    assert pack.results
    assert {result.resolution for result in pack.results} == {"partial-suffix"}
    assert "python:pkg/core.py::Greeter.greet" in {
        result.doc_id for result in pack.results
    }


def test_unresolvable_dotted_query_falls_back_to_labelled_suffix_matches(
    tmp_path: Path,
):
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-summaries"]) == 0

    pack = retrieve(tmp_path, "pkg.Greeter.greet", expand=False)
    assert _top(pack) == ("python:pkg/core.py::Greeter.greet", "partial-suffix")
    assert {result.resolution for result in pack.results} == {"partial-suffix"}
    assert (
        retrieve(tmp_path, "nowhere.qqq_missing.zzz_absent", expand=False).results == []
    )


def test_existing_symbol_query_forms_are_unlabelled_or_exact(tmp_path: Path):
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-summaries"]) == 0

    short = retrieve(tmp_path, "Greeter.greet", expand=False)
    assert _top(short) == ("python:pkg/core.py::Greeter.greet", "")
    full = retrieve(tmp_path, "python:pkg/core.py::Greeter.greet", expand=False)
    assert _top(full) == ("python:pkg/core.py::Greeter.greet", "exact")
    assert all(
        not r.resolution for r in retrieve(tmp_path, "greet", expand=False).results
    )
