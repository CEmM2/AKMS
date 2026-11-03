"""`mirror_provider = "builtin"`: mirrors from the exporter shipped in akms."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from akms_failure_memory.config import load_project_config
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.project import init_project, render_project_config
from akms_failure_memory.provider import _input_fingerprints
from akms_failure_memory.refresh import preflight, refresh_project

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
GENERATED_AT = "2026-01-01T00:00:00+00:00"
_REPO2MD_KEYS = (
    "repo2md_command",
    "repo2md_version",
    "repo2md_export_schema_version",
    "repo2md_fixture_sha256",
    "repo2md_commit",
    "repo2md_dirty_policy",
)


def _init(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "demo.py").write_text(
        '"""Demo."""\n\n\ndef answer() -> int:\n    """Return 42."""\n    return 42\n',
        encoding="utf-8",
    )
    result = init_project(
        repository_root=repo,
        config_path=".failure-memory/config.toml",
        repository_id="demo-repo",
        node_namespace="demo-failure",
    )
    vault = tmp_path / "vault"
    vault.mkdir()
    return repo, repo / result["config"], vault


def _write_config(tmp_path: Path, toolchain_edit) -> Path:
    data = render_project_config("demo-repo", "demo-failure").decode("utf-8")
    path = tmp_path / "config.toml"
    path.write_text(toolchain_edit(data), encoding="utf-8")
    return path


def test_init_writes_builtin_without_repo2md_keys() -> None:
    rendered = render_project_config("demo-repo", "demo-failure").decode("utf-8")
    toolchain = tomllib.loads(rendered)["toolchain"]

    assert toolchain["mirror_provider"] == "builtin"
    assert not any(key in toolchain for key in _REPO2MD_KEYS)


def test_builtin_config_loads(tmp_path: Path) -> None:
    config = load_project_config(_write_config(tmp_path, lambda text: text))

    assert config.mirror_provider == "builtin"


def test_absent_provider_is_repo2md_and_requires_its_keys(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path, lambda text: text.replace('mirror_provider = "builtin"\n', "")
    )

    with pytest.raises(FailureMemoryError) as error:
        load_project_config(path)

    assert error.value.code == "invalid_config"
    assert "repo2md_commit" in str(error.value)


def test_unknown_provider_is_rejected(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        lambda text: text.replace(
            'mirror_provider = "builtin"', 'mirror_provider = "legacy"'
        ),
    )

    with pytest.raises(FailureMemoryError) as error:
        load_project_config(path)

    assert error.value.code == "invalid_config"


def test_json_schema_follows_the_provider() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    import json

    schema = json.loads(
        (PACKAGE_ROOT / "schemas/project-config.schema.json").read_text(
            encoding="utf-8"
        )
    )
    rendered = render_project_config("demo-repo", "demo-failure").decode("utf-8")
    config = tomllib.loads(rendered)
    jsonschema.validate(config, schema)

    del config["toolchain"]["mirror_provider"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(config, schema)


def test_preflight_needs_no_external_repo_wiki(tmp_path: Path, monkeypatch) -> None:
    repo, config_path, _ = _init(tmp_path)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))

    result = preflight(config=load_project_config(config_path), repository_root=repo)

    assert result["mirror"]["provider"] == "builtin"
    assert result["mirror"]["export_schema_version"] == 1
    assert "repo2md" not in result
    assert not any(a["code"].startswith("repo2md") for a in result["advisories"])


@pytest.mark.integration
def test_refresh_all_writes_a_dot_knowledge_mirror_the_graph_loads(
    tmp_path: Path,
) -> None:
    repo, config_path, vault = _init(tmp_path)

    result = refresh_project(
        action="all",
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
        generated_at=GENERATED_AT,
    )

    mirror = result["stages"]["mirror"]
    assert mirror["provider"] == "builtin"
    assert mirror["files_processed"] == 1
    assert (repo / ".knowledge/code-mirror/src/demo.md").is_file()
    assert not (repo / "knowledge").exists()
    assert result["stages"]["graph"]["nodes"] == 1

    config = load_project_config(config_path)
    fingerprints = _input_fingerprints(config, repo)
    assert "repo2md_fixture_sha256" not in fingerprints
    assert set(fingerprints) == {
        "config_sha256",
        "graph_sha256",
        "routes_sha256",
        "toolchain_sha256",
    }
