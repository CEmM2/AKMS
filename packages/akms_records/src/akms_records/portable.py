"""Portable JSONL export and import of one scope.

An export is one JSON object per line:

1. ``header``: format ``akms-records-export/v1``, the scope, the time;
2. one ``schema`` line per registered schema, with its digest and its
   extraction rules (or ``null``) with their digest;
3. one ``erasure`` line per logged erasure in the scope (content-free);
4. one ``event`` line per event, record by record, oldest revision first;
5. ``footer``: counts, and the SHA-256 of every preceding line.

Records whose current sensitivity is ``sensitive`` are left out unless asked
for. Export refuses a scope with records that do not replay, unless told to
skip them; skipped records are listed in the result.

Import checks the footer, every schema digest, every event's seal and chain,
and every payload against its schema, then writes missing event files with
the store's exclusive write. It is idempotent: importing the same file twice
writes nothing the second time. A record whose local history has diverged
from the imported one is reported as a conflict and left alone, and a record
named in the local erasure log is never brought back.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from pathlib import Path
from typing import IO, Any

from akms_records.canonical import canonical_bytes, compact_line, digest, loads_strict
from akms_records.errors import NotFound, RecordsError, ReplayError
from akms_records.fsio import append_line, fsync_dir, write_exclusive
from akms_records.ids import parse_record_id
from akms_records.schemas import (
    check_rules,
    check_schema_document,
    parse_ref,
    split_rules,
    validate_instance,
)
from akms_records.scope import Scope
from akms_records.store import (
    ERASURE_LOG,
    RecordStore,
    fold_events,
    read_event_files,
    verify_events,
)

EXPORT_FORMAT = "akms-records-export/v1"


def _export_lines(
    store: RecordStore,
    *,
    include_sensitive: bool,
    skip_broken: bool,
    exporter: str,
    summary: dict[str, Any],
) -> Iterator[str]:
    yield compact_line(
        {
            "type": "header",
            "format": EXPORT_FORMAT,
            "scope": store.scope.to_json(),
            "exported_at": store.now(),
            "exporter": exporter,
        }
    )
    for ref, loaded in store.schemas.iter_checked():
        if isinstance(loaded, RecordsError):
            raise loaded
        summary["schemas"] += 1
        rules = store.schemas.rules_record(ref)
        yield compact_line(
            {
                "type": "schema",
                "schema_ref": ref,
                "schema_sha256": loaded.schema_sha256,
                "schema": loaded.schema,
                "rules": rules["rules"] if rules else None,
                "rules_sha256": rules["rules_sha256"] if rules else None,
            }
        )
    entries, _ = store.erasure_entries()
    for entry in entries:
        if entry.get("scope") == str(store.scope):
            summary["erasures"] += 1
            yield compact_line({"type": "erasure", "erasure": entry})
    broken: list[str] = []
    for item in store.iter_records():
        if isinstance(item, ReplayError):
            broken.append(item.record_id)
            continue
        if item.sensitivity == "sensitive" and not include_sensitive:
            summary["skipped_sensitive"].append(item.record_id)
            continue
        summary["records"] += 1
        for event in store.history(item.record_id):
            summary["events"] += 1
            yield compact_line({"type": "event", "event": event})
    if broken and not skip_broken:
        raise RecordsError(
            f"{len(broken)} record(s) do not replay; run doctor, or pass "
            "--skip-broken to export the others",
            code="replay_error",
            details={"records": broken},
        )
    summary["skipped_broken"] = broken


def export_records(
    store: RecordStore,
    out: IO[str],
    *,
    include_sensitive: bool = False,
    skip_broken: bool = False,
    exporter: str = "akms-records",
) -> dict[str, Any]:
    """Write ``store``'s scope to ``out`` as JSONL and return a summary."""
    summary: dict[str, Any] = {
        "schemas": 0,
        "erasures": 0,
        "records": 0,
        "events": 0,
        "skipped_sensitive": [],
        "skipped_broken": [],
    }
    hasher = hashlib.sha256()
    lines = []
    for line in _export_lines(
        store,
        include_sensitive=include_sensitive,
        skip_broken=skip_broken,
        exporter=exporter,
        summary=summary,
    ):
        hasher.update(line.encode("utf-8") + b"\n")
        lines.append(line)
    footer = {
        "type": "footer",
        "schemas": summary["schemas"],
        "erasures": summary["erasures"],
        "records": summary["records"],
        "events": summary["events"],
        "sha256": hasher.hexdigest(),
    }
    # Written only after every check passed, so a refused export writes nothing.
    for line in lines:
        out.write(line + "\n")
    out.write(compact_line(footer) + "\n")
    return {"status": "ok", "scope": str(store.scope), **summary}


