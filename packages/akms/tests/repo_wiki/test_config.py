from pathlib import Path

from akms.repo_wiki.cli import main
from akms.repo_wiki.config import default_config, init_repo_wiki, load_config
from akms.repo_wiki.simple_yaml import load_yaml


def test_init_creates_deterministic_config(tmp_path: Path):
    init_repo_wiki(tmp_path)
    config_path = tmp_path / ".repo_wiki" / "config.yaml"
    first = config_path.read_text()
    init_repo_wiki(tmp_path)
    assert config_path.read_text() == first
    config = load_config(tmp_path)
    assert config["summaries"]["provider"] == "local"
    assert config["summaries"]["allow_source_code_upload"] is False
    assert ".env" in config["scanner"]["exclude"]


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
