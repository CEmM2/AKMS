from pathlib import Path

import pytest

from akms.repo_wiki.cli import main
from akms.repo_wiki.config import (
    DEFAULT_EXCLUDE_PATTERNS,
    SECRET_EXCLUDE_PATTERNS,
    TOOL_STATE_EXCLUDE_PATTERNS,
    default_config,
    effective_excludes,
    init_repo_wiki,
    load_config,
)
from akms.repo_wiki.simple_yaml import dump_yaml, load_yaml

# The ``scanner.exclude`` list that ``init`` wrote before user patterns extended
# the defaults. Pinned literally: existing configs carry exactly this list.
PRE_EXTEND_INIT_EXCLUDE = [
    ".git/**",
    ".repo_wiki/generated/**",
    ".repo_wiki/index/**",
    ".venv/**",
    "venv/**",
    "env/**",
    "__pycache__/**",
    ".mypy_cache/**",
    ".pytest_cache/**",
    "node_modules/**",
    "dist/**",
    "build/**",
    "*.egg-info/**",
    "data/**",
    "outputs/**",
    "checkpoints/**",
    "wandb/**",
    ".env",
    ".env.*",
    "*.env",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*_secret",
    "*_secret.*",
    "*_secrets",
    "*_secrets.*",
    "*.secret",
    "*.secrets",
    "secrets.yaml",
    "secrets.yml",
    "secrets.json",
    "credentials",
    "credentials.*",
    "credentials.json",
    "credentials.yaml",
    "credentials.yml",
    "id_rsa",
    "id_ed25519",
    "id_dsa",
    "id_ecdsa",
    ".netrc",
    "*.netrc",
]


# What a fresh init config applies: the fixed tool-state set, the ordinary
# defaults, then the secret set.
FRESH_EFFECTIVE = [
    ".git",
    ".git/**",
    ".repo_wiki/**",
    ".repo_wiki/generated/**",
    ".repo_wiki/index/**",
    ".repo2md-export.lock",
    ".repo2md-export-*.lock",
    *(p for p in PRE_EXTEND_INIT_EXCLUDE if not p.startswith((".git", ".repo_wiki"))),
]


def _write_config(root: Path, text: str) -> None:
    path = root / ".repo_wiki" / "config.yaml"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _block_list(key: str, items: list[str], indent: int = 2) -> str:
    pad = " " * indent
    return f"{pad}{key}:\n" + "".join(f"{pad}  - {item}\n" for item in items)


def test_init_creates_deterministic_config(tmp_path: Path):
    init_repo_wiki(tmp_path)
    config_path = tmp_path / ".repo_wiki" / "config.yaml"
    first = config_path.read_text()
    init_repo_wiki(tmp_path)
    assert config_path.read_text() == first
    config = load_config(tmp_path)
    assert config["summaries"]["provider"] == "local"
    assert config["summaries"]["allow_source_code_upload"] is False
    assert ".env" in effective_excludes(config)


def test_yaml_nested_duplicate_keys_and_single_quoted_scalars():
    data = load_yaml(
        """
        first:
          include:
            - src/**
        second:
          include:
            - tests/**
          label: 'Bob''s config'
        """
    )

    assert data["first"]["include"] == ["src/**"]
    assert data["second"]["include"] == ["tests/**"]
    assert data["second"]["label"] == "Bob's config"


def test_default_config_is_private_and_local(tmp_path: Path):
    """No default config key about upload or remote operation is enabled."""
    config = load_config(tmp_path)
    assert config["summaries"]["provider"] in {"none", "local"}
    assert config["summaries"]["allow_source_code_upload"] is False

    def enabled_remote_keys(value: object, path: str = "") -> list[str]:
        found: list[str] = []
        if isinstance(value, dict):
            for key, item in value.items():
                name = f"{path}.{key}" if path else str(key)
                if (
                    isinstance(key, str)
                    and ("upload" in key.lower() or "remote" in key.lower())
                    and item
                ):
                    found.append(name)
                found.extend(enabled_remote_keys(item, name))
        return found

    assert enabled_remote_keys(config) == []
    assert default_config(tmp_path)["summaries"]["provider"] == "local"


def test_heuristic_edge_expansion_defaults_on_and_is_configurable(tmp_path: Path):
    """retrieval.expand_heuristic_edges defaults to true, can be set false, and fills in when absent."""
    assert default_config()["retrieval"]["expand_heuristic_edges"] is True

    config_file = tmp_path / ".repo_wiki" / "config.yaml"
    config_file.parent.mkdir()
    config_file.write_text(
        "retrieval:\n  expand_heuristic_edges: false\n", encoding="utf-8"
    )
    assert load_config(tmp_path)["retrieval"]["expand_heuristic_edges"] is False

    config_file.write_text("retrieval:\n  top_k_initial: 20\n", encoding="utf-8")
    assert load_config(tmp_path)["retrieval"]["expand_heuristic_edges"] is True


def test_stats_reports_uninitialised_until_init_creates_the_wiki(
    tmp_path: Path, capsys
):
    assert main(["--repo-root", str(tmp_path), "stats"]) == 0
    assert "Initialized: False" in capsys.readouterr().out
    assert main(["--repo-root", str(tmp_path), "init"]) == 0
    assert (tmp_path / ".repo_wiki" / "config.yaml").exists()
    assert (tmp_path / ".repo_wiki" / "overlays").is_dir()
    assert (tmp_path / ".repo_wiki" / "SPEC.md").exists()
    assert main(["--repo-root", str(tmp_path), "stats"]) == 0
    assert "Initialized: True" in capsys.readouterr().out


