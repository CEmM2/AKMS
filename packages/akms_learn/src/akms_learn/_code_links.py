"""Shared helpers for code-link extraction.

Promoted from ``compiler.py`` and ``modes/implementation_first.py`` to
remove duplication. Lives at the package
top level so both the compiler stage and the ``implementation_first`` mode
can call into the same authoritative implementation.

Surface
-------
* :data:`MISSING_SOURCE_PATH_SENTINELS` — frozenset of placeholder strings
  that count as "no usable source path" (``"", "unknown", "none", "null"``).
* :func:`is_missing_source_path` — predicate over a raw ``source_path``
  value; case-insensitive, whitespace-tolerant, None-safe.
* :func:`coerce_line_range` — best-effort coercion of a node/edge
  ``line_range`` value into a ``(start, end)`` integer tuple.
* :func:`build_code_links` — walks ``implements`` edges and emits one
  :class:`CodeLinkView` per edge. Optionally invokes a missing-source
  callback so the compiler can emit ``code_mirror_missing_source_path``
  warnings while the mode keeps its own simpler warning path.

Callers
-------
* ``compiler._build_code_links`` thin-wraps :func:`build_code_links`
  passing the WarningAccumulator-driven callback.
* ``implementation_first._build_code_references`` uses the no-callback
  form; it emits ``implementation_anchor_missing_source`` separately
  via :func:`implementation_first._emit_anchor_missing_source_warnings`.

The module has no LLM imports.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from akms_learn.models import CodeLinkView

__all__ = [
    "MISSING_SOURCE_PATH_SENTINELS",
    "is_missing_source_path",
    "coerce_line_range",
    "build_code_links",
]


MISSING_SOURCE_PATH_SENTINELS: frozenset[str] = frozenset(
    {"", "unknown", "none", "null"}
)


def is_missing_source_path(value: Any) -> bool:
    """Return True if *value* is an unusable placeholder source path.

    Treats ``None``, empty string, and the canonical sentinels
    (``"unknown"`` / ``"none"`` / ``"null"``) as missing. Comparison is
    case-insensitive after stripping whitespace.
    """
    if value is None:
        return True
    text = str(value).strip().lower()
    return text in MISSING_SOURCE_PATH_SENTINELS


def coerce_line_range(value: Any) -> tuple[int, int]:
    """Best-effort coercion of a node/edge ``line_range`` to ``(start, end)``.

    Returns ``(0, 0)`` for any malformed input (non-list, wrong length,
    non-integer elements). The placeholder pair is recognised by callers
    that want to skip uninformative line ranges.
    """
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return (int(value[0]), int(value[1]))
        except (TypeError, ValueError):
            pass
    return (0, 0)


def build_code_links(
    edges: tuple[dict[str, Any], ...] | list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
    on_missing_mirror_source: Optional[Callable[[str, str], None]] = None,
) -> list[CodeLinkView]:
    """Walk ``implements`` edges and emit one :class:`CodeLinkView` per edge.

    Behaviour:

    * One :class:`CodeLinkView` per edge with ``type == "implements"``.
    * ``source_node_id`` is the edge's ``from`` endpoint.
    * ``target`` resolves to the target node id (always set when present).
    * ``relation`` is fixed to ``"implements"``.
    * ``file_path`` and ``line_range`` come from the target node when the
      target has a usable ``source_path``; otherwise the fields stay
      ``None``.
    * When *on_missing_mirror_source* is supplied AND the target node is a
      ``code_mirror`` with a missing/sentinel ``source_path``, the callback
      is invoked once per such edge with ``(mirror_node_id, edge_id)``.
      The mode-level caller (``implementation_first``) passes ``None`` so
      it can emit its own ``implementation_anchor_missing_source`` warning
      via a separate code path.

    The collector is order-stable: edges are processed in the order they
    arrive in (assumed already sorted by the caller) and the returned list
    preserves that order.
    """
    code_links: list[CodeLinkView] = []
    for edge in edges:
        if edge.get("type") != "implements":
            continue

        source_id = str(edge.get("from") or "")
        target_id = str(edge.get("to") or "")
        edge_id = str(edge.get("edge_id") or "")

        target_node = nodes_by_id.get(target_id) or {}
        target_source_path = target_node.get("source_path")
        line_range_raw = target_node.get("line_range")

        usable_path: Optional[str] = (
            None
            if is_missing_source_path(target_source_path)
            else str(target_source_path)
        )
        usable_line_range: Optional[tuple[int, int]] = None
        if usable_path is not None and line_range_raw is not None:
            coerced = coerce_line_range(line_range_raw)
            if coerced != (0, 0):
                usable_line_range = coerced

        target_value = target_id or (usable_path or "")

        code_links.append(
            CodeLinkView(
                node_id=source_id or target_id or edge_id,
                source_file=usable_path or "unknown",
                source_node_id=source_id or None,
                target=target_value or None,
                relation="implements",
                file_path=usable_path,
                line_range=usable_line_range,
                mirror_node_id=(
                    target_id if target_node.get("kind") == "code_mirror" else None
                ),
            )
        )

        if (
            on_missing_mirror_source is not None
            and target_node.get("kind") == "code_mirror"
            and is_missing_source_path(target_source_path)
        ):
            on_missing_mirror_source(target_id, edge_id)

    return code_links
