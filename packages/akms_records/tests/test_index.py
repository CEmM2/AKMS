"""The derived SQLite index: parity, staleness, reconcile, erasure."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3

import pytest

from akms_records import IndexUnavailable, RecordStore, Scope
from akms_records import index as index_module
from akms_records.cli import main
from akms_records.index import RecordIndex, normalize_time
from akms_records.schemas import load_template

SECRET = "zebracornflux"
SECRET2 = "quokkamarmalade"


def ids(result):
    return [hit.record_id for hit in result.hits]


def settle(store):
    """Age every directory past the racy window, then let a read record it.

    Without this, every directory in a fast test is "too recent to trust", so
    every read rescans everything and a test cannot tell whether the cheap
    check itself noticed a change.
    """
    past = os.stat(store.root).st_mtime_ns - 10 * index_module.RACY_NS
    for path in [store.root, *store.root.rglob("*")]:
        if path.is_dir() and ".index" not in path.parts and ".git" not in path.parts:
            os.utime(path, ns=(past, past))
    store.recall()
    index = store.open_index()
    assert None not in dict(index.db.execute("SELECT month, sig FROM months")).values()
    assert (
        None not in dict(index.db.execute("SELECT record_id, sig FROM files")).values()
    )


def count_replays(monkeypatch):
    calls = []
    original = RecordIndex._sync_record

    def counting(self, record_id, *args, **kwargs):
        calls.append(record_id)
        return original(self, record_id, *args, **kwargs)

    monkeypatch.setattr(RecordIndex, "_sync_record", counting)
    return calls


def build_mixed_store(make_store, clock):
    """A store root exercising every kind of write the index sees."""
    store = make_store(clock=clock())
    store.register_schema(load_template("decision"), actor="t")
    store.register_schema(load_template("idea"), actor="t")
    other = make_store("project:other", clock=clock("2026-11-03T11:00:00"))
    a = store.create(
        {
            "schema_ref": "decision/v1",
            "payload": {
                "decision": "Keep the surrogate",
                "rationale": "within budget",
                "decided_at": "2026-10-01",
            },
            "tags": ["model", "surrogate"],
            "source_refs": [{"kind": "issue", "ref": "#1"}],
            "origin": {"kind": "human", "actor_id": "t"},
        },
        actor="t",
    ).record_id
    b = store.create(
        {"schema_ref": "idea/v1", "payload": {"idea": "Try a mesh refinement"}},
        actor="t",
    ).record_id
    store.amend(
        a,
        {"tags": ["model"], "review_state": "user_confirmed"},
        expected_revision=1,
        actor="t",
    )
    store.amend(
        a, {"summary": "Keep the surrogate model"}, expected_revision=2, actor="t"
    )
    superseded = store.supersede(
        b,
        expected_revision=1,
        actor="t",
        document={"schema_ref": "idea/v1", "payload": {"idea": "Refine the mesh"}},
        reason="clearer",
    )
    c = store.create(
        {
            "schema_ref": "idea/v1",
            "payload": {"idea": "Drop the cache"},
            "sensitivity": "sensitive",
        },
        actor="t",
    ).record_id
    store.retract(c, expected_revision=1, reason="wrong", actor="t")
    gone = store.create(
        {"schema_ref": "idea/v1", "payload": {"idea": f"Erase {SECRET}"}},
        actor="t",
    ).record_id
    store.erase(gone, reason="privacy", actor="t")
    other.register_schema(load_template("decision"), actor="t")
    other.create(
        {
            "schema_ref": "decision/v1",
            "payload": {"decision": "Other project", "rationale": "x"},
        },
        actor="t",
    )
    other.close()
    return store, {"a": a, "b": b, "c": c, "successor": superseded["superseded_by"]}


def test_rebuild_matches_incremental_indexing(make_store, clock):
    store, _ = build_mixed_store(make_store, clock)
    incremental = store.open_index().snapshot()
    assert len([row for row in incremental if row[0] == "record"]) == 5
    report = store.open_index().rebuild()
    assert report["records"] == 5
    assert store.open_index().snapshot() == incremental
    assert store.open_index().compare()["status"] == "ok"
    # A fresh index built by the first read is the same as well.
    store.close()
    shutil.rmtree(store.root / ".index")
    fresh = RecordStore(store.root, store.scope)
    assert fresh.index_for_read() is not None
    assert fresh.open_index().snapshot() == incremental
    fresh.close()


def test_index_rows_carry_metadata(make_store, clock):
    store, names = build_mixed_store(make_store, clock)
    rows = {row[1]: row for row in store.open_index().snapshot() if row[0] == "record"}
    a = dict(zip(index_module.RECORD_COLUMNS, rows[names["a"]][1:], strict=True))
    assert a["revision"] == 3 and a["review_state"] == "user_confirmed"
    assert a["record_time"] == "2026-10-01T00:00:00.000000Z"  # the time field
    assert a["time_value"] == a["record_time"]
    assert json.loads(a["tags"]) == ["model"] and a["label"] == "Keep the surrogate"
    assert json.loads(a["source_refs"]) == [{"kind": "issue", "ref": "#1"}]
    successor = dict(
        zip(index_module.RECORD_COLUMNS, rows[names["successor"]][1:], strict=True)
    )
    assert json.loads(successor["supersedes"]) == [names["b"]]
    old = dict(zip(index_module.RECORD_COLUMNS, rows[names["b"]][1:], strict=True))
    assert old["lifecycle"] == "superseded"
    assert old["superseded_by"] == names["successor"]


def test_a_lower_revision_never_replaces_a_higher_one(store, doc):
    rid = store.create(doc(), actor="t").record_id
    first = store.get(rid)
    store.amend(rid, {"summary": "second"}, expected_revision=1, actor="t")
    index = store.open_index()
    assert index.write(first) is False  # a stale writer arriving late
    assert store.recall().hits[0].revision == 2
    assert store.recall().hits[0].summary == "second"


def test_rules_change_reextracts_records(store, make_store):
    rid = store.create(
        {
            "schema_ref": "decision/v1",
            "payload": {
                "decision": "Keep it",
                "rationale": "latency matters",
                "decided_by": "nightingale",
            },
        },
        actor="t",
    ).record_id
    assert ids(store.recall("nightingale")) == []  # decided_by is not search text
    rules = store.schemas.rules("decision/v1")
    other = make_store()  # another writer, in another store object
    other.set_rules(
        "decision/v1",
        {**rules, "search_text": [*rules["search_text"], "/decided_by"]},
        actor="ed",
    )
    other.close()
    assert ids(store.recall("nightingale")) == [rid]
    sha = store.schemas.rules_record("decision/v1")["rules_sha256"]
    rows = [r for r in store.open_index().snapshot() if r[0] == "record"]
    assert rows[0][1 + index_module.RECORD_COLUMNS.index("rules_sha256")] == sha
    assert store.open_index().compare()["status"] == "ok"


def test_unindexed_changes_are_found_by_check_and_reconcile(store, doc, repo, capsys):
    rid = store.create(doc(), actor="t").record_id
    quiet = RecordStore(store.root, store.scope, index=False)  # bulk-load mode
    quiet.amend(rid, {"summary": "changed quietly"}, expected_revision=1, actor="t")
    quiet.close()
    args = ["--scope", "project:example", "--repo", str(repo)]
    assert main(["index", "check", *args]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "drift" and out["stale"] == [rid]
    assert main(["index", "check", *args]) == 1  # check changed nothing
    capsys.readouterr()
    report = store.doctor()
    assert {"record_id": rid, "problem": "stale"} in next(
        c["items"] for c in report["checks"] if c["check"] == "index_drift"
    )
    assert main(["index", "reconcile", *args]) == 0
    assert json.loads(capsys.readouterr().out)["updated"] == [rid]
    assert main(["index", "check", *args]) == 0
    assert store.recall().hits[0].summary == "changed quietly"


def test_doctor_fix_reconciles_the_index(store, doc):
    rid = store.create(doc(), actor="t").record_id
    quiet = RecordStore(store.root, store.scope, index=False)
    quiet.retract(rid, expected_revision=1, reason="no", actor="t")
    quiet.close()
    assert store.doctor()["status"] == "error"
    fixed = store.doctor(fix=True)
    assert fixed["repairs"]["index_reconciled"] == [rid]
    assert store.doctor()["status"] == "ok"
    assert store.recall().hits == ()


def test_a_crashed_index_update_is_caught_by_its_marker(store, doc, monkeypatch):
    rid = store.create(doc(), actor="t").record_id

    def crash(self, record):
        raise sqlite3.OperationalError("simulated crash before the index update")

    monkeypatch.setattr(RecordIndex, "write", crash)
    store.amend(rid, {"summary": "after the crash"}, expected_revision=1, actor="t")
    monkeypatch.undo()
    markers = list((store.root / ".index" / "pending").iterdir())
    assert [m.name.split(".")[0] for m in markers] == [rid]
    reader = RecordStore(store.root, store.scope)
    assert reader.recall().hits[0].summary == "after the crash"
    reader.close()
    # A marker whose writer has exited is removed once it has been handled.
    dead = markers[0].with_name(f"{rid}.999999999.0badf00d.pending")
    markers[0].rename(dead)
    assert store.recall().hits[0].revision == 2
    assert not dead.exists()


def test_reconcile_after_git_checkout(store, doc, repo, git):
    git(repo, "init", "-q")
    keep = store.create(doc("Keep this"), actor="t").record_id
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    git(repo, "checkout", "-qb", "feature")
    store.amend(keep, {"summary": "Feature summary"}, expected_revision=1, actor="t")
    added = store.create(doc("Only on the feature branch"), actor="t").record_id
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "feature")
    assert {h.record_id for h in store.recall().hits} == {keep, added}
    settle(store)
    git(repo, "checkout", "-q", "main")
    hits = store.recall().hits  # the cheap check sees the new git state
    assert [(h.record_id, h.revision) for h in hits] == [(keep, 1)]
    assert hits[0].summary == "Decision: Keep this"
    assert store.open_index().compare()["status"] == "ok"
    git(repo, "checkout", "-q", "feature")
    assert {h.record_id for h in store.recall().hits} == {keep, added}


def test_checkout_between_two_versions_of_one_revision(store, doc, repo, git):
    git(repo, "init", "-q")
    rid = store.create(doc(), actor="t").record_id
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    for branch, text in (("left", "Left amend"), ("right", "Right amend")):
        git(repo, "checkout", "-q", "-b", branch, "main")
        store.amend(rid, {"summary": text}, expected_revision=1, actor="t")
        git(repo, "add", "-A")
        git(repo, "commit", "-qm", branch)
    assert store.recall().hits[0].summary == "Right amend"
    settle(store)
    month = os.stat(store.root / "2026-11").st_mtime_ns
    git(repo, "checkout", "-q", "left")
    if os.name != "nt":  # the month directory is untouched: only git shows it
        assert os.stat(store.root / "2026-11").st_mtime_ns == month
    assert store.recall().hits[0].summary == "Left amend"  # same revision number


def test_reconcile_after_merge(store, doc, repo, git):
    git(repo, "init", "-q")
    base = store.create(doc("Base"), actor="t").record_id
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    git(repo, "checkout", "-qb", "side")
    side = store.create(doc("Side"), actor="t").record_id
    store.amend(base, {"tags": ["side"]}, expected_revision=1, actor="t")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "side")
    git(repo, "checkout", "-q", "main")
    main_only = store.create(doc("Main"), actor="t").record_id
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "main")
    assert {h.record_id for h in store.recall().hits} == {base, main_only}
    settle(store)
    git(repo, "merge", "-q", "--no-edit", "side")
    assert {h.record_id for h in store.recall().hits} == {base, side, main_only}
    assert {h.record_id for h in store.recall(tags=["side"]).hits} == {base}
    assert store.open_index().compare()["status"] == "ok"


def test_a_merge_that_brings_back_an_erased_record_never_indexes_it(
    store, doc, repo, git
):
    git(repo, "init", "-q")
    rid = store.create(doc(f"About {SECRET}"), actor="t").record_id
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    git(repo, "checkout", "-qb", "late")
    store.amend(rid, {"summary": f"Late {SECRET}"}, expected_revision=1, actor="t")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "late amend")
    git(repo, "checkout", "-q", "main")
    store.erase(rid, reason="privacy", actor="owner")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "erase")
    git(repo, "merge", "-q", "--no-edit", "late")
    assert store.record_dir(rid).exists()  # the late amend came back
    assert store.recall().hits == ()  # but the index skips erased records
    assert store.recall(SECRET).hits == ()


def index_bytes(store):
    out = b""
    for path in sorted((store.root / ".index").glob("records.sqlite*")):
        out += path.read_bytes()
    return out


def test_erasure_leaves_no_bytes_in_the_index(store, doc):
    keep = store.create(doc("Keep this"), actor="t").record_id
    rid = store.create(
        {
            "schema_ref": "decision/v1",
            "payload": {"decision": f"Use {SECRET}", "rationale": f"because {SECRET}"},
            "summary": f"Summary {SECRET}",
        },
        actor="t",
    ).record_id
    store.amend(rid, {"summary": f"Summary {SECRET2}"}, expected_revision=1, actor="t")
    assert ids(store.recall(SECRET)) == [rid]
    assert SECRET.encode() in index_bytes(store)
    report = store.erase(rid, reason="privacy request", actor="owner")
    assert report["index"]["status"] == "purged"
    assert report["index"]["rows_removed"] is True
    assert report["index"]["checkpoint"] == "complete"
    raw = index_bytes(store)
    assert SECRET.encode() not in raw and SECRET2.encode() not in raw
    assert store.recall(SECRET).hits == ()
    assert ids(store.recall()) == [keep]
    assert store.doctor()["status"] == "ok"


def test_doctor_fix_purges_a_reerased_record_from_the_index(store, doc):
    rid = store.create(doc(f"About {SECRET}"), actor="t").record_id
    saved = {p.name: p.read_bytes() for p in store.record_dir(rid).iterdir()}
    store.erase(rid, reason="privacy", actor="owner")
    store.record_dir(rid).mkdir(parents=True)  # a merge brings the files back
    for name, data in saved.items():
        (store.record_dir(rid) / name).write_bytes(data)
    assert store.recall().hits == ()
    store.doctor(fix=True)
    assert not store.record_dir(rid).exists()
    assert SECRET.encode() not in index_bytes(store)


def test_an_index_in_another_format_is_rebuilt(store, doc):
    rid = store.create(doc(), actor="t").record_id
    store.open_index().db.execute(
        "UPDATE meta SET value='akms-records-index/v0' WHERE key='format'"
    )
    store.close()
    assert store.doctor()["checks"][-2]["items"] == [{"problem": "format"}]
    assert ids(store.recall()) == [rid]


def test_missing_fts5_is_a_typed_error(store, doc, monkeypatch):
    store.close()
    shutil.rmtree(store.root / ".index")
    monkeypatch.setattr(index_module, "_FTS5_CHECKED", False)
    plain = RecordStore(store.root, store.scope)
    result = plain.create(doc(), actor="t")  # writes still work
    assert plain.get(result.record_id).revision == 1
    with pytest.raises(IndexUnavailable) as caught:
        plain.recall()
    assert caught.value.code == "fts5_unavailable"
    assert "FTS5" in str(caught.value)


def test_reads_before_the_first_write_create_nothing(tmp_path):
    store = RecordStore.open(Scope("agent", "scout"), home=tmp_path / "home")
    assert store.recall().hits == ()
    assert not (tmp_path / "home").exists()


def test_time_normalization():
    assert normalize_time("2026-11-03") == "2026-11-03T00:00:00.000000Z"
    assert normalize_time("2026-11-03T12:00:00+02:00") == "2026-11-03T10:00:00.000000Z"
    assert normalize_time("2026-11-03T10:00:00.5Z") == "2026-11-03T10:00:00.500000Z"
    assert normalize_time("next tuesday") is None
    assert normalize_time(42) is None


def test_racy_directory_signatures_are_not_trusted(store, doc):
    store.create(doc(), actor="t")
    store.recall()
    months = dict(store.open_index().db.execute("SELECT month, sig FROM months"))
    # The month directory changed less than two seconds ago: rechecked next time.
    assert list(months.values()) == [None]
    old = os.stat(store.root / "2026-11").st_mtime_ns - 10 * index_module.RACY_NS
    os.utime(store.root / "2026-11", ns=(old, old))
    store.recall()
    months = dict(store.open_index().db.execute("SELECT month, sig FROM months"))
    assert list(months.values()) != [None]


def test_the_cheap_check_replays_nothing_when_nothing_changed(store, doc, monkeypatch):
    for n in range(5):
        store.create(doc(f"Decision {n}"), actor="t")
    settle(store)
    calls = count_replays(monkeypatch)
    assert len(store.recall().hits) == 5
    assert calls == []
    rid = store.recall().hits[0].record_id
    store.amend(rid, {"summary": "changed"}, expected_revision=1, actor="t")
    assert store.recall(query="changed").hits[0].record_id == rid
    assert calls == []  # the write updated the index itself
