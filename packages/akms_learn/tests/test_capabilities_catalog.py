"""Unit tests for the capabilities catalog.

Covers the catalog module's contract:

* Six structured mode/exporter strings are exposed.
* Four advanced adapter strings appear in
  :func:`capabilities_with_status` with status ``unavailable`` /
  ``planned`` / ``available`` — never silently dropped.
* :func:`unavailable_capabilities` returns structured records with the
  ``missing_extra`` populated.
* Regression: no known capability string disappears from the catalog.

Cross-mode end-to-end coverage lives in
``test_cross_mode_structured.py`` (integration tier).
"""

from __future__ import annotations

import importlib.util as _iu
from typing import Any

import pytest

from akms_learn.adapters import AdapterStatus
from akms_learn.capabilities_catalog import (
    ADAPTER_CAPABILITIES,
    BASELINE_CAPABILITIES,
    EXPORTER_CAPABILITIES,
    all_capabilities,
    capabilities_with_status,
    unavailable_capabilities,
)
from akms_learn.capability_gates import build_capability_gate
from akms_learn.plugin import get_plugin


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_extras(monkeypatch: pytest.MonkeyPatch, available: set[str]) -> None:
    """Patch ``importlib.util.find_spec`` so the named extras appear installed.

    Only ``nbformat`` and ``jinja2`` are extras-probed by the gate.  The
    ``llm`` extra uses ``None`` as its probe so the gate's
    :func:`build_capability_gate` always reports ``llm: False`` regardless of
    ``find_spec``.  Tests that need the ``llm`` extra patch
    ``probe_optional_extras`` directly (see
    ``_open_llm_gate``).
    """
    original = _iu.find_spec

    probe_to_package = {"notebook": "nbformat", "html": "jinja2"}

    def _patched(name: str, *args: Any, **kwargs: Any):
        for extra in available:
            pkg = probe_to_package.get(extra)
            if pkg is not None and name == pkg:
                return object()
        return original(name, *args, **kwargs)

    monkeypatch.setattr(_iu, "find_spec", _patched)


def _open_llm_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force ``probe_optional_extras`` to report ``llm: True``.

    The ``llm`` extra has no concrete probe package — every probe returns
    ``False`` by design unless callers explicitly override.  Tests that need
    ``llm`` available patch ``probe_optional_extras`` to flip the flag.
    """
    import akms_learn.capability_gates as cap_gates

    original = cap_gates.probe_optional_extras

    def _patched() -> dict[str, bool]:
        result = original()
        result["llm"] = True
        return result

    monkeypatch.setattr(cap_gates, "probe_optional_extras", _patched)


# ---------------------------------------------------------------------------
# Six structured mode/exporter strings always present in catalog
# ---------------------------------------------------------------------------


PLAN3_MODE_AND_EXPORTER_STRINGS: tuple[str, ...] = (
    "notebook_source",
    "notebook_export",
    "assessment_first",
    "quiz_export",
    "llm_expanded",
    "adaptive_path",
)


@pytest.mark.unit
def test_all_six_structured_mode_and_exporter_strings_present() -> None:
    """All six structured mode/exporter strings appear in the catalog."""
    caps = set(all_capabilities())
    missing = set(PLAN3_MODE_AND_EXPORTER_STRINGS) - caps
    assert not missing, f"missing structured-mode capabilities: {sorted(missing)}"


@pytest.mark.unit
def test_plugin_capabilities_delegates_to_catalog() -> None:
    """``Plugin.capabilities()`` returns exactly :func:`all_capabilities`."""
    assert get_plugin().capabilities() == all_capabilities()


# ---------------------------------------------------------------------------
# Four adapter capabilities always present with status
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_adapter_capabilities_surface_with_status_when_no_real_adapter() -> None:
    """All four adapter strings present with ``unavailable``/``planned``.

    With no real adapter installed every adapter capability defaults to
    ``planned`` (see :data:`adapters.status._DEFAULT_REGISTRY`).  The catalog
    MUST report all four — silently dropping any of them breaks consumers.
    """
    entries = capabilities_with_status()
    by_name = {e["capability"]: e["status"] for e in entries}

    for adapter_cap in ADAPTER_CAPABILITIES:
        assert adapter_cap in by_name, (
            f"adapter capability {adapter_cap!r} disappeared from "
            f"capabilities_with_status() output"
        )
        assert by_name[adapter_cap] in {"planned", "unavailable", "available"}
        # With no override the registry default is `planned`.
        assert by_name[adapter_cap] == "planned"


@pytest.mark.unit
def test_adapter_status_override_surfaces_available() -> None:
    """A real adapter override flips status to ``available``."""
    overrides = {"concept_kit_adapter": AdapterStatus.available}
    entries = capabilities_with_status(adapter_overrides=overrides)
    by_name = {e["capability"]: e["status"] for e in entries}
    assert by_name["concept_kit_adapter"] == "available"
    # Other adapters remain `planned`.
    assert by_name["pedagogical_workbench_adapter"] == "planned"
    assert by_name["executable_bridge_adapter"] == "planned"
    assert by_name["notebook_execution_adapter"] == "planned"


# ---------------------------------------------------------------------------
# unavailable_capabilities slot is structured
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_unavailable_capabilities_lists_missing_extras(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extras-gated capabilities whose extra is absent appear with
    the ``missing_extra`` populated, sorted by capability name."""

    # Force every extra absent.
    def _none(name: str, *args: Any, **kwargs: Any):
        return None

    monkeypatch.setattr(_iu, "find_spec", _none)

    rows = unavailable_capabilities()
    by_cap = {r["capability"]: r["missing_extra"] for r in rows}

    # Every extras-gated capability is reported.
    assert by_cap == {
        "notebook_source": "notebook",
        "notebook_export": "notebook",
        "assessment_first": "notebook",
        "quiz_export": "html",
        "html_export": "html",
        "llm_expanded": "llm",
        "adaptive_path": "llm",
    }

    # Sorted ascending by capability key.
    keys = [r["capability"] for r in rows]
    assert keys == sorted(keys)


