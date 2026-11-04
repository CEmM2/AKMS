"""The derived SQLite index of one store root.

The index lives at ``<root>/.index/records.sqlite`` (WAL mode), is ignored by
git, and can always be rebuilt from the event files. It holds one row per
record that replays, for every scope in the root:

* ``records``: the current state's metadata (head revision and digest, scope,
  schema ref and digests, review state, lifecycle, sensitivity, times, origin,
  tags, source refs, supersession links, label and summary);
* ``record_tags``: one row per tag, for exact tag filters;
* ``records_fts``: an FTS5 table over the summary, the tags and the search
  text the schema's extraction rules select;
* ``files``, ``months``, ``rules`` and ``meta``: bookkeeping for the
  staleness check (directory signatures, rules digests, git and erasure-log
  signatures). They are not part of the record rows.

**Writes.** Every write through :class:`~akms_records.store.RecordStore`
updates the index after the event file is linked. An update is accepted only
when it carries a higher revision than the indexed one, so writers that race
cannot move the index backwards. A writer first drops a *pending marker* in
``.index/pending/`` and removes it once the index is updated; a writer that
dies in between leaves the marker, and the next read reconciles that record.

**Reads.** Before every read, :meth:`RecordIndex.refresh` runs a cheap
staleness check: one ``stat`` per month directory, the pending markers, the
signature of the worktree's git index and ``HEAD``, the erasure log, and the
rules file of every indexed schema version. Only what changed is
reconciled: a changed month directory is rescanned (one ``stat`` per record
directory), and only records whose directory changed are replayed. A changed
git signature (checkout, merge, reset, commit) rescans every month. A changed
rules digest re-extracts the records of that schema version.

Directory times have a coarse resolution on some filesystems, so a signature
taken less than two seconds after the directory changed is not trusted: it is
stored as unknown and rechecked on the next read.

The cheap check covers changes made through the API and through git. Files
copied or edited by other means need ``akms-records index reconcile`` (or
``doctor --fix``), which replays every record.

**Erasure.** The connection runs with ``PRAGMA secure_delete=ON`` and the
FTS5 table with its ``secure-delete`` option, so deleted rows are
overwritten, and every deletion ends with a ``wal_checkpoint(TRUNCATE)``.
Where the SQLite library predates FTS5 ``secure-delete`` (3.42), deletions
also run the FTS5 ``optimize`` command and ``VACUUM``.
"""

from __future__ import annotations

import os
import re
import secrets
import sqlite3
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from akms_records.canonical import compact_line, digest
from akms_records.envelope import Record
from akms_records.errors import IndexUnavailable, NotFound, RecordsError, ReplayError
from akms_records.ids import RECORD_ID_RE
from akms_records.procs import pid_alive
from akms_records.schemas import REF_RE, SchemaRegistry, pointer_text, pointer_value

INDEX_DIRNAME = ".index"
INDEX_FILENAME = "records.sqlite"
PENDING_DIRNAME = "pending"
INDEX_FORMAT = "akms-records-index/v1"
MONTH_RE = re.compile(r"[0-9]{4}-[0-9]{2}")
MARKER_RE = re.compile(
    r"(?P<target>rec-[0-9]{8}-[0-9a-hjkmnp-tv-z]{8}|month-[0-9]{4}-[0-9]{2})"
    r"\.(?P<pid>[0-9]+)\.(?P<rand>[0-9a-f]{8})\.pending"
)
# A directory signature younger than this is not trusted (coarse mtimes).
RACY_NS = 2_000_000_000
MARKER_MAX_AGE_SECONDS = 3600.0
REVIEW_RANK = {"rejected": 0, "unreviewed": 1, "agent_reviewed": 2, "user_confirmed": 3}

RECORD_COLUMNS = (
    "record_id",
    "revision",
    "head_sha256",
    "scope",
    "schema_ref",
    "schema_name",
    "schema_sha256",
    "rules_sha256",
    "review_state",
    "review_rank",
    "lifecycle",
    "sensitivity",
    "recorded_at",
    "updated_at",
    "record_time",
    "time_value",
    "origin_kind",
    "origin_actor",
    "tags",
    "source_refs",
    "superseded_by",
    "supersedes",
    "label",
    "summary",
)

