"""The read-only importer of failure-memory registries."""

from __future__ import annotations

import copy
import json
import operator
import os
import shutil
from pathlib import Path

import pytest

from akms_records import RecordsError, RecordStore, Scope, import_failure_memory
from akms_records.citations import FAILURE_LESSON_REF, lesson_digest, lesson_schema
from akms_records.cli import main
from akms_records.failure_memory import load_lessons
from akms_records.portable import export_records, import_records

FIXTURES = (
    Path(__file__).resolve().parents[2] / "akms_failure_memory" / "tests" / "fixtures"
)
PACKS = FIXTURES / "consumer_contract"
pytestmark = pytest.mark.skipif(
    not PACKS.is_dir(), reason="the failure-memory fixtures are not in this checkout"
)
DATED_PATTERN = "^(?:L[0-9]{3}|L[0-9]{8}-[0-9a-hjkmnp-tv-z]{4})$"


def lesson(lesson_id: str, *, symptom: str = "It failed.", **extra) -> dict:
    return {
        "id": lesson_id,
        "date_found": "2026-08-11",
        "date_found_precision": "exact",
        "date_fixed": "2026-08-12",
        "date_fixed_precision": "approximate",
        "location": {
            "area": "tool",
            "package": "demo pkg",
            "module": "demo.module",
            "file": "tools/demo.py",
            "symbol": "",
            "line_hint": f"topic {lesson_id}",
        },
        "found_by": {"type": "test", "trigger": "recorded during a test"},
        "symptom": symptom,
        "root_cause": "Known cause.",
        "fix": "Known fix.",
        "prevention": "Do not repeat this failure.",
        "references": {"commit": "abc", "issue": "#1", "pr": "", "plan": ""},
        "related": [],
        **extra,
    }


def write_config(root: Path, *, version: int, registry: str) -> Path:
    config = root / "project.toml"
    config.write_text(
        'schema_version = "failure-memory-project/v1"\n'
        'repository_id = "demo"\n'
        f'[paths]\nregistry = "{registry}"\n'
        f"[validation]\nregistry_schema_version = {version}\n"
        f'id_pattern = "{DATED_PATTERN}"\n',
        encoding="utf-8",
    )
    return config


def write_v1(root: Path, lessons: list[dict]) -> Path:
    (root / "lessons.json").write_text(
        json.dumps({"schema_version": 1, "_field_spec": {}, "lessons": lessons}),
        encoding="utf-8",
    )
    return write_config(root, version=1, registry="lessons.json")


def write_v2(root: Path, lessons: list[dict]) -> Path:
    folder = root / "lessons"
    folder.mkdir(exist_ok=True)
    (folder / "_registry.json").write_text(
        json.dumps({"schema_version": 2, "_field_spec": {}}), encoding="utf-8"
    )
    for item in lessons:
        (folder / f"{item['id']}.json").write_text(json.dumps(item), encoding="utf-8")
    return write_config(root, version=2, registry="lessons")


def snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    out = {}
    for item in sorted(root.rglob("*")):
        if item.is_file():
            out[str(item.relative_to(root))] = (
                item.read_bytes(),
                item.stat().st_mtime_ns,
            )
        else:
            out[str(item.relative_to(root))] = (b"", item.stat().st_mtime_ns)
    return out


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source"
    path.mkdir()
    return path


def lesson_ref(record) -> str:
    [ref] = [r for r in record.source_refs if r["kind"] == "failure-lesson"]
    return ref["ref"]


def assert_round_trip(store: RecordStore, lessons, *, repository_id: str) -> None:
    """Every lesson's every field is in a record, and the ID is a source reference."""
    records = {
        lesson_ref(r): r
        for r in store.iter_records()
        if r.schema_ref == FAILURE_LESSON_REF
    }
    assert set(records) == {item["id"] for item in lessons}
    for item in lessons:
        record = records[item["id"]]
        assert record.payload == item
        assert record.origin["kind"] == "import"
        assert record.review_state == "unreviewed"
        assert record.lifecycle == "active"
        assert {
            "kind": "failure-lesson",
            "ref": item["id"],
            "note": repository_id,
        } in record.source_refs
        assert record.schema_sha256 == lesson_digest()


