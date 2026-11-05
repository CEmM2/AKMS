"""Static execution flows: entry points walked over the symbol graph's call links.

A *flow* starts at an entry point and follows ``calls`` links breadth-first, CONFIDENT links
only unless ``flows.include_heuristic`` is set. It is a pure function of the symbol graph,
the ``flows:`` configuration and the console scripts declared in ``pyproject.toml`` files:
no model, no network, nothing is run. Entry points, in priority order (one flow per entry):

==============  ===============================================================
kind            entry point
==============  ===============================================================
console_script  the target of a ``[project.scripts]`` (or ``gui-scripts``, or
                ``[tool.poetry.scripts]``) entry in any ``pyproject.toml``
script          a module's ``if __name__ == "__main__":`` block, or a
                ``__main__.py`` module (the flow starts at the module)
cli             a function decorated with a ``flows.cli_decorators`` pattern
                (``@app.command()``) or passed as ``set_defaults(func=...)``
root            a public function or method that nothing outside the tests
                calls with a CONFIDENT link, and that calls something itself
test            a test function (off by default: ``flows.entries.tests``)
==============  ===============================================================

Three caps bound a flow: ``max_depth`` (levels below the entry), ``max_fanout`` (callees
followed per step; the rest are omitted) and ``max_steps`` (steps per flow). A capped step
is marked with ``cut`` (``depth``, ``fanout`` or ``steps``) and the flow with
``truncated``. A link back to a step already on the path to the current one is a cycle: it
is recorded in ``cycles`` and not followed again.

``flows.json`` records the SHA-256 of the ``symbol_graph.json`` bytes it was derived from
and of its other inputs; readers recompute in memory when either differs.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from collections import deque
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath

from akms.repo_wiki.code_graph import (
    CONFIDENT,
    HEURISTIC,
    CodeGraph,
    Edge,
    graph_file,
    is_test_path,
)
from akms.repo_wiki.config import default_flows_config, deep_merge
from akms.repo_wiki.hashing import sha256_file
from akms.repo_wiki.paths import ensure_parent

FLOWS_FILE_SCHEMA = "repo-wiki/flows-file/v1"
FLOWS_FILENAME = "flows.json"

#: Entry kinds, highest priority first; a symbol that matches several rules gets the first.
ENTRY_KINDS = ("console_script", "script", "cli", "root", "test")
_KIND_ORDER = {kind: index for index, kind in enumerate(ENTRY_KINDS)}
#: ``flows.entries`` rule name -> entry kind.
RULE_KINDS = {
    "console_scripts": "console_script",
    "scripts": "script",
    "cli": "cli",
    "tests": "test",
    "roots": "root",
}
#: Settings that change what a flow contains (``enabled`` only gates writing on build).
_CONTENT_SETTINGS = (
    "cli_decorators",
    "entries",
    "include_heuristic",
    "max_depth",
    "max_fanout",
    "max_flows",
    "max_steps",
)

_COMMENT = (
    "repo-wiki/flows-file/v1; derived from symbol_graph.json (graph_sha256) and the "
    "flows settings plus console scripts (inputs_sha256); each flow: id, name, kind "
    "(console_script|script|cli|root|test), entry, steps [{id, depth, via, resolution, "
    "basis, provenance, cut?, omitted?, omitted_ids?}], terminals, cycles, truncated, "
    "truncated_reasons"
)


@dataclass(slots=True, frozen=True)
class ConsoleScript:
    """One console-script declaration: ``name = "pkg.mod:attr"`` in a ``pyproject.toml``."""

    name: str
    spec: str
    pyproject: str

    @property
    def dotted(self) -> str:
        module, _, attr = self.spec.partition(":")
        attr = attr.split("[", 1)[0].strip()  # drop "extras" markers
        return f"{module.strip()}.{attr}" if attr else module.strip()


@dataclass(slots=True)
class Entry:
    id: str
    kind: str
    name: str
    detail: str | None = None
    aliases: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FlowIndex:
    """Flows loaded from ``flows.json`` or computed in memory, with lookups."""

    payload: dict[str, object]
    source: str  # "file" or "computed"
    reason: str | None = None
    _by_symbol: dict[str, list[tuple[dict, dict]]] | None = field(default=None)

    @property
    def flows(self) -> list[dict]:
        flows = self.payload.get("flows")
        return flows if isinstance(flows, list) else []

    def info(self) -> dict[str, object]:
        """Where the flows came from (for the ``flows`` block of JSON output)."""
        return {
            "source": self.source,
            "reason": self.reason,
            "graph_sha256": self.payload.get("graph_sha256"),
            "settings": self.payload.get("settings"),
        }

    def touching(self, symbol_id: str) -> list[tuple[dict, dict]]:
        """``(flow, step)`` for every flow with a step on *symbol_id*, in flow order."""
        if self._by_symbol is None:
            index: dict[str, list[tuple[dict, dict]]] = {}
            for flow in self.flows:
                for step in flow.get("steps", []):
                    index.setdefault(str(step["id"]), []).append((flow, step))
            self._by_symbol = index
        return list(self._by_symbol.get(symbol_id, []))

    def find(self, query: str) -> list[dict]:
        """Flows whose ID, name or entry ID equals *query* (ID first, then name, then entry)."""
        for key in ("id", "name", "entry"):
            matches = [f for f in self.flows if f.get(key) == query]
            if matches:
                return matches
        return [f for f in self.flows if query in (f.get("aliases") or [])]


# ------------------------------------------------------------------- settings


def flows_settings(config: dict[str, object]) -> dict[str, object]:
    """The effective ``flows:`` section (defaults merged under the configured values)."""
    raw = config.get("flows")
    return deep_merge(default_flows_config(), raw if isinstance(raw, dict) else {})


def flows_file(repo_root: Path, config: dict[str, object]) -> Path:
    """``flows.json`` sits next to ``symbol_graph.json`` (``generation.output_dir``)."""
    return graph_file(repo_root, config).with_name(FLOWS_FILENAME)


def _content_settings(settings: dict[str, object]) -> dict[str, object]:
    return {key: settings[key] for key in _CONTENT_SETTINGS if key in settings}


# --------------------------------------------------------------- console scripts


def read_console_scripts(repo_root: Path, paths: list[str]) -> list[ConsoleScript]:
    """Console scripts from every ``pyproject.toml`` in a directory holding *paths*."""
    directories: set[str] = {"."}
    for path in paths:
        parent = PurePosixPath(path).parent
        while str(parent) not in directories:
            directories.add(str(parent))
            parent = parent.parent
    scripts: list[ConsoleScript] = []
    for directory in sorted(directories):
        rel = "pyproject.toml" if directory == "." else f"{directory}/pyproject.toml"
        file = repo_root / rel
        if not file.is_file():
            continue
        try:
            data = tomllib.loads(file.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            continue
        project = _table(data, "project")
        poetry = _table(_table(data, "tool"), "poetry")
        tables = [
            project.get("scripts"),
            project.get("gui-scripts"),
            poetry.get("scripts"),
        ]
        for table in tables:
            if not isinstance(table, dict):
                continue
            for name, spec in sorted(table.items()):
                if isinstance(spec, str) and ":" in spec:
                    scripts.append(ConsoleScript(str(name), spec, rel))
    return sorted(set(scripts), key=lambda s: (s.name, s.spec, s.pyproject))


def _table(data: dict[str, object], key: str) -> dict[str, object]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def inputs_sha256(settings: dict[str, object], scripts: list[ConsoleScript]) -> str:
    """Hash of everything besides the graph that a flow depends on."""
    blob = json.dumps(
        {
            "settings": _content_settings(settings),
            "console_scripts": [[s.pyproject, s.name, s.spec] for s in scripts],
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ------------------------------------------------------------- entry detection


def _public(qualname: str) -> bool:
    return bool(qualname) and not any(p.startswith("_") for p in qualname.split("."))


def _is_test_function(graph: CodeGraph, node_id: str) -> bool:
    node = graph.nodes[node_id]
    if node.kind not in ("function", "method") or not is_test_path(node.path):
        return False
    if not node.name.startswith("test"):
        return False
    if node.parent_id is None:
        return True
    parent = graph.nodes.get(node.parent_id)
    return (
        parent is not None
        and parent.kind == "class"
        and parent.name.startswith("Test")
        and parent.parent_id is None
    )


def _flow_name(graph: CodeGraph, node_id: str) -> str:
    return graph.dotted_name(node_id) or node_id


def detect_entries(
    graph: CodeGraph, settings: dict[str, object], scripts: list[ConsoleScript]
) -> list[Entry]:
    """Every entry point the enabled rules find, one per symbol, sorted by kind and name."""
    rules = settings.get("entries")
    rules = rules if isinstance(rules, dict) else {}
    include_heuristic = bool(settings.get("include_heuristic"))
    found: dict[str, Entry] = {}

    def offer(entry: Entry) -> None:
        current = found.get(entry.id)
        if current is None or _KIND_ORDER[entry.kind] < _KIND_ORDER[current.kind]:
            found[entry.id] = entry
        elif (
            current.kind == entry.kind == "console_script"
            and entry.name != current.name
            and entry.name not in current.aliases
        ):
            current.aliases.append(entry.name)  # two scripts, one target

    def symbol(node_id: str | None) -> bool:
        return (
            node_id is not None
            and node_id in graph.nodes
            and not graph.nodes[node_id].is_module
        )

    if rules.get("console_scripts"):
        for script in scripts:
            target = graph.resolve_dotted(script.dotted)
            if target is not None and symbol(target):
                offer(Entry(target, "console_script", script.name, script.spec))
    if rules.get("scripts"):
        for module_id in sorted(graph.main_calls):
            if module_id in graph.nodes:
                name = f"{graph.dotted_name(module_id) or module_id}:__main__"
                offer(Entry(module_id, "script", name, "__main__"))
    if rules.get("cli"):
        raw_patterns = settings.get("cli_decorators")
        patterns = (
            [str(p) for p in raw_patterns] if isinstance(raw_patterns, list) else []
        )
        for node_id, names in sorted(graph.decorators.items()):
            if not symbol(node_id):
                continue
            matched = next(
                (n for n in names if any(fnmatchcase(n, p) for p in patterns)), None
            )
            if matched:
                offer(Entry(node_id, "cli", _flow_name(graph, node_id), f"@{matched}"))
        for node_id, handlers in sorted(graph.cli_handlers.items()):
            for handler in handlers:
                for edge in graph.resolve_reference(node_id, handler):
                    if edge.resolution == CONFIDENT and symbol(edge.target):
                        offer(
                            Entry(
                                edge.target,
                                "cli",
                                _flow_name(graph, edge.target),
                                f"set_defaults(func={handler})",
                            )
                        )
    if rules.get("tests"):
        for node_id in sorted(graph.nodes):
            if _is_test_function(graph, node_id):
                offer(Entry(node_id, "test", _flow_name(graph, node_id)))
    if rules.get("roots"):
        for node_id in sorted(graph.nodes):
            if node_id in found:
                continue
            node = graph.nodes[node_id]
            if node.kind not in ("function", "method") or is_test_path(node.path):
                continue
            if not _public(node.qualname):
                continue
            parent = graph.nodes.get(node.parent_id) if node.parent_id else None
            if parent is not None and parent.kind != "class":
                continue  # a nested function is reached through its enclosing one
            if any(
                e.type == "calls"
                and e.resolution == CONFIDENT
                and e.source in graph.nodes
                and not is_test_path(graph.nodes[e.source].path)
                for e in graph.in_edges.get(node_id, [])
            ):
                continue
            if not _callees(graph, node_id, include_heuristic):
                continue
            offer(Entry(node_id, "root", _flow_name(graph, node_id)))
    return sorted(found.values(), key=lambda e: (_KIND_ORDER[e.kind], e.name, e.id))


# ------------------------------------------------------------------ traversal


def _callees(graph: CodeGraph, node_id: str, include_heuristic: bool) -> list[Edge]:
    """Followable call links from *node_id*, CONFIDENT first, one per target."""
    node = graph.nodes.get(node_id)
    if node is None:
        return []
    if node.is_module:
        edges = [
            edge
            for name in graph.main_calls.get(node_id, [])
            for edge in graph.resolve_reference(node_id, name)
        ]
    else:
        edges = [e for e in graph.out_edges.get(node_id, []) if e.type == "calls"]
    allowed = (CONFIDENT, HEURISTIC) if include_heuristic else (CONFIDENT,)
    best: dict[str, Edge] = {}
    for edge in edges:
        target = graph.nodes.get(edge.target)
        if edge.resolution not in allowed or target is None or target.is_module:
            continue
        if edge.target == node_id:
            continue
        previous = best.get(edge.target)
        if previous is None or (
            previous.resolution != CONFIDENT and edge.resolution == CONFIDENT
        ):
            best[edge.target] = edge
    return sorted(best.values(), key=lambda e: (e.resolution != CONFIDENT, e.target))


def flow_id(entry_id: str) -> str:
    """Stable flow ID: derived from the entry's node ID only."""
    return "flow:" + hashlib.sha256(entry_id.encode("utf-8")).hexdigest()[:12]


