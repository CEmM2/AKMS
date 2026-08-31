"""deterministic registry ordering.

Builds a :class:`~akms_learn.domain_packs.DomainPackRegistry` from a set of
descriptors registered in randomized order and asserts that
``ordered_descriptors()`` returns a byte-stable list (alphabetic by id)
across two independent builds.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from akms_learn.domain_packs import (
    DomainPackDescriptor,
    DomainPackRegistry,
    load_descriptor_from_yaml,
)

_TESTS_DIR = Path(__file__).resolve().parent
_FIXTURE_ROOT = _TESTS_DIR / "fixtures" / "domain_packs" / "compmech_reference"
DOMAIN_PACK_YAML = _FIXTURE_ROOT / "domain_pack.yaml"


def _build_random_descriptors() -> list[DomainPackDescriptor]:
    """Return 4 descriptors — 1 from the fixture YAML + 3 synthesized stubs.

    Using a real fixture descriptor alongside 3 synthesized ones exercises
    the ordering invariant on the actual production-shape data without
    requiring 4 separate YAML files.
    """
    fixture = load_descriptor_from_yaml(DOMAIN_PACK_YAML)
    return [
        fixture,
        DomainPackDescriptor(pack_id="alpha.pack", name="Alpha", version="0.0.1"),
        DomainPackDescriptor(pack_id="zeta.pack", name="Zeta", version="0.0.1"),
        DomainPackDescriptor(pack_id="mu.pack", name="Mu", version="0.0.1"),
    ]


@pytest.mark.integration
def test_registry_ordering_deterministic() -> None:
    """Two registries built with the same 4 descriptors in different random
    insertion orders produce identical ``ordered_descriptors`` lists."""
    descriptors = _build_random_descriptors()
    expected_ids = sorted(d.id for d in descriptors)

    rng1 = random.Random(20260519)
    order1 = list(descriptors)
    rng1.shuffle(order1)

    rng2 = random.Random(99887766)
    order2 = list(descriptors)
    rng2.shuffle(order2)

    # The two shuffles must actually differ — otherwise we are not really
    # testing the ordering invariant. We retry once if the RNG seeds happen
    # to produce identical permutations (vanishingly unlikely with these
    # seeds, but defensive).
    if [d.id for d in order1] == [d.id for d in order2]:
        rng2 = random.Random(12345)
        order2 = list(descriptors)
        rng2.shuffle(order2)

    r1 = DomainPackRegistry()
    for d in order1:
        r1.register(d)
    r2 = DomainPackRegistry()
    for d in order2:
        r2.register(d)

    ids1 = [d.id for d in r1.ordered_descriptors()]
    ids2 = [d.id for d in r2.ordered_descriptors()]

    assert ids1 == expected_ids, (
        f"Registry ordering not alphabetic — got {ids1!r}, expected {expected_ids!r}"
    )
    assert ids1 == ids2, (
        "DomainPackRegistry.ordered_descriptors() is not deterministic — "
        f"build1={ids1!r}, build2={ids2!r}"
    )
