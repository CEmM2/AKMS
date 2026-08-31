"""Validation rules for Learning Source Packets and requests.

This module implements the cross-field invariants Pydantic cannot express in a
``BaseModel`` alone. Pydantic enforces field presence and type; this layer
enforces *relational* requirements between fields (e.g. every edge endpoint
must resolve to a node in the same packet) and traceability metadata
requirements (non-empty hashes).

Hard vs. soft contract
----------------------

**Hard errors** raise :class:`PacketValidationError`:

* Missing ``packet.request.request_hash``.
* Missing ``packet.source.graph_hash``.
* Any :class:`~akms_learn.models.LearningEdgeView` whose ``from`` or ``to``
  references a ``node_id`` not present in ``packet.body.nodes``.

**Soft issues** are accumulated as :class:`~akms_learn.models.LearningWarning`
via :class:`~akms_learn.warnings.WarningAccumulator` and returned from
:func:`validate_packet`. Examples: an empty ``body.nodes`` or ``body.edges``
list. ``DomainPackWarning`` is an independent type — the accumulator
pattern here is for ``LearningWarning`` specifically; the domain-pack
layer defines its own equivalent accumulator.
"""

from __future__ import annotations

from akms_learn.models import LearningSourcePacket, LearningWarning
from akms_learn.warnings import WarningAccumulator

__all__ = ["PacketValidationError", "validate_packet"]


class PacketValidationError(Exception):
    """Raised when a :class:`LearningSourcePacket` violates a hard invariant.

    Carries one or more textual ``issues`` describing the missing field(s) or
    dangling reference(s). The string form joins issues with ``"; "`` so error
    messages stay informative when surfaced through a single ``str(exc)``.
    """

    def __init__(self, issues: list[str]) -> None:
        self.issues: list[str] = list(issues)
        super().__init__("; ".join(self.issues))


def validate_packet(packet: LearningSourcePacket) -> list[LearningWarning]:
    """Validate cross-field invariants on a compiled LSP.

    Returns the list of accumulated soft warnings (possibly empty) on success.
    Raises :class:`PacketValidationError` if any hard invariant is violated.

    Hard checks run first and short-circuit on failure (a packet that lacks a
    ``request_hash`` is not meaningful to soft-check).
    """
    issues: list[str] = []

    # --- Hard check 1: request_hash is present and non-empty.
    request_hash = (packet.request.request_hash or "").strip()
    if not request_hash:
        issues.append("request.request_hash is missing or empty")

    # --- Hard check 2: source.graph_hash is present and non-empty.
    graph_hash = (packet.source.graph_hash or "").strip()
    if not graph_hash:
        issues.append("source.graph_hash is missing or empty")

    # --- Hard check 3: every edge endpoint resolves to a node in the packet.
    known_node_ids = {n.node_id for n in packet.body.nodes}
    for edge in packet.body.edges:
        if edge.from_node not in known_node_ids:
            issues.append(
                f"edge {edge.edge_id!r} 'from' references unknown "
                f"node_id {edge.from_node!r}"
            )
        if edge.to_node not in known_node_ids:
            issues.append(
                f"edge {edge.edge_id!r} 'to' references unknown "
                f"node_id {edge.to_node!r}"
            )

    if issues:
        raise PacketValidationError(issues)

    # --- Soft checks: empty bodies are valid but worth flagging.
    acc = WarningAccumulator()
    if not packet.body.nodes:
        acc.append(
            LearningWarning(
                severity="warning",
                code="empty_nodes",
                message="packet.body.nodes is empty",
                source_ref="body.nodes",
            )
        )
    if not packet.body.edges:
        acc.append(
            LearningWarning(
                severity="info",
                code="empty_edges",
                message="packet.body.edges is empty",
                source_ref="body.edges",
            )
        )

    return acc.finalize()
