"""Capabilities catalog — single source of truth for capability strings.

Two groups of capability strings are exposed to Logic-Loom / external
callers:

* six mode/exporter capability strings:
  ``notebook_source``, ``notebook_export``, ``assessment_first``,
  ``quiz_export``, ``llm_expanded``, ``adaptive_path``.

* four advanced adapter capability strings:
  ``notebook_execution_adapter``, ``concept_kit_adapter``,
  ``pedagogical_workbench_adapter``, ``executable_bridge_adapter``.

Together with the pre-existing baseline strings the catalog forms the
full set of capabilities reported by
:meth:`akms_learn.plugin.Plugin.capabilities`.

Append-only invariant
---------------------
Capability strings may only ever be **added** to the catalog.  Removing or
renaming a capability is a breaking change and would silently invalidate
downstream consumers that detect features by capability string.
A regression test asserts the catalog is a strict superset of every
known string.

Surfacing rules
---------------
* ``notebook_source`` / ``notebook_export`` / ``assessment_first`` /
  ``quiz_export`` / ``html_export`` / ``llm_expanded`` / ``adaptive_path``
  are gated on optional extras (see :mod:`akms_learn.capability_gates`).
  They appear in :func:`all_capabilities` unconditionally; when their extras
  are absent the gate-aware view (:func:`capabilities_with_status`) reports
  them with status ``unavailable`` and lists them in
  :func:`unavailable_capabilities` with the missing extra named.

* The four adapter capabilities are surfaced with their
  :class:`~akms_learn.adapters.AdapterStatus` (``planned`` /
  ``unavailable`` / ``available``) sourced from
  :func:`~akms_learn.adapters.adapter_registry`.  They **never** disappear
  silently when no real adapter is installed — a hard compatibility requirement.

Public API
----------
``BASELINE_CAPABILITIES``
    Tuple of the eighteen pre-existing capability strings historically
    returned by :meth:`Plugin.capabilities` (the original six, the four
    domain-pack additions, the four pedagogical modes, and the four
    structured-mode strings).

``EXPORTER_CAPABILITIES``
    Tuple of the three exporter capability strings
    (``notebook_export``, ``quiz_export``, ``html_export``).  These mirror
    keys already present in
    :data:`akms_learn.capability_gates._CAPABILITY_EXTRA_MAP`.

``ADAPTER_CAPABILITIES``
    Tuple of the four advanced adapter capability strings.

``all_capabilities()``
    Return every catalog string as a fresh ``list[str]``.  Stable, sorted
    inside each group; group order is baseline → exporters → adapters.

``capabilities_with_status(gate=None, adapter_overrides=None)``
    Return a sorted list of ``{"capability": str, "status": str}`` dicts.
    Status values: ``available``, ``unavailable``, ``planned``.

``unavailable_capabilities(gate=None)``
    Return a sorted list of
    ``{"capability": str, "missing_extra": str}`` dicts for every
    extras-gated capability whose extra is absent.
"""

from __future__ import annotations

from typing import Any

from akms_learn.adapters import AdapterStatus, adapter_registry
from akms_learn.capability_gates import (
    _CAPABILITY_EXTRA_MAP,
    CapabilityGate,
    build_capability_gate,
)

__all__ = [
    "BASELINE_CAPABILITIES",
    "EXPORTER_CAPABILITIES",
    "ADAPTER_CAPABILITIES",
    "all_capabilities",
    "capabilities_with_status",
    "unavailable_capabilities",
]


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

#: Capability strings historically returned by :meth:`Plugin.capabilities`.
#: Append-only — preserved verbatim to guarantee the original contract is
#: unchanged.  Order mirrors the original method so the
#: emitted list stays byte-stable for any consumer that compared against a
#: golden snapshot.
BASELINE_CAPABILITIES: tuple[str, ...] = (
    # Original six.
    "learning_source_packet",
    "deterministic_outline",
    "node_anthology",
    "pitfall_driven",
    "markdown_export",
    "bundle_export",
    # plan §21 (L404–L409) — domain-pack additions.
    "domain_pack_registry",
    "static_domain_pack_descriptors",
    "source_pack_descriptors",
    "code_mirror_provenance",
    # Four pedagogical modes.
    "pedagogical_template",
    "derivation_first",
    "implementation_first",
    "multi_granularity",
    # Four structured modes.
    "notebook_source",
    "adaptive_path",
    "assessment_first",
    "llm_expanded",
)


