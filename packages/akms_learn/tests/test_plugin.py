"""Plugin entry-point smoke test for akms-learn.

Validates the ``akms.plugins:learn`` entry-point declared in
:file:`pyproject.toml` resolves to :func:`akms_learn.plugin.get_plugin` and
that the returned :class:`Plugin` exposes the the specification contract.

These tests are deterministic and depend only on the entry-point declared by
this package — they do not assume any other plugin is registered.
"""

from __future__ import annotations

from importlib.metadata import entry_points

import pytest

# The original six + the domain-pack
# additions) = the canonical 10-capability set REQUIRED to be present. The
# assertions below check a *superset* relation so later phases may APPEND new
# capability strings without breaking this test.
REQUIRED_CAPABILITIES: set[str] = {
    # the specification — original six.
    "learning_source_packet",
    "deterministic_outline",
    "node_anthology",
    "pitfall_driven",
    "markdown_export",
    "bundle_export",
    # Domain-pack additions.
    "domain_pack_registry",
    "static_domain_pack_descriptors",
    "source_pack_descriptors",
    "code_mirror_provenance",
}


def _find_learn_entry_point():
    """Return the ``learn`` entry-point under ``akms.plugins``.

    Uses the Python 3.10+ ``select(group=...)`` API on the ``EntryPoints``
    collection returned by :func:`importlib.metadata.entry_points`.
    """
    eps = entry_points().select(group="akms.plugins")
    matches = [ep for ep in eps if ep.name == "learn"]
    assert matches, "No 'learn' entry-point found under group 'akms.plugins'"
    return matches[0]


@pytest.mark.unit
def test_entry_point_lookup() -> None:
    """The ``learn`` entry-point resolves to ``akms_learn.plugin:get_plugin``."""
    ep = _find_learn_entry_point()
    assert ep.name == "learn"
    assert ep.value == "akms_learn.plugin:get_plugin"
    assert ep.module == "akms_learn.plugin"
    assert ep.attr == "get_plugin"


@pytest.mark.unit
def test_plugin_attributes() -> None:
    """Loaded plugin exposes the the specification string attributes with correct values."""
    ep = _find_learn_entry_point()
    factory = ep.load()
    plugin = factory()

    assert isinstance(plugin.plugin_api, str)
    assert plugin.plugin_api == "akms-learn-plugin/v1"

    assert isinstance(plugin.learning_packet_schema, str)
    assert plugin.learning_packet_schema == "learn/v1"

    assert isinstance(plugin.supported_akms_schema_min, str)
    assert plugin.supported_akms_schema_min == "v2"

    assert isinstance(plugin.supported_akms_schema_max, str)
    assert plugin.supported_akms_schema_max == "v2"


@pytest.mark.unit
def test_capabilities_membership_initial() -> None:
    """``capabilities()`` advertises at least the canonical baseline set.

    The original six plus the four domain-pack
    capability strings (``domain_pack_registry``,
    ``static_domain_pack_descriptors``, ``source_pack_descriptors``,
    ``code_mirror_provenance``) — a total of ten REQUIRED strings.

    Later phases may APPEND new capability strings; the assertion uses
    superset semantics so those additions don't regress this test. Capability
    strings may only ever be added, never removed or reordered — the
    superset check enforces the "never removed" half of that invariant. The
    test name is preserved so historical review trails remain unbroken.
    """
    ep = _find_learn_entry_point()
    plugin = ep.load()()
    caps = plugin.capabilities()

    assert isinstance(caps, list)
    assert all(isinstance(c, str) for c in caps)
    assert len(caps) >= 10
    assert REQUIRED_CAPABILITIES <= set(caps), (
        f"capabilities() missing required strings: {REQUIRED_CAPABILITIES - set(caps)}"
    )
