"""Token discipline: what wake leaves to the AKMS loadout and to failure-memory."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from akms_records import (
    RecordsError,
    consolidate,
    consolidation_status,
    manifest_nodes,
    wake,
)
from akms_records.citations import lesson_schema
from akms_records.cli import main
from akms_records.query import EXCLUSION_KINDS
from akms_records.render import estimate_tokens
from akms_records.schemas import load_template

WORKERS = Path(__file__).resolve().parent / "workers"
SUMMARIZER = WORKERS / "summarizer.py"
AUDIT = WORKERS / "wake_audit.py"
LESSON = {
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
    "root_cause": "Cause.",
    "fix": "Fix.",
    "prevention": "Prevent.",
    "references": {"commit": "", "issue": "", "pr": "", "plan": ""},
    "related": [],
}


@pytest.fixture
def home(tmp_path, monkeypatch):
    path = tmp_path / "home"
    monkeypatch.setenv("AKMS_RECORDS_HOME", str(path))
    return path


@pytest.fixture
def project(make_store, clock):
    store = make_store(clock=clock())
    store.register_schema(load_template("decision"), actor="t")
    store.register_schema(lesson_schema(), actor="t")
    yield store
    store.close()


def add(store, text="Keep the coarse mesh", *, state="user_confirmed", tags=("mesh",)):
    return store.create(
        {
            "schema_ref": "decision/v1",
            "payload": {"decision": text, "rationale": "because"},
            "tags": list(tags),
            "review_state": state,
        },
        actor="t",
    ).record_id


def add_lesson(store, lesson_id="L001", *, state="unreviewed", tags=("mesh",)):
    return store.create(
        {
            "schema_ref": "failure-lesson/v1",
            "payload": {
                **LESSON,
                "id": lesson_id,
                "symptom": f"Mesh failed {lesson_id}",
            },
            "summary": f"{lesson_id}: Mesh failed",
            "tags": list(tags),
            "source_refs": [
                {"kind": "failure-lesson", "ref": lesson_id, "note": "demo"}
            ],
            "origin": {"kind": "import", "actor_id": "failure-memory-import"},
            "review_state": state,
        },
        actor="t",
    ).record_id


def link(store, record_id, node_id=None):
    record = store.get(record_id)
    store.record_promotion(
        record_id,
        node_id=node_id or f"node-{record_id}",
        revision=record.revision,
        path="default",
        expected_revision=record.revision,
        actor="t",
    )


def run(repo, home, **options):
    return wake(
        agent=options.pop("agent", "scout"),
        task=options.pop("task", "mesh"),
        budget_tokens=options.pop("budget", 3000),
        scopes=options.pop("scopes", ["project:example"]),
        repo=repo,
        home=home,
        **options,
    )


def included(result):
    return [entry.record_id for entry in result.entries]


def write_manifest(path: Path, nodes) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "v1",
                "selected_nodes": [
                    {"node_id": node, "selection_class": "required", "reasons": ["r"]}
                    for node in nodes
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


# -------------------------------------------------------------- promoted records
def test_promoted_records_are_left_to_the_loadout(project, repo, home):
    kept = add(project, "Stays in wake")
    promoted = add(project, "Became a node")
    link(project, promoted)
    result = run(repo, home)
    assert included(result) == [kept]
    assert result.excluded["promoted"] == (promoted,)
    assert result.to_json()["report"]["excluded"]["promoted"] == {
        "count": 1,
        "ids": [promoted],
    }
    assert "promoted 1" in result.render_markdown()


def test_include_promoted_takes_them_back_and_recall_reaches_them(project, repo, home):
    promoted = add(project)
    link(project, promoted)
    result = run(repo, home, include_promoted=True)
    assert included(result) == [promoted]
    assert result.excluded["promoted"] == ()
    hits = project.recall("mesh")
    assert [hit.record_id for hit in hits.hits] == [promoted]


def test_a_newer_revision_of_a_promoted_record_is_still_promoted(project, repo, home):
    promoted = add(project)
    link(project, promoted)
    project.amend(promoted, {"tags": ["mesh", "more"]}, expected_revision=2, actor="t")
    assert run(repo, home).excluded["promoted"] == (promoted,)


# -------------------------------------------------------------- imported lessons
def test_imported_lessons_are_left_to_failure_memory(project, repo, home):
    lesson = add_lesson(project)
    kept = add(project)
    result = run(repo, home)
    assert included(result) == [kept]
    assert result.excluded["imported"] == (lesson,)
    assert "imported 1" in result.render_markdown()


def test_include_imported_admits_them_unreviewed_and_recall_reaches_them(
    project, repo, home
):
    lesson = add_lesson(project)
    result = run(repo, home, include_imported=True)
    assert included(result) == [lesson]
    assert result.entries[0].review_state == "unreviewed"
    assert [hit.record_id for hit in project.recall("mesh").hits] == [lesson]
    strict = run(repo, home, include_imported=True, review_state="agent_reviewed")
    assert included(strict) == []
    assert strict.excluded["review_state"] == (lesson,)


# ------------------------------------------------------------------- the manifest
def test_exclude_nodes_drops_records_whose_node_is_in_the_loadout(
    project, repo, home, tmp_path
):
    loaded = add(project, "Node is in this loadout")
    other = add(project, "Node is not in this loadout")
    link(project, loaded, "node-loaded")
    link(project, other, "node-other")
    nodes = manifest_nodes(write_manifest(tmp_path / "m.json", ["node-loaded", "x"]))
    assert nodes == {"node-loaded", "x"}
    result = run(repo, home, include_promoted=True, exclude_nodes=nodes)
    assert included(result) == [other]
    assert result.excluded["in_loadout"] == (loaded,)
    default = run(repo, home, exclude_nodes=nodes)
    assert included(default) == []
    assert default.excluded["in_loadout"] == (loaded,)
    assert default.excluded["promoted"] == (other,)


def test_a_manifest_from_the_real_resolver_code(project, repo, home, tmp_path):
    pytest.importorskip("akms")
    from akms.task_context.manifest import (
        create_resolution_manifest,
        write_resolution_manifest,
    )
    from akms.task_context.query import (
        NodeSelection,
        SelectionClass,
        TaskKnowledgeQueryResult,
    )
    from akms.task_context.resolve import ResolvedSeeds

    manifest = create_resolution_manifest(
        task={"task_id": "T-1", "title": "A task", "scope": ["src/a.py"]},
        resolved_seeds=ResolvedSeeds(
            advisory_tags=(),
            exact_mirror_node_ids=(),
            required_route_node_ids=("node-loaded",),
            reasons={"node-loaded": ("required route path",)},
        ),
        query_result=TaskKnowledgeQueryResult(
            selections=(
                NodeSelection(
                    node_id="node-loaded",
                    selection_class=SelectionClass.REQUIRED,
                    node_data={"title": "Loaded"},
                    reasons=("required route path",),
                ),
            )
        ),
        agent_role="implementer",
        graph_version="graph-sha256",
        route_index_hash="route-sha256",
    )
    path = write_resolution_manifest(tmp_path / "manifest.json", manifest)
    assert manifest_nodes(path) == {"node-loaded"}
    loaded = add(project)
    link(project, loaded, "node-loaded")
    result = run(repo, home, include_promoted=True, exclude_nodes=manifest_nodes(path))
    assert result.excluded["in_loadout"] == (loaded,)


@pytest.mark.parametrize(
    "text",
    [
        "{",
        "[]",
        "{}",
        '{"schema_version": "v2", "selected_nodes": []}',
        '{"schema_version": "v1"}',
        '{"schema_version": "v1", "selected_nodes": {}}',
        '{"schema_version": "v1", "selected_nodes": [{"node_id": ""}]}',
        '{"schema_version": "v1", "selected_nodes": ["x"]}',
    ],
)
def test_an_invalid_manifest_is_a_typed_error(tmp_path, text):
    path = tmp_path / "bad.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(RecordsError) as caught:
        manifest_nodes(path)
    assert caught.value.code == "manifest_invalid"


def test_a_missing_manifest_is_a_typed_error(tmp_path):
    with pytest.raises(RecordsError) as caught:
        manifest_nodes(tmp_path / "absent.json")
    assert caught.value.code == "manifest_missing"
    with pytest.raises(RecordsError) as caught:
        manifest_nodes(tmp_path)
    assert caught.value.code == "manifest_invalid"


def cli(capsys, *args):
    code = main(["--json-errors", *args])
    return code, capsys.readouterr().out


def test_cli_flags(project, repo, home, tmp_path, capsys):
    promoted = add(project, "Became a node")
    lesson = add_lesson(project)
    link(project, promoted, "node-loaded")
    base = [
        "wake",
        "--agent",
        "scout",
        "--task",
        "mesh",
        "--budget-tokens",
        "2000",
        "--scope",
        "project:example",
        "--repo",
        str(repo),
    ]
    code, out = cli(capsys, *base)
    report = json.loads(out)["report"]
    assert code == 0
    assert report["included"]["ids"] == []
    assert report["excluded"]["promoted"]["ids"] == [promoted]
    assert report["excluded"]["imported"]["ids"] == [lesson]
    code, out = cli(capsys, *base, "--include-promoted", "--include-imported")
    assert sorted(json.loads(out)["report"]["included"]["ids"]) == sorted(
        [promoted, lesson]
    )
    manifest = write_manifest(tmp_path / "m.json", ["node-loaded"])
    code, out = cli(
        capsys, *base, "--include-promoted", "--exclude-nodes", str(manifest)
    )
    assert json.loads(out)["report"]["excluded"]["in_loadout"]["ids"] == [promoted]
    code, out = cli(capsys, *base, "--exclude-nodes", str(tmp_path / "absent.json"))
    assert code == 2 and json.loads(out)["error"]["code"] == "manifest_missing"
    (tmp_path / "bad.json").write_text("[]", encoding="utf-8")
    code, out = cli(capsys, *base, "--exclude-nodes", str(tmp_path / "bad.json"))
    assert code == 2 and json.loads(out)["error"]["code"] == "manifest_invalid"
    code, out = cli(capsys, *base, "--format", "markdown")
    assert code == 0 and "promoted 1, imported 1, in_loadout 0" in out


# ----------------------------------------------------------------------- summaries
def make_summary(project, tags=("mesh",)):
    return consolidate(project, actor="t", tags=list(tags))["record_id"]


def test_a_link_does_not_make_a_summary_stale(project, repo, home):
    first, second = add(project, "First"), add(project, "Second")
    summary = make_summary(project)
    assert consolidation_status(project, summary)["status"] == "valid"
    link(project, first)
    assert consolidation_status(project, summary)["status"] == "valid"
    states = {
        s["record_id"]: s["state"]
        for s in consolidation_status(project, summary)["sources"]
    }
    assert states == {first: "current", second: "current"}
    project.amend(first, {"tags": ["mesh", "x"]}, expected_revision=2, actor="t")
    assert consolidation_status(project, summary)["status"] == "stale"


def test_a_summary_of_promoted_sources_is_left_out_as_promoted(project, repo, home):
    first, second = add(project, "First"), add(project, "Second")
    summary = make_summary(project)
    link(project, first)
    link(project, second)
    result = run(repo, home)
    assert included(result) == []
    assert result.excluded["promoted"] == tuple(sorted([first, second, summary]))
    assert result.excluded["stale"] == ()
    assert result.excluded["review_state"] == ()


def test_a_summary_of_imported_sources_is_left_out_as_imported(project, repo, home):
    first = add_lesson(project, "L001", state="agent_reviewed")
    second = add_lesson(project, "L002", state="agent_reviewed")
    summary = make_summary(project)
    result = run(repo, home)
    assert included(result) == []
    assert result.excluded["imported"] == tuple(sorted([first, second, summary]))


def test_a_summary_of_mixed_held_sources_takes_the_first_reason(project, repo, home):
    promoted = add(project, "First")
    lesson = add_lesson(project, "L001", state="agent_reviewed")
    summary = make_summary(project)
    link(project, promoted)
    result = run(repo, home)
    assert summary in result.excluded["promoted"]
    assert result.excluded["imported"] == (lesson,)


def test_an_extractive_summary_with_a_held_source_yields_to_the_others(
    project, repo, home
):
    promoted, kept = add(project, "First"), add(project, "Second")
    summary = make_summary(project)
    link(project, promoted)
    result = run(repo, home)
    assert included(result) == [kept]
    assert sorted(result.excluded["promoted"]) == sorted([promoted, summary])
    assert result.excluded["covered"] == ()


def test_an_unreviewed_source_still_decides_as_before(project, repo, home):
    promoted = add(project, "First")
    unreviewed = add(project, "Second", state="unreviewed")
    summary = make_summary(project)
    link(project, promoted)
    result = run(repo, home)
    assert summary in result.excluded["review_state"]
    assert unreviewed in result.excluded["review_state"]


def test_including_the_sources_makes_the_summary_eligible_again(project, repo, home):
    first, second = add(project, "First " * 30), add(project, "Second " * 30)
    summary = make_summary(project)
    link(project, first)
    link(project, second)
    result = run(repo, home, include_promoted=True)
    assert result.excluded["promoted"] == ()
    assert summary in included(result) or summary in result.excluded["duplicate"]


def provider_summary(project):
    from akms_records import command_summarizer

    summarizer = command_summarizer([sys.executable, str(SUMMARIZER), "ok"], timeout=30)
    summary = consolidate(
        project, actor="t", tags=["mesh"], method="provider", summarizer=summarizer
    )["record_id"]
    project.amend(
        summary, {"review_state": "agent_reviewed"}, expected_revision=1, actor="t"
    )
    return summary


def test_a_reviewed_provider_summary_of_held_sources_is_left_out(project, repo, home):
    first, second = add(project, "First"), add(project, "Second")
    summary = provider_summary(project)
    link(project, first)
    link(project, second)
    result = run(repo, home)
    assert result.excluded["promoted"] == tuple(sorted([first, second, summary]))


def test_a_reviewed_provider_summary_with_an_eligible_source_stays(project, repo, home):
    first, second = add(project, "First " * 40), add(project, "Second " * 40)
    summary = provider_summary(project)
    link(project, first)
    result = run(repo, home)
    assert first in result.excluded["promoted"]
    assert summary not in result.excluded["promoted"]
    assert summary in included(result) or summary in result.excluded["duplicate"]
    assert second in included(result) or second in result.excluded["covered"]


def test_a_promoted_summary_is_left_out_itself(project, repo, home):
    source = add(project, "First")
    summary = make_summary(project)
    project.amend(
        summary, {"review_state": "user_confirmed"}, expected_revision=1, actor="t"
    )
    link(project, summary)
    result = run(repo, home)
    assert summary in result.excluded["promoted"]
    assert source in included(result)


# ------------------------------------------------------------ the hard token cap
def test_every_budget_is_a_hard_cap_with_held_records_around(project, repo, home):
    for number in range(12):
        add(project, f"Decision number {number} about the mesh " * 3)
        add_lesson(project, f"L{number:03d}")
    held = add(project, "Became a node")
    link(project, held)
    full = run(repo, home, budget=20000, include_imported=True)
    assert len(full.entries) == 25 - 1
    for budget in (120, 200, 400, 800, 1600):
        for options in ({}, {"include_imported": True, "include_promoted": True}):
            try:
                result = run(repo, home, budget=budget, **options)
            except RecordsError as exc:
                assert exc.code == "budget_too_small"
                continue
            text = result.render_markdown()
            assert result.used_tokens <= budget
            pieces = estimate_tokens(result.header) + estimate_tokens(result.footer)
            pieces += sum(estimate_tokens(entry.text) for entry in result.entries)
            assert pieces == result.used_tokens
            assert text.count("### ") == len(result.entries)


def test_held_records_do_not_spend_the_budget(project, repo, home):
    add(project, "Only this one")
    for number in range(20):
        add_lesson(project, f"L{number:03d}")
    result = run(repo, home, budget=400)
    assert len(result.entries) == 1
    assert result.omitted_by_budget == ()
    assert len(result.excluded["imported"]) == 20


def test_wake_output_stays_deterministic(project, repo, home):
    add(project, "First")
    second = add(project, "Second")
    add_lesson(project)
    link(project, second)
    first = run(repo, home)
    assert run(repo, home).render_markdown() == first.render_markdown()
    assert run(repo, home).to_json() == first.to_json()
    assert set(first.to_json()["report"]["excluded"]) == set(EXCLUSION_KINDS)


# ------------------------------------------------------------ wake reads the store
def test_wake_reads_only_the_records_store(project, repo, home, tmp_path):
    """No failure-memory registry, no AKMS node and no AKMS import, proved by audit."""
    secret = "zqx-unrelated-sentinel"
    knowledge = repo / ".knowledge"
    (knowledge / "local-nodes").mkdir(parents=True)
    (knowledge / "local-nodes" / "a-node.md").write_text(
        f"---\nid: a-node\n---\n{secret} failure lesson mesh\n", encoding="utf-8"
    )
    (knowledge / "lessons.json").write_text(
        json.dumps({"lessons": [{"id": "L999", "symptom": secret}]}), encoding="utf-8"
    )
    (knowledge / "failure-memory.toml").write_text(f"# {secret}\n", encoding="utf-8")
    (knowledge / "graph").mkdir()
    (knowledge / "graph" / "graph.json").write_text(f'"{secret}"', encoding="utf-8")
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "global.md").write_text(secret, encoding="utf-8")
    kept = add(project, "A mesh decision")
    lesson = add_lesson(project)
    project.close()
    env_home = str(home)
    done = subprocess.run(
        [sys.executable, str(AUDIT), str(repo), env_home, "scout"],
        capture_output=True,
        text=True,
        env={**os.environ, "AKMS_GLOBAL_VAULT": str(vault)},
    )
    assert done.returncode == 0, done.stderr
    report = json.loads(done.stdout)
    assert sorted(report["included"]) == sorted([kept, lesson])
    assert secret not in report["markdown"]
    assert report["used"] <= 4000
    records_root = (knowledge / "records").resolve()
    forbidden = [
        (knowledge / "local-nodes").resolve(),
        (knowledge / "graph").resolve(),
        (knowledge / "lessons.json").resolve(),
        (knowledge / "failure-memory.toml").resolve(),
        vault.resolve(),
    ]
    touched = []
    for name in report["opened"]:
        path = Path(name).resolve()
        if path.is_relative_to(repo.resolve()) or path.is_relative_to(
            tmp_path.resolve()
        ):
            touched.append(path)
            assert not any(
                path == bad or path.is_relative_to(bad) for bad in forbidden
            ), path
    assert any(path.is_relative_to(records_root) for path in touched)
