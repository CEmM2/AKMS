"""Executable conformance suite for the shared consumer contract pack v1.

The pack under ``tests/fixtures/consumer_contract/v1`` is the single
behavioural seam that downstream consumer repositories build against. These
tests make the contract executable rather than documentary: the generated
artifacts are proven to be compiler output, and every pinned expectation is
proven against the real provider.

Every consumer repository MUST assert ``EXPECTED_PACK_SHA256`` before using any
file in the pack. Changing that constant is a deliberate re-freeze of the
contract and requires a full contract review before adoption.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

import akms
from akms.graph.build_graph import build_graph

from akms_failure_memory.compiler import run_compiler
from akms_failure_memory.config import load_project_config
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.provider import resolve_provider, validate_fingerprint
from akms_failure_memory.record import add_lesson
from akms_failure_memory.refresh import (
    _finalize_graph_payload,
    _timestamp,
    refresh_project,
)


# The pack's expected outputs pin provider fingerprints, and those move with
# akms_version (it feeds toolchain_sha256). Pack v1 was frozen under the akms
# version below; under any other version the pinned expectations cannot verify,
# so the suite skips rather than fail on a known toolchain mismatch. Owner
# decision 2026-08-18: the public tree defers the deliberate re-freeze; remove
# the mismatch by re-freezing the pack (new EXPECTED_PACK_SHA256) or running
# under the frozen toolchain.
PACK_FROZEN_AKMS_VERSION = "0.6.1"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        akms.__version__ != PACK_FROZEN_AKMS_VERSION,
        reason=(
            f"consumer-contract pack v1 is frozen under akms "
            f"{PACK_FROZEN_AKMS_VERSION}; provider fingerprints cannot verify "
            f"under akms {akms.__version__} (re-freeze deferred by owner "
            f"decision, 2026-08-18)"
        ),
    ),
]

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PACK = PACKAGE_ROOT / "tests/fixtures/consumer_contract/v1"
REPO_ROOT = PACKAGE_ROOT.parents[1]

# The digest every consumer must assert. Do not edit without a full contract
# review. Amendment 1 (docs routing + fingerprint
# portability) superseded 4d3e5e2a3c0aca8861f5420959b91c7d14be7ac5bbeb134b28620e97b2a8127c.
# Re-frozen when akms_public_api_sha256 was removed from the provider fingerprint
# inputs: that key appeared in eight expected results, and every pinned
# fingerprint moved with it. Deliberate re-freeze -- the pin stays literal so an
# accidental pack edit still fails loudly. Previous value:
# 8efa2a0135d0481f2b7281f0ba1dce436f2fcc190137d1070ead63c0741108f3
EXPECTED_PACK_SHA256 = "90ad2801481723e224e7215fffb3a7b1cd661e615bcbaa9c5a62565a40c94eb7"

# The pack's pinned deterministic graph timestamp. Canonical publication feeds
# this to the project-owned finalizer, which is what makes every fingerprint in
# expected/ reproducible across machines, scratch roots and vault mount paths.
CANONICAL_GENERATED_AT = "2026-08-17T00:00:00+00:00"
ALTERNATE_GENERATED_AT = "2026-08-18T00:00:00+00:00"

# The ONLY fields still reduced out of a pinned result, and only when the
# invocation wrote artifacts: absolute scratch-root paths. Nothing else is
# reduced -- raw fingerprints are pinned.
REDUCED_RESOLUTION = ("loadout_path", "manifest_path")


# ── pack helpers ──────────────────────────────────────────────────────────


def _load(relative: str) -> Any:
    return json.loads((PACK / relative).read_text(encoding="utf-8"))


def _manifest() -> dict[str, Any]:
    return _load("fixture-manifest.json")


def _case(expected_file: str, case_id: str) -> dict[str, Any]:
    for case in _load(f"expected/{expected_file}")["cases"]:
        if case["case_id"] == case_id:
            return case
    raise AssertionError(f"{expected_file} has no case {case_id!r}")


class _Verifier(dict):
    """Namespace holding verify_pack.py's functions.

    Executed rather than imported so that consuming the pack never writes a
    ``__pycache__`` into it -- the pack must stay byte-identical, including when
    it has been vendored read-only.
    """

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AttributeError(name) from exc


def _verifier() -> _Verifier:
    source = (PACK / "verify_pack.py").read_text(encoding="utf-8")
    namespace = _Verifier(
        __name__="consumer_contract_verify_pack", __file__=str(PACK / "verify_pack.py")
    )
    exec(compile(source, str(PACK / "verify_pack.py"), "exec"), namespace)  # noqa: S102
    return namespace


def _project(result: dict[str, Any]) -> dict[str, Any]:
    """Drop only the absolute scratch-root paths; keep every digest raw."""
    projected = {key: value for key, value in result.items() if key != "resolution"}
    projected["resolution"] = {
        key: value
        for key, value in result["resolution"].items()
        if key not in REDUCED_RESOLUTION
    }
    return projected


def _stage(destination: Path, *, vault_subdir: str = "vault") -> tuple[Path, Path]:
    """Copy the pack to a scratch root and create its empty global vault.

    The real global vault is never referenced: an empty temporary directory is
    passed explicitly, so nothing can read or write ``~/.claude/akms/nodes``.
    ``vault_subdir`` exists so a test can mount the (identically empty) vault at
    a deliberately different absolute path and prove that alone changes nothing.
    """
    repo = destination / "repo"
    shutil.copytree(PACK, repo)
    vault = destination / vault_subdir
    vault.mkdir(parents=True)
    return repo, vault


def _publish_graph(
    repo: Path,
    vault: Path,
    *,
    generated_at: str = CANONICAL_GENERATED_AT,
    canonical: bool = True,
) -> None:
    """Publish graph.json the way the pack's staging contract requires.

    Canonical publication is: build into a scratch file, pass the payload
    through the project-owned finalizer (which pins ``generated_at``, stamps the
    configured ``repo_id`` and canonicalizes the machine-specific vault mount
    path), then write those bytes. ``refresh_project(action="graph")`` is the
    production entry point that does exactly this; the pack performs the same
    publication directly because ``refresh_project`` also runs ``preflight``,
    which demands a pinned editable repo2md checkout that a fixture consumer
    will not have. ``test_pack_staging_matches_canonical_refresh_publication``
    proves the two produce byte-identical output.

    ``canonical=False`` publishes the RAW ``build_graph`` bytes, which is what a
    consumer that skips the finalizer would get. It exists only to prove that
    doing so produces permanent false staleness.
    """
    config = load_project_config(repo / "project.toml")
    output = config.resolve(repo, "graph")
    output.parent.mkdir(parents=True, exist_ok=True)
    scratch = output.parent / f".{output.name}.staging"
    build_graph(
        config.resolve(repo, "akms_repo_root"),
        global_vault=vault,
        output_path=scratch,
        strict=True,
    )
    if canonical:
        payload = _finalize_graph_payload(
            json.loads(scratch.read_text(encoding="utf-8")),
            config=config,
            generated_at=generated_at,
        )
    else:
        payload = scratch.read_bytes()
    scratch.unlink()
    output.write_bytes(payload)


def _build(repo: Path, vault: Path) -> None:
    _publish_graph(repo, vault)


@pytest.fixture(scope="module")
def staged(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """One read-only staged pack shared by the non-mutating provider cases."""
    repo, vault = _stage(tmp_path_factory.mktemp("consumer-contract"))
    _build(repo, vault)
    return repo, vault


def _resolve(repo: Path, request: str, *, write_artifacts: bool = True) -> dict[str, Any]:
    return resolve_provider(
        config_path=repo / "project.toml",
        repository_root=repo,
        request_source=repo / "requests" / request,
        write_artifacts=write_artifacts,
    )


def _assert_matches(expected_case: dict[str, Any], result: dict[str, Any]) -> None:
    assert _project(result) == expected_case["expect"]["result"]


# ── pack integrity and provenance ─────────────────────────────────────────


def test_pack_checksum_is_pinned_and_verifiable_in_one_command() -> None:
    manifest = _manifest()
    assert manifest["checksum"]["pack_sha256"] == EXPECTED_PACK_SHA256

    ok, problems = _verifier().verify(PACK)
    assert ok, problems

    # The command a consumer actually runs, executed exactly as documented.
    command = manifest["verification"]["consumer_command"].split()
    completed = subprocess.run(
        [sys.executable, *command[1:]],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert EXPECTED_PACK_SHA256 in _load("fixture-manifest.json")["checksum"]["pack_sha256"]


def test_pack_checksum_detects_any_edit(tmp_path: Path) -> None:
    copy = tmp_path / "pack"
    shutil.copytree(PACK, copy)
    verifier = _verifier()
    assert verifier.verify(copy)[0]

    target = copy / "expected/required.json"
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    ok, problems = verifier.verify(copy)
    assert not ok and any("expected/required.json" in problem for problem in problems)

    target.write_text(
        (PACK / "expected/required.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (copy / "requests/smuggled.json").write_text("{}\n", encoding="utf-8")
    ok, problems = verifier.verify(copy)
    assert not ok and any("smuggled" in problem for problem in problems)


def test_generated_artifacts_are_real_compiler_output(tmp_path: Path) -> None:
    repo, vault = _stage(tmp_path)
    # This pack's lock (runtime/.lock) shares a parent with the AKMS graph
    # output, which this test never builds. A real deployment bootstraps
    # runtime/ once; simulate that explicitly rather than relying on the
    # incidental side effect of building a graph this test does not need.
    # (regression guard: read-only compiler modes no longer create this
    # directory themselves -- see test_check_mode_creates_no_directories.)
    load_project_config(repo / "project.toml").resolve(repo, "lock").parent.mkdir(
        parents=True, exist_ok=True
    )
    check = run_compiler(
        config_path=repo / "project.toml",
        repository_root=repo,
        global_vault=vault,
        mode="check",
    )
    assert check["status"] == "clean", check
    manifest = _manifest()
    assert check["counts"] == manifest["generated"]["counts"]
    assert check["source_sha256"] == manifest["project"]["registry_source_sha256"]

    routes = json.loads((repo / "generated/routes.json").read_text(encoding="utf-8"))
    assert routes["source_hash"] == f"sha256:{check['source_sha256']}"
    assert routes["by_symbol"] == {}, "pack ships no source files, so no symbol routes"


def test_pack_identity_matches_the_integration_lock() -> None:
    manifest = _manifest()
    config = load_project_config(PACK / "project.toml")
    assert config.toolchain["akms_public_api_sha256"] == manifest["identity"][
        "akms_public_api_sha256"
    ]
    assert config.toolchain["repo2md_fixture_sha256"] == manifest["identity"][
        "repo2md_fixture_sha256"
    ]
    assert config.fingerprint == manifest["project"]["config_fingerprint"]

    lock_path = REPO_ROOT / manifest["identity"]["integration_lock"]
    if lock_path.is_file():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        assert lock["akms"]["public_api_sha256"] == config.toolchain[
            "akms_public_api_sha256"
        ]
        assert lock["repo2md"]["fixture_pack_sha256"] == config.toolchain[
            "repo2md_fixture_sha256"
        ]


def test_manifest_behaviour_matrix_is_complete() -> None:
    behaviours = _manifest()["behaviours"]
    assert set(behaviours) == {
        "exact_required",
        "coactivated_load_with",
        "advisory",
        "unrelated_near_prefix_negative",
        "diff_only_discovery",
        "stale_fingerprint",
        "missing_required_node",
        "record_recompile_roundtrip",
        "readonly_mutation_rejection",
        "absent_package_degradation",
        # Amendment 1, required by the contract review.
        "documentation_only_route_suppression",
        "fingerprint_portability",
        "staleness_decidability",
    }
    module = sys.modules[__name__]
    for name, entry in behaviours.items():
        assert hasattr(module, entry["test"]), f"{name} names a missing test"
        if entry["request"]:
            assert (PACK / entry["request"]).is_file()


def test_every_request_is_pinned_by_exactly_one_expected_case() -> None:
    requests = {path.name for path in (PACK / "requests").iterdir()}
    claimed: list[str] = []
    for name in (
        "required.json",
        "coactivated.json",
        "advisory.json",
        "empty.json",
        "docs-routing.json",
    ):
        for case in _load(f"expected/{name}")["cases"]:
            claimed.append(Path(case["request"]).name)
    for case in _load("expected/errors.json")["cases"]:
        if case["request"]:
            claimed.append(Path(case["request"]).name)
    # exact-path is reused by the missing-required-node error case and by every
    # case in expected/staleness.json, which varies the ENVIRONMENT rather than
    # the request.
    assert set(claimed) == requests
    assert claimed.count("exact-path.json") == 2
    assert len(claimed) == len(requests) + 1
    staleness = _load("expected/staleness.json")
    assert staleness["recorded_baseline"]["request"] == "requests/exact-path.json"
    assert (
        staleness["recorded_baseline"]["fingerprint"]
        == _case("required.json", "exact_required")["expect"]["result"]["fingerprint"]
    ), "the staleness baseline must be the same raw digest pinned in required.json"


# ── the ten frozen behaviours ─────────────────────────────────────────────


def test_exact_required_lesson(staged: tuple[Path, Path]) -> None:
    repo, _vault = staged
    result = _resolve(repo, "exact-path.json")
    _assert_matches(_case("required.json", "exact_required"), result)
    assert [record["node_id"] for record in result["records"]] == ["cc-failure-l001"]
    assert {record["selection_class"] for record in result["records"]} == {"required"}
    assert (repo / result["artifacts"]["result"]).is_file()
    assert (repo / result["artifacts"]["loadout"]).is_file()


def test_coactivated_load_with_lesson(staged: tuple[Path, Path]) -> None:
    repo, _vault = staged
    result = _resolve(repo, "related.json")
    _assert_matches(_case("coactivated.json", "coactivated_load_with"), result)
    classes = [record["selection_class"] for record in result["records"]]
    assert classes == ["required", "coactivated"]
    coactivated = result["records"][1]
    assert coactivated["node_id"] == "cc-failure-l003"
    assert coactivated["reasons"] == ["load_with from required node 'cc-failure-l002'"]
    routes = json.loads((repo / "generated/routes.json").read_text(encoding="utf-8"))
    assert "cc-failure-l003" not in json.dumps(
        routes["by_path"]["src/engine/scheduler.py"]
    )


def test_advisory_result(staged: tuple[Path, Path]) -> None:
    repo, _vault = staged
    result = _resolve(repo, "advisory-tags.json")
    _assert_matches(_case("advisory.json", "advisory"), result)
    assert [record["selection_class"] for record in result["records"]] == ["advisory"]
    assert result["records"][0]["node_id"] == "cc-failure-l004"


def test_unrelated_near_prefix_is_empty(staged: tuple[Path, Path]) -> None:
    repo, _vault = staged
    result = _resolve(repo, "unrelated-near-prefix.json")
    _assert_matches(_case("empty.json", "unrelated_near_prefix_negative"), result)
    assert result["status"] == "ok"
    assert result["records"] == []
    declared = _load("requests/unrelated-near-prefix.json")["declared_paths"]
    routes = json.loads((repo / "generated/routes.json").read_text(encoding="utf-8"))
    assert "src/engine/interface.py" in routes["by_path"]
    assert not set(declared) & set(routes["by_path"])


def test_diff_only_discovery(staged: tuple[Path, Path]) -> None:
    repo, _vault = staged
    result = _resolve(repo, "diff-only.json")
    _assert_matches(_case("required.json", "diff_only_discovery"), result)
    assert result["diagnostics"]["post_diff_only_required"] == ["cc-failure-l005"]
    assert result["diagnostics"]["empty_diff_fallback"] is False
    declared = _load("requests/diff-only.json")["declared_paths"]
    assert "src/storage/writer.py" not in declared


def test_stale_fingerprint(tmp_path: Path) -> None:
    repo, vault = _stage(tmp_path)
    _build(repo, vault)
    recorded = _resolve(repo, "exact-path.json")
    result_path = repo / recorded["artifacts"]["result"]
    expected = _case("errors.json", "stale_fingerprint")["expect"]

    current = validate_fingerprint(
        config_path=repo / "project.toml",
        repository_root=repo,
        request_source=repo / "requests/exact-path.json",
        result_path=result_path,
    )
    assert current == expected["current"], "raw digests are pinned, not reduced"
    assert current["recorded_fingerprint"] == current["current_fingerprint"]

    stale = validate_fingerprint(
        config_path=repo / "project.toml",
        repository_root=repo,
        request_source=repo / "requests/stale-baseline.json",
        result_path=result_path,
    )
    assert stale == expected["stale"], "raw digests are pinned, not reduced"
    assert stale["recorded_fingerprint"] != stale["current_fingerprint"]
    assert expected["canonical_generated_at"] == CANONICAL_GENERATED_AT
    assert not (repo / "runtime/provider/stale-baseline").exists()


def test_missing_required_node_fails_closed(tmp_path: Path) -> None:
    repo, vault = _stage(tmp_path)
    config = load_project_config(repo / "project.toml")
    (config.resolve(repo, "generated_nodes") / "cc-failure-l001.md").unlink()
    _build(repo, vault)
    expected = _case("errors.json", "missing_required_node")["expect"]["error"]
    with pytest.raises(FailureMemoryError) as raised:
        _resolve(repo, "exact-path.json", write_artifacts=False)
    assert raised.value.code == expected["code"]
    assert expected["message_contains"] in str(raised.value)


def test_record_and_recompile_round_trip(tmp_path: Path) -> None:
    repo, vault = _stage(tmp_path)
    expected = _load("recording/accepted-result.json")["expect"]
    created = add_lesson(
        config_path=repo / "project.toml",
        repository_root=repo,
        global_vault=vault,
        request_path=repo / "recording/proposal.json",
    )
    assert created == expected["result"]

    check = run_compiler(
        config_path=repo / "project.toml",
        repository_root=repo,
        global_vault=vault,
        mode="check",
    )
    assert {"status": check["status"], "counts": check["counts"]} == expected["recompile"]

    routes = json.loads((repo / "generated/routes.json").read_text(encoding="utf-8"))
    assert "src/engine/recorder.py" in routes["by_path"]
    assert "tests/engine/test_recorder_append.py" in routes["by_path"]
    node = (
        load_project_config(repo / "project.toml").resolve(repo, "generated_nodes")
        / "cc-failure-l007.md"
    ).read_text(encoding="utf-8")
    assert 'load_with: ["cc-failure-l001"]' in node

    # The recompiled tree still resolves: the new node is in the graph, the new
    # route is live, and the pre-existing exact route is unaffected.
    _build(repo, vault)
    graph = json.loads((repo / "runtime/graph.json").read_text(encoding="utf-8"))
    assert "cc-failure-l007" in {node["id"] for node in graph["nodes"]}
    resolved = _resolve(repo, "exact-path.json", write_artifacts=False)
    assert [record["node_id"] for record in resolved["records"]] == ["cc-failure-l001"]


def test_readonly_mutation_is_rejected(tmp_path: Path) -> None:
    repo, vault = _stage(tmp_path)
    expected = _case("errors.json", "readonly_mutation_rejection")["expect"]

    proposal = json.loads((repo / "recording/proposal.json").read_text(encoding="utf-8"))
    proposal["id"] = "L900"
    forged = repo / "forged-proposal.json"
    forged.write_text(json.dumps(proposal), encoding="utf-8")
    registry = repo / "lessons.json"
    before = registry.read_bytes()
    with pytest.raises(FailureMemoryError) as raised:
        add_lesson(
            config_path=repo / "project.toml",
            repository_root=repo,
            global_vault=vault,
            request_path=forged,
        )
    assert raised.value.code == expected["self_allocated_id"]["error"]["code"]
    assert (
        expected["self_allocated_id"]["error"]["message_contains"] in str(raised.value)
    )
    assert registry.read_bytes() == before
    assert expected["self_allocated_id"]["registry_unchanged"] is True

    node = (
        load_project_config(repo / "project.toml").resolve(repo, "generated_nodes")
        / "cc-failure-l001.md"
    )
    node.write_text(node.read_text(encoding="utf-8") + "\ntampered\n", encoding="utf-8")
    tampered = node.read_bytes()
    # See test_generated_artifacts_are_real_compiler_output: this pack's
    # lock parent is never created by this test's setup, and read-only
    # compiler modes no longer create it themselves.
    load_project_config(repo / "project.toml").resolve(repo, "lock").parent.mkdir(
        parents=True, exist_ok=True
    )
    check = run_compiler(
        config_path=repo / "project.toml",
        repository_root=repo,
        global_vault=vault,
        mode="check",
    )
    assert check["status"] == expected["check_mode_is_read_only"]["status"]
    assert check["counts"] == expected["check_mode_is_read_only"]["counts"]
    assert node.read_bytes() == tampered, "check mode must not repair, only report"


def test_absent_package_degradation() -> None:
    expected = _case("errors.json", "absent_package_degradation")["expect"]
    script = textwrap.dedent(
        """
        import importlib.util, json, sys
        from pathlib import Path

        # Remove every sys.path entry that can supply the package, so the probe
        # below observes a genuinely absent installation.
        for _ in range(64):
            spec = importlib.util.find_spec("akms_failure_memory")
            if spec is None:
                break
            locations = list(spec.submodule_search_locations or [])
            roots = {str(Path(item).resolve().parent) for item in locations}
            if spec.origin:
                roots.add(str(Path(spec.origin).resolve().parents[1]))
            sys.path[:] = [
                entry
                for entry in sys.path
                if str(Path(entry or ".").resolve()) not in roots
            ]
            sys.modules.pop("akms_failure_memory", None)
            importlib.invalidate_caches()

        available = importlib.util.find_spec("akms_failure_memory") is not None
        if available:
            print(json.dumps({"probe": "failed-to-hide-package"}))
            raise SystemExit(2)

        # The reference consumer degradation path, in full.
        envelope = {
            "schema_version": "failure-memory-consumer-degradation/v1",
            "status": "unavailable",
            "degraded": True,
            "reason": {
                "code": "failure_memory_absent",
                "message": (
                    "akms_failure_memory is not installed; "
                    "failure-memory context is unavailable."
                ),
            },
            "records": [],
            "required_node_ids": [],
            "enforcement": "disabled",
        }
        print(json.dumps(envelope, sort_keys=True))
        """
    )
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(Path(os.sep)),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout) == expected["envelope"]
    assert expected["envelope"]["schema_version"] != "failure-memory-provider-result/v1"
    schema = json.loads(
        (PACKAGE_ROOT / "schemas/provider-result.v1.json").read_text(encoding="utf-8")
    )
    assert schema["properties"]["status"] == {"const": "ok"}


# ── documented package findings, kept executable so they cannot rot ───────


# ── amendment 1: documentation-only route suppression ─────────────────────


def test_docs_only_scope_suppresses_the_required_lane(
    staged: tuple[Path, Path],
) -> None:
    """The lesson IS in advisory and is ABSENT from required -- both halves.

    ``akms.task_context.resolve._is_documentation_only`` drops every exact path
    spec when all of a task's path inputs are documentation, so an exact
    compiled route on a docs path can never produce a required record from a
    documentation-only task. The route genuinely exists, which is asserted here
    first so the miss cannot be mistaken for a missing route.
    """
    repo, _vault = staged
    routes = json.loads((repo / "generated/routes.json").read_text(encoding="utf-8"))
    docs_route = routes["by_path"]["docs/architecture.md"]
    assert [record["node_id"] for record in docs_route] == ["cc-failure-l006"]

    result = _resolve(repo, "docs-only.json")
    _assert_matches(_case("docs-routing.json", "docs_only_suppressed_to_advisory"), result)

    by_class: dict[str, set[str]] = {}
    for record in result["records"]:
        by_class.setdefault(record["selection_class"], set()).add(record["node_id"])
    assert "cc-failure-l006" in by_class.get("advisory", set()), "present in advisory"
    assert "cc-failure-l006" not in by_class.get("required", set()), "absent from required"
    assert by_class.get("required", set()) == set()
    assert result["resolution"]["required_count"] == 0
    assert result["resolution"]["advisory_count"] == 1


def test_docs_only_without_an_advisory_tag_delivers_nothing(
    staged: tuple[Path, Path],
) -> None:
    """Advisory is not a guaranteed fallback lane for a suppressed docs lesson."""
    repo, _vault = staged
    result = _resolve(repo, "docs-only-untagged.json")
    _assert_matches(
        _case("docs-routing.json", "docs_only_untagged_is_delivered_nowhere"), result
    )
    assert result["status"] == "ok"
    assert result["records"] == [], (
        "an exact route existed and the lesson was still delivered nowhere: a consumer "
        "must not call this outcome fail-closed enforcement"
    )


def test_docs_lesson_is_required_once_any_declared_path_is_code(
    staged: tuple[Path, Path],
) -> None:
    """The same docs lesson IS enforced when the task also touches code.

    Enforcement of a documentation lesson is therefore contingent on unrelated
    declared paths in the same task -- the control that proves the previous two
    outcomes are the documentation-only rule and not a broken route.
    """
    repo, _vault = staged
    result = _resolve(repo, "docs-mixed.json")
    _assert_matches(
        _case("docs-routing.json", "docs_mixed_scope_restores_required"), result
    )
    required = {
        record["node_id"]
        for record in result["records"]
        if record["selection_class"] == "required"
    }
    assert required == {"cc-failure-l001", "cc-failure-l006"}

    untagged = _load("requests/docs-only-untagged.json")["declared_paths"]
    mixed = _load("requests/docs-mixed.json")["declared_paths"]
    assert set(untagged) < set(mixed), "the mixed request only ADDS a non-documentation path"


# ── amendment 1: fingerprint portability and staleness decidability ───────


def test_pack_staging_matches_canonical_refresh_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pack's staging IS the canonical refresh publication, byte for byte.

    ``refresh_project(action="graph")`` is the production entry point. It also
    runs ``preflight``, a pure identity check over the installed AKMS and a
    pinned editable repo2md checkout, which a fixture consumer will not have;
    preflight contributes nothing to the published bytes, so it is stubbed here.
    Everything that DOES shape the bytes -- build_graph, the project-owned
    finalizer, the pinned generated_at -- is real.
    """
    repo, vault = _stage(tmp_path / "pack-staging")
    _publish_graph(repo, vault)
    pack_bytes = (repo / "runtime/graph.json").read_bytes()

    other, other_vault = _stage(tmp_path / "refresh-staging")
    monkeypatch.setattr(
        "akms_failure_memory.refresh.preflight", lambda **_kwargs: {"stubbed": True}
    )
    refresh_project(
        action="graph",
        config_path=other / "project.toml",
        repository_root=other,
        global_vault=other_vault,
        generated_at=CANONICAL_GENERATED_AT,
    )
    assert (other / "runtime/graph.json").read_bytes() == pack_bytes

    metadata = json.loads(pack_bytes)["graph"]
    assert metadata["generated_at"] == CANONICAL_GENERATED_AT
    assert metadata["repo_id"] == "ConsumerContract"
    assert metadata["global_vault"] == "<external-global-vault>", (
        "stage the pack outside $HOME; a vault under $HOME canonicalizes to a ~ form "
        "instead and will not reproduce the pinned digests"
    )
    assert str(vault) not in pack_bytes.decode("utf-8")


