"""Lesson index, record-derived titles and the annotations sidecar."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tomllib
from pathlib import Path
from typing import Any

import pytest

from akms_failure_memory.annotations import validate_annotations
from akms_failure_memory.cli import main
from akms_failure_memory.compiler import compile_registry, run_compiler
from akms_failure_memory.config import load_project_config
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.index_query import query_lesson_index
from akms_failure_memory.lesson_index import first_sentence, record_title
from akms_failure_memory.project import render_project_config
from akms_failure_memory.refresh import refresh_project
from akms_failure_memory.registry_migrate import migrate_registry


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PACK_V1 = PACKAGE_ROOT / "tests/fixtures/consumer_contract/v1"
PACK_V2 = PACKAGE_ROOT / "tests/fixtures/consumer_contract/v2"
GATE = 'lesson_index_version = "failure-lesson-index/v1"\n'
INDEX_JSON = "generated/lesson_index.json"
INDEX_MARKDOWN = "generated/lesson_index.md"


def _enable(config_path: Path) -> None:
    text = config_path.read_text(encoding="utf-8")
    anchor = 'source_hash_suffix = " -->"\n'
    assert text.count(anchor) == 1
    config_path.write_text(text.replace(anchor, anchor + GATE), encoding="utf-8")


def _project(
    tmp_path: Path,
    *,
    gate: bool = True,
    lessons: list[dict[str, Any]] | None = None,
    pack: Path = PACK_V1,
) -> tuple[Path, Path, Path]:
    """Stage the frozen pack's registry and config, optionally gated on."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    shutil.copyfile(pack / "project.toml", repo / "project.toml")
    if pack == PACK_V2:
        shutil.copytree(pack / "lessons", repo / "lessons")
    elif lessons is None:
        shutil.copyfile(pack / "lessons.json", repo / "lessons.json")
    else:
        registry = json.loads((pack / "lessons.json").read_text(encoding="utf-8"))
        registry["lessons"] = lessons
        (repo / "lessons.json").write_text(
            json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    # Read-only compiler modes take the lock but never create its parent.
    (repo / "runtime").mkdir()
    if gate:
        _enable(repo / "project.toml")
    vault = tmp_path / "vault"
    vault.mkdir()
    return repo, repo / "project.toml", vault


def _compile(repo: Path, config: Path, vault: Path, mode: str = "write") -> dict:
    return run_compiler(
        config_path=config, repository_root=repo, global_vault=vault, mode=mode
    )


def _pack_lessons() -> list[dict[str, Any]]:
    return json.loads((PACK_V1 / "lessons.json").read_text(encoding="utf-8"))["lessons"]


def _annotate(path: Path, lessons: dict[str, Any], **categories: str) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "failure-lesson-annotations/v1",
                "categories": categories,
                "lessons": lessons,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes() if path.is_file() else b"/")
    return digest.hexdigest()


# -- configuration gate ------------------------------------------------------


def test_absent_gate_keeps_line_hint_titles_and_writes_no_index(
    tmp_path: Path,
) -> None:
    repo, config, vault = _project(tmp_path, gate=False)
    loaded = load_project_config(config)
    frozen = json.loads((PACK_V1 / "fixture-manifest.json").read_text("utf-8"))

    assert loaded.lesson_index_version is None
    assert "lesson_index_version" not in loaded.canonical_data["compatibility"]
    assert loaded.fingerprint == frozen["project"]["config_fingerprint"]
    _compile(repo, config, vault)
    assert not (repo / INDEX_JSON).exists()
    assert not (repo / INDEX_MARKDOWN).exists()
    frozen_outputs = sorted((PACK_V1 / "generated").rglob("*.*"))
    compiled_outputs = sorted((repo / "generated").rglob("*.*"))
    assert [path.relative_to(repo) for path in compiled_outputs] == [
        path.relative_to(PACK_V1) for path in frozen_outputs
    ]
    for frozen, compiled in zip(frozen_outputs, compiled_outputs, strict=True):
        assert compiled.read_bytes() == frozen.read_bytes()


