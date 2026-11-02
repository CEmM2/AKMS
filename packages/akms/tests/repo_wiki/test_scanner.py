from pathlib import Path

from akms.repo_wiki.cli import main
from akms.repo_wiki.config import default_config, load_config
from akms.repo_wiki.scanner import (
    LANGUAGE_BY_SUFFIX,
    matches_any,
    matches_pattern,
    scan_repository,
)
from .test_build_render_graph_summary import copy_fixture

FIXTURES = Path(__file__).resolve().parent / "fixtures"

DEFAULT_INCLUDE = ["**/*.py", "**/*.md", "**/*.yaml", "**/*.yml", "**/*.toml"]


def _language_config(include, languages):
    return {
        "scanner": {"include": include, "exclude": [], "respect_gitignore": False},
        "languages": languages,
    }


def _seed_multilang_sources(root: Path) -> None:
    src = root / "src"
    src.mkdir()
    (src / "a.py").write_text("x = 1\n")
    (src / "b.rs").write_text("pub fn f() {}\n")
    (src / "c.cpp").write_text("int f() { return 0; }\n")
    (src / "d.jl").write_text("f() = 1\n")


def test_scanner_respects_gitignore_secret_excludes_and_hashes():
    root = (FIXTURES / "scan_repo").resolve()
    sources, skipped = scan_repository(root, default_config(root))
    assert [source.path for source in sources] == ["src/app.py"]
    skipped_paths = {item.path for item in skipped}
    assert ".env" in skipped_paths
    assert "ignored.py" in skipped_paths
    assert sources[0].content_hash.startswith("sha256:")


def test_scanner_prunes_excluded_directories_before_file_filtering(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n")
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "ignored.py").write_text("print('skip')\n")

    sources, skipped = scan_repository(tmp_path, default_config(tmp_path))

    assert [source.path for source in sources] == ["src/app.py"]
    skipped_paths = {item.path for item in skipped}
    assert "node_modules" in skipped_paths
    assert "node_modules/pkg/ignored.py" not in skipped_paths


def test_scan_cli_json_lists_scanned_files(capsys):
    """The scan command prints the scanned sources as JSON."""
    assert main(["--repo-root", str(FIXTURES / "scan_repo"), "scan", "--json"]) == 0
    out = capsys.readouterr().out
    assert '"files"' in out
    assert "src/app.py" in out


def test_suffixes_map_to_languages():
    """Rust, Julia and every C++ suffix resolve to their language."""
    assert LANGUAGE_BY_SUFFIX[".rs"] == "rust"
    assert LANGUAGE_BY_SUFFIX[".jl"] == "julia"
    for suffix in (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".h", ".hxx"):
        assert LANGUAGE_BY_SUFFIX[suffix] == "cpp"


def test_scanner_includes_files_of_enabled_languages(tmp_path: Path):
    """With a language enabled, its files are scanned with that language."""
    _seed_multilang_sources(tmp_path)
    languages = {name: {"enabled": True} for name in ("python", "rust", "cpp", "julia")}
    sources, _ = scan_repository(tmp_path, _language_config(DEFAULT_INCLUDE, languages))
    by_path = {source.path: source.language for source in sources}
    assert by_path.get("src/b.rs") == "rust"
    assert by_path.get("src/c.cpp") == "cpp"
    assert by_path.get("src/d.jl") == "julia"


def test_scanner_skips_files_of_disabled_languages(tmp_path: Path):
    """With only Python enabled, other languages' files are skipped as not included."""
    _seed_multilang_sources(tmp_path)
    sources, skipped = scan_repository(
        tmp_path, _language_config(DEFAULT_INCLUDE, {"python": {"enabled": True}})
    )
    assert {source.path for source in sources} == {"src/a.py"}
    not_included = {item.path for item in skipped if item.reason == "not_included"}
    assert {"src/b.rs", "src/c.cpp", "src/d.jl"} <= not_included


def test_secret_files_are_skipped_and_never_reach_generated_docs(tmp_path: Path):
    """Secret-named files are not scanned and their contents never appear in generated output."""
    copy_fixture((FIXTURES / "tiny_repo"), tmp_path)
    secret_value = "SUPER-SECRET-TOKEN-DO-NOT-LEAK-12345"
    secret_files = {
        ".env": f"API_KEY={secret_value}\n",
        ".env.production": f"API_KEY={secret_value}\n",
        "credentials.json": f'{{"token": "{secret_value}"}}\n',
        "service_secrets.yaml": f"token: {secret_value}\n",
        # The PEM armour is split so the public-tree secret scan does not flag it.
        "key.pem": f"-----BEGIN PRIVATE {'KEY'}-----\n{secret_value}\n-----END PRIVATE KEY-----\n",
        "deploy.key": f"{secret_value}\n",
    }
    for name, content in secret_files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")

    config = load_config(tmp_path)
    sources, skipped = scan_repository(tmp_path, config)
    assert not set(secret_files) & {source.path for source in sources}
    assert set(secret_files) <= {item.path for item in skipped}

    assert (
        main(["--repo-root", str(tmp_path), "build", "--no-summaries", "--no-index"])
        == 0
    )
    for generated in (tmp_path / ".repo_wiki" / "generated").rglob("*"):
        if generated.is_file():
            assert secret_value not in generated.read_text(
                encoding="utf-8", errors="replace"
            )

    exclude = [str(pattern) for pattern in config["scanner"]["exclude"]]
    for name in secret_files:
        assert matches_any(name, exclude)
    assert matches_pattern("key.pem", "*.pem")
    assert matches_pattern("deploy.key", "*.key")

