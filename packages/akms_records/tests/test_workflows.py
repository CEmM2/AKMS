"""Schema-neutral workflows, without live stores, external models or a network."""

import io
import json
from importlib.resources import files

import pytest

from akms_records import RecordsError, StaleRevision
from akms_records.cli import main
from akms_records.workflows import (
    draft_document,
    review_queue,
    review_record,
    validate_document,
)


@pytest.fixture
def custom(store):
    store.register_schema(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "specimen": {"$ref": "#/$defs/specimen"},
                "mode": {"enum": ["measured", "estimated"], "default": "measured"},
                "reading": {"type": "number"},
            },
            "$defs": {
                "specimen": {
                    "type": "object",
                    "properties": {"a/b~c": {"type": "string"}},
                    "required": ["a/b~c"],
                }
            },
            "required": ["specimen", "mode"],
            "if": {"properties": {"mode": {"const": "measured"}}, "required": ["mode"]},
            "then": {"required": ["reading"]},
            "additionalProperties": False,
        },
        name="custom",
        version=1,
        actor="tester",
    )
    return store


def test_draft_does_not_invent_values_or_write(custom, no_network):
    before = sorted(str(path) for path in custom.root.rglob("*"))
    result = draft_document(custom, "custom")
    assert result["document"] == {"schema_ref": "custom/v1", "payload": {}}
    assert result["missing_fields"] == [
        "/payload/mode",
        "/payload/specimen",
        "/summary",
    ]
    assert result["status"] == "ok" and not result["valid"]
    assert not list(custom.iter_records())
    assert before == sorted(str(path) for path in custom.root.rglob("*"))
    assert not no_network


def test_validation_local_refs_conditionals_and_pointer_escaping(custom):
    document = {
        "schema_ref": "custom",
        "payload": {"specimen": {}, "mode": "measured"},
        "summary": "Observation",
    }
    report = validate_document(custom, document)
    assert report["missing_fields"] == ["/payload/reading", "/payload/specimen/a~1b~0c"]
    document["payload"]["specimen"]["a/b~c"] = "sample A"
    document["payload"]["reading"] = 0
    assert validate_document(custom, document)["valid"]
    assert custom.create(document, actor="tester").revision == 1


def test_union_does_not_claim_all_branches_are_required(store):
    store.register_schema(
        {"type": "object", "oneOf": [{"required": ["left"]}, {"required": ["right"]}]},
        name="choice",
        version=1,
        actor="tester",
    )
    result = draft_document(store, "choice", document={"summary": "Known summary"})
    assert not result["valid"] and result["missing_fields"] == []
    assert result["errors"][0]["code"] == "payload_invalid"


def test_validation_preserves_envelope_checks(store, doc):
    assert not validate_document(store, doc(record_id="forged"))["valid"]
    assert not validate_document(
        store, doc(source_refs=[{"kind": "promoted-to", "ref": "x@1"}])
    )["valid"]
    assert not validate_document(store, doc(payload={"summary": "shadow"}))["valid"]
    assert validate_document(store, doc())["valid"]


def test_review_queue_filters_and_checked_review(store, doc):
    first = store.create(doc(), actor="tester")
    store.create(doc(sensitivity="sensitive"), actor="tester")
    rejected = store.create(doc(review_state="rejected"), actor="tester")
    retracted = store.create(doc(), actor="tester")
    store.retract(
        retracted.record_id, expected_revision=1, actor="tester", reason="obsolete"
    )
    assert [r["record_id"] for r in review_queue(store)["records"]] == [first.record_id]
    result = review_queue(store, include_sensitive=True, limit=1)
    assert result["has_more"] and result["total"] == 2
    assert review_queue(store, schema="other")["total"] == 0
    assert (
        review_queue(store, state="rejected")["records"][0]["record_id"]
        == rejected.record_id
    )
    before = store.get(first.record_id).payload
    review_record(
        store,
        first.record_id,
        state="agent_reviewed",
        expected_revision=1,
        actor="reviewer",
        event_id="review-1",
    )
    assert store.get(first.record_id).payload == before
    assert store.history(first.record_id)[-1]["actor"] == "reviewer"
    assert review_record(
        store,
        first.record_id,
        state="agent_reviewed",
        expected_revision=1,
        actor="reviewer",
        event_id="review-1",
    ).noop
    with pytest.raises(StaleRevision):
        review_record(
            store,
            first.record_id,
            state="user_confirmed",
            expected_revision=1,
            actor="person",
        )
    assert store.get(first.record_id).revision == 2
    with pytest.raises(RecordsError):
        review_queue(store, limit=0)


