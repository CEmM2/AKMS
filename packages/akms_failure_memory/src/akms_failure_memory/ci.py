"""Hermetic reusable CI gate for one configured failure-memory project."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from akms_failure_memory.compiler import run_compiler
from akms_failure_memory.config import load_project_config
from akms_failure_memory.errors import FailureMemoryError


_COMPATIBILITY_DIGESTS = {
    "source_registry.json": "729bdc646b4fec9b2f868b52f060e2f428d700375c1230d7f03c392c3ba77946",
    "nw-failure-l900.md": "20ce6a390469f1835fd33b6c4041d00c8e138bca4edacebb1c8d3149b52094e7",
    "nw-failure-l901.md": "f883f138959b0b132aa5f37130d9405b4c62e370a1ad527ad173d9addec9a391",
    "failure_routes.json": "8511ce591438117df146bb75e6e9eac88ef9251cbbf1bc160de20e36e3966171",
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _asset_paths() -> tuple[Path, Path, Path]:
    source_root = Path(__file__).resolve().parents[2]
    if (source_root / "schemas/project-config.schema.json").is_file():
        return (
            source_root / "schemas",
            source_root / "tests/fixtures/project_configs/numerixweave.toml",
            source_root / "tests/fixtures/numerixweave_phase1/source_registry.json",
        )
    shared = Path(sys.prefix) / "share/akms-failure-memory"
    return (
        shared / "schemas",
        shared / "fixtures/numerixweave.toml",
        shared / "fixtures/source_registry.json",
    )


def release_source_digest(package_root: str | Path) -> str:
    """Digest the immutable release inputs while excluding the circular pin."""
    root = Path(package_root).resolve(strict=True)
    files = [root / "README.md", root / "CHANGELOG.md", root / "pyproject.toml"]
    for relative_root, patterns in (
        ("src/akms_failure_memory", ("*.py",)),
        ("schemas", ("*.json",)),
        ("docs", ("*.md",)),
        ("templates", ("*",)),
        ("tests/fixtures", ("*.json", "*.toml")),
    ):
        directory = root / relative_root
        for pattern in patterns:
            files.extend(path for path in directory.rglob(pattern) if path.is_file())
    digest = hashlib.sha256()
    for path in sorted(set(files), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _check_schemas(schema_root: Path) -> dict[str, str]:
    identities = {}
    expected = {
        "project-config.schema.json": "failure-memory-project/v1",
        "provider-request.v1.json": "failure-memory-provider-request/v1",
        "provider-result.v1.json": "failure-memory-provider-result/v1",
    }
    for name, contract in expected.items():
        path = schema_root / name
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise FailureMemoryError(
                f"Invalid bundled schema {name}: {exc}", code="contract_drift"
            ) from exc
        if schema.get("additionalProperties") is not False:
            raise FailureMemoryError(
                f"Bundled schema {name} is not closed", code="contract_drift"
            )
        serialized = json.dumps(schema, ensure_ascii=False, sort_keys=True)
        if contract not in serialized:
            raise FailureMemoryError(
                f"Bundled schema {name} lost {contract}", code="contract_drift"
            )
        identities[name] = _digest(path)
    return identities


def _check_compatibility_fixture(
    config_source: Path, registry_source: Path
) -> dict[str, str]:
    with tempfile.TemporaryDirectory(prefix="failure-memory-ci-") as temporary:
        repo = Path(temporary) / "repo"
        registry = repo / "dev/lessons_from_failing.json"
        registry.parent.mkdir(parents=True)
        shutil.copyfile(registry_source, registry)
        for relative in (
            "apps/tifem/src/tifem/Elements/CohesiveInterface.py",
            "apps/tifem/tests/test_cohesive_history_idempotent.py",
        ):
            source = repo / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            source.touch()
        config_path = repo / "failure-memory.toml"
        shutil.copyfile(config_source, config_path)
        vault = Path(temporary) / "vault"
        vault.mkdir()
        run_compiler(
            config_path=config_path,
            repository_root=repo,
            global_vault=vault,
            mode="write",
        )
        config = load_project_config(config_path)
        actual = {
            "source_registry.json": _digest(registry),
            "nw-failure-l900.md": _digest(
                config.resolve(repo, "generated_nodes") / "nw-failure-l900.md"
            ),
            "nw-failure-l901.md": _digest(
                config.resolve(repo, "generated_nodes") / "nw-failure-l901.md"
            ),
            "failure_routes.json": _digest(config.resolve(repo, "routes")),
        }
    if actual != _COMPATIBILITY_DIGESTS:
        raise FailureMemoryError(
            "Bundled Numerix compatibility fixture drifted",
            code="compatibility_drift",
            details={"actual": actual, "expected": _COMPATIBILITY_DIGESTS},
        )
    return actual


def ci_check(*, config_path: str | Path, repository_root: str | Path) -> dict[str, Any]:
    """Check config, registry, generated bytes, schemas, and compatibility fixture."""
    schema_root, fixture_config, fixture_registry = _asset_paths()
    config = load_project_config(config_path)
    root = Path(repository_root).resolve(strict=True)
    validation = run_compiler(
        config_path=config_path,
        repository_root=root,
        mode="validate",
    )
    with tempfile.TemporaryDirectory(prefix="failure-memory-vault-") as temporary:
        generated = run_compiler(
            config_path=config_path,
            repository_root=root,
            global_vault=Path(temporary),
            mode="check",
        )
    if generated.get("status") != "clean":
        raise FailureMemoryError(
            "Committed generated failure-memory outputs have drifted",
            code="generated_drift",
            details=generated,
        )
    return {
        "status": "ok",
        "config_fingerprint": config.fingerprint,
        "validation": validation,
        "generated": generated,
        "contracts": _check_schemas(schema_root),
        "compatibility_fixture": _check_compatibility_fixture(
            fixture_config, fixture_registry
        ),
    }


__all__ = ["ci_check", "release_source_digest"]
