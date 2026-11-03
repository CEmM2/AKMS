"""``akms migrate-layout``: move a repository's knowledge to ``.knowledge/``.

Repositories created before ``.knowledge/`` became the default keep their
knowledge in ``knowledge/``, and AKMS keeps reading it there. This command
moves it, for a project that wants the new layout. Projects that use
``akms-failure-memory`` should run ``failure-memory migrate-layout`` instead,
which also updates that package's configuration.

Registered via :func:`register_layout_commands`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_migrate_layout(args: argparse.Namespace) -> int:
    from akms.layout import KnowledgeLayoutError, migrate_knowledge_layout

    try:
        result = migrate_knowledge_layout(Path(args.repo), check=args.check)
    except KnowledgeLayoutError as exc:
        if args.json:
            print(json.dumps({"error": str(exc), "code": exc.code}, indent=2))
        else:
            print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return 0
    print(format_migration(result.to_dict()))
    return 0


def format_migration(data: dict) -> str:
    """Human-readable summary of a ``KnowledgeMigration`` dict."""
    status = data["status"]
    if status == "already_migrated":
        return f"{data['repo_root']} already uses {data['to']}/; nothing to do."
    verb = "Would move" if status == "planned" else "Moved"
    how = "git mv" if data["move"] == "git-mv" else "rename"
    lines = [f"{verb} {data['from']}/ to {data['to']}/ ({how})."]
    if data["edits"]:
        lines.append("Rewritten lines:")
        lines += [
            f"  {e['file']}:{e['line']}: {e['before']}  ->  {e['after']}"
            for e in data["edits"]
        ]
    if data["removed"]:
        lines.append("Removed compiled outputs (rebuilt on next use):")
        lines += [f"  {path}" for path in data["removed"]]
    if data["mentions"]:
        lines.append(f"Still mentioning {data['from']}/ (not changed; review by hand):")
        lines += [f"  {m['file']}:{m['line']}: {m['text']}" for m in data["mentions"]]
    return "\n".join(lines)


def register_layout_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register ``migrate-layout`` on the root parser."""
    migrate = subparsers.add_parser(
        "migrate-layout",
        help="Move <repo>/knowledge/ to <repo>/.knowledge/",
        description=(
            "Move an existing knowledge/ directory to .knowledge/, re-anchor "
            ".gitignore and .gitattributes lines on it, and drop the compiled "
            "graph so it is rebuilt. Tracked directories move with git mv. "
            "Projects using failure-memory: run `failure-memory migrate-layout`."
        ),
    )
    # SUPPRESS keeps a root-level `akms --repo X migrate-layout` value.
    migrate.add_argument(
        "--repo",
        "-r",
        default=argparse.SUPPRESS,
        help="Repository root whose knowledge/ moves (default: current directory)",
    )
    migrate.add_argument(
        "--check", action="store_true", help="Show what would change; change nothing"
    )
    migrate.add_argument("--json", action="store_true", help="Emit JSON")
    migrate.set_defaults(func=cmd_migrate_layout)
