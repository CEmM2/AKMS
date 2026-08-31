"""Regression coverage for a [high] review finding:

Every lock acquisition (``ProjectLock.acquire``) used to create its
configured parent directory unconditionally, even for pure reads. A
``resolve_provider(write_artifacts=False)`` call, or the compiler in
``validate``/``check``/``dry-run`` mode, against a project whose lock parent
did not yet exist would silently create it and leave it behind -- an
ordinary read-only call mutating a repository it does not own. This was
invisible under the common (default ``init``) layout, where the lock's
parent is created by ``init`` itself, and only surfaced against a
deliberately nested, not-yet-created lock path -- exactly the kind of
"invisible under a benign starting state" defect this program keeps
finding (see integration-lock.json history: empty registries, a
pre-existing lock directory, ...).

Fix: ``ProjectLock(create_parent_directories=...)``. Write paths
(record a lesson, compile in write mode, refresh) keep the old default
(``True``) and are unaffected. Read paths
(``resolve_provider(write_artifacts=False)``; the compiler in
``validate``/``check``/``dry-run`` mode) now pass ``False``: if the parent
already exists (the common case), a real lock is still taken -- mutual
exclusion against concurrent writers is unchanged; if it does not exist,
``ProjectLock.acquire`` raises ``FailureMemoryError(code="lock_parent_missing")``
before touching the filesystem at all, rather than creating it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from akms_failure_memory.compiler import run_compiler
from akms_failure_memory.config import load_project_config
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.project import init_project
from akms_failure_memory.provider import resolve_provider
from akms_failure_memory.record import add_lesson


def _tree_digest(root: Path) -> str:
    """sha256 over every path (relative POSIX) + its bytes (b"" for a dir),
    sorted -- a strict superset of "no new file", also catching a new EMPTY
    directory, which a byte-content-only digest would miss.
    """
    entries = sorted(
        p.relative_to(root).as_posix() + ("/" if p.is_dir() else "")
        for p in root.rglob("*")
    )
    digest = hashlib.sha256()
    for relative in entries:
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        full = root / relative.rstrip("/")
        digest.update(full.read_bytes() if full.is_file() else b"")
        digest.update(b"\0")
    return digest.hexdigest()


def _paths(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob("*")}


def _adversarial_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A fresh, never-touched project whose lock parent genuinely does not
    exist -- the exact condition the review gate exercised. Nests `lock`
    one level deeper than the (already-fixed) init default, matching the
    contract pack's own convention of putting `lock` under a directory
    (``runtime/``) that only a write operation creates.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    config_path = repo / ".failure-memory" / "config.toml"
    init_project(
        repository_root=repo,
        config_path=".failure-memory/config.toml",
        repository_id="Adversarial",
        node_namespace="adversarial-failure",
    )
    text = config_path.read_text(encoding="utf-8")
    assert 'lock = ".failure-memory/.lock"' in text
    text = text.replace(
        'lock = ".failure-memory/.lock"',
        'lock = ".failure-memory/runtime/.lock"',
    )
    config_path.write_text(text, encoding="utf-8")
    lock_parent = repo / ".failure-memory" / "runtime"
    assert not lock_parent.exists(), "test setup must start with no lock parent"
    return repo, vault, config_path


def _provider_request(repository_id: str) -> dict:
    return {
        "schema_version": "failure-memory-provider-request/v1",
        "invocation_id": "readonly-no-mutation",
        "mode": "pre-task",
        "role": "implementer",
        "repository_id": repository_id,
        "task": {
            "task_id": "readonly-no-mutation",
            "title": "x",
            "objective": "x",
            "scope": [],
            "deliverables": [],
            "akms_tags": [],
        },
        "declared_paths": ["src/anything.py"],
        "changed_paths": [],
        "base": None,
        "head": None,
        "baseline": "readonly-no-mutation-baseline",
        "refresh_policy": "never",
        "output_dir": ".failure-memory/runtime/provider",
    }


def test_read_operations_create_nothing_from_a_nonexistent_lock_parent(
    tmp_path: Path,
) -> None:
    repo, vault, config_path = _adversarial_project(tmp_path)
    lock_parent = repo / ".failure-memory" / "runtime"
    before_digest = _tree_digest(repo)
    before_paths = _paths(repo)

    request_path = tmp_path / "request.json"
    request_path.write_text(
        json.dumps(_provider_request("Adversarial")), encoding="utf-8"
    )

    read_calls = [
        lambda: resolve_provider(
            config_path=config_path,
            repository_root=repo,
            request_source=request_path,
            write_artifacts=False,
        ),
        lambda: run_compiler(
            config_path=config_path, repository_root=repo, mode="validate"
        ),
        lambda: run_compiler(
            config_path=config_path,
            repository_root=repo,
            global_vault=vault,
            mode="check",
        ),
        lambda: run_compiler(
            config_path=config_path,
            repository_root=repo,
            global_vault=vault,
            mode="dry-run",
        ),
    ]
    for call in read_calls:
        try:
            call()
        except FailureMemoryError as exc:
            # A typed failure is the sanctioned outcome when the lock
            # parent genuinely does not exist (see module docstring) --
            # what must never happen is it succeeding AND creating the
            # directory, or creating the directory as a side effect of
            # failing for some other reason.
            assert exc.code in {
                "lock_parent_missing",
                "provider_resolve",
                "provider_stale",
            }, f"unexpected failure code {exc.code!r}: {exc}"
        assert not lock_parent.exists(), (
            "a read-only operation created the lock parent directory"
        )
        assert _paths(repo) == before_paths, "a read-only operation created a path"
        assert _tree_digest(repo) == before_digest, (
            "a read-only operation mutated the repository tree"
        )

    assert not lock_parent.exists()
    assert _tree_digest(repo) == before_digest


def test_read_operations_succeed_normally_when_lock_parent_already_exists(
    tmp_path: Path,
) -> None:
    """The common (default `init`) case: the lock's parent already exists
    (created by `init` itself), so a read must behave exactly as before --
    no new `lock_parent_missing` failure, a real result comes back, and
    still nothing new is created.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    vault = tmp_path / "vault"
    vault.mkdir()
    config_path = repo / ".failure-memory" / "config.toml"
    init_project(
        repository_root=repo,
        config_path=".failure-memory/config.toml",
        repository_id="Warm",
        node_namespace="warm-failure",
    )
    config = load_project_config(config_path)
    assert config.resolve(repo, "lock").parent.is_dir()

    before_digest = _tree_digest(repo)
    validation = run_compiler(
        config_path=config_path, repository_root=repo, mode="validate"
    )
    assert validation["status"] == "valid"
    assert _tree_digest(repo) == before_digest, (
        "a read against an already-bootstrapped project must still create nothing new"
    )


