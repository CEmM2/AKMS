"""Git merges of project records, CRLF checkouts, erasure, and doctor."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from akms_records import RecordStore, ReplayError, Scope
from akms_records.schemas import load_template

SECRET = "zqx-private-7f3a9c"


def open_store(repo: Path) -> RecordStore:
    return RecordStore.open(Scope("project", "example"), repo=repo)


@pytest.fixture
def project(repo, git, doc):
    git(repo, "init", "-q")
    store = open_store(repo)
    store.register_schema(load_template("decision"), actor="t")
    base = [store.create(doc(f"base {i}"), actor="t").record_id for i in range(4)]
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    return store, base


def commit(git, repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def test_disjoint_records_merge_cleanly_in_both_orders(project, repo, git, doc):
    store, base = project
    for branch, amended in (("a", base[0]), ("b", base[1])):
        git(repo, "checkout", "-q", "-b", branch, "main")
        st = open_store(repo)
        for i in range(3):
            st.create(doc(f"{branch} {i}"), actor=branch)
        st.amend(
            amended, {"summary": f"by {branch}"}, expected_revision=1, actor=branch
        )
        commit(git, repo, branch)
    trees = []
    for name, order in (("m1", ("a", "b")), ("m2", ("b", "a"))):
        git(repo, "checkout", "-q", "-b", name, "main")
        for branch in order:
            assert (
                git(repo, "merge", "--no-edit", "-q", branch, check=False).returncode
                == 0
            )
        st = open_store(repo)
        records = list(st.iter_records())
        assert len(records) == 10
        assert not [r for r in records if isinstance(r, ReplayError)]
        assert st.get(base[0]).revision == 2 and st.get(base[1]).revision == 2
        assert st.doctor()["status"] == "ok"
        trees.append(git(repo, "rev-parse", "HEAD^{tree}").stdout.strip())
    assert trees[0] == trees[1]


def test_same_revision_on_two_branches_conflicts_and_is_detected(project, repo, git):
    store, base = project
    target = base[2]
    for branch in ("c", "d"):
        git(repo, "checkout", "-q", "-b", branch, "main")
        open_store(repo).amend(
            target, {"summary": f"by {branch}"}, expected_revision=1, actor=branch
        )
        commit(git, repo, branch)
    git(repo, "checkout", "-q", "-b", "m", "main")
    assert git(repo, "merge", "--no-edit", "-q", "c", check=False).returncode == 0
    assert git(repo, "merge", "--no-edit", "-q", "d", check=False).returncode != 0
    st = open_store(repo)
    with pytest.raises(ReplayError) as caught:
        st.get(target)
    assert caught.value.replay_code == "conflict"
    report = st.doctor()
    assert report["conflicts"] == [target]
    assert report["replay_errors"][target]["code"] == "conflict"
    assert report["status"] == "error"
    # The other records still replay.
    assert all(st.get(rid).revision == 1 for rid in base if rid != target)


def test_autocrlf_checkout_keeps_event_bytes(project, repo, git, git_env, tmp_path):
    store, base = project
    clone = tmp_path / "clone"
    result = git(
        tmp_path, "-c", "core.autocrlf=true", "clone", "-q", str(repo), str(clone)
    )
    assert result.returncode == 0
    cloned = open_store(clone)
    sample = cloned.record_dir(base[0]) / "000001.json"
    assert b"\r\n" not in sample.read_bytes()
    assert all(cloned.get(rid).revision == 1 for rid in base)
    assert cloned.doctor(fix=False)["noncanonical"] == []


def test_erasure_removes_files_and_logs_no_content(store, doc):
    keep = store.create(doc("keep"), actor="t").record_id
    rid = store.create(doc(SECRET, summary=f"has {SECRET}"), actor="t").record_id
    store.amend(
        rid,
        {"payload": {"decision": SECRET, "rationale": SECRET}},
        expected_revision=1,
        actor="t",
    )
    report = store.erase(rid, reason="privacy request", actor="owner")
    assert report["files_removed"] == 2
    assert any("git history" in item for item in report["not_reached"])
    assert not store.record_dir(rid).exists()
    log = (store.root / "_erasures.jsonl").read_text(encoding="utf-8")
    assert SECRET not in log
    assert set(json.loads(log.splitlines()[-1])) == {
        "record_id",
        "scope",
        "at",
        "actor",
        "reason",
    }
    for path in store.root.rglob("*"):
        if path.is_file():
            assert SECRET.encode() not in path.read_bytes(), path
    assert [r.record_id for r in store.iter_records()] == [keep]
    assert store.doctor()["status"] == "ok"


def test_doctor_reapplies_an_erasure_a_merge_brought_back(project, repo, git):
    store, base = project
    target = base[3]
    git(repo, "checkout", "-q", "-b", "late", "main")
    open_store(repo).amend(
        target, {"summary": f"late {SECRET}"}, expected_revision=1, actor="late"
    )
    commit(git, repo, "late amend")
    git(repo, "checkout", "-q", "main")
    open_store(repo).erase(target, reason="privacy", actor="owner")
    commit(git, repo, "erase")
    assert git(repo, "merge", "--no-edit", "-q", "late", check=False).returncode == 0
    st = open_store(repo)
    revived = st.record_dir(target) / "000002.json"
    assert SECRET.encode() in revived.read_bytes()
    check = st.doctor(fix=False)
    assert check["erased_but_present"] == [target]
    assert check["status"] == "drift"
    fixed = st.doctor()
    assert fixed["erasures_reapplied"] == [target]
    assert not st.record_dir(target).exists()
    assert st.doctor(fix=False)["status"] == "ok"


def test_erasure_logs_from_two_branches_merge_by_union(project, repo, git):
    store, base = project
    for branch, rid in (("e1", base[0]), ("e2", base[1])):
        git(repo, "checkout", "-q", "-b", branch, "main")
        open_store(repo).erase(rid, reason=f"by {branch}", actor=branch)
        commit(git, repo, branch)
    git(repo, "checkout", "-q", "-b", "m", "main")
    assert git(repo, "merge", "--no-edit", "-q", "e1", check=False).returncode == 0
    assert git(repo, "merge", "--no-edit", "-q", "e2", check=False).returncode == 0
    entries, bad = open_store(repo).erasure_entries()
    assert sorted(e["record_id"] for e in entries) == sorted(base[:2]) and not bad


def test_doctor_cleans_temp_files_and_empty_directories(store, doc):
    rid = store.create(doc(), actor="t").record_id
    directory = store.record_dir(rid)
    dead = directory / ".000002.json.999999.0badc0de.tmp"
    dead.write_bytes(b"partial")
    live = directory / f".000002.json.{os.getpid()}.0badc0df.tmp"
    live.write_bytes(b"partial")
    empty = store.root / "2026-11" / "rec-20261103-zzzzzzzz"
    empty.mkdir()
    old = time.time() - 3600
    os.utime(empty, (old, old))
    check = store.doctor(fix=False)
    assert check["status"] == "drift"
    assert len(check["tmp_files"]) == 2 and check["empty_dirs"]
    fixed = store.doctor()
    assert fixed["tmp_removed"] == [
        f"2026-11/{rid}/{dead.name}"
    ]  # the live writer's stays
    assert live.exists() and not dead.exists() and not empty.exists()
    assert store.doctor(force_tmp=True)["tmp_removed"] == [f"2026-11/{rid}/{live.name}"]
    assert store.doctor(fix=False)["status"] == "ok"


def test_doctor_reports_strays_without_touching_them(store, doc):
    rid = store.create(doc(), actor="t").record_id
    stray = store.record_dir(rid) / "000001.json.orig"
    stray.write_text("x", encoding="utf-8")
    report = store.doctor()
    assert report["stray_files"] == [f"2026-11/{rid}/000001.json.orig"]
    assert stray.exists()


def test_broken_record_needs_force_to_erase_when_scope_is_unknown(store, doc):
    rid = store.create(doc(), actor="t").record_id
    (store.record_dir(rid) / "000001.json").write_text("{broken", encoding="utf-8")
    from akms_records import RecordsError

    with pytest.raises(RecordsError) as caught:
        store.erase(rid, reason="cleanup", actor="t")
    assert caught.value.code == "scope_unknown"
    store.erase(rid, reason="cleanup", actor="t", force=True)
    assert not store.record_dir(rid).exists()
