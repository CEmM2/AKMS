"""Capability declarations for compmech_reference_pack.

`CEmM2/Logic-Loom <https://github.com/CEmM2/Logic-Loom>`_ imports this package
from its ``GET /api/mechdsl/status`` route and reads the capability surface to
decide whether to expose the MechDSL gate.
This module is deliberately import-light and **Taichi-free**: it declares
*what* the package offers; it never runs a solve or initialises Taichi.

Two capabilities are declared:

- ``executable_bridge_adapter`` — the package registers ``MechDSLRunner`` as
  the ``executable_bridge`` adapter (``akms_learn`` reports it available).
- ``code_mirror_provenance`` — ``build_executable`` attaches per-node
  provenance (source sections + references) to every emitted artefact.
"""

from __future__ import annotations

from compmech_reference_pack import __version__

__all__ = [
    "ADAPTER_ID",
    "CODE_MIRROR_PROVENANCE",
    "EXECUTABLE_BRIDGE_ADAPTER",
    "capabilities",
]

#: Stable id of the executable-bridge adapter this package registers.
ADAPTER_ID = "compmech.mechdsl_runner"

#: Capability keys (also the akms_learn adapter-registry capability names).
EXECUTABLE_BRIDGE_ADAPTER = "executable_bridge_adapter"
CODE_MIRROR_PROVENANCE = "code_mirror_provenance"


def capabilities() -> dict:
    """Return the machine-readable capability surface for status discovery.

    Shape consumed by Logic-Loom's status route::

        {package, version, domain_pack, adapter_id, capabilities: {...}}

    The dict is JSON-serialisable and contains no runtime objects.
    """
    return {
        "package": "compmech_reference_pack",
        "version": __version__,
        "domain_pack": "compmech.reference",
        "adapter_id": ADAPTER_ID,
        "capabilities": {
            EXECUTABLE_BRIDGE_ADAPTER: {
                "available": True,
                "adapter_id": ADAPTER_ID,
                "companion_role": "executable_bridge",
                "actions": ["emit", "transpile", "verify"],
                # Mirrors the Tier-1 contract: only ``verify`` pays Taichi.
                "taichi_required_for": ["verify"],
            },
            CODE_MIRROR_PROVENANCE: {
                "available": True,
                "source_pack_id": "compmech.mechdsl",
                "repo": "CEmM2/MechDSL",
                # build_executable attaches {node_id: {sections, references}}.
                "provenance_keys": ["sections", "references"],
            },
        },
    }
