"""The canonical record store: one directory per record, one file per event.

Layout under a store root::

    <root>/<YYYY-MM>/<record_id>/<revision:06d>.json   immutable events
    <root>/_schemas/...                                schema registry
    <root>/_erasures.jsonl                             content-free erasure log
    <root>/.gitattributes                              * -text, union merges
    <root>/.gitignore                                  .index/, *.tmp

An event file is canonical JSON with the fields ``format``, ``event_id``,
``record_id``, ``revision``, ``kind``, ``at``, ``actor``, ``prev_sha256``,
``body`` and ``event_sha256``. ``prev_sha256`` is the digest of the previous
event (``null`` for revision 1), which chains the history. ``event_sha256``
seals the event itself (its digest with that field left out), so an edit to
the newest revision is detected too; the chain alone only covers revisions
that have a successor. Digests are over the canonical re-serialization, so a
line-ending conversion does not break them.

The current state of a record is a replay of its events. Replay never repairs
anything: a gap, a broken chain or seal, or git conflict markers raise a
:class:`~akms_records.errors.ReplayError`.

The store enforces scope in its API: a :class:`RecordStore` is opened for one
scope, and reading or writing a record of another scope raises
:class:`~akms_records.errors.ScopeViolation`. That is a policy for
cooperating agents, not a security boundary.
"""

from __future__ import annotations

import os
import re
import shutil
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from akms_records.canonical import (
    canonical_bytes,
    compact_line,
    digest,
    loads_strict,
    utc_now,
)
from akms_records.envelope import (
    DEFAULT_ORIGIN_KIND,
    LIFECYCLE_STATES,
    Record,
    check_actor,
    check_payload_keys,
    normalize_origin,
    normalize_source_refs,
    normalize_summary,
    normalize_tags,
    parse_record_document,
    REVIEW_STATES,
    SENSITIVITY_LEVELS,
)
from akms_records.errors import (
    NotFound,
    RecordsError,
    ReplayError,
    ScopeViolation,
    StaleRevision,
)
from akms_records.fsio import TMP_RE, append_line, fsync_dir, write_exclusive
from akms_records.ids import (
    RECORD_ID_RE,
    check_event_id,
    day_of,
    new_event_id,
    parse_record_id,
    previous_day,
    record_id_for,
)
from akms_records.policy import PolicyStore
from akms_records.procs import pid_alive
from akms_records.schemas import REGISTRY_DIRNAME, RegisteredSchema, SchemaRegistry
from akms_records.scope import Scope, store_root

EVENT_FORMAT = "akms-records-event/v1"
EVENT_KINDS = ("create", "amend", "supersede", "retract")
EVENT_KEYS = frozenset(
    {
        "format",
        "event_id",
        "record_id",
        "revision",
        "kind",
        "at",
        "actor",
        "prev_sha256",
        "body",
        "event_sha256",
    }
)
EVENT_NAME_RE = re.compile(r"([0-9]{6})\.json")
MONTH_RE = re.compile(r"[0-9]{4}-[0-9]{2}")
ERASURE_LOG = "_erasures.jsonl"
GITATTRIBUTES_LINES = (
    "* -text",
    f"{ERASURE_LOG} merge=union",
    f"{REGISTRY_DIRNAME}/*/_policy_log.jsonl merge=union",
)
GITIGNORE_LINES = (".index/", "*.tmp")
ROOT_ENTRIES = frozenset(
    {".gitattributes", ".gitignore", ERASURE_LOG, REGISTRY_DIRNAME, ".index"}
)
MAX_REVISION = 999_999
CREATE_ATTEMPTS = 64
RETRY_LOOKBACK_ATTEMPTS = 4
TMP_MAX_AGE_SECONDS = 3600.0
EMPTY_DIR_GRACE_SECONDS = 60.0
MAX_REASON = 1000
NOT_REACHED = (
    "git history: commits, packs and remotes that already contain the record",
    "other clones and unmerged branches (run doctor after a merge to re-apply)",
    "exports and backups made before the erasure",
)
_CONFLICT_MARKER = re.compile(rb"(?m)^(?:<{7}|>{7}|={7}|\|{7})(?: |\r?$)")


@dataclass(frozen=True)
class WriteResult:
    """The outcome of one write. ``noop`` means the event already existed."""

    kind: str
    record_id: str
    revision: int
    event_id: str
    noop: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "record_id": self.record_id,
            "revision": self.revision,
            "event_id": self.event_id,
            "noop": self.noop,
        }