_TABLES = ("meta", "records", "record_tags", "files", "months", "rules", "records_fts")
_SCHEMA_SQL = """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
CREATE TABLE records(
  rid INTEGER PRIMARY KEY,
  record_id TEXT NOT NULL UNIQUE,
  revision INTEGER NOT NULL,
  head_sha256 TEXT NOT NULL,
  scope TEXT NOT NULL,
  schema_ref TEXT NOT NULL,
  schema_name TEXT NOT NULL,
  schema_sha256 TEXT NOT NULL,
  rules_sha256 TEXT NOT NULL,
  review_state TEXT NOT NULL,
  review_rank INTEGER NOT NULL,
  lifecycle TEXT NOT NULL,
  sensitivity TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  record_time TEXT,
  time_value TEXT NOT NULL,
  origin_kind TEXT NOT NULL,
  origin_actor TEXT NOT NULL,
  tags TEXT NOT NULL,
  source_refs TEXT NOT NULL,
  superseded_by TEXT,
  supersedes TEXT NOT NULL,
  label TEXT,
  summary TEXT NOT NULL
);
CREATE INDEX records_scope ON records(scope, lifecycle, recorded_at);
CREATE INDEX records_schema ON records(schema_ref, rules_sha256);
CREATE TABLE record_tags(
  tag TEXT NOT NULL, record_id TEXT NOT NULL, PRIMARY KEY(tag, record_id)
) WITHOUT ROWID;
CREATE INDEX record_tags_record ON record_tags(record_id);
CREATE TABLE files(
  record_id TEXT PRIMARY KEY, month TEXT NOT NULL, sig TEXT
) WITHOUT ROWID;
CREATE INDEX files_month ON files(month);
CREATE TABLE months(month TEXT PRIMARY KEY, sig TEXT) WITHOUT ROWID;
CREATE TABLE rules(
  schema_ref TEXT PRIMARY KEY, rules_sha256 TEXT NOT NULL, sig TEXT NOT NULL
) WITHOUT ROWID;
CREATE VIRTUAL TABLE records_fts USING fts5(summary, tags, text, tokenize='unicode61');
"""

_FTS5_CHECKED: bool | None = None


def fts5_available() -> bool:
    """Whether this Python's ``sqlite3`` has the FTS5 module."""
    global _FTS5_CHECKED
    if _FTS5_CHECKED is None:
        probe = sqlite3.connect(":memory:")
        try:
            probe.execute("CREATE VIRTUAL TABLE probe USING fts5(x)")
            _FTS5_CHECKED = True
        except sqlite3.OperationalError:
            _FTS5_CHECKED = False
        finally:
            probe.close()
    return _FTS5_CHECKED


def require_fts5() -> None:
    if not fts5_available():
        raise IndexUnavailable(
            f"the Python sqlite3 module (SQLite {sqlite3.sqlite_version}) was built "
            "without FTS5; recall, wake and the index need it. The event files "
            "are unaffected.",
            code="fts5_unavailable",
        )


def format_time(moment: datetime) -> str:
    """``YYYY-MM-DDTHH:MM:SS.ffffffZ`` in UTC, the store's timestamp form."""
    moment = moment.astimezone(UTC)
    return (
        f"{moment.year:04d}-{moment.month:02d}-{moment.day:02d}T"
        f"{moment.hour:02d}:{moment.minute:02d}:{moment.second:02d}."
        f"{moment.microsecond:06d}Z"
    )


def normalize_time(value: Any) -> str | None:
    """An ISO 8601 date or date-time as a UTC timestamp, or ``None``.

    A date means midnight UTC; a time without an offset is taken as UTC.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    try:
        return format_time(parsed)
    except (OverflowError, ValueError):
        return None


@dataclass(frozen=True)
class IndexRow:
    """One record's index content: the ``records`` row, its tags and FTS text."""

    values: tuple[Any, ...]
    tags: tuple[str, ...]
    fts: tuple[str, str, str]

    @property
    def record_id(self) -> str:
        return self.values[0]

    @property
    def revision(self) -> int:
        return self.values[1]


