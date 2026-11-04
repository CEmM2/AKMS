"""``context``, ``impact``, ``changes``, ``flows`` and ``flow``: argument parsing and output.

Exit codes: 0 success, 1 git or I/O failure, 2 usage error, 3 symbol graph missing,
unreadable or stale, 4 symbol or flow unknown or ambiguous. With ``--json`` a failure
prints an ``repo-wiki/error/v1`` object on stdout as well as the message on stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from akms.repo_wiki.code_graph import (
    GraphUnavailableError,
    LoadedGraph,
    load_code_graph,
)
from akms.repo_wiki.config import load_config
from akms.repo_wiki.flows import (
    ENTRY_KINDS,
    FlowIndex,
    flow_summary,
    flows_settings,
    load_flows,
    participation,
)
from akms.repo_wiki.locking import LockError
from akms.repo_wiki.refresh import refresh_graph
from akms.repo_wiki.impact import (
    DEFAULT_DEPTH,
    SymbolLookupError,
    build_context,
    build_impact,
    resolve_symbol,
    symbol_details,
)

ERROR_SCHEMA = "repo-wiki/error/v1"
FLOWS_SCHEMA = "repo-wiki/flows/v1"
FLOW_SCHEMA = "repo-wiki/flow/v1"
EXIT_GIT = 1
EXIT_USAGE = 2
EXIT_GRAPH = 3
EXIT_SYMBOL = 4

INTEL_COMMANDS = ("context", "impact", "changes", "flows", "flow")

#: How many flows ``context``, ``impact`` and ``changes`` list (the count is always total).
CONTEXT_FLOWS = 5
REPORT_FLOWS = 10
DEFAULT_FLOWS_LIMIT = 50


class FlowLookupError(Exception):
    """The requested flow is unknown or ambiguous; ``candidates`` lists the matches."""

    def __init__(
        self, code: str, message: str, candidates: list[dict[str, object]]
    ) -> None:
        super().__init__(message)
        self.code = code
        self.candidates = candidates


def add_intel_parsers(sub: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    """Register the three code-intelligence subcommands."""
    stale_help = "Use a stale symbol graph instead of failing (results may be wrong)"
    context = sub.add_parser(
        "context",
        help="Definition, callers, callees and module imports of one symbol",
        description=(
            "Show where SYMBOL is defined, who calls it, what it calls, and what its "
            "module imports. SYMBOL is a node ID, path::qualname, dotted import path, "
            "qualname or bare name; an ambiguous name lists the candidates."
        ),
    )
    context.add_argument("symbol")
    context.add_argument("--json", action="store_true")
    context.add_argument("--allow-stale", action="store_true", help=stale_help)

    impact = sub.add_parser(
        "impact",
        help="Dependents (or dependencies) of one symbol, grouped by depth, with risk",
        description=(
            "Walk the symbol graph from SYMBOL. Upstream (default) lists who depends on "
            "it: d=1 will break, d=2 likely affected, d=3 may need testing. CONFIDENT "
            "links are counted; HEURISTIC links are listed separately as possible."
        ),
    )
    impact.add_argument("symbol")
    impact.add_argument(
        "--direction", choices=("upstream", "downstream"), default="upstream"
    )
    impact.add_argument(
        "--depth", type=int, default=DEFAULT_DEPTH, help="Levels to walk (default: 3)"
    )
    tests = impact.add_mutually_exclusive_group()
    tests.add_argument(
        "--include-tests",
        dest="include_tests",
        action="store_true",
        default=True,
        help="List test code among dependents (default; tests never raise the risk)",
    )
    tests.add_argument(
        "--exclude-tests",
        dest="include_tests",
        action="store_false",
        help="Leave test code out of the walk entirely",
    )
    impact.add_argument("--json", action="store_true")
    impact.add_argument("--allow-stale", action="store_true", help=stale_help)

    changes = sub.add_parser(
        "changes",
        help="Map a git diff to changed symbols and their direct callers",
        description=(
            "Map the git diff to the symbols whose line ranges it touches, and list "
            "each symbol's direct (d=1) callers. Default: the worktree, including "
            "untracked files, against HEAD."
        ),
    )
    mode = changes.add_mutually_exclusive_group()
    mode.add_argument(
        "--base",
        metavar="REF",
        help="Compare the worktree with the merge base of REF and HEAD",
    )
    mode.add_argument(
        "--staged", action="store_true", help="Compare the index with HEAD"
    )
    mode.add_argument(
        "--worktree",
        action="store_true",
        help="Compare the worktree (and untracked files) with HEAD (default)",
    )
    changes.add_argument("--json", action="store_true")
    changes.add_argument("--allow-stale", action="store_true", help=stale_help)
    changes.add_argument(
        "--refresh",
        action="store_true",
        help=(
            "Run the incremental build first (under the build lock), then report the "
            "flows of the graph both before and after it"
        ),
    )

    flows = sub.add_parser(
        "flows",
        help="List execution flows: entry points walked over confident call links",
        description=(
            "List the static execution flows derived from the symbol graph: console "
            "scripts, __main__ blocks, CLI commands and uncalled public functions, each "
            "walked breadth-first over CONFIDENT call links under depth, fan-out and step "
            "caps."
        ),
    )
    flows.add_argument(
        "--entry",
        metavar="TEXT",
        help="Only flows whose name or entry ID contains TEXT (* and ? are wildcards)",
    )
    flows.add_argument(
        "--kind", choices=ENTRY_KINDS, help="Only flows whose entry is of this kind"
    )
    flows.add_argument(
        "--touching",
        metavar="SYMBOL",
        help="Only flows with a step on SYMBOL (named as for context)",
    )
    flows.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_FLOWS_LIMIT,
        help=f"Show at most N flows (default: {DEFAULT_FLOWS_LIMIT}; 0 for all)",
    )
    flows.add_argument("--json", action="store_true")
    flows.add_argument("--allow-stale", action="store_true", help=stale_help)

    flow = sub.add_parser(
        "flow",
        help="Show the steps of one execution flow",
        description=(
            "Show one flow as a call tree. FLOW is a flow ID, a flow name, a console "
            "script name, or the entry symbol (named as for context)."
        ),
    )
    flow.add_argument("flow")
    flow.add_argument("--json", action="store_true")
    flow.add_argument("--allow-stale", action="store_true", help=stale_help)


def run_intel(args: argparse.Namespace, repo_root: Path) -> int:
    """Dispatch one code-intelligence subcommand."""
    from akms.repo_wiki.changes import GitError, detect_changes

    try:
        config = load_config(repo_root)
        if args.command == "changes":
            mode = "base" if args.base else ("staged" if args.staged else "worktree")
            before: FlowIndex | None = None
            refreshed: dict[str, object] | None = None
            if args.refresh:
                before = _stored_flows(repo_root, config)
                refreshed = refresh_graph(
                    repo_root,
                    on_wait=lambda who: print(
                        f"repo-wiki changes: waiting for a running build ({who})",
                        file=sys.stderr,
                    ),
                )
            used: list[LoadedGraph] = []
            payload = detect_changes(
                repo_root,
                config,
                mode=mode,
                base=args.base,
                allow_stale=args.allow_stale,
                loaded_out=used,
            )
            after = _attach_change_flows(repo_root, config, payload, used)
            if refreshed is not None:
                payload["refresh"] = refreshed
                if after is not None:
                    _attach_refreshed_flows(payload, before, after)
            _emit(payload, args.json, render_changes)
            return 0
        if args.command == "flows" and args.limit < 0:
            return _fail(
                args, EXIT_USAGE, "usage", f"--limit must be >= 0, got {args.limit}"
            )
        if args.command == "impact" and args.depth < 1:
            return _fail(
                args, EXIT_USAGE, "usage", f"--depth must be >= 1, got {args.depth}"
            )
        loaded = load_code_graph(repo_root, config=config, allow_stale=args.allow_stale)
        graph = loaded.graph
        if args.command in ("flows", "flow"):
            index = load_flows(repo_root, config, graph, loaded.path)
            if index.source == "computed":
                print(
                    f"repo-wiki {args.command}: flows.json {index.reason}; "
                    "flows were computed in memory (rebuild to refresh the file)",
                    file=sys.stderr,
                )
            if args.command == "flows":
                payload = list_flows(index, loaded, args)
                payload["graph"] = loaded.to_dict(repo_root)
                _emit(payload, args.json, render_flows)
                return 0
            payload = show_flow(index, loaded, args.flow)
            payload["graph"] = loaded.to_dict(repo_root)
            _emit(payload, args.json, render_flow)
            return 0
        node_id = resolve_symbol(graph, args.symbol)
        if args.command == "context":
            payload = build_context(
                graph,
                node_id,
                details=symbol_details(repo_root, config, graph.nodes[node_id]),
            )
            payload["graph"] = loaded.to_dict(repo_root)
            if _flows_enabled(config):
                index = load_flows(repo_root, config, graph, loaded.path)
                flows = participation(index, [node_id], limit=CONTEXT_FLOWS)
                flows["as_entry"] = next(
                    (f["id"] for f in index.flows if f["entry"] == node_id), None
                )
                payload["flows"] = flows
            _emit(payload, args.json, render_context)
            return 0
        payload = build_impact(
            graph,
            node_id,
            direction=args.direction,
            depth=args.depth,
            include_tests=args.include_tests,
        )
        payload["graph"] = loaded.to_dict(repo_root)
        if _flows_enabled(config):
            index = load_flows(repo_root, config, graph, loaded.path)
            reached = [
                str(item["id"])
                for level in payload["levels"]  # type: ignore[union-attr]
                for item in level["confident"]
            ]
            flows = participation(
                index, [node_id, *reached], limit=REPORT_FLOWS, primary=node_id
            )
            flows["through_target"] = len(index.touching(node_id))
            payload["flows"] = flows
        _emit(payload, args.json, render_impact)
        return 0
    except GraphUnavailableError as exc:
        return _fail(args, EXIT_GRAPH, exc.code, str(exc), details=exc.details)
    except SymbolLookupError as exc:
        return _fail(args, EXIT_SYMBOL, exc.code, str(exc), candidates=exc.candidates)
    except FlowLookupError as exc:
        return _fail(args, EXIT_SYMBOL, exc.code, str(exc), candidates=exc.candidates)
    except LockError as exc:
        return _fail(args, EXIT_GIT, "build_lock", str(exc))
    except GitError as exc:
        return _fail(args, EXIT_GIT, "git_error", str(exc))


def _flows_enabled(config: dict[str, object]) -> bool:
    return bool(flows_settings(config).get("enabled", True))


def _attach_change_flows(
    repo_root: Path,
    config: dict[str, object],
    payload: dict[str, object],
    used: list[LoadedGraph],
) -> FlowIndex | None:
    """Add the flows that contain a changed (or moved-away) symbol to a changes payload.

    The stored flows describe the graph before the change, which is what a diff touches.
    """
    if not _flows_enabled(config):
        return None
    loaded = (
        used[0]
        if used
        else load_code_graph(repo_root, config=config, allow_stale=True, finalize=False)
    )
    index = load_flows(repo_root, config, loaded.graph, loaded.path)
    flows = participation(index, _changed_ids(payload), limit=REPORT_FLOWS)
    payload["flows"] = flows
    summary = payload.get("summary")
    if isinstance(summary, dict):
        summary["flows_touched"] = flows["count"]
    return index


def _changed_ids(payload: dict[str, object]) -> list[str]:
    ids: set[str] = set()
    for item in payload.get("changed_symbols") or []:  # type: ignore[union-attr]
        ids.add(str(item["id"]))
        if item.get("old_id"):
            ids.add(str(item["old_id"]))
    return sorted(ids)


def _stored_flows(repo_root: Path, config: dict[str, object]) -> FlowIndex | None:
    """The flows of the stored graph as it is now, or None when there is no graph."""
    if not _flows_enabled(config):
        return None
    try:
        loaded = load_code_graph(
            repo_root, config=config, allow_stale=True, finalize=False
        )
    except GraphUnavailableError:
        return None
    return load_flows(repo_root, config, loaded.graph, loaded.path)


def _attach_refreshed_flows(
    payload: dict[str, object],
    before: FlowIndex | None,
    after: FlowIndex,
) -> None:
    """``flows_before`` / ``flows_after`` and the counts for ``changes --refresh``.

    ``flows`` (already attached) is read from the refreshed graph, so it equals
    ``flows_after``. ``summary.flows_touched`` counts the distinct flows that contain a
    changed symbol in either graph.
    """
    ids = _changed_ids(payload)
    payload["flows_after"] = payload.get("flows")
    payload["flows_before"] = (
        participation(before, ids, limit=REPORT_FLOWS) if before is not None else None
    )
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return
    after_set = _touched_ids(after, ids)
    before_set = _touched_ids(before, ids)
    summary["flows_touched"] = len(after_set | before_set)
    summary["flows_touched_before"] = len(before_set) if before is not None else None
    summary["flows_touched_after"] = len(after_set)
    summary["flows_only_before"] = len(before_set - after_set)
    summary["flows_only_after"] = len(after_set - before_set)


def _touched_ids(index: FlowIndex | None, ids: list[str]) -> set[str]:
    if index is None:
        return set()
    return {str(flow["id"]) for sid in ids for flow, _ in index.touching(sid)}


def _matches_entry(flow: dict, text: str) -> bool:
    from fnmatch import fnmatchcase

    names = [str(flow["name"]), str(flow["entry"]), *flow.get("aliases", [])]
    if any(ch in text for ch in "*?["):
        return any(fnmatchcase(name, text) for name in names)
    return any(text in name for name in names)


def list_flows(
    index: FlowIndex, loaded: LoadedGraph, args: argparse.Namespace
) -> dict[str, object]:
    """The ``flows`` payload: filtered flow summaries, newest filters recorded."""
    flows = index.flows
    depth_of: dict[str, int] = {}
    touching_id = None
    if args.touching:
        loaded.graph.finalize()
        touching_id = resolve_symbol(loaded.graph, args.touching)
        hits = index.touching(touching_id)
        depth_of = {str(flow["id"]): int(step["depth"]) for flow, step in hits}
        flows = [f for f in flows if f["id"] in depth_of]
    if args.kind:
        flows = [f for f in flows if f["kind"] == args.kind]
    if args.entry:
        flows = [f for f in flows if _matches_entry(f, args.entry)]
    by_kind: dict[str, int] = {}
    for flow in flows:
        by_kind[str(flow["kind"])] = by_kind.get(str(flow["kind"]), 0) + 1
    shown = flows if args.limit == 0 else flows[: args.limit]
    items = []
    for flow in shown:
        item = flow_summary(flow)
        if touching_id is not None:
            item["touching_depth"] = depth_of[str(flow["id"])]
        items.append(item)
    total = index.payload.get("summary")
    return {
        "schema": FLOWS_SCHEMA,
        "filters": {
            "entry": args.entry,
            "kind": args.kind,
            "touching": touching_id,
            "limit": args.limit,
        },
        "flows": items,
        "summary": {
            "total": len(index.flows),
            "matched": len(flows),
            "shown": len(items),
            "by_kind": dict(sorted(by_kind.items())),
            "omitted_flows": total.get("omitted_flows", {})
            if isinstance(total, dict)
            else {},
        },
        "settings": index.payload.get("settings"),
        "flows_source": {"source": index.source, "reason": index.reason},
    }


def find_flow(index: FlowIndex, loaded: LoadedGraph, query: str) -> dict:
    """One flow by ID, name, script alias or entry ID, else by the entry symbol's name."""
    matches = index.find(query)
    if not matches:
        loaded.graph.finalize()
        try:
            node_id = resolve_symbol(loaded.graph, query)
        except SymbolLookupError as exc:
            if exc.code != "unknown_symbol":
                raise
            raise FlowLookupError(
                "unknown_flow",
                f"no flow named {query!r} (tried flow IDs, names, console scripts and "
                "entry symbols); list them with `repo-wiki flows`",
                [],
            ) from exc
        matches = [f for f in index.flows if f["entry"] == node_id]
        if not matches:
            count = len(index.touching(node_id))
            raise FlowLookupError(
                "unknown_flow",
                f"{node_id} is not the entry of any flow; it is a step in {count} "
                f"flow(s): run `repo-wiki flows --touching {query}`",
                [],
            )
    if len(matches) > 1:
        raise FlowLookupError(
            "ambiguous_flow",
            f"{query!r} matches {len(matches)} flows; pass one of the IDs listed",
            [flow_summary(f) for f in matches],
        )
    return matches[0]


