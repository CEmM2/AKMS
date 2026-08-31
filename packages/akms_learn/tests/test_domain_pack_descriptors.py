"""domain-pack descriptor parsing.

Loads the four fixture YAMLs that ship under
``tests/fixtures/domain_packs/compmech_reference/`` via the public loaders
in :mod:`akms_learn.domain_packs` and asserts they parse into the canonical
descriptor models without error.

The fixtures are pure metadata; no companion package (``constkit``,
``mechdsl``, ``symbolic_fem_workbench``) is imported or installed. The test
must succeed in an akms-learn-only environment per the the specification closure
condition (L425).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from akms_learn.domain_packs import (
    CapabilityStatus,
    DomainPackDescriptor,
    RuntimeHint,
    SourcePackDescriptor,
    load_descriptor_from_yaml,
    load_source_pack_from_yaml,
)

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_TESTS_DIR = Path(__file__).resolve().parent
_FIXTURE_ROOT = _TESTS_DIR / "fixtures" / "domain_packs" / "compmech_reference"
DOMAIN_PACK_YAML = _FIXTURE_ROOT / "domain_pack.yaml"
SOURCE_PACK_DIR = _FIXTURE_ROOT / "source_packs"
CONSTKIT_YAML = SOURCE_PACK_DIR / "constkit.yaml"
MECHDSL_YAML = SOURCE_PACK_DIR / "mechdsl.yaml"
FEMWB_YAML = SOURCE_PACK_DIR / "symbolic_fem_workbench.yaml"


@pytest.mark.integration
def test_descriptor_parsing_4_fixtures() -> None:
    """All 4 fixture YAMLs round-trip through the public loaders cleanly."""
    # Domain pack via the module-level loader.
    pack = load_descriptor_from_yaml(DOMAIN_PACK_YAML)
    assert isinstance(pack, DomainPackDescriptor)
    assert pack.id == "compmech.reference"
    assert pack.version == "0.1.0"
    assert pack.status == "reference"
    assert len(pack.companion_roles) == 3

    # Three source packs — each loader returns a SourcePackDescriptor.
    constkit = load_source_pack_from_yaml(CONSTKIT_YAML)
    mechdsl = load_source_pack_from_yaml(MECHDSL_YAML)
    femwb = load_source_pack_from_yaml(FEMWB_YAML)

    for sp in (constkit, mechdsl, femwb):
        assert isinstance(sp, SourcePackDescriptor)
        assert sp.id
        assert sp.name
        assert sp.version
        assert isinstance(sp.capability_status, CapabilityStatus)

    assert constkit.id == "compmech.constkit"
    assert constkit.companion_role == "concept_kit"
    assert mechdsl.id == "compmech.mechdsl"
    assert mechdsl.companion_role == "executable_bridge"
    assert mechdsl.capability_status is CapabilityStatus.unavailable
    assert femwb.id == "compmech.symbolic_fem_workbench"
    assert femwb.companion_role == "pedagogical_workbench"


@pytest.mark.integration
def test_descriptor_companion_roles_carry_required_hint() -> None:
    """The domain-pack descriptor's mechdsl companion is marked required."""
    pack = load_descriptor_from_yaml(DOMAIN_PACK_YAML)
    by_id = {c.id: c for c in pack.companion_roles}
    assert by_id["mechdsl"].runtime_hint is RuntimeHint.required
    assert by_id["mechdsl"].capability_status is CapabilityStatus.unavailable
    # constkit and symbolic_fem_workbench are planned/optional in the fixture.
    assert by_id["constkit"].runtime_hint is RuntimeHint.optional
    assert by_id["constkit"].capability_status is CapabilityStatus.planned
    assert by_id["symbolic_fem_workbench"].runtime_hint is RuntimeHint.optional
