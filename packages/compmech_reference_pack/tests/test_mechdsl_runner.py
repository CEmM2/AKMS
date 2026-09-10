"""MechDSLRunner — executable_bridge adapter unit tests."""

from __future__ import annotations

import sys
from types import ModuleType

import pytest
from akms_learn.adapters.protocols import ExecutableBridgeAdapter
from akms_learn.adapters.status import AdapterStatus
from compmech_reference_pack.adapters.mechdsl_runner import (
    ADAPTER_ID,
    MechDSLRunner,
    adapter_registry_overrides,
    available_adapter_registry,
)

_IMPL = "\n".join(
    [
        "```latex",
        r"\begin{algorithmic}",
        r"\State $y = a \cdot b$",
        r"\end{algorithmic}",
        "```",
    ]
)


def _excerpt() -> dict:
    return {
        "node_id": "node.demo",
        "extracted": {"implementation": _IMPL},
        "included_sections": [{"heading": "Demo"}],
        "references": [
            {"citation": "Simo & Hughes (1998)", "source_node_ids": ["node.demo"]}
        ],
    }


@pytest.mark.unit
def test_satisfies_executable_bridge_protocol() -> None:
    assert isinstance(MechDSLRunner(), ExecutableBridgeAdapter)


@pytest.mark.unit
def test_can_handle() -> None:
    runner = MechDSLRunner()
    assert runner.can_handle(_excerpt()) is True
    assert runner.can_handle({"node_id": "x", "extracted": {}}) is False


@pytest.mark.unit
def test_build_executable_shape_and_transpile(monkeypatch) -> None:
    integration = ModuleType("mechdsl.integration")
    integration.transpile_algorithm = lambda source, backend: {
        "code": "def node_demo():\n    return None\n",
        "entry_point": "node_demo",
        "valid_python": True,
    }
    mechdsl = ModuleType("mechdsl")
    mechdsl.__path__ = []
    mechdsl.integration = integration
    monkeypatch.setitem(sys.modules, "mechdsl", mechdsl)
    monkeypatch.setitem(sys.modules, "mechdsl.integration", integration)

    result = MechDSLRunner().build_executable(_excerpt())
    assert result["adapter"] == ADAPTER_ID
    assert result["status"] == "ok"
    assert result["transpiled"] is not None
    assert result["transpiled"]["valid_python"] is True
    assert result["normalized_input"]
    assert "node.demo" in result["provenance"]
    assert isinstance(result["warnings"], list)
    # emit-only default: no verification attached
    assert "verification" not in result


@pytest.mark.unit
def test_provenance_carries_references() -> None:
    result = MechDSLRunner().build_executable(_excerpt())
    refs = result["provenance"]["node.demo"]["references"]
    assert any("Simo & Hughes" in str(ref) for ref in refs)


@pytest.mark.unit
def test_registry_override_marks_available() -> None:
    assert (
        adapter_registry_overrides()["executable_bridge_adapter"]
        is AdapterStatus.available
    )
    assert (
        available_adapter_registry()["executable_bridge_adapter"]
        is AdapterStatus.available
    )


@pytest.mark.unit
def test_empty_node_is_error_not_crash() -> None:
    result = MechDSLRunner().build_executable({"node_id": "n", "extracted": {}})
    assert result["status"] == "error"
    assert result["warnings"]


@pytest.mark.unit
def test_missing_backend_degrades_with_install_hint(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "mechdsl.integration", None)

    result = MechDSLRunner().build_executable(_excerpt())

    assert result["status"] == "ok"
    assert result["transpiled"] is None
    assert any(
        "compmech-reference-pack[mechdsl]" in warning for warning in result["warnings"]
    )


@pytest.mark.unit
def test_missing_required_backend_returns_error(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "mechdsl.integration", None)

    result = MechDSLRunner().build_executable(
        _excerpt(), options={"require_executable": True}
    )

    assert result["status"] == "error"
    assert any(
        "MechDSL backend unavailable" in warning for warning in result["warnings"]
    )


@pytest.mark.unit
def test_missing_verify_backend_returns_structured_failure(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "mechdsl.integration", None)

    result = MechDSLRunner().build_executable(_excerpt(), options={"run_verify": True})

    assert result["status"] == "ok"
    assert result["verification"]["passed"] is False
    assert any(
        "MechDSL backend unavailable" in warning for warning in result["warnings"]
    )


@pytest.mark.unit
def test_status_is_taichi_free_descriptor() -> None:
    status = MechDSLRunner().status()
    assert status["adapter"] == ADAPTER_ID
    assert status["available"] is True
    assert status["taichi_required_for"] == ["verify"]


# --- malformed-excerpt robustness (a failed adapter must not crash the packet) ---

_MALFORMED_EXCERPTS = [
    pytest.param({}, id="empty"),
    pytest.param({"nodes": []}, id="empty-nodes"),
    pytest.param({"nodes": ["a string, not a node"]}, id="nodes-str"),
    pytest.param({"nodes": [None]}, id="nodes-none"),
    pytest.param({"node_id": "n", "extracted": "not a dict"}, id="extracted-str"),
    pytest.param({"node_id": "n", "extracted": None}, id="extracted-none"),
    pytest.param(
        {"node_id": "n", "extracted": {}, "references": "not a list"},
        id="references-str",
    ),
]


@pytest.mark.unit
@pytest.mark.parametrize("excerpt", _MALFORMED_EXCERPTS)
def test_build_executable_never_crashes_on_malformed_excerpt(excerpt: dict) -> None:
    result = MechDSLRunner().build_executable(excerpt)
    assert isinstance(result, dict)
    assert result["adapter"] == ADAPTER_ID
    # Nothing to build -> error status + a warning, but never an exception.
    assert result["status"] == "error"
    assert result["warnings"]
    assert "provenance" in result and "vv_plan" in result


@pytest.mark.unit
@pytest.mark.parametrize("excerpt", _MALFORMED_EXCERPTS)
def test_can_handle_is_total_on_malformed_excerpt(excerpt: dict) -> None:
    assert MechDSLRunner().can_handle(excerpt) is False


@pytest.mark.unit
def test_vv_plan_citation_matches_provenance_references() -> None:
    """The vv_plan citation is drawn from the same scoped references as provenance."""
    result = MechDSLRunner().build_executable(_excerpt())
    citation = result["vv_plan"]["citation"]
    prov_refs = result["provenance"]["node.demo"]["references"]
    assert citation == "Simo & Hughes (1998)"
    assert any(citation in str(ref) for ref in prov_refs)