def show_flow(index: FlowIndex, loaded: LoadedGraph, query: str) -> dict[str, object]:
    """The ``flow`` payload: one flow's summary and its steps with node details."""
    flow = find_flow(index, loaded, query)
    nodes = loaded.graph.nodes
    steps = []
    for step in flow["steps"]:
        node = nodes.get(str(step["id"]))
        detail: dict[str, object] = {"missing": node is None}
        if node is not None:
            detail = {
                "kind": node.kind,
                "name": node.name if not node.is_module else node.id,
                "qualname": node.qualname,
                "path": node.path,
                "start_line": node.start_line,
                "end_line": node.end_line,
            }
        steps.append({**step, **detail})
    return {
        "schema": FLOW_SCHEMA,
        "flow": {
            **flow_summary(flow),
            "aliases": flow.get("aliases", []),
            "steps": steps,
            "terminals": flow["terminals"],
            "cycles": flow["cycles"],
        },
        "settings": index.payload.get("settings"),
        "flows_source": {"source": index.source, "reason": index.reason},
    }


def _emit(payload: dict[str, object], as_json: bool, render) -> None:  # noqa: ANN001
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(render(payload))


def _fail(
    args: argparse.Namespace,
    exit_code: int,
    code: str,
    message: str,
    *,
    candidates: list[dict[str, object]] | None = None,
    details: dict[str, object] | None = None,
) -> int:
    print(f"repo-wiki {args.command}: {message}", file=sys.stderr)
    if candidates:
        for candidate in candidates:
            print(f"  {_where(candidate)}  {candidate['id']}", file=sys.stderr)
    if getattr(args, "json", False):
        error: dict[str, object] = {"code": code, "message": message}
        if candidates is not None:
            error["candidates"] = candidates
        if details:
            error["details"] = details
        print(
            json.dumps(
                {"schema": ERROR_SCHEMA, "error": error}, indent=2, sort_keys=True
            )
        )
    return exit_code


