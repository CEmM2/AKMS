"""Pydantic v2 descriptors for AKMS Learn domain packs.

These descriptors are **pure metadata**. They carry companion package names
as *strings* (e.g. ``"compmech.constkit"``) so that the AKMS Learn core can
discover, validate, and display domain-pack declarations without ever
importing companion packages. Spec:
the akms-learn internal specification (not published).

Per the Phase 2 context summary (L19), the source of this subpackage MUST
NOT contain any ``import constkit``, ``import mechdsl``, or
``import symbolic_fem_workbench`` statements. The companion-import lint test
in :mod:`tests/test_domain_packs.py` enforces this via AST scan.

The five top-level types defined here are:

* :class:`RuntimeHint` — enum describing how a companion is needed at runtime.
* :class:`CompanionRole` — a companion (concept_kit / pedagogical_workbench /
  executable_bridge) declared by a domain pack.
* :class:`SourcePackDescriptor` — a companion source repository / package
  declared as metadata only (spec §4).
* :class:`DomainPackDescriptor` — top-level domain pack declaration (spec §3).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from akms_learn.domain_packs.capabilities import CapabilityStatus

__all__ = [
    "RuntimeHint",
    "CompanionRole",
    "SourcePackDescriptor",
    "DomainPackDescriptor",
]


class RuntimeHint(str, Enum):
    """Whether a companion is needed at runtime.

    * ``required`` — LSP compile fails (LearningCapabilityError) if absent.
    * ``optional`` — LSP compile succeeds with a warning if absent.
    * ``none``     — companion is purely descriptive; no runtime check.
    """

    required = "required"
    optional = "optional"
    none = "none"


class CompanionRole(BaseModel):
    """A companion declared by a domain pack (spec §5).

    Carries the companion's role id, dotted package name (as a *string* —
    never imported here), runtime hint, and current capability status.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(
        ...,
        description="Stable lowercase role identifier (e.g. 'constkit').",
    )
    package_name: str = Field(
        ...,
        description="Dotted module path used to reference the companion "
        "(e.g. 'compmech.constkit'). MUST NOT be imported by the core "
        "compiler; it is metadata only.",
    )
    runtime_hint: RuntimeHint = Field(
        default=RuntimeHint.optional,
        description="How this companion is needed at runtime.",
    )
    capability_status: CapabilityStatus = Field(
        default=CapabilityStatus.planned,
        description="Lifecycle status — available / planned / unavailable.",
    )


class SourcePackDescriptor(BaseModel):
    """A source pack — a companion source repo / package (spec §4).

    Source packs are **pure metadata** declarations. They describe a
    companion's repository roots, capability surface, and adapter id, but
    they never trigger any import of the companion code.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    # Optional spec-level fields (mirroring §4) — kept lower_snake_case.
    source_pack_schema: str | None = Field(
        default=None,
        description="Source-pack schema URI (spec §4); informational.",
    )
    id: str = Field(
        ...,
        alias="source_pack_id",
        description="Stable source-pack identifier (e.g. 'compmech.constkit').",
    )
    name: str = Field(..., description="Human-readable source pack name.")
    version: str = Field(..., description="Source-pack version string.")
    companion_role: str = Field(
        ...,
        validation_alias=AliasChoices("companion_role", "role"),
        description="Spec-§5 role id: 'concept_kit' | "
        "'pedagogical_workbench' | 'executable_bridge'. Spec §4 wording "
        "uses bare 'role:'; both spellings are accepted.",
    )
    capability_status: CapabilityStatus = Field(
        default=CapabilityStatus.planned,
        validation_alias=AliasChoices("capability_status", "status"),
        description="Lifecycle status of this source pack. Spec §4 wording "
        "uses bare 'status:'; both spellings are accepted.",
    )

    # Optional metadata bags from spec §4.
    repo: dict[str, Any] | None = Field(
        default=None,
        description="Repository hint dict — kind / name / ref.",
    )
    roots: dict[str, str] | None = Field(
        default=None,
        description="Path roots inside the repo (docs / code / examples / tests).",
    )
    capabilities: dict[str, bool] | None = Field(
        default=None,
        description="Per-source-pack capability map.",
    )
    runtime: dict[str, Any] | None = Field(
        default=None,
        description="Runtime hints — required_python, dependencies list.",
    )
    adapter: dict[str, Any] | None = Field(
        default=None,
        description="Adapter declaration — adapter_id / status.",
    )


class DomainPackDescriptor(BaseModel):
    """Top-level domain pack descriptor (spec §3).

    A domain pack declares a curated learning domain. The core compiler
    MUST be able to load and reason about this descriptor without
    importing any companion package.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Optional spec-§3 schema marker.
    domain_pack_schema: str | None = Field(
        default=None,
        description="Domain-pack schema URI (spec §3); informational.",
    )
    domain_id: str | None = Field(
        default=None,
        description="Stable lowercase domain id (e.g. 'compmech').",
    )
    id: str = Field(
        ...,
        alias="pack_id",
        description="Stable pack identifier (e.g. 'compmech.reference'). "
        "Used as the registry key.",
    )
    name: str = Field(..., description="Human-readable pack name.")
    version: str = Field(..., description="Pack version string.")
    status: Literal["reference", "experimental", "planned", "deprecated"] = Field(
        default="reference",
        description="Lifecycle status (spec §3).",
    )
    summary: str | None = Field(
        default=None,
        validation_alias=AliasChoices("summary", "description"),
        description="Short prose summary of the pack. Spec §3 canonical key "
        "is 'summary'; YAML written against the older 'description' key is "
        "also accepted.",
    )

    # Optional spec-§3 sections.
    compatibility: dict[str, Any] | None = Field(
        default=None,
        description="AKMS Learn schema compatibility window.",
    )
    roots: dict[str, str] | None = Field(
        default=None,
        description="Filesystem roots — nodes / code_mirror / examples / bundles.",
    )
    capabilities: dict[str, bool] | None = Field(
        default=None,
        description="Domain-pack-level capability map (spec §6).",
    )
    provenance: dict[str, Any] | None = Field(
        default=None,
        description="Source repos / vault refs / Zotero collection refs.",
    )

    # Companion roles + source pack pointers (the live data).
    companion_roles: list[CompanionRole] = Field(
        default_factory=list,
        description="Companion roles declared by this pack.",
    )
    source_packs: list[str] = Field(
        default_factory=list,
        description="Paths (relative to the descriptor) of source-pack "
        "YAML files belonging to this domain pack.",
    )
