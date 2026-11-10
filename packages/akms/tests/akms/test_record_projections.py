"""Record projection integrity and loadout fail-closed regression tests."""

import hashlib
import importlib

import networkx as nx
import pytest

from akms.graph.record_projections import (
    FOOTER,
    ProjectionError,
    guard_projection_content,
    parse_projections,
    render_projection,
    replace_projection,
    source_snapshot,
)
from akms.schema.models import AgentRole, LoadoutMode


@pytest.fixture
def projection(tmp_path):
    source = tmp_path / "records" / "r1"
    source.mkdir(parents=True)
    (source / "000001.json").write_text('{"payload":"secret"}')
    body = "## Summary\nprivate summary\n\n## Pitfalls\nprivate warning\n"
    block = render_projection(
        body,
        record_id="r1",
        revision=1,
        source_dir={"base": "repo", "path": "records/r1"},
        source_sha256=source_snapshot(source),
        scope="project",
    )
    return source, body, block


def test_snapshot_protocol_and_non_events(projection):
    source, _, _ = projection
    data = (source / "000001.json").read_bytes()
    expected = hashlib.sha256(
        b"000001.json\0" + str(len(data)).encode() + b"\0" + data
    ).hexdigest()
    (source / "pending.tmp").write_text("ignored")
    assert source_snapshot(source, max_revision=1) == expected
    (source / "000003.json").write_text("new")
    with pytest.raises(ProjectionError):
        source_snapshot(source, max_revision=1)


def test_snapshot_symlink_rejected(projection):
    source, _, _ = projection
    (source / "000002.json").symlink_to(source / "000001.json")
    with pytest.raises(ProjectionError):
        source_snapshot(source)


def test_roundtrip_replace_preserves_authored_text(tmp_path, projection):
    _, body, block = projection
    text = "Manual before\n" + block + "Manual after\n"
    guarded = guard_projection_content(text, tmp_path)
    assert guarded.current and guarded.managed
    assert guarded.content == "Manual before\n" + body + "Manual after\n"
    assert replace_projection(text, "r1", "") == "Manual before\nManual after\n"
    with pytest.raises(ProjectionError):
        replace_projection(text.replace("private summary", "edit"), "r1", "")


@pytest.mark.parametrize("fence", ["```", "~~~", "   ````"])
def test_fenced_fake_markers_are_data(tmp_path, projection, fence):
    source, _, _ = projection
    fake = f"{fence}\n<!-- akms-records-projection/v1 nonsense -->\n{FOOTER}\n{fence}\n"
    assert not guard_projection_content(fake, tmp_path).managed
    block = render_projection(
        fake,
        record_id="r1",
        revision=1,
        source_dir={"base": "repo", "path": "records/r1"},
        source_sha256=source_snapshot(source),
    )
    assert guard_projection_content(block, tmp_path).content == fake


@pytest.mark.parametrize(
    "mutation",
    ["append", "missing", "corrupt", "manual", "duplicate", "unclosed", "nested"],
)
def test_invalid_sources_or_blocks_fail_closed(tmp_path, projection, mutation):
    source, _, block = projection
    if mutation == "append":
        (source / "000002.json").write_text("new event")
    elif mutation == "missing":
        (source / "000001.json").unlink()
    elif mutation == "corrupt":
        (source / "000001.json").write_text("broken")
    elif mutation == "manual":
        block = block.replace("private summary", "edited")
    elif mutation == "duplicate":
        block += block
    elif mutation == "unclosed":
        block = block.replace(FOOTER, "")
    else:
        block = block.replace("## Summary", block + "## Summary")
    guarded = guard_projection_content("Manual prose\n" + block, tmp_path)
    assert guarded.managed and not guarded.current and guarded.content == ""


def test_legacy_projection_requires_upgrade(tmp_path):
    text = "Promoted from a stored record.\n## Sources\n- record: r1\n"
    assert not guard_projection_content(text, tmp_path).current
    assert not guard_projection_content("```\n" + text + "```\n", tmp_path).managed


def test_source_traversal_rejected(projection):
    _, _, block = projection
    with pytest.raises(ProjectionError):
        parse_projections(block.replace('"records/r1"', '"../records/r1"'))


