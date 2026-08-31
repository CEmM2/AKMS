"""Capability-status enum and capability error type for domain packs.

This module defines:

* :class:`CapabilityStatus` — a string enum with the three statuses recognized
  by the AKMS Learn domain-pack architecture (spec
  ``09_domain_pack_and_companion_architecture.md`` §6).
* :class:`LearningCapabilityError` — a hard error raised when an LSP compile
  request explicitly requires a capability whose backing companion/source pack
  is ``unavailable`` (plan §21 rule 5).

Note: missing / planned companions are *soft* issues and produce a
:class:`~akms_learn.domain_packs.warnings.DomainPackWarning` instead of an
exception. The exception path is reserved for cases where a request mode
*requires* a runtime adapter that is not present.
"""

from __future__ import annotations

from enum import Enum

__all__ = [
    "CapabilityStatus",
    "LearningCapabilityError",
]


class CapabilityStatus(str, Enum):
    """Lifecycle status of a domain-pack / source-pack capability.

    Values map onto the spec's three-state model:

    * ``available``  — the capability is present and usable now.
    * ``planned``    — declared by the descriptor, not yet wired up.
    * ``unavailable``— intentionally not provided in this environment.
    """

    available = "available"
    planned = "planned"
    unavailable = "unavailable"


class LearningCapabilityError(Exception):
    """Raised when a request needs an unavailable required capability.

    Per plan §21 rule 5 / spec §4 rule 2: missing source packs degrade to
    warnings *unless* the requested mode explicitly requires that pack — in
    which case the compiler MUST raise this error.
    """
