"""Portable JSONL export and import."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from akms_records import RecordStore, RecordsError, Scope
from akms_records.portable import export_records, import_records
from akms_records.schemas import load_template


def export_text(store: RecordStore, **kwargs) -> str:
    buffer = io.StringIO()
    export_records(store, buffer, **kwargs)
    return buffer.getvalue()


def write(tmp_path: Path, text: str, name: str = "export.jsonl") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def populated(store, doc):
    a = store.create(doc("a", tags=["x"]), actor="t").record_id
    store.amend(a, {"review_state": "user_confirmed"}, expected_revision=1, actor="t")
    b = store.create(doc("b"), actor="t").record_id
    store.retract(b, expected_revision=1, reason="wrong", actor="t")
    secret = store.create(doc("s", sensitivity="sensitive"), actor="t").record_id
    gone = store.create(doc("gone"), actor="t").record_id
    store.erase(gone, reason="privacy", actor="owner")
    return store, {"a": a, "b": b, "secret": secret, "gone": gone}


def test_round_trip_reconstructs_identical_records(populated, tmp_path):
    store, ids = populated
    text = export_text(store)
    target = RecordStore.open(Scope("project", "example"), repo=tmp_path / "other")
    report = import_records(target, write(tmp_path, text), actor="importer")
    assert report["status"] == "ok"
    assert sorted(report["records_written"]) == sorted([ids["a"], ids["b"]])
    assert report["events_written"] == 4
    assert report["erasures_added"] == 1
    for key in ("a", "b"):
        assert target.get(ids[key]) == store.get(ids[key])
        for name in ("000001.json", "000002.json"):
            assert (target.record_dir(ids[key]) / name).read_bytes() == (
                store.record_dir(ids[key]) / name
            ).read_bytes()
    assert not target.record_dir(ids["secret"]).exists()  # sensitive left out
    assert target.schemas.get("decision/v1").schema_sha256 == (
        store.schemas.get("decision/v1").schema_sha256
    )
    again = import_records(target, write(tmp_path, text), actor="importer")
    assert again["records_written"] == [] and again["events_written"] == 0
    assert sorted(again["records_unchanged"]) == sorted([ids["a"], ids["b"]])
    assert again["erasures_added"] == 0


def test_include_sensitive(populated):
    store, ids = populated
    assert ids["secret"] not in export_text(store)
    assert ids["secret"] in export_text(store, include_sensitive=True)


def test_import_appends_only_missing_revisions(store, doc, tmp_path):
    rid = store.create(doc(), actor="t").record_id
    first = export_text(store)
    target = RecordStore.open(Scope("project", "example"), repo=tmp_path / "other")
    import_records(target, write(tmp_path, first), actor="i")
    store.amend(rid, {"summary": "later"}, expected_revision=1, actor="t")
    report = import_records(target, write(tmp_path, export_text(store)), actor="i")
    assert report["events_written"] == 1 and target.get(rid).summary == "later"


def test_diverged_history_is_a_conflict_left_alone(store, doc, tmp_path):
    rid = store.create(doc(), actor="t").record_id
    target = RecordStore.open(Scope("project", "example"), repo=tmp_path / "other")
    import_records(target, write(tmp_path, export_text(store)), actor="i")
    store.amend(rid, {"summary": "here"}, expected_revision=1, actor="t")
    target.amend(rid, {"summary": "there"}, expected_revision=1, actor="t")
    report = import_records(target, write(tmp_path, export_text(store)), actor="i")
    assert report["status"] == "drift" and rid in report["conflicts"]
    assert target.get(rid).summary == "there"


def test_erased_record_is_not_brought_back(populated, tmp_path):
    store, ids = populated
    text = export_text(store)
    target = RecordStore.open(Scope("project", "example"), repo=tmp_path / "other")
    import_records(target, write(tmp_path, text), actor="i")
    target.erase(ids["a"], reason="privacy", actor="owner")
    report = import_records(target, write(tmp_path, text), actor="i")
    assert ids["a"] in report["skipped_erased"]
    assert not target.record_dir(ids["a"]).exists()


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda lines: lines[:-1],  # truncated: no footer
        lambda lines: lines[:2] + lines[3:],  # a line dropped
        lambda lines: [
            lines[0].replace("akms-records-export/v1", "other/v9"),
            *lines[1:],
        ],
    ],
)
def test_corrupt_exports_are_refused(populated, tmp_path, corrupt):
    store, _ = populated
    lines = export_text(store).splitlines()
    target = RecordStore.open(Scope("project", "example"), repo=tmp_path / "other")
    with pytest.raises(RecordsError) as caught:
        import_records(
            target, write(tmp_path, "\n".join(corrupt(lines)) + "\n"), actor="i"
        )
    assert caught.value.code == "export_corrupt"
    assert not target.root.exists()


def _refooter(lines: list[str]) -> list[str]:
    """Recompute the footer so only the deeper digest checks can object."""
    import hashlib

    body = lines[:-1]
    footer = json.loads(lines[-1])
    footer["sha256"] = hashlib.sha256(
        "".join(line + "\n" for line in body).encode("utf-8")
    ).hexdigest()
    return [*body, json.dumps(footer, sort_keys=True, separators=(",", ":"))]


def test_tampered_event_or_schema_is_refused_even_with_a_valid_footer(
    populated, tmp_path
):
    store, _ = populated
    lines = export_text(store).splitlines()
    event_line = next(i for i, line in enumerate(lines) if '"type":"event"' in line)
    item = json.loads(lines[event_line])
    item["event"]["body"]["payload"]["decision"] = "forged"
    tampered = list(lines)
    tampered[event_line] = json.dumps(item, sort_keys=True, separators=(",", ":"))
    target = RecordStore.open(Scope("project", "example"), repo=tmp_path / "other")
    with pytest.raises(RecordsError) as caught:
        import_records(
            target, write(tmp_path, "\n".join(_refooter(tampered)) + "\n"), actor="i"
        )
    assert caught.value.code == "replay_error"
    assert not target.root.exists()  # nothing written, not even the schema
    schema_line = next(i for i, line in enumerate(lines) if '"type":"schema"' in line)
    item = json.loads(lines[schema_line])
    item["schema"]["properties"]["decision"]["maxLength"] = 1
    tampered = list(lines)
    tampered[schema_line] = json.dumps(item, sort_keys=True, separators=(",", ":"))
    with pytest.raises(RecordsError) as caught:
        import_records(
            target, write(tmp_path, "\n".join(_refooter(tampered)) + "\n"), actor="i"
        )
    assert caught.value.code == "digest_mismatch"
    assert not target.root.exists()


def test_import_refuses_another_scope(populated, tmp_path):
    store, _ = populated
    target = RecordStore.open(Scope("project", "elsewhere"), repo=tmp_path / "other")
    with pytest.raises(RecordsError) as caught:
        import_records(target, write(tmp_path, export_text(store)), actor="i")
    assert caught.value.code == "scope_violation"


def test_export_refuses_broken_records_unless_skipped(store, doc):
    good = store.create(doc("good"), actor="t").record_id
    bad = store.create(doc("bad"), actor="t").record_id
    store.amend(bad, {"summary": "b"}, expected_revision=1, actor="t")
    (store.record_dir(bad) / "000001.json").unlink()
    with pytest.raises(RecordsError) as caught:
        export_text(store)
    assert caught.value.details["records"] == [bad]
    text = export_text(store, skip_broken=True)
    assert good in text and bad not in text


def test_schemas_travel_with_the_export(make_store, doc, tmp_path):
    source = make_store()
    source.register_schema(load_template("idea"), actor="t")
    source.create({"schema_ref": "idea/v1", "payload": {"idea": "cache it"}}, actor="t")
    target = RecordStore.open(Scope("project", "example"), repo=tmp_path / "other")
    report = import_records(target, write(tmp_path, export_text(source)), actor="i")
    assert report["schemas_registered"] == ["idea/v1"]