@pytest.mark.parametrize(
    "mode,priority",
    [
        (LoadoutMode.ROUTING, None),
        (LoadoutMode.FULL, None),
        (LoadoutMode.ROUTING, "pitfalls-only"),
        (LoadoutMode.FULL, "summary"),
    ],
)
@pytest.mark.parametrize("stale", [False, True])
@pytest.mark.parametrize("explicit_ref", [False, True])
def test_loadout_uses_disk_and_hides_entire_stale_node(
    tmp_path, monkeypatch, projection, mode, priority, stale, explicit_ref
):
    source, _, block = projection
    module = importlib.import_module("akms.graph.generate_loadout")
    monkeypatch.setattr(
        module,
        "get_cached",
        lambda *a: [
            {
                "path": ".knowledge/local-nodes/n1.md",
                "line": 1,
                "content": "stale cached secret",
            }
        ],
    )
    monkeypatch.setattr(module, "_retrieve_node_content_qmd", lambda *a: [])
    monkeypatch.setattr(module.shutil, "which", lambda _: "/fake/qmd")
    path = tmp_path / ".knowledge/local-nodes/n1.md"
    path.parent.mkdir(parents=True)
    path.write_text("---\nid: n1\n---\nManual private prose\n" + block)
    if stale:
        (source / "000002.json").write_text("retracted")
    data = {
        "title": "private title",
        "node_origin": "local",
        "reading_priority": priority,
        "session_refs": ["private-session"],
    }
    if explicit_ref:
        data["content_ref"] = ".knowledge/local-nodes/n1.md"
    graph = nx.DiGraph()
    graph.add_node("n1", **data)
    graph.add_edge("n1", "other", type="pitfall", note="private edge")
    result = module.generate_loadout(
        graph,
        [("n1", data)],
        task_id="task",
        phase=1,
        graph_version="v1",
        seed_tags=[],
        agent_role=AgentRole.IMPLEMENTER,
        mode=mode,
        repo_root=tmp_path,
    )
    assert "stale cached secret" not in result
    assert "akms-records-projection" not in result
    assert "source_sha256" not in result
    if stale:
        assert "Record projection needs review" in result
        assert "private" not in result
        assert "local-nodes/n1.md" not in result
    else:
        assert (
            "private warning" in result
            if priority == "pitfalls-only"
            else "private summary" in result
        )
    assert path.read_text().endswith(block)


def test_source_revision_can_include_link_event(tmp_path, projection):
    source, body, _ = projection
    (source / "000002.json").write_text("link event")
    block = render_projection(
        body,
        record_id="r1",
        revision=1,
        source_revision=2,
        source_dir={"base": "repo", "path": "records/r1"},
        source_sha256=source_snapshot(source),
    )
    assert guard_projection_content(block, tmp_path).current


def test_graph_retains_projection_hint_and_missing_file_fails_closed(
    tmp_path, monkeypatch, projection
):
    from akms.graph.build_graph import build_graph

    source, _, block = projection
    module = importlib.import_module("akms.graph.generate_loadout")
    monkeypatch.setattr(module, "get_cached", lambda *a: None)
    monkeypatch.setattr(module, "_retrieve_node_content_qmd", lambda *a: [])
    path = tmp_path / ".knowledge/local-nodes/n1.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        "---\nid: n1\ntitle: private title\nakms_schema: v2\ndomain: test\nstatus: tentative\nconfidence: 0.7\nsource: agent\ntags: [test]\n---\n"
        + block
    )
    vault = tmp_path / "vault"
    vault.mkdir()
    graph = build_graph(tmp_path, global_vault=vault)
    assert graph.nodes["n1"]["_record_projection"] is True
    path.unlink()
    result = module.generate_loadout(
        graph,
        [("n1", dict(graph.nodes["n1"]))],
        task_id="t",
        phase=1,
        graph_version="v1",
        seed_tags=[],
        agent_role=AgentRole.IMPLEMENTER,
        repo_root=tmp_path,
    )
    assert "private" not in result
    assert "Record projection needs review" in result


def test_mixed_projections_hide_whole_node_if_one_stale(tmp_path, projection):
    source, body, block = projection
    other = tmp_path / "records/r2"
    other.mkdir()
    (other / "000001.json").write_text("another record")
    second = render_projection(
        body,
        record_id="r2",
        revision=1,
        source_dir={"base": "repo", "path": "records/r2"},
        source_sha256=source_snapshot(other),
    )
    mixed = "Manual content\n" + block + second
    assert guard_projection_content(mixed, tmp_path).current
    (other / "000001.json").unlink()
    guarded = guard_projection_content(mixed, tmp_path)
    assert not guarded.current and not guarded.content


def test_repo_source_symlink_escape_rejected(tmp_path, projection):
    source, _, block = projection
    link = tmp_path / "escape"
    link.symlink_to(tmp_path.parent, target_is_directory=True)
    block = block.replace('"records/r1"', '"escape"')
    assert not guard_projection_content(block, tmp_path).current


def test_mixed_legacy_and_managed_requires_upgrade(tmp_path, projection):
    _, _, block = projection
    mixed = (
        block + "\nPromoted from a stored record.\n## Sources\n- record: `legacy@1`\n"
    )
    guarded = guard_projection_content(mixed, tmp_path)
    assert guarded.managed and not guarded.current and guarded.content == ""