def seal_of(event: dict[str, Any]) -> str:
    """The event's own digest, taken with ``event_sha256`` left out."""
    return digest({key: value for key, value in event.items() if key != "event_sha256"})


def make_event(
    *,
    record_id: str,
    revision: int,
    kind: str,
    at: str,
    actor: str,
    prev_sha256: str | None,
    body: dict[str, Any],
    event_id: str,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "format": EVENT_FORMAT,
        "event_id": event_id,
        "record_id": record_id,
        "revision": revision,
        "kind": kind,
        "at": at,
        "actor": actor,
        "prev_sha256": prev_sha256,
        "body": body,
    }
    event["event_sha256"] = seal_of(event)
    return event


def _reason(value: Any, *, required: bool) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_REASON:
        raise RecordsError(
            f"reason must be non-empty text of at most {MAX_REASON} characters",
            code="invalid_record",
        )
    return value


def verify_events(record_id: str, events: list[Any]) -> list[dict[str, Any]]:
    """Check the structure, seals and chain of a record's events, in order."""
    out: list[dict[str, Any]] = []
    for index, event in enumerate(events, start=1):
        name = f"{index:06d}.json"
        if not isinstance(event, dict) or set(event) != EVENT_KEYS:
            raise ReplayError(record_id, "format", f"{name}: unexpected fields")
        if event["format"] != EVENT_FORMAT:
            raise ReplayError(record_id, "format", f"{name}: unknown format")
        if event["revision"] != index or event["record_id"] != record_id:
            raise ReplayError(
                record_id, "mismatch", f"{name}: wrong revision or record"
            )
        if event["event_sha256"] != seal_of(event):
            raise ReplayError(record_id, "digest", f"{name}: event digest mismatch")
        kind = event["kind"]
        if kind not in EVENT_KINDS or (index == 1) != (kind == "create"):
            raise ReplayError(record_id, "kind", f"{name}: unexpected kind {kind!r}")
        expected_prev = None if index == 1 else digest(out[-1])
        if event["prev_sha256"] != expected_prev:
            raise ReplayError(record_id, "chain", f"{name}: prev_sha256 mismatch")
        try:
            check_event_id(event["event_id"])
            check_actor(event["actor"])
            day_of(str(event["at"]))
        except RecordsError as exc:
            raise ReplayError(record_id, "format", f"{name}: {exc}") from None
        out.append(event)
    if not out:
        raise ReplayError(record_id, "empty", "no event files")
    return out


def _envelope_from_body(record_id: str, name: str, body: Any) -> dict[str, Any]:
    if not isinstance(body, dict) or set(body) != {"envelope", "payload"}:
        raise ReplayError(
            record_id, "format", f"{name}: body needs envelope and payload"
        )
    envelope = body["envelope"]
    keys = {
        "schema_ref",
        "schema_sha256",
        "scope",
        "origin",
        "source_refs",
        "summary",
        "tags",
        "sensitivity",
        "review_state",
    }
    if not isinstance(envelope, dict) or set(envelope) != keys:
        raise ReplayError(record_id, "format", f"{name}: envelope fields differ")
    try:
        check_payload_keys(body["payload"])
        Scope.from_json(envelope["scope"])
        normalize_origin(envelope["origin"])
        normalize_source_refs(envelope["source_refs"])
        normalize_tags(envelope["tags"])
        normalize_summary(envelope["summary"])
    except RecordsError as exc:
        raise ReplayError(record_id, "format", f"{name}: {exc}") from None
    if (
        envelope["sensitivity"] not in SENSITIVITY_LEVELS
        or envelope["review_state"] not in REVIEW_STATES
        or not isinstance(envelope["schema_ref"], str)
        or not isinstance(envelope["schema_sha256"], str)
    ):
        raise ReplayError(record_id, "format", f"{name}: invalid envelope value")
    return envelope


