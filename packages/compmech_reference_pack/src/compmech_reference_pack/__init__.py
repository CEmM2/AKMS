"""compmech_reference_pack — Tier-2 computational-mechanics companion adapter.

Bridges AKMS ``akms_learn`` Learning Source Packet (LSP) excerpts to the
MechDSL Tier-1 ``mechdsl.integration`` façade: it normalises human-authored
algpseudocode into algo2code-grammar-clean form, then emits executable Python
and/or compiled-solver summaries with provenance.

This package depends on **both** ``akms-learn`` and ``mechdsl-core`` (plus
``algo2code``, MechDSL's transpiler backend). It registers the
``executable_bridge`` adapter so ``akms_learn`` reports
``executable_bridge_adapter = available``.

Companion-adapter pattern: MechDSL stays AKMS-unaware; this package is the only
place that knows about both sides. The public surface is populated across the
the executable-bridge tier.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__: list[str] = []