def test_fingerprint_portability(tmp_path: Path) -> None:
    """Same logical state ⇒ same fingerprint, raw and pinned.

    Two independent scratch roots, with the (identically empty) global vault
    mounted at two deliberately different absolute paths. Every digest must
    match, and must match the raw values pinned in expected/required.json.
    """
    pinned = _case("required.json", "exact_required")["expect"]["result"]
    observed = []
    for index, subdir in enumerate(("vault", "a/deeper/differently-named/vault")):
        repo, vault = _stage(tmp_path / f"portable{index}", vault_subdir=subdir)
        _publish_graph(repo, vault)
        observed.append(
            (
                (repo / "runtime/graph.json").read_bytes(),
                _resolve(repo, "exact-path.json"),
            )
        )
    (graph_a, result_a), (graph_b, result_b) = observed

    assert graph_a == graph_b, "canonical graph.json is byte-identical across mounts"
    assert result_a["fingerprint"] == result_b["fingerprint"] == pinned["fingerprint"]
    assert (
        result_a["resolution_fingerprint"]
        == result_b["resolution_fingerprint"]
        == pinned["resolution_fingerprint"]
    )
    assert (
        result_a["input_fingerprints"]["graph_sha256"]
        == hashlib.sha256(graph_a).hexdigest()
        == pinned["input_fingerprints"]["graph_sha256"]
    )
    assert (
        result_a["resolution"]["graph_version"]
        == pinned["resolution"]["graph_version"]
    )
    assert _project(result_a) == _project(result_b) == pinned

    # The only reduced fields are absolute paths, and they feed no digest.
    assert set(result_a["resolution"]) - set(pinned["resolution"]) == set(
        REDUCED_RESOLUTION
    )
    assert result_a["resolution"]["loadout_path"] != result_b["resolution"]["loadout_path"]


