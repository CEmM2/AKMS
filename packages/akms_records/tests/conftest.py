from __future__ import annotations

import itertools
import os
import shutil
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from akms_records import RecordStore, Scope
from akms_records.schemas import load_template

TESTS = Path(__file__).resolve().parent
WORKER = TESTS / "workers" / "writer.py"


class Clock:
    """A deterministic clock: one microsecond per call from a fixed start."""

    def __init__(self, start: str = "2026-11-03T10:00:00") -> None:
        self.start = start
        self.counter = itertools.count()

    def __call__(self) -> str:
        return f"{self.start}.{next(self.counter):06d}Z"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir()
    return path


@pytest.fixture
def make_store(repo: Path) -> Callable[..., RecordStore]:
    def make(scope: str = "project:example", **kwargs: Any) -> RecordStore:
        return RecordStore.open(Scope.parse(scope), repo=repo, **kwargs)

    return make


@pytest.fixture
def store(make_store: Callable[..., RecordStore]) -> RecordStore:
    st = make_store(clock=Clock())
    st.register_schema(load_template("decision"), actor="tester")
    return st


def decision(text: str = "Keep the model", **extra: Any) -> dict[str, Any]:
    return {
        "schema_ref": "decision/v1",
        "payload": {"decision": text, "rationale": "within budget"},
        **extra,
    }


@pytest.fixture
def git_env(tmp_path: Path) -> dict[str, str]:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    empty = tmp_path / "empty.gitconfig"
    empty.write_text("", encoding="utf-8")
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": str(empty),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "tester",
        "GIT_AUTHOR_EMAIL": "tester@example.invalid",
        "GIT_COMMITTER_NAME": "tester",
        "GIT_COMMITTER_EMAIL": "tester@example.invalid",
    }
    return env


@pytest.fixture
def git(git_env: dict[str, str]) -> Callable[..., subprocess.CompletedProcess[str]]:
    def run(
        repo: Path, *args: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [
                "git",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "init.defaultBranch=main",
                "-c",
                "core.hooksPath=" + os.devnull,
                *args,
            ],
            cwd=repo,
            env=git_env,
            capture_output=True,
            text=True,
        )
        if check and result.returncode != 0:
            raise AssertionError(f"git {args}: {result.stdout}\n{result.stderr}")
        return result

    return run


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[Any]]:
    """Fail and count every socket connection attempt."""
    import socket

    attempts: list[Any] = []

    def blocked(*args: Any, **kwargs: Any) -> Any:
        attempts.append(args[:2])
        raise OSError("network blocked by test")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    yield attempts


@pytest.fixture
def doc() -> Callable[..., dict[str, Any]]:
    """Build a decision/v1 record document."""
    return decision


@pytest.fixture
def clock() -> type[Clock]:
    return Clock


@pytest.fixture
def worker() -> Path:
    return WORKER
