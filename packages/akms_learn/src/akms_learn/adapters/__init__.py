"""Adapter protocols package for akms-learn.

This package defines pure-Python protocol surfaces for four advanced-companion
adapters.  No real adapter implementations ship here; all concrete
implementations are provided by downstream packages.

No-mutation invariant
---------------------
Adapters in this package MUST NOT:
- Write to the AKMS global vault or any AKMS-owned path.
- Mutate any AKMS graph object passed to them.
- Write files via any file-write API targeting AKMS-owned paths.

Public surface
--------------
``protocols``   — the four runtime_checkable Protocol classes.
``status``      — AdapterStatus enum + adapter_registry() accessor.
``fake_adapter``— Fake implementations for use in tests ONLY.
"""

from akms_learn.adapters.protocols import (
    ConceptKitAdapter,
    ExecutableBridgeAdapter,
    NotebookExecutionAdapter,
    PedagogicalWorkbenchAdapter,
)
from akms_learn.adapters.status import AdapterStatus, adapter_registry

__all__ = [
    # Protocols
    "ConceptKitAdapter",
    "ExecutableBridgeAdapter",
    "NotebookExecutionAdapter",
    "PedagogicalWorkbenchAdapter",
    # Status
    "AdapterStatus",
    "adapter_registry",
]
