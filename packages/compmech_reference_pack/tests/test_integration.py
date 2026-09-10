"""end-to-end executable-bridge integration on a fixture LSP excerpt.

Covers the deliverable acceptance:
  - isinstance(MechDSLRunner(), ExecutableBridgeAdapter);
  - a radial-return node excerpt -> build_executable -> valid transpiled Python
    + provenance carrying references (Simo & Hughes);
  - run_verify=False does not initialise Taichi (fresh-interpreter subprocess);
  - one run_verify=True slow test that exercises the Taichi-paying branch.
"""

from __future__ import annotations

import subprocess
import sys

import pytest
from akms_learn.adapters.protocols import ExecutableBridgeAdapter
from compmech_reference_pack.adapters.mechdsl_runner import MechDSLRunner

# A radial-return learning node, markdown-authored (no % directives) — the
# common LSP-node shape, with a Simo & Hughes provenance reference.
_RADIAL_RETURN_IMPL = "\n".join(
    [
        "## Return mapping (J2, isotropic power-law hardening)",
        "",
        "```latex",
        r"\begin{algorithmic}",
        r"\State $sy \gets sigy0 + K \cdot \alpha^{n}$",
        r"\State $f = sigma_eq - sy$",
        r"\If{$f < 0$}",
        r"\State $dl = 0$",
        r"\Else",
        r"\State $dl = f / (3 \cdot mu)$",
        r"\EndIf",
        r"\end{algorithmic}",
        "```",
    ]
)


def _radial_return_excerpt() -> dict:
    return {
        "node_id": "compmech.node.radial_return_j2",
        "extracted": {"implementation": _RADIAL_RETURN_IMPL},
        "included_sections": [
            {"heading": "Return-mapping algorithm", "source_path": "dev/notes/j2.md"}
        ],
        "references": [
            {
                "citation": "Simo & Hughes (1998), Computational Inelasticity",
                "source_node_ids": ["compmech.node.radial_return_j2"],
            }
        ],
    }


@pytest.mark.integration
def test_runner_satisfies_protocol() -> None:
    assert isinstance(MechDSLRunner(), ExecutableBridgeAdapter)


@pytest.mark.integration
def test_build_executable_end_to_end() -> None:
    result = MechDSLRunner().build_executable(_radial_return_excerpt())

    assert result["adapter"] == "compmech.mechdsl_runner"
    assert result["status"] == "ok"

    transpiled = result["transpiled"]
    assert transpiled is not None
    assert transpiled["valid_python"] is True
    assert transpiled["entry_point"] == "radial_return_j2"

    assert result["normalized_input"]
    prov = result["provenance"]["compmech.node.radial_return_j2"]
    assert any("Simo & Hughes" in str(ref) for ref in prov["references"])
    assert prov["sections"]

    # Emit-only default: no Taichi-paying verification attached.
    assert "verification" not in result


@pytest.mark.integration
def test_run_verify_false_does_not_initialise_taichi() -> None:
    """The load-bearing contract: the default emit path stays Taichi-free.

    Run in a fresh interpreter so no parent-process Taichi import contaminates
    the check.
    """
    script = "\n".join(
        [
            "import sys",
            "from compmech_reference_pack.adapters.mechdsl_runner import MechDSLRunner",
            "impl = chr(10).join([r'\\begin{algorithmic}', r'\\State $y = a \\cdot b$', r'\\end{algorithmic}'])",
            "excerpt = {'node_id': 'n', 'extracted': {'implementation': impl}}",
            "res = MechDSLRunner().build_executable(excerpt, options={'run_verify': False})",
            "assert res['transpiled'] is not None and res['transpiled']['valid_python']",
            "loaded = 'taichi' in sys.modules",
            "print('taichi_loaded:', loaded)",
            "sys.exit(1 if loaded else 0)",
        ]
    )
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, (
        "build_executable(run_verify=False) initialised Taichi.\n"
        f"stdout: {proc.stdout!r}\nstderr: {proc.stderr!r}"
    )
    assert "taichi_loaded: False" in proc.stdout


@pytest.mark.integration
@pytest.mark.slow
def test_run_verify_true_pays_taichi_and_returns_result() -> None:
    """run_verify=True reaches the Tier-1 verify branch (the Taichi-paying path)."""
    options = {
        "run_verify": True,
        "verify_kind": "patch_test",
        "verify_params": {"nx": 1, "ny": 1, "nz": 1, "lam": 1.0, "mu": 1.0},
    }
    result = MechDSLRunner().build_executable(_radial_return_excerpt(), options=options)

    assert "verification" in result
    verification = result["verification"]
    assert verification["kind"] == "patch_test"
    assert isinstance(verification["passed"], bool)
    assert "details" in verification