def _staleness_case(case_id: str) -> dict[str, Any]:
    for case in _load("expected/staleness.json")["cases"]:
        if case["case_id"] == case_id:
            return case
    raise AssertionError(f"expected/staleness.json has no case {case_id!r}")


def _recorded_result(tmp_path: Path) -> bytes:
    repo, vault = _stage(tmp_path / "recorded")
    _publish_graph(repo, vault)
    result = _resolve(repo, "exact-path.json")
    assert result["fingerprint"] == _load("expected/staleness.json")["recorded_baseline"][
        "fingerprint"
    ]
    return (repo / result["artifacts"]["result"]).read_bytes()


def _verdict(repo: Path, recorded: bytes) -> dict[str, Any]:
    target = repo / "recorded-result.json"
    target.write_bytes(recorded)
    return validate_fingerprint(
        config_path=repo / "project.toml",
        repository_root=repo,
        request_source=repo / "requests/exact-path.json",
        result_path=target,
    )


def test_staleness_rebuild_alone_is_current(tmp_path: Path) -> None:
    """A rebuild on its own is NEVER stale -- the property the gate rests on."""
    recorded = _recorded_result(tmp_path)
    repo, vault = _stage(
        tmp_path / "rebuilt", vault_subdir="a/deeper/differently-named/vault"
    )
    _publish_graph(repo, vault)
    verdict = _verdict(repo, recorded)
    expect = _staleness_case("rebuilt_is_current")["expect"]
    assert verdict["status"] == expect["status"]
    assert verdict["stale"] is expect["stale"]
    assert verdict["recorded_fingerprint"] == expect["recorded_fingerprint"]
    assert verdict["current_fingerprint"] == expect["current_fingerprint"]