def build_row(record: Record, rules: dict[str, Any], rules_sha256: str) -> IndexRow:
    """The index row for ``record`` under ``rules``. Pure: no I/O."""
    payload = record.payload
    search = [
        text
        for pointer in rules.get("search_text", [])
        if (text := pointer_text(payload, pointer))
    ]
    label = pointer_text(payload, rules["label"]) if "label" in rules else ""
    record_time = None
    if "time_field" in rules:
        record_time = normalize_time(pointer_value(payload, rules["time_field"]))
    time_value = record_time or normalize_time(record.recorded_at) or record.recorded_at
    match = REF_RE.fullmatch(record.schema_ref)
    schema_name = match.group(1) if match else record.schema_ref
    supersedes = sorted(
        {
            ref["ref"]
            for ref in record.source_refs
            if ref.get("kind") == "supersedes" and RECORD_ID_RE.fullmatch(ref["ref"])
        }
    )
    values = (
        record.record_id,
        record.revision,
        record.head_sha256,
        str(record.scope),
        record.schema_ref,
        schema_name,
        record.schema_sha256,
        rules_sha256,
        record.review_state,
        REVIEW_RANK[record.review_state],
        record.lifecycle,
        record.sensitivity,
        record.recorded_at,
        record.updated_at,
        record_time,
        time_value,
        record.origin["kind"],
        record.origin["actor_id"],
        compact_line(list(record.tags)),
        compact_line(record.source_refs),
        record.superseded_by,
        compact_line(supersedes),
        label or None,
        record.summary,
    )
    return IndexRow(
        values,
        tuple(sorted(set(record.tags))),
        (record.summary, " ".join(record.tags), "\n".join(search)),
    )


def _file_sig(path: Path) -> str:
    try:
        st = os.stat(path)
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "unreadable"
    return f"{st.st_mtime_ns}:{st.st_size}:{st.st_ino}"


def _settled(sig: str, mtime_ns: int, now_ns: int) -> str | None:
    """``sig``, or ``None`` when the change it reflects is too recent to trust."""
    return sig if now_ns - mtime_ns >= RACY_NS else None


def find_git_dir(start: Path) -> Path | None:
    """The git directory of the worktree that contains ``start``, if any."""
    try:
        current = start.resolve()
    except OSError:
        return None
    for folder in (current, *current.parents):
        dot = folder / ".git"
        if dot.is_dir():
            return dot
        if dot.is_file():
            try:
                text = dot.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            if text.startswith("gitdir:"):
                target = Path(text[len("gitdir:") :].strip())
                return target if target.is_absolute() else (folder / target)
            return None
    return None