# ------------------------------------------------------------------- rendering


def _where(item: dict[str, object]) -> str:
    return f"{item['path']}:L{item['start_line']}-L{item['end_line']}"


def _edge_tag(item: dict[str, object]) -> str:
    edge = item.get("edge")
    if not isinstance(edge, dict):
        return ""
    tag = f"[{edge['resolution']} {edge['basis']}"
    candidates = edge.get("candidates")
    if isinstance(candidates, list) and len(candidates) > 1:
        tag += f", 1 of {len(candidates)} candidates"
    return tag + "]"


def _flags(item: dict[str, object]) -> str:
    flags = []
    if item.get("is_test"):
        flags.append("test")
    if item.get("public_entry"):
        flags.append(f"public:{item['public_entry']}")
    if item.get("changed"):
        flags.append("changed")
    return f" ({', '.join(flags)})" if flags else ""


def _links(lines: list[str], title: str, bucket: object, indent: str = "  ") -> None:
    if not isinstance(bucket, dict):
        return
    confident = bucket.get("confident") or []
    possible = bucket.get("possible") or []
    lines.append(f"{title}: {len(confident)} confident, {len(possible)} possible")
    for item in confident:
        lines.append(
            f"{indent}{item['id']}  {_where(item)}  {_edge_tag(item)}{_flags(item)}"
        )
    for item in possible:
        lines.append(
            f"{indent}? {item['id']}  {_where(item)}  {_edge_tag(item)}{_flags(item)}"
        )