def walk_flow(
    graph: CodeGraph, entry: Entry, settings: dict[str, object]
) -> dict[str, object]:
    """Breadth-first walk from *entry* under the depth, fan-out and step caps."""
    max_depth = int(settings["max_depth"])  # type: ignore[call-overload]
    max_fanout = int(settings["max_fanout"])  # type: ignore[call-overload]
    max_steps = int(settings["max_steps"])  # type: ignore[call-overload]
    include_heuristic = bool(settings.get("include_heuristic"))
    degrees: dict[str, int] = {}
    steps: list[dict[str, object]] = [{"id": entry.id, "depth": 0, "via": None}]
    index = {entry.id: 0}
    parent: dict[str, str | None] = {entry.id: None}
    queue: deque[str] = deque([entry.id])
    reasons: set[str] = set()
    cycles: list[list[str]] = []
    terminals: list[str] = []
    full = False
    while queue:
        current = queue.popleft()
        step = steps[index[current]]
        depth = int(step["depth"])  # type: ignore[call-overload]
        edges = _callees(graph, current, include_heuristic)
        if not edges:
            terminals.append(current)
            continue
        if full:
            continue
        if depth >= max_depth:
            omitted = sum(1 for e in edges if e.target not in index)
            if omitted:
                step["cut"], step["omitted"] = "depth", omitted
                reasons.add("depth")
            continue
        if len(edges) > max_fanout:
            kept, dropped = _pick_fanout(graph, edges, max_fanout, degrees)
            step["cut"], step["omitted"] = "fanout", len(dropped)
            step["omitted_ids"] = [e.target for e in dropped[:OMITTED_IDS_LIMIT]]
            reasons.add("fanout")
            edges = kept
        for position, edge in enumerate(edges):
            target = edge.target
            if target in index:
                if _on_path(target, current, parent):
                    cycles.append([current, target])
                continue
            if len(steps) >= max_steps:
                left = sum(1 for e in edges[position:] if e.target not in index)
                step["cut"] = "steps"
                step["omitted"] = int(step.get("omitted", 0) or 0) + left  # type: ignore[call-overload]
                reasons.add("steps")
                full = True
                break
            index[target] = len(steps)
            parent[target] = current
            steps.append(
                {
                    "id": target,
                    "depth": depth + 1,
                    "via": current,
                    "resolution": edge.resolution,
                    "basis": edge.basis,
                    "provenance": edge.provenance,
                }
            )
            queue.append(target)
    node = graph.nodes[entry.id]
    return {
        "id": flow_id(entry.id),
        "name": entry.name,
        "kind": entry.kind,
        "entry": entry.id,
        "detail": entry.detail,
        "aliases": sorted(entry.aliases),
        "path": node.path,
        "start_line": node.start_line,
        "end_line": node.end_line,
        "steps": steps,
        "depth": max(int(s["depth"]) for s in steps),  # type: ignore[call-overload]
        "terminals": sorted(terminals),
        "cycles": sorted(cycles),
        "truncated": bool(reasons),
        "truncated_reasons": sorted(reasons),
        "heuristic_steps": sum(1 for s in steps if s.get("resolution") == HEURISTIC),
        "inferred_steps": sum(1 for s in steps if s.get("provenance") == "inferred"),
    }