def test_gate_changes_titles_but_not_node_identity(tmp_path: Path) -> None:
    legacy_repo, legacy_config, _ = _project(tmp_path / "legacy", gate=False)
    repo, config, _ = _project(tmp_path / "gated")
    before = compile_registry(load_project_config(legacy_config), legacy_repo)
    after = compile_registry(load_project_config(config), repo)

    assert [node.node_id for node in before.nodes] == [
        node.node_id for node in after.nodes
    ]
    assert before.adapted_routes == after.adapted_routes
    titles = {node.lesson_id: node.frontmatter["title"] for node in after.nodes}
    assert titles["L002"] == "L002: The scheduler iterated an unordered mapping"
    assert before.nodes[1].frontmatter["title"] == "L002: coactivation source"
    for node in after.nodes:
        assert f"# {node.frontmatter['title']}\n" in node.content
        rest = {k: v for k, v in node.frontmatter.items() if k != "title"}
        legacy = next(item for item in before.nodes if item.node_id == node.node_id)
        assert rest == {k: v for k, v in legacy.frontmatter.items() if k != "title"}


def test_init_writes_the_gate_and_the_schema_accepts_it() -> None:
    rendered = render_project_config("demo-repo", "demo-failure").decode("utf-8")
    data = tomllib.loads(rendered)

    assert data["compatibility"]["lesson_index_version"] == "failure-lesson-index/v1"
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(
        (PACKAGE_ROOT / "schemas/project-config.schema.json").read_text("utf-8")
    )
    jsonschema.validate(data, schema)
    del data["compatibility"]["lesson_index_version"]
    jsonschema.validate(data, schema)
    data["compatibility"]["lesson_index_version"] = "failure-lesson-index/v9"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


@pytest.mark.parametrize("value", ['"failure-lesson-index/v9"', "1", "[]"])
def test_unknown_gate_value_is_rejected(tmp_path: Path, value: str) -> None:
    _, config, _ = _project(tmp_path)
    text = config.read_text(encoding="utf-8")
    config.write_text(
        text.replace('"failure-lesson-index/v1"', value, 1), encoding="utf-8"
    )
    with pytest.raises(FailureMemoryError) as error:
        load_project_config(config)
    assert error.value.code == "schema_version"


# -- titles and card text ----------------------------------------------------


def _lesson(**changes: Any) -> dict[str, Any]:
    lesson = copy.deepcopy(_pack_lessons()[0])
    lesson.update(changes)
    return lesson


@pytest.mark.parametrize(
    ("root_cause", "symptom", "expected"),
    [
        ("The cache key omitted the backend.", "", "The cache key omitted the backend"),
        ("Writes raced; the lock was advisory.", "", "Writes raced"),
        ("A stale key — never invalidated.", "", "A stale key"),
        (
            "When warm, e.g. on rerun, it failed. Later more.",
            "",
            "When warm, e.g. on rerun, it failed",
        ),
        ("", "Repeated commits advanced state.", "Repeated commits advanced state"),
        ("  \n ", "", "exact route conformance"),
    ],
)
def test_record_title_uses_the_first_clause(
    root_cause: str, symptom: str, expected: str
) -> None:
    assert record_title(_lesson(root_cause=root_cause, symptom=symptom)) == expected


def test_record_title_is_capped_at_a_word_boundary() -> None:
    title = record_title(_lesson(root_cause="word " * 60))
    assert len(title) <= 96
    assert title.endswith("word...")


def test_first_sentence_keeps_paths_and_abbreviations() -> None:
    text = "Edit src/a.py, e.g. the loader. Then rerun."
    assert first_sentence(text) == "Edit src/a.py, e.g. the loader."


# -- sidecar and acceptance properties --------------------------------------


def _many_lessons() -> list[dict[str, Any]]:
    template = _pack_lessons()[0]
    lessons = []
    for number in range(1, 31):
        lesson = copy.deepcopy(template)
        lesson["id"] = f"L{number:03d}"
        lesson["location"].update(
            area=("src", "tools", "")[number % 3],
            package=f"pkg{number % 4}",
            module=f"mod{number % 5}",
        )
        lesson["root_cause"] = f"Mechanism number {number}. Second sentence."
        lessons.append(lesson)
    lessons[3]["related"] = ["L001"]
    return lessons


