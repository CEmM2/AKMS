"""Structured warning emission for the learn pipeline.

This module provides:

* :class:`WarningAccumulator` — an order-preserving, dedup-on-``(code,
  source_ref)`` collector for :class:`~akms_learn.models.LearningWarning`
  instances. Used throughout the LSP compiler pipeline (Phases 2–4) to gather
  soft issues without short-circuiting compilation.
* Helper emit functions that build canonical :class:`LearningWarning`
  payloads for the common soft-issue shapes consumed by the Phase 3 extractors
  and the Phase 2 validator.

Hard errors are raised through :class:`akms_learn.validation.PacketValidationError`;
the accumulator is exclusively for soft (``warning`` / ``info``) issues.

``DomainPackWarning`` is an independent type —
it reuses the same accumulator *pattern* but should not share
this :class:`WarningAccumulator` instance, which is typed against
:class:`LearningWarning`.
"""

from __future__ import annotations

from typing import Iterable, Iterator, Optional

from akms_learn.models import LearningWarning

__all__ = [
    "WarningAccumulator",
    "emit_missing_section_warning",
    "emit_dangling_reference_warning",
    "emit_code_mirror_missing_source_path_warning",
]


class WarningAccumulator:
    """Order-preserving, deduping collector for :class:`LearningWarning`.

    Dedup key is ``(warning.code, warning.source_ref)``. Two warnings sharing
    that pair are coalesced — only the first occurrence is retained, and the
    insertion order of distinct keys is preserved.

    Example::

        acc = WarningAccumulator()
        acc.append(LearningWarning(severity="warning", code="C", message="m"))
        acc.append(LearningWarning(severity="warning", code="C", message="m2"))
        assert len(acc) == 1
    """

    def __init__(self) -> None:
        self._seen: set[tuple[str, Optional[str]]] = set()
        self._warnings: list[LearningWarning] = []

    def append(self, w: LearningWarning) -> None:
        """Add a warning, deduped on ``(code, source_ref)``."""
        key = (w.code, w.source_ref)
        if key in self._seen:
            return
        self._seen.add(key)
        self._warnings.append(w)

    def extend(self, ws: Iterable[LearningWarning]) -> None:
        """Add multiple warnings; each is independently deduped."""
        for w in ws:
            self.append(w)

    def finalize(self) -> list[LearningWarning]:
        """Return the accumulated warnings in insertion order.

        Safe to call multiple times; returns a shallow copy so callers cannot
        mutate the internal list.
        """
        return list(self._warnings)

    def __len__(self) -> int:
        return len(self._warnings)

    def __iter__(self) -> Iterator[LearningWarning]:
        return iter(self._warnings)


def emit_missing_section_warning(
    node_id: str, section_name: str
) -> LearningWarning:
    """Build a soft warning for a node missing an optional teaching section.

    Used by the Phase 3 extractors when a node lacks ``prerequisites`` /
    ``derivations`` / ``implementations`` / ``pitfalls`` content. The
    ``source_ref`` is namespaced as ``"<node_id>#<section_name>"`` so two
    different missing sections on the same node are NOT deduped.
    """
    return LearningWarning(
        severity="warning",
        code="missing_section",
        message=(
            f"Node {node_id!r} is missing the {section_name!r} teaching "
            "section; downstream views may be incomplete."
        ),
        source_ref=f"{node_id}#{section_name}",
    )


def emit_code_mirror_missing_source_path_warning(
    mirror_node_id: str, edge_id: Optional[str] = None
) -> LearningWarning:
    """Build a soft warning for a code-mirror node lacking a source path.

    This warning is emitted when an ``implements`` edge points at a
    ``code_mirror`` node whose ``source_path`` is missing or set to the
    sentinel ``"unknown"`` value used by the toy executable-bridge fixture.

    The ``source_ref`` is the mirror node id so the warning de-dupes per
    mirror — multiple ``implements`` edges into the same mirror produce one
    warning, not N.
    """
    return LearningWarning(
        severity="warning",
        code="code_mirror_missing_source_path",
        message=(
            f"Code-mirror node {mirror_node_id!r} is referenced by an "
            "implements edge but has no usable source path (missing or "
            "set to 'unknown'); CodeLinkView.file_path will be unset."
        ),
        source_ref=mirror_node_id,
    )


def emit_dangling_reference_warning(
    edge_id: str, missing_node_id: str
) -> LearningWarning:
    """Build a soft warning for an edge that references an unresolved node.

    Exposed for higher layers (e.g. Phase 3 extractors) that may prefer to
    *warn* about a dangling reference rather than raise. The Phase 2
    :func:`akms_learn.validation.validate_packet` itself treats dangling
    edges as a HARD error and raises ``PacketValidationError``.
    """
    return LearningWarning(
        severity="warning",
        code="dangling_reference",
        message=(
            f"Edge {edge_id!r} references node_id {missing_node_id!r} which "
            "is not present in packet.body.nodes."
        ),
        source_ref=edge_id,
    )