#: A fan-out cut lists at most this many of the callees it did not follow.
OMITTED_IDS_LIMIT = 25


def _pick_fanout(
    graph: CodeGraph, edges: list[Edge], limit: int, degrees: dict[str, int]
) -> tuple[list[Edge], list[Edge]]:
    """Keep *limit* callees: CONFIDENT first, then those that call the most themselves.

    A callee that calls nothing ends its branch, so when something must be dropped the
    leaves go first. Both lists come back in the usual (resolution, ID) order.
    """

    def degree(target: str) -> int:
        if target not in degrees:
            degrees[target] = sum(
                1
                for e in graph.out_edges.get(target, [])
                if e.type == "calls" and e.resolution == CONFIDENT
            )
        return degrees[target]

    ranked = sorted(
        edges, key=lambda e: (e.resolution != CONFIDENT, -degree(e.target), e.target)
    )
    keep = {e.target for e in ranked[:limit]}
    kept = [e for e in edges if e.target in keep]
    dropped = [e for e in edges if e.target not in keep]
    return kept, dropped


def _on_path(target: str, current: str, parent: dict[str, str | None]) -> bool:
    """True when *target* is *current* or one of its ancestors in the walk."""
    node: str | None = current
    while node is not None:
        if node == target:
            return True
        node = parent.get(node)
    return False


