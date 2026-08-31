from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path

import pytest

from akms_failure_memory.compiler import (
    compile_registry,
    run_compiler,
    serialize_node,
    serialize_routes,
)
from akms_failure_memory.config import load_project_config
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.locks import ProjectLock


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONFIG = PACKAGE_ROOT / "tests/fixtures/project_configs/numerixweave.toml"
SECOND_CONFIG = PACKAGE_ROOT / "tests/fixtures/project_configs/second_project.toml"
SOURCE = PACKAGE_ROOT / "tests/fixtures/numerixweave_phase1/source_registry.json"


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    registry = repo / "dev/lessons_from_failing.json"
    registry.parent.mkdir(parents=True)
    registry.write_bytes(SOURCE.read_bytes())
    for relative in (
        "apps/tifem/src/tifem/Elements/CohesiveInterface.py",
        "apps/tifem/tests/test_cohesive_history_idempotent.py",
    ):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    return repo


def test_compatibility_fixture_exact_bytes(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    compilation = compile_registry(load_project_config(CONFIG), repo)
    assert (
        compilation.source_sha256
        == "729bdc646b4fec9b2f868b52f060e2f428d700375c1230d7f03c392c3ba77946"
    )
    assert [node.node_id for node in compilation.nodes] == [
        "nw-failure-l900",
        "nw-failure-l901",
    ]
    first = serialize_node(compilation.nodes[0])
    assert b"Fixture prose must be copied verbatim, not summarized." in first
    assert (
        hashlib.sha256(first).hexdigest()
        == "20ce6a390469f1835fd33b6c4041d00c8e138bca4edacebb1c8d3149b52094e7"
    )
    assert (
        hashlib.sha256(serialize_node(compilation.nodes[1])).hexdigest()
        == "f883f138959b0b132aa5f37130d9405b4c62e370a1ad527ad173d9addec9a391"
    )
    assert (
        hashlib.sha256(serialize_routes(compilation.adapted_routes)).hexdigest()
        == "8511ce591438117df146bb75e6e9eac88ef9251cbbf1bc160de20e36e3966171"
    )


def test_atomic_check_prune(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    global_vault = tmp_path / "global"
    global_vault.mkdir()
    result = run_compiler(
        config_path=CONFIG, repository_root=repo, global_vault=global_vault
    )
    assert result["status"] == "written"
    assert (
        run_compiler(
            config_path=CONFIG,
            repository_root=repo,
            global_vault=global_vault,
            mode="check",
        )["status"]
        == "clean"
    )
    generated = repo / "dev/knowledge/local-nodes/generated/failure-lessons"
    stale = generated / "nw-failure-l999.md"
    stale.write_bytes(
        (generated / "nw-failure-l900.md")
        .read_bytes()
        .replace(b"nw-failure-l900", b"nw-failure-l999")
    )
    assert (
        run_compiler(
            config_path=CONFIG,
            repository_root=repo,
            global_vault=global_vault,
            mode="check",
        )["status"]
        == "drift"
    )
    run_compiler(config_path=CONFIG, repository_root=repo, global_vault=global_vault)
    assert not stale.exists()


def test_synthetic_project_uses_distinct_namespace_and_layout(tmp_path: Path) -> None:
    repo = tmp_path / "synthetic"
    registry = repo / ".failure-memory/lessons.json"
    registry.parent.mkdir(parents=True)
    value = json.loads(SOURCE.read_text(encoding="utf-8"))
    value["lessons"][0]["id"] = "L0900"
    value["lessons"][0]["related"] = ["L0901"]
    value["lessons"][0]["location"]["file"] = "src/a.py"
    value["lessons"][0]["found_by"]["trigger"] = "tests/test_a.py::test_a"
    value["lessons"][0]["prevention"] = "tests/test_a.py prevents recurrence."
    value["lessons"][1]["id"] = "L0901"
    value["lessons"][1]["location"]["file"] = "src/b.py"
    value["lessons"][1]["found_by"]["trigger"] = "tests/test_b.py::test_b"
    value["lessons"][1]["prevention"] = "tests/test_b.py prevents recurrence."
    registry.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    for relative in ("src/a.py", "src/b.py", "tests/test_a.py", "tests/test_b.py"):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    compilation = compile_registry(load_project_config(SECOND_CONFIG), repo)
    assert [node.node_id for node in compilation.nodes] == [
        "demo-memory-l0900",
        "demo-memory-l0901",
    ]
    assert all("nw-" not in node.node_id for node in compilation.nodes)
    assert set(compilation.canonical_routes["by_path"]) == {
        "src/a.py",
        "src/b.py",
        "tests/test_a.py",
        "tests/test_b.py",
    }


def test_unicode_and_yaml_sensitive_prose_is_verbatim(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    registry = repo / "dev/lessons_from_failing.json"
    value = json.loads(registry.read_text(encoding="utf-8"))
    lesson = value["lessons"][0]
    lesson["location"]["line_hint"] = 'Résumé: 日本語 "YAML" # value'
    lesson["symptom"] = 'Quoted: "verbatim" — café 日本語\nSecond line: # prose'
    lesson["notes"] = "Keep Ω and emoji 🧪 verbatim."
    registry.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    node = compile_registry(load_project_config(CONFIG), repo).nodes[0]
    rendered = serialize_node(node)
    assert lesson["symptom"].encode("utf-8") in rendered
    assert lesson["notes"].encode("utf-8") in rendered
    assert "line-hint-resume-yaml-value" in node.frontmatter["tags"]


def test_invalid_registry_preserves_previous_outputs(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    global_vault = tmp_path / "global"
    global_vault.mkdir()
    run_compiler(config_path=CONFIG, repository_root=repo, global_vault=global_vault)
    output = repo / "dev/knowledge/generated/failure_routes.json"
    before = output.read_bytes()
    registry = repo / "dev/lessons_from_failing.json"
    value = json.loads(registry.read_text())
    value["lessons"][1]["id"] = "L900"
    registry.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(FailureMemoryError, match="Duplicate lesson ID"):
        run_compiler(
            config_path=CONFIG, repository_root=repo, global_vault=global_vault
        )
    assert output.read_bytes() == before


def test_semicolon_and_near_path_rejected(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    registry = repo / "dev/lessons_from_failing.json"
    value = json.loads(registry.read_text())
    value["lessons"][0]["location"]["file"] += "; apps/other.py"
    registry.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(FailureMemoryError, match="must not use"):
        compile_registry(load_project_config(CONFIG), repo)


def test_generated_directory_symlink_is_rejected_before_external_write(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    vault = tmp_path / "global"
    vault.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    generated = repo / "dev/knowledge/local-nodes/generated/failure-lessons"
    generated.parent.mkdir(parents=True)
    generated.symlink_to(outside, target_is_directory=True)
    with pytest.raises(FailureMemoryError, match="symlink"):
        run_compiler(config_path=CONFIG, repository_root=repo, global_vault=vault)
    assert list(outside.iterdir()) == []
    assert not (repo / "dev/knowledge/generated/failure_routes.json").exists()


def test_mid_publication_failure_restores_every_prior_output(
    tmp_path: Path, monkeypatch
) -> None:
    repo = _repo(tmp_path)
    vault = tmp_path / "global"
    vault.mkdir()
    run_compiler(config_path=CONFIG, repository_root=repo, global_vault=vault)
    generated = repo / "dev/knowledge/local-nodes/generated/failure-lessons"
    stale = generated / "nw-failure-l999.md"
    stale.write_bytes(
        (generated / "nw-failure-l900.md")
        .read_bytes()
        .replace(b"nw-failure-l900", b"nw-failure-l999")
    )
    tracked = [
        *sorted(generated.glob("*.md")),
        repo / "dev/knowledge/generated/failure_routes.json",
    ]
    before = {path: path.read_bytes() for path in tracked}
    registry = repo / "dev/lessons_from_failing.json"
    value = json.loads(registry.read_text())
    value["lessons"][0]["symptom"] = "Changed for transactional publication."
    registry.write_text(json.dumps(value), encoding="utf-8")

    import akms_failure_memory.compiler as compiler_module

    real_replace = compiler_module._atomic_replace
    calls = 0

    def fail_second(root: Path, path: Path, content: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected mid-publication failure")
        real_replace(root, path, content)

    monkeypatch.setattr(compiler_module, "_atomic_replace", fail_second)
    with pytest.raises(OSError, match="injected"):
        run_compiler(config_path=CONFIG, repository_root=repo, global_vault=vault)
    assert {path: path.read_bytes() for path in tracked} == before


def test_direct_compile_uses_project_lock(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    vault = tmp_path / "global"
    vault.mkdir()
    config_path = repo / "failure-memory.toml"
    config_path.write_text(
        CONFIG.read_text().replace("timeout_seconds = 120", "timeout_seconds = 0.05")
    )
    config = load_project_config(config_path)
    acquired = threading.Event()
    release = threading.Event()

    def hold_lock() -> None:
        with ProjectLock(config.resolve(repo, "lock")):
            acquired.set()
            release.wait(timeout=2)

    thread = threading.Thread(target=hold_lock)
    thread.start()
    assert acquired.wait(timeout=1)
    try:
        with pytest.raises(FailureMemoryError, match="Timed out"):
            run_compiler(
                config_path=config_path,
                repository_root=repo,
                global_vault=vault,
            )
    finally:
        release.set()
        thread.join(timeout=2)
