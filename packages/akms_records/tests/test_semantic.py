"""``recall --semantic``: off by default, private to the store, and erasable.

Most tests run a stand-in for qmd, so they need neither the tool nor its model. The
last ones run the real tool where it is installed.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

from akms_records import RecordStore, Scope, recall_scopes, semantic
from akms_records.cli import main
from akms_records.errors import RecordsError, ScopeViolation
from akms_records.schemas import load_template
from akms_records.semantic import MODEL_ENV, drop_index

FAKE_QMD = Path(__file__).parent / "workers" / "fake_qmd.py"
SECRET = "zebrafish-erasure-marker"
SENSITIVE = "okapi-sensitive-marker"


@pytest.fixture
def qmd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Use the stand-in, and return the file that logs its calls."""
    log = tmp_path / "qmd.log"
    model = tmp_path / "model.gguf"
    model.write_bytes(b"not really a model")
    monkeypatch.setattr(
        semantic, "_qmd_command", lambda: [sys.executable, str(FAKE_QMD)]
    )
    monkeypatch.setenv(MODEL_ENV, str(model))
    monkeypatch.setenv("FAKE_QMD_LOG", str(log))
    return log


def calls(log: Path) -> list[dict[str, Any]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def commands(log: Path) -> list[str]:
    return [call["argv"][0] for call in calls(log)]


def index_bytes(store: RecordStore) -> bytes:
    """Every byte the store's index folder holds."""
    return b"".join(
        path.read_bytes()
        for path in (store.root / ".index").rglob("*")
        if path.is_file()
    )


def semantic_folder(store: RecordStore) -> Path:
    return store.root / ".index" / "semantic"


def test_a_plain_recall_never_runs_qmd(store, doc, monkeypatch):
    def refuse() -> list[str]:
        raise AssertionError("qmd was run")

    monkeypatch.setattr(semantic, "_qmd_command", refuse)
    store.create(doc("the lock file"), actor="t")
    result = store.recall("lock")
    assert result.semantic is False
    assert [hit.found_by for hit in result.hits] == [None]
    assert not semantic_folder(store).exists()


def test_missing_qmd_is_a_typed_error_that_names_it(store, doc, monkeypatch):
    monkeypatch.setattr(semantic.shutil, "which", lambda name: None)
    store.create(doc("the lock file"), actor="t")
    with pytest.raises(RecordsError) as caught:
        store.recall("lock", semantic=True)
    assert caught.value.code == "qmd_missing"
    assert "qmd" in str(caught.value)


def test_a_missing_model_stops_before_qmd_could_download_it(
    store, doc, qmd, tmp_path, monkeypatch
):
    monkeypatch.setenv(MODEL_ENV, str(tmp_path / "absent.gguf"))
    store.create(doc("the lock file"), actor="t")
    with pytest.raises(RecordsError) as caught:
        store.recall("lock", semantic=True)
    assert caught.value.code == "semantic_model_missing"
    assert calls(qmd) == []


@pytest.mark.parametrize(
    "options",
    [{"semantic": True}, {"embed_sensitive": True}],
    ids=["semantic-without-query", "embed-without-semantic"],
)
def test_flags_that_make_no_sense_are_refused(store, options):
    with pytest.raises(RecordsError) as caught:
        store.recall(None, **options)
    assert caught.value.code == "usage"


def test_a_search_uses_no_llm_and_stays_inside_the_store(store, doc, qmd, tmp_path):
    store.create(doc("the lock file"), actor="t")
    store.recall("lock", semantic=True)
    folder = str(semantic_folder(store))
    seen = calls(qmd)
    assert all(call["argv"][0] != "vsearch" for call in seen)
    search = next(call for call in seen if call["argv"][0] == "query")
    assert search["argv"][1] == "vec: lock"
    assert "--no-rerank" in search["argv"]
    for call in seen:
        env = call["env"]
        for name in (
            "INDEX_PATH",
            "QMD_CONFIG_DIR",
            "XDG_CONFIG_HOME",
            "XDG_CACHE_HOME",
        ):
            assert env[name].startswith(folder), name
        assert env["QMD_EMBED_MODEL"] == str(tmp_path / "model.gguf")
        assert not Path(env["QMD_GENERATE_MODEL"]).exists()
        assert not Path(env["QMD_RERANK_MODEL"]).exists()


def test_a_query_is_made_fit_for_qmds_grammar(store, doc, qmd):
    store.create(doc("the lock file"), actor="t")
    store.recall('non-empty "lock\nfile', semantic=True)
    search = next(call for call in calls(qmd) if call["argv"][0] == "query")
    assert search["argv"][1] == "vec: non empty lock file"


def test_vector_hits_join_text_hits_and_say_where_they_came_from(store, doc, qmd):
    both = store.create(doc("lock"), actor="t").record_id
    vector = store.create(doc("chromium viewport"), actor="t").record_id
    result = store.recall("lock", semantic=True)
    assert result.semantic is True
    assert result.match == "all"
    found = {hit.record_id: hit for hit in result.hits}
    assert found[both].found_by == "both"
    assert found[both].bm25 is not None
    assert found[vector].found_by == "vector"
    assert found[vector].bm25 is None
    assert found[vector].snippet
    assert result.hits[0].record_id == both
    assert result.to_json()["semantic"] is True
    assert result.to_json()["results"][0]["found_by"] == "both"
    assert "found by: both" in result.render_text()


def test_the_merged_order_is_repeatable(store, doc, qmd):
    for number in range(8):
        store.create(doc(f"entry {number} about locks"), actor="t")
    orders = {
        tuple(hit.record_id for hit in store.recall("locks", semantic=True).hits)
        for _ in range(2)
    }
    assert len(orders) == 1


def test_vector_hits_pass_recalls_filters(store, doc, qmd):
    kept = store.create(doc("lock kept"), actor="t").record_id
    gone = store.create(doc("lock retracted"), actor="t").record_id
    store.retract(gone, expected_revision=1, actor="t", reason="wrong")
    ids = [hit.record_id for hit in store.recall("lock", semantic=True).hits]
    assert ids == [kept]
    assert store.recall("lock", semantic=True, schema="nope").hits == ()


def test_another_agents_scope_is_refused_before_qmd_runs(repo, qmd):
    with pytest.raises(ScopeViolation):
        recall_scopes(
            ["agent:someone"], query="lock", agent="me", repo=repo, semantic=True
        )
    assert calls(qmd) == []


@pytest.fixture
def shared(tmp_path: Path) -> RecordStore:
    """A scope with a store root of its own."""
    other = RecordStore.open(Scope("shared", "team"), home=tmp_path / "home")
    other.register_schema(load_template("decision"), actor="tester")
    return other


def test_each_root_has_its_own_index_and_each_hit_names_its_scope(
    store, shared, doc, repo, tmp_path, qmd
):
    first = store.create(doc("lock one"), actor="t").record_id
    second = shared.create(doc("lock two"), actor="t").record_id
    result = recall_scopes(
        ["project:example", "shared:team"],
        query="lock",
        repo=repo,
        home=tmp_path / "home",
        semantic=True,
    )
    scopes = {hit.record_id: hit.scope for hit in result.hits}
    assert scopes == {first: "project:example", second: "shared:team"}
    assert result.semantic is True
    assert b"lock two" not in index_bytes(store)
    assert b"lock one" not in index_bytes(shared)


def test_scopes_that_share_a_root_share_an_index_but_not_results(
    store, make_store, doc, qmd
):
    other = make_store("project:other")
    other.register_schema(load_template("decision"), actor="tester")
    mine = store.create(doc("lock one"), actor="t").record_id
    theirs = other.create(doc("lock two"), actor="t").record_id
    assert [hit.record_id for hit in store.recall("lock", semantic=True).hits] == [mine]
    assert [hit.record_id for hit in other.recall("lock", semantic=True).hits] == [
        theirs
    ]
    assert commands(qmd).count("collection") == 1  # asking in turn does not rebuild


def test_the_match_mode_comes_from_the_text_search_alone(
    store, shared, doc, repo, tmp_path, qmd
):
    """Vector hits are always there, so they must not stop the any-word fallback."""
    store.create(doc("lock file"), actor="t")
    shared.create(doc("viewport"), actor="t")
    result = recall_scopes(
        ["project:example", "shared:team"],
        query="lock mismatch",
        repo=repo,
        home=tmp_path / "home",
        semantic=True,
    )
    assert result.match == "any"
    assert any(hit.found_by == "both" for hit in result.hits)


def test_sensitive_records_are_not_embedded_unless_allowed(store, doc, qmd):
    store.create(doc("plain"), actor="t")
    store.create(doc(SENSITIVE, sensitivity="sensitive"), actor="t")
    assert store.recall("plain", semantic=True).hits
    folder = semantic_folder(store)

    def held() -> bytes:
        return b"".join(p.read_bytes() for p in folder.rglob("*") if p.is_file())

    assert SENSITIVE.encode() not in held()
    # include_sensitive reads them, but it is not permission to embed them.
    store.recall("plain", semantic=True, include_sensitive=True)
    assert SENSITIVE.encode() not in held()

    store.recall("plain", semantic=True, embed_sensitive=True)
    assert SENSITIVE.encode() in held()
    hidden = store.recall(SENSITIVE, semantic=True, embed_sensitive=True)
    assert all(SENSITIVE not in hit.summary for hit in hidden.hits)
    shown = store.recall(
        SENSITIVE, semantic=True, embed_sensitive=True, include_sensitive=True
    )
    assert any(SENSITIVE in hit.summary for hit in shown.hits)

    # The first call without the flag takes them out again, bytes included.
    store.recall("plain", semantic=True)
    assert SENSITIVE.encode() not in held()


def test_a_record_that_becomes_sensitive_leaves_the_index(store, doc, qmd):
    rid = store.create(doc(SENSITIVE), actor="t").record_id
    store.create(doc("plain"), actor="t")
    store.recall("plain", semantic=True)
    assert SENSITIVE.encode() in (semantic_folder(store) / "qmd.sqlite").read_bytes()
    store.amend(rid, {"sensitivity": "sensitive"}, expected_revision=1, actor="t")
    store.recall("plain", semantic=True)
    assert (
        SENSITIVE.encode() not in (semantic_folder(store) / "qmd.sqlite").read_bytes()
    )


def test_erasing_removes_the_text_from_every_index_byte(store, doc, qmd):
    store.create(doc("keep the lock"), actor="t")
    rid = store.create(doc(SECRET, summary=f"lock {SECRET}"), actor="t").record_id
    store.recall("lock", semantic=True)
    assert SECRET.encode() in (semantic_folder(store) / "qmd.sqlite").read_bytes()
    report = store.erase(rid, reason="privacy request", actor="owner")
    assert report["index"]["semantic"] == "deleted"
    assert not semantic_folder(store).exists()
    assert SECRET.encode() not in index_bytes(store)

    # The next search builds it again, without the record.
    ids = [hit.record_id for hit in store.recall("lock", semantic=True).hits]
    assert rid not in ids and len(ids) == 1
    assert SECRET.encode() not in index_bytes(store)


def test_erasing_in_a_store_without_the_index_changes_nothing(store, doc):
    rid = store.create(doc("plain"), actor="t").record_id
    report = store.erase(rid, reason="privacy request", actor="owner")
    assert "semantic" not in report["index"]
    assert not semantic_folder(store).exists()


def test_an_index_erasure_could_not_reach_is_reported_and_cleaned_later(
    store, doc, qmd
):
    store.create(doc("keep the lock"), actor="t")
    rid = store.create(doc(SECRET), actor="t").record_id
    store.recall("lock", semantic=True)
    lock = store.root / ".index" / "semantic.lock"
    lock.write_text(str(os.getpid()), encoding="ascii")  # a live holder

    real = semantic.drop_index
    monkey = pytest.MonkeyPatch()
    monkey.setattr("akms_records.store.drop_index", lambda root: real(root, wait=0.0))
    try:
        report = store.erase(rid, reason="privacy request", actor="owner")
    finally:
        monkey.undo()
    assert report["index"]["semantic"] == "not_reached"
    assert any("semantic index" in item for item in report["not_reached"])
    assert SECRET.encode() in (semantic_folder(store) / "qmd.sqlite").read_bytes()

    lock.unlink()
    fixed = store.doctor(fix=True)
    assert fixed["repairs"]["semantic_index_deleted"]
    assert SECRET.encode() not in index_bytes(store)


def test_the_next_search_also_cleans_a_leftover_index(store, doc, qmd):
    store.create(doc("keep the lock"), actor="t")
    rid = store.create(doc(SECRET), actor="t").record_id
    store.recall("lock", semantic=True)
    held = semantic_folder(store).with_name("kept")
    shutil.copytree(semantic_folder(store), held)
    store.erase(rid, reason="privacy request", actor="owner")
    held.rename(semantic_folder(store))  # as if another process had put it back
    store.recall("lock", semantic=True)
    assert SECRET.encode() not in index_bytes(store)


def test_a_lock_left_by_a_dead_process_is_taken_over(store, doc, qmd):
    store.create(doc("lock"), actor="t")
    store.ensure_root()
    (store.root / ".index").mkdir(exist_ok=True)
    (store.root / ".index" / "semantic.lock").write_text("999999999", encoding="ascii")
    assert store.recall("lock", semantic=True).hits
    assert not (store.root / ".index" / "semantic.lock").exists()


def test_drop_index_without_an_index_folder(tmp_path):
    assert drop_index(tmp_path) == "absent"
    assert not (tmp_path / ".index").exists()


def test_updates_are_incremental_until_something_leaves(store, doc, qmd):
    rid = store.create(doc("lock one"), actor="t").record_id
    store.recall("lock", semantic=True)
    assert commands(qmd) == ["collection", "embed", "query"]

    qmd.unlink()
    store.recall("lock", semantic=True)
    assert commands(qmd) == ["query"]

    qmd.unlink()
    store.create(doc("lock two"), actor="t")
    store.recall("lock", semantic=True)
    assert commands(qmd) == ["update", "embed", "query"]

    qmd.unlink()
    store.amend(rid, {"summary": "lock one changed"}, expected_revision=1, actor="t")
    store.recall("lock", semantic=True)
    assert commands(qmd) == ["update", "embed", "query"]

    qmd.unlink()
    store.erase(rid, reason="privacy request", actor="owner")
    store.recall("lock", semantic=True)
    assert commands(qmd) == ["collection", "embed", "query"]


def test_a_different_model_means_a_rebuild(store, doc, qmd, tmp_path, monkeypatch):
    store.create(doc("lock"), actor="t")
    store.recall("lock", semantic=True)
    other = tmp_path / "other.gguf"
    other.write_bytes(b"another model")
    monkeypatch.setenv(MODEL_ENV, str(other))
    qmd.unlink()
    store.recall("lock", semantic=True)
    assert commands(qmd) == ["collection", "embed", "query"]


def test_an_interrupted_build_is_done_again(store, doc, qmd, monkeypatch):
    store.create(doc("lock"), actor="t")
    monkeypatch.setenv("FAKE_QMD_FAIL", "embed")
    with pytest.raises(RecordsError) as caught:
        store.recall("lock", semantic=True)
    assert caught.value.code == "semantic_failed"
    assert "simulated failure" in str(caught.value)
    monkeypatch.delenv("FAKE_QMD_FAIL")
    assert store.recall("lock", semantic=True).hits[0].found_by == "both"


def test_output_that_is_not_json_is_a_typed_error(store, doc, qmd, monkeypatch):
    store.create(doc("lock"), actor="t")
    monkeypatch.setenv("FAKE_QMD_NOT_JSON", "1")
    with pytest.raises(RecordsError) as caught:
        store.recall("lock", semantic=True)
    assert caught.value.code == "semantic_failed"


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_the_index_is_owner_only(store, doc, qmd):
    store.create(doc("lock"), actor="t")
    store.recall("lock", semantic=True)
    folder = semantic_folder(store)
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    for path in folder.iterdir():
        if path.is_file():
            assert stat.S_IMODE(path.stat().st_mode) == 0o600, path
    for path in (folder / "docs").iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600, path


def test_the_index_is_ignored_by_git(store, doc, qmd):
    store.create(doc("lock"), actor="t")
    store.recall("lock", semantic=True)
    assert ".index/" in (store.root / ".gitignore").read_text(encoding="utf-8")


def test_the_cli_flag(store, doc, repo, qmd, capsys):
    store.create(doc("lock"), actor="t")
    code = main(
        ["recall", "--scope", "project:example", "--repo", str(repo)]
        + ["--query", "lock", "--semantic", "--format", "json"]
    )
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["semantic"] is True
    assert out["results"][0]["found_by"] == "both"


# ---------------------------------------------------------------- the real tool
def _real_model() -> Path:
    return Path.home() / ".cache" / "qmd" / "models" / semantic.MODEL_FILE


real_qmd = pytest.mark.skipif(
    shutil.which("qmd") is None or not _real_model().is_file(),
    reason="needs the qmd tool and its embedding model",
)


@pytest.mark.slow
@real_qmd
def test_real_qmd_finds_by_meaning_and_erasure_clears_its_database(store, doc):
    global_files = [
        Path.home() / ".cache" / "qmd" / "index.sqlite",
        Path.home() / ".config" / "qmd" / "index.yml",
    ]
    before = [(p, p.stat().st_mtime_ns) for p in global_files if p.exists()]
    target = store.create(doc("Advisory locks stop two writers appending"), actor="t")
    store.create(doc("Chromium needs a fixed viewport"), actor="t")
    rid = store.create(doc(SECRET, summary=f"secret {SECRET}"), actor="t").record_id

    question = "how do we keep concurrent processes from corrupting the log"
    first = store.recall(question, semantic=True, limit=3)
    assert first.hits[0].record_id == target.record_id
    assert first.hits[0].found_by == "vector"
    again = store.recall(question, semantic=True, limit=3)
    assert [hit.record_id for hit in again.hits] == [
        hit.record_id for hit in first.hits
    ]
    assert SECRET.encode() in (semantic_folder(store) / "qmd.sqlite").read_bytes()

    store.erase(rid, reason="privacy request", actor="owner")
    assert SECRET.encode() not in index_bytes(store)
    assert rid not in [h.record_id for h in store.recall(question, semantic=True).hits]
    assert SECRET.encode() not in index_bytes(store)
    assert [(p, p.stat().st_mtime_ns) for p, _ in before] == before
