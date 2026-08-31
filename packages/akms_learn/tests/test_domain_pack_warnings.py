"""missing planned companion warning.

A companion declared with ``capability_status=planned`` is a soft issue:
the compile MUST succeed and the warning surface MUST emit exactly one
:class:`~akms_learn.domain_packs.DomainPackWarning` per planned companion.

The helper :func:`~akms_learn.domain_packs.warn_planned_companion` is the
canonical builder; we exercise it here against a synthesized planned
companion (so the test stays decoupled from any fixture lifecycle changes
in future) and ALSO confirm the fixture's planned companions can be
discovered via the descriptor.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from akms_learn.domain_packs import (
    CapabilityStatus,
    CompanionRole,
    DomainPackDescriptor,
    DomainPackWarning,
    RuntimeHint,
    load_descriptor_from_yaml,
    warn_planned_companion,
)

_TESTS_DIR = Path(__file__).resolve().parent
_FIXTURE_ROOT = _TESTS_DIR / "fixtures" / "domain_packs" / "compmech_reference"
DOMAIN_PACK_YAML = _FIXTURE_ROOT / "domain_pack.yaml"


def _emit_planned_warnings(
    pack: DomainPackDescriptor,
) -> list[DomainPackWarning]:
    """Return one DomainPackWarning per planned companion role on *pack*."""
    return [
        warn_planned_companion(role.id, role.package_name)
        for role in pack.companion_roles
        if role.capability_status is CapabilityStatus.planned
    ]


@pytest.mark.integration
def test_missing_planned_companion_warning() -> None:
    """A synthesized planned companion produces exactly one DomainPackWarning."""
    pack = DomainPackDescriptor(
        pack_id="test.planned_pack",
        name="Planned-only pack",
        version="0.0.1",
        companion_roles=[
            CompanionRole(
                id="planned_companion",
                package_name="test.planned_companion",
                runtime_hint=RuntimeHint.optional,
                capability_status=CapabilityStatus.planned,
            ),
        ],
    )

    warnings = _emit_planned_warnings(pack)
    assert len(warnings) == 1, (
        f"Expected exactly one DomainPackWarning, got {len(warnings)}: "
        f"{warnings!r}"
    )
    w = warnings[0]
    assert isinstance(w, DomainPackWarning)
    assert w.severity == "warning"
    assert w.code == "planned_companion_unavailable"
    assert "planned_companion" in w.message
    assert w.source_ref == "test.planned_companion"


@pytest.mark.integration
def test_fixture_pack_emits_two_planned_warnings() -> None:
    """The shipped fixture has 2 planned companions (constkit + femwb)."""
    pack = load_descriptor_from_yaml(DOMAIN_PACK_YAML)
    warnings = _emit_planned_warnings(pack)
    # constkit + symbolic_fem_workbench are planned; mechdsl is unavailable.
    codes = [w.code for w in warnings]
    assert codes == ["planned_companion_unavailable"] * 2, (
        f"Expected 2 planned-companion warnings, got {codes!r}"
    )
    refs = sorted(w.source_ref for w in warnings)
    assert refs == sorted(
        ["compmech.constkit", "compmech.symbolic_fem_workbench"]
    )
