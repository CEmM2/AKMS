from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from akms_failure_memory.compiler import run_compiler
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.record import add_lesson


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONFIG_SOURCE = PACKAGE_ROOT / "tests/fixtures/project_configs/numerixweave.toml"
REGISTRY_SOURCE = (
    PACKAGE_ROOT / "tests/fixtures/numerixweave_phase1/source_registry.json"
)


def _repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    registry = repo / "dev/lessons_from_failing.json"
    registry.parent.mkdir(parents=True)
    registry.write_bytes(REGISTRY_SOURCE.read_bytes())
    config = repo / "failure-memory.toml"
    config.write_bytes(CONFIG_SOURCE.read_bytes())
    vault = tmp_path / "global"
    vault.mkdir()
    return repo, config, vault


def _request(index: int = 1) -> dict:
    return {
        "date_found": "2026-08-11",
        "date_found_precision": "exact",
        "date_fixed": "2026-08-11",
        "date_fixed_precision": "exact",
        "location": {
            "area": "tool",
            "package": "demo",
            "module": "demo.module",
            "file": f"tools/demo_{index}.py",
            "symbol": "run",
            "line_hint": f"recording {index}",
        },
        "found_by": {
            "type": "test",
            "trigger": f"tests/test_demo_{index}.py::test_demo",
        },
        "symptom": "Observed failure.",
        "root_cause": "Known cause.",
        "fix": "Known fix.",
        "prevention": f"tests/test_demo_{index}.py prevents recurrence.",
        "references": {"commit": "abc123", "issue": "", "pr": "", "plan": ""},
        "related": ["L900"],
    }


def _request_file(repo: Path, request: dict, name: str = "request.json") -> Path:
    path = repo / name
    path.write_text(json.dumps(request), encoding="utf-8")
    return path


def test_machine_record_and_manual_edit_use_same_schema(tmp_path: Path) -> None:
    repo, config, vault = _repo(tmp_path)
    result = add_lesson(
        config_path=config,
        repository_root=repo,
        global_vault=vault,
        request_path=_request_file(repo, _request()),
    )
    assert result["record"]["id"] == "L902"
    assert result["promotion"] == "not-performed"
    assert result["affected_outputs"]
    manual = json.loads((repo / "dev/lessons_from_failing.json").read_text())
    manual["lessons"].append({"id": "L903", **_request(3)})
    (repo / "dev/lessons_from_failing.json").write_text(
        json.dumps(manual), encoding="utf-8"
    )
    assert (
        run_compiler(
            config_path=config,
            repository_root=repo,
            global_vault=vault,
            mode="validate",
        )["status"]
        == "valid"
    )


def test_interactive_record_produces_canonical_shape(tmp_path: Path) -> None:
    repo, config, vault = _repo(tmp_path)
    request = _request()
    answers = iter(
        [
            request["date_found"],
            request["date_found_precision"],
            request["date_fixed"],
            request["date_fixed_precision"],
            request["location"]["area"],
            request["location"]["package"],
            request["location"]["module"],
            request["location"]["file"],
            request["location"]["symbol"],
            request["location"]["line_hint"],
            request["found_by"]["type"],
            request["found_by"]["trigger"],
            request["symptom"],
            request["root_cause"],
            request["fix"],
            request["prevention"],
            request["references"]["commit"],
            request["references"]["issue"],
            request["references"]["pr"],
            request["references"]["plan"],
            "L900",
            "",
        ]
    )
    result = add_lesson(
        config_path=config,
        repository_root=repo,
        global_vault=vault,
        interactive=True,
        input_fn=lambda _prompt: next(answers),
    )
    expected = {"id", *request.keys()}
    assert set(result["record"]) == expected


def test_concurrent_recorders_allocate_distinct_ids(tmp_path: Path) -> None:
    repo, config, vault = _repo(tmp_path)
    paths = [
        _request_file(repo, _request(index), f"request-{index}.json")
        for index in (1, 2)
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda path: add_lesson(
                    config_path=config,
                    repository_root=repo,
                    global_vault=vault,
                    request_path=path,
                ),
                paths,
            )
        )
    assert {result["record"]["id"] for result in results} == {"L902", "L903"}


def test_invalid_related_id_fails_before_publication(tmp_path: Path) -> None:
    repo, config, vault = _repo(tmp_path)
    before = (repo / "dev/lessons_from_failing.json").read_bytes()
    request = _request()
    request["related"] = ["L999"]
    with pytest.raises(FailureMemoryError, match="unknown related"):
        add_lesson(
            config_path=config,
            repository_root=repo,
            global_vault=vault,
            request_path=_request_file(repo, request),
        )
    assert (repo / "dev/lessons_from_failing.json").read_bytes() == before


def test_recorder_rolls_back_registry_and_all_outputs_on_publish_failure(
    tmp_path: Path, monkeypatch
) -> None:
    repo, config, vault = _repo(tmp_path)
    run_compiler(
        config_path=config, repository_root=repo, global_vault=vault, mode="write"
    )
    registry = repo / "dev/lessons_from_failing.json"
    generated = repo / "dev/knowledge/local-nodes/generated/failure-lessons"
    routes = repo / "dev/knowledge/generated/failure_routes.json"
    before_registry = registry.read_bytes()
    before_outputs = {
        path: path.read_bytes() for path in [*sorted(generated.glob("*.md")), routes]
    }

    import akms_failure_memory.compiler as compiler_module

    real_replace = compiler_module._atomic_replace
    calls = 0

    def fail_second(root: Path, path: Path, content: bytes) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected recorder publication failure")
        real_replace(root, path, content)

    monkeypatch.setattr(compiler_module, "_atomic_replace", fail_second)
    with pytest.raises(OSError, match="injected recorder"):
        add_lesson(
            config_path=config,
            repository_root=repo,
            global_vault=vault,
            request_path=_request_file(repo, _request()),
        )
    assert registry.read_bytes() == before_registry
    assert {path: path.read_bytes() for path in before_outputs} == before_outputs
    assert not (generated / "nw-failure-l902.md").exists()


def test_direct_compile_cannot_interleave_with_recorder(
    tmp_path: Path, monkeypatch
) -> None:
    repo, config, vault = _repo(tmp_path)
    config.write_text(
        config.read_text().replace("timeout_seconds = 120", "timeout_seconds = 0.05")
    )
    request_path = _request_file(repo, _request())
    entered = threading.Event()
    release = threading.Event()

    import akms_failure_memory.compiler as compiler_module

    real_publish = compiler_module._publish_transaction

    def block_publish(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return real_publish(*args, **kwargs)

    monkeypatch.setattr(compiler_module, "_publish_transaction", block_publish)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            add_lesson,
            config_path=config,
            repository_root=repo,
            global_vault=vault,
            request_path=request_path,
        )
        assert entered.wait(2)
        try:
            with pytest.raises(FailureMemoryError, match="Timed out"):
                run_compiler(
                    config_path=config,
                    repository_root=repo,
                    global_vault=vault,
                    mode="write",
                )
        finally:
            release.set()
        assert future.result(timeout=2)["record"]["id"] == "L902"
