"""Re-freeze the consumer-contract pack (maintainers only).

    uv run python packages/akms_failure_memory/tests/refreeze_consumer_pack.py

Recomputes every value the pack pins, the same way test_consumer_contract.py
checks it, and rewrites the pack in place:

1. ``generated/`` -- recompiled from ``lessons.json``.
2. ``expected/*.json`` and ``recording/accepted-result.json`` -- the raw
   provider results, fingerprint verdicts and recording outcomes.
3. ``fixture-manifest.json`` -- the registry source digest and, through
   ``verify_pack.py --update``, every file digest and the pack digest.

It prints the new pack digest; set ``EXPECTED_PACK_SHA256`` in
test_consumer_contract.py to it, and give consumers the new value. A re-freeze
changes the contract every consumer pins, so review the diff of ``expected/``
before committing it. Everything runs in scratch directories with an empty
temporary vault; the real global vault is never touched.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location(
    "consumer_contract_suite", HERE / "test_consumer_contract.py"
)
assert _spec and _spec.loader
suite = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(suite)

from akms_failure_memory.compiler import run_compiler  # noqa: E402
from akms_failure_memory.config import load_project_config  # noqa: E402
from akms_failure_memory.provider import validate_fingerprint  # noqa: E402
from akms_failure_memory.record import add_lesson  # noqa: E402

PACK: Path = suite.PACK
RESULT_FILES = (
    "required.json",
    "coactivated.json",
    "advisory.json",
    "empty.json",
    "docs-routing.json",
)


def _read(relative: str) -> dict[str, Any]:
    return json.loads((PACK / relative).read_text(encoding="utf-8"))


def _write(relative: str, data: dict[str, Any]) -> None:
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    (PACK / relative).write_text(text, encoding="utf-8")


def _bootstrap_lock(repo: Path) -> None:
    load_project_config(repo / "project.toml").resolve(repo, "lock").parent.mkdir(
        parents=True, exist_ok=True
    )


def _regenerate_outputs(scratch: Path) -> str:
    repo, vault = suite._stage(scratch / "compile")
    _bootstrap_lock(repo)
    run_compiler(
        config_path=repo / "project.toml",
        repository_root=repo,
        global_vault=vault,
        mode="write",
    )
    check = run_compiler(
        config_path=repo / "project.toml",
        repository_root=repo,
        global_vault=vault,
        mode="check",
    )
    if check["status"] != "clean":
        raise SystemExit(f"recompiled pack is not clean: {check}")
    shutil.rmtree(PACK / "generated")
    shutil.copytree(repo / "generated", PACK / "generated")
    return check["source_sha256"]


def _published(
    scratch: Path, name: str, *, vault_subdir: str = "vault", **publish: Any
) -> tuple[Path, Path]:
    repo, vault = suite._stage(scratch / name, vault_subdir=vault_subdir)
    suite._publish_graph(repo, vault, **publish)
    return repo, vault


def _refreeze_results(scratch: Path) -> None:
    repo, _vault = _published(scratch, "results")
    for name in RESULT_FILES:
        data = _read(f"expected/{name}")
        for case in data["cases"]:
            result = suite._resolve(repo, Path(case["request"]).name)
            case["expect"]["result"] = suite._project(result)
        _write(f"expected/{name}", data)


def _refreeze_stale_fingerprint(scratch: Path) -> None:
    repo, _vault = _published(scratch, "stale")
    recorded = suite._resolve(repo, "exact-path.json")
    result_path = repo / recorded["artifacts"]["result"]
    data = _read("expected/errors.json")
    for case in data["cases"]:
        if case["case_id"] != "stale_fingerprint":
            continue
        for key, request in (
            ("current", "exact-path.json"),
            ("stale", "stale-baseline.json"),
        ):
            case["expect"][key] = validate_fingerprint(
                config_path=repo / "project.toml",
                repository_root=repo,
                request_source=repo / "requests" / request,
                result_path=result_path,
            )
    _write("expected/errors.json", data)


def _refreeze_recording(scratch: Path) -> None:
    repo, vault = suite._stage(scratch / "recording")
    data = _read("recording/accepted-result.json")
    data["expect"]["result"] = add_lesson(
        config_path=repo / "project.toml",
        repository_root=repo,
        global_vault=vault,
        request_path=repo / "recording/proposal.json",
    )
    check = run_compiler(
        config_path=repo / "project.toml",
        repository_root=repo,
        global_vault=vault,
        mode="check",
    )
    data["expect"]["recompile"] = {"status": check["status"], "counts": check["counts"]}
    _write("recording/accepted-result.json", data)


def _refreeze_staleness(scratch: Path) -> None:
    repo, _vault = _published(scratch, "baseline")
    baseline = suite._resolve(repo, "exact-path.json")
    recorded = (repo / baseline["artifacts"]["result"]).read_bytes()
    data = _read("expected/staleness.json")
    data["recorded_baseline"]["fingerprint"] = baseline["fingerprint"]

    verdicts: dict[str, dict[str, Any]] = {}
    repo, _vault = _published(
        scratch, "rebuilt", vault_subdir="a/deeper/differently-named/vault"
    )
    verdicts["rebuilt_is_current"] = suite._verdict(repo, recorded)

    repo, vault = suite._stage(scratch / "content")
    add_lesson(
        config_path=repo / "project.toml",
        repository_root=repo,
        global_vault=vault,
        request_path=repo / "recording/proposal.json",
    )
    suite._publish_graph(repo, vault)
    verdicts["content_change_is_stale"] = suite._verdict(repo, recorded)

    repo, _vault = _published(scratch, "noncanonical", canonical=False)
    verdicts["noncanonical_publication_is_stale"] = suite._verdict(repo, recorded)

    repo, _vault = _published(
        scratch, "regenerated", generated_at=suite.ALTERNATE_GENERATED_AT
    )
    verdicts["changed_generated_at_is_stale"] = suite._verdict(repo, recorded)

    for case in data["cases"]:
        verdict = verdicts[case["case_id"]]
        expect = case["expect"]
        expect["status"] = verdict["status"]
        expect["stale"] = verdict["stale"]
        expect["recorded_fingerprint"] = verdict["recorded_fingerprint"]
        if "current_fingerprint" in expect:
            expect["current_fingerprint"] = verdict["current_fingerprint"]
    _write("expected/staleness.json", data)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="consumer-pack-refreeze-") as tmp:
        scratch = Path(tmp)
        source_sha256 = _regenerate_outputs(scratch)
        _refreeze_results(scratch)
        _refreeze_stale_fingerprint(scratch)
        _refreeze_recording(scratch)
        _refreeze_staleness(scratch)

    manifest = _read("fixture-manifest.json")
    manifest["project"]["registry_source_sha256"] = source_sha256
    manifest["project"]["config_fingerprint"] = load_project_config(
        PACK / "project.toml"
    ).fingerprint
    (PACK / "fixture-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    # The verifier namespace is a dict, so `.update` would be dict.update.
    digest = suite._verifier()["update"](PACK)
    print(f"pack_sha256 = {digest}")
    print("Set EXPECTED_PACK_SHA256 in test_consumer_contract.py to this value.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
