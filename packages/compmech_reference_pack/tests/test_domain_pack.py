"""The promoted domain pack reads back through the akms_learn loaders.

Acceptance: the akms_learn descriptor loader reports ``compmech.mechdsl``
available (both the domain-pack companion role and the source-pack /
adapter status), while the still-planned companions stay planned.
"""

from __future__ import annotations

import pytest
from akms_learn.domain_packs.capabilities import CapabilityStatus
from akms_learn.domain_packs.registry import (
    load_descriptor_from_yaml,
    load_source_pack_from_yaml,
)
from compmech_reference_pack.paths import domain_pack_path, source_pack_path


@pytest.mark.unit
def test_domain_pack_descriptor_parses() -> None:
    desc = load_descriptor_from_yaml(domain_pack_path())
    assert desc.id == "compmech.reference"


@pytest.mark.unit
def test_mechdsl_companion_role_is_available() -> None:
    desc = load_descriptor_from_yaml(domain_pack_path())
    roles = {r.id: r for r in desc.companion_roles}
    assert roles["mechdsl"].capability_status is CapabilityStatus.available


@pytest.mark.unit
def test_mechdsl_source_pack_and_adapter_available() -> None:
    sp = load_source_pack_from_yaml(source_pack_path("mechdsl"))
    assert sp.id == "compmech.mechdsl"
    assert sp.companion_role == "executable_bridge"
    assert sp.capability_status is CapabilityStatus.available
    assert sp.adapter is not None
    assert sp.adapter["status"] == "available"


@pytest.mark.unit
def test_other_companions_still_planned() -> None:
    """Promotion only flips MechDSL — the other two companions stay planned."""
    desc = load_descriptor_from_yaml(domain_pack_path())
    roles = {r.id: r for r in desc.companion_roles}
    assert roles["constkit"].capability_status is CapabilityStatus.planned
    assert roles["symbolic_fem_workbench"].capability_status is CapabilityStatus.planned


@pytest.mark.unit
def test_every_source_pack_names_a_public_repository() -> None:
    """A published pack must not point a reader at something they cannot fetch.

    The two `planned` companions originally named per-project repositories that
    do not resolve; their source actually lives in the public
    `Teaching-materials` monorepo. This pins the corrected targets so a future
    edit cannot quietly reintroduce a reference nobody outside the project can
    follow.
    """
    public_repos = {"CEmM2/MechDSL", "SOSOVSKI/Teaching-materials"}
    for name in ("constkit", "symbolic_fem_workbench", "mechdsl"):
        sp = load_source_pack_from_yaml(source_pack_path(name))
        assert sp.repo is not None, f"{name} declares no repo"
        assert sp.repo["name"] in public_repos, (
            f"{name} names {sp.repo['name']!r}, which is not a known public repository"
        )
