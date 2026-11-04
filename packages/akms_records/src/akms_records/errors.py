"""Typed errors with stable machine-readable codes.

Every error the store, the schema registry and the CLI raise is a
:class:`RecordsError` (or a subclass) carrying a ``code`` that callers can
branch on and the CLI prints as ``error[<code>]``. Messages are safe to show:
they name records, revisions and paths, never payload text.
"""

from __future__ import annotations

from typing import Any


class RecordsError(RuntimeError):
    """A fail-closed error with a machine-readable code and safe details."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "records_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.details = dict(details or {})
        super().__init__(message)

    def to_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": "error",
            "error": {"code": self.code, "message": str(self)},
        }
        if self.details:
            payload["error"]["details"] = self.details
        return payload


class NotFound(RecordsError):
    """The record, schema or policy does not exist in this store."""

    def __init__(self, message: str, *, code: str = "not_found") -> None:
        super().__init__(message, code=code)


class StaleRevision(RecordsError):
    """A write named an expected revision that is no longer the head.

    ``where`` is ``"precheck"`` when the store saw the newer head before
    writing, and ``"link"`` when another writer won the exclusive link of the
    same revision file first. Either way nothing was written.
    """

    def __init__(self, record_id: str, *, expected: int, head: int, where: str):
        super().__init__(
            f"{record_id}: stale revision: expected {expected}, head is {head}",
            code="stale_revision",
            details={
                "record_id": record_id,
                "expected_revision": expected,
                "head_revision": head,
                "where": where,
            },
        )
        self.record_id = record_id
        self.expected = expected
        self.head = head
        self.where = where


class ScopeViolation(RecordsError):
    """A read or write reached a record outside the requested scope."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="scope_violation")


class ReplayError(RecordsError):
    """A record's event files do not replay into a valid state.

    Replay never repairs anything: gaps, broken chains, digest mismatches and
    git conflict markers are reported with the record and the file involved.
    ``replay_code`` is one of ``gap``, ``conflict``, ``parse``,
    ``noncanonical``, ``mismatch``, ``format``, ``kind``, ``sequence``,
    ``chain``, ``digest`` or ``empty``.
    """

    def __init__(self, record_id: str, replay_code: str, detail: str) -> None:
        super().__init__(
            f"{record_id}: {replay_code}: {detail}",
            code="replay_error",
            details={"record_id": record_id, "replay_code": replay_code},
        )
        self.record_id = record_id
        self.replay_code = replay_code
        self.detail = detail


__all__ = [
    "NotFound",
    "RecordsError",
    "ReplayError",
    "ScopeViolation",
    "StaleRevision",
]
