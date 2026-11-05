"""Create, amend, supersede and retract; replay; duplicates; tamper detection."""

from __future__ import annotations

import json
from datetime import date

import pytest

from akms_records import RecordsError, ReplayError, StaleRevision
from akms_records.canonical import canonical_bytes
from akms_records.ids import RECORD_ID_RE, record_id_for


def tree(root):
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_create_writes_one_canonical_sealed_event(store, doc):
    result = store.create(doc(), actor="tester", event_id="ev-1")
    assert RECORD_ID_RE.fullmatch(result.record_id)
    assert result.record_id.startswith("rec-20261103-")
    path = store.record_dir(result.record_id) / "000001.json"
    raw = path.read_bytes()
    event = json.loads(raw)
    assert raw == canonical_bytes(event)
    assert event["prev_sha256"] is None and event["kind"] == "create"
    assert event["format"] == "akms-records-event/v1"
    record = store.get(result.record_id)
    assert record.revision == 1 and record.lifecycle == "active"
    assert record.summary == "Decision: Keep the model"  # from the template
    assert record.origin == {"kind": "agent", "actor_id": "tester"}
    assert record.schema_sha256 == store.schemas.get("decision/v1").schema_sha256
    assert set(record.envelope_json()) == {
        "record_id",
        "revision",
        "schema_ref",
        "schema_sha256",
        "scope",
        "recorded_at",
        "origin",
        "source_refs",
        "summary",
        "tags",
        "sensitivity",
        "review_state",
        "lifecycle",
        "payload",
    }


def test_record_id_is_derived_from_the_event_id():
    first = record_id_for(date(2026, 11, 3), "ev-1", 0)
    assert first == record_id_for(date(2026, 11, 3), "ev-1", 0)
    assert first != record_id_for(date(2026, 11, 3), "ev-1", 1)
    assert first != record_id_for(date(2026, 11, 3), "ev-2", 0)
    assert RECORD_ID_RE.fullmatch(first)
    assert len(first.rsplit("-", 1)[1]) == 8


def test_amend_chains_and_stale_amend_changes_nothing(store, doc):
    rid = store.create(doc(), actor="t").record_id
    amended = store.amend(rid, {"summary": "new"}, expected_revision=1, actor="t")
    assert amended.revision == 2
    events = store.history(rid)
    assert events[1]["prev_sha256"] is not None
    before = tree(store.root)
    with pytest.raises(StaleRevision) as caught:
        store.amend(rid, {"summary": "stale"}, expected_revision=1, actor="t")
    assert caught.value.code == "stale_revision"
    assert caught.value.head == 2 and caught.value.where == "precheck"
    assert tree(store.root) == before


def test_link_is_the_concurrency_guard(store, doc, monkeypatch):
    """A writer that read an old head loses at the exclusive link."""
    rid = store.create(doc(), actor="t").record_id
    real_load = store._load
    snapshot = real_load(rid)
    store.amend(rid, {"summary": "winner"}, expected_revision=1, actor="t")
    before = tree(store.root)
    monkeypatch.setattr(store, "_load", lambda _rid: snapshot)  # stale view
    with pytest.raises(StaleRevision) as caught:
        store.amend(rid, {"summary": "loser"}, expected_revision=1, actor="t")
    assert caught.value.where == "link"
    assert tree(store.root) == before
    assert not list(store.record_dir(rid).glob("*.tmp"))


def test_amend_validates_the_payload_and_keeps_absent_fields(store, doc):
    rid = store.create(doc(tags=["a"]), actor="t").record_id
    store.amend(rid, {"review_state": "user_confirmed"}, expected_revision=1, actor="t")
    record = store.get(rid)
    assert record.tags == ["a"] and record.review_state == "user_confirmed"
    with pytest.raises(RecordsError) as caught:
        store.amend(rid, {"payload": {"decision": "x"}}, expected_revision=2, actor="t")
    assert caught.value.code == "payload_invalid"
    with pytest.raises(RecordsError, match="must change something"):
        store.amend(rid, {}, expected_revision=2, actor="t")


def test_supersede_links_the_new_record_and_freezes_the_old(store, doc):
    old = store.create(doc("old"), actor="t").record_id
    result = store.supersede(
        old,
        expected_revision=1,
        actor="t",
        document=doc("new"),
        reason="better",
        event_id="sup-1",
    )
    new = result["superseded_by"]
    assert store.get(old).lifecycle == "superseded"
    assert store.get(old).superseded_by == new
    assert {"kind": "supersedes", "ref": old} in store.get(new).source_refs
    again = store.supersede(
        old,
        expected_revision=1,
        actor="t",
        document=doc("new"),
        reason="better",
        event_id="sup-1",
    )
    assert again["superseded"]["noop"] and again["created"]["noop"]
    assert again["superseded_by"] == new
    with pytest.raises(RecordsError) as caught:
        store.amend(old, {"summary": "late"}, expected_revision=2, actor="t")
    assert caught.value.code == "not_active"


def test_supersede_by_an_existing_record(store, doc):
    old = store.create(doc("old"), actor="t").record_id
    new = store.create(doc("new"), actor="t").record_id
    store.supersede(old, expected_revision=1, actor="t", by=new)
    assert store.get(old).superseded_by == new
    with pytest.raises(RecordsError, match="itself"):
        store.supersede(new, expected_revision=1, actor="t", by=new)