def compute_flows(
    graph: CodeGraph,
    settings: dict[str, object],
    scripts: list[ConsoleScript],
    *,
    graph_sha256: str | None,
) -> dict[str, object]:
    """The ``flows.json`` payload for a finalized *graph* (deterministic)."""
    graph.finalize()
    entries = detect_entries(graph, settings, scripts)
    flows = [walk_flow(graph, entry, settings) for entry in entries]
    max_flows = int(settings.get("max_flows", 1000))  # type: ignore[call-overload]
    omitted: dict[str, int] = {}
    if len(flows) > max_flows:
        # Keep flows in entry-kind priority order (opt-in tests go first, then roots),
        # the longest first within a kind; the rest are counted.
        ranked = sorted(
            flows,
            key=lambda f: (
                _KIND_ORDER[str(f["kind"])],
                -len(f["steps"]),  # type: ignore[arg-type]
                str(f["name"]),
            ),
        )
        kept = {str(f["id"]) for f in ranked[:max_flows]}
        for flow in ranked[max_flows:]:
            omitted[str(flow["kind"])] = omitted.get(str(flow["kind"]), 0) + 1
        flows = [f for f in flows if str(f["id"]) in kept]
    by_kind: dict[str, int] = {}
    for flow in flows:
        by_kind[str(flow["kind"])] = by_kind.get(str(flow["kind"]), 0) + 1
    return {
        "_comment": _COMMENT,
        "schema": FLOWS_FILE_SCHEMA,
        "graph_sha256": graph_sha256,
        "inputs_sha256": inputs_sha256(settings, scripts),
        "settings": _content_settings(settings),
        "summary": {
            "flows": len(flows),
            "by_kind": dict(sorted(by_kind.items())),
            "steps": sum(len(f["steps"]) for f in flows),  # type: ignore[arg-type]
            "truncated": sum(1 for f in flows if f["truncated"]),
            "omitted_flows": dict(sorted(omitted.items())),
        },
        "flows": flows,
    }


