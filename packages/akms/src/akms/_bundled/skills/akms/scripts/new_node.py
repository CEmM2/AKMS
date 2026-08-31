#!/usr/bin/env python3
"""Scaffold a schema-valid AKMS v2 local knowledge node.

The point is to start from something that already passes the validator, so the
only work left is writing the knowledge itself.

    python skills/akms/scripts/new_node.py fem-assembly \
        --title "Finite-element global assembly" \
        --domain computational-mechanics \
        --tags fem assembly sparse-matrices

Agent-authored nodes default to status=tentative / source=agent, which is what
the schema requires: only human-authored nodes may enter as established.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

STATUSES = ("draft", "tentative", "established", "deprecated")
SOURCES = ("human", "agent", "hybrid", "generated")
CONTEXT_SIZES = ("small", "medium", "large")
READING_PRIORITIES = ("full", "summary", "pitfalls-only")

TEMPLATE = """---
id: {id}
title: {title}
domain: {domain}
{subdomain_line}tags:
{tag_lines}
status: {status}
confidence: {confidence}
source: {source}
edges: []
load_with: []
context_size: {context_size}
reading_priority: {reading_priority}
content_ref: {content_ref}
akms_schema: v2
---

# {title}

<!-- The bar: a first-year PhD student should be able to implement this from
     the content below alone, without reading the source papers. If a reader
     would still have to go find the paper, this node is not finished. -->

## Summary

TODO replace this paragraph. The summary is REQUIRED — it is the text shown in
routing-mode loadouts, so for most retrievals it is the only part of this node
an agent ever reads. Aim for three to five sentences, roughly forty to eighty
words, stating what this knowledge is and when it applies.

## 1. Core Concept

TODO: definitions and the governing idea. Be concrete enough to implement.

## 2. Mathematical Formulation

TODO: the governing relations, with symbols defined. Delete this section if the
topic is not mathematical.

## 3. Procedure

TODO: the steps, in order.

## 4. Known Pitfalls

<!-- Pitfalls are the highest-value part of most nodes: they are what an agent
     cannot derive from first principles. Delete this section only if the topic
     genuinely has no traps. -->

TODO: the traps. What looks right and is not.
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="new_node.py",
        description="Scaffold a schema-valid AKMS v2 local node.",
    )
    p.add_argument("node_id", help="Stable kebab-case node id (also the filename)")
    p.add_argument("--title", help="Human-readable title (default: derived from id)")
    p.add_argument(
        "--domain", required=True, help="Broad area, e.g. computational-mechanics"
    )
    p.add_argument("--subdomain", default=None, help="Narrower area (optional)")
    p.add_argument(
        "--tags", nargs="+", required=True, help="One or more retrieval tags"
    )
    p.add_argument("--status", choices=STATUSES, default="tentative")
    p.add_argument("--source", choices=SOURCES, default="agent")
    p.add_argument(
        "--confidence",
        type=float,
        default=None,
        help="0.0-1.0 (default: 0.5 tentative, 0.9 established)",
    )
    p.add_argument("--context-size", choices=CONTEXT_SIZES, default="medium")
    p.add_argument("--reading-priority", choices=READING_PRIORITIES, default="summary")
    p.add_argument("--repo", "-r", default=".", help="Repository root (default: cwd)")
    p.add_argument(
        "--force", action="store_true", help="Overwrite an existing node file"
    )
    return p


def main() -> int:
    args = build_parser().parse_args()

    if args.source == "agent" and args.status == "established":
        print(
            "refusing: agent-authored nodes must enter as tentative, not established.\n"
            "Promote it later with `akms promote` once it has proven correct.",
            file=sys.stderr,
        )
        return 2

    if not 0.0 <= (args.confidence if args.confidence is not None else 0.5) <= 1.0:
        print("refusing: --confidence must be between 0.0 and 1.0", file=sys.stderr)
        return 2

    confidence = args.confidence
    if confidence is None:
        confidence = 0.9 if args.status == "established" else 0.5

    title = args.title or args.node_id.replace("-", " ").replace("_", " ").capitalize()

    repo = Path(args.repo).resolve()
    out_dir = repo / "knowledge" / "local-nodes"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.node_id}.md"

    if out_path.exists() and not args.force:
        print(
            f"refusing: {out_path} already exists (use --force to overwrite)",
            file=sys.stderr,
        )
        return 1

    content_ref = f"knowledge/local-nodes/{args.node_id}.md"
    body = TEMPLATE.format(
        id=args.node_id,
        title=title,
        domain=args.domain,
        subdomain_line=f"subdomain: {args.subdomain}\n" if args.subdomain else "",
        tag_lines="\n".join(f"  - {t}" for t in args.tags),
        status=args.status,
        confidence=confidence,
        source=args.source,
        context_size=args.context_size,
        reading_priority=args.reading_priority,
        content_ref=content_ref,
    )
    out_path.write_text(body)

    print(
        f"created {out_path.relative_to(repo) if out_path.is_relative_to(repo) else out_path}"
    )
    print("next:")
    print("  1. write the content (the TODOs)")
    print(f"  2. python -m akms.tools.node_validator {content_ref} --strict")
    print("  3. akms status --repo .")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