@pytest.mark.unit
def test_unavailable_capabilities_empty_when_all_extras_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When every extra is installed, no capability is unavailable."""
    _patch_extras(monkeypatch, available={"notebook", "html"})
    _open_llm_gate(monkeypatch)
    rows = unavailable_capabilities()
    assert rows == []


@pytest.mark.unit
def test_capabilities_with_status_marks_extras_capabilities_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With every extra installed, every extras-gated capability is ``available``."""
    _patch_extras(monkeypatch, available={"notebook", "html"})
    _open_llm_gate(monkeypatch)
    entries = capabilities_with_status()
    by_name = {e["capability"]: e["status"] for e in entries}
    for cap in (
        "notebook_source",
        "notebook_export",
        "assessment_first",
        "quiz_export",
        "html_export",
        "llm_expanded",
        "adaptive_path",
    ):
        assert by_name[cap] == "available"


@pytest.mark.unit
def test_capabilities_with_status_marks_absent_extras_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no extras installed, every extras-gated capability is ``unavailable``."""
    monkeypatch.setattr(_iu, "find_spec", lambda *a, **kw: None)
    entries = capabilities_with_status()
    by_name = {e["capability"]: e["status"] for e in entries}
    for cap in (
        "notebook_source",
        "notebook_export",
        "assessment_first",
        "quiz_export",
        "html_export",
        "llm_expanded",
        "adaptive_path",
    ):
        assert by_name[cap] == "unavailable"


# ---------------------------------------------------------------------------
# Append-only regression: known strings never disappear
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_baseline_eighteen_strings_preserved() -> None:
    """The 18 strings already returned by ``Plugin.capabilities()`` remain.

    Memory 4239 notes the legacy method returned hardcoded strings; this
    test pins the exact eighteen-string baseline so any future refactor
    that accidentally drops one fails loudly.
    """
    caps = set(get_plugin().capabilities())
    expected_baseline = {
        # Original six.
        "learning_source_packet",
        "deterministic_outline",
        "node_anthology",
        "pitfall_driven",
        "markdown_export",
        "bundle_export",
        # Domain-pack additions.
        "domain_pack_registry",
        "static_domain_pack_descriptors",
        "source_pack_descriptors",
        "code_mirror_provenance",
        # Four pedagogical modes.
        "pedagogical_template",
        "derivation_first",
        "implementation_first",
        "multi_granularity",
        # Four structured modes.
        "notebook_source",
        "adaptive_path",
        "assessment_first",
        "llm_expanded",
    }
    missing = expected_baseline - caps
    assert not missing, f"baseline capability strings disappeared: {missing}"


@pytest.mark.regression
def test_appended_exporter_strings_present() -> None:
    """The three exporter capability strings appear in the catalog."""
    caps = set(get_plugin().capabilities())
    for cap in EXPORTER_CAPABILITIES:
        assert cap in caps, f"exporter capability {cap!r} missing"


@pytest.mark.regression
def test_appended_adapter_strings_present() -> None:
    """The four adapter capability strings appear in the catalog."""
    caps = set(get_plugin().capabilities())
    for cap in ADAPTER_CAPABILITIES:
        assert cap in caps, f"adapter capability {cap!r} missing"


@pytest.mark.regression
def test_baseline_tuple_matches_plugin_first_eighteen() -> None:
    """``BASELINE_CAPABILITIES`` matches the first eighteen entries of plugin output.

    This guards against accidental reordering of the baseline group — the
    append-only invariant only holds if existing positions are stable.
    """
    caps = get_plugin().capabilities()
    assert caps[: len(BASELINE_CAPABILITIES)] == list(BASELINE_CAPABILITIES)


@pytest.mark.regression
def test_capabilities_with_status_never_silently_drops_adapters() -> None:
    """Adapter strings appear in status output regardless of installed extras."""
    gate = build_capability_gate()
    entries = capabilities_with_status(gate=gate)
    names = {e["capability"] for e in entries}
    for adapter_cap in ADAPTER_CAPABILITIES:
        assert adapter_cap in names, (
            f"{adapter_cap!r} silently dropped from capabilities_with_status()"
        )
