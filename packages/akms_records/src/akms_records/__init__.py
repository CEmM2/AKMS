"""Experimental schema-driven, provenance-aware record store for AKMS.

Records are typed experiences or observations (decisions, findings, lessons,
preferences), not established knowledge. Each is a fixed envelope around a
payload described by a locally registered JSON Schema, kept as an append-only
history of event files that merges cleanly in git.

A derived SQLite index (FTS5) answers scoped ``recall`` and token-budgeted
``wake`` queries without rebuilding anything.

This package does not import ``akms``. The optional ``[akms]`` extra is
reserved for a later promotion bridge into AKMS project-local nodes.
"""

from akms_records.envelope import ENVELOPE_KEYS, Record
from akms_records.errors import (
    IndexUnavailable,
    NotFound,
    RecordsError,
    ReplayError,
    ScopeViolation,
    StaleRevision,
)
from akms_records.query import RecallHit, RecallResult, WakeEntry, WakeResult, wake
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
    "store_root",
    "wake",
]
