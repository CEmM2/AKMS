"""Primary test suite for adapter protocols + AdapterStatus + fake_adapter.

Acceptance criteria verified here:
  * All four Protocol classes exist and are runtime_checkable.
  * AdapterStatus enum has exactly {unavailable, planned, available}.
  * fake_adapter.py defines a fake per protocol; isinstance checks pass.
  * Adapter modules contain no calls that could mutate AKMS graphs or
        the global vault (canary test).
  * Registry returns unavailable/planned when no real adapter is installed.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from akms_learn.adapters.protocols import (
    ConceptKitAdapter,
    ExecutableBridgeAdapter,
    NotebookExecutionAdapter,
    PedagogicalWorkbenchAdapter,
)
from akms_learn.adapters.status import AdapterStatus, adapter_registry
from akms_learn.adapters.fake_adapter import (
    FakeConceptKit,
    FakeExecutableBridge,
    FakeNotebookExecution,
    FakePedagogicalWorkbench,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ADAPTERS_PKG = (
    pathlib.Path(__file__).parent.parent
    / "src" / "akms_learn" / "adapters"
)

_ADAPTER_SOURCE_FILES = [
    _ADAPTERS_PKG / "__init__.py",
    _ADAPTERS_PKG / "protocols.py",
    _ADAPTERS_PKG / "status.py",
    _ADAPTERS_PKG / "fake_adapter.py",
]

_BOUNDED_EXCERPT: dict = {
    "section_id": "mechanics-101",
    "title": "Introduction to Statics",
    "content": "A body is in equilibrium when ...",
    "tags": ["statics", "equilibrium"],
}

# ---------------------------------------------------------------------------
# Protocol classes are runtime_checkable
# ---------------------------------------------------------------------------


class TestProtocolsExistAndAreRuntimeCheckable:
    """All four Protocol classes must exist and be runtime_checkable."""

    @pytest.mark.unit
    def test_concept_kit_adapter_is_runtime_checkable(self):
        """isinstance works against ConceptKitAdapter at runtime."""
        # A random object that does NOT have the method should return False
        assert not isinstance(object(), ConceptKitAdapter)

    @pytest.mark.unit
    def test_pedagogical_workbench_adapter_is_runtime_checkable(self):
        """isinstance works against PedagogicalWorkbenchAdapter at runtime."""
        assert not isinstance(object(), PedagogicalWorkbenchAdapter)

    @pytest.mark.unit
    def test_executable_bridge_adapter_is_runtime_checkable(self):
        """isinstance works against ExecutableBridgeAdapter at runtime."""
        assert not isinstance(object(), ExecutableBridgeAdapter)

    @pytest.mark.unit
    def test_notebook_execution_adapter_is_runtime_checkable(self):
        """isinstance works against NotebookExecutionAdapter at runtime."""
        assert not isinstance(object(), NotebookExecutionAdapter)

    @pytest.mark.unit
    def test_all_four_protocols_importable_from_protocols_module(self):
        """All four Protocol classes can be imported directly."""
        # Import already happened at the top; just verify the names exist.
        assert ConceptKitAdapter is not None
        assert PedagogicalWorkbenchAdapter is not None
        assert ExecutableBridgeAdapter is not None
        assert NotebookExecutionAdapter is not None


# ---------------------------------------------------------------------------
# AdapterStatus enum
# ---------------------------------------------------------------------------


class TestAdapterStatusEnum:
    """AdapterStatus enum has exactly {unavailable, planned, available}."""

    @pytest.mark.unit
    def test_exactly_three_members(self):
        """AdapterStatus has exactly three members — no more, no less."""
        member_names = {m.name for m in AdapterStatus}
        assert member_names == {"unavailable", "planned", "available"}

    @pytest.mark.unit
    def test_unavailable_member(self):
        """AdapterStatus.unavailable exists and has expected value."""
        assert AdapterStatus.unavailable.value == "unavailable"

    @pytest.mark.unit
    def test_planned_member(self):
        """AdapterStatus.planned exists and has expected value."""
        assert AdapterStatus.planned.value == "planned"

    @pytest.mark.unit
    def test_available_member(self):
        """AdapterStatus.available exists and has expected value."""
        assert AdapterStatus.available.value == "available"

    @pytest.mark.unit
    def test_enum_is_exhaustive(self):
        """No extra members can be constructed with unknown names."""
        with pytest.raises((KeyError, ValueError)):
            AdapterStatus["nonexistent"]


# ---------------------------------------------------------------------------
# fake_adapter isinstance checks
# ---------------------------------------------------------------------------


class TestFakeAdapterIsinstanceChecks:
    """Fake implementations satisfy their respective protocols at runtime."""

    @pytest.mark.unit
    def test_fake_concept_kit_satisfies_protocol(self):
        """isinstance(FakeConceptKit(), ConceptKitAdapter) is True."""
        assert isinstance(FakeConceptKit(), ConceptKitAdapter)

    @pytest.mark.unit
    def test_fake_pedagogical_workbench_satisfies_protocol(self):
        """isinstance(FakePedagogicalWorkbench(), PedagogicalWorkbenchAdapter) is True."""
        assert isinstance(FakePedagogicalWorkbench(), PedagogicalWorkbenchAdapter)

    @pytest.mark.unit
    def test_fake_executable_bridge_satisfies_protocol(self):
        """isinstance(FakeExecutableBridge(), ExecutableBridgeAdapter) is True."""
        assert isinstance(FakeExecutableBridge(), ExecutableBridgeAdapter)

    @pytest.mark.unit
    def test_fake_notebook_execution_satisfies_protocol(self):
        """isinstance(FakeNotebookExecution(), NotebookExecutionAdapter) is True."""
        assert isinstance(FakeNotebookExecution(), NotebookExecutionAdapter)

    @pytest.mark.unit
    def test_fake_does_not_satisfy_wrong_protocol(self):
        """A fake for one protocol does not satisfy a different protocol's methods."""
        # FakeConceptKit has generate_concept_kit, not analyse_pedagogy
        assert not isinstance(FakeConceptKit(), PedagogicalWorkbenchAdapter)

    @pytest.mark.unit
    def test_fake_concept_kit_returns_deterministic_payload(self):
        """FakeConceptKit.generate_concept_kit returns a stable dict with required keys."""
        adapter = FakeConceptKit()
        result = adapter.generate_concept_kit(_BOUNDED_EXCERPT)
        assert result["adapter"] == "FakeConceptKit"
        assert result["status"] == "ok"
        assert "concepts" in result

    @pytest.mark.unit
    def test_fake_pedagogical_workbench_returns_deterministic_payload(self):
        """FakePedagogicalWorkbench.analyse_pedagogy returns a stable dict."""
        adapter = FakePedagogicalWorkbench()
        result = adapter.analyse_pedagogy(_BOUNDED_EXCERPT)
        assert result["adapter"] == "FakePedagogicalWorkbench"
        assert result["status"] == "ok"

    @pytest.mark.unit
    def test_fake_executable_bridge_returns_deterministic_payload(self):
        """FakeExecutableBridge.build_executable returns a stable dict."""
        adapter = FakeExecutableBridge()
        result = adapter.build_executable(_BOUNDED_EXCERPT)
        assert result["adapter"] == "FakeExecutableBridge"
        assert result["status"] == "ok"

    @pytest.mark.unit
    def test_fake_notebook_execution_returns_deterministic_payload(self):
        """FakeNotebookExecution.build_notebook returns a stable dict with cells."""
        adapter = FakeNotebookExecution()
        result = adapter.build_notebook(_BOUNDED_EXCERPT)
        assert result["adapter"] == "FakeNotebookExecution"
        assert result["status"] == "ok"
        assert "cells" in result
        assert len(result["cells"]) >= 1

    @pytest.mark.unit
    def test_notebook_cells_carry_execution_metadata_keys(self):
        """Notebook stub cells carry no_execute, illustrative_only, adapter_executable."""
        adapter = FakeNotebookExecution()
        result = adapter.build_notebook(_BOUNDED_EXCERPT)
        cell = result["cells"][0]
        meta = cell.get("metadata", {})
        assert "no_execute" in meta
        assert "illustrative_only" in meta
        assert "adapter_executable" in meta


