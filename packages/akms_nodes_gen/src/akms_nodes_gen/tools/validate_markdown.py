#!/usr/bin/env python3
"""Built-in Markdown validator for generated AKMS nodes.

Thin CLI wrapper around the canonical ``akms.tools.node_validator`` (the core
AKMS package). It parses a single ``.md`` node, validates its frontmatter + body
against the frozen v2 schema, and exits 0 only when there are no ERROR-level
issues. WARNING/INFO issues are reported but do not fail the gate (matching the
"human reviews warnings" posture of the generation pipeline).

Usage:
    python -m akms_nodes_gen.tools.validate_markdown <node.md> --validate-only [-v]
    python validate_markdown.py <node.md> --validate-only [--strict] [-v]

This matches the call contract in ``nlm_batch._run_postprocessors``
(``python <validator> <md_path> --validate-only -v``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def validate_file(md_path: Path, strict: bool = False) -> tuple[int, list[str]]:
    """Validate one ``.md`` node. Returns (exit_code, message_lines).

    exit_code is 0 when there are no ERROR-level issues (and, under ``strict``,
    no WARNING-level issues either).
    """
    try:
        from akms.tools.node_validator import (  # local import: optional core dep
            Severity,
            parse_md_file,
            validate_frontmatter,
        )
    except Exception as exc:  # noqa: BLE001 - core akms package not importable
        return 2, [f"validate_markdown: cannot import akms.tools.node_validator: {exc}"]

    if not md_path.exists():
        return 2, [f"validate_markdown: file not found: {md_path}"]

    fm, body, parse_issues = parse_md_file(md_path)
    issues = list(parse_issues)
    if fm is not None:
        _model, validation_issues = validate_frontmatter(fm, body, known_ids=None)
        issues.extend(validation_issues)

    errors = [i for i in issues if i.severity == Severity.ERROR]
    warnings = [i for i in issues if i.severity == Severity.WARNING]

    lines = [str(issue) for issue in issues]
    failed = bool(errors) or (strict and bool(warnings))
    return (1 if failed else 0), lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an AKMS node .md against the v2 schema.")
    parser.add_argument("md_path", type=Path, help="Path to the node .md file")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate without writing fixes (accepted for call-contract compatibility; this tool never writes).",
    )
    parser.add_argument("--strict", action="store_true", help="Treat WARNING-level issues as failures too.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print all issues, not just errors.")
    args = parser.parse_args(argv)

    code, lines = validate_file(args.md_path, strict=args.strict)

    if code == 0:
        if args.verbose and lines:
            for line in lines:
                print(line)
        if args.verbose:
            print(f"validate_markdown: OK ({args.md_path})")
        return 0

    # Failure: always emit the issues so the caller can persist them.
    print(f"validate_markdown: validation failed for {args.md_path}", file=sys.stderr)
    for line in lines:
        print(line, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
