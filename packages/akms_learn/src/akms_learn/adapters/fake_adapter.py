"""Fake adapter implementations for tests ONLY.

WARNING: These classes are for use in tests ONLY.  They are intentionally
trivial; they return hard-coded stub payloads and do NOT perform any real
computation.  Never import fake_adapter in production code.

No-mutation invariant
---------------------
Fake adapters MUST NOT write to any AKMS path.  All output is returned in
memory as plain Python dicts.

Protocol conformance
--------------------
Each class satisfies its corresponding Protocol via structural subtyping.
Because the Protocols are ``@runtime_checkable``, the isinstance checks::

    isinstance(FakeConceptKit(), ConceptKitAdapter)
    isinstance(FakePedagogicalWorkbench(), PedagogicalWorkbenchAdapter)
    isinstance(FakeExecutableBridge(), ExecutableBridgeAdapter)
    isinstance(FakeNotebookExecution(), NotebookExecutionAdapter)

all return True.
"""

from __future__ import annotations

from typing import Any

from akms_learn.adapters.protocols import (
    ConceptKitAdapter,
    ExecutableBridgeAdapter,
    NotebookExecutionAdapter,
    PedagogicalWorkbenchAdapter,
)

__all__ = [
    "FakeConceptKit",
    "FakeExecutableBridge",
    "FakeNotebookExecution",
    "FakePedagogicalWorkbench",
]


class FakeConceptKit:
    """Fake ConceptKitAdapter — returns a deterministic stub payload.

    Satisfies :class:`~akms_learn.adapters.protocols.ConceptKitAdapter`
    structurally (and via ``isinstance`` due to ``@runtime_checkable``).
    """

    def generate_concept_kit(
        self,
        excerpt: dict[str, Any],
        *,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a deterministic stub concept-kit payload."""
        return {
            "adapter": "FakeConceptKit",
            "status": "ok",
            "concepts": ["stub_concept_A", "stub_concept_B"],
            "excerpt_keys": sorted(excerpt.keys()),
            "options_received": options is not None,
        }


class FakePedagogicalWorkbench:
    """Fake PedagogicalWorkbenchAdapter — returns a deterministic stub payload.

    Satisfies :class:`~akms_learn.adapters.protocols.PedagogicalWorkbenchAdapter`
    structurally (and via ``isinstance`` due to ``@runtime_checkable``).
    """

    def analyse_pedagogy(
        self,
        excerpt: dict[str, Any],
        *,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a deterministic stub pedagogical analysis payload."""
        return {
            "adapter": "FakePedagogicalWorkbench",
            "status": "ok",
            "objectives": ["stub_objective_1"],
            "difficulty": "intermediate",
            "excerpt_keys": sorted(excerpt.keys()),
            "options_received": options is not None,
        }


class FakeExecutableBridge:
    """Fake ExecutableBridgeAdapter — returns a deterministic stub payload.

    Satisfies :class:`~akms_learn.adapters.protocols.ExecutableBridgeAdapter`
    structurally (and via ``isinstance`` due to ``@runtime_checkable``).
    """

    def build_executable(
        self,
        excerpt: dict[str, Any],
        *,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a deterministic stub executable-artefact payload."""
        return {
            "adapter": "FakeExecutableBridge",
            "status": "ok",
            "executable_type": "stub",
            "source": "# stub source",
            "excerpt_keys": sorted(excerpt.keys()),
            "options_received": options is not None,
        }


class FakeNotebookExecution:
    """Fake NotebookExecutionAdapter — returns a deterministic stub payload.

    Satisfies :class:`~akms_learn.adapters.protocols.NotebookExecutionAdapter`
    structurally (and via ``isinstance`` due to ``@runtime_checkable``).

    The stub cells include all three notebook-metadata keys described in the
    ``NotebookExecutionAdapter`` docstring (``no_execute``,
    ``illustrative_only``, ``adapter_executable``) so that downstream
    notebook-exporter tests can rely on them.
    """

    def build_notebook(
        self,
        excerpt: dict[str, Any],
        *,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a deterministic stub notebook payload."""
        stub_cell = {
            "cell_type": "code",
            "source": "# stub cell",
            "metadata": {
                "no_execute": False,
                "illustrative_only": True,
                "adapter_executable": False,
            },
            "outputs": [],
        }
        return {
            "adapter": "FakeNotebookExecution",
            "status": "ok",
            "nbformat": 4,
            "nbformat_minor": 5,
            "cells": [stub_cell],
            "excerpt_keys": sorted(excerpt.keys()),
            "options_received": options is not None,
        }


# ---------------------------------------------------------------------------
# Runtime isinstance-compatibility assertions (module-level, evaluated once).
# ---------------------------------------------------------------------------
# These raise AssertionError at import time if the structural subtyping is
# accidentally broken, making test failures loud and immediate.

assert isinstance(FakeConceptKit(), ConceptKitAdapter), (
    "FakeConceptKit must satisfy ConceptKitAdapter protocol"
)
assert isinstance(FakePedagogicalWorkbench(), PedagogicalWorkbenchAdapter), (
    "FakePedagogicalWorkbench must satisfy PedagogicalWorkbenchAdapter protocol"
)
assert isinstance(FakeExecutableBridge(), ExecutableBridgeAdapter), (
    "FakeExecutableBridge must satisfy ExecutableBridgeAdapter protocol"
)
assert isinstance(FakeNotebookExecution(), NotebookExecutionAdapter), (
    "FakeNotebookExecution must satisfy NotebookExecutionAdapter protocol"
)
