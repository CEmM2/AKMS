"""Schema 2 directory registries. Contract v1 stays frozen and is not skipped here."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from akms_failure_memory.cli import main
from akms_failure_memory.compiler import (
    compile_registry,
    load_directory_registry,
)
from akms_failure_memory.config import load_project_config
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.locks import ProjectLock
from akms_failure_memory.project import render_project_config
from akms_failure_memory.record import add_lesson
from akms_failure_memory.registry_migrate import (
    _atomic_replace,
    migrate_registry,
    write_directory_registry,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONFIG = PACKAGE_ROOT / "tests/fixtures/project_configs/numerixweave.toml"
SOURCE = PACKAGE_ROOT / "tests/fixtures/numerixweave_phase1/source_registry.json"
PACK_V1 = PACKAGE_ROOT / "tests/fixtures/consumer_contract/v1"
PACK_V2 = PACKAGE_ROOT / "tests/fixtures/consumer_contract/v2"
BOTH_PATTERN = r"^(?:L[0-9]{3}|L[0-9]{8}-[0-9a-hjkmnp-tv-z]{4})$"
_FIELD_SPEC = {
    "id": "Stable lesson identifier.",
    "location": "Repository location for the failure.",
    "found_by": "Discovery mechanism and trigger.",
    "related": "Related lesson identifiers.",
}


def _lesson(
    lesson_id: str,
    *,
    related: list[str] | None = None,
    file: str = "tools/demo.py",
) -> dict:
    return {
        "id": lesson_id,
        "date_found": "2026-08-11",
        "date_found_precision": "exact",
        "date_fixed": "2026-08-11",
        "date_fixed_precision": "exact",
        "location": {
            "area": "tool",
            "package": "demo",
            "module": "demo.module",
            "file": file,
            "symbol": "",
            "line_hint": f"topic {lesson_id}",
        },
        "found_by": {"type": "test", "trigger": "recorded during a test"},
        "symptom": "Observed failure.",
        "root_cause": "Known cause.",
        "fix": "Known fix.",
        "prevention": "Do not repeat this failure.",
        "references": {"commit": "abc123", "issue": "", "pr": "", "plan": ""},
        "related": [] if related is None else related,
    }


def _request_file(root: Path, name: str, *, related: list[str]) -> Path:
    request = _lesson("ignored", related=related)
    del request["id"]
    path = root / name
    path.write_text(json.dumps(request), encoding="utf-8")
    return path


def _vault(tmp_path: Path) -> Path:
    vault = tmp_path / "global-vault"
    vault.mkdir(exist_ok=True)
    return vault


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _phase1_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    registry = repo / "dev/lessons_from_failing.json"
    registry.parent.mkdir(parents=True)
    registry.write_bytes(SOURCE.read_bytes())
    for relative in (
        "apps/tifem/src/tifem/Elements/CohesiveInterface.py",
        "tools/knowledge/refresh.py",
    ):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("anchor\n", encoding="utf-8")
    config = repo / "failure-memory.toml"
    config.write_bytes(CONFIG.read_bytes())
    return repo, config


def _config_text(
    repo: Path, *, schema_version: int, registry: str, pattern: str
) -> Path:
    text = CONFIG.read_text(encoding="utf-8")
    text = text.replace(
        'registry = "dev/lessons_from_failing.json"', f'registry = "{registry}"', 1
    )
    text = text.replace(
        "registry_schema_version = 1",
        f"registry_schema_version = {schema_version}",
        1,
    )
    text = text.replace('id_pattern = "^L[0-9]{3}$"', f'id_pattern = "{pattern}"', 1)
    repo.mkdir(parents=True, exist_ok=True)
    path = repo / "failure-memory.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _assert_same_lessons(before, after, config) -> None:
    assert before.source_schema_version == 1
    assert after.source_schema_version == 2
    assert before.source_sha256 != after.source_sha256
    assert [node.lesson_id for node in before.nodes] == [
        node.lesson_id for node in after.nodes
    ]
    prefix = config.compatibility["source_hash_prefix"]
    suffix = config.compatibility["source_hash_suffix"]
    for left, right in zip(before.nodes, after.nodes, strict=True):
        assert left.node_id == right.node_id
        assert left.frontmatter == right.frontmatter
        left_lines = left.content.splitlines()
        right_lines = right.content.splitlines()
        assert left_lines != right_lines
        assert [
            (old, new)
            for old, new in zip(left_lines, right_lines, strict=True)
            if old != new
        ] == [
            (
                f"{prefix}{before.source_sha256}{suffix}",
                f"{prefix}{after.source_sha256}{suffix}",
            )
        ]

    def canonical(routes: dict, digest: str, version: int) -> dict:
        assert routes["source_sha256"] == digest
        assert routes["source_schema_version"] == version
        cloned = json.loads(json.dumps(routes))
        cloned["source_sha256"] = None
        cloned["source_schema_version"] = None
        return cloned

    assert canonical(before.canonical_routes, before.source_sha256, 1) == canonical(
        after.canonical_routes, after.source_sha256, 2
    )

    def adapted(routes: dict, digest: str, version: int) -> dict:
        assert routes["source_hash"] == f"sha256:{digest}"
        cloned = json.loads(json.dumps(routes))
        cloned["source_hash"] = None
        for table in ("by_path", "by_symbol"):
            for selections in cloned[table].values():
                for selection in selections:
                    provenance = selection["provenance"]
                    assert provenance["source_sha256"] == digest
                    assert provenance["source_schema_version"] == version
                    provenance["source_sha256"] = None
                    provenance["source_schema_version"] = None
        return cloned

    assert adapted(before.adapted_routes, before.source_sha256, 1) == adapted(
        after.adapted_routes, after.source_sha256, 2
    )
    assert before.warnings == after.warnings


def _directory_digest(directory: Path) -> str:
    digest = hashlib.sha256()
    files = [path for path in directory.iterdir() if path.is_file()]
    for path in sorted(files, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def test_new_projects_stay_on_schema_1() -> None:
    rendered = render_project_config("demo-repo", "demo-failure").decode()
    assert "registry_schema_version = 1\n" in rendered
    assert 'registry = ".failure-memory/lessons.json"\n' in rendered
    assert "registry_schema_version = 2" not in rendered


@pytest.mark.parametrize(
    "assignment",
    [
        "registry_schema_version = true",
        'registry_schema_version = "1"',
        "registry_schema_version = [1]",
        "registry_schema_version = { n = 1 }",
    ],
)
def test_non_integer_registry_schema_version_is_not_internal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], assignment: str
) -> None:
    repo = tmp_path / "repo"
    config = _config_text(
        repo, schema_version=1, registry="dev/lessons.json", pattern=r"^L[0-9]{3}$"
    )
    text = config.read_text(encoding="utf-8")
    config.write_text(
        text.replace("registry_schema_version = 1", assignment, 1),
        encoding="utf-8",
    )
    with pytest.raises(
        FailureMemoryError, match="registry_schema_version must be 1 or 2"
    ) as exc_info:
        load_project_config(config)
    assert exc_info.value.code == "schema_version"

    exit_code = main(
        ["--json-errors", "doctor", "--config", str(config), "--repo", str(repo)]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["error"]["code"] == "schema_version"
    assert payload["error"]["message"] == "registry_schema_version must be 1 or 2"


def test_schema_2_is_accepted_and_schema_3_is_rejected(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    config = _config_text(
        repo, schema_version=2, registry="dev/lessons", pattern=r"^L[0-9]{3}$"
    )
    loaded = load_project_config(config)
    assert loaded.validation["registry_schema_version"] == 2
    text = config.read_text(encoding="utf-8").replace(
        "registry_schema_version = 2", "registry_schema_version = 3", 1
    )
    config.write_text(text, encoding="utf-8")
    with pytest.raises(
        FailureMemoryError, match="registry_schema_version must be 1 or 2"
    ) as exc_info:
        load_project_config(config)
    assert exc_info.value.code == "schema_version"


def test_v1_and_v2_compile_the_same_lessons(tmp_path: Path) -> None:
    repo, config_path = _phase1_repo(tmp_path)
    config = load_project_config(config_path)
    before = compile_registry(config, repo)
    assert (
        before.source_sha256
        == hashlib.sha256(
            (repo / "dev/lessons_from_failing.json").read_bytes()
        ).hexdigest()
    )
    checked = migrate_registry(
        config_path=config_path, repository_root=repo, to="2", check=True
    )
    assert checked["status"] == "checked"
    assert checked["would_write"] == "dev/lessons_from_failing"
    assert _snapshot(repo)  # populated
    untouched = _snapshot(repo)
    migrated = migrate_registry(
        config_path=config_path, repository_root=repo, to="2", check=False
    )
    assert migrated["status"] == "migrated"
    assert migrated["previous_registry"] == "dev/lessons_from_failing.json"
    assert migrated["registry"] == "dev/lessons_from_failing"
    assert (repo / "dev/lessons_from_failing.json").read_bytes() == untouched[
        "dev/lessons_from_failing.json"
    ]
    after_config = load_project_config(config_path)
    after = compile_registry(after_config, repo)
    _assert_same_lessons(before, after, config)
    registry = repo / "dev/lessons_from_failing"
    assert after.source_sha256 == _directory_digest(registry)
    assert "_registry.json" in {path.name for path in registry.iterdir()}
    assert (
        not (registry / "_registry.json").read_text(encoding="utf-8").count('"lessons"')
    )
    original_lines = CONFIG.read_text(encoding="utf-8").splitlines()
    updated_lines = config_path.read_text(encoding="utf-8").splitlines()
    changed = [
        (old, new)
        for old, new in zip(original_lines, updated_lines, strict=True)
        if old != new
    ]
    assert changed == [
        (
            'registry = "dev/lessons_from_failing.json"',
            'registry = "dev/lessons_from_failing"',
        ),
        ("registry_schema_version = 1", "registry_schema_version = 2"),
    ]


def test_migrate_check_writes_nothing_and_cli_rejects_other_targets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, config = _phase1_repo(tmp_path)
    before = _snapshot(repo)
    exit_code = main(
        [
            "registry",
            "migrate",
            "--to",
            "2",
            "--check",
            "--config",
            str(config),
            "--repo",
            str(repo),
        ]
    )
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "checked"
    assert _snapshot(repo) == before
    assert not (repo / "dev/knowledge").exists()

    exit_code = main(
        [
            "--json-errors",
            "registry",
            "migrate",
            "--to",
            "3",
            "--config",
            str(config),
            "--repo",
            str(repo),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["error"]["code"] == "usage"
    assert _snapshot(repo) == before


def test_migrate_refuses_schema_2_existing_destination_and_unclear_toml(
    tmp_path: Path,
) -> None:
    repo, config = _phase1_repo(tmp_path)
    migrate_registry(config_path=config, repository_root=repo, to="2")
    with pytest.raises(FailureMemoryError, match="schema 1") as exc_info:
        migrate_registry(config_path=config, repository_root=repo, to="2", check=True)
    assert exc_info.value.code == "registry_schema"

    fresh, fresh_config = _phase1_repo(tmp_path / "dest")
    (fresh / "dev/lessons_from_failing").mkdir()
    before = fresh_config.read_bytes()
    with pytest.raises(FailureMemoryError, match="already exists") as exc_info:
        migrate_registry(config_path=fresh_config, repository_root=fresh, to="2")
    assert exc_info.value.code == "file_exists"
    assert fresh_config.read_bytes() == before
    assert (fresh / "dev/lessons_from_failing.json").read_bytes() == SOURCE.read_bytes()

    commented, commented_config = _phase1_repo(tmp_path / "comment")
    text = commented_config.read_text(encoding="utf-8").replace(
        "registry_schema_version = 1",
        "registry_schema_version = 1 # pinned",
        1,
    )
    commented_config.write_text(text, encoding="utf-8")
    with pytest.raises(FailureMemoryError, match="simple assignment") as exc_info:
        migrate_registry(
            config_path=commented_config, repository_root=commented, to="2"
        )
    assert exc_info.value.code == "invalid_config"
    assert not (commented / "dev/lessons_from_failing").exists()
    assert "registry_schema_version = 1 # pinned" in commented_config.read_text(
        encoding="utf-8"
    )


def test_directory_reader_rejects_strays_and_shape_mismatches(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    registry = repo / "dev/lessons"
    config = _config_text(
        repo, schema_version=2, registry="dev/lessons", pattern=r"^L[0-9]{3}$"
    )
    write_directory_registry(
        registry, field_spec=_FIELD_SPEC, lessons=[_lesson("L001")]
    )
    loaded = load_project_config(config)
    assert [node.lesson_id for node in compile_registry(loaded, repo).nodes] == ["L001"]

    (registry / "notes.txt").write_text("nope\n", encoding="utf-8")
    with pytest.raises(FailureMemoryError, match="stray") as exc_info:
        compile_registry(loaded, repo)
    assert exc_info.value.code == "registry_schema"
    (registry / "notes.txt").unlink()

    (registry / ".keep").write_text("x\n", encoding="utf-8")
    with pytest.raises(FailureMemoryError, match="stray") as exc_info:
        compile_registry(loaded, repo)
    assert exc_info.value.code == "registry_schema"
    (registry / ".keep").unlink()

    (registry / "nested").mkdir()
    with pytest.raises(FailureMemoryError, match="stray") as exc_info:
        compile_registry(loaded, repo)
    assert exc_info.value.code == "registry_schema"
    (registry / "nested").rmdir()

    (registry / "L002.json").symlink_to(registry / "L001.json")
    with pytest.raises(FailureMemoryError, match="stray") as exc_info:
        compile_registry(loaded, repo)
    assert exc_info.value.code == "registry_schema"
    (registry / "L002.json").unlink()

    (registry / "nope.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(FailureMemoryError, match="Malformed lesson ID") as exc_info:
        compile_registry(loaded, repo)
    assert exc_info.value.code == "registry_id"
    (registry / "nope.json").unlink()

    mismatched = _lesson("L002")
    (registry / "L003.json").write_text(
        json.dumps(mismatched, indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(FailureMemoryError, match="does not match id") as exc_info:
        compile_registry(loaded, repo)
    assert exc_info.value.code == "registry_id"
    (registry / "L003.json").unlink()

    (registry / "L002.json").write_text(
        json.dumps(_lesson("L001"), indent=2) + "\n", encoding="utf-8"
    )
    with pytest.raises(FailureMemoryError, match="Duplicate lesson ID") as exc_info:
        compile_registry(loaded, repo)
    assert exc_info.value.code == "duplicate_id"
    (registry / "L002.json").unlink()

    meta = registry / "_registry.json"
    meta_bytes = meta.read_bytes()
    meta.write_text(
        json.dumps({"schema_version": True, "_field_spec": _FIELD_SPEC}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        FailureMemoryError, match="Unsupported registry schema_version"
    ) as exc_info:
        compile_registry(loaded, repo)
    assert exc_info.value.code == "registry_schema"
    meta.write_bytes(meta_bytes)

    meta.unlink()
    with pytest.raises(FailureMemoryError, match="missing _registry.json") as exc_info:
        compile_registry(loaded, repo)
    assert exc_info.value.code == "registry_schema"
    meta.write_bytes(meta_bytes)

    file_config = _config_text(
        tmp_path / "file-as-v2",
        schema_version=2,
        registry="dev/lessons.json",
        pattern=r"^L[0-9]{3}$",
    )
    target = tmp_path / "file-as-v2/dev/lessons.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(SOURCE.read_bytes())
    with pytest.raises(FailureMemoryError, match="directory, not a file") as exc_info:
        compile_registry(load_project_config(file_config), tmp_path / "file-as-v2")
    assert exc_info.value.code == "registry_schema"

    dir_config = _config_text(
        tmp_path / "dir-as-v1",
        schema_version=1,
        registry="dev/lessons",
        pattern=r"^L[0-9]{3}$",
    )
    shutil.copytree(registry, tmp_path / "dir-as-v1/dev/lessons")
    with pytest.raises(FailureMemoryError, match="file, not a directory") as exc_info:
        compile_registry(load_project_config(dir_config), tmp_path / "dir-as-v1")
    assert exc_info.value.code == "registry_schema"


def test_v2_compile_sorts_with_the_shared_lesson_id_key(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    registry = repo / "dev/lessons"
    config = _config_text(
        repo, schema_version=2, registry="dev/lessons", pattern=BOTH_PATTERN
    )
    write_directory_registry(
        registry,
        field_spec=_FIELD_SPEC,
        lessons=[_lesson("L20261027-k3f9"), _lesson("L999")],
    )
    compilation = compile_registry(load_project_config(config), repo)
    assert [node.lesson_id for node in compilation.nodes] == ["L999", "L20261027-k3f9"]
    assert compilation.source_sha256 == _directory_digest(registry)


def test_v2_add_writes_one_file_and_rolls_back_only_that_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, config = _phase1_repo(tmp_path)
    vault = _vault(tmp_path)
    migrate_registry(config_path=config, repository_root=repo, to="2")
    registry = repo / "dev/lessons_from_failing"
    before = {path.name: path.read_bytes() for path in registry.iterdir()}
    created = add_lesson(
        config_path=config,
        repository_root=repo,
        global_vault=vault,
        request_path=_request_file(repo, "request.json", related=["L900"]),
    )
    assert created["status"] == "created"
    assert created["schema_version"] == "failure-memory-registry/v1"
    assert created["record"]["id"] == "L902"
    assert created["promotion"] == "not-performed"
    for name, payload in before.items():
        assert (registry / name).read_bytes() == payload
    assert (registry / "L902.json").is_file()
    assert set(before) | {"L902.json"} == {path.name for path in registry.iterdir()}

    def fail_publish(**_kwargs):
        raise FailureMemoryError("publish failed", code="publication_rollback")

    monkeypatch.setattr("akms_failure_memory.record.run_compiler", fail_publish)
    siblings = {path.name: path.read_bytes() for path in registry.iterdir()}
    with pytest.raises(FailureMemoryError, match="publish failed"):
        add_lesson(
            config_path=config,
            repository_root=repo,
            global_vault=vault,
            request_path=_request_file(repo, "again.json", related=["L900"]),
        )
    assert {path.name: path.read_bytes() for path in registry.iterdir()} == siblings
    assert not (registry / "L903.json").exists()


def test_add_reloads_registry_when_migration_finishes_while_it_waits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, config = _phase1_repo(tmp_path)
    vault = _vault(tmp_path)
    request = _request_file(repo, "request.json", related=["L900"])
    retained = repo / "dev/lessons_from_failing.json"
    retained_bytes = retained.read_bytes()
    original_acquire = ProjectLock.acquire
    migrated = False

    def acquire_after_migration(self: ProjectLock) -> ProjectLock:
        nonlocal migrated
        if not migrated:
            migrated = True
            migrate_registry(config_path=config, repository_root=repo, to="2")
        return original_acquire(self)

    monkeypatch.setattr(ProjectLock, "acquire", acquire_after_migration)
    created = add_lesson(
        config_path=config,
        repository_root=repo,
        global_vault=vault,
        request_path=request,
    )
    lesson_id = created["record"]["id"]
    directory = repo / "dev/lessons_from_failing"
    assert created["status"] == "created"
    assert (directory / f"{lesson_id}.json").is_file()
    assert retained.read_bytes() == retained_bytes
    loaded, _digest = load_directory_registry(directory, load_project_config(config))
    assert any(lesson["id"] == lesson_id for lesson in loaded)
    compiled = compile_registry(load_project_config(config), repo)
    assert any(node.lesson_id == lesson_id for node in compiled.nodes)


def test_failed_migration_publication_is_removed_and_retry_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, config = _phase1_repo(tmp_path)
    before = _snapshot(repo)
    real_replace = _atomic_replace

    def fail_after_registry_metadata(path: Path, content: bytes) -> None:
        real_replace(path, content)
        if path.name == "_registry.json" and repo.resolve() in path.resolve().parents:
            raise OSError("disk full after registry metadata")

    monkeypatch.setattr(
        "akms_failure_memory.registry_migrate._atomic_replace",
        fail_after_registry_metadata,
    )
    with pytest.raises(OSError, match="disk full after registry metadata"):
        migrate_registry(config_path=config, repository_root=repo, to="2")
    destination = repo / "dev/lessons_from_failing"
    assert not destination.exists()
    assert not destination.is_symlink()
    assert [
        path.name
        for path in (repo / "dev").iterdir()
        if path.name.startswith(".failure-memory-migrate-")
    ] == []
    assert _snapshot(repo) == before
    assert load_project_config(config).validation["registry_schema_version"] == 1

    monkeypatch.undo()
    migrated = migrate_registry(config_path=config, repository_root=repo, to="2")
    assert migrated["status"] == "migrated"
    assert destination.is_dir()
    assert (destination / "_registry.json").is_file()
    assert any(
        path.suffix == ".json" and path.name != "_registry.json"
        for path in destination.iterdir()
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(key, None)
    return subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=AKMS Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_branch_adds_merge_and_same_lesson_edits_conflict(tmp_path: Path) -> None:
    repo = tmp_path / "lesson-repo"
    registry = repo / "lessons"
    registry.mkdir(parents=True)
    (registry / "_registry.json").write_text(
        '{"schema_version": 2}\n', encoding="utf-8"
    )
    (registry / "L001.json").write_text(
        '{"id": "L001", "symptom": "base"}\n', encoding="utf-8"
    )

    def git(*args: str) -> subprocess.CompletedProcess[str]:
        return _git(repo, *args)

    assert git("init", "-b", "main").returncode == 0
    assert git("add", "lessons").returncode == 0
    assert git("commit", "-m", "base").returncode == 0
    assert git("branch", "right").returncode == 0
    (registry / "L002.json").write_text('{"id": "L002"}\n', encoding="utf-8")
    assert git("add", "lessons/L002.json").returncode == 0
    assert git("commit", "-m", "add L002").returncode == 0
    assert git("checkout", "right").returncode == 0
    (registry / "L003.json").write_text('{"id": "L003"}\n', encoding="utf-8")
    assert git("add", "lessons/L003.json").returncode == 0
    assert git("commit", "-m", "add L003").returncode == 0
    merged = git("merge", "main", "-m", "merge adds")
    assert merged.returncode == 0, merged.stderr
    assert (registry / "L002.json").is_file()
    assert (registry / "L003.json").is_file()

    conflict = tmp_path / "conflict-repo"
    conflict_registry = conflict / "lessons"
    conflict_registry.mkdir(parents=True)
    (conflict_registry / "L001.json").write_text(
        '{"id": "L001", "symptom": "base"}\n', encoding="utf-8"
    )

    def git_at(*args: str) -> subprocess.CompletedProcess[str]:
        return _git(conflict, *args)

    assert git_at("init", "-b", "main").returncode == 0
    assert git_at("add", "lessons").returncode == 0
    assert git_at("commit", "-m", "base").returncode == 0
    assert git_at("branch", "right").returncode == 0
    (conflict_registry / "L001.json").write_text(
        '{"id": "L001", "symptom": "left"}\n', encoding="utf-8"
    )
    assert git_at("add", "lessons/L001.json").returncode == 0
    assert git_at("commit", "-m", "edit left").returncode == 0
    assert git_at("checkout", "right").returncode == 0
    (conflict_registry / "L001.json").write_text(
        '{"id": "L001", "symptom": "right"}\n', encoding="utf-8"
    )
    assert git_at("add", "lessons/L001.json").returncode == 0
    assert git_at("commit", "-m", "edit right").returncode == 0
    collision = git_at("merge", "main", "-m", "merge edits")
    assert collision.returncode != 0
    unmerged = git_at("diff", "--name-only", "--diff-filter=U")
    assert "lessons/L001.json" in unmerged.stdout


def test_consumer_contract_v2_matches_v1_and_verifies() -> None:
    for pack in (PACK_V1, PACK_V2):
        result = subprocess.run(
            [sys.executable, str(pack / "verify_pack.py"), str(pack)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.startswith("PASS")
    v1_config = load_project_config(PACK_V1 / "project.toml")
    v2_config = load_project_config(PACK_V2 / "project.toml")
    before = compile_registry(v1_config, PACK_V1)
    after = compile_registry(v2_config, PACK_V2)
    _assert_same_lessons(before, after, v1_config)
    v1_lessons = json.loads((PACK_V1 / "lessons.json").read_text(encoding="utf-8"))
    assert v2_config.validation["registry_schema_version"] == 2
    assert v2_config.paths["registry"] == "lessons"
    loaded, digest = load_directory_registry(PACK_V2 / "lessons", v2_config)
    assert [lesson["id"] for lesson in loaded] == [
        lesson["id"] for lesson in v1_lessons["lessons"]
    ]
    assert [dict(lesson) for lesson in loaded] == v1_lessons["lessons"]
    assert digest == after.source_sha256
    assert not (PACK_V2 / "lessons.json").exists()
    assert not (PACK_V2 / "expected").exists()
