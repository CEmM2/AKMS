"""Stable error contract shared by Python and CLI callers."""

from __future__ import annotations

from typing import Any


class FailureMemoryError(RuntimeError):
    """A fail-closed error with a machine-readable code and safe details."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "failure_memory_error",
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
