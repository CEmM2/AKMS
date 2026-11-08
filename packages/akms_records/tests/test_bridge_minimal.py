"""The bridge and its neighbours when ``akms`` is not installed."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from akms_records.schemas import load_template

BLOCKER = """
import sys
class Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in ("akms", "akms_failure_memory", "frontmatter"):
            raise ModuleNotFoundError(f"No module named {name!r}", name=name)
        return None
sys.meta_path.insert(0, Blocker())
from akms_records.cli import main
raise SystemExit(main(sys.argv[1:]))
"""


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", BLOCKER, *args], capture_output=True, text=True
    )


def test_promote_without_akms_names_the_extra(repo, make_store):
    store = make_store()
    store.register_schema(load_template("decision"), actor="t")
    rid = store.create(
        {
            "schema_ref": "decision/v1",
            "payload": {"decision": "Keep it", "rationale": "because"},
            "review_state": "user_confirmed",
        },
        actor="t",
    ).record_id
    store.close()
    base = ("--scope", "project:example", "--repo", str(repo))
    done = run_cli("promote", rid, *base, "--review", "approved")
    assert done.returncode == 2
    assert "error[akms_unavailable]" in done.stderr
    assert "akms-records[akms]" in done.stderr
    assert not (repo / ".knowledge" / "local-nodes").exists()
    done = run_cli("--json-errors", "promote", rid, *base, "--review", "approved")
    assert json.loads(done.stdout)["error"]["code"] == "akms_unavailable"
    show = run_cli("show", rid, *base)
    assert show.returncode == 0
    assert "promoted_to" not in json.loads(show.stdout)["state"]


def test_the_rest_of_the_cli_runs_without_akms(repo, make_store, tmp_path):
    source = tmp_path / "fm"
    source.mkdir()
    lesson = {
        "id": "L001",
        "date_found": "2026-08-01",
        "date_found_precision": "exact",
        "date_fixed": "2026-08-02",
        "date_fixed_precision": "exact",
        "location": {
            "area": "a",
            "package": "p",
            "module": "m",
            "file": "f.py",
            "symbol": "",
            "line_hint": "",
        },
        "found_by": {"type": "t", "trigger": "t"},
        "symptom": "It failed.",
        "root_cause": "c",
        "fix": "f",
        "prevention": "p",
        "references": {"commit": "", "issue": "", "pr": "", "plan": ""},
        "related": [],
    }
    (source / "lessons.json").write_text(
        json.dumps({"schema_version": 1, "_field_spec": {}, "lessons": [lesson]}),
        encoding="utf-8",
    )
    config = source / "project.toml"
    config.write_text(
        'schema_version = "failure-memory-project/v1"\nrepository_id = "demo"\n'
        '[paths]\nregistry = "lessons.json"\n'
        '[validation]\nregistry_schema_version = 1\nid_pattern = "^L[0-9]+$"\n',
        encoding="utf-8",
    )
    base = ("--scope", "project:example", "--repo", str(repo))
    done = run_cli(
        "import",
        *base,
        "--from-failure-memory",
        str(config),
        "--failure-memory-repo",
        str(source),
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["created"][0]["lesson"] == "L001"
    wake = run_cli(
        "wake",
        "--agent",
        "scout",
        "--task",
        "failed",
        "--budget-tokens",
        "500",
        "--scope",
        "project:example",
        "--repo",
        str(repo),
    )
    assert wake.returncode == 0, wake.stderr
    assert json.loads(wake.stdout)["report"]["excluded"]["imported"]["count"] == 1


def test_models_module_is_unchanged():
    """The frozen v2 models stay as they are; the bridge only uses them."""
    import hashlib

    models = (
        Path(__file__).resolve().parents[2]
        / "akms"
        / "src"
        / "akms"
        / "schema"
        / "models.py"
    )
    text = models.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert (
        hashlib.sha256(text.encode("utf-8")).hexdigest()
        == "f39766b86d1bfa6419317f6e66c3c4684d744c8509913a48a9425a63d0b3ae21"
    )