# ---------------------------------------------------------------------- parity
@pytest.mark.parametrize("pack", ["v1", "v2"])
def test_contract_packs_round_trip_and_stay_untouched(make_store, tmp_path, pack):
    root = tmp_path / pack
    shutil.copytree(PACKS / pack, root)
    before = snapshot(root)
    store = make_store()
    result = import_failure_memory(store, root / "project.toml", repo=root, actor="t")
    assert result["status"] == "ok"
    assert result["source"]["registry_schema_version"] == int(pack[1:])
    assert result["lessons"] == len(result["created"]) > 0
    lessons = load_lessons(root / "project.toml", root).lessons
    assert_round_trip(store, lessons, repository_id="ConsumerContract")
    assert snapshot(root) == before
    assert store.doctor()["status"] == "ok"
    store.close()


@pytest.mark.parametrize("pack", ["v1", "v2"])
def test_the_reader_agrees_with_failure_memorys_own_loader(tmp_path, pack):
    pytest.importorskip("akms_failure_memory")
    from akms_failure_memory.compiler import compile_registry
    from akms_failure_memory.config import load_project_config

    root = tmp_path / pack
    shutil.copytree(PACKS / pack, root)
    theirs = compile_registry(load_project_config(root / "project.toml"), root).lessons
    ours = load_lessons(root / "project.toml", root).lessons
    by_id = operator.itemgetter("id")
    assert sorted(ours, key=by_id) == sorted(theirs, key=by_id)
    assert len(ours) > 0


def test_the_pinned_registry_fixture_round_trips(make_store, tmp_path):
    """The hash-pinned registry fixture, whatever its directory is called."""
    registries = sorted(FIXTURES.glob("*/source_registry.json"))
    assert registries, "the pinned registry fixture is missing"
    raw = json.loads(registries[0].read_text(encoding="utf-8"))
    root = tmp_path / "pinned"
    root.mkdir()
    (root / "lessons.json").write_bytes(registries[0].read_bytes())
    config = write_config(root, version=1, registry="lessons.json")
    before = snapshot(root)
    store = make_store()
    result = import_failure_memory(store, config, repo=root, actor="t")
    assert len(result["created"]) == len(raw["lessons"]) > 0
    assert_round_trip(store, raw["lessons"], repository_id="demo")
    assert snapshot(root) == before
    store.close()


@pytest.mark.parametrize("writer", [write_v1, write_v2])
def test_sequential_and_dated_ids_round_trip(make_store, source, writer):
    lessons = [
        lesson("L001"),
        lesson("L20261028-k3f9", notes="A note", related=["L001"]),
    ]
    config = writer(source, lessons)
    before = snapshot(source)
    store = make_store()
    result = import_failure_memory(store, config, repo=source, actor="t")
    assert {row["lesson"] for row in result["created"]} == {"L001", "L20261028-k3f9"}
    assert_round_trip(store, lessons, repository_id="demo")
    assert snapshot(source) == before
    store.close()


def test_the_reader_agrees_on_dated_ids_with_failure_memory(source):
    pytest.importorskip("akms_failure_memory")
    from akms_failure_memory.compiler import load_directory_registry
    from akms_failure_memory.config import load_project_config

    root = source / "project"
    shutil.copytree(PACKS / "v2", root)
    config_path = root / "project.toml"
    text = config_path.read_text(encoding="utf-8")
    config_path.write_text(
        text.replace('id_pattern = "^L[0-9]{3}$"', f'id_pattern = "{DATED_PATTERN}"'),
        encoding="utf-8",
    )
    dated = lesson("L20261028-k3f9")
    (root / "lessons" / "L20261028-k3f9.json").write_text(
        json.dumps(dated), encoding="utf-8"
    )
    theirs, _ = load_directory_registry(
        root / "lessons", load_project_config(config_path)
    )
    ours = load_lessons(config_path, root).lessons
    by_id = operator.itemgetter("id")
    assert sorted(ours, key=by_id) == sorted(theirs, key=by_id)
    assert dated in ours


def test_annotations_are_not_read_as_lessons(make_store, source):
    config = write_v2(source, [lesson("L001")])
    (source / "lessons" / "_annotations.json").write_text("{}", encoding="utf-8")
    store = make_store()
    result = import_failure_memory(store, config, repo=source, actor="t")
    assert result["lessons"] == 1
    store.close()


# ----------------------------------------------------------------- re-running
def test_rerunning_writes_nothing(make_store, source):
    config = write_v1(source, [lesson("L001"), lesson("L002")])
    store = make_store()
    import_failure_memory(store, config, repo=source, actor="t")
    heads = {r.record_id: r.head_sha256 for r in store.iter_records()}
    result = import_failure_memory(store, config, repo=source, actor="t")
    assert result["created"] == [] and result["amended"] == []
    assert sorted(result["unchanged"]) == ["L001", "L002"]
    assert result["schema_registered"] is False
    assert {r.record_id: r.head_sha256 for r in store.iter_records()} == heads
    store.close()