#: Exporter capability strings (already present in
#: ``_CAPABILITY_EXTRA_MAP``).  Appended to the catalog so they surface
#: to external consumers such as Logic-Loom.
EXPORTER_CAPABILITIES: tuple[str, ...] = (
    "notebook_export",
    "quiz_export",
    "html_export",
)


#: Four advanced adapter capability strings.  Status is
#: sourced from :func:`~akms_learn.adapters.adapter_registry`.  These strings
#: MUST appear in any capability listing — they never disappear silently when
#: no real adapter is installed.
ADAPTER_CAPABILITIES: tuple[str, ...] = (
    "notebook_execution_adapter",
    "concept_kit_adapter",
    "pedagogical_workbench_adapter",
    "executable_bridge_adapter",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def all_capabilities() -> list[str]:
    """Return every catalog capability string as a fresh ``list[str]``.

    The order is ``BASELINE_CAPABILITIES`` then ``EXPORTER_CAPABILITIES``
    then ``ADAPTER_CAPABILITIES`` — append-only so any existing consumer
    that indexed into the list at a fixed position keeps working.
    """
    return [
        *BASELINE_CAPABILITIES,
        *EXPORTER_CAPABILITIES,
        *ADAPTER_CAPABILITIES,
    ]


def _gate_status_for(capability: str, gate: CapabilityGate) -> str:
    """Return ``"available"`` / ``"unavailable"`` for an extras-gated capability.

    Capability strings not in :data:`_CAPABILITY_EXTRA_MAP` are unconditional
    and always report ``"available"``.
    """
    if capability not in _CAPABILITY_EXTRA_MAP:
        return "available"
    return "available" if getattr(gate, capability, False) else "unavailable"


def capabilities_with_status(
    gate: CapabilityGate | None = None,
    adapter_overrides: dict[str, AdapterStatus] | None = None,
) -> list[dict[str, Any]]:
    """Return every capability with structured status info.

    Parameters
    ----------
    gate:
        Optional pre-built :class:`CapabilityGate`.  When ``None`` a fresh
        gate is built via :func:`build_capability_gate`.
    adapter_overrides:
        Optional mapping passed straight through to
        :func:`~akms_learn.adapters.adapter_registry` so tests can pretend a
        real adapter is installed without mutating module-level state.

    Returns
    -------
    list[dict[str, Any]]
        One entry per capability:
        ``{"capability": <str>, "status": <"available"|"unavailable"|"planned">}``.

        * Baseline strings + ``markdown_export`` / ``bundle_export`` etc.
          always report ``available`` (no extras gate).
        * Extras-gated strings report ``available`` iff their extra is
          present, ``unavailable`` otherwise.
        * Adapter strings report the registry's :class:`AdapterStatus` value
          (default ``planned``) — they never disappear, satisfying the
          §14 surface requirement.

    The returned list is sorted by capability name for deterministic output.
    """
    if gate is None:
        gate = build_capability_gate()

    adapter_status = adapter_registry(adapter_overrides)

    entries: list[dict[str, Any]] = []
    for cap in BASELINE_CAPABILITIES:
        entries.append({"capability": cap, "status": _gate_status_for(cap, gate)})
    for cap in EXPORTER_CAPABILITIES:
        entries.append({"capability": cap, "status": _gate_status_for(cap, gate)})
    for cap in ADAPTER_CAPABILITIES:
        # adapter_status is guaranteed to contain every adapter capability —
        # never silently dropped.
        status_enum = adapter_status.get(cap, AdapterStatus.unavailable)
        entries.append({"capability": cap, "status": status_enum.value})

    entries.sort(key=lambda e: e["capability"])
    return entries


def unavailable_capabilities(
    gate: CapabilityGate | None = None,
) -> list[dict[str, str]]:
    """Return structured records for every extras-gated capability that is absent.

    Parameters
    ----------
    gate:
        Optional pre-built :class:`CapabilityGate`.  When ``None`` a fresh
        gate is built via :func:`build_capability_gate`.

    Returns
    -------
    list[dict[str, str]]
        Sorted by capability name.  Each entry::

            {"capability": <str>, "missing_extra": <str>}

        Adapter capabilities are *not* included here — they are surfaced via
        :func:`capabilities_with_status` because their absence is a status
        signal (``planned``/``unavailable``) rather than an installable
        extra.
    """
    if gate is None:
        gate = build_capability_gate()

    rows: list[dict[str, str]] = []
    for capability, extra in sorted(_CAPABILITY_EXTRA_MAP.items()):
        if not getattr(gate, capability, False):
            rows.append({"capability": capability, "missing_extra": extra})
    return rows
