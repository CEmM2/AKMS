"""The promotion bridge into AKMS project-local nodes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("akms")

import frontmatter  # noqa: E402
from akms.graph.build_graph import load_graph  # noqa: E402
from akms.graph.record_projections import parse_projections  # noqa: E402
from akms.layout import local_knowledge_dir  # noqa: E402
from akms.schema.models import LocalNodeFrontmatter  # noqa: E402
from akms.schema.validators import parse_node_frontmatter  # noqa: E402

from akms_records import RecordsError, RecordStore, Scope, consolidate  # noqa: E402
from akms_records.bridge import confirm_yes, find_nodes, _load_akms, promote  # noqa: E402
from akms_records.cli import main  # noqa: E402
from akms_records.envelope import PROMOTED_KIND  # noqa: E402
from akms_records.portable import export_records, import_records  # noqa: E402
from akms_records.schemas import load_template  # noqa: E402
from akms_records.store import read_event_files  # noqa: E402

# A person's record, so that actor "t" keeps its review through an amend.
CONFIRMED = {
    "review_state": "user_confirmed",
    "origin": {"kind": "human-confirmed", "actor_id": "t"},
}


def tree(path: Path) -> dict[str, bytes]:
    return {
        str(item.relative_to(path)): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


@pytest.fixture(autouse=True)
def vault(tmp_path, monkeypatch):
    """A global vault with one node, so the guard has bytes to protect."""
    path = tmp_path / "vault"
    path.mkdir()
    (path / "global-node.md").write_text(
        "---\nid: global-node\ntitle: Global\ndomain: general\ntags: [general]\n"
        "status: established\nconfidence: 0.9\nsource: human\nakms_schema: v2\n"
        "---\nbody\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(path))
    return path


@pytest.fixture
def project(make_store, clock):
    store = make_store(clock=clock())
    store.register_schema(load_template("decision"), actor="t")
    yield store
    store.close()


def add(store, text="Keep the coarse mesh", *, rationale="within budget", **extra):
    payload = {"decision": text, "rationale": rationale}
    return store.create(
        {"schema_ref": "decision/v1", "payload": payload, **extra}, actor="t"
    ).record_id


def run(store, record_id, repo, **options):
    options.setdefault("review", "approved")
    options.setdefault("actor", "reviewer")
    return promote(store, record_id, repo=repo, **options)


def set_policy(store, name="decision", **value):
    return store.policies.set(
        name,
        source=value.get("source", "human"),
        status=value.get("status", "established"),
        confidence=value.get("confidence", 0.8),
        actor="person",
        at=store.now(),
    )


def node_files(repo: Path) -> list[Path]:
    folder = local_knowledge_dir(repo) / "local-nodes"
    return sorted(folder.rglob("*.md")) if folder.is_dir() else []


def body_of(path: Path) -> str:
    return str(frontmatter.load(str(path)).content)


def projected_bodies(raw: bytes) -> list[str]:
    """Crash repair may refresh source fingerprints, never the projected facts."""
    body = str(frontmatter.loads(raw.decode("utf-8")).content)
    return [block.body for block in parse_projections(body)]


# ------------------------------------------------------------- the default path
def test_default_path_writes_an_agent_tentative_node(project, repo, no_network):
    source = {"kind": "issue", "ref": "#42"}
    rid = add(project, source_refs=[source], tags=["mesh"], **CONFIRMED)
    result = run(project, rid, repo)
    assert result["action"] == "created"
    assert result["node_id"] == rid
    assert result["path"] == "default"
    assert result["revision"] == 1
    assert result["node"] == {
        "source": "agent",
        "status": "tentative",
        "confidence": 0.5,
    }
    assert result["policy"]["applied"] is False
    assert result["policy"]["reason"] == "no_policy"
    [path] = node_files(repo)
    node = parse_node_frontmatter(path, is_local=True)
    assert isinstance(node, LocalNodeFrontmatter)
    assert node.title == "Keep the coarse mesh"
    assert node.tags == ["mesh", "decision"]
    assert node.domain == "example"
    body = body_of(path)
    assert "Decision: Keep the coarse mesh" in body
    assert '"rationale": "within budget"' in body
    assert f"- record: `{rid}@1`" in body
    assert "- schema: `decision/v1`" in body
    assert f"- schema_sha256: `{project.get(rid).schema_sha256}`" in body
    assert 'origin: human-confirmed "t"' in body
    assert '"ref": "#42"' in body
    graph = load_graph(local_knowledge_dir(repo) / "graph" / "graph.json")
    assert graph.nodes[rid]["node_origin"] == "local"
    assert no_network == []


def test_link_is_an_amend_that_changes_nothing_else(project, repo):
    rid = add(project, tags=["mesh"], **CONFIRMED)
    before = project.get(rid)
    result = run(project, rid, repo, actor="reviewer")
    after = project.get(rid)
    assert result["link"]["kind"] == "amend" and result["link"]["revision"] == 2
    assert after.promoted_to == {"node_id": rid, "revision": 1, "path": "default"}
    assert after.state_json()["promoted_to"] == after.promoted_to
    assert after.payload == before.payload
    assert after.summary == before.summary
    assert after.schema_sha256 == before.schema_sha256
    assert [r for r in after.source_refs if r["kind"] != PROMOTED_KIND] == []
    assert project.history(rid)[-1]["actor"] == "reviewer"
    assert after.content_revision == 1
    assert after.content_sha256 == before.head_sha256


def test_update_graph_dedup_is_reported_and_linked(project, repo):
    words = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu"
    long = " ".join(words.split() * 4)
    first = add(project, "Mesh rule " + long, rationale=long, **CONFIRMED)
    second = add(project, "Mesh rule " + long + " again", rationale=long, **CONFIRMED)
    assert run(project, first, repo)["action"] == "created"
    result = run(project, second, repo)
    assert result["action"] == "dedup_appended"
    assert result["node_id"] == first
    assert result["details"]["score"] > result["details"]["threshold"]
    assert project.get(second).promoted_to["node_id"] == first
    [path] = node_files(repo)
    body = body_of(path)
    assert f"- record: `{first}@1`" in body and f"- record: `{second}@1`" in body


def test_custom_domain_and_title_from_a_long_summary(project, repo):
    rid = add(project, "word " * 80, **CONFIRMED)
    result = run(project, rid, repo, domain="numerics")
    node = parse_node_frontmatter(Path(result["node_file"]), is_local=True)
    assert node.domain == "numerics"
    assert len(node.title) <= 120


# ---------------------------------------------------------- the human-policy path
def test_human_policy_writes_a_validated_node(project, repo):
    set_policy(project, status="established", confidence=0.8)
    policy_dir = project.schemas.root / "decision"
    policy_before = tree(policy_dir)
    rid = add(project, tags=["mesh"], **CONFIRMED)
    result = run(project, rid, repo, confirm=confirm_yes)
    assert result["action"] == "created"
    assert result["path"] == "human-policy"
    assert result["policy"]["applied"] is True
    assert result["node"] == {
        "source": "human",
        "status": "established",
        "confidence": 0.8,
    }
    [path] = node_files(repo)
    node = parse_node_frontmatter(path, is_local=True)
    assert isinstance(node, LocalNodeFrontmatter)
    assert (node.source.value, node.status.value) == ("human", "established")
    graph = load_graph(local_knowledge_dir(repo) / "graph" / "graph.json")
    assert graph.nodes[rid]["node_origin"] == "local"
    assert graph.nodes[rid]["confidence"] == 0.8
    assert project.get(rid).promoted_to["path"] == "human-policy"
    # Promotion read the policy and did not change it.
    assert tree(policy_dir) == policy_before
    assert len(project.policies.log("decision")) == 1


def test_human_policy_tentative_keeps_its_confidence(project, repo):
    set_policy(project, status="tentative", confidence=0.65)
    rid = add(project, **CONFIRMED)
    result = run(project, rid, repo, confirm=confirm_yes)
    assert result["node"] == {
        "source": "human",
        "status": "tentative",
        "confidence": 0.65,
    }


def test_human_policy_applies_only_to_human_confirmed_records(project, repo):
    set_policy(project)
    rid = add(project, review_state="agent_reviewed")
    result = run(project, rid, repo, min_review_state="agent_reviewed")
    assert result["path"] == "default"
    assert result["node"]["source"] == "agent"
    assert result["node"]["status"] == "tentative"
    assert result["policy"]["reason"] == "record_not_human_confirmed"


def test_agent_policy_stays_on_the_default_path(project, repo):
    set_policy(project, source="agent", status="tentative", confidence=0.9)
    rid = add(project, **CONFIRMED)
    result = run(project, rid, repo)
    assert result["path"] == "default"
    assert result["node"]["confidence"] == 0.5  # never inflated
    assert result["policy"]["reason"] == "agent_policy"


def test_a_policy_edited_outside_the_log_is_refused(project, repo):
    set_policy(project, status="tentative")
    path = project.schemas.root / "decision" / "_policy.json"
    data = json.loads(path.read_bytes())
    data["status"] = "established"
    path.write_text(json.dumps(data), encoding="utf-8")
    rid = add(project, **CONFIRMED)
    with pytest.raises(RecordsError) as caught:
        run(project, rid, repo)
    assert caught.value.code == "policy_drift"
    assert node_files(repo) == []


def test_policy_cannot_be_set_through_the_promote_command(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["promote", "x", "--scope", "project:a", "--status", "established"])
    assert caught.value.code == 2
    capsys.readouterr()


# ------------------------------------------------------------- the confirmation
def knowledge_files(repo: Path) -> dict[str, bytes]:
    """Everything under the knowledge directory except the record store."""
    root = local_knowledge_dir(repo)
    return {
        name: data
        for name, data in tree(root).items()
        if not name.startswith("records")
    }


class FakeTerminal:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.read = False

    def isatty(self) -> bool:
        return True

    def readline(self) -> str:
        self.read = True
        return self.answer


class NoTerminal:
    def isatty(self) -> bool:
        return False

    def readline(self) -> str:
        raise AssertionError("no terminal to read")


def human_cli(repo, rid, *extra):
    return [
        "promote",
        rid,
        "--scope",
        "project:example",
        "--repo",
        str(repo),
        "--review",
        "approved",
        *extra,
    ]


def test_the_human_path_is_refused_without_confirmation(project, repo):
    set_policy(project)
    rid = add(project, **CONFIRMED)
    before = tree(project.root)
    with pytest.raises(RecordsError) as caught:
        run(project, rid, repo)
    assert caught.value.code == "confirmation_required"
    assert "--yes" in str(caught.value) and "terminal" in str(caught.value)
    assert "fall back" in str(caught.value)
    assert knowledge_files(repo) == {}
    assert tree(project.root) == before
    assert project.get(rid).revision == 1
    # Nothing was written at all: no lock directory either.
    assert not (project.root / ".index" / "promote.lock").exists()


def test_the_cli_refuses_without_a_terminal_or_yes(project, repo, capsys, monkeypatch):
    set_policy(project)
    rid = add(project, **CONFIRMED)
    monkeypatch.setattr("sys.stdin", NoTerminal())
    code = main(["--json-errors", *human_cli(repo, rid)])
    error = json.loads(capsys.readouterr().out)["error"]
    assert code == 2 and error["code"] == "confirmation_required"
    assert error["details"]["node_id"] == rid
    assert knowledge_files(repo) == {}
    assert project.get(rid).promoted_to is None


def test_the_cli_yes_confirms_and_records_it(project, repo, capsys, monkeypatch):
    set_policy(project)
    rid = add(project, **CONFIRMED)
    monkeypatch.setattr("sys.stdin", NoTerminal())
    assert main(human_cli(repo, rid, "--yes")) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["path"] == "human-policy"
    assert result["confirmation"] == "yes"
    assert result["node"]["status"] == "established"
    assert "- confirmation: yes" in body_of(node_files(repo)[0])


@pytest.mark.parametrize("answer", ["y\n", "yes\n", "YES\n"])
def test_a_terminal_yes_shows_the_labels_and_records_it(
    project, repo, capsys, monkeypatch, answer
):
    set_policy(project, status="established", confidence=0.8)
    rid = add(project, **CONFIRMED)
    terminal = FakeTerminal(answer)
    monkeypatch.setattr("sys.stdin", terminal)
    assert main(human_cli(repo, rid)) == 0
    captured = capsys.readouterr()
    assert terminal.read
    for shown in (rid, "source=human", "status=established", "confidence=0.8"):
        assert shown in captured.err
    assert json.loads(captured.out)["confirmation"] == "tty"
    assert "- confirmation: tty" in body_of(node_files(repo)[0])


@pytest.mark.parametrize("answer", ["n\n", "\n", "", "maybe\n", "yes please\n"])
def test_anything_but_yes_on_a_terminal_writes_nothing(
    project, repo, capsys, monkeypatch, answer
):
    set_policy(project)
    rid = add(project, **CONFIRMED)
    monkeypatch.setattr("sys.stdin", FakeTerminal(answer))
    code = main(["--json-errors", *human_cli(repo, rid)])
    assert code == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "not_confirmed"
    assert knowledge_files(repo) == {}
    assert project.get(rid).promoted_to is None


def test_the_python_api_never_reads_a_terminal(project, repo, monkeypatch):
    set_policy(project)
    rid = add(project, **CONFIRMED)
    terminal = FakeTerminal("yes\n")
    monkeypatch.setattr("sys.stdin", terminal)
    with pytest.raises(RecordsError) as caught:
        run(project, rid, repo)
    assert caught.value.code == "confirmation_required"
    assert terminal.read is False
    assert run(project, rid, repo, confirm=confirm_yes)["confirmation"] == "yes"


def test_a_confirm_callable_sees_the_write_and_may_refuse(project, repo):
    set_policy(project, status="tentative", confidence=0.6)
    rid = add(project, **CONFIRMED)
    seen = []

    def refuse(write):
        seen.append(write)
        raise RecordsError("no", code="not_confirmed")

    with pytest.raises(RecordsError) as caught:
        run(project, rid, repo, confirm=refuse)
    assert caught.value.code == "not_confirmed"
    assert seen == [
        {
            "record_id": rid,
            "revision": 1,
            "action": "create",
            "node_id": rid,
            "source": "human",
            "status": "tentative",
            "confidence": 0.6,
        }
    ]
    assert knowledge_files(repo) == {}
    with pytest.raises(RecordsError) as caught:
        run(project, rid, repo, confirm=lambda _write: "certainly")
    assert caught.value.code == "usage"
    assert knowledge_files(repo) == {}


def test_a_policy_changed_during_the_prompt_is_stale(project, repo):
    set_policy(project, status="established", confidence=0.8)
    rid = add(project, **CONFIRMED)

    def change_it(_write):
        set_policy(project, status="tentative", confidence=0.3)
        return "tty"

    with pytest.raises(RecordsError) as caught:
        run(project, rid, repo, confirm=change_it)
    assert caught.value.code == "confirmation_stale"
    assert node_files(repo) == []


def test_the_default_path_needs_no_confirmation(project, repo, capsys, monkeypatch):
    rid = add(project, **CONFIRMED)
    monkeypatch.setattr("sys.stdin", NoTerminal())

    def never(_write):
        raise AssertionError("the default path must not ask")

    result = run(project, rid, repo, confirm=never)
    assert result["path"] == "default" and result["confirmation"] is None
    assert "- confirmation:" not in body_of(node_files(repo)[0])
    other = add(project, "A record of another kind entirely", **CONFIRMED)
    assert main(human_cli(repo, other)) == 0
    assert json.loads(capsys.readouterr().out)["path"] == "default"


def test_a_human_policy_with_an_unconfirmed_record_stays_on_the_default_path(
    project, repo, capsys, monkeypatch
):
    set_policy(project)
    rid = add(project, review_state="agent_reviewed")
    monkeypatch.setattr("sys.stdin", NoTerminal())
    args = human_cli(repo, rid, "--min-review-state", "agent_reviewed")
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["path"] == "default"
    assert result["node"]["source"] == "agent"


def test_update_onto_a_human_node_needs_confirmation(
    project, repo, capsys, monkeypatch
):
    set_policy(project)
    rid = add(project, **CONFIRMED)
    run(project, rid, repo, confirm=confirm_yes)
    project.amend(rid, {"summary": "Corrected"}, expected_revision=2, actor="t")
    before = knowledge_files(repo)
    monkeypatch.setattr("sys.stdin", NoTerminal())
    args = human_cli(repo, rid, "--update")
    code = main(["--json-errors", *args])
    assert code == 2
    error = json.loads(capsys.readouterr().out)["error"]
    assert error["code"] == "confirmation_required"
    assert knowledge_files(repo) == before
    assert project.get(rid).revision == 3

    monkeypatch.setattr("sys.stdin", FakeTerminal("n\n"))
    assert main(args) == 2
    capsys.readouterr()
    assert knowledge_files(repo) == before

    monkeypatch.setattr("sys.stdin", FakeTerminal("y\n"))
    assert main(args) == 0
    captured = capsys.readouterr()
    assert f"in node {rid}" in captured.err and "keeps source=human" in captured.err
    result = json.loads(captured.out)
    assert result["action"] == "updated" and result["confirmation"] == "tty"
    body = body_of(node_files(repo)[0])
    assert "- confirmation: yes" not in body and "- confirmation: tty" in body


def test_update_onto_an_agent_node_needs_no_confirmation(project, repo):
    rid = add(project, **CONFIRMED)
    run(project, rid, repo)
    project.amend(rid, {"summary": "Corrected"}, expected_revision=2, actor="t")
    result = run(project, rid, repo, update=True)
    assert result["action"] == "updated" and result["confirmation"] is None


def test_crash_recovery_needs_no_terminal_and_no_confirmation(
    project, repo, capsys, monkeypatch
):
    set_policy(project)
    rid = add(project, **CONFIRMED)

    def crash(*_args, **_kwargs):
        raise OSError("simulated crash before the link")

    with monkeypatch.context() as patch:
        patch.setattr(RecordStore, "record_promotion", crash)
        with pytest.raises(OSError):
            run(project, rid, repo, confirm=confirm_yes)
    assert project.get(rid).promoted_to is None
    node = node_files(repo)[0].read_bytes()
    monkeypatch.setattr("sys.stdin", NoTerminal())
    assert main(human_cli(repo, rid)) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["action"] == "link_completed"
    assert result["path"] == "human-policy"
    assert result["confirmation"] is None
    assert result["node"]["source"] == "human"
    assert projected_bodies(node_files(repo)[0].read_bytes()) == projected_bodies(node)
    assert "- confirmation: yes" in body_of(node_files(repo)[0])
    assert project.get(rid).promoted_to["path"] == "human-policy"


def test_crash_recovery_of_an_update_needs_no_confirmation(project, repo, monkeypatch):
    set_policy(project)
    rid = add(project, **CONFIRMED)
    run(project, rid, repo, confirm=confirm_yes)
    project.amend(rid, {"summary": "Corrected"}, expected_revision=2, actor="t")

    def crash(*_args, **_kwargs):
        raise OSError("simulated crash before the link")

    with monkeypatch.context() as patch:
        patch.setattr(RecordStore, "record_promotion", crash)
        with pytest.raises(OSError):
            run(project, rid, repo, update=True, confirm=confirm_yes)
    node = node_files(repo)[0].read_bytes()
    result = run(project, rid, repo, update=True)
    assert result["action"] == "link_completed"
    assert projected_bodies(node_files(repo)[0].read_bytes()) == projected_bodies(node)
    assert project.get(rid).promoted_to["revision"] == 3


def test_a_crash_before_the_write_still_needs_confirmation(project, repo, monkeypatch):
    set_policy(project)
    rid = add(project, **CONFIRMED)
    import akms_records.bridge as bridge

    def crash(*_args, **_kwargs):
        raise OSError("simulated crash before the write")

    with monkeypatch.context() as patch:
        patch.setattr(bridge, "write_exclusive", crash)
        with pytest.raises(OSError):
            run(project, rid, repo, confirm=confirm_yes)
    assert node_files(repo) == []
    with pytest.raises(RecordsError) as caught:
        run(project, rid, repo)
    assert caught.value.code == "confirmation_required"


# ----------------------------------------------------------------- the refusals
def refused(store, record_id, repo, code, **options):
    before = tree(local_knowledge_dir(repo) / "local-nodes") if node_files(repo) else {}
    with pytest.raises(RecordsError) as caught:
        run(store, record_id, repo, **options)
    assert caught.value.code == code
    after = tree(local_knowledge_dir(repo) / "local-nodes") if node_files(repo) else {}
    assert after == before
    return caught.value


def test_refuses_without_explicit_approval(project, repo):
    rid = add(project, **CONFIRMED)
    refused(project, rid, repo, "review_required", review=None)


@pytest.mark.parametrize("state", ["unreviewed", "agent_reviewed", "rejected"])
def test_refuses_below_the_default_threshold(project, repo, state):
    rid = add(project, review_state=state)
    error = refused(project, rid, repo, "review_below_threshold")
    assert error.details["required"] == "user_confirmed"


def test_threshold_can_be_lowered_but_never_below_a_review(project, repo):
    reviewed = add(project, review_state="agent_reviewed")
    assert run(project, reviewed, repo, min_review_state="agent_reviewed")
    fresh = add(project, "Another decision")
    refused(
        project,
        fresh,
        repo,
        "review_below_threshold",
        min_review_state="agent_reviewed",
    )
    refused(project, fresh, repo, "usage", min_review_state="unreviewed")


def test_refuses_agent_and_shared_scope_without_scope_ok(repo, tmp_path, monkeypatch):
    monkeypatch.setenv("AKMS_RECORDS_HOME", str(tmp_path / "home"))
    for scope in ("agent:scout", "shared:team"):
        store = RecordStore.open(Scope.parse(scope))
        store.register_schema(load_template("decision"), actor="t")
        rid = add(store, f"From {scope}", **CONFIRMED)
        refused(store, rid, repo, "scope_not_project")
        result = run(store, rid, repo, scope_ok=True)
        assert result["action"] == "created"
        store.close()


def test_refuses_retracted_superseded_and_erased_records(project, repo):
    retracted = add(project, "Retract me", **CONFIRMED)
    project.retract(retracted, expected_revision=1, reason="wrong", actor="t")
    refused(project, retracted, repo, "record_retracted")
    old = add(project, "Old one", **CONFIRMED)
    new = add(project, "New one", **CONFIRMED)
    project.supersede(old, expected_revision=1, by=new, actor="t")
    refused(project, old, repo, "record_superseded")
    erased = add(project, "Erase me", **CONFIRMED)
    project.erase(erased, reason="privacy", actor="t")
    refused(project, erased, repo, "record_erased")


def test_refuses_schema_mismatch(project, repo):
    rid = add(project, **CONFIRMED)
    path = project.schemas.root / "decision" / "v1" / "schema.json"
    path.write_bytes(path.read_bytes().replace(b'"Decision"', b'"Tampered"'))
    refused(project, rid, repo, "schema_mismatch")


def test_refuses_sensitive_records_unless_allowed(project, repo):
    rid = add(project, sensitivity="sensitive", **CONFIRMED)
    refused(project, rid, repo, "record_sensitive")
    assert run(project, rid, repo, allow_sensitive=True)["action"] == "created"


def test_refuses_summaries_until_reviewed_and_valid(project, repo):
    rid = add(project, tags=["mesh"], **CONFIRMED)
    summary = consolidate(project, actor="t", tags=["mesh"])["record_id"]
    refused(project, summary, repo, "summary_unreviewed")
    project.amend(
        summary, {"review_state": "user_confirmed"}, expected_revision=1, actor="t"
    )
    assert run(project, summary, repo)["action"] == "created"
    assert project.get(summary).promoted_to is not None
    from akms_records import consolidation_status

    assert consolidation_status(project, summary)["status"] == "valid"
    # The source is still promotable, and the summary stays valid after that.
    assert run(project, rid, repo)["action"] == "created"
    assert consolidation_status(project, summary)["status"] == "valid"


def test_refuses_a_stale_summary(project, repo):
    rid = add(project, tags=["mesh"], **CONFIRMED)
    summary = consolidate(project, actor="t", tags=["mesh"])["record_id"]
    project.amend(
        summary, {"review_state": "user_confirmed"}, expected_revision=1, actor="t"
    )
    project.amend(rid, {"tags": ["mesh", "more"]}, expected_revision=1, actor="t")
    refused(project, summary, repo, "summary_stale")


def test_refuses_imported_lessons_unless_allowed(project, repo):
    from akms_records.citations import lesson_schema

    project.register_schema(lesson_schema(), actor="t")
    lesson = {
        "id": "L001",
        "date_found": "2026-08-01",
        "date_found_precision": "exact",
        "date_fixed": "2026-08-02",
        "date_fixed_precision": "exact",
        "location": {
            "area": "src",
            "package": "p",
            "module": "m",
            "file": "src/m.py",
            "symbol": "",
            "line_hint": "",
        },
        "found_by": {"type": "test", "trigger": "t"},
        "symptom": "It failed.",
        "root_cause": "Cause.",
        "fix": "Fix.",
        "prevention": "Prevent.",
        "references": {"commit": "", "issue": "", "pr": "", "plan": ""},
        "related": [],
    }
    rid = project.create(
        {
            "schema_ref": "failure-lesson/v1",
            "payload": lesson,
            "summary": "L001: It failed.",
            "review_state": "user_confirmed",
        },
        actor="t",
    ).record_id
    refused(project, rid, repo, "imported_not_promotable")
    assert run(project, rid, repo, allow_imported=True)["action"] == "created"


def test_refuses_a_record_with_no_room_for_the_link(project, repo):
    refs = [{"kind": "issue", "ref": f"#{n}"} for n in range(64)]
    rid = add(project, source_refs=refs, **CONFIRMED)
    refused(project, rid, repo, "source_refs_full")
    assert project.get(rid).revision == 1


# ----------------------------------------------------------------- idempotency
def test_promoting_the_same_revision_twice_changes_nothing(project, repo):
    rid = add(project, **CONFIRMED)
    first = run(project, rid, repo)
    knowledge = local_knowledge_dir(repo)
    nodes = tree(knowledge / "local-nodes")
    events = len(project.history(rid))
    second = run(project, rid, repo)
    assert second["action"] == "already_promoted"
    assert second["node_id"] == first["node_id"]
    assert second["node_present"] is True
    assert second["link"] is None
    assert tree(knowledge / "local-nodes") == nodes
    assert len(project.history(rid)) == events == 2


def test_a_removed_node_is_reported_not_recreated(project, repo):
    rid = add(project, **CONFIRMED)
    run(project, rid, repo)
    [path] = node_files(repo)
    path.unlink()
    result = run(project, rid, repo)
    assert result["action"] == "already_promoted"
    assert result["node_present"] is False
    assert node_files(repo) == []


def test_a_newer_revision_needs_update(project, repo):
    rid = add(project, **CONFIRMED)
    run(project, rid, repo)
    project.amend(
        rid, {"summary": "A corrected summary"}, expected_revision=2, actor="t"
    )
    error = refused(project, rid, repo, "already_promoted")
    assert error.details == {"node_id": rid, "revision": 3}
    result = run(project, rid, repo, update=True)
    assert result["action"] == "updated"
    assert result["node_id"] == rid
    assert result["revision"] == 3
    assert project.get(rid).promoted_to["revision"] == 3
    [path] = node_files(repo)
    body = body_of(path)
    assert f"- record: `{rid}@1`" not in body and f"- record: `{rid}@3`" in body
    assert "A corrected summary" in body
    assert run(project, rid, repo, update=True)["action"] == "already_promoted"


def test_update_keeps_a_human_nodes_labels(project, repo):
    set_policy(project, status="established", confidence=0.8)
    rid = add(project, **CONFIRMED)
    run(project, rid, repo, confirm=confirm_yes)
    project.amend(rid, {"summary": "Corrected"}, expected_revision=2, actor="t")
    set_policy(project, status="tentative", confidence=0.3)
    result = run(project, rid, repo, update=True, confirm=confirm_yes)
    assert result["action"] == "updated"
    assert result["node"] == {
        "source": "human",
        "status": "established",
        "confidence": 0.8,
    }
    assert result["policy"]["reason"] == "existing_node_keeps_labels"
    assert len(node_files(repo)) == 1
    assert "Corrected" in body_of(node_files(repo)[0])


def test_update_of_an_agent_node_that_left_tentative_is_refused(project, repo):
    rid = add(project, **CONFIRMED)
    run(project, rid, repo)
    project.amend(rid, {"summary": "Corrected"}, expected_revision=2, actor="t")
    [path] = node_files(repo)
    post = frontmatter.load(str(path))
    post.metadata["status"] = "deprecated"
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    refused(project, rid, repo, "node_not_updatable", update=True)


# ----------------------------------------------------------------- crash order
def test_crash_between_the_node_and_the_link_completes_on_rerun(
    project, repo, monkeypatch
):
    rid = add(project, **CONFIRMED)

    def crash(*_args, **_kwargs):
        raise OSError("simulated crash before the link")

    with monkeypatch.context() as patch:
        patch.setattr(RecordStore, "record_promotion", crash)
        with pytest.raises(OSError):
            run(project, rid, repo)
    assert project.get(rid).promoted_to is None
    assert project.get(rid).revision == 1
    [path] = node_files(repo)
    once = path.read_bytes()
    result = run(project, rid, repo)
    assert result["action"] == "link_completed"
    assert result["node_id"] == rid
    assert project.get(rid).promoted_to["revision"] == 1
    assert node_files(repo) == [path]
    assert projected_bodies(path.read_bytes()) == projected_bodies(once)
    assert run(project, rid, repo)["action"] == "already_promoted"


def test_crash_inside_update_graph_after_the_node_write(project, repo, monkeypatch):
    import akms.graph.update_graph as module

    rid = add(project, **CONFIRMED)

    def crash(*_args, **_kwargs):
        raise OSError("simulated crash before the overlay")

    with monkeypatch.context() as patch:
        patch.setattr(module, "_write_overlay", crash)
        with pytest.raises(RecordsError) as caught:
            run(project, rid, repo)
    assert caught.value.code == "promote_graph_failed"
    assert len(node_files(repo)) == 1
    result = run(project, rid, repo)
    assert result["action"] == "link_completed"
    assert len(node_files(repo)) == 1
    graph = load_graph(local_knowledge_dir(repo) / "graph" / "graph.json")
    assert rid in graph


def test_crash_on_the_human_path_completes_on_rerun(project, repo, monkeypatch):
    set_policy(project)
    rid = add(project, **CONFIRMED)

    def crash(*_args, **_kwargs):
        raise OSError("simulated crash before the link")

    with monkeypatch.context() as patch:
        patch.setattr(RecordStore, "record_promotion", crash)
        with pytest.raises(OSError):
            run(project, rid, repo, confirm=confirm_yes)
    result = run(project, rid, repo)
    assert result["action"] == "link_completed"
    assert result["path"] == "human-policy"
    assert result["node"]["status"] == "established"
    assert len(node_files(repo)) == 1


def test_crash_and_a_later_amend_reports_the_existing_node(project, repo, monkeypatch):
    rid = add(project, **CONFIRMED)

    def crash(*_args, **_kwargs):
        raise OSError("simulated crash before the link")

    with monkeypatch.context() as patch:
        patch.setattr(RecordStore, "record_promotion", crash)
        with pytest.raises(OSError):
            run(project, rid, repo)
    project.amend(rid, {"summary": "Edited meanwhile"}, expected_revision=1, actor="t")
    assert refused(project, rid, repo, "already_promoted").details["node_id"] == rid
    assert run(project, rid, repo, update=True)["action"] == "updated"
    assert len(node_files(repo)) == 1


def test_a_removed_node_retries_past_the_replay_ledger(project, repo, monkeypatch):
    rid = add(project, **CONFIRMED)

    def crash(*_args, **_kwargs):
        raise OSError("simulated crash before the link")

    with monkeypatch.context() as patch:
        patch.setattr(RecordStore, "record_promotion", crash)
        with pytest.raises(OSError):
            run(project, rid, repo)
    # The ledger names the source, but the node is gone: nothing holds the record.
    node_files(repo)[0].unlink()
    result = run(project, rid, repo)
    assert result["action"] == "created"
    overlay = local_knowledge_dir(repo) / "graph" / "local_state.yaml"
    assert f"akms-records-{rid}-r1-a1" in overlay.read_text(encoding="utf-8")


def test_a_write_update_graph_dropped_is_typed_and_retried(project, repo, monkeypatch):
    import akms.graph.update_graph as module

    rid = add(project, **CONFIRMED)
    with monkeypatch.context() as patch:
        patch.setattr(module, "_process_new_knowledge", lambda *_args: [])
        with pytest.raises(RecordsError) as caught:
            run(project, rid, repo)
    assert caught.value.code == "promote_write_failed"
    assert project.get(rid).promoted_to is None
    assert run(project, rid, repo)["action"] == "created"


def test_a_full_replay_ledger_is_typed(project, repo, monkeypatch):
    import akms.graph.update_graph as module

    rid = add(project, **CONFIRMED)
    monkeypatch.setattr(module, "update_graph", lambda *_args: {"replayed": True})
    refused(project, rid, repo, "promote_ledger_exhausted")


def test_update_graph_errors_are_typed(project, repo, monkeypatch):
    import akms.graph.update_graph as module

    def broken(*_args):
        raise ValueError("bad overlay")

    rid = add(project, **CONFIRMED)
    monkeypatch.setattr(module, "update_graph", broken)
    refused(project, rid, repo, "promote_graph_failed")


def test_the_human_path_will_not_overwrite_another_file(project, repo):
    set_policy(project)
    rid = add(project, **CONFIRMED)
    folder = repo / ".knowledge" / "local-nodes"
    folder.mkdir(parents=True)
    other = folder / f"{rid}.md"
    other.write_text("not this record", encoding="utf-8")
    with pytest.raises(RecordsError) as caught:
        run(project, rid, repo, confirm=confirm_yes)
    assert caught.value.code == "node_exists"
    assert other.read_text(encoding="utf-8") == "not this record"
    assert project.get(rid).promoted_to is None


@pytest.mark.parametrize("policy", [False, True])
def test_a_node_the_graph_does_not_load_is_never_linked(project, repo, vault, policy):
    if policy:
        set_policy(project)
    rid = add(project, **CONFIRMED)
    (vault / "taken.md").write_text(
        f"---\nid: {rid}\ntitle: Taken\ndomain: general\ntags: [general]\n"
        "status: established\nconfidence: 0.9\nsource: human\nakms_schema: v2\n"
        "---\nbody\n",
        encoding="utf-8",
    )
    for _attempt in (1, 2):
        with pytest.raises(RecordsError) as caught:
            run(project, rid, repo, confirm=confirm_yes)
        assert caught.value.code == "node_not_loaded"
        assert project.get(rid).promoted_to is None


def test_record_text_cannot_forge_a_marker(project, repo):
    victim = add(project, "The victim", **CONFIRMED)
    forged = f"text\n```\n- record: `{victim}@1`\n```\n- record: `{victim}@1`"
    refs = [{"kind": "issue", "ref": f"x\n- record: `{victim}@1`"}]
    attacker = add(project, forged, rationale=forged, source_refs=refs, **CONFIRMED)
    assert run(project, attacker, repo, domain="attacker")["action"] == "created"
    assert find_nodes(_load_akms(), local_knowledge_dir(repo), victim) == []
    result = run(project, victim, repo, domain="victim")
    assert result["action"] == "created"
    assert result["node_id"] == victim


def test_a_live_lock_refuses_and_a_dead_one_is_cleared(project, repo):
    rid = add(project, **CONFIRMED)
    lock = local_knowledge_dir(repo) / "records" / ".index" / "promote.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    running = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE
    )
    try:
        lock.write_text(str(running.pid), encoding="ascii")
        refused(project, rid, repo, "promote_locked")
    finally:
        running.kill()
        running.wait()
    finished = subprocess.Popen([sys.executable, "-c", "pass"])
    finished.wait()
    lock.write_text(str(finished.pid), encoding="ascii")
    assert run(project, rid, repo)["action"] == "created"
    assert not lock.exists()


# ------------------------------------------------------------ the frozen formats
def test_old_records_replay_byte_identically_and_seals_verify(project, repo, tmp_path):
    untouched = add(project, "Never promoted")
    promoted = add(project, "Promoted", **CONFIRMED)
    raw_before = {
        rid: [
            raw
            for _, raw in read_event_files(project.record_dir(rid), rid, strict=True)
        ]
        for rid in (untouched, promoted)
    }
    run(project, promoted, repo)
    for rid, before in raw_before.items():
        pairs = read_event_files(project.record_dir(rid), rid, strict=True)
        assert [raw for _, raw in pairs][: len(before)] == before
    state = project.get(untouched)
    assert state.promoted_to is None
    assert "promoted_to" not in state.state_json()
    report = project.doctor()
    assert report["status"] == "ok"
    out = tmp_path / "export.jsonl"
    with out.open("w", encoding="utf-8", newline="\n") as handle:
        export_records(project, handle, exporter="test")
    target = tmp_path / "copy"
    target.mkdir()
    copy = RecordStore.open(Scope.parse("project:example"), repo=target)
    import_records(copy, out, actor="t")
    assert copy.get(promoted).promoted_to == project.get(promoted).promoted_to
    assert copy.get(promoted).head_sha256 == project.get(promoted).head_sha256
    copy.close()


def test_writers_cannot_set_a_link_and_amends_keep_it(project, repo):
    forged = [{"kind": PROMOTED_KIND, "ref": "some-node@1"}]
    with pytest.raises(RecordsError) as caught:
        add(project, source_refs=forged, **CONFIRMED)
    assert caught.value.code == "reserved_source_ref"
    rid = add(project, **CONFIRMED)
    with pytest.raises(RecordsError) as caught:
        project.amend(rid, {"source_refs": forged}, expected_revision=1, actor="t")
    assert caught.value.code == "reserved_source_ref"
    run(project, rid, repo)
    refs = [{"kind": "issue", "ref": "#1"}]
    project.amend(rid, {"source_refs": refs}, expected_revision=2, actor="t")
    state = project.get(rid)
    assert state.promoted_to["node_id"] == rid
    assert refs[0] in state.source_refs
    many = [{"kind": "issue", "ref": f"#{n}"} for n in range(64)]
    with pytest.raises(RecordsError) as caught:
        project.amend(rid, {"source_refs": many}, expected_revision=3, actor="t")
    assert caught.value.code == "source_refs_full"


def test_a_link_with_a_malformed_ref_reads_as_no_link():
    from akms_records.envelope import promotion_link

    for ref in ("node", "node@", "@3", "node@0", "node@x"):
        assert promotion_link([{"kind": PROMOTED_KIND, "ref": ref}]) is None
    assert promotion_link("nonsense") is None


def test_erasing_a_promoted_record_names_the_node_it_cannot_reach(project, repo):
    plain = add(project, "Not promoted", **CONFIRMED)
    report = project.erase(plain, reason="privacy", actor="t")
    assert not any("AKMS node" in item for item in report["not_reached"])
    rid = add(project, **CONFIRMED)
    run(project, rid, repo)
    report = project.erase(rid, reason="privacy", actor="t")
    assert any(f"AKMS node {rid}" in item for item in report["not_reached"])


# ------------------------------------------------------------ the global vault
def test_no_path_writes_the_global_vault(project, repo, vault):
    before = tree(vault)
    default = add(project, "Through update_graph", **CONFIRMED)
    assert run(project, default, repo)["path"] == "default"
    assert tree(vault) == before
    set_policy(project)
    human = add(project, "Through the human policy", **CONFIRMED)
    assert run(project, human, repo, confirm=confirm_yes)["path"] == "human-policy"
    assert tree(vault) == before
    project.amend(human, {"summary": "Newer"}, expected_revision=2, actor="t")
    assert (
        run(project, human, repo, update=True, confirm=confirm_yes)["action"]
        == "updated"
    )
    assert tree(vault) == before
    graph = load_graph(local_knowledge_dir(repo) / "graph" / "graph.json")
    assert graph.nodes["global-node"]["node_origin"] == "global"


@pytest.mark.parametrize("target", [".knowledge", ".knowledge/local-nodes", "."])
def test_refuses_a_knowledge_directory_that_is_the_vault(
    project, repo, monkeypatch, target
):
    rid = add(project, **CONFIRMED)
    vault_dir = (repo / target).resolve()
    vault_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(vault_dir))
    before = tree(repo)
    refused(project, rid, repo, "global_vault_target")
    assert tree(repo) == before


def test_refuses_a_vault_reached_through_a_symlink(project, repo, vault):
    if os.name == "nt":
        pytest.skip("symlinks need privileges on Windows")
    rid = add(project, **CONFIRMED)
    os.symlink(vault, repo / ".knowledge" / "local-nodes")
    before = tree(vault)
    refused(project, rid, repo, "global_vault_target")
    assert tree(vault) == before


def test_refuses_the_vault_named_in_the_propagation_config(project, repo, monkeypatch):
    rid = add(project, **CONFIRMED)
    graph = repo / ".knowledge" / "graph"
    graph.mkdir(parents=True)
    (graph / "propagation_config.yaml").write_text(
        f"akms_schema: v2\nglobal_vault: {repo / '.knowledge'}\n", encoding="utf-8"
    )
    monkeypatch.delenv("AKMS_GLOBAL_VAULT")
    refused(project, rid, repo, "global_vault_target")


# ---------------------------------------------------------------- with wake
def test_a_promoted_record_leaves_wake_and_the_node_serves_it(project, repo, tmp_path):
    from akms_records import manifest_nodes, wake

    rid = add(project, tags=["mesh"], **CONFIRMED)
    kept = add(project, "Stays a record", tags=["mesh"], **CONFIRMED)
    home = tmp_path / "home"
    options = {
        "agent": "scout",
        "task": "mesh",
        "budget_tokens": 2000,
        "scopes": ["project:example"],
        "repo": repo,
        "home": home,
    }
    assert {e.record_id for e in wake(**options).entries} == {rid, kept}
    node_id = run(project, rid, repo)["node_id"]
    result = wake(**options)
    assert [e.record_id for e in result.entries] == [kept]
    assert result.excluded["promoted"] == (rid,)
    manifest = {
        "schema_version": "v1",
        "generated_at": "2026-11-05T00:00:00Z",
        "selected_nodes": [{"node_id": node_id}],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = wake(**options, include_promoted=True, exclude_nodes=manifest_nodes(path))
    assert result.excluded["in_loadout"] == (rid,)


# ----------------------------------------------------------------------- the CLI
def cli(capsys, *args):
    code = main(["--json-errors", *args])
    return code, json.loads(capsys.readouterr().out)


def test_cli_promote_end_to_end(project, repo, capsys, monkeypatch):
    rid = add(project, **CONFIRMED)
    base = ["--scope", "project:example", "--repo", str(repo)]
    code, out = cli(capsys, "promote", rid, *base)
    assert code == 2 and out["error"]["code"] == "review_required"
    code, out = cli(capsys, "promote", rid, *base, "--review", "approved")
    assert code == 0 and out["action"] == "created" and out["node_id"] == rid
    code, out = cli(capsys, "promote", rid, *base, "--review", "approved")
    assert code == 0 and out["action"] == "already_promoted"
    code, out = cli(capsys, "show", rid, *base)
    assert out["state"]["promoted_to"]["node_id"] == rid
    code, out = cli(capsys, "recall", *base)
    assert out["count"] == 1
    amended = cli(
        capsys,
        "amend",
        rid,
        *base,
        "--actor",
        "t",
        "--expect-revision",
        "2",
        "--summary",
        "New",
    )
    assert amended[0] == 0
    code, out = cli(capsys, "promote", rid, *base, "--review", "approved")
    assert code == 2 and out["error"]["code"] == "already_promoted"
    assert out["error"]["details"]["node_id"] == rid
    code, out = cli(capsys, "promote", rid, *base, "--review", "approved", "--update")
    assert code == 0 and out["action"] == "updated"


# ------------------------------------------------ managed projection migration


def test_explicit_update_repairs_a_missing_node(project, repo):
    from akms_records.bridge import promotion_status

    rid = add(project, **CONFIRMED)
    run(project, rid, repo)
    [path] = node_files(repo)
    path.unlink()
    result = run(project, rid, repo, update=True)
    assert result["action"] == "created"
    assert len(node_files(repo)) == 1
    assert promotion_status(project, rid, repo=repo)["results"][0]["state"] == "current"


def make_legacy(path):
    post = frontmatter.load(str(path))
    [block] = parse_projections(str(post.content))
    post.content = block.body
    path.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")


def test_exact_legacy_projection_upgrades_only_explicitly(project, repo):
    from akms_records.bridge import promotion_status

    rid = add(project, **CONFIRMED)
    run(project, rid, repo)
    [path] = node_files(repo)
    make_legacy(path)
    post = frontmatter.load(str(path))
    post.content += "\n\nUnrelated manual note.\n"
    path.write_text(frontmatter.dumps(post), encoding="utf-8")
    before = path.read_bytes()
    assert (
        promotion_status(project, rid, repo=repo)["results"][0]["state"]
        == "projection_stale"
    )
    refused(project, rid, repo, "already_promoted")
    assert path.read_bytes() == before
    assert run(project, rid, repo, update=True)["action"] == "updated"
    [block] = parse_projections(body_of(path))
    assert block.metadata["record_id"] == rid
    assert "Unrelated manual note." in body_of(path)
    assert promotion_status(project, rid, repo=repo)["results"][0]["state"] == "current"


def test_manually_edited_legacy_projection_is_not_overwritten(project, repo):
    rid = add(project, **CONFIRMED)
    run(project, rid, repo)
    [path] = node_files(repo)
    make_legacy(path)
    path.write_text(path.read_text().replace("within budget", "my manual correction"))
    before = path.read_bytes()
    refused(project, rid, repo, "projection_conflict", update=True)
    assert path.read_bytes() == before


def test_legacy_crash_recovery_requires_explicit_upgrade(project, repo, monkeypatch):
    rid = add(project, **CONFIRMED)
    with monkeypatch.context() as patch:
        patch.setattr(
            RecordStore,
            "record_promotion",
            lambda *a, **kw: (_ for _ in ()).throw(OSError("crash")),
        )
        with pytest.raises(OSError):
            run(project, rid, repo)
    [path] = node_files(repo)
    make_legacy(path)
    refused(project, rid, repo, "already_promoted")
    assert project.get(rid).promoted_to is None
    assert run(project, rid, repo, update=True)["action"] == "updated"
    assert project.get(rid).promoted_to["revision"] == 1
    assert len(parse_projections(body_of(path))) == 1


def test_finalize_does_not_silently_reseal_mutated_source_bytes(project, repo):
    from akms_records.bridge import promotion_status

    rid = add(project, **CONFIRMED)
    run(project, rid, repo)
    [path] = node_files(repo)
    event_path = project.record_dir(rid) / "000001.json"
    # Semantically identical JSON still changes the byte-level integrity witness.
    event = json.loads(event_path.read_text())
    event_path.write_text(json.dumps(event, indent=4) + "\n")
    assert (
        promotion_status(project, rid, repo=repo)["results"][0]["state"]
        == "projection_stale"
    )
    before = path.read_bytes()
    refused(project, rid, repo, "already_promoted")
    assert path.read_bytes() == before
    assert run(project, rid, repo, update=True)["action"] == "updated"
    assert promotion_status(project, rid, repo=repo)["results"][0]["state"] == "current"


def test_cli_promotion_status_and_withdraw(project, repo, capsys):
    rid = add(project, **CONFIRMED)
    run(project, rid, repo)
    base = ["--scope", "project:example", "--repo", str(repo)]
    code, result = cli(capsys, "promotion", "status", rid, *base)
    assert code == 0 and result["results"][0]["state"] == "current"
    project.amend(rid, {"summary": "Changed"}, expected_revision=2, actor="t")
    code, result = cli(capsys, "promotion", "status", rid, *base)
    assert code == 1 and result["results"][0]["state"] == "source_changed"
    code, result = cli(
        capsys,
        "promotion",
        "withdraw",
        rid,
        *base,
        "--expect-revision",
        "3",
        "--reason",
        "No longer needed",
    )
    assert code == 0 and result["action"] == "withdrawn"
    assert project.get(rid).promoted_to is None
    code, result = cli(capsys, "promotion", "status", rid, *base)
    assert code == 0 and result["results"][0]["state"] == "not_promoted"
