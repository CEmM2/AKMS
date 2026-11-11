"""Real processes exercise lock publication, replacement, and crash recovery."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

pytest.importorskip("akms")
import frontmatter
from akms.graph.build_graph import build_graph
from akms.graph.record_projections import parse_projections
from akms.layout import local_knowledge_dir
from akms.schema.models import LocalNodeFrontmatter
from akms_records.bridge import promotion_status

WORKER = Path(__file__).parent / "workers/promoter.py"


def wait_for(*paths):
    deadline = time.monotonic() + 20
    while not any(path.exists() for path in paths):
        if time.monotonic() > deadline:
            pytest.fail(f"process barrier timed out: {paths}")
        time.sleep(0.01)


def finish(process):
    stdout, stderr = process.communicate(timeout=20)
    assert process.returncode == 0, stdout + stderr


def start(repo, rid, mode, barriers):
    return subprocess.Popen(
        [sys.executable, str(WORKER), str(repo), rid, mode, str(barriers)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


@pytest.fixture
def race(store, repo, tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(vault))
    ids = []
    for word in ("first", "second"):
        ids.append(
            store.create(
                {
                    "schema_ref": "decision/v1",
                    "payload": {
                        "decision": f"Shared promotion {word}",
                        "rationale": "source preserved",
                    },
                    "review_state": "user_confirmed",
                    "origin": {"kind": "human-confirmed", "actor_id": "t"},
                },
                actor="t",
            ).record_id
        )
    knowledge = local_knowledge_dir(repo)
    nodes = knowledge / "local-nodes"
    nodes.mkdir(parents=True)
    model = LocalNodeFrontmatter(
        id="shared",
        title="Shared promotion",
        domain="example",
        tags=["decision"],
        source="agent",
        status="tentative",
        confidence=0.5,
    )
    path = nodes / "shared.md"
    path.write_text(
        frontmatter.dumps(
            frontmatter.Post(
                "Human authored shared guidance.",
                **model.model_dump(mode="json", exclude_none=True),
            )
        )
        + "\n"
    )
    graph = knowledge / "graph"
    graph.mkdir()
    (graph / "propagation_config.yaml").write_text(
        "akms_schema: v2\ngraph:\n  dedup_threshold: 0.0\n"
    )
    build_graph(repo)
    barriers = tmp_path / "barriers"
    barriers.mkdir()
    return ids, path, barriers


def assert_preserved(store, repo, ids, path):
    body = frontmatter.load(path).content
    assert {block.metadata["record_id"] for block in parse_projections(body)} == set(
        ids
    )
    assert "Human authored shared guidance." in body
    for rid in ids:
        record = store.get(rid)
        assert record.payload["rationale"] == "source preserved"
        assert record.promoted_to["node_id"] == "shared"
        report = promotion_status(store, rid, repo=repo)
        assert report["results"][0]["state"] == "current"
        assert report["results"][0]["nodes"][0]["current"]


@pytest.mark.parametrize("stale", [False, True])
def test_overlapping_promotions_cannot_steal_unpublished_owner(
    store, repo, race, stale
):
    ids, path, barriers = race
    if stale:
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        lock = local_knowledge_dir(repo) / "records/.index/promote.lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text(str(dead.pid))
    first = start(repo, ids[0], "init", barriers)
    processes = [first]
    try:
        wait_for(barriers / "init.ready")
        second = start(repo, ids[1], "write", barriers)
        processes.append(second)
        wait_for(barriers / "write.ready", barriers / "write.result.json")
        # On the old implementation, B owns A's empty PID file and has read
        # the shared node. Let A finish before B writes its stale read back.
        (barriers / "init.release").touch()
        finish(first)
        (barriers / "write.release").touch()
        finish(second)
        outcome = json.loads((barriers / "write.result.json").read_text())
        if "error" not in outcome:
            # This assertion reproduces the former lost projection, not just
            # the fact that two lock contexts were entered simultaneously.
            assert_preserved(store, repo, ids, path)
        assert outcome == {"error": "promote_locked"}
        retry = start(repo, ids[1], "plain", barriers)
        processes.append(retry)
        finish(retry)
        assert "error" not in json.loads((barriers / "plain.result.json").read_text())
        assert_preserved(store, repo, ids, path)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.communicate()


@pytest.mark.parametrize("stage", ["init", "body"])
def test_killed_owner_releases_guard_and_retry_preserves_sources(
    store, repo, race, stage
):
    ids, path, barriers = race
    owner = start(repo, ids[0], stage, barriers)
    try:
        wait_for(barriers / f"{stage}.ready")
        owner.kill()
        owner.communicate(timeout=10)
        assert store.get(ids[0]).promoted_to is None
        for rid in reversed(ids):
            retry = start(repo, rid, "plain", barriers)
            finish(retry)
            assert "error" not in json.loads(
                (barriers / "plain.result.json").read_text()
            )
        assert_preserved(store, repo, ids, path)
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.communicate()


@pytest.mark.parametrize("other_projection", [False, True])
def test_status_requires_its_own_projection_not_another_current_block(
    store, repo, race, other_projection
):
    from akms.graph.record_projections import replace_projection
    from akms_records.bridge import promote

    ids, path, _ = race
    for rid in ids if other_projection else ids[:1]:
        promote(store, rid, repo=repo, review="approved", actor="t")
    post = frontmatter.load(path)
    post.content = replace_projection(post.content, ids[0], "")
    path.write_text(frontmatter.dumps(post) + "\n")
    before = path.read_bytes()
    history = store.history(ids[0])
    report = promotion_status(store, ids[0], repo=repo)
    row = report["results"][0]
    assert report["status"] == "drift"
    assert row["state"] == "projection_missing"
    assert row["nodes"][0]["current"] is False
    assert row["nodes"][0]["reason"] == "matching record projection missing"
    assert path.read_bytes() == before
    assert store.history(ids[0]) == history
    if other_projection:
        assert (
            promotion_status(store, ids[1], repo=repo)["results"][0]["state"]
            == "current"
        )


def test_lock_left_under_this_pid_is_reclaimed(store, repo, race):
    """A killed run whose PID this process reuses must not block it for good."""
    import os

    from akms_records.bridge import promote

    ids, _, _ = race
    lock = local_knowledge_dir(repo) / "records/.index/promote.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(str(os.getpid()))
    promote(store, ids[0], repo=repo, review="approved", actor="t")
    assert store.get(ids[0]).promoted_to is not None
    assert not lock.exists()


def test_second_thread_of_this_process_is_refused(repo):
    import threading

    from akms_records import RecordsError
    from akms_records.bridge import _promote_lock

    knowledge = local_knowledge_dir(repo)
    codes = []

    def contend():
        try:
            with _promote_lock(knowledge):
                codes.append("entered")
        except RecordsError as exc:
            codes.append(exc.code)

    with _promote_lock(knowledge):
        thread = threading.Thread(target=contend)
        thread.start()
        thread.join()
    assert codes == ["promote_locked"]
    with _promote_lock(knowledge):
        pass


@pytest.mark.parametrize("contents", ["", "not-a-pid", "-1", "0"])
def test_unknown_legacy_owner_is_not_reclaimed(store, repo, race, contents):
    from akms_records import RecordsError
    from akms_records.bridge import promote

    ids, path, _ = race
    lock = local_knowledge_dir(repo) / "records/.index/promote.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(contents)
    before = path.read_bytes()
    with pytest.raises(RecordsError) as exc:
        promote(store, ids[0], repo=repo, review="approved", actor="t")
    assert exc.value.code == "promote_locked"
    assert lock.read_text() == contents
    assert path.read_bytes() == before
    assert store.get(ids[0]).promoted_to is None


def test_guard_inode_persists_across_success_and_refusal(store, repo, race):
    from akms_records import RecordsError
    from akms_records.bridge import _promote_lock, promote

    ids, _, _ = race
    knowledge = local_knowledge_dir(repo)
    with _promote_lock(knowledge):
        guard = knowledge / "records/.index/promote.guard"
        inode = (guard.stat().st_dev, guard.stat().st_ino)
        with pytest.raises(RecordsError) as exc:
            promote(store, ids[0], repo=repo, review="approved", actor="t")
        assert exc.value.code == "promote_locked"
    for rid in ids:
        promote(store, rid, repo=repo, review="approved", actor="t")
        assert (guard.stat().st_dev, guard.stat().st_ino) == inode
