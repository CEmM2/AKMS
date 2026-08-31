from __future__ import annotations

import json
import tomllib
from pathlib import Path


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
            PACKAGE_ROOT.parents[1]
            / "docs/reference/failure-memory/internals.md"
        ).read_text(encoding="utf-8")
    ).lower()
    assert "nw-failure" not in generic
