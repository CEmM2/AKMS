"""Explicit, schema-neutral authoring and review workflows.

Drafting and validation never write records or invent payload values. Validation
uses the same local-only JSON Schema engine as writes, including conditional
schemas and local references. A successful preflight is not a write guarantee:
creation still validates against the current registry and extraction rules.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from akms_records.envelope import (
    REVIEW_STATES,
    check_actor,
    parse_record_document,
    refuse_promotion_links,
)
from akms_records.errors import RecordsError
from akms_records.schemas import _validation, render_summary
from akms_records.store import RecordStore, WriteResult


def _pointer(parts: Any) -> str:
    return "".join("/" + str(p).replace("~", "~0").replace("/", "~1") for p in parts)


def validate_document(store: RecordStore, document: dict[str, Any]) -> dict[str, Any]:
    """Report envelope and payload problems without modifying the store.

    ``missing_fields`` lists required-property pointers from unconditional
    validation errors. Alternative branches remain in ``errors``; we never
    select a branch or claim that all its possible fields are mandatory.
    """
    errors: list[dict[str, Any]] = []
    missing: set[str] = set()
    try:
        fields = parse_record_document(document, scope=store.scope, partial=False)
        refuse_promotion_links(fields["source_refs"])
    except RecordsError as exc:
        return {
            "status": "error",
            "valid": False,
            "errors": [exc.to_json()["error"]],
            "missing_fields": [],
        }
    ref = store.schemas.resolve_ref(fields["schema_ref"])
    schema = store.schemas.get(ref)
    # Consolidations have a dedicated writer. Match create's reserved-schema guard.
    from akms_records.citations import is_consolidation

    if is_consolidation(ref):
        errors.append(
            {
                "code": "reserved_schema",
                "path": "/schema_ref",
                "message": "Use consolidate to create this schema's records",
            }
        )
    validation = _validation()
    validator = validation.Validator(
        schema.schema, registry=validation.refusing, format_checker=None
    )
    try:
        for error in validator.iter_errors(fields["payload"]):
            path = "/payload" + _pointer(error.absolute_path)
            errors.append(
                {
                    "code": "payload_invalid",
                    "path": path,
                    "schema_path": _pointer(error.absolute_schema_path),
                    "message": error.message,
                }
            )
            if error.validator == "required" and isinstance(error.instance, dict):
                missing.update(
                    path + _pointer([key])
                    for key in error.validator_value
                    if key not in error.instance
                )
    except validation.Unresolvable as exc:
        raise RecordsError(
            f"{ref}: schema reference refused: {exc}", code="schema_ref_refused"
        ) from None
    if not fields.get("summary"):
        try:
            summary = render_summary(store.schemas.rules(ref), fields["payload"])
        except RecordsError as exc:
            errors.append(exc.to_json()["error"])
            summary = None
        if not summary:
            missing.add("/summary")
            errors.append(
                {
                    "code": "summary_required",
                    "path": "/summary",
                    "message": "Supply summary or satisfy the schema's summary_template",
                }
            )
    errors.sort(key=lambda item: (item.get("path", ""), item["message"]))
    return {
        "status": "error" if errors else "ok",
        "valid": not errors,
        "schema_ref": ref,
        "schema_sha256": schema.schema_sha256,
        "errors": errors,
        "missing_fields": sorted(missing),
    }


def draft_document(
    store: RecordStore, schema_ref: str, *, document: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Pin a schema and inspect a partial document, without filling unknown facts."""
    candidate = deepcopy(document) if document is not None else {}
    candidate["schema_ref"] = store.schemas.resolve_ref(schema_ref)
    candidate.setdefault("payload", {})
    report = validate_document(store, candidate)
    return {**report, "status": "ok", "document": candidate}


def review_queue(
    store: RecordStore,
    *,
    schema: str | None = None,
    state: str = "unreviewed",
    include_sensitive: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    """Return oldest active records in exactly one review state, without an index."""
    if state not in REVIEW_STATES:
        raise RecordsError("unknown review state", code="usage")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise RecordsError("limit must be a positive integer", code="usage")
    rows, errors = [], []
    for record in store.iter_records():
        if isinstance(record, RecordsError):
            errors.append(record.to_json()["error"])
            continue
        if record.lifecycle != "active" or record.review_state != state:
            continue
        if record.sensitivity == "sensitive" and not include_sensitive:
            continue
        if (
            schema
            and record.schema_ref != schema
            and record.schema_ref.split("/v")[0] != schema
        ):
            continue
        rows.append(record.envelope_json())
    rows.sort(key=lambda row: (row["recorded_at"], row["record_id"]))
    return {
        "status": "error" if errors else "ok",
        "records": rows[:limit],
        "total": len(rows),
        "has_more": len(rows) > limit,
        "replay_errors": errors,
    }


def review_record(
    store: RecordStore,
    record_id: str,
    *,
    state: str,
    expected_revision: int,
    actor: str,
    event_id: str | None = None,
) -> WriteResult:
    """Record an explicit review of the inspected revision, preserving content.

    ``user_confirmed`` is an assertion by the caller, not identity verification.
    Agents must only use it when the person actually approved this revision.
    """
    check_actor(actor)
    if state not in REVIEW_STATES:
        raise RecordsError("unknown review state", code="usage")
    return store.amend(
        record_id,
        {"review_state": state},
        expected_revision=expected_revision,
        actor=actor,
        event_id=event_id,
    )


def render_records(records: list[dict[str, Any]]) -> str:
    """Human display of complete records; JSON remains the machine interface."""
    import json

    return "\n\n".join(
        f"{row['record_id']}@{row['revision']} | {row['schema_ref']} | {row['review_state']}\n"
        + json.dumps(row, ensure_ascii=False, indent=2, sort_keys=True)
        for row in records
    ) + ("\n" if records else "")