class RecordIndex:
    """The derived index of one store root (see the module docstring).

    ``replay`` returns a record's current state from its files, whatever its
    scope, and raises :class:`NotFound` or :class:`ReplayError`. ``erased``
    returns the IDs in the erasure log; those records are never indexed.
    ``create=False`` opens an existing index without changing its tables, for
    a report that must not modify anything.
    """

    def __init__(
        self,
        root: Path,
        *,
        schemas: SchemaRegistry,
        replay: Callable[[str], Record],
        erased: Callable[[], set[str]],
        erasure_log: Path,
        create: bool = True,
    ) -> None:
        require_fts5()
        self.root = Path(root)
        self.directory = self.root / INDEX_DIRNAME
        self.path = self.directory / INDEX_FILENAME
        self.pending = self.directory / PENDING_DIRNAME
        self._schemas = schemas
        self._replay = replay
        self._erased = erased
        self._erasure_log = erasure_log
        self._rules_cache: dict[str, tuple[str, dict[str, Any], str]] = {}
        self._git_dir = find_git_dir(self.root)
        if not create and not self.path.is_file():
            raise IndexUnavailable(f"no index at {self.path}", code="index_absent")
        try:
            if create:
                self.directory.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(self.path, timeout=60, isolation_level=None)
        except (OSError, sqlite3.Error) as exc:
            raise IndexUnavailable(
                f"cannot open the index {self.path}: {exc}"
            ) from None
        try:
            self.db.execute("PRAGMA busy_timeout=60000")
            self.db.execute("PRAGMA secure_delete=ON")
            if create:
                self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=NORMAL")
            self._ensure_schema(create=create)
        except sqlite3.Error as exc:
            self.db.close()
            raise IndexUnavailable(f"cannot use the index {self.path}: {exc}") from None
        except BaseException:
            self.db.close()
            raise

    # ------------------------------------------------------------ plumbing
    def close(self) -> None:
        self.db.close()

    def _meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def _current_format(self) -> str | None:
        try:
            return self._meta("format")
        except sqlite3.OperationalError:
            return None

    def _ensure_schema(self, *, create: bool) -> None:
        if self._current_format() == INDEX_FORMAT:
            self.fts_secure_delete = self._meta("fts_secure_delete") == "1"
            return
        if not create:
            raise IndexUnavailable(
                f"the index {self.path} has another format; rebuild it",
                code="index_format",
            )
        self._begin()
        try:
            # Another process may have created the tables while this one
            # waited for the write lock: look again before dropping anything.
            if self._current_format() == INDEX_FORMAT:
                self.fts_secure_delete = self._meta("fts_secure_delete") == "1"
            else:
                self._create_tables()
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _create_tables(self) -> None:
        """Drop and recreate every table, inside the caller's transaction."""
        for table in _TABLES:
            self.db.execute(f"DROP TABLE IF EXISTS {table}")
        for statement in _SCHEMA_SQL.split(";"):
            if statement.strip():
                self.db.execute(statement)
        try:
            self.db.execute(
                "INSERT INTO records_fts(records_fts, rank) VALUES('secure-delete', 1)"
            )
            secure = True
        except sqlite3.OperationalError:
            secure = False  # SQLite < 3.42: deletions run optimize and VACUUM
        self.fts_secure_delete = secure
        self._set_meta("format", INDEX_FORMAT)
        self._set_meta("fts_secure_delete", "1" if secure else "0")

    def _begin(self) -> None:
        self.db.execute("BEGIN IMMEDIATE")

    def _transaction(self, body: Callable[[], Any]) -> Any:
        self._begin()
        try:
            out = body()
            self.db.execute("COMMIT")
            return out
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    # --------------------------------------------------------------- rules
    def _rules_sig(self, ref: str) -> str:
        path = self._schemas.rules_path(ref)
        return "none" if path is None else _file_sig(path)

    def _rules_for(self, ref: str) -> tuple[dict[str, Any], str, str]:
        """The rules of ``ref``, their digest, and the rules file signature."""
        sig = self._rules_sig(ref)  # taken before reading, so a later change shows
        cached = self._rules_cache.get(ref)
        if cached is not None and cached[0] == sig and sig != "absent":
            return cached[1], cached[2], sig
        try:
            rules = self._schemas.rules(ref)
        except RecordsError:
            rules = {}  # unreadable or tampered rules: doctor reports rules_drift
        sha = digest(rules)
        self._rules_cache[ref] = (sig, rules, sha)
        return rules, sha, sig

    def row_for(self, record: Record) -> IndexRow:
        rules, sha, _ = self._rules_for(record.schema_ref)
        return build_row(record, rules, sha)

    # ------------------------------------------------------- row primitives
    def _stored(self, record_id: str) -> tuple[int, IndexRow] | None:
        row = self.db.execute(
            f"SELECT rid, {', '.join(RECORD_COLUMNS)} FROM records WHERE record_id=?",
            (record_id,),
        ).fetchone()
        if row is None:
            return None
        rid, values = row[0], tuple(row[1:])
        fts = self.db.execute(
            "SELECT summary, tags, text FROM records_fts WHERE rowid=?", (rid,)
        ).fetchone()
        tags = tuple(
            tag
            for (tag,) in self.db.execute(
                "SELECT tag FROM record_tags WHERE record_id=? ORDER BY tag",
                (record_id,),
            )
        )
        text = (str(fts[0]), str(fts[1]), str(fts[2])) if fts else ("", "", "")
        return rid, IndexRow(values, tags, text)

    def _put(self, row: IndexRow, current: tuple[int, IndexRow] | None) -> None:
        columns = ", ".join(RECORD_COLUMNS)
        if current is None:
            placeholders = ", ".join("?" for _ in RECORD_COLUMNS)
            rid = self.db.execute(
                f"INSERT INTO records({columns}) VALUES({placeholders})", row.values
            ).lastrowid
            fts_changed = True
        else:
            rid, old = current
            assignments = ", ".join(f"{name}=?" for name in RECORD_COLUMNS[1:])
            self.db.execute(
                f"UPDATE records SET {assignments} WHERE rid=?",
                (*row.values[1:], rid),
            )
            fts_changed = old.fts != row.fts
            if fts_changed:
                self.db.execute("DELETE FROM records_fts WHERE rowid=?", (rid,))
            if old.tags != row.tags:
                self.db.execute(
                    "DELETE FROM record_tags WHERE record_id=?", (row.record_id,)
                )
        if fts_changed:
            self.db.execute(
                "INSERT INTO records_fts(rowid, summary, tags, text) VALUES(?, ?, ?, ?)",
                (rid, *row.fts),
            )
        self.db.executemany(
            "INSERT OR IGNORE INTO record_tags(tag, record_id) VALUES(?, ?)",
            [(tag, row.record_id) for tag in row.tags],
        )

    def _delete(self, record_id: str) -> bool:
        found = self.db.execute(
            "SELECT rid FROM records WHERE record_id=?", (record_id,)
        ).fetchone()
        self.db.execute("DELETE FROM record_tags WHERE record_id=?", (record_id,))
        if found is None:
            return False
        self.db.execute("DELETE FROM records_fts WHERE rowid=?", (found[0],))
        self.db.execute("DELETE FROM records WHERE rid=?", (found[0],))
        return True

    def _set_file(self, record_id: str, sig: str | None) -> None:
        self.db.execute(
            "INSERT INTO files(record_id, month, sig) VALUES(?, ?, ?) "
            "ON CONFLICT(record_id) DO UPDATE SET sig=excluded.sig",
            (record_id, _month_of(record_id), sig),
        )

    def _note_rules(self, ref: str) -> None:
        """Remember ``ref``'s rules state the first time a record of it is indexed."""
        _, sha, sig = self._rules_for(ref)
        self.db.execute(
            "INSERT OR IGNORE INTO rules(schema_ref, rules_sha256, sig) VALUES(?, ?, ?)",
            (ref, sha, sig),
        )

    # -------------------------------------------------------------- writes
    def mark(self, target: str) -> Path | None:
        """Drop a pending marker before a write; ``None`` if that fails."""
        path = self.pending / f"{target}.{os.getpid()}.{secrets.token_hex(4)}.pending"
        try:
            self.pending.mkdir(parents=True, exist_ok=True)
            os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644))
        except OSError:
            return None
        return path

    @staticmethod
    def unmark(marker: Path | None) -> None:
        if marker is None:
            return
        try:
            os.unlink(marker)
        except OSError:
            pass  # a later read removes it once this process has exited

    def write(self, record: Record) -> bool:
        """Index a record a writer just wrote. Only a higher revision is accepted."""

        def body() -> bool:
            current = self._stored(record.record_id)
            if current is not None and current[1].revision >= record.revision:
                return False  # never move backwards
            self._note_rules(record.schema_ref)
            self._put(self.row_for(record), current)
            self._set_file(record.record_id, None)  # rechecked by the next rescan
            return True

        return self._transaction(body)

    # ------------------------------------------------------------- reconcile
    def _sync_record(
        self,
        record_id: str,
        sig: str | None,
        erased: set[str],
        changes: dict[str, list[str]],
    ) -> None:
        """Make the index agree with one record's files (inside a transaction)."""
        directory = self.root / _month_of(record_id) / record_id
        if record_id in erased:
            if self._delete(record_id):
                changes["removed"].append(record_id)
            self._set_file(record_id, sig)
            return
        try:
            record = self._replay(record_id)
        except (NotFound, ReplayError):
            if self._delete(record_id):
                changes["removed"].append(record_id)
            if directory.is_dir():
                self._set_file(record_id, sig)
            else:
                self.db.execute("DELETE FROM files WHERE record_id=?", (record_id,))
            return
        current = self._stored(record_id)
        self._note_rules(record.schema_ref)
        row = self.row_for(record)
        if current is None:
            self._put(row, None)
            changes["added"].append(record_id)
        elif current[1] != row:
            self._put(row, current)
            changes["updated"].append(record_id)
        self._set_file(record_id, sig)

    def _sync_month(
        self,
        month: str,
        erased: set[str],
        changes: dict[str, list[str]],
        *,
        now_ns: int,
        force: bool = False,
    ) -> set[str]:
        """Rescan one month directory; replay the records whose directory changed."""
        folder = self.root / month
        try:
            st = os.stat(folder)
        except OSError:
            st = None
        stored = dict(
            self.db.execute(
                "SELECT record_id, sig FROM files WHERE month=?", (month,)
            ).fetchall()
        )
        disk: dict[str, tuple[str, int]] = {}
        if st is not None and folder.is_dir():
            with os.scandir(folder) as entries:
                for entry in entries:
                    if RECORD_ID_RE.fullmatch(entry.name) and entry.is_dir(
                        follow_symlinks=False
                    ):
                        # On Windows a directory listing carries cached times
                        # that NTFS updates lazily; ask the directory itself.
                        mtime = (
                            os.stat(entry.path, follow_symlinks=False).st_mtime_ns
                            if os.name == "nt"
                            else entry.stat(follow_symlinks=False).st_mtime_ns
                        )
                        disk[entry.name] = (str(mtime), mtime)
        for record_id in sorted(set(disk) | set(stored)):
            seen = disk.get(record_id)
            old = stored.get(record_id)
            if not force and seen is not None and old is not None and old == seen[0]:
                continue
            sig = _settled(seen[0], seen[1], now_ns) if seen is not None else None
            self._sync_record(record_id, sig, erased, changes)
        if st is None or not folder.is_dir():
            self.db.execute("DELETE FROM months WHERE month=?", (month,))
        else:
            self.db.execute(
                "INSERT INTO months(month, sig) VALUES(?, ?) "
                "ON CONFLICT(month) DO UPDATE SET sig=excluded.sig",
                (
                    month,
                    _settled(f"{st.st_mtime_ns}:{st.st_ino}", st.st_mtime_ns, now_ns),
                ),
            )
        return set(disk)

    def _disk_months(self) -> dict[str, str]:
        out: dict[str, str] = {}
        try:
            names = os.listdir(self.root)
        except OSError:
            return out
        for name in names:
            if MONTH_RE.fullmatch(name):
                try:
                    st = os.stat(self.root / name)
                except OSError:
                    continue
                out[name] = f"{st.st_mtime_ns}:{st.st_ino}"
        return out

    def _git_sig(self) -> str:
        if self._git_dir is None or not self._git_dir.is_dir():
            # Looked up again on every check while absent: a repository may
            # be created (or a worktree moved) after the store.
            self._git_dir = find_git_dir(self.root)
        if self._git_dir is None:
            return "none"
        return "|".join(_file_sig(self._git_dir / name) for name in ("index", "HEAD"))

    def _markers(self) -> list[tuple[Path, str, bool]]:
        """Pending markers: path, target, and whether their writer is gone."""
        try:
            names = sorted(os.listdir(self.pending))
        except OSError:
            return []
        out = []
        now = time.time()
        for name in names:
            match = MARKER_RE.fullmatch(name)
            if match is None:
                continue
            path = self.pending / name
            try:
                age = now - path.stat().st_mtime
            except OSError:
                continue
            gone = age > MARKER_MAX_AGE_SECONDS or not pid_alive(int(match["pid"]))
            out.append((path, match["target"], gone))
        return out

    def _stale_rules(self) -> list[str]:
        rows = self.db.execute("SELECT schema_ref, sig FROM rules").fetchall()
        return sorted(ref for ref, sig in rows if self._rules_sig(ref) != sig)

    def _resync_rules(
        self, refs: Iterable[str], erased: set[str], changes: dict[str, list[str]]
    ) -> None:
        for ref in refs:
            _, sha, sig = self._rules_for(ref)
            stale = [
                row[0]
                for row in self.db.execute(
                    "SELECT record_id FROM records WHERE schema_ref=? "
                    "AND rules_sha256!=? ORDER BY record_id",
                    (ref, sha),
                )
            ]
            for record_id in stale:
                self._sync_record(record_id, None, erased, changes)
            self.db.execute(
                "UPDATE rules SET rules_sha256=?, sig=? WHERE schema_ref=?",
                (sha, sig, ref),
            )

    def refresh(self) -> dict[str, list[str]]:
        """The cheap staleness check; reconcile only what changed.

        Returns the record IDs it ``added``, ``updated`` and ``removed``.
        """
        changes: dict[str, list[str]] = {"added": [], "updated": [], "removed": []}
        disk = self._disk_months()
        stored = dict(self.db.execute("SELECT month, sig FROM months").fetchall())
        git_sig = self._git_sig()
        erasure_sig = _file_sig(self._erasure_log)
        markers = self._markers()
        stale_rules = self._stale_rules()
        erasure_changed = erasure_sig != self._meta("erasure_sig")
        if git_sig != self._meta("git_sig"):
            months = set(disk) | set(stored)
        else:
            months = {
                month
                for month in set(disk) | set(stored)
                if stored.get(month) is None or disk.get(month) != stored.get(month)
            }
        records = set()
        for _, target, _ in markers:
            if target.startswith("month-"):
                months.add(target[len("month-") :])
            else:
                records.add(target)
        if not (months or records or stale_rules or erasure_changed):
            return changes
        now_ns = time.time_ns()

        def body() -> None:
            erased = self._erased()
            if erasure_changed:
                for record_id in sorted(erased):
                    if self._delete(record_id):
                        changes["removed"].append(record_id)
            for month in sorted(months):
                self._sync_month(month, erased, changes, now_ns=now_ns)
            for record_id in sorted(records):
                self._sync_record(record_id, None, erased, changes)
            self._resync_rules(stale_rules, erased, changes)
            self._set_meta("git_sig", git_sig)
            self._set_meta("erasure_sig", erasure_sig)

        self._transaction(body)
        for path, _, gone in markers:
            if gone:
                self.unmark(path)
        if changes["removed"]:
            self.scrub()
        return _sorted_changes(changes)

    def reconcile(self) -> dict[str, list[str]]:
        """Replay every record and fix every difference (the thorough check)."""
        changes: dict[str, list[str]] = {"added": [], "updated": [], "removed": []}
        git_sig = self._git_sig()
        erasure_sig = _file_sig(self._erasure_log)
        markers = self._markers()
        now_ns = time.time_ns()

        def body() -> None:
            erased = self._erased()
            stored_months = {
                row[0] for row in self.db.execute("SELECT month FROM months")
            } | {row[0] for row in self.db.execute("SELECT DISTINCT month FROM files")}
            seen: set[str] = set()
            for month in sorted(set(self._disk_months()) | stored_months):
                seen |= self._sync_month(
                    month, erased, changes, now_ns=now_ns, force=True
                )
            orphans = [
                row[0]
                for row in self.db.execute("SELECT record_id FROM records")
                if row[0] not in seen
            ]
            for record_id in sorted(orphans):
                self._sync_record(record_id, None, erased, changes)
            refs = [row[0] for row in self.db.execute("SELECT schema_ref FROM rules")]
            self._resync_rules(refs, erased, changes)
            self._set_meta("git_sig", git_sig)
            self._set_meta("erasure_sig", erasure_sig)

        self._transaction(body)
        for path, _, gone in markers:
            if gone:
                self.unmark(path)
        self.scrub()
        return _sorted_changes(changes)

    def rebuild(self) -> dict[str, Any]:
        """Drop every table and index every record again from the files."""
        changes: dict[str, list[str]] = {"added": [], "updated": [], "removed": []}
        git_sig = self._git_sig()
        erasure_sig = _file_sig(self._erasure_log)
        markers = self._markers()
        now_ns = time.time_ns()
        self._rules_cache.clear()

        def body() -> None:
            self._create_tables()
            erased = self._erased()
            for month in sorted(self._disk_months()):
                self._sync_month(month, erased, changes, now_ns=now_ns, force=True)
            self._set_meta("git_sig", git_sig)
            self._set_meta("erasure_sig", erasure_sig)

        self._transaction(body)
        for path, _, gone in markers:
            if gone:
                self.unmark(path)
        checkpoint = self.scrub()
        return {"records": len(changes["added"]), "checkpoint": checkpoint}

    # ---------------------------------------------------------- comparison
    def expected_rows(
        self, replayed: dict[str, Record | None] | None = None
    ) -> tuple[dict[str, IndexRow], list[str]]:
        """What a rebuild would index now, and the records that do not replay."""
        rows: dict[str, IndexRow] = {}
        unindexable: list[str] = []
        if replayed is None:
            erased = self._erased()
            replayed = {}
            for record_id in self.disk_record_ids():
                if record_id in erased:
                    continue
                try:
                    replayed[record_id] = self._replay(record_id)
                except NotFound:
                    continue  # an empty directory is not a record
                except ReplayError:
                    replayed[record_id] = None
        for record_id, record in sorted(replayed.items()):
            if record is None:
                unindexable.append(record_id)
            else:
                rows[record_id] = self.row_for(record)
        return rows, unindexable

    def stored_rows(self) -> dict[str, IndexRow]:
        rows: dict[str, IndexRow] = {}
        for (record_id,) in self.db.execute("SELECT record_id FROM records").fetchall():
            stored = self._stored(record_id)
            if stored is not None:
                rows[record_id] = stored[1]
        return rows

    def compare(
        self, replayed: dict[str, Record | None] | None = None
    ) -> dict[str, Any]:
        """Compare the index with the files. Changes nothing."""
        self._rules_cache.clear()
        expected, unindexable = self.expected_rows(replayed)
        stored = self.stored_rows()
        missing = sorted(set(expected) - set(stored))
        extra = sorted(set(stored) - set(expected))
        stale = sorted(
            record_id
            for record_id in set(expected) & set(stored)
            if expected[record_id] != stored[record_id]
        )
        drift = bool(missing or extra or stale)
        return {
            "status": "drift" if drift else "ok",
            "records": len(expected),
            "indexed": len(stored),
            "missing": missing,
            "extra": extra,
            "stale": stale,
            "unindexable": unindexable,
        }

    def snapshot(self) -> list[tuple[Any, ...]]:
        """Every record row, tag and FTS row, keyed by record ID (no row IDs)."""
        out: list[tuple[Any, ...]] = []
        for record_id, row in sorted(self.stored_rows().items()):
            out.append(("record", *row.values))
            out.append(("fts", record_id, *row.fts))
        out.extend(
            ("tag", *row)
            for row in self.db.execute(
                "SELECT record_id, tag FROM record_tags ORDER BY record_id, tag"
            )
        )
        out.extend(
            ("rules", *row)
            for row in self.db.execute(
                "SELECT schema_ref, rules_sha256 FROM rules ORDER BY schema_ref"
            )
        )
        return out

    def disk_record_ids(self) -> list[str]:
        out: list[str] = []
        for month in sorted(self._disk_months()):
            try:
                names = sorted(os.listdir(self.root / month))
            except OSError:
                continue
            out.extend(
                name
                for name in names
                if RECORD_ID_RE.fullmatch(name) and (self.root / month / name).is_dir()
            )
        return out

    # -------------------------------------------------------------- erasure
    def purge(self, record_id: str) -> dict[str, Any]:
        """Remove a record's rows so that none of its bytes stay in the files."""

        def body() -> bool:
            removed = self._delete(record_id)
            self.db.execute("DELETE FROM files WHERE record_id=?", (record_id,))
            return removed

        removed = self._transaction(body)
        return {"rows_removed": removed, "checkpoint": self.scrub()}

    def scrub(self) -> str:
        """Flush deleted content out of the WAL; ``complete`` or ``busy``."""
        if not self.fts_secure_delete:
            self.db.execute("INSERT INTO records_fts(records_fts) VALUES('optimize')")
            self.db.execute("VACUUM")
        busy, _, _ = self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        return "complete" if busy == 0 else "busy"


def _month_of(record_id: str) -> str:
    match = RECORD_ID_RE.fullmatch(record_id)
    if match is None:
        raise RecordsError(f"invalid record ID {record_id!r}", code="invalid_record_id")
    return f"{match.group(1)}-{match.group(2)}"


def _sorted_changes(changes: dict[str, list[str]]) -> dict[str, list[str]]:
    return {key: sorted(set(value)) for key, value in changes.items()}


__all__ = [
    "INDEX_FORMAT",
    "IndexRow",
    "RECORD_COLUMNS",
    "REVIEW_RANK",
    "RecordIndex",
    "build_row",
    "fts5_available",
    "normalize_time",
]
