"""What an amend does to a record's summary and review state."""

from __future__ import annotations

import pytest

from akms_records import wake
from akms_records.schemas import load_template


@pytest.fixture
def store(make_store, clock):
    opened = make_store(clock=clock())
    opened.register_schema(load_template("decision"), actor="owner")
    yield opened
    opened.close()


def add(store, text="Use a global store lock", *, actor="a", **extra):
    payload = {"decision": text, "rationale": "because"}
    return store.create(
        {"schema_ref": "decision/v1", "payload": payload, **extra}, actor=actor
    ).record_id


def new_payload(text="Use no lock"):
    return {"payload": {"decision": text, "rationale": "because"}}


def wake_text(repo, tmp_path, agent="a", task="lock"):
    return wake(
        agent=agent,
        task=task,
        budget_tokens=600,
        scopes=["project:example"],
        repo=repo,
        home=tmp_path / "home",
    ).render_markdown()


# --------------------------------------------------------------------- summaries
def test_a_template_summary_follows_a_payload_amend(store, repo, tmp_path):
    rid = add(store)
    assert store.get(rid).summary == "Decision: Use a global store lock"
    store.amend(rid, new_payload(), expected_revision=1, actor="a")
    assert store.get(rid).summary == "Decision: Use no lock"
    assert store.recall("lock").hits[0].summary == "Decision: Use no lock"
    assert store.recall("global").hits == ()
    text = wake_text(repo, tmp_path)
    assert "Use no lock" in text and "global store lock" not in text


def test_a_written_summary_stays(store):
    rid = add(store, summary="My own words about locks")
    store.amend(rid, new_payload(), expected_revision=1, actor="a")
    assert store.get(rid).summary == "My own words about locks"


def test_a_summary_named_in_the_amend_wins(store):
    rid = add(store)
    store.amend(
        rid,
        {**new_payload(), "summary": "Written with the change"},
        expected_revision=1,
        actor="a",
    )
    assert store.get(rid).summary == "Written with the change"
    store.amend(rid, new_payload("Again"), expected_revision=2, actor="a")
    assert store.get(rid).summary == "Written with the change"


def test_only_a_payload_change_regenerates(store):
    rid = add(store, summary="Decision: Use a global store lock")
    store.amend(rid, {"tags": ["x"]}, expected_revision=1, actor="a")
    assert store.get(rid).summary == "Decision: Use a global store lock"
    same = {"decision": "Use a global store lock", "rationale": "because"}
    store.amend(rid, {"payload": same}, expected_revision=2, actor="a")
    assert store.get(rid).summary == "Decision: Use a global store lock"


def test_a_summary_left_behind_by_an_older_amend_heals_on_the_next(store):
    rid = add(store)
    # What an amend used to leave: the new payload with the old template text.
    store.amend(
        rid,
        {**new_payload("Second"), "summary": "Decision: Use a global store lock"},
        expected_revision=1,
        actor="a",
    )
    assert store.get(rid).summary == "Decision: Use a global store lock"
    store.amend(rid, new_payload("Third"), expected_revision=2, actor="a")
    assert store.get(rid).summary == "Decision: Third"


def test_a_template_changed_since_the_create_is_still_recognized(store):
    rid = add(store)
    store.set_rules(
        "decision/v1", {"summary_template": "Chosen: {decision}"}, actor="o"
    )
    store.amend(rid, new_payload(), expected_revision=1, actor="a")
    assert store.get(rid).summary == "Chosen: Use no lock"


def test_a_template_that_renders_nothing_keeps_the_summary(store):
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"note": {"type": "string"}, "other": {"type": "string"}},
        "x-akms-records": {
            "name": "sparse",
            "version": 1,
            "rules": {"summary_template": "{note}"},
        },
    }
    store.register_schema(schema, actor="o")
    rid = store.create(
        {"schema_ref": "sparse/v1", "payload": {"note": "First note"}}, actor="a"
    ).record_id
    store.amend(rid, {"payload": {"other": "x"}}, expected_revision=1, actor="a")
    assert store.get(rid).summary == "First note"


def test_regenerating_keeps_the_events_before_it_and_a_replay_agrees(store):
    from akms_records.store import read_event_files

    rid = add(store)
    first = read_event_files(store.record_dir(rid), rid, strict=True)[0][1]
    store.amend(rid, new_payload(), expected_revision=1, actor="a")
    pairs = read_event_files(store.record_dir(rid), rid, strict=True)
    assert pairs[0][1] == first
    assert pairs[1][0]["body"]["envelope"]["summary"] == "Decision: Use no lock"
    assert store.doctor()["status"] == "ok"