def dump_flows(payload: dict[str, object]) -> str:
    """Serialized ``flows.json``: sorted keys, one compact flow per line, final newline.

    One line per flow keeps the file small and its diffs readable; the result is plain
    JSON and byte-identical for the same input.
    """
    parts: list[str] = []
    for key in sorted(payload):
        value = payload[key]
        if key == "flows" and isinstance(value, list) and value:
            lines = [
                "    " + json.dumps(flow, sort_keys=True, separators=(",", ":"))
                for flow in value
            ]
            text = "[\n" + ",\n".join(lines) + "\n  ]"
        else:
            text = json.dumps(value, sort_keys=True, indent=2).replace("\n", "\n  ")
        parts.append(f"  {json.dumps(key)}: {text}")
    return "{\n" + ",\n".join(parts) + "\n}\n"


def write_flows(path: Path, payload: dict[str, object]) -> Path:
    ensure_parent(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(dump_flows(payload), encoding="utf-8")
    tmp.replace(path)
    return path


def build_flows(
    repo_root: Path,
    config: dict[str, object],
    graph_data: dict[str, object],
    graph_path: Path,
) -> Path | None:
    """Called by ``build`` right after it writes ``symbol_graph.json``."""
    settings = flows_settings(config)
    path = flows_file(repo_root, config)
    if not settings.get("enabled", True):
        path.unlink(missing_ok=True)  # a disabled build leaves no stale flows behind
        return None
    graph = CodeGraph.from_symbol_graph(graph_data).finalize()
    scripts = read_console_scripts(repo_root, graph.paths())
    payload = compute_flows(
        graph, settings, scripts, graph_sha256=sha256_file(graph_path)
    )
    return write_flows(path, payload)


# ------------------------------------------------------------------- reading


def load_flows(
    repo_root: Path,
    config: dict[str, object],
    graph: CodeGraph,
    graph_path: Path,
) -> FlowIndex:
    """``flows.json`` when it matches *graph_path* and the settings, else computed now.

    Nothing is written: a missing or stale file is recomputed in memory and the result
    says so (``source: computed`` with a ``reason``).
    """
    settings = flows_settings(config)
    scripts = read_console_scripts(repo_root, graph.paths())
    graph_sha = sha256_file(graph_path) if graph_path.is_file() else None
    inputs = inputs_sha256(settings, scripts)
    path = flows_file(repo_root, config)
    reason = "missing"
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload, reason = None, "unreadable"
        if isinstance(payload, dict) and payload.get("schema") == FLOWS_FILE_SCHEMA:
            if payload.get("graph_sha256") != graph_sha:
                reason = "graph changed since flows.json was written"
            elif payload.get("inputs_sha256") != inputs:
                reason = "flows settings or console scripts changed"
            else:
                return FlowIndex(payload, "file")
        elif payload is not None:
            reason = "unknown schema"
    computed = compute_flows(graph, settings, scripts, graph_sha256=graph_sha)
    return FlowIndex(computed, "computed", reason)


# ------------------------------------------------------------------ summaries


def flow_summary(flow: dict) -> dict[str, object]:
    """A flow without its steps (for lists)."""
    return {
        "id": flow["id"],
        "name": flow["name"],
        "kind": flow["kind"],
        "entry": flow["entry"],
        "detail": flow.get("detail"),
        "path": flow["path"],
        "start_line": flow["start_line"],
        "end_line": flow["end_line"],
        "steps": len(flow["steps"]),
        "depth": flow["depth"],
        "terminals": len(flow["terminals"]),
        "truncated": flow["truncated"],
        "truncated_reasons": flow["truncated_reasons"],
        "heuristic_steps": flow["heuristic_steps"],
        "inferred_steps": flow["inferred_steps"],
    }


def participation(
    index: FlowIndex,
    symbol_ids: list[str],
    *,
    limit: int | None = None,
    primary: str | None = None,
) -> dict[str, object]:
    """Flows with a step on any of *symbol_ids*: count, and the first *limit* of them.

    Ordered by the depth of *primary* in the flow when it is a step there (else the
    shallowest matched step), then entry kind and name.
    """
    hits: dict[str, tuple[dict, list[tuple[str, int]]]] = {}
    for symbol_id in symbol_ids:
        for flow, step in index.touching(symbol_id):
            entry = hits.setdefault(str(flow["id"]), (flow, []))
            entry[1].append((symbol_id, int(step["depth"])))

    def depth_key(matched: list[tuple[str, int]]) -> int:
        own = [depth for sid, depth in matched if sid == primary]
        return min(own) if own else min(depth for _, depth in matched)

    ordered = sorted(
        hits.values(),
        key=lambda item: (
            depth_key(item[1]),
            _KIND_ORDER.get(str(item[0]["kind"]), len(ENTRY_KINDS)),
            str(item[0]["name"]),
        ),
    )
    shown = ordered if limit is None else ordered[:limit]
    return {
        "count": len(ordered),
        "flows": [
            {
                **flow_summary(flow),
                "matched": [
                    {"id": sid, "depth": depth} for sid, depth in sorted(matched)
                ],
            }
            for flow, matched in shown
        ],
        "source": index.source,
        "reason": index.reason,
    }