def _flow_tags(flow: dict) -> str:
    steps = flow["steps"]
    count = len(steps) if isinstance(steps, list) else steps
    tags = [str(flow["kind"]), f"{count} steps", f"depth {flow['depth']}"]
    if flow.get("truncated"):
        tags.append("truncated: " + ", ".join(flow["truncated_reasons"]))
    if flow.get("heuristic_steps"):
        tags.append(f"{flow['heuristic_steps']} HEURISTIC")
    return "[" + "; ".join(tags) + "]"


def _flow_lines(
    lines: list[str],
    title: str,
    block: object,
    *,
    primary: str | None = None,
    extra: str = "",
) -> None:
    """One line per listed flow; where the matched symbols sit in it, briefly."""
    if not isinstance(block, dict):
        return
    flows = block.get("flows") or []
    count = int(block["count"])  # type: ignore[call-overload]
    shown = f", showing {len(flows)}" if len(flows) < count else ""  # type: ignore[arg-type]
    lines.append(f"{title}: {count}{extra}{shown}")
    for flow in flows:  # type: ignore[union-attr]
        matched = flow["matched"]
        at_primary = [m for m in matched if m["id"] == primary]
        if len(matched) == 1 or at_primary:
            where = f"at d={(at_primary or matched)[0]['depth']}"
        else:
            where = f"through {len(matched)} of the symbols"
        lines.append(f"  {flow['name']}  {_flow_tags(flow)}  {where}  {flow['id']}")


