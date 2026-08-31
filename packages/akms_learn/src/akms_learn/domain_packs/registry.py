"""In-memory registry for :class:`DomainPackDescriptor` plus YAML loaders.

This module is the public surface that the Phase 3 ``compile_learning_source``
orchestrator will consume to discover what domain packs are available. It is
**pure** — no companion-package imports, no filesystem side effects beyond
reading the user-supplied YAML files via :mod:`yaml.safe_load`.

Public surface:

* :class:`DomainPackRegistry` — register, lookup, and deterministically
  ordered iteration over descriptors.
* :func:`load_descriptor_from_yaml` — parse a single :class:`DomainPackDescriptor`
  from a YAML path.
* :func:`load_source_pack_from_yaml` — parse a single
  :class:`SourcePackDescriptor` from a YAML path.
* :func:`build_registry_from_paths` — convenience builder that loads N
  descriptor YAMLs and returns a populated registry.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Union

import yaml

from akms_learn.domain_packs.descriptors import (
    DomainPackDescriptor,
    SourcePackDescriptor,
)

__all__ = [
    "DomainPackRegistry",
    "load_descriptor_from_yaml",
    "load_source_pack_from_yaml",
    "build_registry_from_paths",
]

PathLike = Union[str, Path]


class DomainPackRegistry:
    """In-memory map of :class:`DomainPackDescriptor` keyed by ``descriptor.id``.

    Deterministic: :meth:`ordered_descriptors` always returns descriptors
    sorted alphabetically by id, regardless of insertion order.
    """

    def __init__(self) -> None:
        self._descriptors: dict[str, DomainPackDescriptor] = {}

    def register(self, descriptor: DomainPackDescriptor) -> None:
        """Add ``descriptor`` to the registry.

        Raises:
            ValueError: If a descriptor with the same id is already
                registered. Duplicate ids would make
                :meth:`ordered_descriptors` ambiguous.
        """
        if descriptor.id in self._descriptors:
            raise ValueError(
                f"DomainPackDescriptor id {descriptor.id!r} is already registered."
            )
        self._descriptors[descriptor.id] = descriptor

    def get(self, descriptor_id: str) -> DomainPackDescriptor | None:
        """Return the descriptor with id ``descriptor_id`` or ``None``."""
        return self._descriptors.get(descriptor_id)

    def ordered_descriptors(self) -> list[DomainPackDescriptor]:
        """Return descriptors sorted alphabetically by id.

        Deterministic across runs and Python sessions.
        """
        return [self._descriptors[k] for k in sorted(self._descriptors)]

    def __len__(self) -> int:
        return len(self._descriptors)

    def __contains__(self, descriptor_id: object) -> bool:
        return descriptor_id in self._descriptors

    # The single-YAML loader is also exposed as a method for callers that
    # want to do registry.load_from_yaml(...) without importing the
    # module-level function.
    def load_from_yaml(self, yaml_path: PathLike) -> DomainPackDescriptor:
        """Load a :class:`DomainPackDescriptor` from ``yaml_path``.

        The descriptor is parsed and returned but **not** automatically
        registered. Callers may decide whether to register it (this keeps
        the loader free of registration side effects).
        """
        return load_descriptor_from_yaml(yaml_path)


def load_descriptor_from_yaml(yaml_path: PathLike) -> DomainPackDescriptor:
    """Parse a :class:`DomainPackDescriptor` from a YAML file."""
    p = Path(yaml_path)
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(
            f"Expected mapping at top level of {p!s}; got {type(data).__name__}."
        )
    return DomainPackDescriptor.model_validate(data)


def load_source_pack_from_yaml(yaml_path: PathLike) -> SourcePackDescriptor:
    """Parse a :class:`SourcePackDescriptor` from a YAML file."""
    p = Path(yaml_path)
    with p.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(
            f"Expected mapping at top level of {p!s}; got {type(data).__name__}."
        )
    return SourcePackDescriptor.model_validate(data)


def build_registry_from_paths(
    domain_pack_paths: Sequence[PathLike],
) -> DomainPackRegistry:
    """Load multiple domain-pack YAMLs into a fresh :class:`DomainPackRegistry`.

    Each path is parsed via :func:`load_descriptor_from_yaml` and registered
    in input order, but :meth:`DomainPackRegistry.ordered_descriptors`
    output remains deterministic (alphabetic by id).
    """
    registry = DomainPackRegistry()
    for path in domain_pack_paths:
        registry.register(load_descriptor_from_yaml(path))
    return registry