def test_index_is_byte_identical_across_rebuilds(tmp_path: Path) -> None:
    repo, config, vault = _project(tmp_path / "a", lessons=_many_lessons())
    other, other_config, other_vault = _project(tmp_path / "b", lessons=_many_lessons())
    _annotate(
        repo / "lessons.annotations.json", {"L004": {"categories": ["io"]}}, io="I/O"
    )
    shutil.copyfile(
        repo / "lessons.annotations.json", other / "lessons.annotations.json"
    )

    first = _compile(repo, config, vault)
    assert INDEX_JSON in first["added"] and INDEX_MARKDOWN in first["added"]
    snapshot = {
        name: (repo / name).read_bytes() for name in (INDEX_JSON, INDEX_MARKDOWN)
    }
    rebuilt = _compile(repo, config, vault)
    assert rebuilt["added"] == rebuilt["changed"] == rebuilt["stale"] == []
    assert _compile(repo, config, vault, mode="check")["status"] == "clean"
    _compile(other, other_config, other_vault)
    for name, content in snapshot.items():
        assert (repo / name).read_bytes() == content
        assert (other / name).read_bytes() == content
    index = json.loads(snapshot[INDEX_JSON])
    assert (
        index["inputs"]["annotations_sha256"]
        == hashlib.sha256((repo / "lessons.annotations.json").read_bytes()).hexdigest()
    )
    assert index["counts"]["lessons"] == 30
    assert "generated_at" not in snapshot[INDEX_JSON].decode("utf-8")


def test_v1_file_and_v2_directory_index_the_same_cards(tmp_path: Path) -> None:
    v1, v1_config, v1_vault = _project(tmp_path / "v1")
    v2, v2_config, v2_vault = _project(tmp_path / "v2", pack=PACK_V2)
    _compile(v1, v1_config, v1_vault)
    _compile(v2, v2_config, v2_vault)
    left = json.loads((v1 / INDEX_JSON).read_text("utf-8"))
    right = json.loads((v2 / INDEX_JSON).read_text("utf-8"))

    assert left["areas"] == right["areas"]
    assert left["inputs"]["source_schema_version"] == 1
    assert right["inputs"]["source_schema_version"] == 2


def test_every_lesson_is_within_three_expansions_of_the_root(tmp_path: Path) -> None:
    lessons = _many_lessons()
    repo, config, vault = _project(tmp_path, lessons=lessons)
    _compile(repo, config, vault)

    def ask(**selectors: str) -> dict[str, Any]:
        return query_lesson_index(config_path=config, repository_root=repo, **selectors)

    root = ask()
    assert root["level"] == "groups"
    reached: dict[str, int] = {}
    for area in root["areas"]:
        for package in area["packages"]:
            for module in package["modules"]:
                # Expansion 1: a group to its cards.
                cards = ask(
                    area=area["name"], package=package["name"], module=module["name"]
                )
                assert cards["level"] == "cards"
                assert cards["matches"] == module["lessons"]
                for card in cards["areas"][0]["packages"][0]["modules"][0]["cards"]:
                    # Expansion 2: a card to its full record.
                    record = ask(expand=card["id"])
                    assert record["level"] == "record"
                    assert record["card"] == card
                    reached[card["id"]] = 2
    assert sorted(reached) == sorted(lesson["id"] for lesson in lessons)
    assert max(reached.values()) <= 3
    for lesson in lessons:
        assert ask(expand=lesson["id"])["record"] == lesson


def test_cards_carry_the_specified_fields(tmp_path: Path) -> None:
    repo, config, vault = _project(tmp_path)
    _compile(repo, config, vault)
    index = json.loads((repo / INDEX_JSON).read_text("utf-8"))
    card = index["areas"][1]["packages"][0]["modules"][2]["cards"][0]

    assert [area["name"] for area in index["areas"]] == ["docs", "src", "tools"]
    assert card == {
        "id": "L002",
        "node_id": "cc-failure-l002",
        "title": "The scheduler iterated an unordered mapping",
        "trigger": "tests/engine/test_scheduler_order.py::test_stable_order",
        "mechanism": "The scheduler iterated an unordered mapping.",
        "prevention": "tests/engine/test_scheduler_order.py asserts a deterministic "
        "enqueue order.",
        "references": {"plan": "dev/plans/consumer-integration.md"},
        "related": ["L003"],
        "categories": [],
        "superseded_by": None,
    }
    markdown = (repo / INDEX_MARKDOWN).read_text("utf-8")
    assert markdown.startswith("<!-- GENERATED: edit lessons.json -->\n")
    assert f"lesson_index_sha256: {index['fingerprint']}" in markdown


