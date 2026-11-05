"""Record and event identifiers.

A record ID is ``rec-<YYYYMMDD>-<8 Crockford base32 characters>``. The date is
the UTC day of the creating event. The eight characters (40 bits) come from
``sha256("<event_id>:<k>")``, where ``k`` counts allocation retries. Deriving
them from the event ID makes a retried create land on the same record
directory, so the retry is recognised and does nothing; 40 bits keep separate
clones from picking the same ID for unrelated records.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import date, timedelta

from akms_records.errors import RecordsError

CROCKFORD_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
SUFFIX_LENGTH = 8
RECORD_ID_RE = re.compile(r"rec-([0-9]{4})([0-9]{2})([0-9]{2})-([0-9a-hjkmnp-tv-z]{8})")
EVENT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")


def new_event_id() -> str:
    """A fresh random event ID."""
    return uuid.uuid4().hex


def check_event_id(event_id: str) -> str:
    if not isinstance(event_id, str) or not EVENT_ID_RE.fullmatch(event_id):
        raise RecordsError(
            f"invalid event ID {event_id!r}: use 1-128 characters from "
            "letters, digits and . _ : -, starting with a letter or digit",
            code="invalid_event_id",
        )
    return event_id


def suffix_for(event_id: str, attempt: int) -> str:
    """The eight-character suffix for ``event_id`` on allocation ``attempt``."""
    raw = hashlib.sha256(f"{event_id}:{attempt}".encode("utf-8")).digest()
    value = int.from_bytes(raw[:5], "big")
    chars = [
        CROCKFORD_ALPHABET[(value >> (5 * (SUFFIX_LENGTH - 1 - i))) & 31]
        for i in range(SUFFIX_LENGTH)
    ]
    return "".join(chars)


def record_id_for(day: date, event_id: str, attempt: int) -> str:
    return f"rec-{day:%Y%m%d}-{suffix_for(event_id, attempt)}"


def day_of(timestamp: str) -> date:
    """The UTC day of an event timestamp ``YYYY-MM-DDT...``."""
    try:
        return date.fromisoformat(timestamp[:10])
    except ValueError as exc:
        raise RecordsError(
            f"invalid timestamp {timestamp!r}", code="invalid_timestamp"
        ) from exc


def previous_day(day: date) -> date:
    return day - timedelta(days=1)


def parse_record_id(record_id: str) -> tuple[str, str]:
    """Return ``(month_dir, record_id)`` for a well-formed record ID."""
    match = RECORD_ID_RE.fullmatch(record_id) if isinstance(record_id, str) else None
    if match is None:
        raise RecordsError(
            f"invalid record ID {record_id!r}: expected rec-YYYYMMDD-xxxxxxxx",
            code="invalid_record_id",
        )
    year, month, day = match.group(1), match.group(2), match.group(3)
    try:
        date(int(year), int(month), int(day))
    except ValueError as exc:
        raise RecordsError(
            f"invalid record ID {record_id!r}: bad date", code="invalid_record_id"
        ) from exc
    return f"{year}-{month}", record_id


__all__ = [
    "CROCKFORD_ALPHABET",
    "RECORD_ID_RE",
    "check_event_id",
    "day_of",
    "new_event_id",
    "parse_record_id",
    "record_id_for",
    "suffix_for",
]