def test_staleness_content_change_is_stale(tmp_path: Path) -> None:
    """A genuine content change produces a specific, reproducible new digest."""
    recorded = _recorded_result(tmp_path)
    repo, vault = _stage(tmp_path / "content")
    add_lesson(
        config_path=repo / "project.toml",
        repository_root=repo,
        global_vault=vault,
        request_path=repo / "recording/proposal.json",
    )
    _publish_graph(repo, vault)
    verdict = _verdict(repo, recorded)
    expect = _staleness_case("content_change_is_stale")["expect"]
    assert verdict["status"] == expect["status"]
    assert verdict["stale"] is expect["stale"]
    assert verdict["current_fingerprint"] == expect["current_fingerprint"]


def test_staleness_noncanonical_publication_is_falsely_stale(tmp_path: Path) -> None:
    """Skipping the finalizer produces permanent, non-reproducible staleness."""
    recorded = _recorded_result(tmp_path)
    verdicts = []
    for index in range(2):
        repo, vault = _stage(tmp_path / f"noncanonical{index}")
        _publish_graph(repo, vault, canonical=False)
        verdicts.append(_verdict(repo, recorded))
    expect = _staleness_case("noncanonical_publication_is_stale")["expect"]
    assert expect["current_fingerprint_is_pinned"] is False
    for verdict in verdicts:
        assert verdict["status"] == expect["status"]
        assert verdict["stale"] is expect["stale"]
        assert verdict["recorded_fingerprint"] == expect["recorded_fingerprint"]
        assert verdict["current_fingerprint"] != verdict["recorded_fingerprint"]
    assert verdicts[0]["current_fingerprint"] != verdicts[1]["current_fingerprint"], (
        "raw build_graph output is not even self-consistent between two runs"
    )


