"""Repository-agnostic models for deterministic task knowledge routes.

These models intentionally live outside :mod:`akms.schema.models`: task route
indexes are retrieval inputs, not part of the frozen AKMS v2 node frontmatter
or propagation schemas.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

TASK_ROUTE_INDEX_SCHEMA_VERSION = "v1"

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def normalize_repository_path(path: str) -> str:
    """Return a canonical repository-relative POSIX path.

    Both POSIX and Windows separators are accepted. Absolute paths, drive
    prefixes, parent traversal, NUL bytes, and paths that normalize to the
    repository root are rejected.
    """

    if not isinstance(path, str):
        raise ValueError("Route path must be a string")

    candidate = path.strip()
    if not candidate:
        raise ValueError("Route path must not be empty")
    if "\x00" in candidate:
        raise ValueError("Route path must not contain NUL bytes")

    candidate = candidate.replace("\\", "/")
    if candidate.startswith("/") or _WINDOWS_DRIVE.match(candidate):
        raise ValueError("Route path must be repository-relative")

    parts: list[str] = []
    for part in candidate.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            raise ValueError("Route path must not traverse outside the repository")
        parts.append(part)

    if not parts:
        raise ValueError("Route path must identify a repository entry")
    return "/".join(parts)


class RouteRecord(BaseModel):
    """One required-node route and its audit information."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str
    reason: str
    provenance: str | dict[str, JsonValue]

    @field_validator("node_id", "reason")
    @classmethod
    def _nonempty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value must not be empty")
        return value

    @field_validator("provenance")
    @classmethod
    def _nonempty_provenance(
        cls, value: str | dict[str, JsonValue]
    ) -> str | dict[str, JsonValue]:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("Provenance must not be empty")
            return value
        if not value:
            raise ValueError("Provenance mapping must not be empty")
        cls._validate_finite_json(value)
        return value

    @classmethod
    def _validate_finite_json(cls, value: JsonValue) -> None:
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Provenance numbers must be finite")
        if isinstance(value, dict):
            for nested in value.values():
                cls._validate_finite_json(nested)
        elif isinstance(value, list):
            for nested in value:
                cls._validate_finite_json(nested)

    def canonical_sort_key(self) -> tuple[str, str, str]:
        """Return the stable ordering key used within one route."""

        provenance = json.dumps(
            self.provenance,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return self.node_id, self.reason, provenance


class RouteValidationIssue(BaseModel):
    """A machine-readable route validation failure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    location: tuple[str | int, ...]
    message: str
    node_id: str | None = None


class RouteIndexValidationError(ValueError):
    """Raised with all route-index validation issues found in one pass."""

    def __init__(
        self, issues: list[RouteValidationIssue] | tuple[RouteValidationIssue, ...]
    ):
        if not issues:
            raise ValueError("RouteIndexValidationError requires at least one issue")
        self.issues = tuple(issues)
        summary = "; ".join(
            f"{'.'.join(str(part) for part in issue.location)}: {issue.message}"
            for issue in self.issues
        )
        super().__init__(summary)

    def errors(self) -> list[dict[str, Any]]:
        """Return Pydantic-style serializable issue dictionaries."""

        return [
            issue.model_dump(mode="json", exclude_none=True) for issue in self.issues
        ]


class TaskRouteIndex(BaseModel):
    """Canonical path/symbol routes to required AKMS nodes."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["v1"]
    source_hash: str
    by_path: dict[str, tuple[RouteRecord, ...]]
    by_symbol: dict[str, tuple[RouteRecord, ...]] = Field(default_factory=dict)

    @field_validator("source_hash")
    @classmethod
    def _nonempty_source_hash(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Source hash must not be empty")
        return value

    @field_validator("by_path", mode="before")
    @classmethod
    def _normalize_path_keys(cls, value: Mapping[str, Any]) -> dict[str, list[Any]]:
        if not isinstance(value, Mapping):
            raise ValueError("by_path must be a mapping")

        normalized: dict[str, list[Any]] = {}
        for raw_path, records in value.items():
            path = normalize_repository_path(raw_path)
            if not isinstance(records, (list, tuple)):
                raise ValueError(f"Route '{raw_path}' must contain a list of records")
            normalized.setdefault(path, []).extend(records)
        return normalized

    @field_validator("by_symbol", mode="before")
    @classmethod
    def _validate_symbol_keys(cls, value: Mapping[str, Any] | None) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ValueError("by_symbol must be a mapping")

        symbols: dict[str, Any] = {}
        for raw_symbol, records in value.items():
            if not isinstance(raw_symbol, str) or not raw_symbol.strip():
                raise ValueError("Symbol route key must be a non-empty string")
            if not isinstance(records, (list, tuple)):
                raise ValueError(
                    f"Symbol route '{raw_symbol}' must contain a list of records"
                )
            symbol = raw_symbol.strip()
            if symbol in symbols:
                raise ValueError(f"Duplicate symbol route '{symbol}'")
            symbols[symbol] = records
        return symbols

    @model_validator(mode="after")
    def _canonicalize_routes(self) -> TaskRouteIndex:
        self.by_path = self._canonical_route_map(self.by_path)
        self.by_symbol = self._canonical_route_map(self.by_symbol)
        return self

    @staticmethod
    def _canonical_route_map(
        routes: Mapping[str, tuple[RouteRecord, ...]],
    ) -> dict[str, tuple[RouteRecord, ...]]:
        canonical: dict[str, tuple[RouteRecord, ...]] = {}
        for route_key in sorted(routes):
            records = routes[route_key]
            seen: dict[str, RouteRecord] = {}
            for record in records:
                previous = seen.get(record.node_id)
                if previous is not None:
                    kind = "Duplicate" if previous == record else "Conflicting"
                    raise ValueError(
                        f"{kind} node record '{record.node_id}' in route '{route_key}'"
                    )
                seen[record.node_id] = record
            canonical[route_key] = tuple(
                sorted(records, key=RouteRecord.canonical_sort_key)
            )
        return canonical

    def canonical_data(self) -> dict[str, Any]:
        """Return the canonical JSON-compatible representation."""

        return self.model_dump(mode="json")

    def canonical_json(self) -> str:
        """Serialize deterministically for hashing, caching, and diffs."""

        return json.dumps(
            self.canonical_data(),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
