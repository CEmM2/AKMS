from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from akms.graph.build_graph import build_graph

from akms_failure_memory.compiler import run_compiler
from akms_failure_memory.config import load_project_config
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.provider import resolve_provider, validate_fingerprint
from akms_failure_memory.refresh import _finalize_graph_payload


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONFIG_SOURCE = PACKAGE_ROOT / "tests/fixtures/project_configs/numerixweave.toml"
REGISTRY_SOURCE = (
    PACKAGE_ROOT / "tests/fixtures/numerixweave_phase1/source_registry.json"
)


def _prepare(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    registry = repo / "dev/lessons_from_failing.json"
    registry.parent.mkdir(parents=True)
    registry.write_bytes(REGISTRY_SOURCE.read_bytes())
    for relative in (
        "apps/tifem/src/tifem/Elements/CohesiveInterface.py",
        "tools/knowledge/refresh.py",
    ):
        source = repo / relative
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("# provider fixture\n", encoding="utf-8")
    config_path = repo / "failure-memory.toml"
    config_path.write_bytes(CONFIG_SOURCE.read_bytes())
    vault = tmp_path / "global-vault"
    vault.mkdir()
    run_compiler(
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
        mode="write",
    )
    config = load_project_config(config_path)
    # Publish CANONICALLY (build to scratch, then through the project-owned
    # finalizer), exactly like refresh_project(action="graph"). Raw build_graph
    # output carries the scratch directory's basename as repo_id, which
    # validate_publication correctly refuses as a foreign identity.
    scratch = tmp_path / "graph.staging.json"
    build_graph(
        config.resolve(repo, "akms_repo_root"),
        global_vault=vault,
        output_path=scratch,
        strict=True,
    )
    graph_path = config.resolve(repo, "graph")
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_bytes(
        _finalize_graph_payload(
            json.loads(scratch.read_text(encoding="utf-8")),
            config=config,
            generated_at="2026-08-17T00:00:00+00:00",
        )
    )
    return repo, config_path, vault


def _request(
    *,
    invocation_id: str = "invoke-1",
    mode: str = "pre-task",
    role: str = "implementer",
    declared_paths: list[str] | None = None,
    changed_paths: list[str] | None = None,
    baseline: str = "base-001",
    refresh_policy: str = "never",
) -> dict:
    return {
        "schema_version": "failure-memory-provider-request/v1",
        "invocation_id": invocation_id,
        "repository_id": "NumerixWeave",
        "baseline": baseline,
        "mode": mode,
        "role": role,
        "declared_paths": declared_paths
        or ["apps/tifem/src/tifem/Elements/CohesiveInterface.py"],
        "changed_paths": changed_paths or [],
        "base": None,
        "head": None,
        "refresh_policy": refresh_policy,
        "output_dir": "dev/knowledge/provider",
        "task": {
            "task_id": "F3-provider-fixture",
            "phase": 3,
            "title": "Resolve a deterministic failure lesson",
            "objective": "Exercise the provider contract.",
            "scope": [],
            "deliverables": [],
            "akms_tags": [],
        },
    }


def test_pre_task_exact_near_miss_and_isolated_outputs(tmp_path: Path) -> None:
    repo, config, _vault = _prepare(tmp_path)
    exact = resolve_provider(
        config_path=config,
        repository_root=repo,
        request_source=_request(),
    )
    required = [r for r in exact["records"] if r["selection_class"] == "required"]
    assert [record["node_id"] for record in required] == ["nw-failure-l900"]
    assert required[0]["reasons"]
    assert Path(repo, exact["artifacts"]["result"]).is_file()
    assert Path(repo, exact["artifacts"]["loadout"]).is_file()

    near = resolve_provider(
        config_path=config,
        repository_root=repo,
        request_source=_request(
            invocation_id="near-miss",
            declared_paths=["apps/tifem/src/tifem/Elements/CohesiveInterfac.py"],
        ),
    )
    assert not [r for r in near["records"] if r["selection_class"] == "required"]
    assert exact["artifacts"]["result"] != near["artifacts"]["result"]


def test_post_diff_adds_required_and_unrelated_change_is_excluded(
    tmp_path: Path,
) -> None:
    repo, config, _vault = _prepare(tmp_path)
    result = resolve_provider(
        config_path=config,
        repository_root=repo,
        request_source=_request(
            mode="post-diff",
            role="code_reviewer",
            changed_paths=["tools/knowledge/refresh.py", "docs/unrelated.md"],
        ),
    )
    assert result["diagnostics"]["post_diff_only_required"] == ["nw-failure-l901"]
    required = {
        r["node_id"] for r in result["records"] if r["selection_class"] == "required"
    }
    assert required == {"nw-failure-l900", "nw-failure-l901"}


def test_empty_post_diff_falls_back_to_declared_scope(tmp_path: Path) -> None:
    repo, config, _vault = _prepare(tmp_path)
    result = resolve_provider(
        config_path=config,
        repository_root=repo,
        request_source=_request(mode="post-diff", role="physics_reviewer"),
        write_artifacts=False,
    )
    assert result["diagnostics"]["empty_diff_fallback"] is True
    assert "nw-failure-l900" in {r["node_id"] for r in result["records"]}


def test_fingerprint_covers_request_routes_graph_role_diff_and_config(
    tmp_path: Path,
) -> None:
    repo, config_path, _vault = _prepare(tmp_path)
    base_request = _request(mode="post-diff", role="code_reviewer")

    def fingerprint(request: dict) -> str:
        return resolve_provider(
            config_path=config_path,
            repository_root=repo,
            request_source=request,
            write_artifacts=False,
        )["fingerprint"]

    original = fingerprint(base_request)
    changed_baseline = deepcopy(base_request)
    changed_baseline["baseline"] = "base-002"
    assert fingerprint(changed_baseline) != original
    changed_role = deepcopy(base_request)
    changed_role["role"] = "physics_reviewer"
    assert fingerprint(changed_role) != original
    changed_diff = deepcopy(base_request)
    changed_diff["changed_paths"] = ["tools/knowledge/refresh.py"]
    assert fingerprint(changed_diff) != original

    config = load_project_config(config_path)
    routes_path = config.resolve(repo, "routes")
    routes = json.loads(routes_path.read_text())
    routes["source_hash"] = "sha256:" + "1" * 64
    routes_path.write_text(json.dumps(routes, sort_keys=True, indent=2) + "\n")
    route_fingerprint = fingerprint(base_request)
    assert route_fingerprint != original

    graph_path = config.resolve(repo, "graph")
    graph = json.loads(graph_path.read_text())
    graph["provider_fixture_marker"] = "changed"
    graph_path.write_text(json.dumps(graph, sort_keys=True, indent=2) + "\n")
    graph_fingerprint = fingerprint(base_request)
    assert graph_fingerprint != route_fingerprint

    config_text = config_path.read_text().replace(
        'owner = "NumerixWeave maintainers"',
        'owner = "NumerixWeave release maintainers"',
    )
    config_path.write_text(config_text)
    assert fingerprint(base_request) != graph_fingerprint


def test_stale_validation_and_subprocess_cli_without_harness(tmp_path: Path) -> None:
    repo, config, _vault = _prepare(tmp_path)
    request_path = repo / "request.json"
    request_path.write_text(json.dumps(_request(), sort_keys=True), encoding="utf-8")
    result = resolve_provider(
        config_path=config,
        repository_root=repo,
        request_source=request_path,
    )
    result_path = repo / result["artifacts"]["result"]
    current = validate_fingerprint(
        config_path=config,
        repository_root=repo,
        request_source=request_path,
        result_path=result_path,
    )
    assert current == {
        "status": "current",
        "stale": False,
        "recorded_fingerprint": result["fingerprint"],
        "current_fingerprint": result["fingerprint"],
    }
    changed = _request(baseline="different")
    request_path.write_text(json.dumps(changed, sort_keys=True), encoding="utf-8")
    assert (
        validate_fingerprint(
            config_path=config,
            repository_root=repo,
            request_source=request_path,
            result_path=result_path,
        )["status"]
        == "stale"
    )

    changed["invocation_id"] = "subprocess"
    request_path.write_text(json.dumps(changed, sort_keys=True), encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(PACKAGE_ROOT / "src"), str(PACKAGE_ROOT.parent / "AKMS/src")]
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "akms_failure_memory.cli",
            "resolve",
            "--config",
            str(config),
            "--repo",
            str(repo),
            "--request",
            str(request_path),
        ],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["status"] == "ok"
    assert (
        "whatter"
        not in (PACKAGE_ROOT / "src/akms_failure_memory/provider.py")
        .read_text()
        .lower()
    )