def test_turning_the_gate_off_prunes_the_index(tmp_path: Path) -> None:
    repo, config, vault = _project(tmp_path)
    _compile(repo, config, vault)
    config.write_text(config.read_text("utf-8").replace(GATE, ""), encoding="utf-8")

    check = _compile(repo, config, vault, mode="check")
    assert check["status"] == "drift"
    assert sorted(check["stale"]) == [INDEX_JSON, INDEX_MARKDOWN]
    _compile(repo, config, vault)
    assert not (repo / INDEX_JSON).exists()
    assert not (repo / INDEX_MARKDOWN).exists()


def test_refresh_clean_removes_a_disposable_index(tmp_path: Path) -> None:
    repo, config, vault = _project(tmp_path)
    text = config.read_text("utf-8").replace(
        'lessons = "committed"', 'lessons = "disposable"', 1
    )
    config.write_text(text, encoding="utf-8")
    _compile(repo, config, vault)

    result = refresh_project(
        action="clean", config_path=config, repository_root=repo, global_vault=vault
    )
    assert INDEX_JSON in result["removed"] and INDEX_MARKDOWN in result["removed"]


# -- annotations sidecar -----------------------------------------------------


def test_annotations_surface_on_cards_and_records(tmp_path: Path) -> None:
    repo, config, vault = _project(tmp_path)
    _annotate(
        repo / "lessons.annotations.json",
        {
            "L002": {
                "categories": ["ordering", "nondeterminism"],
                "contradicts": ["L003"],
                "exceptions": ["Insertion-ordered mappings are safe."],
                "applicability": "Schedulers that fan out work.",
            },
            "L001": {"superseded_by": "L005"},
        },
        ordering="Order-dependent behaviour.",
        nondeterminism="Run-to-run variation.",
    )
    registry_before = (repo / "lessons.json").read_bytes()
    _compile(repo, config, vault)

    record = query_lesson_index(config_path=config, repository_root=repo, expand="L002")
    assert record["card"]["categories"] == ["nondeterminism", "ordering"]
    assert record["annotations"] == {
        "categories": ["nondeterminism", "ordering"],
        "contradicts": ["L003"],
        "exceptions": ["Insertion-ordered mappings are safe."],
        "superseded_by": None,
        "applicability": "Schedulers that fan out work.",
    }
    superseded = query_lesson_index(
        config_path=config, repository_root=repo, expand="L001"
    )
    assert superseded["card"]["superseded_by"] == "L005"
    by_category = query_lesson_index(
        config_path=config, repository_root=repo, grep="^ordering$"
    )
    assert by_category["matches"] == 1
    assert (repo / "lessons.json").read_bytes() == registry_before


@pytest.mark.parametrize(
    ("lessons", "code"),
    [
        ({"L999": {}}, "annotation_id"),
        ({"L001": {"contradicts": ["L999"]}}, "annotation_id"),
        ({"L001": {"contradicts": ["L001"]}}, "annotation_id"),
        ({"L001": {"superseded_by": "L999"}}, "annotation_id"),
        (
            {"L001": {"superseded_by": "L002"}, "L002": {"superseded_by": "L001"}},
            "annotation_id",
        ),
        ({"L001": {"categories": ["undeclared"]}}, "annotations_schema"),
        ({"L001": {"severity": "high"}}, "annotations_schema"),
        ({"L001": {"exceptions": ["same", "same"]}}, "annotations_schema"),
    ],
)
def test_invalid_annotations_fail_validation(
    tmp_path: Path, lessons: dict[str, Any], code: str
) -> None:
    repo, config, _ = _project(tmp_path)
    _annotate(repo / "lessons.annotations.json", lessons, io="I/O")

    with pytest.raises(FailureMemoryError) as error:
        run_compiler(config_path=config, repository_root=repo, mode="validate")
    assert error.value.code == code


