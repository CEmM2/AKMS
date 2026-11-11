"""Per-schema promotion policy, stored beside the schema.

A promotion policy says how a later promotion into an AKMS project-local node
should label records of one schema. It is kept outside the schema document,
so setting or changing it never needs a new schema version and never changes
existing records::

    <root>/_schemas/<name>/_policy.json        the current policy
    <root>/_schemas/<name>/_policy_log.jsonl   append-only: actor, time,
                                               previous value, new value

This module only stores and shows policies; :mod:`akms_records.bridge` reads
them and cannot change them. Setting a policy is a human operation: the CLI asks for
interactive confirmation. The log entry is written before the policy file, so
an interrupted change is still visible in the log.

Without a policy, promotion uses ``source: agent``, ``status: tentative``.
An agent-sourced policy can never be ``established``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from akms_records.canonical import canonical_bytes, compact_line, loads_strict
from akms_records.envelope import check_actor
from akms_records.errors import NotFound, RecordsError
from akms_records.fsio import append_line, replace_file
from akms_records.schemas import NAME_RE, SchemaRegistry

POLICY_FORMAT = "akms-records-policy/v1"
POLICY_SOURCES = ("human", "agent")
POLICY_STATUSES = ("tentative", "established")
DEFAULT_POLICY = {"source": "agent", "status": "tentative", "confidence": 0.5}
POLICY_FILE = "_policy.json"
POLICY_LOG = "_policy_log.jsonl"


def _value(policy: dict[str, Any] | None) -> dict[str, Any] | None:
    if policy is None:
        return None
    return {key: policy[key] for key in ("source", "status", "confidence")}


def check_policy_value(source: Any, status: Any, confidence: Any) -> dict[str, Any]:
    if source not in POLICY_SOURCES:
        raise RecordsError(
            "policy source must be one of " + ", ".join(POLICY_SOURCES),
            code="invalid_policy",
        )
    if status not in POLICY_STATUSES:
        raise RecordsError(
            "policy status must be one of " + ", ".join(POLICY_STATUSES),
            code="invalid_policy",
        )
    if source == "agent" and status == "established":
        raise RecordsError(
            "an agent-sourced policy cannot be established", code="invalid_policy"
        )
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not 0.0 <= float(confidence) <= 1.0
    ):
        raise RecordsError(
            "policy confidence must be a number from 0 to 1", code="invalid_policy"
        )
    return {"source": source, "status": status, "confidence": float(confidence)}


class PolicyStore:
    """Promotion policies of the schemas registered in one store root."""

    def __init__(self, registry: SchemaRegistry) -> None:
        self.registry = registry

    def _dir(self, name: str) -> Path:
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            raise RecordsError(
                f"invalid schema name {name!r}", code="invalid_schema_ref"
            )
        if not self.registry.versions(name):
            raise NotFound(f"schema {name} is not registered", code="schema_not_found")
        return self.registry.root / name

    def current(self, name: str) -> dict[str, Any] | None:
        path = self._dir(name) / POLICY_FILE
        if not path.is_file():
            return None
        try:
            policy = loads_strict(path.read_bytes())
        except (ValueError, UnicodeDecodeError) as exc:
            raise RecordsError(
                f"policy for {name} is unreadable: {exc}", code="invalid_policy"
            ) from None
        if not isinstance(policy, dict) or policy.get("format") != POLICY_FORMAT:
            raise RecordsError(f"policy for {name} is malformed", code="invalid_policy")
        check_policy_value(
            policy.get("source"), policy.get("status"), policy.get("confidence")
        )
        return policy

    def log(self, name: str) -> list[dict[str, Any]]:
        path = self._dir(name) / POLICY_LOG
        if not path.is_file():
            return []
        entries = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                entry = loads_strict(line)
            except ValueError as exc:
                raise RecordsError(
                    f"policy log for {name}, line {number}: {exc}",
                    code="invalid_policy",
                ) from None
            entries.append(entry)
        return entries

    def set(
        self,
        name: str,
        *,
        source: str,
        status: str,
        confidence: float,
        actor: str,
        at: str,
    ) -> dict[str, Any]:
        """Set the policy and log the change. Callers must confirm with a person."""
        folder = self._dir(name)
        value = check_policy_value(source, status, confidence)
        check_actor(actor)
        previous = self.current(name)
        entry = {
            "schema": name,
            "at": at,
            "actor": actor,
            "previous": _value(previous),
            "value": value,
        }
        append_line(folder / POLICY_LOG, compact_line(entry))
        policy = {
            "format": POLICY_FORMAT,
            "schema": name,
            **value,
            "set_at": at,
            "set_by": actor,
        }
        replace_file(folder / POLICY_FILE, canonical_bytes(policy))
        return {"policy": policy, "previous": _value(previous), "logged": entry}

    def show(self, name: str) -> dict[str, Any]:
        policy = self.current(name)
        return {
            "schema": name,
            "policy": policy,
            "effective": _value(policy) or dict(DEFAULT_POLICY),
            "default_applies": policy is None,
            "log": self.log(name),
        }

    def drift(self, name: str) -> str | None:
        """A problem description when the policy file and its log disagree."""
        try:
            policy = self.current(name)
            log = self.log(name)
        except RecordsError as exc:
            return str(exc)
        if not log:
            return None if policy is None else "policy set without a log entry"
        latest = max(log, key=lambda entry: str(entry.get("at", "")))
        if latest.get("value") != _value(policy):
            return "the newest policy log entry differs from the current policy"
        return None


__all__ = [
    "DEFAULT_POLICY",
    "POLICY_SOURCES",
    "POLICY_STATUSES",
    "PolicyStore",
    "check_policy_value",
]
