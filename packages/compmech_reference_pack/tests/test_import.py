"""The compmech_reference_pack package exists and its dependencies resolve.

Acceptance criteria:
  - ``uv sync`` resolves akms-learn into the package env (the hard dependency).
  - the package is importable without the MechDSL backend installed.
  - with the ``mechdsl`` extra installed, the Tier-1 backend (mechdsl-core) and
    algo2code resolve and import Taichi-free.

akms-learn (the Tier-2 host) is a hard dependency and must always import.
mechdsl-core (the Tier-1 backend) and algo2code (its transpiler) are an optional
``[mechdsl]`` extra — their import tests ``importorskip`` so a core-only install
(e.g. a downstream consumer that omits the extra to keep Taichi out of its lock
closure) collects green, while a full install still validates resolution.
"""

from __future__ import annotations

import importlib
import sys

import pytest


@pytest.mark.unit
def test_import_package() -> None:
    """The package imports cleanly and exposes a version."""
    mod = importlib.import_module("compmech_reference_pack")
    assert mod.__version__


@pytest.mark.unit
def test_akms_learn_dependency_resolves() -> None:
    """akms-learn (Tier-2 host) — the adapter protocols module — is importable."""
    protocols = importlib.import_module("akms_learn.adapters.protocols")
    assert hasattr(protocols, "ExecutableBridgeAdapter")


@pytest.mark.unit
def test_mechdsl_tier1_dependency_resolves_taichi_free() -> None:
    """With the ``mechdsl`` extra, the Tier-1 façade imports Taichi-free.

    Skips when the optional backend is not installed (a core-only consumer that
    omits ``compmech-reference-pack[mechdsl]``).
    """
    pytest.importorskip(
        "mechdsl.integration",
        reason="optional 'mechdsl' extra not installed (install compmech-reference-pack[mechdsl])",
    )
    assert "taichi" not in sys.modules, (
        "importing mechdsl.integration must not initialise Taichi"
    )


@pytest.mark.unit
def test_algo2code_dependency_resolves() -> None:
    """With the ``mechdsl`` extra, algo2code (the transpiler backend) is importable.

    Skips when the optional backend is not installed.
    """
    pytest.importorskip(
        "algo2code",
        reason="optional 'mechdsl' extra not installed (install compmech-reference-pack[mechdsl])",
    )
