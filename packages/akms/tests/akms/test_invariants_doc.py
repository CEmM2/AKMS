"""The published conformance invariants must match the frozen code.

``docs/reference/akms/conformance-invariants.md`` is what ``skills/akms-spec-check`` and
``agents/akms-spec-reviewer`` audit against. It exists because the full design
documents live in ``docs/specification/AKMS_v2_specification.md`` and ship only in the source repository —
published copies strip ``dev/``, which left both assets pointing at files that
were not there.

A conformance document that drifts from the code is worse than none: an audit
would pass against stale values and report a clean result. These tests parse the
document's own tables and compare them to ``akms.schema.models``, so drift fails
the build rather than shipping.
"""

from __future__ import annotations

import enum
import re
from pathlib import Path

import pytest

import akms
from akms.schema import models

pytestmark = pytest.mark.unit

DOC = (
    Path(__file__).resolve().parents[4]
    / "docs"
    / "reference"
    / "akms"
    / "conformance-invariants.md"
)

DOCUMENTED_ENUMS = [
    "NodeStatus",
    "NodeSource",
    "EdgeType",
    "ContextSize",
    "ReadingPriority",
    "AgentRole",
    "LoadoutMode",
    "Coverage",
    "Priority",
    "Severity",
    "TaskStatus",
    "SessionOutcome",
    "ImpactOnNextPhase",
    "TitleMatch",
]

_REGEN = (
    "\n\nThe vocabulary and constant tables are generated from akms.schema.models; "
    "regenerate them rather than editing by hand."
)


@pytest.fixture(scope="module")
def text() -> str:
    assert DOC.is_file(), f"conformance document missing at {DOC}"
    return DOC.read_text(encoding="utf-8")


def _documented_values(text: str, enum_name: str) -> list[str]:
    """Pull the frozen values recorded for one enum from the vocabulary table."""
    match = re.search(rf"^\|\s*`{enum_name}`\s*\|(.+?)\|\s*$", text, re.M)
    assert match, f"{enum_name} has no row in the vocabulary table{_REGEN}"
    return re.findall(r"`([^`]+)`", match.group(1))


@pytest.mark.parametrize("enum_name", DOCUMENTED_ENUMS)
def test_documented_enum_matches_code(text: str, enum_name: str) -> None:
    cls = getattr(models, enum_name, None)
    assert cls is not None and issubclass(cls, enum.Enum), (
        f"{enum_name} is documented as frozen but is not an enum in "
        f"akms.schema.models — the document is describing something that no "
        f"longer exists{_REGEN}"
    )
    assert _documented_values(text, enum_name) == [member.value for member in cls], (
        f"{enum_name} values in the conformance document do not match the code. "
        f"Enum values are frozen at v2, so either the code change is a breaking "
        f"change needing a v3 bump, or the document is stale{_REGEN}"
    )


def test_every_frozen_enum_is_documented() -> None:
    """A new enum must be added to the document, not silently omitted."""
    in_code = {
        name
        for name in dir(models)
        if isinstance(getattr(models, name), type)
        and issubclass(getattr(models, name), enum.Enum)
        and getattr(models, name).__module__ == models.__name__
    }
    missing = sorted(in_code - set(DOCUMENTED_ENUMS))
    assert not missing, (
        f"enums exist in akms.schema.models but are absent from the conformance "
        f"document: {missing}{_REGEN}"
    )


def test_schema_version_constant_matches(text: str) -> None:
    documented = re.search(r"`AKMS_SCHEMA_VERSION`\s*\|\s*`([^`]+)`", text)
    assert documented, f"AKMS_SCHEMA_VERSION not recorded{_REGEN}"
    assert documented.group(1) == akms.AKMS_SCHEMA_VERSION


def test_loadable_statuses_match(text: str) -> None:
    row = re.search(r"`LOADABLE_STATUSES`\s*\|(.+?)\|", text)
    assert row, f"LOADABLE_STATUSES not recorded{_REGEN}"
    documented = set(re.findall(r"`([^`]+)`", row.group(1)))
    assert documented == {status.value for status in models.LOADABLE_STATUSES}
    # The whole point of the constant: these two and nothing else.
    assert "draft" not in documented and "deprecated" not in documented


def test_experiential_fields_match(text: str) -> None:
    row = re.search(r"`EXPERIENTIAL_FIELDS`\s*\|(.+?)\|", text)
    assert row, f"EXPERIENTIAL_FIELDS not recorded{_REGEN}"
    documented = set(re.findall(r"`([^`]+)`", row.group(1)))
    assert documented == set(models.EXPERIENTIAL_FIELDS)


def test_invariant_ids_are_unique_and_well_formed(text: str) -> None:
    """Findings cite these IDs, so a duplicate would make a finding ambiguous."""
    ids = re.findall(r"\*\*`(INV-[A-Z]+-\d+)`\*\*", text)
    assert ids, "no invariant IDs found — findings would have nothing to cite"
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    assert not duplicates, f"duplicate invariant IDs: {duplicates}"


def test_document_states_the_design_docs_are_authoritative(text: str) -> None:
    """The narrow doc must not present itself as the whole specification."""
    lowered = text.lower()
    assert "AKMS_v2_specification" in text, (
        "the document must name where the full spec lives; it now ships at "
        "docs/specification/AKMS_v2_specification.md rather than in the "
        "unpublished internal design documents"
    )
    assert "authoritative" in lowered, (
        "the document must say the design documents remain authoritative; without "
        "that, a reader could take this subset for the entire frozen spec"
    )