def render_flows(payload: dict[str, object]) -> str:
    summary = payload["summary"]
    assert isinstance(summary, dict)
    by_kind = ", ".join(f"{v} {k}" for k, v in summary["by_kind"].items())
    lines = [
        f"Flows: {summary['matched']} of {summary['total']}"
        f"{f' ({by_kind})' if by_kind else ''}; showing {summary['shown']}"
    ]
    for flow in payload.get("flows") or []:  # type: ignore[union-attr]
        at = f"  at d={flow['touching_depth']}" if "touching_depth" in flow else ""
        lines.append(f"  {flow['id']}  {flow['name']}  {_flow_tags(flow)}{at}")
        lines.append(f"      entry {flow['entry']}  {_where(flow)}")
    omitted = summary.get("omitted_flows") or {}
    if omitted:
        lines.append(
            "Not stored (flows.max_flows): "
            + ", ".join(f"{v} {k}" for k, v in omitted.items())
        )
    return "\n".join(lines)


def render_flow(payload: dict[str, object]) -> str:
    flow = payload["flow"]
    assert isinstance(flow, dict)
    head = f"Flow {flow['name']}  {_flow_tags(flow)}  {flow['id']}"
    lines = [head, f"  entry {flow['entry']}  {_where(flow)}"]
    if flow.get("detail"):
        lines.append(f"  via {flow['detail']}")
    if flow.get("aliases"):
        lines.append(f"  also {', '.join(flow['aliases'])}")
    steps = flow["steps"]
    children: dict[str | None, list[dict]] = {}
    for step in steps:
        children.setdefault(step.get("via"), []).append(step)
    stack = list(reversed(children.get(None, [])))
    while stack:
        step = stack.pop()
        indent = "  " * (int(step["depth"]) + 1)
        tag = ""
        if step.get("resolution"):
            tag = f"  [{step['resolution']} {step['basis']}]"
            if step.get("resolution") == "HEURISTIC":
                indent = indent[:-2] + "? "
        where = f"  {_where(step)}" if not step.get("missing") else "  (not in graph)"
        cut = ""
        if step.get("cut"):
            cut = f"  ... {step['omitted']} more not followed ({step['cut']} cap)"
        lines.append(f"{indent}{step.get('qualname') or step['id']}{where}{tag}{cut}")
        stack.extend(reversed(children.get(str(step["id"]), [])))
    lines.append(f"Terminals: {len(flow['terminals'])}")
    if flow.get("cycles"):
        lines.append("Cycles: " + ", ".join(f"{a} -> {b}" for a, b in flow["cycles"]))
    return "\n".join(lines)


