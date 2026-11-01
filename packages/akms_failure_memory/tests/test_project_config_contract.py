from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pytest

from akms_failure_memory.config import (
    is_version_specifier,
    load_project_config,
    version_pin_matches,
)
from akms_failure_memory.errors import FailureMemoryError


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PACKAGE_ROOT / "tests/fixtures/project_configs"


def test_project_config_schema_is_closed_and_versioned() -> None:
    schema = json.loads(
        (PACKAGE_ROOT / "schemas/project-config.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema["properties"]["schema_version"]["const"] == (
        "failure-memory-project/v1"
    )
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["paths"]["additionalProperties"] is False
    assert schema["$defs"]["toolchain"]["additionalProperties"] is False


def test_two_project_fixtures_have_distinct_authorities_and_policies() -> None:
    first = tomllib.loads((FIXTURES / "numerixweave.toml").read_text(encoding="utf-8"))
    second = tomllib.loads(
        (FIXTURES / "second_project.toml").read_text(encoding="utf-8")
    )

    assert (
        first["schema_version"]
        == second["schema_version"]
        == ("failure-memory-project/v1")
    )
    assert first["repository_id"] != second["repository_id"]
    assert first["node_namespace"] != second["node_namespace"]
    assert first["paths"]["registry"] != second["paths"]["registry"]
    assert first["generated"]["lessons"] == "committed"
    assert second["generated"]["lessons"] == "disposable"
    assert (
        first["promotion"]["mode"]
        == second["promotion"]["mode"]
        == ("manual-human-approved")
    )


def test_generic_contract_contains_no_consumer_identity() -> None:
    generic = (
        (PACKAGE_ROOT / "schemas/project-config.schema.json").read_text(
            encoding="utf-8"
        )
        + (
            PACKAGE_ROOT.parents[1] / "docs/reference/failure-memory/internals.md"
        ).read_text(encoding="utf-8")
    ).lower()
    assert "nw-failure" not in generic


@pytest.mark.parametrize("key", ["akms_version", "repo2md_version"])
@pytest.mark.parametrize("value", ["0.3.2", ">=0.3.2,<0.4", "~=0.2", "!=0.3.0"])
def test_toolchain_version_pin_accepts_a_version_or_a_specifier_set(
    tmp_path: Path, key: str, value: str
) -> None:
    config = load_project_config(_with_pin(tmp_path, key, f'"{value}"'))
    # The text is kept as written, so the config fingerprint does not move.
    assert config.toolchain[key] == value


@pytest.mark.parametrize("key", ["akms_version", "repo2md_version"])
@pytest.mark.parametrize(
    "value",
    ['"not-a-version"', '">=0.3.2,<<0.4"', '"0.3.2,0.4"', '">= banana"', '""', "3"],
)
def test_invalid_toolchain_version_pin_fails_validation(
    tmp_path: Path, key: str, value: str
) -> None:
    with pytest.raises(FailureMemoryError) as caught:
        load_project_config(_with_pin(tmp_path, key, value))
    assert caught.value.code == "invalid_config"
    assert f"toolchain.{key}" in str(caught.value)


@pytest.mark.parametrize(
    ("pin", "installed", "matches"),
    [
        ("0.3.2", "0.3.2", True),
        ("0.3.2", "0.3.3", False),
        (">=0.3.2,<0.4", "0.3.2", True),
        (">=0.3.2,<0.4", "0.3.9", True),
        (">=0.3.2,<0.4", "0.4.0", False),
        (">=0.3.2,<0.4", "0.4.0rc1", False),
        (">=0.3.2,<0.4", "0.3.1", False),
        (">=0.3.2,<0.4", "not a version", False),
    ],
)
def test_version_pin_matches(pin: str, installed: str, matches: bool) -> None:
    assert version_pin_matches(pin, installed) is matches


@pytest.mark.parametrize(
    ("pin", "specifier"),
    [
        ("0.3.2", False),
        ("1.0.0rc1", False),
        ("0.3.2.post1", False),
        (">=0.3.2", True),
        ("<0.4", True),
        ("==0.3.2", True),
        ("!=0.3.2", True),
        ("~=0.3", True),
        ("0.3.2,0.4", True),
    ],
)
def test_version_pin_is_a_specifier_when_it_contains_an_operator(
    pin: str, specifier: bool
) -> None:
    assert is_version_specifier(pin) is specifier


def _with_pin(tmp_path: Path, key: str, value: str) -> Path:
    text = (FIXTURES / "numerixweave.toml").read_text(encoding="utf-8")
    text, count = re.subn(
        rf"^{key} = .*$", f"{key} = {value}", text, flags=re.MULTILINE
    )
    assert count == 1
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path
