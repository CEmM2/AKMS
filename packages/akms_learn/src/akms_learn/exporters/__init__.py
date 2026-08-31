"""Exporters that render LearningSourcePackets to bytes/files.

Dispatch contract
-----------------
The **compiler dispatches** exporters from Stage 9 of
:func:`akms_learn.compiler.compile_learning_source`. Callers do NOT invoke
exporters separately after compilation — the request's ``exporters`` list
drives Stage 9, and produced artifacts surface on
``CompileResult.export_paths``. The CLI is a thin wrapper around
``compile_learning_source``; it must not re-invoke exporters either.

Rationale:

* "Export" is the ninth pipeline stage; treating it as part of
  the compiler keeps the 9-stage ordering enforceable by
  ``CompileResult.stage_log``.
* The CLI surface stays minimal: one entry point, one byte-stable artifact
  set per invocation.
* External callers (e.g. Logic-Loom feature detection, review-bundle
  regeneration) get a single mental model: pass a request, receive a
  ``CompileResult``.

Exporter protocol
-----------------
Every exporter (markdown, bundle, notebook, assessment, html) MUST
implement the ``Exporter`` callable protocol below. Concretely each exporter module
exposes a top-level :data:`export` function:

.. code-block:: python

    def export(
        packet: LearningSourcePacket,
        output_dir: Path,
        /,
    ) -> list[Path]:
        '''Write artifacts to *output_dir* and return their absolute paths.

        Implementations MUST:
        * be pure (no network, no LLM, no global state)
        * be deterministic (same inputs → byte-equal outputs except packet
          timestamp)
        * sort any iterable they emit
        * accumulate soft issues as LearningWarning rather than raise
        * raise PacketValidationError only on contract violation
        '''

``KNOWN_EXPORTERS`` is the single source of truth for the names the compiler
will attempt to dispatch. Unknown names emit
``LearningWarning(code='exporter_unavailable')`` — they never raise.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from akms_learn.models import LearningSourcePacket

__all__ = ["Exporter", "KNOWN_EXPORTERS"]


#: Registered exporter names. The compiler attempts ``__import__`` of
#: ``akms_learn.exporters.<name>`` for each entry in ``request.exporters``
#: that is a member of this tuple. Names outside this set always emit
#: ``exporter_unavailable`` warnings.
KNOWN_EXPORTERS: tuple[str, ...] = (
    "markdown",
    "bundle",
    "notebook",
    "assessment",
    "html",
)


@runtime_checkable
class Exporter(Protocol):
    """Callable contract every Phase 4 exporter module must satisfy.

    ``markdown.py`` and ``bundle.py`` expose real ``export`` functions
    matching this protocol.
    """

    def __call__(
        self,
        packet: "LearningSourcePacket",
        output_dir: Path,
        /,
    ) -> list[Path]: ...
