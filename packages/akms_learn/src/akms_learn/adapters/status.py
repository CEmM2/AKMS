"""Adapter capability status enum and registry.

This module answers the question: *which advanced adapters are installed, and
what is their readiness?*

No-mutation invariant
---------------------
This module is read-only.  It MUST NOT write to any AKMS path.

AdapterStatus
-------------
Three-value enum that describes the readiness of a named adapter capability:

``unavailable``
    The capability has not been implemented yet, or is permanently absent
    from this installation.

``planned``
    The capability is on the roadmap (defined by protocol) but no real
    implementation is installed.  This is the expected status for the four
    adapter capabilities until real runners ship.

``available``
    A real implementation is installed and the capability can be exercised.

Registry
--------
:func:`adapter_registry` returns a mapping of the four adapter capability
names to their current :class:`AdapterStatus`.

Capability strings
--------------------------------
``concept_kit_adapter``
``pedagogical_workbench_adapter``
``executable_bridge_adapter``
``notebook_execution_adapter``

Default status with no real adapter installed
---------------------------------------------
All four capabilities default to ``planned`` — they are protocol-defined and
on the roadmap, but no real runner ships with akms-learn core.  The
capability catalog surfaces these values.
"""

from __future__ import annotations

import enum

__all__ = [
    "AdapterStatus",
    "adapter_registry",
]

# ---------------------------------------------------------------------------
# AdapterStatus
# ---------------------------------------------------------------------------


class AdapterStatus(enum.Enum):
    """Readiness status for an adapter capability.

    Members
    -------
    unavailable:
        Not implemented / not on the roadmap for this installation.
    planned:
        Protocol defined; no real implementation installed yet.
    available:
        Real implementation present and exercisable.
    """

    unavailable = "unavailable"
    planned = "planned"
    available = "available"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Default statuses for all four adapter capabilities.
# With no real adapter installed every capability is ``planned`` — the
# protocol surfaces are defined; real runners arrive later.
_DEFAULT_REGISTRY: dict[str, AdapterStatus] = {
    "concept_kit_adapter": AdapterStatus.planned,
    "pedagogical_workbench_adapter": AdapterStatus.planned,
    "executable_bridge_adapter": AdapterStatus.planned,
    "notebook_execution_adapter": AdapterStatus.planned,
}


def adapter_registry(
    overrides: dict[str, AdapterStatus] | None = None,
) -> dict[str, AdapterStatus]:
    """Return the current adapter capability registry.

    Parameters
    ----------
    overrides:
        Optional mapping of capability name → :class:`AdapterStatus`.  Used
        by tests (and future real adapters) to inject ``available`` status
        without mutating module-level state.  Any capability not present in
        *overrides* falls back to the default status.

    Returns
    -------
    dict[str, AdapterStatus]
        A fresh dict mapping every known adapter capability name to its
        :class:`AdapterStatus`.  With no real adapter installed all four
        capabilities report ``planned``.  The dict is always sorted by key
        for deterministic output.

    Notes
    -----
    - This function is cache-free: every call constructs a new dict so that
      test overrides always take effect without cache invalidation.
    - All four capability strings are always present in the returned dict;
      none are silently dropped.
    """
    if overrides:
        unknown = set(overrides) - _DEFAULT_REGISTRY.keys()
        if unknown:
            raise ValueError(
                f"Unknown adapter capability {sorted(unknown)[0]!r}. "
                f"Known capabilities: {sorted(_DEFAULT_REGISTRY)}"
            )
        merged = {**_DEFAULT_REGISTRY, **overrides}
    else:
        merged = _DEFAULT_REGISTRY
    return dict(sorted(merged.items()))