# ---------------------------------------------------------------------------
# Canary — no mutation of AKMS graph or global vault
# ---------------------------------------------------------------------------

# Patterns that indicate an AKMS/vault write operation in source code.
# We scan raw file bytes so we catch any encoding-trick attempts.
_FORBIDDEN_PATTERNS: list[re.Pattern] = [
    re.compile(rb'write_text\s*\('),
    re.compile(rb'open\s*\([^)]*["\']w["\']'),
    re.compile(rb'open\s*\([^)]*["\']wb["\']'),
    re.compile(rb'open\s*\([^)]*["\']a["\']'),
    re.compile(rb'\.mkdir\s*\('),
    re.compile(rb'~[/\\]\.claude[/\\]akms'),           # hard-coded vault path
    re.compile(rb'AKMS_GLOBAL_VAULT.*=.*(?!os\.environ)', re.DOTALL),  # writing env var
]


class TestNoMutationCanary:
    """Adapter source files must not contain AKMS graph/vault write operations."""

    @pytest.mark.unit
    @pytest.mark.parametrize("source_file", _ADAPTER_SOURCE_FILES, ids=lambda p: p.name)
    def test_no_write_operations_in_source(self, source_file: pathlib.Path):
        """No forbidden write patterns appear in adapter source files."""
        content = source_file.read_bytes()
        for pattern in _FORBIDDEN_PATTERNS:
            match = pattern.search(content)
            assert match is None, (
                f"Forbidden mutation pattern {pattern.pattern!r} found in "
                f"{source_file.name} at byte offset {match.start()}"
            )

    @pytest.mark.unit
    def test_adapter_files_all_exist(self):
        """All expected adapter source files exist on disk."""
        for source_file in _ADAPTER_SOURCE_FILES:
            assert source_file.exists(), f"Missing adapter source file: {source_file}"