def fold_events(record_id: str, events: list[dict[str, Any]]) -> Record:
    """Replay verified events into the record's current state."""
    fields: dict[str, Any] = {}
    lifecycle = "active"
    superseded_by: str | None = None
    reason: str | None = None
    scope: Scope | None = None
    for event in events:
        kind, body, name = event["kind"], event["body"], f"{event['revision']:06d}.json"
        if kind != "create" and lifecycle != "active":
            raise ReplayError(
                record_id, "sequence", f"{name}: {kind} after {lifecycle}"
            )
        if kind in ("create", "amend"):
            envelope = _envelope_from_body(record_id, name, body)
            event_scope = Scope.from_json(envelope["scope"])
            if scope is not None and event_scope != scope:
                raise ReplayError(record_id, "sequence", f"{name}: scope changed")
            scope = event_scope
            fields = {**envelope, "payload": body["payload"]}
        elif kind == "supersede":
            if not isinstance(body, dict) or set(body) != {"superseded_by", "reason"}:
                raise ReplayError(record_id, "format", f"{name}: bad supersede body")
            if not RECORD_ID_RE.fullmatch(str(body["superseded_by"])):
                raise ReplayError(record_id, "format", f"{name}: bad superseded_by")
            lifecycle, superseded_by, reason = (
                "superseded",
                body["superseded_by"],
                body["reason"],
            )
        else:
            if not isinstance(body, dict) or set(body) != {"reason"}:
                raise ReplayError(record_id, "format", f"{name}: bad retract body")
            lifecycle, reason = "retracted", body["reason"]
    assert scope is not None and lifecycle in LIFECYCLE_STATES
    return Record(
        record_id=record_id,
        revision=events[-1]["revision"],
        schema_ref=fields["schema_ref"],
        schema_sha256=fields["schema_sha256"],
        scope=scope,
        recorded_at=events[0]["at"],
        origin=fields["origin"],
        source_refs=fields["source_refs"],
        summary=fields["summary"],
        tags=fields["tags"],
        sensitivity=fields["sensitivity"],
        review_state=fields["review_state"],
        lifecycle=lifecycle,
        payload=fields["payload"],
        updated_at=events[-1]["at"],
        head_sha256=digest(events[-1]),
        superseded_by=superseded_by,
        reason=reason,
        event_ids=tuple(event["event_id"] for event in events),
    )


def read_event_files(
    record_dir: Path, record_id: str, *, strict: bool = False
) -> list[tuple[dict[str, Any], bytes]]:
    """Read and verify a record's event files. ``strict`` also demands canonical bytes."""
    try:
        names = os.listdir(record_dir)
    except FileNotFoundError:
        raise NotFound(f"record {record_id} not found") from None
    revisions = sorted(
        int(match.group(1))
        for name in names
        if (match := EVENT_NAME_RE.fullmatch(name)) is not None
    )
    if not revisions:
        # An interrupted create leaves an empty directory: no record exists.
        raise NotFound(
            f"record {record_id} not found (empty directory; doctor removes it)"
        )
    pairs: list[tuple[dict[str, Any], bytes]] = []
    for expected, revision in enumerate(revisions, start=1):
        name = f"{revision:06d}.json"
        if revision != expected:
            raise ReplayError(
                record_id, "gap", f"expected revision {expected}, found {revision}"
            )
        raw = (record_dir / name).read_bytes()
        if _CONFLICT_MARKER.search(raw):
            raise ReplayError(record_id, "conflict", f"git conflict markers in {name}")
        try:
            event = loads_strict(raw)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ReplayError(record_id, "parse", f"{name}: {exc}") from None
        if strict and raw != canonical_bytes(event):
            raise ReplayError(record_id, "noncanonical", name)
        pairs.append((event, raw))
    verify_events(record_id, [event for event, _ in pairs])
    return pairs


