"""The fixed record envelope around a schema-defined payload.

A record is an AKMS-controlled envelope plus a ``payload`` that a registered
JSON Schema describes. The envelope keys are reserved: a payload may not use
any of them as a top-level key, and a schema may not declare them as
top-level properties, so no flat view of a record can confuse the two.

Fields fall into three groups:

* set by the store: ``record_id``, ``revision``, ``schema_sha256``,
  ``recorded_at`` (the time of the creating event) and ``lifecycle``
  (``active``, ``superseded`` or ``retracted``, from the event history);
* fixed by the request: ``scope``;
* supplied by the writer: ``schema_ref``, ``origin``, ``source_refs``,
  ``summary``, ``tags``, ``sensitivity``, ``review_state`` and ``payload``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from akms_records.errors import RecordsError
from akms_records.scope import Scope

ENVELOPE_KEYS = (
    "record_id",
    "revision",
    "schema_ref",
    "schema_sha256",
    "scope",
    "recorded_at",
    "origin",
    "source_refs",
    "summary",
    "tags",
    "sensitivity",
    "review_state",
    "lifecycle",
    "payload",
)
STORE_MANAGED_KEYS = (
    "record_id",
    "revision",
    "schema_sha256",
    "recorded_at",
    "lifecycle",
)
WRITER_KEYS = (
    "schema_ref",
    "origin",
    "source_refs",
    "summary",
    "tags",
    "sensitivity",
    "review_state",
    "payload",
)

ORIGIN_KINDS = ("human", "human-confirmed", "agent", "tool", "import")
SENSITIVITY_LEVELS = ("public", "internal", "sensitive")
REVIEW_STATES = ("unreviewed", "agent_reviewed", "user_confirmed", "rejected")
LIFECYCLE_STATES = ("active", "superseded", "retracted")

DEFAULT_SENSITIVITY = "internal"
DEFAULT_REVIEW_STATE = "unreviewed"
DEFAULT_ORIGIN_KIND = "agent"

MAX_SUMMARY = 1000
MAX_TAG = 64
MAX_TAGS = 64
MAX_REFS = 64
MAX_REF_TEXT = 1000
_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/+-]*")
_ACTOR = re.compile(r"[^\x00-\x1f\x7f]{1,128}")


def _invalid(message: str) -> RecordsError:
    return RecordsError(message, code="invalid_record")


def check_actor(actor: Any) -> str:
    if not isinstance(actor, str) or not _ACTOR.fullmatch(actor) or not actor.strip():
        raise _invalid("actor must be 1-128 printable characters")
    return actor


def normalize_origin(value: Any) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) - {"kind", "actor_id"}:
        raise _invalid("origin must be an object with kind and actor_id")
    kind = value.get("kind")
    if kind not in ORIGIN_KINDS:
        raise _invalid(f"origin.kind {kind!r} is not one of " + ", ".join(ORIGIN_KINDS))
    return {"kind": kind, "actor_id": check_actor(value.get("actor_id"))}


def normalize_source_refs(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) > MAX_REFS:
        raise _invalid(f"source_refs must be a list of at most {MAX_REFS} objects")
    out: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or not {"kind", "ref"} <= set(item):
            raise _invalid(f"source_refs[{index}] needs kind and ref")
        if set(item) - {"kind", "ref", "note"}:
            raise _invalid(f"source_refs[{index}] allows only kind, ref and note")
        kind, ref = item["kind"], item["ref"]
        if not isinstance(kind, str) or not _SLUG.fullmatch(kind) or len(kind) > 64:
            raise _invalid(f"source_refs[{index}].kind {kind!r} is not a short slug")
        if not isinstance(ref, str) or not ref.strip() or len(ref) > MAX_REF_TEXT:
            raise _invalid(f"source_refs[{index}].ref must be non-empty text")
        entry = {"kind": kind, "ref": ref}
        if "note" in item:
            note = item["note"]
            if not isinstance(note, str) or len(note) > MAX_REF_TEXT:
                raise _invalid(f"source_refs[{index}].note must be text")
            entry["note"] = note
        out.append(entry)
    return out


def normalize_tags(value: Any) -> list[str]:
    if not isinstance(value, list) or len(value) > MAX_TAGS:
        raise _invalid(f"tags must be a list of at most {MAX_TAGS} strings")
    seen: set[str] = set()
    for tag in value:
        if not isinstance(tag, str) or not _SLUG.fullmatch(tag) or len(tag) > MAX_TAG:
            raise _invalid(f"tag {tag!r} must be 1-{MAX_TAG} characters without spaces")
        if tag in seen:
            raise _invalid(f"duplicate tag {tag!r}")
        seen.add(tag)
    return list(value)


def normalize_summary(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_SUMMARY:
        raise _invalid(f"summary must be non-empty text of at most {MAX_SUMMARY}")
    return value


def check_payload_keys(payload: Any) -> dict[str, Any]:
    """Refuse a payload that is not an object or reuses an envelope key."""
    if not isinstance(payload, dict):
        raise _invalid("payload must be a JSON object")
    shadowed = sorted(set(payload) & set(ENVELOPE_KEYS))
    if shadowed:
        raise RecordsError(
            "payload keys shadow envelope keys: " + ", ".join(shadowed),
            code="envelope_shadow",
            details={"keys": shadowed},
        )
    return payload


def parse_record_document(
    document: Any, *, scope: Scope, partial: bool
) -> dict[str, Any]:
    """Validate a writer's record document and return the fields it sets.

    ``partial`` is for amendments: absent fields keep their current value.
    A create (``partial=False``) fills defaults for ``origin``,
    ``source_refs``, ``tags``, ``sensitivity`` and ``review_state``; the
    caller fills ``summary`` from the schema's template when it is absent.
    """
    if not isinstance(document, dict):
        raise _invalid("a record document must be a JSON object")
    managed = sorted(set(document) & set(STORE_MANAGED_KEYS))
    if managed:
        raise _invalid(
            "fields set by the store cannot be supplied: " + ", ".join(managed)
        )
    unknown = sorted(set(document) - set(WRITER_KEYS) - {"scope"})
    if unknown:
        raise _invalid(
            "unknown top-level fields: "
            + ", ".join(unknown)
            + " (payload fields go under payload)"
        )
    if "scope" in document and Scope.from_json(document["scope"]) != scope:
        raise RecordsError(
            f"document scope {document['scope']!r} differs from the requested "
            f"scope {scope}",
            code="scope_violation",
        )
    out: dict[str, Any] = {}
    if "schema_ref" in document:
        if not isinstance(document["schema_ref"], str):
            raise _invalid("schema_ref must be a string")
        out["schema_ref"] = document["schema_ref"]
    if "payload" in document:
        out["payload"] = check_payload_keys(document["payload"])
    if "origin" in document:
        out["origin"] = normalize_origin(document["origin"])
    if "source_refs" in document:
        out["source_refs"] = normalize_source_refs(document["source_refs"])
    if "tags" in document:
        out["tags"] = normalize_tags(document["tags"])
    if "summary" in document:
        out["summary"] = normalize_summary(document["summary"])
    if "sensitivity" in document:
        if document["sensitivity"] not in SENSITIVITY_LEVELS:
            raise _invalid(
                "sensitivity must be one of " + ", ".join(SENSITIVITY_LEVELS)
            )
        out["sensitivity"] = document["sensitivity"]
    if "review_state" in document:
        if document["review_state"] not in REVIEW_STATES:
            raise _invalid("review_state must be one of " + ", ".join(REVIEW_STATES))
        out["review_state"] = document["review_state"]
    if not partial:
        if "payload" not in out:
            raise _invalid("a new record needs a payload")
        if "schema_ref" not in out:
            raise _invalid("a new record needs a schema_ref")
        out.setdefault("source_refs", [])
        out.setdefault("tags", [])
        out.setdefault("sensitivity", DEFAULT_SENSITIVITY)
        out.setdefault("review_state", DEFAULT_REVIEW_STATE)
    return out


@dataclass(frozen=True)
class Record:
    """The current state of one record, rebuilt by replaying its events."""

    record_id: str
    revision: int
    schema_ref: str
    schema_sha256: str
    scope: Scope
    recorded_at: str
    origin: dict[str, str]
    source_refs: list[dict[str, str]]
    summary: str
    tags: list[str]
    sensitivity: str
    review_state: str
    lifecycle: str
    payload: dict[str, Any]
    updated_at: str
    head_sha256: str
    superseded_by: str | None = None
    reason: str | None = None
    event_ids: tuple[str, ...] = field(default_factory=tuple)

    def envelope_json(self) -> dict[str, Any]:
        """The record as its envelope plus payload: the public record shape."""
        return {
            "record_id": self.record_id,
            "revision": self.revision,
            "schema_ref": self.schema_ref,
            "schema_sha256": self.schema_sha256,
            "scope": self.scope.to_json(),
            "recorded_at": self.recorded_at,
            "origin": dict(self.origin),
            "source_refs": [dict(ref) for ref in self.source_refs],
            "summary": self.summary,
            "tags": list(self.tags),
            "sensitivity": self.sensitivity,
            "review_state": self.review_state,
            "lifecycle": self.lifecycle,
            "payload": self.payload,
        }

    def state_json(self) -> dict[str, Any]:
        """Replay facts that are not part of the record itself."""
        return {
            "updated_at": self.updated_at,
            "head_sha256": self.head_sha256,
            "superseded_by": self.superseded_by,
            "reason": self.reason,
            "events": len(self.event_ids),
        }

    def writer_fields(self) -> dict[str, Any]:
        return {
            "schema_ref": self.schema_ref,
            "origin": dict(self.origin),
            "source_refs": [dict(ref) for ref in self.source_refs],
            "summary": self.summary,
            "tags": list(self.tags),
            "sensitivity": self.sensitivity,
            "review_state": self.review_state,
            "payload": self.payload,
        }


__all__ = [
    "ENVELOPE_KEYS",
    "LIFECYCLE_STATES",
    "ORIGIN_KINDS",
    "REVIEW_STATES",
    "Record",
    "SENSITIVITY_LEVELS",
    "check_payload_keys",
    "parse_record_document",
]
