"""The batch picker runs from an installed package, without an AKMS checkout.

Covers path resolution (flags over environment over defaults), start-up with
missing inputs, the zsum hint, and the plan's free-form PDF folder field.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from akms_nodes_gen.batch_picker.config import ZSUM_URL, Paths
from akms_nodes_gen.batch_picker.plan_parser import parse_plan
from akms_nodes_gen.batch_picker.server import create_app
from akms_nodes_gen.batch_picker.status import ZSUM_HINT

PICKER_ENV = (
    "AKMS_REPO_ROOT",
    "AKMS_PLAN_MD",
    "AKMS_BBT_JSON",
    "AKMS_ZOTSUMS_ROOT",
    "AKMS_PICKER_WORKSPACE",
    "AKMS_BATCH_STATE",
    "AKMS_SAVED_QUERIES",
    "AKMS_NLM_INPUTS",
    "AKMS_SOURCES_NEW",
)

PLAN = """# Round 1: Kinematics
**Theme:** Finite strain

## R1_B1 — Deformation Measures (1 nodes)
**PDF folder:** `pdfs/R1_B1_deformation/`
**Sources:** Belytschko Ch. 3

| # | Node ID | Title | Key Concepts | Size |
|---|---------|-------|--------------|------|
| 1 | `deformation-gradient` | Deformation gradient | F | small |
"""

EXPORT = {
    "items": [
        {
            "itemID": 1,
            "citationKey": "smith2020",
            "title": "Finite strain kinematics",
            "date": "2020",
            "itemType": "journalArticle",
            "creators": [{"lastName": "Smith", "firstName": "A"}],
        }
    ],
    "collections": {"C1": {"name": "Mechanics", "items": [1], "collections": []}},
}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for name in PICKER_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.chdir(tmp_path)


def _write_inputs(root: Path) -> tuple[Path, Path]:
    plan = root / "plans" / "generation_plan.md"
    plan.parent.mkdir(parents=True)
    plan.write_text(PLAN, encoding="utf-8")
    export = root / "zotero" / "library.json"
    export.parent.mkdir(parents=True)
    export.write_text(json.dumps(EXPORT), encoding="utf-8")
    return plan, export


def test_defaults_need_no_checkout(tmp_path):
    paths = Paths.resolve()
    assert paths.plan_md == tmp_path / "generation_plan.md"
    assert paths.workspace == tmp_path
    assert paths.state_file == tmp_path / "batch_assignments.json"
    assert "Sources_Evals" not in str(paths.state_file)
    assert paths.bbt_json == tmp_path / "home" / "ZotSums" / "zsumbib.json"


def test_plan_flag_moves_the_workspace_with_it(tmp_path):
    plan, _ = _write_inputs(tmp_path)
    paths = Paths.resolve(plan=plan)
    assert paths.plan_md == plan
    assert paths.workspace == plan.parent
    assert paths.queries_file == plan.parent / "saved_queries.json"
    assert paths.sources_dir == plan.parent / "pdfs"


def test_flags_beat_environment_and_workspace_is_independent(tmp_path, monkeypatch):
    plan, export = _write_inputs(tmp_path)
    monkeypatch.setenv("AKMS_PLAN_MD", str(tmp_path / "elsewhere.md"))
    ws = tmp_path / "ws"
    paths = Paths.resolve(plan=plan, bibtex_json=export, workspace=ws)
    assert paths.plan_md == plan
    assert paths.bbt_json == export
    assert paths.state_file == ws / "batch_assignments.json"


def test_environment_is_used_without_flags(tmp_path, monkeypatch):
    plan, _ = _write_inputs(tmp_path)
    monkeypatch.setenv("AKMS_PLAN_MD", str(plan))
    assert Paths.resolve().plan_md == plan


def test_repo_root_keeps_the_monorepo_layout(tmp_path, monkeypatch):
    monkeypatch.setenv("AKMS_REPO_ROOT", str(tmp_path))
    paths = Paths.resolve()
    assert paths.plan_md == (
        tmp_path / "Packages" / "AKMS_nodes_gen" / "generation_plan.md"
    )
    assert paths.state_file == (
        tmp_path / "Sources_Evals" / "NLM" / "batch_assignments.json"
    )


def test_starts_with_nothing_and_explains_what_is_missing(tmp_path):
    app = create_app(Paths.resolve())
    client = TestClient(app)
    notices = client.get("/api/status").json()["notices"]
    levels = {n["level"] for n in notices}
    text = " ".join(n["message"] for n in notices)
    assert "error" in levels
    assert "--plan" in text
    assert "--bibtex-json" in text
    assert client.get("/api/batches").json() == []
    assert client.get("/").status_code == 200


def test_zsum_absence_is_a_hint_not_a_failure(tmp_path):
    plan, export = _write_inputs(tmp_path)
    app = create_app(Paths.resolve(plan=plan, bibtex_json=export))
    client = TestClient(app)
    notices = client.get("/api/status").json()["notices"]
    assert [n["level"] for n in notices] == ["info"]
    assert ZSUM_HINT in notices[0]["message"]
    assert notices[0]["link"] == ZSUM_URL
    assert [b["id"] for b in client.get("/api/batches").json()] == ["R1_B1"]
    papers = client.get("/api/papers").json()
    assert any(p["citekey"] == "smith2020" for p in papers["results"])


def test_unreadable_export_is_reported_not_raised(tmp_path):
    plan, export = _write_inputs(tmp_path)
    export.write_text("{not json", encoding="utf-8")
    app = create_app(Paths.resolve(plan=plan, bibtex_json=export))
    notices = TestClient(app).get("/api/status").json()["notices"]
    assert any(
        n["level"] == "error" and "Could not read the Zotero export" in n["message"]
        for n in notices
    )


@pytest.mark.parametrize(
    ("field", "slug"),
    [
        ("`pdfs/R1_B1_deformation/`", "R1_B1_deformation"),
        ("AKMS_Sources/new/R7_B2_energy/", "R7_B2_energy"),
        ("/abs/path/R3_B1_x", "R3_B1_x"),
    ],
)
def test_pdf_folder_accepts_any_path(tmp_path, field, slug):
    plan = tmp_path / "plan.md"
    plan.write_text(PLAN.replace("`pdfs/R1_B1_deformation/`", field), encoding="utf-8")
    assert parse_plan(plan)[0].pdf_slug == slug
