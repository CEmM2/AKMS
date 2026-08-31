"""Generic protocol surfaces for the four advanced-companion adapters.

No-mutation invariant
---------------------
Adapter implementations MUST NOT write to the AKMS global vault, mutate AKMS
graph objects, or perform any filesystem write targeting AKMS-owned paths.

All four protocols consume *validated LSP excerpts* or *bounded excerpts* —
small, self-contained data structures derived from a compiled LSP (Learner
Support Pack).  Return types are generic ``dict[str, Any]`` so that
downstream Phase-2/3 code can pattern-match on the keys without this module
importing domain-specific types from computational mechanics.

Design principles
-----------------
- ``@runtime_checkable`` is required so that ``isinstance(obj, Protocol)``
  works in tests.
- Method signatures use only built-in Python types and ``Any`` to avoid
  coupling to optional or domain-specific packages.
- Real runners (constkit, symbolic_fem_workbench, MechDSL) remain out of
  scope; only the protocol shape is defined here.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = [
    "ConceptKitAdapter",
    "ExecutableBridgeAdapter",
    "NotebookExecutionAdapter",
    "PedagogicalWorkbenchAdapter",
]


@runtime_checkable
class ConceptKitAdapter(Protocol):
    """Protocol for concept-kit generation from bounded LSP excerpts.

    A ConceptKit adapter receives a bounded excerpt from a validated LSP and
    produces structured concept-definition artefacts (concept cards, glossary
    entries, prerequisite maps, etc.).  The exact schema of the returned dict
    is defined by the implementing package.

    No-mutation contract: implementations MUST NOT write to any AKMS path.
    """

    def generate_concept_kit(
        self,
        excerpt: dict[str, Any],
        *,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a concept kit from a bounded LSP excerpt.

        Parameters
        ----------
        excerpt:
            A bounded, validated excerpt from a compiled LSP.  Keys and
            structure are defined by the LSP schema; adapters MUST NOT assume
            any extra context beyond this dict.
        options:
            Optional adapter-specific configuration (e.g. target audience,
            depth level).  Implementations must tolerate ``None``.

        Returns
        -------
        dict[str, Any]
            Adapter-specific concept-kit payload.  Must always include at
            minimum the key ``"adapter"`` (adapter name string) and
            ``"status"`` (string, typically ``"ok"`` or ``"error"``).
        """
        ...


@runtime_checkable
class PedagogicalWorkbenchAdapter(Protocol):
    """Protocol for pedagogical analysis and scaffolding from bounded excerpts.

    A PedagogicalWorkbench adapter receives a bounded LSP excerpt and returns
    pedagogical structure — e.g. learning objective trees, prerequisite
    hierarchies, difficulty estimates, or scaffolding suggestions.

    No-mutation contract: implementations MUST NOT write to any AKMS path.
    """

    def analyse_pedagogy(
        self,
        excerpt: dict[str, Any],
        *,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Analyse a bounded LSP excerpt and return pedagogical structure.

        Parameters
        ----------
        excerpt:
            A bounded, validated excerpt from a compiled LSP.
        options:
            Optional adapter-specific configuration.  Implementations must
            tolerate ``None``.

        Returns
        -------
        dict[str, Any]
            Adapter-specific pedagogical analysis payload.  Must always include
            ``"adapter"`` and ``"status"`` keys.
        """
        ...


@runtime_checkable
class ExecutableBridgeAdapter(Protocol):
    """Protocol for bridging bounded LSP excerpts to executable environments.

    An ExecutableBridge adapter converts a bounded LSP excerpt into an
    artefact that can be submitted to an external executor (e.g. a Jupyter
    kernel, a sandboxed Python runner, or a symbolic solver).  The adapter
    does NOT execute code itself; it only produces the artefact.

    No-mutation contract: implementations MUST NOT write to any AKMS path.
    """

    def build_executable(
        self,
        excerpt: dict[str, Any],
        *,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build an executable artefact from a bounded LSP excerpt.

        Parameters
        ----------
        excerpt:
            A bounded, validated excerpt from a compiled LSP.
        options:
            Optional adapter-specific configuration (e.g. target kernel,
            sandbox constraints).  Implementations must tolerate ``None``.

        Returns
        -------
        dict[str, Any]
            Adapter-specific executable artefact payload.  Must always include
            ``"adapter"`` and ``"status"`` keys.
        """
        ...


@runtime_checkable
class NotebookExecutionAdapter(Protocol):
    """Protocol for notebook-execution artefact generation from bounded excerpts.

    A NotebookExecution adapter converts a bounded LSP excerpt into a notebook
    artefact (e.g. an ``nbformat`` cell list or a serialised ``.ipynb`` dict).
    Notebook cells may be tagged with execution metadata; real execution is
    the responsibility of the caller or a downstream runner.

    No-mutation contract: implementations MUST NOT write to any AKMS path.

    Note on notebook metadata
    -------------------------
    Downstream notebook exporters look for the following keys
    inside each cell's metadata dict:

    - ``no_execute``: bool — cell must not be auto-executed.
    - ``illustrative_only``: bool — cell is illustrative; skip in strict mode.
    - ``adapter_executable``: bool — cell is safe for adapter-driven execution.

    Implementations of this protocol are encouraged (but not required) to set
    these keys.  Tests use ``fake_adapter.py`` which always sets all three.
    """

    def build_notebook(
        self,
        excerpt: dict[str, Any],
        *,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build a notebook artefact from a bounded LSP excerpt.

        Parameters
        ----------
        excerpt:
            A bounded, validated excerpt from a compiled LSP.
        options:
            Optional adapter-specific configuration (e.g. kernel name,
            execution policy).  Implementations must tolerate ``None``.

        Returns
        -------
        dict[str, Any]
            Adapter-specific notebook payload.  Must always include
            ``"adapter"`` and ``"status"`` keys.  Implementations should
            include a ``"cells"`` key containing a list of cell dicts, each
            optionally carrying the metadata keys listed above.
        """
        ...