def test_optional_source_title_is_validated_and_hidden(tmp_path, projection):
    source, body, _ = projection
    block = render_projection(
        body,
        record_id="r1",
        revision=1,
        source_dir={"base": "repo", "path": "records/r1"},
        source_sha256=source_snapshot(source),
        source_title="Secret generated title",
    )
    assert (
        parse_projections(block)[0].metadata["source_title"] == "Secret generated title"
    )
    guard = guard_projection_content(block, tmp_path)
    assert guard.current and "Secret generated title" not in guard.content
    bad = block.replace('"Secret generated title"', "42")
    with pytest.raises(ProjectionError, match="Invalid projection metadata"):
        parse_projections(bad)


def test_snapshot_rejects_fifo_without_blocking(projection):
    import os

    source, _, _ = projection
    os.mkfifo(source / "000002.json")
    with pytest.raises(ProjectionError):
        source_snapshot(source)


def test_historical_prefix_is_explicit_and_contiguous(projection):
    source, _, _ = projection
    original = source_snapshot(source, max_revision=1)
    (source / "000002.json").write_text("link event")
    assert source_snapshot(source, max_revision=1, prefix=True) == original
    with pytest.raises(ProjectionError):
        source_snapshot(source, max_revision=1)
    with pytest.raises(ProjectionError):
        source_snapshot(source, prefix=True)
    (source / "000002.json").unlink()
    (source / "000003.json").write_text("gap")
    with pytest.raises(ProjectionError):
        source_snapshot(source, max_revision=2, prefix=True)


def test_prefix_rejects_unstable_complete_listing(projection, monkeypatch):
    from pathlib import Path

    source, _, _ = projection
    original_iterdir = Path.iterdir
    calls = 0

    def changing_iterdir(path):
        nonlocal calls
        calls += 1
        if calls == 2:
            (source / "000002.json").write_text("concurrent append")
        return original_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", changing_iterdir)
    with pytest.raises(ProjectionError):
        source_snapshot(source, max_revision=1, prefix=True)


def test_pre_dependency_metadata_requires_explicit_upgrade(tmp_path, projection):
    _, _, block = projection
    legacy = block.replace('"dependencies": [], ', "")
    assert parse_projections(legacy)
    guarded = guard_projection_content(legacy, tmp_path)
    assert guarded.managed and not guarded.current
    assert guarded.reason == "dependency metadata requires upgrade"


@pytest.mark.parametrize("dependencies", [None, {}, [None], [{"revision": True}]])
def test_malformed_dependency_metadata_fails_closed(tmp_path, projection, dependencies):
    import json

    _, _, block = projection
    malformed = block.replace(
        '"dependencies": []', '"dependencies": ' + json.dumps(dependencies)
    )
    assert not guard_projection_content(malformed, tmp_path).current


def test_collection_witness_tracks_membership_and_events_but_excludes_self(tmp_path):
    from akms.graph.record_projections import collection_snapshot

    own = tmp_path / "month/self"
    other = tmp_path / "month/other"
    own.mkdir(parents=True)
    other.mkdir()
    (own / "000001.json").write_text("own")
    (other / "000001.json").write_text("other")
    before = collection_snapshot(tmp_path, excluded_path="month/self")
    (own / "000002.json").write_text("own promotion link")
    (tmp_path / "cache.json").write_text("irrelevant index")
    assert collection_snapshot(tmp_path, excluded_path="month/self") == before
    (other / "000002.json").write_text("amended")
    changed = collection_snapshot(tmp_path, excluded_path="month/self")
    assert changed != before
    new = tmp_path / "next/new"
    new.mkdir(parents=True)
    (new / "000001.json").write_text("new input")
    assert collection_snapshot(tmp_path, excluded_path="month/self") != changed


def test_collection_witness_rejects_symlinked_event(tmp_path):
    from akms.graph.record_projections import collection_snapshot

    (tmp_path / "000001.json").symlink_to(tmp_path / "target")
    (tmp_path / "target").write_text("event")
    with pytest.raises(ProjectionError):
        collection_snapshot(tmp_path, excluded_path="self")


def test_old_citation_only_projection_requires_collection_upgrade(tmp_path, projection):
    _, _, block = projection
    old = block.replace('"collection": null, ', "")
    assert parse_projections(old)
    assert not guard_projection_content(old, tmp_path).current


@pytest.mark.parametrize("excluded", ["", ".", "..", "../other", "/absolute"])
def test_collection_exclusion_cannot_cover_the_store_or_escape(tmp_path, excluded):
    from akms.graph.record_projections import collection_snapshot

    with pytest.raises(ProjectionError):
        collection_snapshot(tmp_path, excluded_path=excluded)
