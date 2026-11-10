"""End-to-end promotion freshness, guarded reads, and explicit withdrawal."""

from __future__ import annotations

import importlib
import json

import pytest

pytest.importorskip("akms")
import frontmatter  # noqa: E402
from akms.graph.build_graph import load_graph  # noqa: E402
from akms.graph.generate_loadout import generate_loadout  # noqa: E402
from akms.graph.record_projections import parse_projections  # noqa: E402
from akms.layout import local_knowledge_dir  # noqa: E402
from akms.schema.models import AgentRole, LoadoutMode  # noqa: E402
from akms_records import RecordsError  # noqa: E402
from akms_records.bridge import (
    confirm_yes,
    promote,
    promotion_status,
    withdraw_promotion,
)  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_sources(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(vault))
    module = importlib.import_module("akms.graph.generate_loadout")
    monkeypatch.setattr(module, "_retrieve_node_content_qmd", lambda *a: [])
    monkeypatch.setattr(module, "get_cached", lambda *a: None)


def create(store, text="OLD PRIVATE PAYLOAD"):
    return store.create(
        {
            "schema_ref": "decision/v1",
            "payload": {"decision": text, "rationale": "private rationale"},
            "review_state": "user_confirmed",
            "origin": {"kind": "human-confirmed", "actor_id": "t"},
        },
        actor="t",
    ).record_id


def publish(store, rid, repo, **kwargs):
    return promote(store, rid, repo=repo, actor="t", review="approved", **kwargs)


def node_path(repo):
    [path] = list((local_knowledge_dir(repo) / "local-nodes").glob("*.md"))
    return path


def state(store, rid, repo):
    return promotion_status(store, rid, repo=repo)["results"][0]["state"]


def withdraw(store, rid, repo, **kwargs):
    kwargs.setdefault(
        "expected_revision", None if kwargs.get("erased") else store.get(rid).revision
    )
    return withdraw_promotion(
        store,
        rid,
        repo=repo,
        actor="t",
        reason="No longer applicable",
        confirm=confirm_yes,
        **kwargs,
    )


def loadout(repo):
    graph = load_graph(local_knowledge_dir(repo) / "graph/graph.json")
    return generate_loadout(
        graph,
        list(graph.nodes(data=True)),
        task_id="test",
        phase=1,
        graph_version="v1",
        seed_tags=["decision"],
        agent_role=AgentRole.IMPLEMENTER,
        repo_root=repo,
        mode=LoadoutMode.FULL,
    )


def test_amend_withholds_old_content_update_restores_current(store, repo):
    rid = create(store)
    publish(store, rid, repo)
    assert state(store, rid, repo) == "current"
    store.amend(
        rid,
        {"payload": {"decision": "NEW CONTENT", "rationale": "new rationale"}},
        expected_revision=store.get(rid).revision,
        actor="t",
    )
    assert state(store, rid, repo) == "source_changed"
    rendered = loadout(repo)
    assert "OLD PRIVATE PAYLOAD" not in rendered
    assert "Record projection needs review" in rendered
    publish(store, rid, repo, update=True)
    text = node_path(repo).read_text()
    assert "OLD PRIVATE PAYLOAD" not in text
    assert "NEW CONTENT" in text
    assert state(store, rid, repo) == "current"
    assert "NEW CONTENT" in loadout(repo)


def test_manually_edited_sources_remain_discoverable_and_refused(store, repo):
    rid = create(store)
    publish(store, rid, repo)
    path = node_path(repo)
    path.write_text(
        path.read_text().replace(f"- record: `{rid}@1`", "- record: `manual-edit@1`")
    )
    before = path.read_bytes()
    assert state(store, rid, repo) == "projection_stale"
    for action in (
        lambda: publish(store, rid, repo, update=True),
        lambda: withdraw(store, rid, repo),
    ):
        with pytest.raises(RecordsError) as exc:
            action()
        assert exc.value.code == "projection_conflict"
        assert path.read_bytes() == before