def test_provider_schemas_are_closed() -> None:
    for name in ("provider-request.v1.json", "provider-result.v1.json"):
        schema = json.loads((PACKAGE_ROOT / "schemas" / name).read_text())
        assert schema["additionalProperties"] is False


def test_require_current_rejects_stale_inputs_while_never_reads_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, config_path, vault = _prepare(tmp_path)
    config = load_project_config(config_path)
    generated = next(config.resolve(repo, "generated_nodes").glob("*.md"))
    generated.write_text(generated.read_text() + "\nstale\n", encoding="utf-8")
    assert (
        resolve_provider(
            config_path=config_path,
            repository_root=repo,
            request_source=_request(refresh_policy="never"),
            write_artifacts=False,
        )["status"]
        == "ok"
    )
    monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(vault))
    monkeypatch.setattr("akms_failure_memory.provider.preflight", lambda **_kwargs: {})
    with pytest.raises(FailureMemoryError, match="compiler outputs are stale"):
        resolve_provider(
            config_path=config_path,
            repository_root=repo,
            request_source=_request(refresh_policy="require-current"),
            write_artifacts=False,
        )

    run_compiler(
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
        mode="write",
    )
    graph_path = config.resolve(repo, "graph")
    graph = json.loads(graph_path.read_text())
    graph["graph"]["node_count"] += 1
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    with pytest.raises(FailureMemoryError, match="graph is stale"):
        resolve_provider(
            config_path=config_path,
            repository_root=repo,
            request_source=_request(refresh_policy="require-current"),
            write_artifacts=False,
        )
