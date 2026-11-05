"""Best-effort relationship graph generation."""

from __future__ import annotations

import enum
import json
from pathlib import Path

from akms.repo_wiki.models import ParsedModule, Symbol
from akms.repo_wiki.paths import ensure_parent

_GRAPH_SCHEMA_COMMENT = (
    "symbol_graph v1; edge fields: source, target, type, "
    "resolution (CONFIDENT|HEURISTIC|UNRESOLVED), dst_id (str|null), dst_name (str), "
    "dst_candidates (list[str], HEURISTIC only), "
    "provenance (static|observed|inferred, optional: absent means static); "
    "module node fields (optional, Python only): bindings ({local name: dotted import "
    "target}), dispatch ({dict name: [value names]}); symbol node fields (optional, "
    "Python only): receivers ({local name: [constructor or annotation names]}), "
    "table_refs ([module-level names indexed]), cli_handlers ([names passed as "
    "set_defaults(func=...)]); decorators ([decorator names, arguments dropped]); "
    "module node field (optional): main_calls ([call names run as a script])"
)

#: Where an edge comes from. ``static``: read from source text (every edge written today).
#: ``observed``: seen at run time. ``inferred``: derived from a pattern (a typed local
#: receiver, a dispatch table) rather than a direct call. Only non-static values are
#: written, so graphs without the field stay byte-identical and v1 readers are unaffected.
STATIC = "static"
OBSERVED = "observed"
INFERRED = "inferred"
PROVENANCES = (STATIC, OBSERVED, INFERRED)


class Resolution(enum.Enum):
    """Per-edge resolution: CONFIDENT (one match), HEURISTIC (several), UNRESOLVED (none)."""

    CONFIDENT = "CONFIDENT"
    HEURISTIC = "HEURISTIC"
    UNRESOLVED = "UNRESOLVED"


def _make_edge(
    source: str,
    target: str,
    edge_type: str,
    *,
    dst_name: str,
    dst_id: str | None,
    resolution: Resolution,
    dst_candidates: list[str] | None = None,
    provenance: str = STATIC,
) -> dict[str, object]:
    """Return an edge dict.

    ``dst_candidates`` is attached only for HEURISTIC edges and ``provenance`` only when it
    is not ``static``.
    """
    edge: dict[str, object] = {
        "dst_id": dst_id,
        "dst_name": dst_name,
        "resolution": resolution.value,
        "source": source,
        "target": target,
        "type": edge_type,
    }
    if dst_candidates is not None:
        edge["dst_candidates"] = dst_candidates
    if provenance != STATIC:
        if provenance not in PROVENANCES:
            raise ValueError(f"unknown edge provenance {provenance!r}")
        edge["provenance"] = provenance
    return edge


def edge_provenance(edge: dict[str, object]) -> str:
    """The provenance of an on-disk edge; absent or unknown values read as ``static``."""
    value = edge.get("provenance", STATIC)
    return value if isinstance(value, str) and value in PROVENANCES else STATIC


def _resolve_from_multimap(
    known: dict[str, list[str]], name: str
) -> tuple[str | None, Resolution, list[str] | None]:
    """Return ``(dst_id, resolution, dst_candidates)``; HEURISTIC picks the sorted-first ID."""
    candidates = known.get(name)
    if not candidates:
        return None, Resolution.UNRESOLVED, None
    if len(candidates) == 1:
        return candidates[0], Resolution.CONFIDENT, None
    return candidates[0], Resolution.HEURISTIC, list(candidates)


def _resolve_edge(
    known: dict[str, list[str]],
    source: str,
    dst_name: str,
    edge_type: str,
) -> dict[str, object]:
    """Build one name-resolved (``inherits``/``calls``) edge; target is the ID, else the name."""
    dst_id, resolution, dst_candidates = _resolve_from_multimap(known, dst_name)
    return _make_edge(
        source,
        dst_id if dst_id is not None else dst_name,
        edge_type,
        dst_name=dst_name,
        dst_id=dst_id,
        resolution=resolution,
        dst_candidates=dst_candidates,
    )


