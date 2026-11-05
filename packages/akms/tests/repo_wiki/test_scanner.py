import json
import subprocess
from pathlib import Path

import pytest

from akms.repo_wiki.cli import main
from akms.repo_wiki.code_graph import GraphUnavailableError, load_code_graph
from akms.repo_wiki.config import default_config, effective_excludes, load_config
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

    exclude = effective_excludes(config)
    for name in secret_files:
        assert matches_any(name, exclude)
    assert matches_pattern("key.pem", "*.pem")
    assert matches_pattern("deploy.key", "*.key")


SECRET_TOKEN = "SECRET-TOKEN-MUST-NOT-LEAK-67890"


def _seed_secret_repo(root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text('"""App."""\n\nVALUE = 1\n')
    (root / "private").mkdir()
    (root / "private" / "notes.py").write_text(f'NOTE = "{SECRET_TOKEN}"\n')
    (root / "build").mkdir()
    (root / "build" / "generated.py").write_text("BUILT = 1\n")
    (root / "src" / "secrets.yaml").write_text(f"token: {SECRET_TOKEN}\n")
    (root / "src" / "db_secret.py").write_text(f'TOKEN = "{SECRET_TOKEN}"\n')
    (root / "conf").mkdir()
    (root / "conf" / "credentials.toml").write_text(f'token = "{SECRET_TOKEN}"\n')


def _write_scanner_config(root: Path, body: str) -> None:
    (root / ".repo_wiki").mkdir(exist_ok=True)
    (root / ".repo_wiki" / "config.yaml").write_text(
        "scanner:\n" + body, encoding="utf-8"
    )


SECRET_PATHS = {"src/secrets.yaml", "src/db_secret.py", "conf/credentials.toml"}


def test_user_exclude_adds_to_defaults_and_keeps_secrets_out(tmp_path: Path, capsys):
    """A custom exclude list no longer drops the built-in or secret patterns."""
    _seed_secret_repo(tmp_path)
    _write_scanner_config(tmp_path, "  exclude:\n    - private/**\n")

    sources, skipped = scan_repository(tmp_path, load_config(tmp_path))
    assert {source.path for source in sources} == {"src/app.py"}
    excluded = {item.path for item in skipped if item.reason == "excluded"}
    assert SECRET_PATHS | {"private"} <= excluded  # private/** prunes the dir
    assert "build" in excluded  # the default build/** prune still applies
    assert ".repo_wiki" in excluded  # tool state, config.yaml included

    assert main(["--repo-root", str(tmp_path), "scan", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["exclude"] == effective_excludes(load_config(tmp_path))
    assert {"secrets.yaml", "build/**", "private/**"} <= set(payload["exclude"])

    # End to end: the wiki, the search index and an exported mirror stay clean.
    assert main(["--repo-root", str(tmp_path), "build", "--no-summaries"]) == 0
    assert (
        main(
            [
                "--repo-root",
                str(tmp_path),
                "export-akms",
                "--output",
                "akms-output",
                "--phase",
                "1",
                "--generated-at",
                "2026-03-07T12:00:00+00:00",
                "--full",
            ]
        )
        == 0
    )
    capsys.readouterr()
    manifest = json.loads((tmp_path / ".repo_wiki" / "manifest.json").read_text())
    assert set(manifest["files"]) == {"src/app.py"}
    for written in (tmp_path / ".repo_wiki").rglob("*"):
        if written.is_file() and written.parent.name != "overlays":
            assert SECRET_TOKEN.encode() not in written.read_bytes(), written
    mirrors = [p for p in (tmp_path / "akms-output").rglob("*") if p.is_file()]
    assert mirrors
    for mirror in mirrors:
        assert SECRET_TOKEN.encode() not in mirror.read_bytes(), mirror


def test_use_default_excludes_false_still_skips_secrets(tmp_path: Path):
    _seed_secret_repo(tmp_path)
    _write_scanner_config(tmp_path, "  use_default_excludes: false\n")

    sources, skipped = scan_repository(tmp_path, load_config(tmp_path))
    paths = {source.path for source in sources}
    assert "build/generated.py" in paths  # ordinary defaults dropped
    assert "private/notes.py" in paths
    assert not SECRET_PATHS & paths
    assert SECRET_PATHS <= {item.path for item in skipped if item.reason == "excluded"}


def test_tool_state_is_excluded_whatever_the_config(tmp_path: Path):
    """use_default_excludes: false and an empty include still skip tool state."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("VALUE = 1\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (tmp_path / "vendor" / "lib").mkdir(parents=True)
    # A submodule or worktree has a .git file, not a directory.
    (tmp_path / "vendor" / "lib" / ".git").write_text("gitdir: ../../.git/modules\n")
    (tmp_path / "vendor" / "lib" / "mod.py").write_text("X = 1\n")
    (tmp_path / "vendor" / "nested" / ".git").mkdir(parents=True)
    (tmp_path / "vendor" / "nested" / ".git" / "config").write_text("[core]\n")
    for rel in (
        ".repo_wiki/generated/modules/src.app.md",
        ".repo_wiki/locks/export-akms.lock",
        ".repo_wiki/hooks/post-commit.py",
        ".repo_wiki/overlays/notes.md",
        "wiki-out/page.md",
        "out/.repo2md-export-0123456789abcdef.lock",
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("state\n")
    _write_scanner_config(
        tmp_path,
        "  use_default_excludes: false\n  include: []\n"
        "generation:\n  output_dir: wiki-out\n",
    )

    sources, skipped = scan_repository(tmp_path, load_config(tmp_path))
    assert {source.path for source in sources} == {"src/app.py", "vendor/lib/mod.py"}
    excluded = {item.path for item in skipped if item.reason == "excluded"}
    assert {".git", ".repo_wiki", "vendor/lib/.git", "vendor/nested/.git"} <= excluded
    assert {"wiki-out", "out/.repo2md-export-0123456789abcdef.lock"} <= excluded


def test_raw_scanner_config_cannot_disable_secret_patterns(tmp_path: Path):
    """The scanner enforces the secret set even for a config built by hand."""
    _seed_secret_repo(tmp_path)
    (tmp_path / ".env").write_text(f"KEY={SECRET_TOKEN}\n")
    (tmp_path / "conf" / ".env.local").write_text(f"KEY={SECRET_TOKEN}\n")
    config = {
        "scanner": {
            "include": [],
            "exclude": [],
            "use_default_excludes": False,
            "respect_gitignore": False,
        }
    }
    sources, _ = scan_repository(tmp_path, config)
    paths = {source.path for source in sources}
    assert not (SECRET_PATHS | {".env", "conf/.env.local"}) & paths
    assert {"src/app.py", "private/notes.py", "build/generated.py"} <= paths


def _seed_with_outside_link(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    outside = tmp_path / "outside"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("VALUE = 1\n")
    outside.mkdir()
    (outside / "data.py").write_text("SECRET = 2\n")
    (root / "results").symlink_to(outside, target_is_directory=True)
    return root, outside


def test_scanner_skips_symlink_pointing_outside_root(tmp_path: Path):
    root, _ = _seed_with_outside_link(tmp_path)

    sources, skipped = scan_repository(root, default_config(root))

    assert [source.path for source in sources] == ["src/app.py"]
    assert {(item.path, item.reason) for item in skipped} >= {("results", "symlink")}


def test_scanner_reports_ignored_outside_symlink_as_excluded(tmp_path: Path):
    root, _ = _seed_with_outside_link(tmp_path)
    (root / ".gitignore").write_text("results\n")

    sources, skipped = scan_repository(root, default_config(root))

    assert [source.path for source in sources] == ["src/app.py"]
    assert ("results", "excluded") in {(item.path, item.reason) for item in skipped}


def test_scanner_does_not_follow_symlinks_inside_root(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("VALUE = 1\n")
    (tmp_path / "alias").symlink_to(tmp_path / "src", target_is_directory=True)
    (tmp_path / "link.py").symlink_to(tmp_path / "src" / "app.py")

    sources, skipped = scan_repository(tmp_path, default_config(tmp_path))

    assert [source.path for source in sources] == ["src/app.py"]
    reasons = {(item.path, item.reason) for item in skipped}
    assert {("alias", "symlink"), ("link.py", "symlink")} <= reasons


def test_scanner_skips_broken_symlink(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("VALUE = 1\n")
    (tmp_path / "src" / "dangling.py").symlink_to(tmp_path / "missing.py")

    sources, skipped = scan_repository(tmp_path, default_config(tmp_path))

    assert [source.path for source in sources] == ["src/app.py"]
    reasons = {(item.path, item.reason) for item in skipped}
    assert ("src/dangling.py", "symlink") in reasons


def test_export_akms_succeeds_beside_symlink_outside_root(tmp_path: Path, capsys):
    root, _ = _seed_with_outside_link(tmp_path)
    argv = ["--repo-root", str(root), "export-akms", "--output", "akms-output"]
    argv += ["--phase", "1", "--generated-at", "2026-03-07T12:00:00+00:00"]

    assert main([*argv, "--full", "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["errors"] == []
    assert [entry["source_path"] for entry in payload["written"]] == ["src/app.py"]


def test_change_analysis_and_graph_staleness_use_the_same_excludes(tmp_path: Path):
    """``changes`` and the code graph's new-source check skip what build skips."""
    from akms.repo_wiki.changes import _extractable
    from akms.repo_wiki.code_graph import _new_sources

    _seed_secret_repo(tmp_path)
    (tmp_path / ".repo_wiki").mkdir()
    (tmp_path / ".repo_wiki" / "hooks").mkdir()
    (tmp_path / ".repo_wiki" / "hooks" / "hook.py").write_text("X = 1\n")
    config = load_config(tmp_path)

    assert _extractable("src/app.py", config) == "python"
    for rel in ("src/db_secret.py", "build/generated.py", ".repo_wiki/hooks/hook.py"):
        assert _extractable(rel, config) is None, rel

    new = set(_new_sources(tmp_path, config, set()))
    assert {"src/app.py", "private/notes.py"} <= new
    assert not {"src/db_secret.py", "build/generated.py"} & new
    assert not any(path.startswith(".repo_wiki/") for path in new)


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        ("a.py", "**/*.py", True),
        ("src/a.py", "**/*.py", True),
        ("src/deep/a.py", "**/*.py", True),
        ("src/a.py", "src/**/*.py", True),
        ("src/deep/a.py", "src/**/*.py", True),
        ("lib/a.py", "src/**/*.py", False),
        ("a.py", "src/**/*.py", False),
        ("a/b/c.py", "**/b/**/*.py", True),
        ("b/c.py", "**/b/**/*.py", True),
        ("c.py", "**/b/**/*.py", False),
        ("generated/x.py", "**/generated/**", True),
        ("src/generated/x.py", "**/generated/**", True),
        ("a.txt", "**/*.py", False),
        # Not a directory segment: stays an ordinary glob.
        ("a.py", "x**/*.py", False),
    ],
)
def test_a_double_star_segment_can_match_no_directory(path, pattern, expected):
    assert matches_pattern(path, pattern) is expected


def test_default_includes_reach_root_files_of_every_type(tmp_path: Path):
    names = ["setup.py", "README.md", "pyproject.toml", "ci.yaml", "mkdocs.yml"]
    for name in [*names, "notes.txt"]:
        (tmp_path / name).write_text("x = 1\n", encoding="utf-8")
    sources, skipped = scan_repository(tmp_path, load_config(tmp_path))
    assert sorted(source.path for source in sources) == sorted(names)
    assert {item.path: item.reason for item in skipped}["notes.txt"] == "not_included"


def test_enabled_language_globs_reach_root_files(tmp_path: Path):
    (tmp_path / "lib.rs").write_text("fn main() {}\n", encoding="utf-8")
    config = load_config(tmp_path)
    assert "lib.rs" not in {s.path for s in scan_repository(tmp_path, config)[0]}
    config["languages"] = {"rust": {"enabled": True}}
    assert "lib.rs" in {s.path for s in scan_repository(tmp_path, config)[0]}


def test_a_custom_include_still_replaces_and_reaches_the_root(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# b\n", encoding="utf-8")
    _write_scanner_config(tmp_path, '  include:\n    - "**/*.py"\n')
    sources, _ = scan_repository(tmp_path, load_config(tmp_path))
    assert [source.path for source in sources] == ["a.py"]


def test_an_exclude_reaches_the_root_too(tmp_path: Path):
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("x = 1\n", encoding="utf-8")
    _write_scanner_config(tmp_path, '  exclude:\n    - "**/a.py"\n')
    sources, skipped = scan_repository(tmp_path, load_config(tmp_path))
    assert [source.path for source in sources] == ["b.py"]
    assert {item.path: item.reason for item in skipped}["a.py"] == "excluded"


ROOT_SECRET_FILES = (
    ".env",
    ".env.local",
    "prod.env",
    "secrets.yaml",
    "secrets.yml",
    "secrets.json",
    "app.secrets",
    "db_secret.py",
    "db_secret.toml",
    "api_secrets.yaml",
    "credentials.toml",
    "credentials.yaml",
    "credentials.py",
    "tls.key",
    "tls.pem",
)


@pytest.mark.parametrize("use_default_excludes", [True, False])
def test_root_secret_files_stay_excluded_at_every_include(
    tmp_path: Path, use_default_excludes: bool
):
    for name in ROOT_SECRET_FILES:
        (tmp_path / name).write_text(f"token = '{SECRET_TOKEN}'\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    _write_scanner_config(
        tmp_path,
        f"  use_default_excludes: {str(use_default_excludes).lower()}\n"
        '  include:\n    - "**/*"\n',
    )
    sources, skipped = scan_repository(tmp_path, load_config(tmp_path))
    assert "app.py" in {source.path for source in sources}
    assert not set(ROOT_SECRET_FILES) & {source.path for source in sources}
    reasons = {item.path: item.reason for item in skipped}
    assert all(reasons[name] == "excluded" for name in ROOT_SECRET_FILES)


def test_root_secret_files_never_reach_the_graph_or_mirrors(tmp_path: Path):
    for name in ROOT_SECRET_FILES:
        (tmp_path / name).write_text(f"token = '{SECRET_TOKEN}'\n", encoding="utf-8")
    (tmp_path / "app.py").write_text('"""App."""\n\nVALUE = 1\n', encoding="utf-8")
    assert main(["--repo-root", str(tmp_path), "build", "--no-summaries"]) == 0
    assert (
        main(
            [
                "--repo-root",
                str(tmp_path),
                "export-akms",
                "--output",
                "out",
                "--phase",
                "1",
                "--generated-at",
                "2026-03-07T12:00:00+00:00",
            ]
        )
        == 0
    )
    written = [
        path
        for root in (tmp_path / ".repo_wiki", tmp_path / "out")
        for path in root.rglob("*")
        if path.is_file()
    ]
    assert any(path.name == "app.md" for path in written)
    for path in written:
        assert SECRET_TOKEN.encode() not in path.read_bytes()


@pytest.mark.parametrize(
    "name", ["setup.py", "conftest.py", "__main__.py", "__init__.py"]
)
def test_a_root_python_file_gets_a_graph_node_and_a_mirror(tmp_path: Path, name: str):
    (tmp_path / name).write_text(
        "def helper():\n    return 1\n\n\ndef run():\n    return helper()\n",
        encoding="utf-8",
    )
    assert main(["--repo-root", str(tmp_path), "build", "--no-summaries"]) == 0
    graph = json.loads(
        (tmp_path / ".repo_wiki/generated/symbol_graph.json").read_text(
            encoding="utf-8"
        )
    )
    assert f"python:{name}::run" in graph["nodes"]
    code = load_code_graph(tmp_path).graph
    callers = code.in_edges[f"python:{name}::helper"]
    assert [edge.source for edge in callers] == [f"python:{name}::run"]
    assert (
        main(
            [
                "--repo-root",
                str(tmp_path),
                "export-akms",
                "--output",
                "out",
                "--phase",
                "1",
                "--generated-at",
                "2026-03-07T12:00:00+00:00",
            ]
        )
        == 0
    )
    assert list((tmp_path / "out/.knowledge/code-mirror").glob("*.md"))


def test_a_new_root_python_file_makes_the_graph_stale_and_a_rebuild_clears_it(
    tmp_path: Path,
):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert main(["--repo-root", str(tmp_path), "build", "--no-summaries"]) == 0
    (tmp_path / "new.py").write_text("y = 1\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "new.py"], check=True)
    with pytest.raises(GraphUnavailableError, match="stale"):
        load_code_graph(tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-summaries"]) == 0
    assert "new" in load_code_graph(tmp_path).graph.nodes