def render_context(payload: dict[str, object]) -> str:
    symbol = payload["symbol"]
    assert isinstance(symbol, dict)
    lines = [
        f"{symbol['id']}  ({symbol['kind']}){_flags(symbol)}",
        f"  {_where(symbol)}",
    ]
    if symbol.get("signature"):
        lines.append(f"  {symbol['signature']}")
    if symbol.get("docstring"):
        lines.append(f"  {symbol['docstring']}")
    _links(lines, "Callers", payload.get("callers"))
    _links(lines, "Callees", payload.get("callees"))
    for key, title in (("bases", "Bases"), ("subclasses", "Subclasses")):
        bucket = payload.get(key)
        if isinstance(bucket, dict) and (
            bucket.get("confident") or bucket.get("possible")
        ):
            _links(lines, title, bucket)
    members = payload.get("members") or []
    if members:
        lines.append(f"Members: {len(members)}")  # type: ignore[arg-type]
    for key, title in (
        ("unresolved_calls", "Unresolved calls"),
        ("external_calls", "External calls"),
    ):
        names = payload.get(key) or []
        if names:
            lines.append(f"{title}: {', '.join(names)}")  # type: ignore[arg-type]
    module = payload.get("module")
    if isinstance(module, dict):
        imports = module.get("imports") or []
        importers = module.get("importers") or []
        external = module.get("external_imports") or []
        lines.append(
            f"Module {module['id']}: imports {len(imports)} repository module(s) "  # type: ignore[arg-type]
            f"and {len(external)} external name(s); imported by {len(importers)}"  # type: ignore[arg-type]
        )
        for name in importers:  # type: ignore[union-attr]
            lines.append(f"  imported by {name}")
    flows = payload.get("flows")
    if isinstance(flows, dict):
        _flow_lines(lines, "Flows through it", flows, primary=str(symbol["id"]))
        if flows.get("as_entry"):
            lines.append(f"  entry of {flows['as_entry']}")
    return "\n".join(lines)


