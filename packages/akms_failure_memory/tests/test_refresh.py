from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import akms
import pytest
from akms_failure_memory.cli import main
from akms_failure_memory.config import load_project_config
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.locks import ProjectLock
from akms_failure_memory.provider import resolve_provider
from akms_failure_memory.refresh import (
    _akms_public_digest,
    preflight,
    refresh_project,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONFIG_SOURCE = PACKAGE_ROOT / "tests/fixtures/project_configs/numerixweave.toml"
SECOND_CONFIG_SOURCE = (
    PACKAGE_ROOT / "tests/fixtures/project_configs/second_project.toml"
)
REGISTRY_SOURCE = (
    PACKAGE_ROOT / "tests/fixtures/numerixweave_phase1/source_registry.json"
)
VALID_STATE_BYTES = (
    b"akms_schema: v2\nrepo_id: preserved\nnodes: {}\nlocal_edges: []\n"
    b"session_nodes: {}\nsuppressed_edges: []\nprocessed_sources: []\n"
)
VALID_GRAPH_BYTES = b'{"graph":{"sentinel":"exact"}}\n'


def _toolchain(tmp_path: Path, *, version: str = "0.2.0", valid_help: bool = True):
    tool_root = tmp_path / "repo2md"
    fixture = tool_root / "tests/fixtures/akms_export/contract.json"
    fixture.parent.mkdir(parents=True)
    fixture.write_text('{"schema": 1}\n', encoding="utf-8")
    content = fixture.read_bytes()
    digest = hashlib.sha256()
    digest.update(b"contract.json\0")
    digest.update(content)
    digest.update(b"\0")
    fixture_sha = digest.hexdigest()
    pin = {
        "package": "repo2md",
        "version": version,
        "fixture_contract_version": 1,
        "export_schema_version": 1,
        "akms_schema_version": "v2",
        "fixture_root": "tests/fixtures/akms_export",
        "fixture_pack_sha256": fixture_sha,
        "files": [
            {
                "path": "contract.json",
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        ],
    }
    pin_path = tool_root / "dev/plans/mirror_export/release/integration_pin.json"
    pin_path.parent.mkdir(parents=True)
    pin_path.write_text(json.dumps(pin), encoding="utf-8")
    (tool_root / "pyproject.toml").write_text(
        f'[project]\nname = "repo2md"\nversion = "{version}"\n', encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q", str(tool_root)], check=True)
    subprocess.run(["git", "-C", str(tool_root), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tool_root),
            "-c",
            "user.name=Failure Memory Tests",
            "-c",
            "user.email=failure-memory@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    commit = subprocess.run(
        ["git", "-C", str(tool_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    environment = tmp_path / "tool-environment"
    executable = environment / "bin/repo-wiki"
    executable.parent.mkdir(parents=True)
    flags = "--output --phase --json" if valid_help else "usage only"
    executable.write_text(f'#!/bin/sh\nprintf "%s\\n" "{flags}"\n', encoding="utf-8")
    executable.chmod(0o755)
    dist = environment / "lib/python3.12/site-packages/repo2md-0.2.0.dist-info"
    dist.mkdir(parents=True)
    (dist / "METADATA").write_text(
        f"Metadata-Version: 2.4\nName: repo2md\nVersion: {version}\n", encoding="utf-8"
    )
    (dist / "direct_url.json").write_text(
        json.dumps({"url": tool_root.as_uri(), "dir_info": {"editable": True}}),
        encoding="utf-8",
    )
    (dist / "entry_points.txt").write_text(
        "[console_scripts]\nrepo-wiki = repo2md.cli:main\n", encoding="utf-8"
    )
    executable_hash = (
        base64.urlsafe_b64encode(hashlib.sha256(executable.read_bytes()).digest())
        .decode("ascii")
        .rstrip("=")
    )
    (dist / "RECORD").write_text(
        f"../../../bin/repo-wiki,sha256={executable_hash},{executable.stat().st_size}\n",
        encoding="utf-8",
    )
    return executable, tool_root, commit, fixture_sha


def _repo(
    tmp_path: Path,
    *,
    version: str = "0.2.0",
    timeout: str = "120",
    valid_help: bool = True,
    config_source: Path = CONFIG_SOURCE,
) -> tuple[Path, Path, Path, Path]:
    repo = tmp_path / "repo"
    registry = repo / "dev/lessons_from_failing.json"
    registry.parent.mkdir(parents=True)
    registry.write_bytes(REGISTRY_SOURCE.read_bytes())
    tool, tool_root, commit, fixture_sha = _toolchain(
        tmp_path, version=version, valid_help=valid_help
    )
    config = repo / "failure-memory.toml"
    text = config_source.read_text(encoding="utf-8")
    text = text.replace(
        'repo2md_command = ["repo-wiki"]', f'repo2md_command = ["{tool}"]'
    )
    text = text.replace("timeout_seconds = 120", f"timeout_seconds = {timeout}")
    text = text.replace("478be35c76325ab1ccea48b69a5ea25b095952a6", commit).replace(
        "5d2e398b7baab7045615ccb0e935c2baeae154d21fb4a29ba5498f06687d2d6b",
        fixture_sha,
    )
    config.write_text(text, encoding="utf-8")
    vault = tmp_path / "global"
    vault.mkdir()
    return repo, config, vault, tool_root


def _successful_mirror(*_args, **_kwargs) -> SimpleNamespace:
    return SimpleNamespace(
        success=True,
        provider="repo2md",
        files_processed=0,
        definitions_total=0,
        provider_metadata={},
        errors=[],
    )


def _provider_request(repository_id: str) -> dict[str, object]:
    return {
        "schema_version": "failure-memory-provider-request/v1",
        "invocation_id": "refresh-provider-current",
        "repository_id": repository_id,
        "baseline": "base-001",
        "mode": "pre-task",
        "role": "implementer",
        "declared_paths": ["apps/tifem/src/tifem/Elements/CohesiveInterface.py"],
        "changed_paths": [],
        "base": None,
        "head": None,
        "refresh_policy": "require-current",
        "output_dir": "dev/knowledge/provider",
        "task": {
            "task_id": "F3-provider-current",
            "phase": 3,
            "title": "Resolve current failure memory",
            "objective": "Exercise canonical graph freshness.",
            "scope": [],
            "deliverables": [],
            "akms_tags": [],
        },
    }


def test_preflight_reports_identity_without_mutation(tmp_path: Path) -> None:
    """preflight reports the installed identity and touches nothing.

    The reported digest is compared against the one recomputed from the installed
    AKMS rather than a hardcoded literal. Pinning the literal here made this test
    a second place to chase whenever any of the seventeen AKMS public sources
    changed, which is the friction this module's docstring describes; what matters
    is that preflight reports the digest faithfully, not that it has some
    particular historical value.
    """
    repo, config_path, _vault, _tool_root = _repo(tmp_path)
    before = sorted(path.relative_to(repo) for path in repo.rglob("*"))
    result = preflight(config=load_project_config(config_path), repository_root=repo)
    assert result["status"] == "ok"
    assert result["akms"]["public_api_sha256"] == _akms_public_digest()
    assert len(result["akms"]["public_api_sha256"]) == 64
    assert result["akms"]["version"] == akms.__version__
    assert result["akms"]["schema"] == akms.AKMS_SCHEMA_VERSION
    assert sorted(path.relative_to(repo) for path in repo.rglob("*")) == before


def _codes(result: dict) -> set[str]:
    """Advisory codes reported by a preflight result."""
    return {entry["code"] for entry in result.get("advisories", [])}


def test_preflight_blocks_only_when_the_next_step_cannot_run(tmp_path: Path) -> None:
    """Two conditions block: repo2md missing, and its CLI contract incomplete.

    Identity drift does not. preflight is a usability check for a dev tool, not
    an attestation — see the docstring on preflight() for why enforcing identity
    on every call made correct edits fail closed.
    """
    # A repo2md that cannot be invoked at all still fails, before any mutation.
    repo, config_path, _vault, _tool_root = _repo(tmp_path)
    config_path.write_text(
        config_path.read_text().replace(
            str(tmp_path / "tool-environment/bin/repo-wiki"), str(tmp_path / "missing")
        )
    )
    with pytest.raises(FailureMemoryError, match="unavailable"):
        preflight(config=load_project_config(config_path), repository_root=repo)
    assert not (repo / "dev/knowledge").exists()

    # A repo2md whose export-akms contract lacks the flags we depend on.
    repo, config_path, _vault, _tool_root = _repo(
        tmp_path / "contract", valid_help=False
    )
    with pytest.raises(FailureMemoryError, match="CLI contract"):
        preflight(config=load_project_config(config_path), repository_root=repo)
    assert not (repo / "dev/knowledge").exists()


def test_version_drift_is_advisory_not_fatal(tmp_path: Path) -> None:
    """A repo2md version that differs from the pin no longer refuses to run."""
    repo, config_path, _vault, _tool_root = _repo(tmp_path, version="9.9.9")
    result = preflight(config=load_project_config(config_path), repository_root=repo)
    assert result["status"] == "ok"
    assert "repo2md_version_drift" in _codes(result)
    assert not (repo / "dev/knowledge").exists()


def test_unverifiable_distribution_is_advisory(tmp_path: Path) -> None:
    """repo2md not linked to an editable install is reported, not rejected."""
    repo, config_path, _vault, _tool_root = _repo(tmp_path)
    fake = tmp_path / "fake"
    fake.write_text(
        '#!/bin/sh\necho "repo2md 0.2.0"\n'
        'case "$*" in *export-akms*) echo "--output --phase --json";; esac\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    config_path.write_text(
        config_path.read_text().replace(
            str(tmp_path / "tool-environment/bin/repo-wiki"), str(fake)
        )
    )
    result = preflight(config=load_project_config(config_path), repository_root=repo)
    assert result["status"] == "ok"
    assert "repo2md_distribution_unknown" in _codes(result)


def test_commit_dirty_and_fixture_drift_are_advisory(tmp_path: Path) -> None:
    """The identity tuple is reported so drift stays visible, but never blocks."""
    # Commit drift.
    repo, config_path, _vault, tool_root = _repo(tmp_path / "commit")
    head = subprocess.run(
        ["git", "-C", str(tool_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    config_path.write_text(config_path.read_text().replace(head, "0" * 40))
    result = preflight(config=load_project_config(config_path), repository_root=repo)
    assert "repo2md_commit_drift" in _codes(result)

    # Dirty checkout, under the require-clean policy.
    repo, config_path, _vault, tool_root = _repo(tmp_path / "dirty")
    (tool_root / "untracked").write_text("dirty")
    result = preflight(config=load_project_config(config_path), repository_root=repo)
    assert "repo2md_dirty" in _codes(result)

    # Export-schema drift.
    repo, config_path, _vault, tool_root = _repo(tmp_path / "schema")
    config_path.write_text(
        config_path.read_text().replace("require-clean", "allow-dirty")
    )
    pin = tool_root / "dev/plans/mirror_export/release/integration_pin.json"
    pin.write_text(
        pin.read_text().replace(
            '"export_schema_version": 1', '"export_schema_version": 2'
        )
    )
    result = preflight(config=load_project_config(config_path), repository_root=repo)
    assert "repo2md_export_schema_drift" in _codes(result)

    # Fixture-pack drift.
    repo, config_path, _vault, tool_root = _repo(tmp_path / "fixture")
    config_path.write_text(
        config_path.read_text().replace("require-clean", "allow-dirty")
    )
    (tool_root / "tests/fixtures/akms_export/contract.json").write_text("mutated")
    result = preflight(config=load_project_config(config_path), repository_root=repo)
    assert _codes(result) & {"repo2md_fixture_drift", "repo2md_fixture_unreadable"}


def test_akms_public_api_drift_is_advisory(tmp_path: Path) -> None:
    """Editing AKMS source must not stop a developer using failure memory.

    This is the case that motivated the change: any byte change to one of the
    seventeen pinned AKMS sources used to fail every operation closed.
    """
    repo, config_path, _vault, _tool_root = _repo(tmp_path)
    config_path.write_text(
        re.sub(
            r'akms_public_api_sha256 = "[0-9a-f]{64}"',
            'akms_public_api_sha256 = "%s"' % ("0" * 64),
            config_path.read_text(),
        )
    )
    result = preflight(config=load_project_config(config_path), repository_root=repo)
    assert result["status"] == "ok"
    assert "akms_public_api_drift" in _codes(result)


def test_public_api_pin_is_optional(tmp_path: Path) -> None:
    """A project need not carry a pin that no longer gates anything."""
    repo, config_path, _vault, _tool_root = _repo(tmp_path)
    config_path.write_text(
        re.sub(
            r'akms_public_api_sha256 = "[0-9a-f]{64}"\n', "", config_path.read_text()
        )
    )
    result = preflight(config=load_project_config(config_path), repository_root=repo)
    assert result["status"] == "ok"
    assert "akms_public_api_drift" not in _codes(result)


def test_single_writer_lock_contention(tmp_path: Path) -> None:
    repo, config_path, vault, _tool_root = _repo(tmp_path, timeout="0.05")
    config = load_project_config(config_path)
    acquired = threading.Event()
    release = threading.Event()

    def holder() -> None:
        with ProjectLock(config.resolve(repo, "lock")):
            acquired.set()
            release.wait(2)

    thread = threading.Thread(target=holder)
    thread.start()
    assert acquired.wait(2)
    try:
        with pytest.raises(FailureMemoryError, match="Timed out"):
            refresh_project(
                action="lessons",
                config_path=config_path,
                repository_root=repo,
                global_vault=vault,
            )
    finally:
        release.set()
        thread.join(2)


def test_all_stops_before_graph_when_mirror_fails(tmp_path: Path, monkeypatch) -> None:
    repo, config_path, vault, _tool_root = _repo(tmp_path)

    def fail(*_args, **_kwargs):
        raise FailureMemoryError("mirror exploded", code="mirror_failure")

    monkeypatch.setattr("akms_failure_memory.refresh.run_mirror_provider", fail)
    with pytest.raises(FailureMemoryError, match="mirror exploded"):
        refresh_project(
            action="all",
            config_path=config_path,
            repository_root=repo,
            global_vault=vault,
            generated_at="2026-08-11T00:00:00+00:00",
        )
    assert not (repo / "dev/knowledge/graph/graph.json").exists()


@pytest.mark.parametrize("action", ["graph", "all"])
def test_graph_refresh_uses_explicit_deterministic_timestamp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    repo, config_path, vault, _tool_root = _repo(tmp_path)
    monkeypatch.setattr(
        "akms_failure_memory.refresh.run_mirror_provider",
        lambda *_args, **_kwargs: SimpleNamespace(
            success=True,
            provider="repo2md",
            files_processed=0,
            definitions_total=0,
            provider_metadata={},
            errors=[],
        ),
    )
    graph_path = repo / "dev/knowledge/graph/graph.json"
    state_path = repo / "dev/knowledge/graph/local_state.yaml"
    generated_at = "2026-08-11T00:00:00+00:00"

    first = refresh_project(
        action=action,
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
        generated_at=generated_at,
    )
    first_bytes = graph_path.read_bytes()
    first_sha = hashlib.sha256(first_bytes).hexdigest()
    second = refresh_project(
        action=action,
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
        generated_at=generated_at,
    )
    second_bytes = graph_path.read_bytes()

    assert second_bytes == first_bytes
    assert hashlib.sha256(second_bytes).hexdigest() == first_sha
    assert json.loads(first_bytes)["graph"]["generated_at"] == generated_at
    assert not state_path.exists()
    assert second["config_fingerprint"] == first["config_fingerprint"]
    status_result = refresh_project(
        action="status",
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
    )
    assert status_result["artifacts"]["graph"]["sha256"] == first_sha

    changed_at = "2026-08-12T00:00:00+00:00"
    refresh_project(
        action=action,
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
        generated_at=changed_at,
    )
    changed_bytes = graph_path.read_bytes()
    first_graph = json.loads(first_bytes)
    changed_graph = json.loads(changed_bytes)
    assert changed_bytes != first_bytes
    assert changed_graph["graph"]["generated_at"] == changed_at
    first_graph["graph"].pop("generated_at")
    changed_graph["graph"].pop("generated_at")
    assert changed_graph == first_graph


@pytest.mark.parametrize("action", ["graph", "all"])
def test_absent_state_graph_identity_comes_from_project_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    repo, config_path, vault, _tool_root = _repo(tmp_path)
    monkeypatch.setattr(
        "akms_failure_memory.refresh.run_mirror_provider", _successful_mirror
    )
    config = load_project_config(config_path)
    graph_path = config.resolve(repo, "graph")
    state_path = (
        config.resolve(repo, "akms_repo_root") / "knowledge/graph/local_state.yaml"
    )
    generated_at = "2026-08-11T00:00:00+00:00"

    first = refresh_project(
        action=action,
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
        generated_at=generated_at,
    )
    first_bytes = graph_path.read_bytes()
    second = refresh_project(
        action=action,
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
        generated_at=generated_at,
    )

    assert graph_path.read_bytes() == first_bytes
    assert json.loads(first_bytes)["graph"]["repo_id"] == config.repository_id
    assert (
        json.loads(first_bytes)["graph"]["repo_id"]
        != config.resolve(repo, "akms_repo_root").name
    )
    assert not state_path.exists()
    assert first["stages"]["graph"]["status"] == "ok"
    assert first["toolchain"]["status"] == "ok"
    assert first["config_fingerprint"] == config.fingerprint
    assert second["config_fingerprint"] == config.fingerprint


def test_config_identity_overrides_conflicting_overlay_without_mutating_state(
    tmp_path: Path,
) -> None:
    repo, config_path, vault, _tool_root = _repo(tmp_path)
    config = load_project_config(config_path)
    graph_path = config.resolve(repo, "graph")
    state_path = (
        config.resolve(repo, "akms_repo_root") / "knowledge/graph/local_state.yaml"
    )
    state_path.parent.mkdir(parents=True)
    state_path.write_bytes(VALID_STATE_BYTES)
    before = state_path.read_bytes()

    refresh_project(
        action="graph",
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
        generated_at="2026-08-11T00:00:00+00:00",
    )

    assert state_path.read_bytes() == before
    graph_identity = json.loads(graph_path.read_bytes())["graph"]["repo_id"]
    assert graph_identity == config.repository_id
    assert graph_identity != "preserved"


def test_distinct_project_configs_produce_distinct_graph_identities(
    tmp_path: Path,
) -> None:
    outputs: dict[str, str] = {}
    for fixture in (CONFIG_SOURCE, SECOND_CONFIG_SOURCE):
        repo, config_path, vault, _tool_root = _repo(
            tmp_path / fixture.stem, config_source=fixture
        )
        config = load_project_config(config_path)
        refresh_project(
            action="graph",
            config_path=config_path,
            repository_root=repo,
            global_vault=vault,
            generated_at="2026-08-11T00:00:00+00:00",
        )
        outputs[fixture.name] = json.loads(config.resolve(repo, "graph").read_bytes())[
            "graph"
        ]["repo_id"]
        assert outputs[fixture.name] == config.repository_id

    assert len(set(outputs.values())) == len(outputs)


@pytest.mark.parametrize("action", ["graph", "all"])
def test_production_refresh_then_require_current_provider_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    action: str,
) -> None:
    repo, config_path, vault, _tool_root = _repo(tmp_path)
    config = load_project_config(config_path)
    state_path = (
        config.resolve(repo, "akms_repo_root") / "knowledge/graph/local_state.yaml"
    )
    request_path = repo / "provider-request.json"
    request_path.write_text(
        json.dumps(_provider_request(config.repository_id)), encoding="utf-8"
    )
    monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(vault))
    monkeypatch.setattr(
        "akms_failure_memory.refresh.run_mirror_provider", _successful_mirror
    )
    if action == "graph":
        assert (
            main(
                [
                    "compile",
                    "--config",
                    str(config_path),
                    "--repo",
                    str(repo),
                    "--global-vault",
                    str(vault),
                ]
            )
            == 0
        )
    assert (
        main(
            [
                "refresh",
                action,
                "--config",
                str(config_path),
                "--repo",
                str(repo),
                "--global-vault",
                str(vault),
                "--generated-at",
                "2026-08-11T00:00:00+00:00",
            ]
        )
        == 0
    )
    assert not state_path.exists()
    capsys.readouterr()

    assert (
        main(
            [
                "resolve",
                "--config",
                str(config_path),
                "--repo",
                str(repo),
                "--request",
                str(request_path),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["repository_id"] == config.repository_id
    assert not any(vault.iterdir())


def test_config_identity_change_invalidates_then_refreshes_provider_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, config_path, vault, _tool_root = _repo(tmp_path)
    monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(vault))
    refresh_project(
        action="lessons",
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
    )
    refresh_project(
        action="graph",
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
        generated_at="2026-08-11T00:00:00+00:00",
    )
    first_config = load_project_config(config_path)
    first = resolve_provider(
        config_path=config_path,
        repository_root=repo,
        request_source=_provider_request(first_config.repository_id),
        write_artifacts=False,
    )

    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            'repository_id = "NumerixWeave"',
            'repository_id = "NumerixWeave-Replica"',
            1,
        ),
        encoding="utf-8",
    )
    second_config = load_project_config(config_path)
    second_request = _provider_request(second_config.repository_id)
    with pytest.raises(FailureMemoryError, match="graph is stale"):
        resolve_provider(
            config_path=config_path,
            repository_root=repo,
            request_source=second_request,
            write_artifacts=False,
        )

    refresh_project(
        action="graph",
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
        generated_at="2026-08-11T00:00:00+00:00",
    )
    second = resolve_provider(
        config_path=config_path,
        repository_root=repo,
        request_source=second_request,
        write_artifacts=False,
    )

    graph = json.loads(second_config.resolve(repo, "graph").read_bytes())
    assert graph["graph"]["repo_id"] == second_config.repository_id
    assert second["fingerprint"] != first["fingerprint"]


def test_require_current_preserves_conflicting_overlay_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, config_path, vault, _tool_root = _repo(tmp_path)
    config = load_project_config(config_path)
    state_path = (
        config.resolve(repo, "akms_repo_root") / "knowledge/graph/local_state.yaml"
    )
    state_path.parent.mkdir(parents=True)
    state_path.write_bytes(VALID_STATE_BYTES)
    before = state_path.read_bytes()
    monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(vault))
    refresh_project(
        action="lessons",
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
    )
    refresh_project(
        action="graph",
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
        generated_at="2026-08-11T00:00:00+00:00",
    )

    result = resolve_provider(
        config_path=config_path,
        repository_root=repo,
        request_source=_provider_request(config.repository_id),
        write_artifacts=False,
    )

    assert result["status"] == "ok"
    assert state_path.read_bytes() == before
    assert not any(vault.iterdir())


def test_require_current_rejects_recorded_repo_identity_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, config_path, vault, _tool_root = _repo(tmp_path)
    config = load_project_config(config_path)
    monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(vault))
    refresh_project(
        action="lessons",
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
    )
    refresh_project(
        action="graph",
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
        generated_at="2026-08-11T00:00:00+00:00",
    )
    graph_path = config.resolve(repo, "graph")
    graph = json.loads(graph_path.read_bytes())
    graph["graph"]["repo_id"] = "wrong-recorded-identity"
    graph_path.write_text(json.dumps(graph), encoding="utf-8")

    with pytest.raises(FailureMemoryError, match="graph is stale"):
        resolve_provider(
            config_path=config_path,
            repository_root=repo,
            request_source=_provider_request(config.repository_id),
            write_artifacts=False,
        )


def test_graph_refresh_failure_preserves_previous_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, config_path, vault, _tool_root = _repo(tmp_path)
    graph_path = repo / "dev/knowledge/graph/graph.json"
    refresh_project(
        action="graph",
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
        generated_at="2026-08-11T00:00:00+00:00",
    )
    previous = graph_path.read_bytes()

    def write_invalid_graph(*_args, output_path: Path, **_kwargs):
        Path(output_path).write_text('{"graph":', encoding="utf-8")
        return SimpleNamespace(number_of_nodes=lambda: 0, number_of_edges=lambda: 0)

    monkeypatch.setattr("akms_failure_memory.refresh.build_graph", write_invalid_graph)
    with pytest.raises(FailureMemoryError, match="deterministic AKMS graph metadata"):
        refresh_project(
            action="graph",
            config_path=config_path,
            repository_root=repo,
            global_vault=vault,
            generated_at="2026-08-12T00:00:00+00:00",
        )
    assert graph_path.read_bytes() == previous
    assert not list(graph_path.parent.glob(f".{graph_path.name}.*.tmp"))


@pytest.mark.parametrize(
    ("state_bytes", "graph_bytes"),
    [
        (None, None),
        (VALID_STATE_BYTES, None),
        (None, VALID_GRAPH_BYTES),
        (VALID_STATE_BYTES, VALID_GRAPH_BYTES),
    ],
)
def test_graph_refresh_real_schema_failure_preserves_all_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    state_bytes: bytes | None,
    graph_bytes: bytes | None,
) -> None:
    repo, config_path, vault, _tool_root = _repo(tmp_path)
    graph_dir = repo / "dev/knowledge/graph"
    state_path = graph_dir / "local_state.yaml"
    graph_path = graph_dir / "graph.json"
    malformed_node = repo / "dev/knowledge/local-nodes/malformed.md"
    malformed_node.parent.mkdir(parents=True)
    malformed_node.write_text(
        "---\nakms_schema: v1\nid: malformed\n---\nMalformed node.\n",
        encoding="utf-8",
    )
    if state_bytes is not None:
        graph_dir.mkdir(parents=True, exist_ok=True)
        state_path.write_bytes(state_bytes)
    if graph_bytes is not None:
        graph_dir.mkdir(parents=True, exist_ok=True)
        graph_path.write_bytes(graph_bytes)

    exit_code = main(
        [
            "refresh",
            "graph",
            "--config",
            str(config_path),
            "--repo",
            str(repo),
            "--global-vault",
            str(vault),
            "--generated-at",
            "2026-08-11T00:00:00+00:00",
        ]
    )

    assert exit_code == 2
    assert "Schema version mismatch" in capsys.readouterr().err
    if state_bytes is None:
        assert not state_path.exists()
    else:
        assert state_path.read_bytes() == state_bytes
    if graph_bytes is None:
        assert not graph_path.exists()
    else:
        assert graph_path.read_bytes() == graph_bytes
    assert not list(graph_dir.glob(".*.tmp"))


def test_graph_refresh_requires_timestamp_before_mutation(tmp_path: Path) -> None:
    repo, config_path, vault, _tool_root = _repo(tmp_path)
    with pytest.raises(FailureMemoryError) as caught:
        refresh_project(
            action="graph",
            config_path=config_path,
            repository_root=repo,
            global_vault=vault,
        )
    assert caught.value.code == "generated_at_required"
    assert not (repo / "dev/knowledge/graph/local_state.yaml").exists()
    assert not (repo / "dev/knowledge/graph/graph.json").exists()


def test_lessons_status_and_disposable_clean(tmp_path: Path) -> None:
    repo, config_path, vault, _tool_root = _repo(tmp_path)
    result = refresh_project(
        action="lessons",
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
    )
    assert result["stages"]["lessons"]["status"] == "written"
    status_result = refresh_project(
        action="status",
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
    )
    assert status_result["artifacts"]["routes"]["exists"] is True
    # Numerix compatibility policy commits lessons/routes, so clean preserves them.
    cleaned = refresh_project(
        action="clean",
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
    )
    assert cleaned["removed"] == []
    assert (repo / "dev/knowledge/generated/failure_routes.json").exists()


def test_stale_dead_pid_lock_recovers(tmp_path: Path) -> None:
    lock = tmp_path / "lock"
    lock.write_text(json.dumps({"pid": 99999999, "token": "dead", "version": 1}))
    with ProjectLock(lock, timeout_seconds=0.1):
        assert lock.exists()
    assert not lock.exists()


@pytest.mark.skipif(
    os.environ.get("AKMS_REPO2MD_E2E") != "1",
    reason="real pinned repo2md smoke is explicitly opt-in",
)
def test_pinned_real_tool_preflight(tmp_path: Path) -> None:
    personal_root = tmp_path
    tool = Path(
        os.environ.get("AKMS_REPO2MD_COMMAND", "~/.local/bin/repo-wiki")
    ).expanduser()
    config_path = tmp_path / "failure-memory.toml"
    text = CONFIG_SOURCE.read_text(encoding="utf-8")
    text = text.replace(
        'repo2md_command = ["repo-wiki"]', f'repo2md_command = ["{tool}"]'
    )
    config_path.write_text(text, encoding="utf-8")
    old = os.environ.get("AKMS_REPO2MD_ROOT")
    os.environ["AKMS_REPO2MD_ROOT"] = str(Path("/opt/example/repo2md"))
    try:
        result = preflight(
            config=load_project_config(config_path), repository_root=personal_root
        )
    finally:
        if old is None:
            os.environ.pop("AKMS_REPO2MD_ROOT", None)
        else:
            os.environ["AKMS_REPO2MD_ROOT"] = old
    assert result["repo2md"]["commit"] == "478be35c76325ab1ccea48b69a5ea25b095952a6"


def test_graph_metadata_global_vault_is_portable_across_mount_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression test for the provider_fingerprint_is_not_portable finding.

    ``akms.graph.build_graph`` writes the fully-resolved absolute vault path
    into ``graph.json``'s ``graph.global_vault``. Before this fix,
    ``_finalize_graph_payload`` normalized ``generated_at`` and ``repo_id``
    but left ``global_vault`` untouched, so two builds against the SAME
    logical vault content (both empty here) mounted at two DIFFERENT
    absolute paths produced two different ``graph_sha256`` values -- and
    therefore two different ``result.fingerprint`` /
    ``result.resolution_fingerprint`` / ``resolution.graph_version`` values,
    which would make WWW's required stale-fingerprint check fire falsely on
    nothing but a different machine, container, or per-run temp mount.

    This asserts the actual property downstream consumers depend on: build twice from
    the identical logical state with the vault mounted at two different
    absolute paths, and the published graph.json (and therefore every
    fingerprint derived from it) must be byte-identical. A companion
    same-vault-twice build proves the fix did not reintroduce a wall-clock
    dependency (generated_at is still the explicit, caller-supplied value).
    """
    monkeypatch.setattr(
        "akms_failure_memory.refresh.run_mirror_provider", _successful_mirror
    )
    repo, config_path, vault_a, _tool_root = _repo(tmp_path)

    # A second, differently-rooted, empty vault: same (empty) logical
    # content as vault_a, but a genuinely different absolute path.
    vault_b = tmp_path / "an-entirely-different" / "mount-point" / "for-vault-b"
    vault_b.mkdir(parents=True)
    assert str(vault_a) != str(vault_b)

    graph_path = repo / "dev/knowledge/graph/graph.json"
    generated_at = "2026-08-17T00:00:00+00:00"

    refresh_project(
        action="graph",
        config_path=config_path,
        repository_root=repo,
        global_vault=vault_a,
        generated_at=generated_at,
    )
    bytes_a = graph_path.read_bytes()
    metadata_a = json.loads(bytes_a)["graph"]

    refresh_project(
        action="graph",
        config_path=config_path,
        repository_root=repo,
        global_vault=vault_b,
        generated_at=generated_at,
    )
    bytes_b = graph_path.read_bytes()
    metadata_b = json.loads(bytes_b)["graph"]

    # The published metadata must not contain either raw absolute path --
    # that is the whole point of canonicalizing it.
    assert str(vault_a) not in json.dumps(metadata_a)
    assert str(vault_b) not in json.dumps(metadata_b)
    assert metadata_a["global_vault"] == metadata_b["global_vault"]

    assert bytes_a == bytes_b, (
        "graph.json must be byte-identical across two different absolute "
        "vault mount paths with identical (empty) vault content"
    )
    assert hashlib.sha256(bytes_a).hexdigest() == hashlib.sha256(bytes_b).hexdigest()

    # Companion property: two rebuilds against the SAME vault, same
    # explicit generated_at, remain identical too (no reintroduced
    # wall-clock dependency).
    refresh_project(
        action="graph",
        config_path=config_path,
        repository_root=repo,
        global_vault=vault_a,
        generated_at=generated_at,
    )
    bytes_a_again = graph_path.read_bytes()
    assert bytes_a_again == bytes_a


def test_home_relative_global_vault_collapses_to_tilde_form(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A vault under $HOME canonicalizes to the frozen schema's own
    documented example shape (``~/.claude/akms/nodes`` in
    docs/specification/AKMS_v2_specification.md §8), not to the
    external-vault marker -- so a real, non-test deployment using the
    documented default vault location still gets a meaningful, and still
    portable, value rather than an opaque placeholder.
    """
    from akms_failure_memory.refresh import _canonical_global_vault

    home = str(Path.home())
    assert _canonical_global_vault(home) == "~"
    assert (
        _canonical_global_vault(home + "/.claude/akms/nodes") == "~/.claude/akms/nodes"
    )
    assert (
        _canonical_global_vault("/some/other/machine-specific/path")
        == "<external-global-vault>"
    )
    assert _canonical_global_vault(None) == "<external-global-vault>"