def test_retract(store, doc):
    rid = store.create(doc(), actor="t").record_id
    store.retract(rid, expected_revision=1, reason="wrong", actor="t")
    record = store.get(rid)
    assert record.lifecycle == "retracted" and record.reason == "wrong"
    with pytest.raises(RecordsError) as caught:
        store.retract(rid, expected_revision=2, reason="again", actor="t")
    assert caught.value.code == "not_active"


def test_replay_is_deterministic(store, doc, make_store):
    rid = store.create(doc(), actor="t").record_id
    store.amend(rid, {"tags": ["x"]}, expected_revision=1, actor="t")
    store.retract(rid, expected_revision=2, reason="done", actor="t")
    first = store.get(rid)
    second = make_store().get(rid)
    assert first == second
    assert first.envelope_json() == second.envelope_json()


def test_duplicate_event_is_a_noop(store, doc):
    created = store.create(doc(), actor="t", event_id="same")
    again = store.create(doc(), actor="t", event_id="same")
    assert again.noop and again.record_id == created.record_id
    store.amend(
        created.record_id,
        {"summary": "a"},
        expected_revision=1,
        actor="t",
        event_id="am",
    )
    before = tree(store.root)
    # A retry of the amend still names the old expected revision: no-op, not stale.
    retry = store.amend(
        created.record_id,
        {"summary": "a"},
        expected_revision=1,
        actor="t",
        event_id="am",
    )
    assert retry.noop and retry.revision == 2
    assert tree(store.root) == before
    with pytest.raises(RecordsError) as caught:
        store.retract(
            created.record_id, expected_revision=2, reason="r", actor="t", event_id="am"
        )
    assert caught.value.code == "event_id_reused"


def test_retried_create_after_midnight_is_recognised(make_store, doc, clock):
    first = make_store(clock=clock("2026-11-03T23:59:59"))
    from akms_records.schemas import load_template

    first.register_schema(load_template("decision"), actor="t")
    created = first.create(doc(), actor="t", event_id="late")
    retry = make_store(clock=clock("2026-11-04T00:00:01")).create(
        doc(), actor="t", event_id="late"
    )
    assert retry.noop and retry.record_id == created.record_id


def test_id_collision_moves_to_the_next_attempt(store, doc, monkeypatch):
    from akms_records import store as store_module

    real = store_module.record_id_for
    taken = store.create(doc(), actor="t", event_id="a").record_id

    def colliding(day, event_id, attempt):
        return taken if attempt == 0 else real(day, event_id, attempt)

    monkeypatch.setattr(store_module, "record_id_for", colliding)
    other = store.create(doc("other"), actor="t", event_id="b")
    assert not other.noop and other.record_id != taken


def _rewrite(path, change):
    event = json.loads(path.read_bytes())
    change(event)
    path.write_bytes(canonical_bytes(event))


def test_tampered_middle_revision_breaks_the_chain(store, doc):
    rid = store.create(doc(), actor="t").record_id
    store.amend(rid, {"summary": "b"}, expected_revision=1, actor="t")
    path = store.record_dir(rid) / "000001.json"

    def change(event):
        event["body"]["payload"]["decision"] = "forged"
        from akms_records.store import seal_of

        event["event_sha256"] = seal_of(event)  # even with a recomputed seal

    _rewrite(path, change)
    with pytest.raises(ReplayError) as caught:
        store.get(rid)
    assert caught.value.replay_code == "chain"


def test_tampered_head_revision_is_detected(store, doc):
    """The chain alone misses an edit to the newest revision; the seal does not."""
    rid = store.create(doc(), actor="t").record_id
    store.amend(rid, {"summary": "b"}, expected_revision=1, actor="t")
    _rewrite(
        store.record_dir(rid) / "000002.json",
        lambda event: event["body"]["envelope"].update(summary="forged"),
    )
    with pytest.raises(ReplayError) as caught:
        store.get(rid)
    assert caught.value.replay_code == "digest"


def test_gap_mismatch_and_conflict_markers_are_reported(store, doc):
    rid = store.create(doc(), actor="t").record_id
    store.amend(rid, {"summary": "b"}, expected_revision=1, actor="t")
    store.amend(rid, {"summary": "c"}, expected_revision=2, actor="t")
    directory = store.record_dir(rid)
    second = (directory / "000002.json").read_bytes()
    (directory / "000002.json").unlink()
    with pytest.raises(ReplayError) as caught:
        store.get(rid)
    assert caught.value.replay_code == "gap"
    (directory / "000002.json").write_bytes(
        b"<<<<<<< HEAD\n" + second + b"=======\n" + second + b">>>>>>> other\n"
    )
    with pytest.raises(ReplayError) as caught:
        store.get(rid)
    assert caught.value.replay_code == "conflict"


def test_whitespace_only_change_keeps_the_digests(store, doc, items):
    rid = store.create(doc(), actor="t").record_id
    store.amend(rid, {"summary": "b"}, expected_revision=1, actor="t")
    path = store.record_dir(rid) / "000001.json"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert store.get(rid).revision == 2  # hashes are over canonical JSON
    report = store.doctor()
    assert items(report, "noncanonical") == [f"2026-11/{rid}/000001.json"]
    assert report["status"] == "ok"
