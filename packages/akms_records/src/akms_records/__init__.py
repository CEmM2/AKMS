"""Experimental schema-driven, provenance-aware record store for AKMS.

Records are typed experiences or observations (decisions, findings, lessons,
preferences), not established knowledge. Each is a fixed envelope around a
payload described by a locally registered JSON Schema, kept as an append-only
history of event files that merges cleanly in git.

A derived SQLite index (FTS5) answers scoped ``recall`` and token-budgeted
``wake`` queries without rebuilding anything. Optional ``consolidate``
summaries are records too; each assertion cites the source revisions it came
from, and a summary turns stale when a source changes.

Importing this package does not import ``akms``. The optional ``[akms]`` extra
enables ``promote``, which writes a reviewed record as an AKMS project-local
node; ``import_failure_memory`` reads a failure-memory registry without
needing that package at all.
"""

from akms_records.bridge import confirm_yes, promote
from akms_records.consolidate import (
    command_summarizer,
    consolidate,
    consolidation_status,
    list_consolidations,
    refresh_consolidation,
)
from akms_records.envelope import ENVELOPE_KEYS, Record
from akms_records.errors import (
    IndexUnavailable,
    NotFound,
    RecordsError,
    ReplayError,
    ScopeViolation,
    StaleRevision,
)
from akms_records.failure_memory import import_failure_memory
from akms_records.query import (
    RecallHit,
    RecallResult,
    WakeEntry,
    WakeResult,
    manifest_nodes,
    wake,
)
from akms_records.schemas import RegisteredSchema, SchemaRegistry
from akms_records.scope import Scope, store_root
from akms_records.store import RecordStore, WriteResult

__version__ = "0.3.2"

__all__ = [
    "ENVELOPE_KEYS",
    "IndexUnavailable",
    "NotFound",
    "RecallHit",
    "RecallResult",
    "Record",
    "RecordStore",
    "RecordsError",
    "RegisteredSchema",
    "ReplayError",
    "SchemaRegistry",
    "Scope",
    "ScopeViolation",
    "StaleRevision",
    "WakeEntry",
    "WakeResult",
    "WriteResult",
    "__version__",
    "command_summarizer",
    "confirm_yes",
    "consolidate",
    "consolidation_status",
    "import_failure_memory",
    "list_consolidations",
    "manifest_nodes",
    "promote",
    "refresh_consolidation",
    "store_root",
    "wake",
]
