"""The CLI's JSON contract, and promotion-policy storage."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from akms_records import RecordsError
from akms_records.cli import main


class FakeStdin(io.StringIO):
    def __init__(self, text: str = "", tty: bool = False) -> None:
        super().__init__(text)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def run(capsys, *argv: str) -> tuple[int, dict, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    out = captured.out.strip()
    return code, (json.loads(out) if out else {}), captured.err


@pytest.fixture
def cli(repo, capsys, monkeypatch):
    monkeypatch.setenv("AKMS_RECORDS_ACTOR", "tester")
    monkeypatch.setattr(sys, "stdin", FakeStdin())

    def invoke(*argv: str) -> tuple[int, dict, str]:
        return run(capsys, *argv, "--scope", "project:example", "--repo", str(repo))

    invoke("schema", "register", "--template", "decision")
    return invoke


def write_doc(tmp_path: Path, document: dict) -> str:
    path = tmp_path / "doc.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return str(path)


def test_add_show_history_list(cli, tmp_path):
    path = write_doc(tmp_path, {"payload": {"decision": "d", "rationale": "r"}})
    code, out, _ = cli("add", "--schema", "decision/v1", "--file", path, "--tag", "x")
    assert code == 0 and out["status"] == "ok" and out["revision"] == 1
    rid = out["record_id"]
    code, shown, _ = cli("show", rid)
    assert (
        shown["record"]["tags"] == ["x"]
        and shown["record"]["origin"]["actor_id"] == "tester"
    )
    code, out, _ = cli(
        "amend", rid, "--expect-revision", "1", "--review-state", "user_confirmed"
    )
    assert code == 0 and out["revision"] == 2
    code, out, err = cli("amend", rid, "--expect-revision", "1", "--summary", "late")
    assert code == 2 and "error[stale_revision]" in err
    code, history, _ = cli("history", rid)
    assert [e["kind"] for e in history["events"]] == ["create", "amend"]
    code, listing, _ = cli("list")
    assert [r["record_id"] for r in listing["records"]] == [rid]
    code, out, _ = cli(
        "supersede",
        rid,
        "--expect-revision",
        "2",
        "--file",
        path,
        "--schema",
        "decision/v1",
    )
    assert code == 0 and out["created"]["revision"] == 1
    code, out, _ = cli(
        "retract", out["superseded_by"], "--expect-revision", "1", "--reason", "x"
    )
    assert code == 0


def test_json_errors(cli, capsys, repo):
    code = main(
        [
            "--json-errors",
            "show",
            "rec-20261103-00000000",
            "--scope",
            "project:example",
            "--repo",
            str(repo),
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert code == 2 and out == {
        "status": "error",
        "error": {
            "code": "not_found",
            "message": "record rec-20261103-00000000 not found",
        },
    }


def test_doctor_check_exit_code(cli, repo):
    stray = repo / ".knowledge" / "records" / "2026-11" / "rec-20261103-zzzzzzzz"
    stray.mkdir(parents=True)
    code, out, _ = cli("doctor", "--check")
    assert code == 1 and out["status"] == "drift"


def test_export_and_import_commands(cli, tmp_path, repo, capsys):
    path = write_doc(tmp_path, {"payload": {"decision": "d", "rationale": "r"}})
    cli("add", "--schema", "decision/v1", "--file", path)
    exported = tmp_path / "out.jsonl"
    code, out, _ = cli("export", "--output", str(exported))
    assert code == 0 and out["records"] == 1 and exported.is_file()
    other = tmp_path / "other"
    other.mkdir()
    code = main(
        ["import", str(exported), "--scope", "project:example", "--repo", str(other)]
    )
    report = json.loads(capsys.readouterr().out)
    assert code == 0 and report["events_written"] == 1


def test_policy_set_needs_a_terminal_or_yes(cli, monkeypatch):
    code, _, err = cli(
        "schema",
        "policy",
        "set",
        "decision",
        "--source",
        "human",
        "--status",
        "established",
        "--confidence",
        "0.8",
    )
    assert code == 2 and "error[confirmation_required]" in err
    code, shown, _ = cli("schema", "policy", "show", "decision")
    assert shown["policy"] is None and shown["default_applies"]
    assert shown["effective"] == {
        "source": "agent",
        "status": "tentative",
        "confidence": 0.5,
    }
    assert shown["log"] == []


def test_policy_set_on_a_terminal_asks_first(cli, monkeypatch):
    monkeypatch.setattr(sys, "stdin", FakeStdin("n\n", tty=True))
    code, _, err = cli(
        "schema",
        "policy",
        "set",
        "decision",
        "--source",
        "human",
        "--status",
        "established",
        "--confidence",
        "0.8",
    )
    assert code == 2 and "not_confirmed" in err
    monkeypatch.setattr(sys, "stdin", FakeStdin("yes\n", tty=True))
    code, out, _ = cli(
        "schema",
        "policy",
        "set",
        "decision",
        "--source",
        "human",
        "--status",
        "established",
        "--confidence",
        "0.8",
    )
    assert code == 0 and out["policy"]["status"] == "established"


def test_policy_changes_are_logged_with_the_previous_value(cli):
    for status, confidence in (("tentative", "0.6"), ("established", "0.9")):
        code, _, _ = cli(
            "schema",
            "policy",
            "set",
            "decision",
            "--source",
            "human",
            "--status",
            status,
            "--confidence",
            confidence,
            "--yes",
        )
        assert code == 0
    code, shown, _ = cli("schema", "policy", "show", "decision")
    assert shown["policy"]["status"] == "established"
    log = shown["log"]
    assert [entry["previous"] for entry in log] == [
        None,
        {"source": "human", "status": "tentative", "confidence": 0.6},
    ]
    assert all(entry["actor"] == "tester" and entry["at"] for entry in log)
    code, out, _ = cli("doctor", "--check")
    assert out["policy_drift"] == {}


def test_policy_rules(store):
    with pytest.raises(RecordsError) as caught:
        store.policies.set(
            "decision",
            source="agent",
            status="established",
            confidence=0.9,
            actor="a",
            at="t",
        )
    assert caught.value.code == "invalid_policy"
    with pytest.raises(RecordsError) as caught:
        store.policies.set(
            "decision",
            source="human",
            status="tentative",
            confidence=1.5,
            actor="a",
            at="t",
        )
    assert caught.value.code == "invalid_policy"
    with pytest.raises(RecordsError) as caught:
        store.policies.show("unknown")
    assert caught.value.code == "schema_not_found"


def test_policy_change_does_not_change_the_schema_or_records(store, doc):
    rid = store.create(doc(), actor="t").record_id
    before = store.schemas.get("decision/v1").schema_sha256
    record = store.get(rid)
    store.policies.set(
        "decision",
        source="human",
        status="established",
        confidence=0.8,
        actor="p",
        at="t",
    )
    assert store.schemas.get("decision/v1").schema_sha256 == before
    assert store.get(rid) == record


def test_policy_file_edited_behind_the_log_is_reported(store):
    store.policies.set(
        "decision",
        source="human",
        status="tentative",
        confidence=0.5,
        actor="p",
        at="t1",
    )
    path = store.schemas.root / "decision" / "_policy.json"
    policy = json.loads(path.read_text(encoding="utf-8"))
    policy["status"] = "established"
    path.write_text(json.dumps(policy), encoding="utf-8")
    assert "decision" in store.doctor(fix=False)["policy_drift"]


def test_module_entry_point_help():
    result = subprocess.run(
        [sys.executable, "-m", "akms_records", "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    for command in (
        "schema",
        "add",
        "amend",
        "supersede",
        "retract",
        "show",
        "history",
        "erase",
        "doctor",
        "export",
        "import",
    ):
        assert command in result.stdout


def test_rules_commands(cli, tmp_path):
    code, shown, _ = cli("schema", "rules", "show", "decision")
    assert code == 0 and shown["schema_ref"] == "decision/v1"
    assert shown["rules"]["label"] == "/decision" and len(shown["log"]) == 1
    code, out, _ = cli(
        "schema",
        "rules",
        "set",
        "decision",
        "--label",
        "/rationale",
        "--unset",
        "time_field",
    )
    assert code == 0 and out["rules"]["label"] == "/rationale"
    assert "time_field" not in out["rules"] and out["previous"]["label"] == "/decision"
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(json.dumps({"search_text": ["/decision"]}), encoding="utf-8")
    code, out, _ = cli(
        "schema", "rules", "set", "decision/v1", "--file", str(rules_file)
    )
    assert code == 0 and out["rules"] == {"search_text": ["/decision"]}
    code, _, err = cli("schema", "rules", "set", "decision", "--label", "/missing")
    assert code == 2 and "error[invalid_rules]" in err
    code, _, err = cli("schema", "rules", "set", "decision")
    assert code == 2 and "error[usage]" in err
    code, shown, _ = cli("schema", "show", "decision")
    assert shown["schema"]["rules"] == {"search_text": ["/decision"]}
    assert shown["schema"]["rules_sha256"]
    code, shown, _ = cli("schema", "rules", "show", "decision")
    assert len(shown["log"]) == 3 and shown["set_by"] == "tester"


def test_register_takes_rules_from_options(cli, tmp_path):
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {"note": {"type": "string"}},
    }
    path = tmp_path / "note.schema.json"
    path.write_text(json.dumps(schema), encoding="utf-8")
    code, out, _ = cli(
        "schema",
        "register",
        str(path),
        "--name",
        "note",
        "--version",
        "1",
        "--summary-template",
        "Note: {note}",
        "--search-text",
        "/note",
    )
    assert code == 0 and out["rules"] == "set"
    assert out["schema"]["rules"] == {
        "search_text": ["/note"],
        "summary_template": "Note: {note}",
    }
