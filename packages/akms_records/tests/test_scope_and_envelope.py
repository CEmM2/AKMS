"""Scope isolation, store roots, and the reserved envelope."""

from __future__ import annotations

from pathlib import Path

import pytest

from akms_records import RecordStore, RecordsError, Scope, ScopeViolation, store_root
from akms_records.envelope import ENVELOPE_KEYS
from akms_records.schemas import load_template


def test_project_root_follows_the_knowledge_dir_rule(tmp_path: Path):
    repo = tmp_path / "r"
    repo.mkdir()
    scope = Scope("project", "p")
    assert store_root(scope, repo=repo) == repo / ".knowledge" / "records"
    (repo / "knowledge").mkdir()
    assert store_root(scope, repo=repo) == repo / "knowledge" / "records"
    (repo / ".knowledge").mkdir()
    assert store_root(scope, repo=repo) == repo / ".knowledge" / "records"


def test_agent_and_shared_roots_honour_the_home_override(tmp_path, monkeypatch):
    monkeypatch.setenv("AKMS_RECORDS_HOME", str(tmp_path / "home"))
    assert store_root(Scope("agent", "scout")) == tmp_path / "home" / "agent" / "scout"
    assert store_root(Scope("shared", "team")) == tmp_path / "home" / "shared" / "team"
    monkeypatch.delenv("AKMS_RECORDS_HOME")
    assert store_root(Scope("agent", "scout")) == (
        Path.home() / ".knowledge" / "records" / "agent" / "scout"
    )


@pytest.mark.parametrize(
    "text", ["project", "team:x", "agent:", "agent:../x", "agent:a/b"]
)
def test_bad_scopes_are_refused(text):
    with pytest.raises(RecordsError) as caught:
        Scope.parse(text)
    assert caught.value.code == "invalid_scope"


def test_api_enforces_scope_isolation(make_store, doc):
    mine = make_store("project:alpha")
    mine.register_schema(load_template("decision"), actor="t")
    other = make_store("project:beta")
    rid = mine.create(doc(), actor="t").record_id
    other_rid = other.create(doc("beta's"), actor="t").record_id
    with pytest.raises(ScopeViolation):
        other.get(rid)
    with pytest.raises(ScopeViolation):
        other.history(rid)
    with pytest.raises(ScopeViolation):
        other.amend(rid, {"summary": "x"}, expected_revision=1, actor="t")
    with pytest.raises(ScopeViolation):
        other.retract(rid, expected_revision=1, reason="x", actor="t")
    with pytest.raises(ScopeViolation):
        other.supersede(rid, expected_revision=1, actor="t", by=other_rid)
    with pytest.raises(ScopeViolation):
        mine.supersede(rid, expected_revision=1, actor="t", by=other_rid)
    with pytest.raises(ScopeViolation):
        other.erase(rid, reason="x", actor="t")
    assert [r.record_id for r in mine.iter_records()] == [rid]
    assert [r.record_id for r in other.iter_records()] == [other_rid]
    with pytest.raises(RecordsError) as caught:
        mine.create({**doc(), "scope": {"kind": "project", "id": "beta"}}, actor="t")
    assert caught.value.code == "scope_violation"
    with pytest.raises(RecordsError) as caught:
        other.create(doc(), actor="t", event_id=mine.history(rid)[0]["event_id"])
    assert caught.value.code == "event_id_reused"


def test_agent_scopes_live_in_separate_roots(tmp_path, monkeypatch, doc):
    monkeypatch.setenv("AKMS_RECORDS_HOME", str(tmp_path / "home"))
    scout = RecordStore.open("agent:scout")
    critic = RecordStore.open("agent:critic")
    assert scout.root != critic.root
    scout.register_schema(load_template("decision"), actor="t")
    rid = scout.create(doc(), actor="scout").record_id
    with pytest.raises(RecordsError) as caught:
        critic.get(rid)
    assert caught.value.code == "not_found"


@pytest.mark.parametrize(
    "key", ["summary", "record_id", "scope", "lifecycle", "payload"]
)
def test_payload_cannot_shadow_envelope_keys(store, doc, key):
    document = doc()
    document["payload"][key] = "shadow"
    with pytest.raises(RecordsError) as caught:
        store.create(document, actor="t")
    assert caught.value.code == "envelope_shadow"
    assert key in ENVELOPE_KEYS


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"record_id": "rec-20261103-00000000"}, "set by the store"),
        ({"revision": 7}, "set by the store"),
        ({"schema_sha256": "0" * 64}, "set by the store"),
        ({"lifecycle": "retracted"}, "set by the store"),
        ({"decision": "flat"}, "unknown top-level fields"),
        ({"tags": ["a", "a"]}, "duplicate tag"),
        ({"sensitivity": "top-secret"}, "sensitivity"),
        ({"origin": {"kind": "oracle", "actor_id": "x"}}, "origin.kind"),
        ({"source_refs": [{"kind": "doc"}]}, "kind and ref"),
    ],
)
def test_envelope_input_is_validated(store, doc, extra, message):
    with pytest.raises(RecordsError, match=message):
        store.create({**doc(), **extra}, actor="t")
    assert store.record_ids() == []


def test_symlinked_store_root_is_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(RecordsError) as caught:
        RecordStore(link, Scope("project", "p"))
    assert caught.value.code == "store_path"


def test_reads_do_not_create_the_store(make_store):
    store = make_store()
    assert list(store.iter_records()) == []
    assert store.doctor()["status"] == "ok"
    assert not store.root.exists()
