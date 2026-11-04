"""``context``, ``impact`` and ``changes`` subcommands: argument parsing and text output.

Exit codes: 0 success, 1 git or I/O failure, 2 usage error, 3 symbol graph missing,
unreadable or stale, 4 symbol unknown or ambiguous. With ``--json`` a failure prints an
``repo-wiki/error/v1`` object on stdout as well as the message on stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from akms.repo_wiki.code_graph import GraphUnavailableError, load_code_graph
from akms.repo_wiki.config import load_config
from akms.repo_wiki.impact import (
    DEFAULT_DEPTH,
    SymbolLookupError,
    build_context,
    build_impact,
    resolve_symbol,
    symbol_details,
)

ERROR_SCHEMA = "repo-wiki/error/v1"
EXIT_GIT = 1
EXIT_USAGE = 2
EXIT_GRAPH = 3
EXIT_SYMBOL = 4

INTEL_COMMANDS = ("context", "impact", "changes")


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


def run_intel(args: argparse.Namespace, repo_root: Path) -> int:
    """Dispatch one code-intelligence subcommand."""
    from akms.repo_wiki.changes import GitError, detect_changes

    try:
        config = load_config(repo_root)
        if args.command == "changes":
            mode = "base" if args.base else ("staged" if args.staged else "worktree")
            payload = detect_changes(
                repo_root,
                config,
                mode=mode,
                base=args.base,
                allow_stale=args.allow_stale,
            )
            _emit(payload, args.json, render_changes)
            return 0
        if args.command == "impact" and args.depth < 1:
            return _fail(
                args, EXIT_USAGE, "usage", f"--depth must be >= 1, got {args.depth}"
            )
        loaded = load_code_graph(repo_root, config=config, allow_stale=args.allow_stale)
        graph = loaded.graph
        node_id = resolve_symbol(graph, args.symbol)
        if args.command == "context":
            payload = build_context(
                graph,
                node_id,
                details=symbol_details(repo_root, config, graph.nodes[node_id]),
            )
            payload["graph"] = loaded.to_dict(repo_root)
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
        _emit(payload, args.json, render_impact)
        return 0
    except GraphUnavailableError as exc:
        return _fail(args, EXIT_GRAPH, exc.code, str(exc), details=exc.details)
    except SymbolLookupError as exc:
        return _fail(args, EXIT_SYMBOL, exc.code, str(exc), candidates=exc.candidates)
    except GitError as exc:
        return _fail(args, EXIT_GIT, "git_error", str(exc))


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
    return "\n".join(lines)