@pytest.mark.parametrize(
    "field,expected",
    [("scope", "scope_violation"), ("source_dir", "projection_source_mismatch")],
)
def test_source_identity_collision_refused(store, repo, field, expected):
    rid = create(store)
    publish(store, rid, repo)
    path = node_path(repo)
    post = frontmatter.load(path)
    block = parse_projections(post.content)[0]
    old = block.metadata[field]
    new = (
        "project:other" if field == "scope" else {"base": "repo", "path": "other-store"}
    )
    post.content = post.content.replace(
        json.dumps(old, sort_keys=True), json.dumps(new, sort_keys=True), 1
    )
    path.write_text(frontmatter.dumps(post) + "\n")
    before = path.read_bytes()
    for action in (
        lambda: publish(store, rid, repo, update=True),
        lambda: withdraw(store, rid, repo),
    ):
        with pytest.raises(RecordsError) as exc:
            action()
        assert exc.value.code in {expected, "projection_source_mismatch"}
        assert path.read_bytes() == before


@pytest.mark.parametrize("lifecycle", ["retract", "erase"])
def test_inactive_source_withheld_and_explicit_withdrawal(store, repo, lifecycle):
    rid = create(store)
    publish(store, rid, repo)
    if lifecycle == "erase":
        store.erase(rid, actor="t", reason="privacy")
    else:
        store.retract(
            rid, actor="t", reason="obsolete", expected_revision=store.get(rid).revision
        )
    assert state(store, rid, repo) == (
        "source_erased" if lifecycle == "erase" else "source_retracted"
    )
    assert "OLD PRIVATE PAYLOAD" not in loadout(repo)
    result = withdraw(store, rid, repo, erased=lifecycle == "erase")
    assert result["action"] == "withdrawn"
    assert "OLD PRIVATE PAYLOAD" not in node_path(repo).read_text()
    assert state(store, rid, repo) == "withdrawn"


def test_active_withdrawal_requires_current_revision_and_clears_live_link(store, repo):
    rid = create(store)
    publish(store, rid, repo)
    before = node_path(repo).read_bytes()
    with pytest.raises(RecordsError) as exc:
        withdraw(store, rid, repo, expected_revision=1)
    assert exc.value.code == "stale_revision"
    assert node_path(repo).read_bytes() == before
    assert withdraw(store, rid, repo)["action"] == "withdrawn"
    assert store.get(rid).promoted_to is None
    assert store.get(rid).lifecycle == "active"
    assert "OLD PRIVATE PAYLOAD" not in loadout(repo)


@pytest.mark.parametrize("manual_title", [False, True])
def test_erased_mixed_node_preserves_manual_prose_not_generated_title(
    store, repo, manual_title
):
    rid = create(store)
    publish(store, rid, repo)
    path = node_path(repo)
    post = frontmatter.load(path)
    post.content += "\n\nUnrelated authored guidance.\n"
    if manual_title:
        post.metadata["title"] = "My authored title"
    path.write_text(frontmatter.dumps(post) + "\n")
    store.erase(rid, actor="t", reason="privacy")
    withdraw(store, rid, repo, erased=True)
    after = path.read_text()
    assert "Unrelated authored guidance." in after
    assert "OLD PRIVATE PAYLOAD" not in after
    assert ("My authored title" in after) is manual_title
    assert "OLD PRIVATE PAYLOAD" not in loadout(repo)


def test_withdrawal_graph_failure_is_retryable(store, repo, monkeypatch):
    rid = create(store)
    publish(store, rid, repo)
    graph_module = importlib.import_module("akms.graph.build_graph")
    original = graph_module.build_graph
    monkeypatch.setattr(
        graph_module,
        "build_graph",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("test failure")),
    )
    with pytest.raises(RecordsError) as exc:
        withdraw(store, rid, repo)
    assert exc.value.code == "promote_graph_failed"
    assert "OLD PRIVATE PAYLOAD" not in node_path(repo).read_text()
    assert store.get(rid).promoted_to is not None
    assert "OLD PRIVATE PAYLOAD" not in loadout(repo)
    monkeypatch.setattr(graph_module, "build_graph", original)
    withdraw(store, rid, repo)
    assert store.get(rid).promoted_to is None
    assert "OLD PRIVATE PAYLOAD" not in loadout(repo)