def test_a_changed_lesson_is_an_amend_and_needs_a_new_review(make_store, source):
    config = write_v1(source, [lesson("L001"), lesson("L002")])
    store = make_store()
    first = import_failure_memory(store, config, repo=source, actor="t")
    rid = next(r["record_id"] for r in first["created"] if r["lesson"] == "L001")
    store.amend(rid, {"review_state": "user_confirmed"}, expected_revision=1, actor="t")
    write_v1(source, [lesson("L001", symptom="It failed differently."), lesson("L002")])
    result = import_failure_memory(store, config, repo=source, actor="t")
    assert result["created"] == []
    assert [row["lesson"] for row in result["amended"]] == ["L001"]
    assert result["unchanged"] == ["L002"]
    record = store.get(rid)
    assert record.payload["symptom"] == "It failed differently."
    assert record.summary == "L001: It failed differently."
    assert record.review_state == "unreviewed"
    assert record.revision == 3
    assert record.origin["kind"] == "import"
    again = import_failure_memory(store, config, repo=source, actor="t")
    assert again["amended"] == []
    assert store.get(rid).revision == 3
    store.close()


def test_a_lesson_removed_upstream_is_reported_not_retracted(make_store, source):
    config = write_v1(source, [lesson("L001"), lesson("L002")])
    store = make_store()
    first = import_failure_memory(store, config, repo=source, actor="t")
    gone = next(r["record_id"] for r in first["created"] if r["lesson"] == "L002")
    write_v1(source, [lesson("L001")])
    result = import_failure_memory(store, config, repo=source, actor="t")
    assert result["removed_upstream"] == [{"lesson": "L002", "record_id": gone}]
    assert store.get(gone).lifecycle == "active"
    assert store.get(gone).revision == 1
    write_v1(source, [lesson("L001"), lesson("L002")])
    back = import_failure_memory(store, config, repo=source, actor="t")
    assert back["removed_upstream"] == [] and back["created"] == []
    store.close()


def test_an_erased_or_retracted_record_is_not_brought_back(make_store, source):
    config = write_v1(source, [lesson("L001"), lesson("L002")])
    store = make_store()
    first = import_failure_memory(store, config, repo=source, actor="t")
    ids = {row["lesson"]: row["record_id"] for row in first["created"]}
    store.erase(ids["L001"], reason="privacy", actor="t")
    store.retract(ids["L002"], expected_revision=1, reason="no longer true", actor="t")
    write_v1(source, [lesson("L001"), lesson("L002", symptom="Changed.")])
    result = import_failure_memory(store, config, repo=source, actor="t")
    assert result["created"] == [] and result["amended"] == []
    assert result["skipped"]["erased"] == [{"lesson": "L001", "record_id": ids["L001"]}]
    assert result["skipped"]["inactive"] == [
        {"lesson": "L002", "record_id": ids["L002"], "lifecycle": "retracted"}
    ]
    assert store.get(ids["L002"]).lifecycle == "retracted"
    store.close()


def test_two_projects_can_share_a_store(make_store, tmp_path):
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir(), two.mkdir()
    write_v1(one, [lesson("L001")])
    write_v1(two, [lesson("L001", symptom="Other project.")])
    for root, name in ((one, "first"), (two, "second")):
        path = root / "project.toml"
        path.write_text(
            path.read_text("utf-8").replace('"demo"', f'"{name}"'), encoding="utf-8"
        )
    store = make_store()
    for root in (one, two):
        result = import_failure_memory(
            store, root / "project.toml", repo=root, actor="t"
        )
        assert len(result["created"]) == 1
    assert sum(1 for _ in store.iter_records()) == 2
    store.close()


def test_survives_export_and_import(make_store, source, tmp_path, clock):
    config = write_v1(source, [lesson("L001")])
    store = make_store(clock=clock())
    import_failure_memory(store, config, repo=source, actor="t")
    out = tmp_path / "export.jsonl"
    with out.open("w", encoding="utf-8", newline="\n") as handle:
        export_records(store, handle, exporter="test")
    target = tmp_path / "elsewhere"
    target.mkdir()
    other = RecordStore.open(Scope.parse("project:example"), repo=target, clock=clock())
    import_records(other, out, actor="t")
    assert import_failure_memory(other, config, repo=source, actor="t")["created"] == []
    store.close()
    other.close()