def build_symbol_graph(parsed_modules: list[ParsedModule]) -> dict[str, object]:
    nodes: dict[str, dict[str, object]] = {}
    edges: list[dict[str, object]] = []
    known: dict[str, list[str]] = {}
    seen: dict[str, set[str]] = {}
    for parsed in parsed_modules:
        module_id = parsed.module
        nodes[module_id] = {
            "kind": "module",
            "path": parsed.source_file.path,
            "start_line": 1,
            "end_line": 1,
        }
        if parsed.import_bindings:
            nodes[module_id]["bindings"] = dict(parsed.import_bindings)
        if parsed.dispatch_tables:
            nodes[module_id]["dispatch"] = {
                k: list(v) for k, v in sorted(parsed.dispatch_tables.items())
            }
        if parsed.main_calls:
            nodes[module_id]["main_calls"] = list(parsed.main_calls)
        # Module-level `imports` edges: once per module (all symbols share the import list).
        for imported in parsed.imports:
            edges.append(
                _make_edge(
                    module_id,
                    imported,
                    "imports",
                    dst_name=imported,
                    dst_id=None,
                    resolution=Resolution.UNRESOLVED,
                )
            )
        for symbol in parsed.symbols:
            nodes[symbol.symbol_id] = node_for_symbol(symbol)
            for key in (symbol.name, symbol.qualname):
                bucket = known.setdefault(key, [])
                bucket_seen = seen.setdefault(key, set())
                if symbol.symbol_id not in bucket_seen:
                    bucket.append(symbol.symbol_id)
                    bucket_seen.add(symbol.symbol_id)
            edges.append(
                _make_edge(
                    symbol.symbol_id,
                    module_id,
                    "defined_in",
                    dst_name=module_id,
                    dst_id=module_id,
                    resolution=Resolution.CONFIDENT,
                )
            )
            if symbol.parent_id:
                edges.append(
                    _make_edge(
                        symbol.symbol_id,
                        symbol.parent_id,
                        "belongs_to",
                        dst_name=symbol.parent_id,
                        dst_id=symbol.parent_id,
                        resolution=Resolution.CONFIDENT,
                    )
                )
    for bucket in known.values():
        bucket.sort()
    for parsed in parsed_modules:
        for symbol in parsed.symbols:
            for base in symbol.bases:
                edges.append(_resolve_edge(known, symbol.symbol_id, base, "inherits"))
            for call in symbol.calls:
                edges.append(_resolve_edge(known, symbol.symbol_id, call, "calls"))
    return {
        "_comment": _GRAPH_SCHEMA_COMMENT,
        "nodes": dict(sorted(nodes.items())),
        "edges": sorted(edges, key=lambda e: (e["source"], e["type"], e["target"])),
    }


def node_for_symbol(symbol: Symbol) -> dict[str, object]:
    """Graph node of one symbol; optional fields are written only when non-empty."""
    node: dict[str, object] = {
        "kind": symbol.kind,
        "path": symbol.path,
        "start_line": symbol.start_line,
        "end_line": symbol.end_line,
    }
    if symbol.receivers:
        node["receivers"] = {k: list(v) for k, v in sorted(symbol.receivers.items())}
    if symbol.table_refs:
        node["table_refs"] = list(symbol.table_refs)
    if symbol.cli_handlers:
        node["cli_handlers"] = list(symbol.cli_handlers)
    decorators = decorator_names(symbol.decorators)
    if decorators:
        node["decorators"] = decorators
    return node


def decorator_names(decorators: list[str]) -> list[str]:
    """``@app.command("x")`` -> ``app.command``: the decorator's dotted name, in order."""
    names: list[str] = []
    for text in decorators:
        name = text.lstrip("@").split("(", 1)[0].strip()
        if name and name not in names:
            names.append(name)
    return names


def write_symbol_graph(graph: dict[str, object], path: Path) -> Path:
    ensure_parent(path)
    path.write_text(
        json.dumps(graph, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path