def test_mixed_exact_and_edited_legacy_blocks_refuse_partial_migration(store, repo):
    from akms_records.bridge import node_body

    rid = create(store)
    publish(store, rid, repo)
    path = node_path(repo)
    post = frontmatter.load(path)
    record = store.get(rid)
    legacy = node_body(record, revision=record.content_revision, actor="t")
    edited = legacy.replace("OLD PRIVATE PAYLOAD", "Manually corrected legacy claim")
    post.content = legacy + "\n\nAuthored separator.\n\n" + edited
    path.write_text(frontmatter.dumps(post) + "\n")
    before = path.read_bytes()
    history = store.history(rid)

    with pytest.raises(RecordsError) as exc:
        publish(store, rid, repo, update=True)

    assert exc.value.code == "projection_conflict"
    assert path.read_bytes() == before
    assert store.history(rid) == history


@pytest.mark.parametrize("field", ["scope", "source_dir"])
def test_status_reports_source_identity_mismatch_even_with_valid_fingerprint(
    store, repo, tmp_path, field
):
    import shutil

    from akms.graph.record_projections import guard_projection_content

    rid = create(store)
    publish(store, rid, repo)
    path = node_path(repo)
    post = frontmatter.load(path)
    metadata = parse_projections(post.content)[0].metadata
    if field == "scope":
        replacement = "project:other"
    else:
        foreign = tmp_path / "foreign-source"
        # A missing directory would already fail freshness. This case must prove
        # the status command checks identity as well as a valid event fingerprint.
        shutil.copytree(store.record_dir(rid), foreign)
        replacement = {"base": "absolute", "path": str(foreign)}
    post.content = post.content.replace(
        json.dumps(metadata[field], sort_keys=True),
        json.dumps(replacement, sort_keys=True),
        1,
    )
    path.write_text(frontmatter.dumps(post) + "\n")
    assert guard_projection_content(post.content, repo).current
    before = path.read_bytes()
    history = store.history(rid)

    report = promotion_status(store, rid, repo=repo)

    assert report["status"] == "drift"
    assert report["results"][0]["state"] != "current"
    assert path.read_bytes() == before
    assert store.history(rid) == history


def cached_loadout(repo, graph):
    return generate_loadout(
        graph,
        list(graph.nodes(data=True)),
        task_id="cached",
        phase=1,
        graph_version="v1",
        seed_tags=["decision"],
        agent_role=AgentRole.IMPLEMENTER,
        repo_root=repo,
        mode=LoadoutMode.FULL,
    )


@pytest.mark.parametrize("change", ["amend", "retract", "erase"])
def test_promoted_summary_tracks_cited_dependency(store, repo, change):
    from akms_records import consolidate

    rid = create(store)
    summary = consolidate(store, actor="t")["record_id"]
    store.amend(
        summary, {"review_state": "user_confirmed"}, expected_revision=1, actor="t"
    )
    publish(store, summary, repo)
    graph = load_graph(local_knowledge_dir(repo) / "graph/graph.json")
    assert "OLD PRIVATE PAYLOAD" in cached_loadout(repo, graph)
    if change == "amend":
        store.amend(
            rid,
            {"payload": {"decision": "corrected", "rationale": "new"}},
            expected_revision=store.get(rid).revision,
            actor="t",
        )
    elif change == "retract":
        store.retract(
            rid, reason="obsolete", actor="t", expected_revision=store.get(rid).revision
        )
    else:
        store.erase(rid, reason="privacy", actor="t")
    assert state(store, summary, repo) == (
        "source_erased" if change == "erase" else "projection_stale"
    )
    output = cached_loadout(repo, graph)
    assert "OLD PRIVATE PAYLOAD" not in output
    assert "Record projection needs review" in output