def test_annotations_schema_version_is_required() -> None:
    with pytest.raises(FailureMemoryError) as error:
        validate_annotations(
            {"schema_version": "v0", "categories": {}, "lessons": {}}, ["L001"]
        )
    assert error.value.code == "annotations_schema"


def test_directory_annotations_do_not_move_the_registry_digest(
    tmp_path: Path,
) -> None:
    repo, config, vault = _project(tmp_path, pack=PACK_V2)
    loaded = load_project_config(config)
    before = compile_registry(loaded, repo)
    _annotate(
        repo / "lessons/_annotations.json", {"L003": {"categories": ["io"]}}, io="I/O"
    )
    after = compile_registry(loaded, repo)

    assert after.source_sha256 == before.source_sha256
    assert [node.content for node in after.nodes] == [
        node.content for node in before.nodes
    ]
    _compile(repo, config, vault)
    index = json.loads((repo / INDEX_JSON).read_text("utf-8"))
    assert index["inputs"]["annotations_sha256"] is not None


def test_registry_migration_carries_the_annotations(tmp_path: Path) -> None:
    repo, config, _ = _project(tmp_path)
    sidecar = repo / "lessons.annotations.json"
    _annotate(sidecar, {"L002": {"categories": ["io"]}}, io="I/O")

    checked = migrate_registry(
        config_path=config, repository_root=repo, to="2", check=True
    )
    assert checked["annotations"] == "lessons/_annotations.json"
    migrated = migrate_registry(config_path=config, repository_root=repo, to="2")
    assert migrated["annotations"] == "lessons/_annotations.json"
    assert (repo / "lessons/_annotations.json").read_bytes() == sidecar.read_bytes()
    assert sidecar.is_file()
    card = query_lesson_index(config_path=config, repository_root=repo, expand="L002")
    assert card["card"]["categories"] == ["io"]


# -- retrieval command -------------------------------------------------------


def test_index_command_is_read_only_and_reports_the_sidecar(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, config, vault = _project(tmp_path)

    def run(*arguments: str) -> dict[str, Any]:
        before = _tree_digest(tmp_path)
        code = main(["index", "--config", str(config), "--repo", str(repo), *arguments])
        assert code == 0
        assert _tree_digest(tmp_path) == before
        return json.loads(capsys.readouterr().out)

    assert run()["sidecar"] == {"path": INDEX_JSON, "status": "absent"}
    _compile(repo, config, vault)
    assert run()["sidecar"]["status"] == "current"
    lessons = json.loads((repo / "lessons.json").read_text("utf-8"))
    lessons["lessons"][0]["prevention"] = "A different prevention."
    (repo / "lessons.json").write_text(json.dumps(lessons, indent=2), "utf-8")
    stale = run("--area", "src")
    assert stale["sidecar"]["status"] == "stale"
    assert stale["level"] == "cards" and stale["matches"] == 4
    assert run("--grep", "no such text")["areas"] == []


def test_index_command_works_without_the_gate(tmp_path: Path) -> None:
    repo, config, _ = _project(tmp_path, gate=False)
    result = query_lesson_index(
        config_path=config, repository_root=repo, module="engine.queue"
    )

    assert result["sidecar"]["status"] == "disabled"
    assert result["matches"] == 1
    assert not (repo / "generated").exists()


@pytest.mark.parametrize(
    ("arguments", "code"),
    [
        (["--expand", "L999"], "unknown_lesson"),
        (["--expand", "L001", "--area", "src"], "usage"),
        (["--grep", "("], "usage"),
    ],
)
def test_index_command_errors(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    arguments: list[str],
    code: str,
) -> None:
    repo, config, _ = _project(tmp_path)
    exit_code = main(
        ["--json-errors", "index", "--config", str(config), "--repo", str(repo)]
        + arguments
    )
    assert exit_code == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == code