def test_staleness_changed_generated_at_is_stale(tmp_path: Path) -> None:
    """generated_at is the one portability axis the package cannot close."""
    recorded = _recorded_result(tmp_path)
    repo, vault = _stage(tmp_path / "regenerated")
    _publish_graph(repo, vault, generated_at=ALTERNATE_GENERATED_AT)
    verdict = _verdict(repo, recorded)
    expect = _staleness_case("changed_generated_at_is_stale")["expect"]
    assert expect["alternate_generated_at"] == ALTERNATE_GENERATED_AT
    assert verdict["status"] == expect["status"]
    assert verdict["stale"] is expect["stale"]
    assert verdict["current_fingerprint"] == expect["current_fingerprint"]

    # generated_at is mandatory by design -- there is no implicit wall-clock
    # default a consumer could fall back to without noticing.
    with pytest.raises(FailureMemoryError) as raised:
        _timestamp(None)
    assert raised.value.code == "generated_at_required"


def test_source_ref_is_the_akms_provenance_field_not_a_path(
    staged: tuple[Path, Path],
) -> None:
    repo, _vault = staged
    result = _resolve(repo, "exact-path.json", write_artifacts=False)
    record = result["records"][0]
    assert record["source_ref"] == "human"
    assert record["content_ref"].endswith("cc-failure-l001.md")
    assert (repo / record["content_ref"]).is_file()