def test_cached_graph_uses_current_disk_title_after_update(store, repo):
    rid = create(store)
    publish(store, rid, repo)
    graph = load_graph(local_knowledge_dir(repo) / "graph/graph.json")
    store.amend(
        rid,
        {"payload": {"decision": "CURRENT TITLE", "rationale": "new"}},
        expected_revision=store.get(rid).revision,
        actor="t",
    )
    publish(store, rid, repo, update=True)
    output = cached_loadout(repo, graph)
    assert "OLD PRIVATE PAYLOAD" not in output
    assert "CURRENT TITLE" in output
    assert graph.nodes[rid]["title"] == "OLD PRIVATE PAYLOAD"


@pytest.mark.parametrize("human", [False, True])
@pytest.mark.parametrize("mixed", [False, True])
def test_withdrawn_record_can_be_repromoted_without_false_notice(
    store, repo, human, mixed
):
    if human:
        store.policies.set(
            "decision",
            source="human",
            status="established",
            confidence=0.8,
            actor="t",
            at=store.now(),
        )
    rid = create(store)
    publish(store, rid, repo, confirm=confirm_yes)
    path = node_path(repo)
    if mixed:
        post = frontmatter.load(path)
        post.content += "\n\nHuman authored guidance.\n"
        post.metadata["title"] = "Human authored title"
        path.write_text(frontmatter.dumps(post) + "\n")
    withdraw(store, rid, repo)
    if human:
        before = path.read_bytes()
        with pytest.raises(RecordsError) as exc:
            publish(store, rid, repo)
        assert exc.value.code == "confirmation_required"
        assert path.read_bytes() == before
    publish(store, rid, repo, confirm=confirm_yes)
    assert state(store, rid, repo) == "current"
    assert node_path(repo) == path
    output = loadout(repo)
    assert "OLD PRIVATE PAYLOAD" in output
    assert "No record content remains" not in output
    assert "<!-- akms-records-withdrawn" not in path.read_text()
    if mixed:
        assert "Human authored guidance." in output
        assert "Human authored title" in output
    assert (
        publish(store, rid, repo, confirm=confirm_yes)["action"] == "already_promoted"
    )


def test_projection_on_node_with_external_content_ref_serves_both(store, repo):
    from akms.graph.build_graph import build_graph

    rid = create(store)
    publish(store, rid, repo)
    path = node_path(repo)
    post = frontmatter.load(path)
    post.metadata["content_ref"] = "authored.md"
    post.content += "\nLocal authored guidance.\n"
    path.write_text(frontmatter.dumps(post) + "\n")
    (repo / "authored.md").write_text("External authored guidance.\n")
    build_graph(repo)
    graph = load_graph(local_knowledge_dir(repo) / "graph/graph.json")
    output = cached_loadout(repo, graph)
    assert "Record projection needs review" not in output
    assert "OLD PRIVATE PAYLOAD" in output
    assert "Local authored guidance." in output
    assert "External authored guidance." in output
    store.amend(
        rid,
        {"payload": {"decision": "CURRENT CLAIM", "rationale": "new"}},
        expected_revision=store.get(rid).revision,
        actor="t",
    )
    assert "OLD PRIVATE PAYLOAD" not in cached_loadout(repo, graph)
    publish(store, rid, repo, update=True)
    output = cached_loadout(repo, graph)
    assert "CURRENT CLAIM" in output
    assert "External authored guidance." in output
    assert "OLD PRIVATE PAYLOAD" not in output


@pytest.mark.parametrize("human", [False, True])
def test_legacy_withdrawal_marker_restores_from_verified_history(store, repo, human):
    if human:
        store.policies.set(
            "decision",
            source="human",
            status="established",
            confidence=0.8,
            actor="t",
            at=store.now(),
        )
    rid = create(store)
    publish(store, rid, repo, confirm=confirm_yes)
    withdraw(store, rid, repo)
    path = node_path(repo)
    post = frontmatter.load(path)
    prefix = "<!-- akms-records-withdrawn/v1 "
    lines = post.content.splitlines()
    for index, line in enumerate(lines):
        if line.startswith(prefix):
            metadata = json.loads(line[len(prefix) : -4])
            metadata.pop("source_dir", None)
            lines[index] = prefix + json.dumps(metadata, sort_keys=True) + " -->"
    post.content = "\n".join(lines)
    path.write_text(frontmatter.dumps(post) + "\n")
    publish(store, rid, repo, confirm=confirm_yes)
    assert "No record content remains" not in loadout(repo)
    assert state(store, rid, repo) == "current"


