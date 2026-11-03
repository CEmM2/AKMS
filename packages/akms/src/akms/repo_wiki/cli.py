"""Command line interface for repo-wiki."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from akms.repo_wiki.answer import (
    CITATION_FORMAT,
    INSUFFICIENT_CONTEXT_MSG,
    AnswerResult,
    LocalContextOnlyAnswerProvider,
)
from akms.repo_wiki.config import init_repo_wiki, load_config
from akms.repo_wiki.export import export_akms
from akms.repo_wiki.export.akms import (
    DEFAULT_KNOWLEDGE_DIR,
    KNOWLEDGE_DIRS,
    ErrorRecord,
    ExportResult,
    resolve_generated_at,
)
from akms.repo_wiki.graph_viewer import (
    DEFAULT_GRAPH_RELPATH,
    DEFAULT_HOST,
    DEFAULT_PORT,
    serve,
)
from akms.repo_wiki.index import SearchResult, search_index, update_index
from akms.repo_wiki.locking import LockError
from akms.repo_wiki.manifest import build_repo, get_backend_notes, load_manifest
from akms.repo_wiki.models import SourceFile
from akms.repo_wiki.extract.python_ast import parse_python_file, parsed_module_to_json
from akms.repo_wiki.retrieve import retrieve
from akms.repo_wiki.scanner import scan_repository, scan_to_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repo-wiki")
    parser.add_argument(
        "--repo-root", default=".", help="Repository root to operate on"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    scan = sub.add_parser("scan")
    scan.add_argument("--json", action="store_true")
    parse = sub.add_parser("parse")
    parse.add_argument("path")
    parse.add_argument("--json", action="store_true")
    build = sub.add_parser("build")
    build.add_argument("--changed-only", action="store_true")
    build.add_argument("--force", action="store_true")
    build.add_argument("--no-summaries", action="store_true")
    build.add_argument("--no-index", action="store_true")
    build.add_argument("--json", action="store_true")
    index = sub.add_parser("index")
    index.add_argument("--changed-only", action="store_true")
    index.add_argument("--force", action="store_true")
    index.add_argument("--json", action="store_true")
    index.add_argument("--query")
    query = sub.add_parser("query")
    query.add_argument("question", nargs="+")
    query.add_argument("--show-context", action="store_true")
    query.add_argument("--json", action="store_true")
    query.add_argument("--no-answer", action="store_true")
    query.add_argument("--top-k", type=int)
    sub.add_parser("summarize")
    summarize = sub.choices["summarize"]
    summarize.add_argument("--changed-only", action="store_true")
    summarize.add_argument("--force", action="store_true")
    summarize.add_argument("--symbol")
    export = sub.add_parser(
        "export-akms",
        description=(
            "Project eligible repository source into deterministic AKMS mirror Markdown. "
            "This command does not summarize or index source. "
            "Full export is the safe default; path and git-diff selection are explicit."
        ),
        epilog=(
            "Example: repo-wiki --repo-root . export-akms --output ./akms "
            "--phase 1 --generated-at 2026-03-07T12:00:00+00:00 --full --json\n"
            "Deterministic timestamp may also come from SOURCE_DATE_EPOCH. "
            "Selection uses repeated --path PATH or --git-base REF [--git-head REF] "
            "as argv lists without shell interpolation."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    export.add_argument("--output", required=True, help="AKMS output root")
    export.add_argument(
        "--knowledge-dir",
        choices=KNOWLEDGE_DIRS,
        default=DEFAULT_KNOWLEDGE_DIR,
        help=(
            "Knowledge directory under --output that receives code-mirror/ "
            "(default: %(default)s)"
        ),
    )
    export.add_argument(
        "--strict-parse",
        action="store_true",
        help=(
            "Treat a source that fails to parse as an error and write nothing "
            "(default: skip it, keep its existing mirror, export the rest)"
        ),
    )
    export.add_argument(
        "--phase", required=True, type=int, help="Positive generating phase"
    )
    export.add_argument(
        "--generated-at",
        default=None,
        help=(
            "Explicit ISO-8601 generation timestamp. Required unless SOURCE_DATE_EPOCH "
            "is set. The exporter never reads the wall clock."
        ),
    )
    mode = export.add_mutually_exclusive_group()
    mode.add_argument(
        "--full", action="store_true", help="Write every requested mirror"
    )
    mode.add_argument(
        "--changed-only",
        action="store_true",
        help="Skip mirrors whose deterministic rendered bytes already match",
    )
    export.add_argument(
        "--path",
        action="append",
        dest="source_paths",
        default=None,
        metavar="PATH",
        help=(
            "Export only this repository-relative source path (repeatable). "
            "Mutually exclusive with --git-base. No shell globbing is performed."
        ),
    )
    export.add_argument(
        "--git-base",
        default=None,
        metavar="REF",
        help=(
            "Select sources changed since this git ref (diff against the worktree, "
            "or against --git-head when provided). Uses argv-safe git calls only."
        ),
    )
    export.add_argument(
        "--git-head",
        default=None,
        metavar="REF",
        help=(
            "Optional second git ref for --git-base...REF two-tree selection. "
            "Refuses a dirty worktree."
        ),
    )
    export.add_argument(
        "--prune",
        action="store_true",
        help=(
            "Remove stale exporter-owned mirrors after a completely successful full export. "
            "Refused when path or git-diff selection is active."
        ),
    )
    export.add_argument(
        "--force-lock",
        action="store_true",
        help=(
            "Reclaim a stale, dead, unreadable, or expired output-scoped export "
            "lock (.repo2md-export-<hash>.lock beside the resolved --output). "
            "Refuses to steal a lock from a live matching exporter process "
            "(PID + start-time/cmdline fingerprint)."
        ),
    )
    export.add_argument(
        "--json", action="store_true", help="Emit only result JSON on stdout"
    )
    sub.add_parser("stats")
    graph = sub.add_parser(
        "graph", help="Serve an interactive viewer for the symbol graph"
    )
    graph.add_argument(
        "input",
        nargs="?",
        default=None,
        help="Symbol graph JSON (default: <repo-root>/.repo_wiki/generated/symbol_graph.json)",
    )
    graph.add_argument("--host", default=DEFAULT_HOST)
    graph.add_argument("--port", type=int, default=DEFAULT_PORT)
    graph.add_argument(
        "--no-browser", action="store_true", help="Do not open a browser"
    )
    sub.add_parser("clean")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    if args.command == "init":
        created = init_repo_wiki(repo_root)
        print(f"Initialized repo wiki at {repo_root / '.repo_wiki'}")
        for path in created:
            print(f"created: {path.relative_to(repo_root).as_posix()}")
        return 0
    if args.command == "scan":
        config = load_config(repo_root)
        sources, skipped = scan_repository(repo_root, config)
        if args.json:
            print(scan_to_json(sources, skipped))
        else:
            print(f"Eligible files: {len(sources)}")
            print(f"Skipped files: {len(skipped)}")
            for source in sources:
                print(source.path)
        return 0
    if args.command == "parse":
        source = source_for_path(repo_root, Path(args.path))
        parsed = parse_python_file(source)
        if args.json:
            print(parsed_module_to_json(parsed))
        else:
            print(f"Module: {parsed.module}")
            print(f"Symbols: {len(parsed.symbols)}")
            for symbol in parsed.symbols:
                print(
                    f"{symbol.kind}: {symbol.symbol_id} L{symbol.start_line}-L{symbol.end_line}"
                )
        return 0 if not parsed.errors else 1
    if args.command == "build":
        summary = build_repo(
            repo_root,
            changed_only=args.changed_only,
            force=args.force,
            no_summaries=args.no_summaries,
            no_index=args.no_index,
        )
        if args.json:
            print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
        else:
            print("--- build summary ---")
            print(f"processed: {summary.parsed}")
            print(f"skipped:   {summary.skipped}")
            print(f"errored:   {len(summary.errors)}")
            if summary.backend_notes:
                print("Backend notes:")
                for note in summary.backend_notes:
                    print(f"  {note}")
            print("--- end summary ---")
        return 0 if not summary.errors else 1
    if args.command == "index":
        summary = update_index(
            repo_root, changed_only=args.changed_only, force=args.force
        )
        if args.query:
            results = [item.to_dict() for item in search_index(repo_root, args.query)]
            print(
                json.dumps(
                    {"summary": summary.to_dict(), "results": results},
                    indent=2,
                    sort_keys=True,
                )
            )
        elif args.json:
            print(json.dumps(summary.to_dict(), indent=2, sort_keys=True))
        else:
            print(f"Indexed: {summary.indexed}")
            print(f"Skipped unchanged: {summary.skipped_unchanged}")
            print(f"Deleted: {summary.deleted}")
        return 0
    if args.command == "query":
        question = " ".join(args.question)
        pack = retrieve(
            repo_root,
            question,
            top_k=args.top_k,
            expand=True,
        )
        provider = LocalContextOnlyAnswerProvider()
        answer_result = (
            provider.context_only(pack, question)
            if args.no_answer
            else provider.answer(pack, question)
        )

        if args.json:
            payload = pack.to_dict()
            payload["answer"] = answer_payload(answer_result)
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        print(f"Query: {question}")
        print("Results:")
        for result in pack.results:
            print(f"- {result_line(result)}")
        # --no-answer always lists context; the answer mode does so only on request.
        if args.no_answer or args.show_context:
            print("Context:")
            for block in pack.context:
                print(f"- [{block.role}] {result_line(block.result)}")
        if not args.no_answer:
            print("Answer:")
            if answer_result.insufficient_context:
                print(INSUFFICIENT_CONTEXT_MSG)
            else:
                for claim in answer_result.claims:
                    for citation in claim.citations:
                        label = (
                            f"[{citation.label}]"
                            if citation.secondary
                            else citation.label
                        )
                        print(f"  {label}: {claim.text}")
        return 0
    if args.command == "summarize":
        summary = build_repo(
            repo_root,
            changed_only=args.changed_only,
            force=args.force,
            no_summaries=False,
            no_index=True,
            summary_symbol=args.symbol,
        )
        print(f"Generated summaries: {summary.generated_summaries}")
        return 0 if not summary.errors else 1
    if args.command == "export-akms":
        generated_at: str | None = None
        try:
            generated_at = resolve_generated_at(args.generated_at)
            if args.phase < 1:
                raise ValueError(
                    f"phase must be a positive integer, got {args.phase!r}"
                )
            if args.git_head is not None and args.git_base is None:
                raise ValueError("--git-head requires --git-base")
            if args.source_paths and args.git_base is not None:
                raise ValueError("--path and --git-base are mutually exclusive")
            output_root = resolve_export_output(repo_root, args.output)
            if output_root.exists() and not output_root.is_dir():
                raise ValueError(f"output path is not a directory: {output_root}")
        except (OSError, TypeError, ValueError) as exc:
            print(f"export-akms: {exc}", file=sys.stderr)
            return 2

        assert generated_at is not None
        try:
            result = export_akms(
                repo_root=repo_root,
                output_root=output_root,
                phase=args.phase,
                generated_at=generated_at,
                changed_only=args.changed_only,
                prune=args.prune,
                source_paths=args.source_paths,
                git_base=args.git_base,
                git_head=args.git_head,
                acquire_lock=True,
                force_lock=args.force_lock,
                knowledge_dir=args.knowledge_dir,
                strict_parse=args.strict_parse,
            )
        except LockError as exc:
            print(f"export-akms lock error: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            result = ExportResult(
                phase=args.phase,
                generated_at=generated_at,
                errors=[ErrorRecord(None, None, "validation", str(exc))],
            )
            emit_export_result(result, json_output=args.json)
            return 1
        emit_export_result(result, json_output=args.json)
        return 0 if not result.errors else 1
    if args.command == "stats":
        manifest = load_manifest(repo_root)
        generated = repo_root / ".repo_wiki" / "generated"
        print(f"Repo: {repo_root.name}")
        print(f"Initialized: {(repo_root / '.repo_wiki').exists()}")
        print(f"Tracked files: {len(manifest.files)}")
        print(
            f"Generated docs: {len(list(generated.rglob('*.md'))) if generated.exists() else 0}"
        )
        notes = get_backend_notes(manifest)
        if notes:
            print("Backend notes:")
            for note in notes:
                print(f"  {note}")
        return 0
    if args.command == "graph":
        graph_path = (
            Path(args.input) if args.input else repo_root / DEFAULT_GRAPH_RELPATH
        )
        return serve(graph_path, args.host, args.port, not args.no_browser)
    if args.command == "clean":
        print("Clean is not implemented; no files removed.")
        return 0
    return 2


def resolve_export_output(repo_root: Path, output: str) -> Path:
    """Resolve a CLI output path, containing relative paths beneath the repository."""

    requested = Path(output)
    if requested.is_absolute():
        return requested.resolve()
    resolved = (repo_root / requested).resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(
            f"relative output path must remain beneath repository root: {output!r}"
        ) from exc
    return resolved


def emit_export_result(result: ExportResult, *, json_output: bool) -> None:
    """Emit the AKMS command result without contaminating JSON stdout."""

    if json_output:
        print(result.to_json())
    else:
        for record in result.written:
            print(f"written: {record.generated_path}")
        for record in result.removed:
            print(f"removed: {record.generated_path}")
        for record in result.skipped:
            print(f"skipped ({record.reason}): {record.source_path}")
    for record in result.skipped:
        if record.reason == "parse_error":
            print(
                f"export-akms warning [{record.source_path}]: source did not parse; "
                "skipped, existing mirror kept",
                file=sys.stderr,
            )
    for error in result.errors:
        source = error.source_path or "<export>"
        print(
            f"export-akms {error.stage} error [{source}]: {error.message}",
            file=sys.stderr,
        )


def answer_payload(answer_result: AnswerResult) -> dict[str, object]:
    """Serialize an AnswerResult for query JSON output via ``asdict`` (all Citation fields)."""
    return {
        "insufficient_context": answer_result.insufficient_context,
        "claims": [asdict(claim) for claim in answer_result.claims],
        "citations": [asdict(citation) for citation in answer_result.citations],
    }


def result_line(result: SearchResult) -> str:
    """Human-readable one-line label + location for a search result."""
    location = (
        CITATION_FORMAT.format(
            path=result.path, start=result.start_line, end=result.end_line
        )
        if result.start_line
        else result.path
    )
    label = result.symbol_id or result.module or result.title
    match = f" [match: {result.resolution}]" if result.resolution else ""
    return f"{label} ({result.doc_type}) {location}{match}"


def source_for_path(repo_root: Path, path: Path) -> SourceFile:
    abs_path = path if path.is_absolute() else repo_root / path
    rel = abs_path.resolve().relative_to(repo_root).as_posix()
    from akms.repo_wiki.hashing import sha256_file

    return SourceFile(
        rel, str(abs_path), "python", abs_path.stat().st_size, sha256_file(abs_path)
    )