class RecordStore:
    """Read and write the records of one scope in one store root."""

    def __init__(
        self,
        root: str | Path,
        scope: Scope,
        *,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.root = Path(root)
        self.scope = scope
        self.schemas = SchemaRegistry(self.root)
        self.policies = PolicyStore(self.schemas)
        self._clock = clock or utc_now
        if self.root.is_symlink():
            raise RecordsError(
                f"refusing a symlinked store root: {self.root}", code="store_path"
            )

    @classmethod
    def open(
        cls,
        scope: Scope | str,
        *,
        repo: str | Path | None = None,
        home: str | Path | None = None,
        clock: Callable[[], str] | None = None,
    ) -> "RecordStore":
        """Open the store that holds ``scope`` (see :mod:`akms_records.scope`)."""
        resolved = Scope.parse(scope) if isinstance(scope, str) else scope
        return cls(store_root(resolved, repo=repo, home=home), resolved, clock=clock)

    # ------------------------------------------------------------- plumbing
    def now(self) -> str:
        return self._clock()

    def ensure_root(self) -> None:
        """Create the root and its git attributes. Only writes call this."""
        self.root.mkdir(parents=True, exist_ok=True)
        for name, lines, header in (
            (
                ".gitattributes",
                GITATTRIBUTES_LINES,
                "# akms-records: event files are hashed, so git must not convert\n"
                "# line endings; the append-only logs merge by union.\n",
            ),
            (
                ".gitignore",
                GITIGNORE_LINES,
                "# akms-records: derived and temporary files\n",
            ),
        ):
            path = self.root / name
            present = path.read_text(encoding="utf-8") if path.is_file() else ""
            missing = [line for line in lines if line not in present.splitlines()]
            if missing:
                text = present if present else header
                if text and not text.endswith("\n"):
                    text += "\n"
                path.write_text(
                    text + "\n".join(missing) + "\n", encoding="utf-8", newline="\n"
                )

    def record_dir(self, record_id: str) -> Path:
        month, record_id = parse_record_id(record_id)
        return self.root / month / record_id

    def record_ids(self) -> list[str]:
        """Every record directory in the root, of any scope, sorted."""
        if not self.root.is_dir():
            return []
        out = []
        for month in sorted(os.listdir(self.root)):
            month_dir = self.root / month
            if not MONTH_RE.fullmatch(month) or not month_dir.is_dir():
                continue
            for name in sorted(os.listdir(month_dir)):
                if RECORD_ID_RE.fullmatch(name) and (month_dir / name).is_dir():
                    out.append(name)
        return out

    def _load(self, record_id: str) -> tuple[list[dict[str, Any]], Record]:
        directory = self.record_dir(record_id)
        if not directory.is_dir():
            raise NotFound(f"record {record_id} not found")
        events = [event for event, _ in read_event_files(directory, record_id)]
        record = fold_events(record_id, events)
        if record.scope != self.scope:
            raise ScopeViolation(f"record {record_id} is not in scope {self.scope}")
        return events, record

    def _cleanup_tmp(self, directory: Path, *, force: bool = False) -> list[str]:
        """Remove temp files whose writer is gone (or that are very old)."""
        removed: list[str] = []
        try:
            names = os.listdir(directory)
        except FileNotFoundError:
            return removed
        for name in names:
            match = TMP_RE.fullmatch(name)
            if match is None:
                continue
            path = directory / name
            try:
                age = time.time() - path.stat().st_mtime
            except FileNotFoundError:
                continue
            if (
                force
                or age > TMP_MAX_AGE_SECONDS
                or not pid_alive(int(match.group("pid")))
            ):
                try:
                    path.unlink()
                    removed.append(self._rel(path))
                except (FileNotFoundError, PermissionError):
                    pass
        return removed

    def _rel(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()

    def _schema(self, ref: str) -> RegisteredSchema:
        return self.schemas.get(self.schemas.resolve_ref(ref))

    def register_schema(
        self,
        schema: Any,
        *,
        actor: str,
        name: str | None = None,
        version: int | None = None,
    ) -> tuple[RegisteredSchema, bool]:
        """Register a schema in this store root; see :class:`SchemaRegistry`."""
        check_actor(actor)
        self.ensure_root()
        return self.schemas.register(
            schema, actor=actor, at=self.now(), name=name, version=version
        )

    # ---------------------------------------------------------------- reads
    def get(self, record_id: str) -> Record:
        """The current state of a record in this scope."""
        return self._load(record_id)[1]

    def history(self, record_id: str) -> list[dict[str, Any]]:
        """Every event of a record in this scope, oldest first."""
        return self._load(record_id)[0]

    def iter_records(self) -> Iterator[Record | ReplayError]:
        """This scope's records, plus replay errors for records that fail.

        A record whose scope cannot be read (its replay failed) is reported
        here only when its creating event names this scope or cannot be read.
        """
        for record_id in self.record_ids():
            try:
                _, record = self._load(record_id)
            except ScopeViolation:
                continue
            except ReplayError as exc:
                if self._probe_scope(record_id) in (None, self.scope):
                    yield exc
                continue
            except NotFound:
                continue
            yield record

    def _probe_scope(self, record_id: str) -> Scope | None:
        """Best-effort scope of a record that does not replay."""
        directory = self.record_dir(record_id)
        for name in sorted(os.listdir(directory)) if directory.is_dir() else []:
            if not EVENT_NAME_RE.fullmatch(name):
                continue
            try:
                event = loads_strict((directory / name).read_bytes())
                return Scope.from_json(event["body"]["envelope"]["scope"])
            except (ValueError, UnicodeDecodeError, KeyError, TypeError, RecordsError):
                continue
        return None

    # --------------------------------------------------------------- writes
    def create(
        self,
        document: dict[str, Any],
        *,
        actor: str,
        event_id: str | None = None,
    ) -> WriteResult:
        """Create a record from a writer's document.

        Retrying with the same ``event_id`` returns the first result with
        ``noop`` set and writes nothing.
        """
        check_actor(actor)
        fields = parse_record_document(document, scope=self.scope, partial=False)
        schema = self._schema(fields["schema_ref"])
        schema.validate_payload(fields["payload"])
        summary = fields.get("summary") or schema.render_summary(fields["payload"])
        if not summary:
            raise RecordsError(
                f"a summary is required: {schema.ref} declares no summary_template",
                code="invalid_record",
            )
        origin = fields.get("origin") or {
            "kind": DEFAULT_ORIGIN_KIND,
            "actor_id": actor,
        }
        body = {
            "envelope": {
                "schema_ref": schema.ref,
                "schema_sha256": schema.schema_sha256,
                "scope": self.scope.to_json(),
                "origin": origin,
                "source_refs": fields["source_refs"],
                "summary": summary,
                "tags": fields["tags"],
                "sensitivity": fields["sensitivity"],
                "review_state": fields["review_state"],
            },
            "payload": fields["payload"],
        }
        event_id = check_event_id(event_id or new_event_id())
        return self._create_event(body, actor=actor, event_id=event_id)

    def _existing_create(self, record_id: str, event_id: str) -> bool:
        """Whether ``record_id`` was created by ``event_id`` (scope-checked)."""
        first = self.record_dir(record_id) / "000001.json"
        try:
            event = loads_strict(first.read_bytes())
        except FileNotFoundError:
            return False
        except (ValueError, UnicodeDecodeError):
            return False
        if not isinstance(event, dict) or event.get("event_id") != event_id:
            return False
        try:
            scope = Scope.from_json(event["body"]["envelope"]["scope"])
        except (KeyError, TypeError, RecordsError):
            scope = None
        if scope != self.scope:
            raise RecordsError(
                f"event ID {event_id} was already used in another scope",
                code="event_id_reused",
            )
        return True

    def _create_event(
        self, body: dict[str, Any], *, actor: str, event_id: str
    ) -> WriteResult:
        at = self.now()
        day = day_of(at)
        # A retry that crosses midnight UTC derives its ID from the new day;
        # look for the first attempt on the previous day before allocating.
        for attempt in range(RETRY_LOOKBACK_ATTEMPTS):
            earlier = record_id_for(previous_day(day), event_id, attempt)
            if self._existing_create(earlier, event_id):
                return WriteResult("create", earlier, 1, event_id, noop=True)
        self.ensure_root()
        for attempt in range(CREATE_ATTEMPTS):
            record_id = record_id_for(day, event_id, attempt)
            directory = self.record_dir(record_id)
            directory.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.mkdir(directory)
                fsync_dir(directory.parent)
            except FileExistsError:
                pass
            if (directory / "000001.json").exists():
                if self._existing_create(record_id, event_id):
                    return WriteResult("create", record_id, 1, event_id, noop=True)
                continue  # an unrelated record already has this ID
            event = make_event(
                record_id=record_id,
                revision=1,
                kind="create",
                at=at,
                actor=actor,
                prev_sha256=None,
                body=body,
                event_id=event_id,
            )
            try:
                write_exclusive(directory, "000001.json", canonical_bytes(event))
            except FileExistsError:
                if self._existing_create(record_id, event_id):
                    return WriteResult("create", record_id, 1, event_id, noop=True)
                continue
            return WriteResult("create", record_id, 1, event_id)
        raise RecordsError("could not allocate a record ID", code="id_exhausted")

    def _append(
        self,
        record_id: str,
        kind: str,
        build_body: Callable[[Record], dict[str, Any]],
        *,
        expected_revision: int,
        actor: str,
        event_id: str | None,
    ) -> WriteResult:
        check_actor(actor)
        event_id = check_event_id(event_id or new_event_id())
        if type(expected_revision) is not int or expected_revision < 1:
            raise RecordsError(
                "expected revision must be a positive integer", code="usage"
            )
        directory = self.record_dir(record_id)
        if not directory.is_dir():
            raise NotFound(f"record {record_id} not found")
        events, record = self._load(record_id)
        for event in events:
            if event["event_id"] == event_id:
                if event["kind"] != kind:
                    raise RecordsError(
                        f"event ID {event_id} was already used for a {event['kind']}",
                        code="event_id_reused",
                    )
                return WriteResult(
                    kind, record_id, event["revision"], event_id, noop=True
                )
        head = len(events)
        if expected_revision != head:
            raise StaleRevision(
                record_id, expected=expected_revision, head=head, where="precheck"
            )
        if record.lifecycle != "active":
            raise RecordsError(
                f"record {record_id} is {record.lifecycle}; only active records "
                f"accept {kind}",
                code="not_active",
            )
        if head >= MAX_REVISION:
            raise RecordsError(f"record {record_id} is full", code="revision_limit")
        body = build_body(record)
        self._cleanup_tmp(directory)
        event = make_event(
            record_id=record_id,
            revision=head + 1,
            kind=kind,
            at=self.now(),
            actor=actor,
            prev_sha256=digest(events[-1]),
            body=body,
            event_id=event_id,
        )
        name = f"{head + 1:06d}.json"
        try:
            write_exclusive(directory, name, canonical_bytes(event))
        except FileExistsError:
            try:
                other = loads_strict((directory / name).read_bytes())
            except (OSError, ValueError, UnicodeDecodeError):
                other = None
            if isinstance(other, dict) and other.get("event_id") == event_id:
                return WriteResult(kind, record_id, head + 1, event_id, noop=True)
            raise StaleRevision(
                record_id, expected=expected_revision, head=head + 1, where="link"
            ) from None
        return WriteResult(kind, record_id, head + 1, event_id)

    def amend(
        self,
        record_id: str,
        document: dict[str, Any],
        *,
        expected_revision: int,
        actor: str,
        event_id: str | None = None,
    ) -> WriteResult:
        """Append an amendment. Fields absent from ``document`` keep their value."""
        fields = parse_record_document(document, scope=self.scope, partial=True)
        if not fields:
            raise RecordsError(
                "an amendment must change something", code="invalid_record"
            )

        def build(record: Record) -> dict[str, Any]:
            merged = {**record.writer_fields(), **fields}
            schema = self._schema(merged["schema_ref"])
            schema.validate_payload(merged["payload"])
            return {
                "envelope": {
                    "schema_ref": schema.ref,
                    "schema_sha256": schema.schema_sha256,
                    "scope": self.scope.to_json(),
                    "origin": merged["origin"],
                    "source_refs": merged["source_refs"],
                    "summary": merged["summary"],
                    "tags": merged["tags"],
                    "sensitivity": merged["sensitivity"],
                    "review_state": merged["review_state"],
                },
                "payload": merged["payload"],
            }

        return self._append(
            record_id,
            "amend",
            build,
            expected_revision=expected_revision,
            actor=actor,
            event_id=event_id,
        )

    def retract(
        self,
        record_id: str,
        *,
        expected_revision: int,
        reason: str,
        actor: str,
        event_id: str | None = None,
    ) -> WriteResult:
        """Mark a record retracted. Its history stays."""
        text = _reason(reason, required=True)
        return self._append(
            record_id,
            "retract",
            lambda _record: {"reason": text},
            expected_revision=expected_revision,
            actor=actor,
            event_id=event_id,
        )

    def supersede(
        self,
        record_id: str,
        *,
        expected_revision: int,
        actor: str,
        by: str | None = None,
        document: dict[str, Any] | None = None,
        reason: str | None = None,
        event_id: str | None = None,
    ) -> dict[str, Any]:
        """Mark a record superseded by another record of the same scope.

        Give ``by`` for an existing record, or ``document`` to create the
        successor first. The successor's create uses the event ID
        ``<event_id>.new``, so retrying the whole operation with the same
        ``event_id`` repeats neither write.
        """
        if (by is None) == (document is None):
            raise RecordsError("give exactly one of by or document", code="usage")
        text = _reason(reason, required=False)
        event_id = check_event_id(event_id or new_event_id())
        events, record = self._load(record_id)
        done = next((e for e in events if e["event_id"] == event_id), None)
        created: WriteResult | None = None
        if done is not None and done["kind"] != "supersede":
            raise RecordsError(
                f"event ID {event_id} was already used for a {done['kind']}",
                code="event_id_reused",
            )
        if done is None:
            if expected_revision != len(events):
                raise StaleRevision(
                    record_id,
                    expected=expected_revision,
                    head=len(events),
                    where="precheck",
                )
            if record.lifecycle != "active":
                raise RecordsError(
                    f"record {record_id} is {record.lifecycle}", code="not_active"
                )
        if document is not None:
            successor = dict(document)
            refs = list(successor.get("source_refs", []))
            link = {"kind": "supersedes", "ref": record_id}
            if link not in refs:
                refs.append(link)
            successor["source_refs"] = refs
            created = self.create(
                successor, actor=actor, event_id=check_event_id(f"{event_id}.new")
            )
            by = created.record_id
        assert by is not None
        if by == record_id:
            raise RecordsError(
                "a record cannot supersede itself", code="invalid_record"
            )
        successor_record = self.get(by)  # exists and is in this scope
        if successor_record.lifecycle != "active" and done is None:
            raise RecordsError(f"successor {by} is not active", code="not_active")
        result = self._append(
            record_id,
            "supersede",
            lambda _record: {"superseded_by": by, "reason": text},
            expected_revision=expected_revision,
            actor=actor,
            event_id=event_id,
        )
        if done is not None:
            by = done["body"]["superseded_by"]  # report what the first attempt did
        out = {"superseded": result.to_json(), "superseded_by": by}
        if created is not None:
            out["created"] = created.to_json()
        return out

    # -------------------------------------------------------------- erasure
    def erasure_entries(self) -> tuple[list[dict[str, Any]], list[int]]:
        """The erasure log's entries, and the numbers of unreadable lines."""
        path = self.root / ERASURE_LOG
        if not path.is_file():
            return [], []
        entries, bad = [], []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                entry = loads_strict(line)
                parse_record_id(entry["record_id"])
            except (ValueError, KeyError, TypeError, RecordsError):
                bad.append(number)
                continue
            entries.append(entry)
        return entries, bad

    def erase(
        self, record_id: str, *, reason: str, actor: str, force: bool = False
    ) -> dict[str, Any]:
        """Remove a record's files and log a content-free erasure line.

        The log line holds the record ID, scope, time, actor and reason, never
        record content: do not put protected content in the reason. ``force``
        erases a record whose scope cannot be determined because it does not
        replay; a record that names another scope is never erased from here.
        """
        check_actor(actor)
        text = _reason(reason, required=True)
        directory = self.record_dir(record_id)
        if not directory.is_dir():
            raise NotFound(f"record {record_id} not found")
        try:
            _, record = self._load(record_id)
            scope: Scope | None = record.scope
        except ReplayError:
            scope = self._probe_scope(record_id)
            if scope is None and not force:
                raise RecordsError(
                    f"record {record_id} does not replay and its scope is unknown; "
                    "pass --force to erase it anyway",
                    code="scope_unknown",
                ) from None
        if scope is not None and scope != self.scope:
            raise ScopeViolation(f"record {record_id} is not in scope {self.scope}")
        entry = {
            "record_id": record_id,
            "scope": str(self.scope),
            "at": self.now(),
            "actor": actor,
            "reason": text,
        }
        # Log first: an interrupted erasure is finished by doctor.
        self.ensure_root()
        append_line(self.root / ERASURE_LOG, compact_line(entry))
        removed = self._remove_record_dir(directory)
        return {
            "record_id": record_id,
            "files_removed": removed,
            "logged": entry,
            "not_reached": list(NOT_REACHED),
        }

    def _remove_record_dir(self, directory: Path) -> int:
        count = sum(1 for _ in directory.iterdir()) if directory.is_dir() else 0
        shutil.rmtree(directory, ignore_errors=False)
        fsync_dir(directory.parent)
        try:
            directory.parent.rmdir()  # only succeeds when the month is now empty
        except OSError:
            pass
        return count

    # --------------------------------------------------------------- doctor
    def doctor(self, *, fix: bool = True, force_tmp: bool = False) -> dict[str, Any]:
        """Check the whole store root and, with ``fix``, clean it up.

        Fixes: remove temp files of dead writers (all of them with
        ``force_tmp``, which is only safe when no writer is running), remove
        empty record and month directories, and re-apply logged erasures, for
        example after a merge brought an erased record back. Never fixed, only
        reported: replay errors, git conflicts, schema digest problems, and
        policy files that disagree with their log.

        Doctor is store-wide maintenance: it covers every scope in the root.
        """
        report: dict[str, Any] = {
            "fixed": fix,
            "tmp_files": [],
            "tmp_removed": [],
            "empty_dirs": [],
            "empty_dirs_removed": [],
            "stray_files": [],
            "noncanonical": [],
            "replay_errors": {},
            "conflicts": [],
            "erased_but_present": [],
            "erasures_reapplied": [],
            "erasure_log_errors": [],
            "schema_errors": {},
            "schema_mismatch": [],
            "policy_drift": {},
            "records_checked": 0,
        }
        if not self.root.is_dir():
            report["status"] = "ok"
            return report
        entries, bad_lines = self.erasure_entries()
        report["erasure_log_errors"] = bad_lines
        erased = sorted({entry["record_id"] for entry in entries})
        for record_id in erased:
            directory = self.record_dir(record_id)
            if directory.exists():
                report["erased_but_present"].append(record_id)
                if fix:
                    self._remove_record_dir(directory)
                    report["erasures_reapplied"].append(record_id)
        schema_digests: dict[str, str] = {}
        for ref, loaded in self.schemas.iter_checked():
            if isinstance(loaded, RecordsError):
                report["schema_errors"][ref] = f"{loaded.code}: {loaded}"
            else:
                schema_digests[ref] = loaded.schema_sha256
        for name in os.listdir(self.root):
            path = self.root / name
            if name in ROOT_ENTRIES or (MONTH_RE.fullmatch(name) and path.is_dir()):
                continue
            if TMP_RE.fullmatch(name):
                report["tmp_files"].append(name)
                if fix:
                    report["tmp_removed"] += self._cleanup_tmp(
                        self.root, force=force_tmp
                    )
                continue
            report["stray_files"].append(name)
        for month in sorted(os.listdir(self.root)):
            month_dir = self.root / month
            if not MONTH_RE.fullmatch(month) or not month_dir.is_dir():
                continue
            for name in sorted(os.listdir(month_dir)):
                directory = month_dir / name
                if not RECORD_ID_RE.fullmatch(name) or not directory.is_dir():
                    report["stray_files"].append(self._rel(directory))
                    continue
                if name in erased and not fix:
                    continue  # reported under erased_but_present
                self._doctor_record(
                    directory, name, report, fix, force_tmp, schema_digests
                )
            if fix and month_dir.is_dir() and not os.listdir(month_dir):
                month_dir.rmdir()
                report["empty_dirs_removed"].append(month)
        for name in self.schemas.names():
            problem = self.policies.drift(name)
            if problem:
                report["policy_drift"][name] = problem
        pending = (
            report["tmp_files"]
            if not fix
            else [p for p in report["tmp_files"] if p not in report["tmp_removed"]]
        )
        errors = (
            report["replay_errors"]
            or report["schema_errors"]
            or report["schema_mismatch"]
            or report["erasure_log_errors"]
            or report["policy_drift"]
        )
        needs_fix = (not fix) and (
            pending or report["empty_dirs"] or report["erased_but_present"]
        )
        report["status"] = "error" if errors else "drift" if needs_fix else "ok"
        return report

    def _doctor_record(
        self,
        directory: Path,
        record_id: str,
        report: dict[str, Any],
        fix: bool,
        force_tmp: bool,
        schema_digests: dict[str, str],
    ) -> None:
        names = os.listdir(directory)
        for name in names:
            if TMP_RE.fullmatch(name):
                report["tmp_files"].append(self._rel(directory / name))
            elif not EVENT_NAME_RE.fullmatch(name):
                report["stray_files"].append(self._rel(directory / name))
        if fix:
            report["tmp_removed"] += self._cleanup_tmp(directory, force=force_tmp)
        if not any(EVENT_NAME_RE.fullmatch(name) for name in os.listdir(directory)):
            age = time.time() - directory.stat().st_mtime
            leftovers = os.listdir(directory)
            if fix and not leftovers and (force_tmp or age > EMPTY_DIR_GRACE_SECONDS):
                directory.rmdir()
                report["empty_dirs_removed"].append(self._rel(directory))
            else:
                report["empty_dirs"].append(self._rel(directory))
            return
        report["records_checked"] += 1
        try:
            pairs = read_event_files(directory, record_id)
            record = fold_events(record_id, [event for event, _ in pairs])
        except ReplayError as exc:
            report["replay_errors"][record_id] = {
                "code": exc.replay_code,
                "detail": exc.detail,
            }
            if exc.replay_code == "conflict":
                report["conflicts"].append(record_id)
            return
        for event, raw in pairs:
            if raw != canonical_bytes(event):
                report["noncanonical"].append(
                    self._rel(directory / f"{event['revision']:06d}.json")
                )
        registered = schema_digests.get(record.schema_ref)
        if registered is not None and registered != record.schema_sha256:
            report["schema_mismatch"].append(record_id)


__all__ = [
    "EVENT_FORMAT",
    "EVENT_KINDS",
    "RecordStore",
    "WriteResult",
    "fold_events",
    "make_event",
    "read_event_files",
    "seal_of",
    "verify_events",
]
