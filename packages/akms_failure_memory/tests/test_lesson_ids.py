from __future__ import annotations

import json
from pathlib import Path

import pytest

from akms.tools.node_validator import NodeFrontmatter
from akms_failure_memory.compiler import compile_registry
from akms_failure_memory.config import load_project_config
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.lesson_ids import (
    CROCKFORD_ALPHABET,
    DATED_ID_ATTEMPTS,
    lesson_id_sort_key,
)
from akms_failure_memory.project import render_project_config
from akms_failure_memory.record import add_lesson


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONFIG = PACKAGE_ROOT / "tests/fixtures/project_configs/numerixweave.toml"
REGISTRY = PACKAGE_ROOT / "tests/fixtures/numerixweave_phase1/source_registry.json"
BOTH_PATTERN = r"^(?:L[0-9]{3}|L[0-9]{8}-[0-9a-hjkmnp-tv-z]{4})$"
_ALLOCATION_DATE = "20261027"


def test_new_project_pattern_accepts_both_id_forms() -> None:
    rendered = render_project_config("demo-repo", "demo-failure").decode()
    assert 'id_pattern = "^(?:L[0-9]{3}|L[0-9]{8}-[0-9a-hjkmnp-tv-z]{4})$"' in rendered
    assert "id_style" not in rendered


def test_id_style_is_optional_and_closed() -> None:
    schema = json.loads(
        (PACKAGE_ROOT / "schemas/project-config.schema.json").read_text(
            encoding="utf-8"
        )
    )
    validation = schema["$defs"]["validation"]
    assert "id_style" not in validation["required"]
    assert validation["properties"]["id_style"]["enum"] == ["sequential", "dated"]
    assert validation["additionalProperties"] is False
    assert validation["properties"]["registry_schema_version"]["const"] == 1
    loaded = load_project_config(CONFIG)
    assert "id_style" not in loaded.validation


def test_invalid_id_style_is_rejected(tmp_path: Path) -> None:
    config = _config(tmp_path, pattern=r"^L[0-9]{3}$", id_style="weekly")
    with pytest.raises(FailureMemoryError, match="id_style") as exc_info:
        load_project_config(config)
    assert exc_info.value.code == "invalid_config"


def test_sort_key_orders_legacy_before_dated_and_rejects_other_forms() -> None:
    scrambled = [
        "L20261028-zzzz",
        "L010",
        "L20261027-k3f9",
        "L002",
        "L20261027-a1b2",
        "L001",
    ]
    assert sorted(scrambled, key=lesson_id_sort_key) == [
        "L001",
        "L002",
        "L010",
        "L20261027-a1b2",
        "L20261027-k3f9",
        "L20261028-zzzz",
    ]
    tied = [("first", "L002"), ("second", "L002")]
    assert [
        item[0] for item in sorted(tied, key=lambda item: lesson_id_sort_key(item[1]))
    ] == [
        "first",
        "second",
    ]
    for rejected in ("L20261027-iiii", "L20261027-oooo", "nw-failure-l001", "L"):
        with pytest.raises(FailureMemoryError, match="Unrecognized lesson ID"):
            lesson_id_sort_key(rejected)
    assert set("ilou").isdisjoint(CROCKFORD_ALPHABET)
    assert len(CROCKFORD_ALPHABET) == 32