def test_cli_author_search_review(custom, repo, tmp_path, capsys, monkeypatch):
    base = ["--scope", "project:example", "--repo", str(repo)]

    def run(*args):
        code = main([*args, *base])
        return code, capsys.readouterr()

    code, output = run("draft", "--schema", "custom", "--format", "document")
    candidate = json.loads(output.out)
    assert code == 0 and candidate["payload"] == {}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(candidate)))
    code, output = run("validate", "--file", "-")
    assert code == 1 and not json.loads(output.out)["valid"]
    payload = tmp_path / "payload.json"
    payload.write_text(
        json.dumps({"specimen": {"a/b~c": "sample"}, "mode": "estimated"})
    )
    code, output = run(
        "add",
        "--schema",
        "custom",
        "--payload",
        str(payload),
        "--summary",
        "Sample observation",
    )
    assert code == 0, output
    rid = json.loads(output.out)["record_id"]
    code, output = run("search", "sample", "--format", "text")
    assert code == 0 and rid in output.out
    code, output = run("search", "nonexistentterm", "--format", "text")
    assert code == 0 and rid not in output.out
    code, output = run("show", rid, "--format", "text")
    assert code == 0 and '"mode": "estimated"' in output.out
    code, output = run("review", "queue")
    assert code == 0 and json.loads(output.out)["records"][0]["revision"] == 1
    code, output = run(
        "review", "set", rid, "--state", "user_confirmed", "--expect-revision", "1"
    )
    assert code == 0 and json.loads(output.out)["revision"] == 2
    code, output = run("review", "queue", "--format", "text")
    assert code == 0 and '"total": 0' in output.out
    code, output = run("search", "sample", "--query", "other")
    assert code == 2 and "usage" in output.err


def test_bundled_skill():
    text = files("akms_records").joinpath("skills/akms-records/SKILL.md").read_text()
    assert "schema show" in text and "--expect-revision" in text


def test_queue_reports_partial_scan_and_does_not_read_other_scope(
    store, make_store, doc
):
    healthy = store.create(doc(), actor="tester")
    broken = store.create(doc(), actor="tester")
    event = store.record_dir(broken.record_id) / "000001.json"
    event.write_text("broken", encoding="utf-8")
    other = make_store("project:other")
    other_record = other.create(doc(), actor="tester")
    report = review_queue(store)
    assert report["status"] == "error" and report["replay_errors"]
    assert [row["record_id"] for row in report["records"]] == [healthy.record_id]
    assert other_record.record_id not in str(report["records"])


def test_draft_copies_input_and_validation_matches_create(custom):
    document = {
        "payload": {"mode": "estimated", "specimen": {"a/b~c": "S"}},
        "summary": "Known",
    }
    result = draft_document(custom, "custom", document=document)
    assert result["valid"]
    result["document"]["payload"]["mode"] = "measured"
    assert document["payload"]["mode"] == "estimated"
    invalid = {"schema_ref": "custom/v1", **document, "payload": {"mode": "unexpected"}}
    assert not validate_document(custom, invalid)["valid"]
    with pytest.raises(RecordsError):
        custom.create(invalid, actor="tester")


@pytest.mark.parametrize("erased", [False, True])
def test_withdraw_cli_forwards_explicit_scope_revision_and_confirmation(
    repo, capsys, monkeypatch, erased
):
    from akms_records import bridge

    calls = []

    def fake_withdraw(store, record_id, **kwargs):
        calls.append((str(store.scope), record_id, kwargs))
        return {"status": "ok", "action": "withdraw"}

    monkeypatch.setattr(bridge, "withdraw_promotion", fake_withdraw, raising=False)
    args = [
        "promotion",
        "withdraw",
        "rec-example",
        "--scope",
        "project:example",
        "--repo",
        str(repo),
        "--reason",
        "obsolete",
        "--actor",
        "reviewer",
        "--yes",
    ]
    args += ["--erased"] if erased else ["--expect-revision", "3"]
    assert main(args) == 0
    assert json.loads(capsys.readouterr().out)["action"] == "withdraw"
    scope, rid, options = calls[0]
    assert scope == "project:example" and rid == "rec-example"
    assert options["repo"] == repo and options["reason"] == "obsolete"
    assert options["actor"] == "reviewer" and options["erased"] == erased
    assert options["expected_revision"] == (None if erased else 3)
    assert options["confirm"] is bridge.confirm_yes


def test_withdraw_requires_revision_or_erasure(repo, capsys):
    base = [
        "promotion",
        "withdraw",
        "rec-example",
        "--scope",
        "project:example",
        "--repo",
        str(repo),
        "--reason",
        "obsolete",
    ]
    with pytest.raises(SystemExit):
        main(base)
    with pytest.raises(SystemExit):
        main([*base, "--erased", "--expect-revision", "1"])
    capsys.readouterr()


@pytest.mark.parametrize(
    "action,verb", [("replace", "Replace"), ("withdraw", "Withdraw")]
)
def test_promotion_confirmation_names_actual_action(monkeypatch, capsys, action, verb):
    from akms_records.cli import _ask_for_promotion

    monkeypatch.setattr("sys.stdin", io.StringIO("yes\n"))
    assert (
        _ask_for_promotion(
            {
                "action": action,
                "record_id": "rec-example",
                "revision": None,
                "node_id": "node-example",
                "source": "human",
                "status": "tentative",
                "confidence": 0.5,
            }
        )
        == "tty"
    )
    prompt = capsys.readouterr().err
    assert verb in prompt and "rec-example" in prompt and "@None" not in prompt