# ---------------------------------------------------------------- bad registries
@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda s, c: c.write_text("not = [toml", "utf-8"), "failure_memory_config"),
        (lambda s, c: c.unlink(), "failure_memory_config"),
        (
            lambda s, c: c.write_text('schema_version = "other/v9"\n', "utf-8"),
            "failure_memory_config",
        ),
        (
            lambda s, c: c.write_text(
                c.read_text("utf-8").replace("lessons.json", "../escape.json"), "utf-8"
            ),
            "failure_memory_config",
        ),
        (
            lambda s, c: c.write_text(
                c.read_text("utf-8").replace("lessons.json", "/etc/lessons.json"),
                "utf-8",
            ),
            "failure_memory_config",
        ),
        (
            lambda s, c: c.write_text(
                c.read_text("utf-8").replace(
                    "schema_version = 1", "schema_version = 3"
                ),
                "utf-8",
            ),
            "failure_memory_config",
        ),
        (lambda s, c: (s / "lessons.json").unlink(), "failure_memory_registry"),
        (
            lambda s, c: (s / "lessons.json").write_text("{", "utf-8"),
            "failure_memory_registry",
        ),
        (
            lambda s, c: (s / "lessons.json").write_text('{"lessons": []}', "utf-8"),
            "failure_memory_registry",
        ),
        (
            lambda s, c: write_v1(s, [lesson("L001"), lesson("L001")]),
            "failure_memory_registry",
        ),
        (lambda s, c: write_v1(s, [lesson("bad-id")]), "failure_memory_registry"),
        (
            lambda s, c: write_v1(s, [lesson("L001", surprise="a new field")]),
            "failure_memory_registry",
        ),
    ],
)
def test_bad_sources_are_refused_and_nothing_is_written(
    make_store, source, mutate, code
):
    config = write_v1(source, [lesson("L001")])
    mutate(source, config)
    store = make_store()
    with pytest.raises(RecordsError) as caught:
        import_failure_memory(store, config, repo=source, actor="t")
    assert caught.value.code == code
    assert list(store.iter_records()) == []
    store.close()


def test_an_extra_top_level_registry_key_is_ignored(source):
    config = write_v1(source, [lesson("L001")])
    registry = source / "lessons.json"
    data = json.loads(registry.read_text(encoding="utf-8"))
    data["_moved_to_elsewhere"] = "a note the project keeps here"
    registry.write_text(json.dumps(data), encoding="utf-8")
    loaded = load_lessons(config, source)
    assert [item["id"] for item in loaded.lessons] == ["L001"]


def test_an_extra_registry_meta_key_is_ignored(source):
    config = write_v2(source, [lesson("L001")])
    meta_path = source / "lessons" / "_registry.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["_moved_to_elsewhere"] = "a note"
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    loaded = load_lessons(config, source)
    assert [item["id"] for item in loaded.lessons] == ["L001"]


def test_a_schema_1_registry_still_needs_its_required_keys(source):
    config = write_v1(source, [lesson("L001")])
    registry = source / "lessons.json"
    data = json.loads(registry.read_text(encoding="utf-8"))
    del data["_field_spec"]
    registry.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(RecordsError) as caught:
        load_lessons(config, source)
    assert caught.value.code == "failure_memory_registry"


def test_one_bad_lesson_leaves_the_others_unwritten(make_store, source):
    bad = copy.deepcopy(lesson("L002"))
    del bad["fix"]
    config = write_v1(source, [lesson("L001"), bad])
    store = make_store()
    with pytest.raises(RecordsError) as caught:
        import_failure_memory(store, config, repo=source, actor="t")
    assert caught.value.code == "failure_memory_registry"
    assert list(store.iter_records()) == []
    store.close()


def test_a_directory_registry_rejects_strays_and_mismatches(make_store, source):
    config = write_v2(source, [lesson("L001")])
    store = make_store()
    stray = source / "lessons" / "README.txt"
    stray.write_text("x", encoding="utf-8")
    with pytest.raises(RecordsError) as caught:
        import_failure_memory(store, config, repo=source, actor="t")
    assert caught.value.code == "failure_memory_registry"
    stray.unlink()
    (source / "lessons" / "L002.json").write_text(
        json.dumps(lesson("L003")), encoding="utf-8"
    )
    with pytest.raises(RecordsError) as caught:
        import_failure_memory(store, config, repo=source, actor="t")
    assert caught.value.code == "failure_memory_registry"
    (source / "lessons" / "L002.json").unlink()
    (source / "lessons" / "_registry.json").unlink()
    with pytest.raises(RecordsError) as caught:
        import_failure_memory(store, config, repo=source, actor="t")
    assert caught.value.code == "failure_memory_registry"
    store.close()