def _corrupt(message: str) -> RecordsError:
    return RecordsError(message, code="export_corrupt")


def _parse_export(text: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw_lines = text.splitlines()
    if not raw_lines:
        raise _corrupt("the export is empty")
    items: list[dict[str, Any]] = []
    hasher = hashlib.sha256()
    for number, line in enumerate(raw_lines, 1):
        try:
            item = loads_strict(line)
        except ValueError as exc:
            raise _corrupt(f"line {number}: {exc}") from None
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            raise _corrupt(f"line {number}: not an export item")
        if number < len(raw_lines):
            hasher.update(line.encode("utf-8") + b"\n")
        items.append(item)
    header, footer = items[0], items[-1]
    if header.get("type") != "header" or header.get("format") != EXPORT_FORMAT:
        raise _corrupt(f"the first line is not an {EXPORT_FORMAT} header")
    if footer.get("type") != "footer" or len(items) < 2:
        raise _corrupt("the export has no footer; it may be truncated")
    if footer.get("sha256") != hasher.hexdigest():
        raise _corrupt("the footer digest does not match the export's lines")
    body = items[1:-1]
    counts = {
        kind: sum(1 for item in body if item["type"] == kind)
        for kind in ("schema", "erasure", "event")
    }
    if (
        footer.get("schemas") != counts["schema"]
        or footer.get("erasures") != counts["erasure"]
        or footer.get("events") != counts["event"]
    ):
        raise _corrupt("the footer counts do not match the export's lines")
    unknown = sorted({item["type"] for item in body} - {"schema", "erasure", "event"})
    if unknown:
        raise _corrupt("unknown item types: " + ", ".join(unknown))
    return header, body


def import_records(
    store: RecordStore, path: str | Path, *, actor: str
) -> dict[str, Any]:
    """Import an export into ``store``; see the module docstring."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise RecordsError(f"cannot read {path}: {exc}", code="io_error") from None
    header, body = _parse_export(text)
    if Scope.from_json(header.get("scope")) != store.scope:
        raise RecordsError(
            f"the export holds scope {Scope.from_json(header.get('scope'))}, "
            f"not the requested {store.scope}",
            code="scope_violation",
        )
    report: dict[str, Any] = {
        "schemas_registered": [],
        "schemas_present": [],
        "rules_set": [],
        "rules_differ": [],
        "records_written": [],
        "records_unchanged": [],
        "events_written": 0,
        "conflicts": {},
        "skipped_erased": [],
        "erasures_added": 0,
        "erased_but_present": [],
    }
    # 1. Schemas: digest-checked and statically checked now, registered at the end.
    schemas: dict[str, dict[str, Any]] = {}
    pending: list[tuple[str, dict[str, Any], str, int, Any]] = []
    rules_to_set: list[tuple[str, dict[str, Any]]] = []
    for item in (i for i in body if i["type"] == "schema"):
        ref, claimed, schema = (
            item.get("schema_ref"),
            item.get("schema_sha256"),
            item.get("schema"),
        )
        name, version = parse_ref(str(ref))
        if not isinstance(schema, dict) or split_rules(schema)[1] is not None:
            raise _corrupt(f"schema {ref}: rules belong on the line, not in the schema")
        if digest(schema) != claimed:
            raise RecordsError(
                f"schema {ref}: content does not match its digest",
                code="digest_mismatch",
            )
        check_schema_document(schema, name=name, version=version)
        rules = item.get("rules")
        if rules is not None:
            if digest(rules) != item.get("rules_sha256"):
                raise RecordsError(
                    f"schema {ref}: rules do not match their digest",
                    code="digest_mismatch",
                )
            check_rules(schema, rules)
        try:
            local = store.schemas.get(str(ref))
        except NotFound:
            pending.append((str(ref), schema, name, version, rules))
        else:
            if rules is not None:
                current = store.schemas.rules_record(str(ref))
                if current is None:
                    rules_to_set.append((str(ref), rules))
                elif current["rules_sha256"] != digest(rules):
                    report["rules_differ"].append(ref)  # local rules are kept
            if local.schema_sha256 != claimed:
                raise RecordsError(
                    f"schema {ref} is registered here with a different digest",
                    code="schema_exists",
                )
            report["schemas_present"].append(ref)
        schemas[str(ref)] = schema
    # 2. Erasures: merged into the local log, and honoured below.
    local_entries, _ = store.erasure_entries()
    known = {compact_line(entry) for entry in local_entries}
    erased = {entry["record_id"] for entry in local_entries}
    new_entries = []
    for item in (i for i in body if i["type"] == "erasure"):
        entry = item.get("erasure")
        if not isinstance(entry, dict) or entry.get("scope") != str(store.scope):
            raise _corrupt("an erasure line outside the export's scope")
        parse_record_id(str(entry.get("record_id")))
        erased.add(entry["record_id"])
        if compact_line(entry) not in known:
            new_entries.append(entry)
    # 3. Events, grouped by record in file order.
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in (i for i in body if i["type"] == "event"):
        event = item.get("event")
        if not isinstance(event, dict) or not isinstance(event.get("record_id"), str):
            raise _corrupt("an event line without a record ID")
        grouped.setdefault(event["record_id"], []).append(event)
    plans: list[tuple[str, list[dict[str, Any]], int]] = []
    for record_id, events in grouped.items():
        parse_record_id(record_id)
        verify_events(record_id, events)
        record = fold_events(record_id, events)
        if record.scope != store.scope:
            raise RecordsError(
                f"record {record_id} in the export is not in scope {store.scope}",
                code="scope_violation",
            )
        for event in events:
            if event["kind"] not in ("create", "amend"):
                continue
            envelope = event["body"]["envelope"]
            ref, sha = envelope["schema_ref"], envelope["schema_sha256"]
            if ref not in schemas:
                try:
                    schemas[ref] = store.schemas.get(ref).schema
                except NotFound:
                    raise RecordsError(
                        f"record {record_id} needs schema {ref}, which is neither "
                        "in the export nor registered here",
                        code="schema_not_found",
                    ) from None
            if digest(schemas[ref]) != sha:
                raise RecordsError(
                    f"record {record_id} revision {event['revision']} carries a "
                    f"different digest for {ref}",
                    code="digest_mismatch",
                )
            validate_instance(schemas[ref], event["body"]["payload"], ref=ref)
        if record_id in erased:
            report["skipped_erased"].append(record_id)
            if store.record_dir(record_id).exists():
                report["erased_but_present"].append(record_id)
            continue
        directory = store.record_dir(record_id)
        start = 0
        if directory.is_dir() and any(directory.iterdir()):
            try:
                local = [event for event, _ in read_event_files(directory, record_id)]
            except ReplayError as exc:
                report["conflicts"][record_id] = (
                    f"local record does not replay: {exc.detail}"
                )
                continue
            shared = min(len(local), len(events))
            if [digest(e) for e in local[:shared]] != [
                digest(e) for e in events[:shared]
            ]:
                report["conflicts"][record_id] = "local and imported histories diverge"
                continue
            start = len(local)
        if start >= len(events):
            report["records_unchanged"].append(record_id)
            continue
        plans.append((record_id, events, start))
    # Every check has passed; nothing was written before this point.
    for ref, schema, name, version, rules in pending:
        outcome = store.register_schema(
            schema, actor=actor, name=name, version=version, rules=rules
        )
        target = "schemas_registered" if outcome.new else "schemas_present"
        report[target].append(ref)
        if outcome.rules == "set":
            report["rules_set"].append(ref)
    for ref, rules in rules_to_set:
        store.set_rules(ref, rules, actor=actor)
        report["rules_set"].append(ref)
    if new_entries:
        store.ensure_root()
        for entry in new_entries:
            append_line(store.root / ERASURE_LOG, compact_line(entry))
        report["erasures_added"] = len(new_entries)
    for record_id, events, start in plans:
        directory = store.record_dir(record_id)
        store.ensure_root()
        directory.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.mkdir(directory)
            fsync_dir(directory.parent)
        except FileExistsError:
            pass
        written = 0
        for event in events[start:]:
            try:
                write_exclusive(
                    directory, f"{event['revision']:06d}.json", canonical_bytes(event)
                )
            except FileExistsError:
                report["conflicts"][record_id] = (
                    f"revision {event['revision']} was written concurrently"
                )
                break
            written += 1
        if written:
            report["records_written"].append(record_id)
            report["events_written"] += written
    report["status"] = "drift" if report["conflicts"] else "ok"
    report["scope"] = str(store.scope)
    return report


__all__ = ["EXPORT_FORMAT", "export_records", "import_records"]
