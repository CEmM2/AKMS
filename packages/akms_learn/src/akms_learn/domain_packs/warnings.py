"""DomainPackWarning model and helpers for domain-pack soft issues.

Per the Phase 2 context summary (L13), ``DomainPackWarning`` is an
*independent type* from ``LearningWarning`` but reuses the same shape:
``severity / code / message / source_ref``.

This module also exposes :func:`warn_planned_companion`, a helper that
builds a warning for the common case of a planned (not-yet-installed)
companion being referenced.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

__all__ = [
    "DomainPackWarning",
    "warn_planned_companion",
]


class DomainPackWarning(BaseModel):
    """Soft issue surfaced from domain-pack discovery / capability checks.

    Independent of :class:`akms_learn.models.LearningWarning` so that the
    domain-pack subsystem can evolve its severity / code vocabulary without
    forcing an LSP schema bump.
    """

    model_config = ConfigDict(frozen=True)

    severity: Literal["info", "warning", "error"]
    code: str
    message: str
    source_ref: str | None = None


def warn_planned_companion(role_id: str, package_name: str) -> DomainPackWarning:
    """Build a warning that a planned companion is not yet available.

    Used when an LSP compile resolves a :class:`CompanionRole` whose
    ``capability_status`` is ``planned``. The companion's absence is not a
    failure — exporters that ignore the role-specific fields will still
    produce a valid LSP — but Logic-Loom / CLI surfaces should display the
    warning so users understand why the artifact is static-only.

    Args:
        role_id: The companion role id (e.g. ``"constkit"``).
        package_name: The dotted-name string declared by the descriptor
            (e.g. ``"compmech.constkit"``). Carried in the message and as
            the ``source_ref`` so warnings can be deduped per package.
    """

    return DomainPackWarning(
        severity="warning",
        code="planned_companion_unavailable",
        message=(
            f"Companion role {role_id!r} (package {package_name!r}) is "
            "declared as planned and not yet available; downstream artifacts "
            "will be static only."
        ),
        source_ref=package_name,
    )