# ---------------------------------------------------------------------------
# Registry defaults to unavailable/planned
# ---------------------------------------------------------------------------


class TestAdapterRegistry:
    """Registry returns unavailable/planned when no real adapter installed."""

    @pytest.mark.unit
    def test_registry_returns_all_four_capabilities(self):
        """adapter_registry() always returns all four capability keys."""
        registry = adapter_registry()
        expected_keys = {
            "concept_kit_adapter",
            "pedagogical_workbench_adapter",
            "executable_bridge_adapter",
            "notebook_execution_adapter",
        }
        assert set(registry.keys()) == expected_keys

    @pytest.mark.unit
    def test_registry_defaults_are_unavailable_or_planned(self):
        """All four adapters report unavailable or planned with no real install."""
        registry = adapter_registry()
        for key, status in registry.items():
            assert status in (AdapterStatus.unavailable, AdapterStatus.planned), (
                f"Adapter {key!r} reported {status!r}; "
                f"expected unavailable or planned with no real adapter installed"
            )

    @pytest.mark.unit
    def test_registry_none_report_available_by_default(self):
        """No capability reports 'available' in the default (no real adapter) registry."""
        registry = adapter_registry()
        available_caps = [k for k, v in registry.items() if v == AdapterStatus.available]
        assert available_caps == [], (
            f"Expected no available adapters by default; got: {available_caps}"
        )

    @pytest.mark.unit
    def test_registry_is_deterministic(self):
        """adapter_registry() is stable across multiple calls."""
        assert adapter_registry() == adapter_registry()

    @pytest.mark.unit
    def test_registry_override_injects_available(self):
        """Passing overrides can set a capability to available (used by tests / future real adapters)."""
        registry = adapter_registry(
            overrides={"concept_kit_adapter": AdapterStatus.available}
        )
        assert registry["concept_kit_adapter"] == AdapterStatus.available
        # Others still planned
        assert registry["pedagogical_workbench_adapter"] in (
            AdapterStatus.unavailable, AdapterStatus.planned
        )

    @pytest.mark.unit
    def test_registry_override_unknown_key_raises(self):
        """Passing an unknown capability name to overrides raises ValueError."""
        with pytest.raises(ValueError, match="Unknown adapter capability"):
            adapter_registry(overrides={"nonexistent_adapter": AdapterStatus.available})

    @pytest.mark.unit
    def test_registry_result_is_sorted(self):
        """adapter_registry() returns keys in sorted order."""
        registry = adapter_registry()
        keys = list(registry.keys())
        assert keys == sorted(keys), "Registry keys must be sorted for deterministic output"


# ---------------------------------------------------------------------------
# Integration: fakes accept bounded excerpts
# ---------------------------------------------------------------------------


class TestFakesAcceptBoundedExcerpts:
    """Fakes correctly accept bounded LSP-style excerpts and return deterministic output."""

    @pytest.mark.unit
    def test_concept_kit_with_bounded_excerpt(self):
        """FakeConceptKit accepts a bounded excerpt and echoes its keys."""
        adapter = FakeConceptKit()
        result = adapter.generate_concept_kit(_BOUNDED_EXCERPT, options={"depth": "shallow"})
        assert result["excerpt_keys"] == sorted(_BOUNDED_EXCERPT.keys())
        assert result["options_received"] is True

    @pytest.mark.unit
    def test_pedagogical_workbench_with_bounded_excerpt(self):
        """FakePedagogicalWorkbench accepts a bounded excerpt."""
        adapter = FakePedagogicalWorkbench()
        result = adapter.analyse_pedagogy(_BOUNDED_EXCERPT)
        assert result["excerpt_keys"] == sorted(_BOUNDED_EXCERPT.keys())
        assert result["options_received"] is False

    @pytest.mark.unit
    def test_executable_bridge_with_bounded_excerpt(self):
        """FakeExecutableBridge accepts a bounded excerpt."""
        adapter = FakeExecutableBridge()
        result = adapter.build_executable(_BOUNDED_EXCERPT)
        assert result["excerpt_keys"] == sorted(_BOUNDED_EXCERPT.keys())

    @pytest.mark.unit
    def test_notebook_execution_with_bounded_excerpt(self):
        """FakeNotebookExecution accepts a bounded excerpt."""
        adapter = FakeNotebookExecution()
        result = adapter.build_notebook(_BOUNDED_EXCERPT)
        assert result["excerpt_keys"] == sorted(_BOUNDED_EXCERPT.keys())

    @pytest.mark.unit
    def test_all_fakes_tolerate_options_none(self):
        """All fakes accept options=None without error."""
        excerpt = {"key": "value"}
        FakeConceptKit().generate_concept_kit(excerpt, options=None)
        FakePedagogicalWorkbench().analyse_pedagogy(excerpt, options=None)
        FakeExecutableBridge().build_executable(excerpt, options=None)
        FakeNotebookExecution().build_notebook(excerpt, options=None)
