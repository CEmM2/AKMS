"""Canonical JSON, digests and timestamps.

Every digest in the store is taken over a *canonical re-serialization* of the
parsed JSON, never over the bytes on disk. Two files that differ only in
whitespace or line endings (for example after a ``core.autocrlf`` checkout)
therefore carry the same digest; a change to any value does not.

Canonical form: keys sorted, UTF-8 without ASCII escaping, two-space indent,
one trailing newline, and no NaN or infinity. Numbers keep Python's own
round-trip representation, so ``1`` and ``1.0`` are different values, and
strings are not Unicode-normalized.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    """Serialize ``value`` in the store's canonical JSON form."""
    text = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        indent=2,
        allow_nan=False,
    )
    return (text + "\n").encode("utf-8")


def compact_line(value: Any) -> str:
    """One canonical JSON line (sorted keys, no spaces), without the newline."""
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(value: Any) -> str:
    """The SHA-256 of ``value``'s canonical serialization."""
    return sha256_hex(canonical_bytes(value))


def utc_now() -> str:
    """The current UTC time as ``YYYY-MM-DDTHH:MM:SS.ffffffZ``."""
    now = time.time()
    whole = int(now)
    micros = int(round((now - whole) * 1_000_000))
    if micros >= 1_000_000:
        whole, micros = whole + 1, 0
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(whole)) + f".{micros:06d}Z"


def loads_strict(raw: bytes | str) -> Any:
    """Parse JSON, refusing duplicate object keys and non-finite numbers."""

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"duplicate key {key!r}")
            out[key] = value
        return out

    def constant(name: str) -> Any:
        raise ValueError(f"non-finite number {name}")

    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


__all__ = [
    "canonical_bytes",
    "compact_line",
    "digest",
    "loads_strict",
    "sha256_hex",
    "utc_now",
]
