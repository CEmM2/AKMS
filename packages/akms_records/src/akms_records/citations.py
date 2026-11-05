"""Citations of record revisions, and the built-in ``consolidation/v1`` schema.

A summary (see :mod:`akms_records.consolidate`) is an ordinary record of the
built-in schema ``consolidation/v1``. Its ``source_refs`` hold one
``{"kind": "record", "ref": "<record_id>@<revision>"}`` entry per source, and
each assertion of its payload lists the same ``<record_id>@<revision>``
strings. These helpers are pure: the store, the index and the consolidation
module share them without importing one another.
"""

from __future__ import annotations

import importlib.resources
import re
from typing import Any

from akms_records.canonical import loads_strict
from akms_records.errors import RecordsError
from akms_records.schemas import schema_digest

CONSOLIDATION_NAME = "consolidation"
CONSOLIDATION_REF = f"{CONSOLIDATION_NAME}/v1"
SOURCE_KIND = "record"
CITATION_RE = re.compile(r"(rec-[0-9]{8}-[0-9a-hjkmnp-tv-z]{8})@([1-9][0-9]{0,5})")

_BUILTIN: dict[str, Any] | None = None


def is_consolidation(schema_ref: Any) -> bool:
    """Whether ``schema_ref`` names a version of the built-in summary schema."""
    return isinstance(schema_ref, str) and (
        schema_ref == CONSOLIDATION_NAME
        or schema_ref.startswith(CONSOLIDATION_NAME + "/")
    )


def citation(record_id: str, revision: int) -> str:
    return f"{record_id}@{revision}"


def parse_citation(text: Any) -> tuple[str, int]:
    """``(record_id, revision)`` of a ``<record_id>@<revision>`` string."""
    match = CITATION_RE.fullmatch(text) if isinstance(text, str) else None
    if match is None:
        raise RecordsError(
            f"invalid citation {text!r}: expected <record_id>@<revision>",
            code="citation_invalid",
            details={"problem": "malformed"},
        )
    return match.group(1), int(match.group(2))


def cited_ids(source_refs: Any, payload: Any) -> set[str]:
    """Every record ID a summary names, in its source refs or its assertions."""
    out: set[str] = set()
    for ref in source_refs if isinstance(source_refs, list) else []:
        if isinstance(ref, dict) and ref.get("kind") == SOURCE_KIND:
            match = CITATION_RE.fullmatch(str(ref.get("ref", "")))
            if match:
                out.add(match.group(1))
    assertions = payload.get("assertions") if isinstance(payload, dict) else None
    for assertion in assertions if isinstance(assertions, list) else []:
        sources = assertion.get("sources") if isinstance(assertion, dict) else None
        for item in sources if isinstance(sources, list) else []:
            match = CITATION_RE.fullmatch(str(item))
            if match:
                out.add(match.group(1))
    return out


def summary_cites(
    schema_ref: Any, source_refs: Any, payload: Any, ids: set[str]
) -> bool:
    """Whether a summary record names any of ``ids`` (False for other records)."""
    return (
        bool(ids)
        and is_consolidation(schema_ref)
        and bool(cited_ids(source_refs, payload) & ids)
    )


def builtin_schema() -> dict[str, Any]:
    """The built-in ``consolidation/v1`` schema document, with its rules."""
    global _BUILTIN
    if _BUILTIN is None:
        folder = importlib.resources.files("akms_records") / "builtin"
        loaded = loads_strict((folder / "consolidation.schema.json").read_bytes())
        assert isinstance(loaded, dict)
        _BUILTIN = loaded
    return _BUILTIN


def builtin_digest() -> str:
    """The schema digest every store must hold for ``consolidation/v1``."""
    return schema_digest(builtin_schema())


__all__ = [
    "CITATION_RE",
    "CONSOLIDATION_NAME",
    "CONSOLIDATION_REF",
    "SOURCE_KIND",
    "builtin_digest",
    "builtin_schema",
    "citation",
    "cited_ids",
    "is_consolidation",
    "parse_citation",
    "summary_cites",
]