def test_mixed_registry_compiles_in_sort_key_order(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    config = _config(repo, pattern=BOTH_PATTERN, id_style=None)
    lessons = [
        _lesson("L20261028-zzzz", related=["L001"]),
        _lesson("L002"),
        _lesson(
            "L010",
            related=["L20261028-zzzz", "L001", "L20261027-k3f9"],
            file="tools/shared.py",
        ),
        _lesson("L20261027-k3f9", related=["L010", "L002"]),
        _lesson("L20261027-a1b2"),
        _lesson("L001", file="tools/shared.py"),
    ]
    _write_registry(repo, lessons)
    compilation = compile_registry(load_project_config(config), repo)
    assert [node.lesson_id for node in compilation.nodes] == [
        "L001",
        "L002",
        "L010",
        "L20261027-a1b2",
        "L20261027-k3f9",
        "L20261028-zzzz",
    ]
    by_id = {node.lesson_id: node for node in compilation.nodes}
    assert by_id["L010"].frontmatter["load_with"] == [
        "nw-failure-l001",
        "nw-failure-l20261027-k3f9",
        "nw-failure-l20261028-zzzz",
    ]
    assert by_id["L20261027-k3f9"].frontmatter["load_with"] == [
        "nw-failure-l002",
        "nw-failure-l010",
    ]
    dated = by_id["L20261027-k3f9"]
    assert dated.node_id == "nw-failure-l20261027-k3f9"
    assert NodeFrontmatter.valid_id(dated.node_id) == dated.node_id
    again = compile_registry(load_project_config(config), repo)
    assert [node.lesson_id for node in again.nodes] == [
        node.lesson_id for node in compilation.nodes
    ]
    assert (
        again.nodes[2].frontmatter["load_with"]
        == by_id["L010"].frontmatter["load_with"]
    )


def test_dated_allocation_retries_then_rejects_exhaustion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    config = _config(repo, pattern=BOTH_PATTERN, id_style="dated")
    _write_registry(repo, [_lesson("L20261027-k3f9"), _lesson("L001")])
    draws = iter(["k3f9", "m4n8"])
    monkeypatch.setattr(
        "akms_failure_memory.record._utc_lesson_date", lambda: _ALLOCATION_DATE
    )
    monkeypatch.setattr(
        "akms_failure_memory.record._draw_id_suffix", lambda: next(draws)
    )
    created = add_lesson(
        config_path=config,
        repository_root=repo,
        global_vault=_vault(tmp_path),
        request_path=_request_file(repo, "first.json"),
    )
    assert created["record"]["id"] == "L20261027-m4n8"

    calls = {"n": 0}

    def colliding() -> str:
        calls["n"] += 1
        return "k3f9"

    monkeypatch.setattr("akms_failure_memory.record._draw_id_suffix", colliding)
    before = (repo / "dev/lessons_from_failing.json").read_bytes()
    with pytest.raises(FailureMemoryError, match="unique dated lesson ID") as exc_info:
        add_lesson(
            config_path=config,
            repository_root=repo,
            global_vault=_vault(tmp_path),
            request_path=_request_file(repo, "second.json", related=["L001"]),
        )
    assert exc_info.value.code == "id_allocation"
    assert calls["n"] == DATED_ID_ATTEMPTS == 32
    assert (repo / "dev/lessons_from_failing.json").read_bytes() == before


def test_two_dated_allocations_differ_under_injected_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    config = _config(repo, pattern=BOTH_PATTERN, id_style="dated")
    _write_registry(repo, [])
    draws = iter(["k3f9", "a1b2"])
    monkeypatch.setattr(
        "akms_failure_memory.record._utc_lesson_date", lambda: _ALLOCATION_DATE
    )
    monkeypatch.setattr(
        "akms_failure_memory.record._draw_id_suffix", lambda: next(draws)
    )
    vault = _vault(tmp_path)
    first = add_lesson(
        config_path=config,
        repository_root=repo,
        global_vault=vault,
        request_path=_request_file(repo, "first.json"),
    )
    second = add_lesson(
        config_path=config,
        repository_root=repo,
        global_vault=vault,
        request_path=_request_file(
            repo, "second.json", related=[first["record"]["id"]]
        ),
    )
    assert first["record"]["id"] == "L20261027-k3f9"
    assert second["record"]["id"] == "L20261027-a1b2"
    assert first["record"]["id"] != second["record"]["id"]


def test_sequential_allocation_keeps_width_with_or_without_id_style(
    tmp_path: Path,
) -> None:
    absent = _allocate(tmp_path / "absent", id_style=None, pattern=r"^L[0-9]{4}$")
    explicit = _allocate(
        tmp_path / "explicit", id_style="sequential", pattern=r"^L[0-9]{4}$"
    )
    assert absent == explicit == "L0013"
    phase1_absent = _allocate_phase1(tmp_path / "phase1-absent", id_style=None)
    phase1_explicit = _allocate_phase1(
        tmp_path / "phase1-explicit", id_style="sequential"
    )
    assert phase1_absent == phase1_explicit == "L902"


def test_dated_id_is_rejected_by_an_unwidened_pattern(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    config = _config(repo, pattern=r"^L[0-9]{3}$", id_style="dated")
    registry = repo / "dev/lessons_from_failing.json"
    registry.parent.mkdir(parents=True)
    registry.write_bytes(REGISTRY.read_bytes())
    before = registry.read_bytes()
    monkeypatch.setattr(
        "akms_failure_memory.record._utc_lesson_date", lambda: _ALLOCATION_DATE
    )
    monkeypatch.setattr("akms_failure_memory.record._draw_id_suffix", lambda: "k3f9")
    with pytest.raises(FailureMemoryError, match="Malformed lesson ID") as exc_info:
        add_lesson(
            config_path=config,
            repository_root=repo,
            global_vault=_vault(tmp_path),
            request_path=_request_file(repo, "request.json", related=["L900"]),
        )
    assert exc_info.value.code == "registry_id"
    assert registry.read_bytes() == before


def test_sequential_project_rejects_an_existing_dated_id(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    config = _config(repo, pattern=BOTH_PATTERN, id_style="sequential")
    registry = _write_registry(
        repo, [_lesson("L001"), _lesson("L20261027-k3f9", related=["L001"])]
    )
    before = registry.read_bytes()
    with pytest.raises(FailureMemoryError, match="dated lesson ID") as exc_info:
        add_lesson(
            config_path=config,
            repository_root=repo,
            global_vault=_vault(tmp_path),
            request_path=_request_file(repo, "request.json", related=["L001"]),
        )
    assert exc_info.value.code == "registry_id"
    assert registry.read_bytes() == before


def _allocate(root: Path, *, id_style: str | None, pattern: str) -> str:
    config = _config(root, pattern=pattern, id_style=id_style)
    _write_registry(root, [_lesson("L0007"), _lesson("L0012")])
    result = add_lesson(
        config_path=config,
        repository_root=root,
        global_vault=root.parent / f"{root.name}-vault",
        request_path=_request_file(root, "request.json", related=["L0007"]),
    )
    return result["record"]["id"]


def _allocate_phase1(root: Path, *, id_style: str | None) -> str:
    config = _config(root, pattern=r"^L[0-9]{3}$", id_style=id_style)
    registry = root / "dev/lessons_from_failing.json"
    registry.parent.mkdir(parents=True)
    registry.write_bytes(REGISTRY.read_bytes())
    result = add_lesson(
        config_path=config,
        repository_root=root,
        global_vault=root.parent / f"{root.name}-vault",
        request_path=_request_file(root, "request.json", related=["L900"]),
    )
    return result["record"]["id"]


def _config(root: Path, *, pattern: str, id_style: str | None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    text = CONFIG.read_text(encoding="utf-8").replace(
        'id_pattern = "^L[0-9]{3}$"',
        f'id_pattern = "{pattern}"',
    )
    if id_style is not None:
        text = text.replace(
            f'id_pattern = "{pattern}"\n',
            f'id_pattern = "{pattern}"\nid_style = "{id_style}"\n',
        )
    path = root / "failure-memory.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _write_registry(root: Path, lessons: list[dict]) -> Path:
    path = root / "dev/lessons_from_failing.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "_field_spec": {
            "id": "Stable lesson identifier.",
            "location": "Repository location for the failure.",
            "found_by": "Discovery mechanism and trigger.",
            "related": "Related lesson identifiers.",
        },
        "lessons": lessons,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _lesson(
    lesson_id: str,
    *,
    related: list[str] | None = None,
    file: str = "tools/demo.py",
) -> dict:
    return {
        "id": lesson_id,
        "date_found": "2026-08-11",
        "date_found_precision": "exact",
        "date_fixed": "2026-08-11",
        "date_fixed_precision": "exact",
        "location": {
            "area": "tool",
            "package": "demo",
            "module": "demo.module",
            "file": file,
            "symbol": "",
            "line_hint": f"topic {lesson_id}",
        },
        "found_by": {"type": "test", "trigger": "recorded during a test"},
        "symptom": "Observed failure.",
        "root_cause": "Known cause.",
        "fix": "Known fix.",
        "prevention": "Do not repeat this failure.",
        "references": {"commit": "abc123", "issue": "", "pr": "", "plan": ""},
        "related": [] if related is None else related,
    }


def _request_file(root: Path, name: str, *, related: list[str] | None = None) -> Path:
    request = _lesson("ignored", related=related)
    del request["id"]
    path = root / name
    path.write_text(json.dumps(request), encoding="utf-8")
    return path


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "global-vault"
    vault.mkdir(exist_ok=True)
    return vault