def test_new_promotion_deduplicates_into_external_content_node(store, repo):
    from akms.graph.build_graph import build_graph
    from akms.schema.models import LocalNodeFrontmatter

    rid = create(store)
    directory = local_knowledge_dir(repo) / "local-nodes"
    directory.mkdir(parents=True)
    model = LocalNodeFrontmatter(
        id=rid,
        title="OLD PRIVATE PAYLOAD",
        domain="example",
        tags=["decision"],
        source="agent",
        status="tentative",
        confidence=0.5,
        content_ref="authored.md",
    )
    path = directory / "arbitrary-filename.md"
    post = frontmatter.Post(
        "Local authored guidance.", **model.model_dump(mode="json", exclude_none=True)
    )
    path.write_text(frontmatter.dumps(post) + "\n")
    (repo / "authored.md").write_text("External authored guidance.\n")
    build_graph(repo)
    result = publish(store, rid, repo)
    assert result["action"] == "dedup_appended"
    assert result["node_id"] == rid
    output = loadout(repo)
    assert "Record projection needs review" not in output
    assert "private rationale" in output
    assert "Local authored guidance." in output
    assert "External authored guidance." in output


@pytest.mark.parametrize("change", ["create", "amend_into_topic"])
def test_promoted_summary_tracks_topic_input_set(store, repo, change):
    from akms_records import consolidate, consolidation_status

    rid = create(store, "Original mesh decision")
    store.amend(rid, {"tags": ["mesh"]}, expected_revision=1, actor="t")
    other = (
        create(store, "New matching decision") if change == "amend_into_topic" else None
    )
    summary = consolidate(store, actor="t", tags=["mesh"])["record_id"]
    store.amend(
        summary, {"review_state": "user_confirmed"}, expected_revision=1, actor="t"
    )
    publish(store, summary, repo)
    graph = load_graph(local_knowledge_dir(repo) / "graph/graph.json")
    assert state(store, summary, repo) == "current"
    if other is None:
        store.create(
            {
                "schema_ref": "decision/v1",
                "payload": {"decision": "New matching decision", "rationale": "new"},
                "tags": ["mesh"],
            },
            actor="t",
        )
    else:
        store.amend(other, {"tags": ["mesh"]}, expected_revision=1, actor="t")
    assert consolidation_status(store, summary)["status"] == "stale"
    assert state(store, summary, repo) == "projection_stale"
    output = cached_loadout(repo, graph)
    assert "Original mesh decision" not in output
    assert "Record projection needs review" in output


def test_malformed_promoted_yaml_withholds_node_without_aborting_loadout(store, repo):
    rid = create(store)
    publish(store, rid, repo)
    graph = load_graph(local_knowledge_dir(repo) / "graph/graph.json")
    graph.add_node("unrelated", title="Unaffected guidance", node_origin="local")
    path = node_path(repo)
    text = path.read_text()
    text = text.replace("title: OLD PRIVATE PAYLOAD", "title: [broken")
    assert "title: [broken" in text
    path.write_text(text)
    output = cached_loadout(repo, graph)
    assert "Record projection needs review" in output
    assert "OLD PRIVATE PAYLOAD" not in output
    assert "Unaffected guidance" in output


def test_unrelated_collection_change_can_be_explicitly_resealed(store, repo):
    from akms_records import consolidate, consolidation_status

    rid = create(store, "Mesh decision")
    store.amend(rid, {"tags": ["mesh"]}, expected_revision=1, actor="t")
    summary = consolidate(store, actor="t", tags=["mesh"])["record_id"]
    store.amend(
        summary, {"review_state": "user_confirmed"}, expected_revision=1, actor="t"
    )
    publish(store, summary, repo)
    create(store, "Unrelated outside-topic record")
    assert consolidation_status(store, summary)["status"] == "valid"
    assert state(store, summary, repo) == "projection_stale"
    publish(store, summary, repo)
    assert state(store, summary, repo) == "current"
    assert "Mesh decision" in loadout(repo)
