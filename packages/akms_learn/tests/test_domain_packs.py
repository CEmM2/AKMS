"""Package-level tests for Domain-pack foundation models.

Covers:

* 1. All 6 Pydantic models defined and importable.
* 2. Registry sorts descriptors deterministically (alphabetic by id).
* 3. Fixture YAMLs parse into descriptors without errors.
* 4. ``domain_packs/`` module's source contains zero imports of
     ``constkit``, ``mechdsl``, ``symbolic_fem_workbench``.
* 5. ``LearningCapabilityError`` defined and raisable.
* 6. Missing planned companion produces a :class:`DomainPackWarning` via
     helper.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from akms_learn.domain_packs import (
    CapabilityStatus,
    CompanionRole,
    DomainPackDescriptor,
    DomainPackRegistry,
    DomainPackWarning,
    LearningCapabilityError,
    RuntimeHint,
    SourcePackDescriptor,
    build_registry_from_paths,
    load_source_pack_from_yaml,
    warn_planned_companion,
)

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_TESTS_DIR = Path(__file__).resolve().parent
_FIXTURE_ROOT = _TESTS_DIR / "fixtures" / "domain_packs" / "compmech_reference"
_DOMAIN_PACK_YAML = _FIXTURE_ROOT / "domain_pack.yaml"
_SOURCE_PACK_DIR = _FIXTURE_ROOT / "source_packs"
_CONSTKIT_YAML = _SOURCE_PACK_DIR / "constkit.yaml"
_FEMWB_YAML = _SOURCE_PACK_DIR / "symbolic_fem_workbench.yaml"
_MECHDSL_YAML = _SOURCE_PACK_DIR / "mechdsl.yaml"


# Path to the domain_packs source tree — used by the AST-scan test.
_DOMAIN_PACKS_SRC = (
    Path(__file__).resolve().parent.parent / "src" / "akms_learn" / "domain_packs"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FORBIDDEN_COMPANIONS = {"constkit", "mechdsl", "symbolic_fem_workbench"}


def _root_module(dotted: str) -> str:
    """Return the top-most module segment of a dotted import path."""
    return dotted.split(".", 1)[0]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDomainPackFoundation:
    """Tests for Domain-pack foundation models."""

    @pytest.mark.unit
    def test_descriptor_parsing(self) -> None:
        """Load 4 fixture YAMLs successfully into descriptors."""
        # Domain pack — also reachable via the registry method form.
        registry = DomainPackRegistry()
        pack = registry.load_from_yaml(_DOMAIN_PACK_YAML)

        assert isinstance(pack, DomainPackDescriptor)
        assert pack.id == "compmech.reference"
        assert pack.domain_id == "compmech"
        assert pack.name == "Computational Mechanics Reference Pack"
        assert pack.version == "0.1.0"
        assert pack.status == "reference"
        assert len(pack.companion_roles) == 3
        # Companion roles are pure data — verify required-runtime, unavailable
        # mechdsl is the canonical "must raise on require" case.
        mechdsl = next(c for c in pack.companion_roles if c.id == "mechdsl")
        assert isinstance(mechdsl, CompanionRole)
        assert mechdsl.package_name == "compmech.mechdsl"
        assert mechdsl.runtime_hint is RuntimeHint.required
        assert mechdsl.capability_status is CapabilityStatus.unavailable

        # Source packs.
        constkit = load_source_pack_from_yaml(_CONSTKIT_YAML)
        femwb = load_source_pack_from_yaml(_FEMWB_YAML)
        mechdsl_sp = load_source_pack_from_yaml(_MECHDSL_YAML)

        for sp in (constkit, femwb, mechdsl_sp):
            assert isinstance(sp, SourcePackDescriptor)
            assert sp.id
            assert sp.name
            assert sp.version
            assert sp.companion_role in {
                "concept_kit",
                "pedagogical_workbench",
                "executable_bridge",
            }
            assert isinstance(sp.capability_status, CapabilityStatus)

        assert constkit.id == "compmech.constkit"
        assert constkit.companion_role == "concept_kit"
        assert femwb.id == "compmech.symbolic_fem_workbench"
        assert femwb.companion_role == "pedagogical_workbench"
        assert mechdsl_sp.id == "compmech.mechdsl"
        assert mechdsl_sp.companion_role == "executable_bridge"
        assert mechdsl_sp.capability_status is CapabilityStatus.unavailable

    @pytest.mark.unit
    def test_registry_ordering_deterministic(self) -> None:
        """Registry sorts descriptors deterministically (alphabetic by id)."""
        d_a = DomainPackDescriptor(pack_id="alpha.pack", name="Alpha", version="0.0.1")
        d_b = DomainPackDescriptor(pack_id="beta.pack", name="Beta", version="0.0.1")
        d_c = DomainPackDescriptor(
            pack_id="charlie.pack", name="Charlie", version="0.0.1"
        )

        # Register in reverse order — output must still be alphabetic.
        r1 = DomainPackRegistry()
        for d in (d_c, d_b, d_a):
            r1.register(d)
        ordered1 = r1.ordered_descriptors()

        # Different insertion order — output must match.
        r2 = DomainPackRegistry()
        for d in (d_b, d_a, d_c):
            r2.register(d)
        ordered2 = r2.ordered_descriptors()

        assert [d.id for d in ordered1] == [
            "alpha.pack",
            "beta.pack",
            "charlie.pack",
        ]
        assert [d.id for d in ordered1] == [d.id for d in ordered2]

        # Lookup / membership still work.
        assert r1.get("beta.pack") is d_b
        assert r1.get("missing") is None
        assert "alpha.pack" in r1
        assert len(r1) == 3

    @pytest.mark.unit
    def test_no_companion_imports(self) -> None:
        """AST scan: no companion imports under ``domain_packs/``."""
        assert _DOMAIN_PACKS_SRC.is_dir(), (
            f"Expected source tree at {_DOMAIN_PACKS_SRC!s}"
        )

        offenders: list[tuple[Path, int, str]] = []
        py_files = sorted(_DOMAIN_PACKS_SRC.rglob("*.py"))
        assert py_files, "No .py files found under domain_packs/"

        for py in py_files:
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if _root_module(alias.name) in _FORBIDDEN_COMPANIONS:
                            offenders.append((py, node.lineno, alias.name))
                elif isinstance(node, ast.ImportFrom):
                    if node.module is None:
                        continue
                    if _root_module(node.module) in _FORBIDDEN_COMPANIONS:
                        offenders.append((py, node.lineno, node.module))

        assert not offenders, (
            f"Forbidden companion imports detected in domain_packs/: {offenders!r}"
        )

    @pytest.mark.unit
    def test_capability_error_raisable(self) -> None:
        """``LearningCapabilityError`` is defined and raisable."""
        msg = "compmech.mechdsl is unavailable but required"
        with pytest.raises(LearningCapabilityError) as exc_info:
            raise LearningCapabilityError(msg)
        assert msg in str(exc_info.value)
        # Must be a real Exception subclass.
        assert issubclass(LearningCapabilityError, Exception)

    @pytest.mark.unit
    def test_planned_companion_warning_helper(self) -> None:
        """``warn_planned_companion`` produces a soft :class:`DomainPackWarning`."""
        w = warn_planned_companion("constkit", "compmech.constkit")

        assert isinstance(w, DomainPackWarning)
        assert w.severity == "warning"
        assert w.code == "planned_companion_unavailable"
        assert "constkit" in w.message
        assert w.source_ref == "compmech.constkit"

    @pytest.mark.unit
    def test_registry_duplicate_id_raises(self) -> None:
        """Registering two descriptors with the same id must raise ValueError."""
        registry = DomainPackRegistry()
        d1 = DomainPackDescriptor(pack_id="dup.pack", name="First", version="0.0.1")
        d2 = DomainPackDescriptor(pack_id="dup.pack", name="Second", version="0.0.2")
        registry.register(d1)
        with pytest.raises(ValueError, match="dup.pack"):
            registry.register(d2)

    @pytest.mark.unit
    def test_source_pack_descriptor_accepts_spec_aliases(self) -> None:
        """Spec §4 bare 'role:' / 'status:' must parse as forward-compat aliases.

        The Python field names are ``companion_role`` / ``capability_status``,
        but spec §4 wording uses the bare names ``role`` / ``status``.
        Pydantic v2 ``AliasChoices`` ensures both spellings populate the same
        canonical Python attributes.
        """
        data = {
            "source_pack_id": "compmech.constkit",
            "name": "ConstKit Concept Helpers",
            "version": "0.1.0",
            "role": "concept_kit",  # spec §4 bare name
            "status": "planned",  # spec §4 bare name
        }
        sp = SourcePackDescriptor.model_validate(data)
        assert sp.id == "compmech.constkit"
        assert sp.companion_role == "concept_kit"
        assert sp.capability_status is CapabilityStatus.planned

        # Canonical Python-side construction must still work.
        sp2 = SourcePackDescriptor(
            source_pack_id="compmech.constkit",
            name="ConstKit Concept Helpers",
            version="0.1.0",
            companion_role="concept_kit",
            capability_status=CapabilityStatus.planned,
        )
        assert sp2.companion_role == "concept_kit"
        assert sp2.capability_status is CapabilityStatus.planned

    @pytest.mark.unit
    def test_domain_pack_summary_accepts_description_alias(self) -> None:
        """Single canonical ``summary`` field — spec §3 uses ``summary``; the
        older ``description`` key is accepted as an alias for backward compat.

        Replaces the earlier redundant pair of optional fields. A YAML may
        carry one or the other; either populates the canonical attribute.
        """
        data = {
            "pack_id": "compmech.reference",
            "name": "Computational Mechanics Reference Pack",
            "version": "0.1.0",
            "description": "Older docs use this key.",  # spec alias
        }
        pack = DomainPackDescriptor.model_validate(data)
        assert pack.summary == "Older docs use this key."

        data2 = dict(data)
        data2.pop("description")
        data2["summary"] = "Canonical spec §3 key."
        pack2 = DomainPackDescriptor.model_validate(data2)
        assert pack2.summary == "Canonical spec §3 key."

    @pytest.mark.unit
    def test_build_registry_from_paths(self) -> None:
        """``build_registry_from_paths`` loads + registers descriptors."""
        registry = build_registry_from_paths([_DOMAIN_PACK_YAML])
        assert len(registry) == 1
        assert registry.get("compmech.reference") is not None
        ordered = registry.ordered_descriptors()
        assert [d.id for d in ordered] == ["compmech.reference"]
