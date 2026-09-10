"""capability surface is declared and readable by a status route."""

from __future__ import annotations

import json

import pytest
from compmech_reference_pack.capabilities import (
    CODE_MIRROR_PROVENANCE,
    EXECUTABLE_BRIDGE_ADAPTER,
    capabilities,
)


@pytest.mark.unit
def test_declares_both_capabilities() -> None:
    caps = capabilities()["capabilities"]
    assert caps[EXECUTABLE_BRIDGE_ADAPTER]["available"] is True
    assert caps[CODE_MIRROR_PROVENANCE]["available"] is True


@pytest.mark.unit
def test_adapter_id_consistent() -> None:
    surface = capabilities()
    assert surface["adapter_id"] == "compmech.mechdsl_runner"
    assert (
        surface["capabilities"][EXECUTABLE_BRIDGE_ADAPTER]["adapter_id"]
        == "compmech.mechdsl_runner"
    )


@pytest.mark.unit
def test_taichi_required_for_mirrors_tier1() -> None:
    bridge = capabilities()["capabilities"][EXECUTABLE_BRIDGE_ADAPTER]
    assert bridge["taichi_required_for"] == ["verify"]


@pytest.mark.unit
def test_surface_is_json_serialisable() -> None:
    """Logic-Loom serialises the surface into its status response."""
    recovered = json.loads(json.dumps(capabilities()))
    assert recovered["package"] == "compmech_reference_pack"
    assert recovered["domain_pack"] == "compmech.reference"
