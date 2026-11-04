import json
from pathlib import Path

from akms.repo_wiki.cli import main
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
    # Below the root: the default ``**/*.py``-style includes do match these.
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
    assert {source.path for source in sources} == {
        "src/app.py",
        ".repo_wiki/config.yaml",
    }
    excluded = {item.path for item in skipped if item.reason == "excluded"}
    assert SECRET_PATHS | {"private"} <= excluded  # private/** prunes the dir
    assert "build" in excluded  # the default build/** prune still applies

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
