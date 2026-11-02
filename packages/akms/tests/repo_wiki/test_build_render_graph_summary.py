import json
from pathlib import Path

from akms.repo_wiki.cli import main
from akms.repo_wiki.models import Language, SourceSpan, Symbol
from akms.repo_wiki.render_markdown import write_symbol_doc

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def copy_fixture(src: Path, dst: Path) -> None:
    for path in src.rglob("*"):
        rel = path.relative_to(src)
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(path.read_bytes())


def test_build_renders_docs_manifest_graph_and_summaries(tmp_path: Path):
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-index"]) == 0
    generated = tmp_path / ".repo_wiki" / "generated"
    assert (generated / "repo_map.md").exists()
    assert (generated / "modules" / "pkg.core.md").exists()
    assert (generated / "symbols" / "python_pkg.core.py__Greeter.greet.md").exists()
    assert (
        generated / "summaries" / "python_pkg.core.py__Greeter.greet.summary.md"
    ).exists()
    graph = json.loads((generated / "symbol_graph.json").read_text())
    assert "python:pkg/core.py::Greeter.greet" in graph["nodes"]
    assert any(edge["type"] == "calls" for edge in graph["edges"])
    manifest = json.loads((tmp_path / ".repo_wiki" / "manifest.json").read_text())
    assert "pkg/core.py" in manifest["files"]


def _cpp_symbol(repo_root: Path, metadata: dict[str, object]) -> Symbol:
    (repo_root / "vec.cpp").write_text("int x;\n", encoding="utf-8")
    return Symbol(
        symbol_id="cpp.vec.Vec3..x",
        path="vec.cpp",
        module="vec",
        name="x",
        qualname="Vec3::x",
        kind="constant",
        parent_id="cpp.vec.Vec3",
        start_line=1,
        end_line=1,
        signature=None,
        docstring=None,
        span=SourceSpan(path="vec.cpp", start_line=1, end_line=1),
        language=Language.CPP,
        metadata=metadata,
    )


def test_symbol_doc_renders_visibility_from_metadata(tmp_path: Path):
    """Non-empty metadata surfaces as a frontmatter line in the symbol doc."""
    sym = _cpp_symbol(tmp_path, {"visibility": "public"})
    out = write_symbol_doc(sym, tmp_path / "out", "deadbeef", "demo", None, tmp_path)
    assert "visibility: public" in out.read_text()


def test_symbol_doc_omits_visibility_when_metadata_empty(tmp_path: Path):
    """Empty metadata adds no extra frontmatter line (byte-identity preserved)."""
    sym = _cpp_symbol(tmp_path, {})
    out = write_symbol_doc(sym, tmp_path / "out", "deadbeef", "demo", None, tmp_path)
    assert "visibility:" not in out.read_text()


def test_changed_only_build_skips_unchanged_files(tmp_path: Path):
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-index"]) == 0
    assert (
        main(["--repo-root", str(tmp_path), "build", "--changed-only", "--no-index"])
        == 0
    )


def test_build_reports_processed_skipped_and_errored_counts(tmp_path: Path, capsys):
    """The build prints a per-run summary of processed, skipped and errored files."""
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-index"]) == 0
    out = capsys.readouterr().out
    for word in ("processed", "skipped", "errored"):
        assert word in out


def _snapshot(generated: Path) -> dict[str, bytes]:
    return {
        path.relative_to(generated).as_posix(): path.read_bytes()
        for path in sorted(generated.rglob("*"))
        if path.is_file()
    }


def test_repeat_and_forced_builds_are_byte_identical(tmp_path: Path):
    """Two builds of the same repo, and a forced rebuild, produce identical generated files."""
    roots = []
    for label in ("a", "b"):
        root = tmp_path / label / "tiny_repo"
        root.mkdir(parents=True)
        copy_fixture((FIXTURES / "tiny_repo"), root)
        assert (
            main(["--repo-root", str(root), "build", "--no-index", "--no-summaries"])
            == 0
        )
        roots.append(root)
    first, second = (_snapshot(root / ".repo_wiki" / "generated") for root in roots)
    assert first
    assert first == second

    manifests = [
        json.loads((root / ".repo_wiki" / "manifest.json").read_text())
        for root in roots
    ]
    assert manifests[0]["files"] == manifests[1]["files"]

    assert (
        main(
            [
                "--repo-root",
                str(roots[0]),
                "build",
                "--no-index",
                "--no-summaries",
                "--force",
            ]
        )
        == 0
    )
    assert _snapshot(roots[0] / ".repo_wiki" / "generated") == first


def test_symbol_doc_cites_source_path_and_lines(tmp_path: Path):
    """A generated symbol doc names its source file and line range."""
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    assert (
        main(["--repo-root", str(tmp_path), "build", "--no-summaries", "--no-index"])
        == 0
    )
    doc = (
        tmp_path / ".repo_wiki/generated/symbols/python_pkg.core.py__Greeter.greet.md"
    ).read_text()
    assert "Source: `pkg/core.py`" in doc
    assert "Lines:" in doc
