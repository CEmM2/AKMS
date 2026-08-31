"""Plugin contract entry-point for akms_learn (``akms.plugins:learn``).

This module is the resolution target of the ``akms.plugins`` entry-point
declared in :file:`pyproject.toml`:

    [project.entry-points."akms.plugins"]
    learn = "akms_learn.plugin:get_plugin"

The plugin object is intentionally **static metadata plus two thin methods**.
It MUST be cheap to import — no graph loads, no filesystem access, no LLM
client initialisation may happen here or in :func:`get_plugin`.

Capability surface
------------------
The canonical capability listing lives in
:mod:`akms_learn.capabilities_catalog` (single source of truth).  This module
delegates :meth:`Plugin.capabilities` to
:func:`~akms_learn.capabilities_catalog.all_capabilities` and adds a sibling
:meth:`Plugin.capabilities_with_status` for gate-aware consumers such as
Logic-Loom feature detection and the review bundle.

Append-only invariant
---------------------
Capability strings may only ever be **added**.  Removing or renaming any
string in :data:`~akms_learn.capabilities_catalog.BASELINE_CAPABILITIES` is a
breaking change.  That is why :meth:`capabilities` returns a plain ``list``
rather than a frozenset.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from akms_learn.capabilities_catalog import (
    all_capabilities,
    capabilities_with_status,
)

__all__ = ["Plugin", "get_plugin"]


@dataclass(frozen=True)
class Plugin:
    """Static plugin metadata for the akms-learn plugin.

    Attribute values follow plan §7 (L125–L131) verbatim. The dataclass is
    frozen so callers cannot mutate the version constants in flight.
    """

    plugin_api: str = "akms-learn-plugin/v1"
    learning_packet_schema: str = "learn/v1"
    supported_akms_schema_min: str = "v2"
    supported_akms_schema_max: str = "v2"

    def capabilities(self) -> list[str]:
        """Return the plugin's capability strings.

        Sourced from :func:`akms_learn.capabilities_catalog.all_capabilities`
        — the single source of truth.  Always returns a freshly constructed
        ``list[str]`` so callers cannot mutate shared state.  Strings may
        only ever be appended; the existing eighteen strings are preserved
        verbatim from earlier releases.
        """
        return all_capabilities()

    def capabilities_with_status(self) -> list[dict[str, Any]]:
        """Return every capability paired with its current status.

        Each entry is ``{"capability": <str>, "status": <str>}`` where
        ``status`` is one of ``"available"``, ``"unavailable"``,
        ``"planned"``.  Adapter capabilities NEVER drop out of this list
        when no real adapter is installed — they appear with status
        ``"planned"``.

        See :func:`akms_learn.capabilities_catalog.capabilities_with_status`
        for the full contract.
        """
        return capabilities_with_status()


def get_plugin() -> Plugin:
    """Return a :class:`Plugin` instance.

    Cheap to call — constructs a frozen dataclass and returns it. No I/O,
    no graph access, no network. Safe to call from plugin discovery hot paths.
    """
    return Plugin()