def render_impact(payload: dict[str, object]) -> str:
    target = payload["target"]
    assert isinstance(target, dict)
    lines = [
        f"Impact of {target['id']} ({target['kind']}) {_where(target)}"
        f" - {payload['direction']}, depth {payload['depth']}"
    ]
    for level in payload.get("levels") or []:  # type: ignore[union-attr]
        _links(lines, f"d={level['depth']} {level['label']}", level, indent="    ")
    for key, title in (
        ("affected_files", "Affected files"),
        ("affected_test_files", "Affected test files"),
        ("possible_files", "Possibly affected files"),
    ):
        paths = payload.get(key) or []
        lines.append(f"{title}: {len(paths)}")  # type: ignore[arg-type]
        for path in paths:  # type: ignore[union-attr]
            lines.append(f"  {path}")
    summary = payload["summary"]
    assert isinstance(summary, dict)
    if summary.get("risk"):
        reasons = "; ".join(summary.get("risk_reasons") or [])
        lines.append(
            f"Risk: {summary['risk']} (counting possible links: "
            f"{summary['risk_with_possible']}) - {reasons}"
        )
    flows = payload.get("flows")
    if isinstance(flows, dict):
        _flow_lines(
            lines,
            "Affected flows",
            flows,
            primary=str(target["id"]),
            extra=f" ({flows['through_target']} through the target; not part of the risk)",
        )
    return "\n".join(lines)