def test_a_symlink_out_of_the_repository_is_refused(make_store, source, tmp_path):
    if os.name == "nt":
        pytest.skip("symlinks need privileges on Windows")
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    config = write_config(source, version=1, registry="lessons.json")
    os.symlink(outside, source / "lessons.json")
    store = make_store()
    with pytest.raises(RecordsError) as caught:
        import_failure_memory(store, config, repo=source, actor="t")
    assert caught.value.code == "failure_memory_config"
    store.close()


# ------------------------------------------------------------ the built-in schema
def test_the_schema_name_is_reserved(make_store):
    store = make_store()
    other = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "x-akms-records": {"name": "failure-lesson", "version": 1},
    }
    with pytest.raises(RecordsError) as caught:
        store.register_schema(other, actor="t")
    assert caught.value.code == "reserved_schema"
    newer = dict(lesson_schema())
    newer["x-akms-records"] = {**newer["x-akms-records"], "version": 2}
    with pytest.raises(RecordsError) as caught:
        store.register_schema(newer, actor="t")
    assert caught.value.code == "reserved_schema"
    outcome = store.register_schema(lesson_schema(), actor="t")
    assert outcome.schema.ref == FAILURE_LESSON_REF
    assert outcome.schema.schema_sha256 == lesson_digest()
    store.close()


def test_a_tampered_store_schema_is_refused(make_store, source):
    config = write_v1(source, [lesson("L001")])
    store = make_store()
    store.register_schema(lesson_schema(), actor="t")
    path = store.schemas.root / "failure-lesson" / "v1" / "schema.json"
    path.write_bytes(path.read_bytes().replace(b"Failure lesson", b"Something else"))
    with pytest.raises(RecordsError) as caught:
        import_failure_memory(store, config, repo=source, actor="t")
    assert caught.value.code == "schema_tampered"
    store.close()


def test_the_schema_mirrors_every_registry_field():
    """The schema's fields are failure-memory's own, so no field is lost."""
    pytest.importorskip("akms_failure_memory")
    from akms_failure_memory import compiler

    properties = lesson_schema()["properties"]
    assert set(properties) == set(compiler._LESSON_KEYS) | {"notes"}
    assert set(properties["location"]["required"]) == set(compiler._LOCATION_KEYS)
    assert set(properties["found_by"]["required"]) == set(compiler._FOUND_KEYS)
    assert set(properties["references"]["required"]) == set(compiler._REFERENCE_KEYS)


# ----------------------------------------------------------------------- the CLI
def cli(capsys, *args):
    code = main(["--json-errors", *args])
    return code, json.loads(capsys.readouterr().out)


def test_cli_import(repo, source, capsys):
    config = write_v2(source, [lesson("L001")])
    base = ["--scope", "project:example", "--repo", str(repo)]
    code, out = cli(
        capsys,
        "import",
        *base,
        "--from-failure-memory",
        str(config),
        "--failure-memory-repo",
        str(source),
    )
    assert code == 0 and [r["lesson"] for r in out["created"]] == ["L001"]
    code, out = cli(capsys, "recall", *base, "--query", "failed")
    assert code == 0 and out["count"] == 1
    assert out["results"][0]["schema_ref"] == FAILURE_LESSON_REF
    code, out = cli(capsys, "import", *base)
    assert code == 2 and out["error"]["code"] == "usage"
    code, out = cli(
        capsys, "import", *base, str(source / "x"), "--from-failure-memory", str(config)
    )
    assert code == 2 and out["error"]["code"] == "usage"
    code, out = cli(
        capsys, "import", *base, str(source / "x"), "--failure-memory-repo", str(source)
    )
    assert code == 2 and out["error"]["code"] == "usage"


def test_cli_defaults_to_the_repo_for_relative_paths(repo, capsys):
    knowledge = repo / ".knowledge"
    knowledge.mkdir()
    (knowledge / "lessons.json").write_text(
        json.dumps(
            {"schema_version": 1, "_field_spec": {}, "lessons": [lesson("L001")]}
        ),
        encoding="utf-8",
    )
    config = knowledge / "failure-memory.toml"
    text = (
        'schema_version = "failure-memory-project/v1"\nrepository_id = "demo"\n'
        '[paths]\nregistry = ".knowledge/lessons.json"\n'
        f'[validation]\nregistry_schema_version = 1\nid_pattern = "{DATED_PATTERN}"\n'
    )
    config.write_text(text, encoding="utf-8")
    code, out = cli(
        capsys,
        "import",
        "--scope",
        "project:example",
        "--repo",
        str(repo),
        "--from-failure-memory",
        str(config),
    )
    assert code == 0 and len(out["created"]) == 1