def test_write_operations_still_create_what_they_need(tmp_path: Path) -> None:
    """Requirement 2: write paths (record, compile write, refresh) may
    legitimately create the lock parent and their own output directories.
    Uses the SAME adversarial nested-lock layout as the read-only test, so
    this is a direct before/after contrast against the identical starting
    state.
    """
    repo, vault, config_path = _adversarial_project(tmp_path)
    lock_parent = repo / ".failure-memory" / "runtime"
    assert not lock_parent.exists()

    proposal = {
        "date_fixed": "2026-08-18",
        "date_fixed_precision": "exact",
        "date_found": "2026-08-17",
        "date_found_precision": "exact",
        "fix": "x",
        "found_by": {"trigger": "tests/x.py::test_x", "type": "test failure"},
        "location": {
            "area": "src",
            "file": "src/anything.py",
            "line_hint": "x",
            "module": "anything",
            "package": "src",
            "symbol": "Anything.thing",
        },
        "notes": "write-still-works regression proof",
        "prevention": "x",
        "references": {"commit": "", "issue": "", "plan": "", "pr": ""},
        "related": [],
        "root_cause": "x",
        "symptom": "x",
    }
    request_path = tmp_path / "proposal.json"
    request_path.write_text(json.dumps(proposal), encoding="utf-8")

    result = add_lesson(
        config_path=config_path,
        repository_root=repo,
        global_vault=vault,
        request_path=request_path,
    )
    assert result["status"] == "created"
    assert lock_parent.is_dir(), (
        "a write operation must be free to create what it needs"
    )
    assert not (lock_parent / ".lock").exists(), (
        "the lock FILE itself is still released/removed after a write completes"
    )

    config = load_project_config(config_path)
    generated = config.resolve(repo, "generated_nodes")
    assert any(generated.glob("*.md")), "the write actually produced generated output"


def test_project_lock_read_mode_rejects_missing_parent_without_touching_disk(
    tmp_path: Path,
) -> None:
    """Direct unit coverage of the ProjectLock mechanism itself, isolated
    from the compiler/provider callers above.
    """
    from akms_failure_memory.locks import ProjectLock

    missing_parent = tmp_path / "does" / "not" / "exist"
    lock_path = missing_parent / ".lock"
    assert not missing_parent.exists()

    with pytest.raises(FailureMemoryError) as raised:
        with ProjectLock(lock_path, create_parent_directories=False):
            pass  # pragma: no cover - must not be reached
    assert raised.value.code == "lock_parent_missing"
    assert not missing_parent.exists(), (
        "acquire() must not create anything before raising"
    )

    # The default (write) behavior is completely unchanged.
    with ProjectLock(lock_path):
        assert missing_parent.is_dir()
        assert lock_path.is_file()
    assert not lock_path.exists(), "the lock file is released"
    assert missing_parent.is_dir(), (
        "the parent directory a write created is not rolled back"
    )