def render_changes(payload: dict[str, object]) -> str:
    summary = payload["summary"]
    assert isinstance(summary, dict)
    base = payload.get("base_commit") or "empty tree"
    label = {"worktree": "worktree vs HEAD", "staged": "index vs HEAD"}.get(
        str(payload["mode"]), f"worktree vs merge base of {payload.get('base')}"
    )
    lines = [
        f"Changes ({label}, {str(base)[:12]}): {summary['files']} file(s), "
        f"{summary['changed_symbols']} changed symbol(s)"
    ]
    for item in payload.get("changed_symbols") or []:  # type: ignore[union-attr]
        moved = f" (was {item['old_id']})" if item.get("old_id") else ""
        lines.append(
            f"  {item['status']:<8} {item['id']}  {_where(item)}{_flags(item)}{moved}"
        )
        _links(lines, "      d=1 callers", item.get("callers"), indent="        ")
    module_level = payload.get("module_level_changes") or []
    for entry in module_level:  # type: ignore[union-attr]
        spans = ", ".join(f"L{a}-L{b}" for a, b in entry["lines"])
        lines.append(f"  module-level {entry['path']}: {spans}")
    unsupported = [
        f["path"]
        for f in payload.get("files") or []  # type: ignore[union-attr]
        if not f["symbols_supported"]
    ]
    if unsupported:
        lines.append(f"Files without symbols: {', '.join(unsupported)}")
    errors = [
        f"{f['path']} ({f['parse_error']})"
        for f in payload.get("files") or []  # type: ignore[union-attr]
        if f.get("parse_error")
    ]
    if errors:
        lines.append(f"Files that did not parse: {', '.join(errors)}")
    callers = summary["affected_callers"]
    by_status = ", ".join(f"{v} {k}" for k, v in summary["by_status"].items())
    lines.append(
        f"Summary: {summary['changed_symbols']} changed symbol(s)"
        f"{f' ({by_status})' if by_status else ''}; affected callers: "
        f"{callers['confident']} confident, {callers['possible']} possible; "
        f"risk {summary['risk']} (counting possible links: {summary['risk_with_possible']})"
    )
    if summary.get("risk_reasons"):
        lines.append(f"  {'; '.join(summary['risk_reasons'])}")
    refresh = payload.get("refresh")
    if isinstance(refresh, dict):
        lines.insert(
            0,
            f"Refreshed the graph first: {refresh['parsed']} file(s) re-parsed "
            f"in {refresh['seconds']:.1f}s",
        )
    flows = payload.get("flows")
    if "flows_after" in payload and isinstance(flows, dict):
        before = payload.get("flows_before")
        before_text = (
            f"{summary['flows_touched_before']}"
            if isinstance(before, dict)
            else "no graph"
        )
        _flow_lines(
            lines,
            "Flows touched",
            flows,
            extra=(
                f" in the refreshed graph (before the refresh: {before_text}; "
                f"only before: {summary['flows_only_before']}, "
                f"only after: {summary['flows_only_after']})"
            ),
        )
    elif isinstance(flows, dict):
        _flow_lines(lines, "Flows touched", flows)
    return "\n".join(lines)
