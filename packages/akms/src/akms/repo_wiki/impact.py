"""Symbol lookup, 360-degree context, depth-grouped impact and the risk rule.

Every dependency carries the resolution of the edge that produced it. CONFIDENT edges are
counted; HEURISTIC edges are reported separately as *possible* and never feed the risk level
(``risk_with_possible`` says what the level would be if they were all real).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from akms.repo_wiki.code_graph import (
    CONFIDENT,
    HEURISTIC,
    CodeGraph,
    Edge,
    Node,
    is_test_path,
)
from akms.repo_wiki.errors import RepoWikiError

CONTEXT_SCHEMA = "repo-wiki/context/v1"
IMPACT_SCHEMA = "repo-wiki/impact/v1"

DEFAULT_DEPTH = 3

#: Upstream depth labels; anything deeper than 3 reads as depth 3.
UPSTREAM_LABELS = {1: "will break", 2: "likely affected", 3: "may need testing"}
DOWNSTREAM_LABELS = {
    1: "direct dependency",
    2: "indirect dependency",
    3: "transitive dependency",
}

RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

#: The risk rule, in one table. A level applies when EITHER count reaches its minimum:
#: ``d1`` = confident non-test direct dependents, ``modules`` = distinct modules (other
#: than the target's own) among all confident non-test dependents up to the requested depth.
#: Checked top-down; below the last row the level is LOW. Reaching a public entry point
#: (a CLI module, or a package ``__init__`` export, including the target itself) raises the
#: level by one step, but never above ``PUBLIC_ENTRY_CAP``: only counts make CRITICAL.
RISK_THRESHOLDS: tuple[tuple[str, int, int], ...] = (
    # level,      min d1, min modules
    ("CRITICAL", 25, 12),
    ("HIGH", 10, 6),
    ("MEDIUM", 3, 3),
)

PUBLIC_ENTRY_CAP = "HIGH"

#: Edge types walked by ``impact`` for symbols; modules walk ``imports``.
SYMBOL_EDGE_TYPES = frozenset({"calls", "inherits"})
MODULE_EDGE_TYPES = frozenset({"imports"})


class SymbolLookupError(RepoWikiError):
    """The requested symbol is unknown or ambiguous; ``candidates`` lists the matches."""

    def __init__(
        self, code: str, message: str, candidates: list[dict[str, object]]
    ) -> None:
        super().__init__(message)
        self.code = code
        self.candidates = candidates


def node_summary(graph: CodeGraph, node: Node) -> dict[str, object]:
    """Stable, compact description of one node."""
    return {
        "id": node.id,
        "kind": node.kind,
        "name": node.name if not node.is_module else node.id,
        "qualname": node.qualname,
        "path": node.path,
        "start_line": node.start_line,
        "end_line": node.end_line,
        "module": node.module_id,
        "is_test": is_test_path(node.path),
        "public_entry": graph.public_entry_kind(node.id),
    }


# --------------------------------------------------------------- symbol lookup


def resolve_symbol(graph: CodeGraph, query: str) -> str:
    """Resolve *query* to exactly one node ID, or raise ``SymbolLookupError``.

    Tried in order, stopping at the first step with any match: exact node ID; ``path::qualname``
    without the language prefix; a dotted import path (``pkg.mod.Class.method`` or a module);
    an exact qualname (``Class.method``); a bare name; a dotted suffix of
    ``<module>.<qualname>``. More than one match at a step is ambiguous: nothing is guessed.
    """
    query = query.strip()
    if not query:
        raise SymbolLookupError("unknown_symbol", "empty symbol name", [])
    nodes = graph.nodes
    if query in nodes:
        return query
    steps: list[list[str]] = []
    if "::" in query:
        steps.append(sorted(i for i in nodes if i.split(":", 1)[-1] == query))
    dotted = graph.resolve_dotted(query) if "." in query else None
    steps.append([dotted] if dotted and dotted in nodes else [])
    steps.append(
        sorted(i for i in graph.find_by_name(query) if nodes[i].qualname == query)
    )
    steps.append(sorted(i for i in graph.find_by_name(query) if nodes[i].name == query))
    if "." in query:
        suffix = "." + query
        steps.append(
            sorted(
                i
                for i, n in nodes.items()
                if not n.is_module and f"{n.module_id}.{n.qualname}".endswith(suffix)
            )
            or sorted(i for i, n in nodes.items() if n.is_module and i.endswith(suffix))
        )
    for matches in steps:
        if len(matches) == 1:
            return matches[0]
        if matches:
            candidates = [node_summary(graph, nodes[m]) for m in matches]
            raise SymbolLookupError(
                "ambiguous_symbol",
                f"{query!r} matches {len(matches)} symbols; pass one of the IDs listed",
                candidates,
            )
    raise SymbolLookupError(
        "unknown_symbol",
        f"no symbol or module named {query!r} in the graph "
        "(rebuild if it was added since the last build)",
        [],
    )


# --------------------------------------------------------------------- context


def _link(graph: CodeGraph, node_id: str, edge: Edge) -> dict[str, object]:
    node = graph.nodes[node_id]
    return {**node_summary(graph, node), "edge": edge.to_dict()}


def _counts(edges: list[Edge]) -> dict[str, int]:
    return {
        CONFIDENT: sum(1 for e in edges if e.resolution == CONFIDENT),
        HEURISTIC: sum(1 for e in edges if e.resolution == HEURISTIC),
    }


def _split(graph: CodeGraph, edges: list[Edge], *, incoming: bool) -> dict[str, list]:
    confident = [
        _link(graph, e.source if incoming else e.target, e)
        for e in edges
        if e.resolution == CONFIDENT
    ]
    possible = [
        _link(graph, e.source if incoming else e.target, e)
        for e in edges
        if e.resolution == HEURISTIC
    ]
    return {"confident": confident, "possible": possible}


def build_context(
    graph: CodeGraph,
    node_id: str,
    *,
    details: dict[str, str | None] | None = None,
) -> dict[str, object]:
    """Definition, callers, callees, members, inheritance and module imports of one node."""
    node = graph.nodes[node_id]
    details = details or {}
    incoming = graph.in_edges.get(node_id, [])
    outgoing = graph.out_edges.get(node_id, [])
    module_id = node.module_id
    module_out = [e for e in graph.out_edges.get(module_id, []) if e.type == "imports"]
    module_in = [e for e in graph.in_edges.get(module_id, []) if e.type == "imports"]
    unresolved = graph.unresolved.get(node_id, [])
    definition = {
        **node_summary(graph, node),
        "signature": details.get("signature"),
        "docstring": details.get("docstring"),
        "dotted_name": graph.dotted_name(node_id),
        "parent": node.parent_id,
    }
    calls_in = [e for e in incoming if e.type == "calls"]
    calls_out = [e for e in outgoing if e.type == "calls"]
    return {
        "schema": CONTEXT_SCHEMA,
        "symbol": definition,
        "callers": _split(graph, calls_in, incoming=True),
        "callees": _split(graph, calls_out, incoming=False),
        "unresolved_calls": sorted({u.name for u in unresolved if not u.external}),
        "external_calls": sorted({u.name for u in unresolved if u.external}),
        "bases": _split(
            graph, [e for e in outgoing if e.type == "inherits"], incoming=False
        ),
        "subclasses": _split(
            graph, [e for e in incoming if e.type == "inherits"], incoming=True
        ),
        "members": sorted(graph.children.get(node_id, [])),
        "module": {
            "id": module_id,
            "path": graph.nodes[module_id].path
            if module_id in graph.nodes
            else node.path,
            "imports": sorted({e.target for e in module_out}),
            "external_imports": sorted(set(graph.external_imports.get(module_id, []))),
            "importers": sorted({e.source for e in module_in}),
        },
        "resolution_counts": {
            "callers": _counts(calls_in),
            "callees": {
                **_counts(calls_out),
                "UNRESOLVED": sum(1 for u in unresolved if not u.external),
                "EXTERNAL": sum(1 for u in unresolved if u.external),
            },
        },
    }


# ---------------------------------------------------------------------- impact


@dataclass(slots=True)
class Hit:
    node_id: str
    depth: int
    via: str
    edge: Edge


@dataclass(slots=True)
class Traversal:
    confident: dict[str, Hit] = field(default_factory=dict)
    possible: dict[str, Hit] = field(default_factory=dict)


def _bfs(
    graph: CodeGraph,
    seed: str,
    *,
    upstream: bool,
    depth: int,
    include_tests: bool,
    confident_only: bool,
) -> dict[str, Hit]:
    edge_types = MODULE_EDGE_TYPES if graph.nodes[seed].is_module else SYMBOL_EDGE_TYPES
    adjacency = graph.in_edges if upstream else graph.out_edges
    hits: dict[str, Hit] = {}
    queue: deque[tuple[str, int]] = deque([(seed, 0)])
    while queue:
        current, level = queue.popleft()
        if level >= depth:
            continue
        for edge in adjacency.get(current, []):
            if edge.type not in edge_types:
                continue
            if confident_only and edge.resolution != CONFIDENT:
                continue
            other = edge.source if upstream else edge.target
            if other == seed or other in hits or other not in graph.nodes:
                continue
            if not include_tests and is_test_path(graph.nodes[other].path):
                continue
            hits[other] = Hit(other, level + 1, current, edge)
            queue.append((other, level + 1))
    return hits


def traverse(
    graph: CodeGraph,
    seed: str,
    *,
    upstream: bool = True,
    depth: int = DEFAULT_DEPTH,
    include_tests: bool = True,
) -> Traversal:
    """Confident dependents (CONFIDENT edges only) and possible ones (needing a HEURISTIC edge)."""
    confident = _bfs(
        graph,
        seed,
        upstream=upstream,
        depth=depth,
        include_tests=include_tests,
        confident_only=True,
    )
    reachable = _bfs(
        graph,
        seed,
        upstream=upstream,
        depth=depth,
        include_tests=include_tests,
        confident_only=False,
    )
    possible = {k: v for k, v in reachable.items() if k not in confident}
    return Traversal(confident, possible)


def risk_level(d1: int, modules: int, public: bool) -> str:
    """Apply ``RISK_THRESHOLDS`` and the public-entry bump."""
    level = "LOW"
    for name, min_d1, min_modules in RISK_THRESHOLDS:
        if d1 >= min_d1 or modules >= min_modules:
            level = name
            break
    if public:
        index = RISK_LEVELS.index(level)
        cap = RISK_LEVELS.index(PUBLIC_ENTRY_CAP)
        level = RISK_LEVELS[max(index, min(index + 1, cap))]
    return level


@dataclass(slots=True)
class Risk:
    level: str
    d1: int
    modules_reached: int
    public_entry_points: list[str]
    reasons: list[str]


def assess_risk(graph: CodeGraph, targets: list[str], hits: list[Hit]) -> Risk:
    """Risk for *targets* given dependent *hits* (tests never count)."""
    counted = [h for h in hits if not is_test_path(graph.nodes[h.node_id].path)]
    own_modules = {graph.nodes[t].module_id for t in targets if t in graph.nodes}
    d1 = len({h.node_id for h in counted if h.depth == 1})
    modules = {graph.nodes[h.node_id].module_id for h in counted} - own_modules
    public = sorted(
        {
            node_id
            for node_id in [*targets, *(h.node_id for h in counted)]
            if node_id in graph.nodes and graph.public_entry_kind(node_id)
        }
    )
    reasons = [f"{d1} direct non-test dependent(s)", f"{len(modules)} other module(s)"]
    if public:
        reasons.append(f"public entry point(s) reached: {len(public)}")
    return Risk(
        risk_level(d1, len(modules), bool(public)), d1, len(modules), public, reasons
    )


def _hit_entry(graph: CodeGraph, hit: Hit) -> dict[str, object]:
    return {
        **node_summary(graph, graph.nodes[hit.node_id]),
        "depth": hit.depth,
        "via": hit.via,
        "edge": hit.edge.to_dict(),
    }


def _label(depth: int, upstream: bool) -> str:
    labels = UPSTREAM_LABELS if upstream else DOWNSTREAM_LABELS
    return labels[min(depth, max(labels))]


def build_impact(
    graph: CodeGraph,
    node_id: str,
    *,
    direction: str = "upstream",
    depth: int = DEFAULT_DEPTH,
    include_tests: bool = True,
) -> dict[str, object]:
    """Dependents (upstream) or dependencies (downstream) of one node, grouped by depth."""
    if depth < 1:
        raise ValueError(f"depth must be >= 1, got {depth}")
    upstream = direction == "upstream"
    result = traverse(
        graph, node_id, upstream=upstream, depth=depth, include_tests=include_tests
    )
    levels: list[dict[str, object]] = []
    for level in range(1, depth + 1):
        confident = sorted(
            (h for h in result.confident.values() if h.depth == level),
            key=lambda h: h.node_id,
        )
        possible = sorted(
            (h for h in result.possible.values() if h.depth == level),
            key=lambda h: h.node_id,
        )
        levels.append(
            {
                "depth": level,
                "label": _label(level, upstream),
                "confident": [_hit_entry(graph, h) for h in confident],
                "possible": [_hit_entry(graph, h) for h in possible],
            }
        )
    confident_paths = {graph.nodes[h].path for h in result.confident}
    possible_paths = {graph.nodes[h].path for h in result.possible} - confident_paths
    summary: dict[str, object] = {
        "confident": len(result.confident),
        "possible": len(result.possible),
    }
    if upstream:
        risk = assess_risk(graph, [node_id], list(result.confident.values()))
        with_possible = assess_risk(
            graph,
            [node_id],
            [*result.confident.values(), *result.possible.values()],
        )
        summary.update(
            {
                "risk": risk.level,
                "risk_with_possible": with_possible.level,
                "d1_confident": risk.d1,
                "modules_reached": risk.modules_reached,
                "public_entry_points": risk.public_entry_points,
                "risk_reasons": risk.reasons,
            }
        )
    else:
        summary.update({"risk": None, "risk_with_possible": None})
    return {
        "schema": IMPACT_SCHEMA,
        "target": node_summary(graph, graph.nodes[node_id]),
        "direction": direction,
        "depth": depth,
        "include_tests": include_tests,
        "levels": levels,
        "affected_files": sorted(p for p in confident_paths if not is_test_path(p)),
        "affected_test_files": sorted(p for p in confident_paths if is_test_path(p)),
        "possible_files": sorted(possible_paths),
        "summary": summary,
    }


def symbol_details(
    repo_root: Path, config: dict[str, object], node: Node
) -> dict[str, str | None]:
    """Signature and first docstring line, from parsing the defining file now."""
    from akms.repo_wiki.changes import extract_path

    parsed = extract_path(repo_root, node.path, config)
    if parsed is None:
        return {"signature": None, "docstring": None}
    if node.is_module:
        doc = parsed.docstring
        return {"signature": None, "docstring": _first_line(doc)}
    for symbol in parsed.symbols:
        if symbol.symbol_id == node.id:
            return {
                "signature": symbol.signature,
                "docstring": _first_line(symbol.docstring),
            }
    return {"signature": None, "docstring": None}


def _first_line(text: str | None) -> str | None:
    if not text:
        return None
    for line in text.strip().splitlines():
        if line.strip():
            return line.strip()
    return None
