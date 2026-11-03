"""Scopes and the store root each one lives in.

==========  ================================================================
Scope       Store root
==========  ================================================================
project     ``<repo>/.knowledge/records/``, or ``<repo>/knowledge/records/``
            when the repository has only the older ``knowledge/`` directory
agent       ``~/.knowledge/records/agent/<id>/``
shared      ``~/.knowledge/records/shared/<id>/``
==========  ================================================================

``AKMS_RECORDS_HOME`` replaces ``~/.knowledge/records`` for agent and shared
scopes. Several project IDs may share one repository's store; agent and
shared scopes get one root per ID.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from akms_records.errors import RecordsError

SCOPE_KINDS = ("project", "agent", "shared")
SCOPE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
HOME_ENV = "AKMS_RECORDS_HOME"

# The same rule AKMS core uses for a repository's knowledge directory,
# repeated here so this package does not import akms.
DEFAULT_KNOWLEDGE_DIRNAME = ".knowledge"
LEGACY_KNOWLEDGE_DIRNAME = "knowledge"


@dataclass(frozen=True, order=True)
class Scope:
    """A record namespace: ``kind`` is project, agent or shared."""

    kind: str
    id: str

    def __post_init__(self) -> None:
        if self.kind not in SCOPE_KINDS:
            raise RecordsError(
                f"invalid scope kind {self.kind!r}: expected one of "
                + ", ".join(SCOPE_KINDS),
                code="invalid_scope",
            )
        if (
            not isinstance(self.id, str)
            or not SCOPE_ID_RE.fullmatch(self.id)
            or ".." in self.id
        ):
            raise RecordsError(
                f"invalid scope id {self.id!r}: use 1-128 letters, digits and "
                ". _ -, starting with a letter or digit",
                code="invalid_scope",
            )

    @classmethod
    def parse(cls, text: str) -> "Scope":
        """Parse ``kind:id``, for example ``project:example``."""
        if not isinstance(text, str) or ":" not in text:
            raise RecordsError(
                f"invalid scope {text!r}: expected project:<id>, agent:<id> "
                "or shared:<id>",
                code="invalid_scope",
            )
        kind, _, ident = text.partition(":")
        return cls(kind, ident)

    @classmethod
    def from_json(cls, value: Any) -> "Scope":
        if (
            not isinstance(value, dict)
            or set(value) != {"kind", "id"}
            or not all(isinstance(value[key], str) for key in ("kind", "id"))
        ):
            raise RecordsError(
                "scope must be an object with string fields kind and id",
                code="invalid_scope",
            )
        return cls(value["kind"], value["id"])

    def to_json(self) -> dict[str, str]:
        return {"kind": self.kind, "id": self.id}

    def __str__(self) -> str:
        return f"{self.kind}:{self.id}"


def local_knowledge_dir(repo_root: str | Path) -> Path:
    """``<repo>/.knowledge``, or ``<repo>/knowledge`` if only that exists."""
    root = Path(repo_root)
    dotted = root / DEFAULT_KNOWLEDGE_DIRNAME
    legacy = root / LEGACY_KNOWLEDGE_DIRNAME
    if dotted.is_dir():
        return dotted
    if legacy.is_dir():
        return legacy
    return dotted


def records_home() -> Path:
    """The user-level root for agent and shared scopes."""
    override = os.environ.get(HOME_ENV)
    if override:
        return Path(override).expanduser()
    return Path.home() / DEFAULT_KNOWLEDGE_DIRNAME / "records"


def store_root(
    scope: Scope,
    *,
    repo: str | Path | None = None,
    home: str | Path | None = None,
) -> Path:
    """The store root that holds ``scope``'s records."""
    if scope.kind == "project":
        if repo is None:
            raise RecordsError(
                "project scope needs a repository (--repo)", code="usage"
            )
        return local_knowledge_dir(repo) / "records"
    base = Path(home).expanduser() if home is not None else records_home()
    return base / scope.kind / scope.id


__all__ = [
    "HOME_ENV",
    "SCOPE_KINDS",
    "Scope",
    "local_knowledge_dir",
    "records_home",
    "store_root",
]
