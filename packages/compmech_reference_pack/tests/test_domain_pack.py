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
def test_public_pack_declares_only_shippable_companions() -> None:
    """Every companion role in the public pack is one a user can actually use.

    The `constkit` and `symbolic_fem_workbench` roles were dropped on
    publication: both were `planned` — no adapter exists — and both named
    source repositories that are not publicly resolvable. A pack that
    advertises companions nobody can obtain is worse than one that stays quiet
    about them, so the public descriptor declares only what ships.
    """
    desc = load_descriptor_from_yaml(domain_pack_path())
    roles = {r.id: r for r in desc.companion_roles}
    assert set(roles) == {"mechdsl"}
    assert all(
        r.capability_status is CapabilityStatus.available for r in desc.companion_roles
    )