def test_init_default_layout_feeds_the_graph_and_resolves(tmp_path: Path) -> None:
    """Regression test for the fixed ``akms_layout_is_hardcoded`` finding.

    This test previously asserted the OPPOSITE outcome (that ``init``'s default
    layout could not feed the graph -- see git history for
    ``test_init_default_layout_cannot_feed_the_graph``). ``akms.graph.build_graph``
    still hardcodes ``<akms_repo_root>/knowledge/local-nodes/`` as the only
    local-node source; the fix was on the ``failure-memory`` side:
    ``render_project_config``'s default ``[paths]`` now puts ``local_nodes``
    (and therefore ``generated_nodes``) INSIDE ``akms_repo_root``, so compiled
    output is graph input by construction, matching this pack's own
    ``project.toml`` layout (see ``generated.layout_rationale`` above).

    This defect's whole character is that it is invisible with zero lessons
    (early consumers adopted the broken default with empty
    registries), so this test does not stop at a path assertion: it records a
    REAL lesson through the public ``add_lesson`` API, builds the REAL AKMS
    graph (``akms.graph.build_graph``, not mocked), and calls the REAL
    ``resolve_provider`` for a task matching that lesson's location -- proving
    it comes back as a required record instead of raising
    ``FailureMemoryError(code="resolve_error")``.
    """
    from akms_failure_memory.project import init_project

    repo = tmp_path / "init-default"
    repo.mkdir()
    vault = tmp_path / "init-vault"
    vault.mkdir()
    config_path = repo / ".failure-memory/config.toml"
    init_project(
        repository_root=repo,
        config_path=".failure-memory/config.toml",
        repository_id="Demo",
        node_namespace="demo-failure",
    )
    config = load_project_config(config_path)
    assert config.resolve(repo, "local_nodes").is_relative_to(
        config.resolve(repo, "akms_repo_root")
    ), "init's default local_nodes must live inside akms_repo_root or build_graph cannot see it"

    proposal = json.loads((PACK / "recording/proposal.json").read_text(encoding="utf-8"))
    proposal["related"] = []  # this registry starts empty, so L001 is the new id
    request = tmp_path / "proposal.json"
    request.write_text(json.dumps(proposal), encoding="utf-8")
    add_lesson(
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
        request_path=request,
    )

    graph = build_graph(
        config.resolve(repo, "akms_repo_root"),
        global_vault=vault,
        output_path=config.resolve(repo, "graph"),
        strict=True,
    )
    assert list(graph.nodes) == [
        "demo-failure-l001"
    ], "the recorded lesson's compiled node must reach the graph"

    provider_request = {
        "schema_version": "failure-memory-provider-request/v1",
        "invocation_id": "init-default-regression",
        "mode": "pre-task",
        "role": "implementer",
        "repository_id": "Demo",
        "task": {
            "task_id": "init-default-regression",
            "title": "Touch the recorded file",
            "objective": "regression: resolve_provider must return the recorded lesson, not raise",
            "scope": [],
            "deliverables": [],
            "akms_tags": [],
        },
        "declared_paths": [proposal["location"]["file"]],
        "changed_paths": [],
        "base": None,
        "head": None,
        "baseline": "init-default-regression-baseline",
        "refresh_policy": "never",
        "output_dir": ".failure-memory/runtime/provider",
    }
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(provider_request), encoding="utf-8")
    result = resolve_provider(
        config_path=config_path,
        repository_root=repo,
        request_source=request_path,
        write_artifacts=False,
    )
    assert result["status"] == "ok"
    assert [r["node_id"] for r in result["records"]] == ["demo-failure-l001"]
    assert result["records"][0]["selection_class"] == "required"


def test_pack_files_are_utf8_json_or_toml() -> None:
    for path in sorted(PACK.rglob("*")):
        if not path.is_file() or path.suffix not in {".json", ".toml", ".md", ".py"}:
            continue
        data = path.read_bytes()
        data.decode("utf-8")
        if path.suffix == ".json":
            json.loads(data)
        assert hashlib.sha256(data).hexdigest()
