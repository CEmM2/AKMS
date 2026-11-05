"""What an amend does to a record's summary and review state."""

from __future__ import annotations

import json

import pytest

from akms_records import RecordsError, wake
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


# ------------------------------------------------------------------ review state
def owned(store, state="user_confirmed", kind="human-confirmed"):
    return add(
        store,
        actor="owner",
        review_state=state,
        origin={"kind": kind, "actor_id": "owner"},
    )


@pytest.mark.parametrize("state", ["user_confirmed", "agent_reviewed"])
def test_an_agents_payload_change_resets_a_review(store, state):
    rid = owned(store, state)
    store.amend(rid, new_payload(), expected_revision=1, actor="some-agent")
    record = store.get(rid)
    assert record.review_state == "unreviewed"
    assert record.origin == {"kind": "human-confirmed", "actor_id": "owner"}


def test_an_agents_summary_or_origin_change_resets_a_review(store):
    rid = owned(store)
    store.amend(rid, {"summary": "Other words"}, expected_revision=1, actor="agent")
    assert store.get(rid).review_state == "unreviewed"
    other = owned(store)
    store.amend(
        other,
        {"origin": {"kind": "human", "actor_id": "agent"}},
        expected_revision=1,
        actor="agent",
    )
    assert store.get(other).review_state == "unreviewed"


def test_an_agent_cannot_make_itself_the_person_in_one_amend(store):
    rid = owned(store)
    store.amend(
        rid,
        {**new_payload(), "origin": {"kind": "human", "actor_id": "agent"}},
        expected_revision=1,
        actor="agent",
    )
    assert store.get(rid).review_state == "unreviewed"


def test_the_records_person_keeps_the_state(store):
    for kind in ("human", "human-confirmed"):
        rid = owned(store, kind=kind)
        store.amend(rid, new_payload(), expected_revision=1, actor="owner")
        assert store.get(rid).review_state == "user_confirmed"


def test_an_agent_origin_never_counts_as_a_person(store):
    rid = add(store, actor="scout", review_state="user_confirmed")
    assert store.get(rid).origin == {"kind": "agent", "actor_id": "scout"}
    store.amend(rid, new_payload(), expected_revision=1, actor="scout")
    assert store.get(rid).review_state == "unreviewed"


def test_amends_that_change_no_content_keep_the_state(store):
    rid = owned(store)
    revision = 1
    for fields in (
        {"tags": ["x"]},
        {"source_refs": [{"kind": "issue", "ref": "#1"}]},
        {"sensitivity": "public"},
        {"payload": store.get(rid).payload},
        {"summary": store.get(rid).summary},
    ):
        store.amend(rid, fields, expected_revision=revision, actor="some-agent")
        revision += 1
        assert store.get(rid).review_state == "user_confirmed", fields


def test_a_rejection_survives_an_agents_edit(store):
    rid = owned(store, "rejected")
    store.amend(rid, new_payload(), expected_revision=1, actor="some-agent")
    assert store.get(rid).review_state == "rejected"


def test_an_unreviewed_record_stays_unreviewed(store):
    rid = add(store)
    store.amend(rid, new_payload(), expected_revision=1, actor="a")
    assert store.get(rid).review_state == "unreviewed"


def test_an_agent_cannot_reassert_user_confirmed_with_its_edit(store):
    rid = owned(store)
    with pytest.raises(RecordsError) as caught:
        store.amend(
            rid,
            {**new_payload(), "review_state": "user_confirmed"},
            expected_revision=1,
            actor="some-agent",
        )
    assert caught.value.code == "review_reassert"
    assert store.get(rid).revision == 1
    assert store.get(rid).payload["decision"] == "Use a global store lock"


@pytest.mark.parametrize("named", ["agent_reviewed", "unreviewed"])
def test_an_agent_can_state_a_lesser_review_with_its_edit(store, named):
    rid = owned(store)
    store.amend(
        rid,
        {**new_payload(), "review_state": named},
        expected_revision=1,
        actor="some-agent",
    )
    assert store.get(rid).review_state == named


def test_the_records_person_can_name_user_confirmed_with_an_edit(store):
    rid = owned(store, "agent_reviewed")
    store.amend(
        rid,
        {**new_payload(), "review_state": "user_confirmed"},
        expected_revision=1,
        actor="owner",
    )
    assert store.get(rid).review_state == "user_confirmed"


def test_confirming_later_in_a_separate_amend_is_visible_in_history(store):
    rid = owned(store)
    store.amend(rid, new_payload(), expected_revision=1, actor="some-agent")
    store.amend(
        rid, {"review_state": "user_confirmed"}, expected_revision=2, actor="owner"
    )
    assert store.get(rid).review_state == "user_confirmed"
    assert [event["actor"] for event in store.history(rid)] == [
        "owner",
        "some-agent",
        "owner",
    ]


def test_a_promotion_link_resets_nothing(store):
    rid = add(store, actor="scout", review_state="user_confirmed")
    store.record_promotion(
        rid,
        node_id="a-node",
        revision=1,
        path="default",
        expected_revision=1,
        actor="some-agent",
    )
    record = store.get(rid)
    assert record.review_state == "user_confirmed"
    assert record.promoted_to["node_id"] == "a-node"
    assert record.summary == "Decision: Use a global store lock"


def test_a_cli_amend_follows_the_same_rule(store, repo, capsys, tmp_path):
    from akms_records.cli import main

    rid = owned(store)
    doc = tmp_path / "doc.json"
    doc.write_text(json.dumps(new_payload()), encoding="utf-8")
    base = ["--scope", "project:example", "--repo", str(repo)]
    args = ["amend", rid, *base, "--file", str(doc), "--expect-revision", "1"]
    code = main([*args, "--actor", "some-agent", "--review-state", "user_confirmed"])
    assert code == 2 and "error[review_reassert]" in capsys.readouterr().err
    assert main([*args, "--actor", "some-agent"]) == 0
    capsys.readouterr()
    assert store.get(rid).review_state == "unreviewed"