def test_init_config_round_trips_to_the_built_in_excludes(tmp_path: Path):
    """A fresh init config applies exactly the exclude set init used to write out."""
    init_repo_wiki(tmp_path)
    text = (tmp_path / ".repo_wiki" / "config.yaml").read_text(encoding="utf-8")
    assert text.startswith("# repo-wiki configuration")
    assert "scanner.exclude adds patterns" in text
    assert "scanner.include replaces the default include list" in text
    written = load_yaml(text)["scanner"]
    assert "exclude" not in written
    assert written["use_default_excludes"] is True

    config = load_config(tmp_path)
    effective = effective_excludes(config)
    assert effective == FRESH_EFFECTIVE
    assert effective == [
        *TOOL_STATE_EXCLUDE_PATTERNS,
        *DEFAULT_EXCLUDE_PATTERNS,
        *SECRET_EXCLUDE_PATTERNS,
    ]
    # The effective set only grew: every pattern older inits wrote still applies.
    assert set(PRE_EXTEND_INIT_EXCLUDE) <= set(effective)


def test_copied_out_default_list_keeps_the_same_effective_excludes(tmp_path: Path):
    """An existing config holding the old full default list adds nothing to it."""
    _write_config(
        tmp_path, "scanner:\n" + _block_list("exclude", PRE_EXTEND_INIT_EXCLUDE)
    )
    assert effective_excludes(load_config(tmp_path)) == FRESH_EFFECTIVE


def test_user_exclude_extends_the_defaults_in_stable_order(tmp_path: Path):
    _write_config(
        tmp_path,
        "scanner:\n" + _block_list("exclude", ["private/**", ".git/**", "notes/**"]),
    )
    first = effective_excludes(load_config(tmp_path))
    assert first == [*FRESH_EFFECTIVE, "private/**", "notes/**"]
    assert effective_excludes(load_config(tmp_path)) == first


def test_use_default_excludes_false_keeps_tool_state_and_secrets(tmp_path: Path):
    _write_config(
        tmp_path,
        "scanner:\n  use_default_excludes: false\n"
        + _block_list("exclude", ["private/**"]),
    )
    config = load_config(tmp_path)
    assert effective_excludes(config) == [
        *TOOL_STATE_EXCLUDE_PATTERNS,
        *SECRET_EXCLUDE_PATTERNS,
        "private/**",
    ]
    assert "data/**" not in effective_excludes(config)


def test_custom_output_dir_is_tool_state(tmp_path: Path):
    _write_config(tmp_path, "generation:\n  output_dir: docs/wiki\n")
    effective = effective_excludes(load_config(tmp_path))
    assert effective[len(TOOL_STATE_EXCLUDE_PATTERNS)] == "docs/wiki/**"
    for unsafe in ("/abs/wiki", "../outside", "."):
        config = {"generation": {"output_dir": unsafe}, "scanner": {}}
        assert effective_excludes(config) == FRESH_EFFECTIVE


def test_tool_state_can_be_left_out_for_overlays():
    patterns = effective_excludes({}, tool_state=False)
    assert not set(TOOL_STATE_EXCLUDE_PATTERNS) & set(patterns)
    assert set(SECRET_EXCLUDE_PATTERNS) <= set(patterns)


def test_secret_set_survives_any_raw_config():
    """Callers that skip load_config still get the secret set."""
    for scanner in (
        {},
        {"exclude": []},
        {"exclude": ["only/**"], "use_default_excludes": False},
    ):
        patterns = effective_excludes({"scanner": scanner})
        assert set(SECRET_EXCLUDE_PATTERNS) <= set(patterns)
        assert set(TOOL_STATE_EXCLUDE_PATTERNS) <= set(patterns)
    assert set(SECRET_EXCLUDE_PATTERNS) <= set(effective_excludes({}))


def test_include_still_replaces_the_default(tmp_path: Path):
    _write_config(tmp_path, "scanner:\n" + _block_list("include", ["src/**"]))
    assert load_config(tmp_path)["scanner"]["include"] == ["src/**"]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            "scanner:\n  use_default_excludes: no\n",
            "scanner.use_default_excludes must be true or false",
        ),
        (
            "scanner:\n  use_default_excludes: 1\n",
            "scanner.use_default_excludes must be true or false",
        ),
        ("scanner:\n  exclude: private/**\n", "scanner.exclude must be a list"),
        ("scanner:\n  exclude: ['private/**']\n", "scanner.exclude must be a list"),
        ("scanner:\n  include: src/**\n", "scanner.include must be a list"),
    ],
)
def test_invalid_scanner_values_fail_loading(tmp_path: Path, text: str, message: str):
    _write_config(tmp_path, text)
    with pytest.raises(ValueError, match=message):
        load_config(tmp_path)


def test_empty_exclude_forms_mean_no_additions(tmp_path: Path):
    for text in ("scanner:\n  exclude: []\n", "scanner:\n  exclude:\n"):
        _write_config(tmp_path, text)
        assert effective_excludes(load_config(tmp_path)) == FRESH_EFFECTIVE


def test_yaml_empty_list_round_trips():
    data = {"scanner": {"exclude": [], "include": ["a"]}}
    assert dump_yaml(data) == "scanner:\n  exclude: []\n  include:\n    - a\n"
    assert load_yaml(dump_yaml(data)) == data
