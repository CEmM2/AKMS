"""AKMS Learn domain-pack foundation.

This subpackage holds **metadata-only** descriptors, a registry, and the
capability / warning types for domain packs and their companion source
packs. The runtime contract is:

* No file in this subpackage may import a companion package
  (``constkit``, ``mechdsl``, ``symbolic_fem_workbench``) directly or
  transitively. Companion names are carried as strings on
  :class:`CompanionRole`.
* All descriptors are loaded from YAML at runtime via the registry —
  never from Python imports.

Spec: the akms-learn internal specification (not published).
"""

from akms_learn.domain_packs.capabilities import (
    CapabilityStatus,
    LearningCapabilityError,
)
from akms_learn.domain_packs.descriptors import (
    CompanionRole,
    DomainPackDescriptor,
    RuntimeHint,
    SourcePackDescriptor,
)
from akms_learn.domain_packs.registry import (
    DomainPackRegistry,
    build_registry_from_paths,
    load_descriptor_from_yaml,
    load_source_pack_from_yaml,
)
from akms_learn.domain_packs.warnings import (
    DomainPackWarning,
    warn_planned_companion,
)

__all__ = [
    "CapabilityStatus",
    "CompanionRole",
    "DomainPackDescriptor",
    "DomainPackRegistry",
    "DomainPackWarning",
    "LearningCapabilityError",
    "RuntimeHint",
    "SourcePackDescriptor",
    "build_registry_from_paths",
    "load_descriptor_from_yaml",
    "load_source_pack_from_yaml",
    "warn_planned_companion",
]
