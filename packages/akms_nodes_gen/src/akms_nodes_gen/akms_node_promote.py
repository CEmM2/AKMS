#!/usr/bin/env python3
"""Move verified AKMS domain nodes from a staging folder into the global vault
(~/.claude/akms/nodes/) with domain-based subdirectory nesting.

Usage
-----
    # Dry-run (default) — show what would happen without touching files
    python akms_node_promote.py --source Sources_Evals/NLM/Outputs/fft_nodes

    # Actually move the files
    python akms_node_promote.py --source Sources_Evals/NLM/Outputs/fft_nodes --execute

    # Move and promote tentative → established
    python akms_node_promote.py --source Sources_Evals/NLM/Outputs/fft_nodes --execute --promote

    # Override vault location
    python akms_node_promote.py --source ... --vault /custom/vault/path --execute

    e.g.: uv run python Packages/AKMS_nodes_gen/src/akms_nodes_gen/akms_node_promote.py --source Sources_Evals/NLM/Outputs/fft_nodes --vault Packages/Nodes_Vault --execute --promote
Destination
-----------
Nodes are placed in: <vault>/<domain>/<filename>.md
where <vault> defaults to Packages/Nodes_Vault/ inside the repo root
(override with --vault or $AKMS_NODES_VAULT).

The 'domain' frontmatter field determines the subdirectory. Dotted domains
(e.g. 'computational-mechanics.fft-galerkin') create nested paths
(e.g. computational-mechanics/fft-galerkin/).

Source --source path is relative to the repo root (the directory containing
this script, or the --repo-root override).
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Frontmatter helpers
# ---------------------------------------------------------------------------

_FM_FENCE = re.compile(r"^---\s*$")


def parse_frontmatter(text: str) -> dict[str, str]:
    """Return a flat dict of scalar frontmatter values (no nested parsing)."""
    lines = text.splitlines()
    if not lines or not _FM_FENCE.match(lines[0]):
        return {}
    fm_lines: list[str] = []
    for line in lines[1:]:
        if _FM_FENCE.match(line):
            break
        fm_lines.append(line)
    kv: dict[str, str] = {}
    for line in fm_lines:
        m = re.match(r"^(\w[\w_-]*)\s*:\s*(.+)$", line)
        if m:
            kv[m.group(1).strip()] = m.group(2).strip().strip('"').strip("'")
    return kv


def rewrite_status(text: str, old: str = "tentative", new: str = "established") -> str:
    """Replace ``status: <old>`` with ``status: <new>`` inside frontmatter."""
    lines = text.splitlines(keepends=True)
    in_fm = False
    out: list[str] = []
    fence_count = 0
    for line in lines:
        if _FM_FENCE.match(line.rstrip()):
            fence_count += 1
            in_fm = fence_count == 1
        if in_fm and re.match(rf"^status\s*:\s*{re.escape(old)}\s*$", line.rstrip()):
            line = re.sub(
                rf"^(status\s*:\s*){re.escape(old)}",
                rf"\g<1>{new}",
                line,
            )
        out.append(line)
    return "".join(out)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

REQUIRED_FM = {"id", "title", "domain", "status", "akms_schema"}


def resolve_vault(repo: Path) -> Path:
    """Return the vault path from $AKMS_NODES_VAULT or Packages/Nodes_Vault/ in repo."""
    env = os.environ.get("AKMS_NODES_VAULT")
    if env:
        return Path(env).expanduser().resolve()
    return (repo / "Packages" / "Nodes_Vault").resolve()


def domain_to_subdir(domain: str) -> Path:
    """Convert a dotted domain like 'computational-mechanics.fft-galerkin'
    into a relative path like 'computational-mechanics/fft-galerkin'.
    A flat domain like 'fft-galerkin' stays as a single directory."""
    parts = domain.split(".")
    return Path(*parts)


def validate_node(path: Path, fm: dict[str, str]) -> list[str]:
    """Return a list of problems (empty = OK)."""
    problems: list[str] = []
    missing = REQUIRED_FM - set(fm.keys())
    if missing:
        problems.append(f"missing frontmatter fields: {', '.join(sorted(missing))}")
    if fm.get("akms_schema") != "v2":
        problems.append(f"akms_schema is '{fm.get('akms_schema')}', expected 'v2'")
    if "[INSUFFICIENT SOURCE]" in path.read_text(encoding="utf-8"):
        problems.append(
            "contains [INSUFFICIENT SOURCE] marker — review before promoting"
        )
    return problems


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Move verified AKMS nodes into Packages/Nodes_Vault/<domain>/",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument(
        "--source",
        required=True,
        help="Relative path (from repo root) to the staging folder containing .md node files",
    )
    ap.add_argument(
        "--repo-root",
        default=None,
        help="Repository root directory (default: directory containing this script)",
    )
    ap.add_argument(
        "--vault",
        default=None,
        help="Vault path (default: $AKMS_NODES_VAULT or Packages/Nodes_Vault/ in repo)",
    )
    ap.add_argument(
        "--promote",
        action="store_true",
        default=False,
        help="Rewrite status: tentative → status: established in moved files",
    )
    ap.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Actually move files.  Without this flag the script only does a dry-run.",
    )
    args = ap.parse_args()

    # Resolve repo root
    # Script lives at Packages/AKMS_nodes_gen/src/akms_nodes_gen/ — 4 levels up
    if args.repo_root:
        repo = Path(args.repo_root).resolve()
    else:
        repo = Path(__file__).resolve().parents[4]

    # Resolve vault
    if args.vault:
        vault = Path(args.vault).expanduser().resolve()
    else:
        vault = resolve_vault(repo)

    source_dir = repo / args.source
    if not source_dir.is_dir():
        print(f"ERROR: source directory does not exist: {source_dir}", file=sys.stderr)
        return 1

    # Collect .md files (ignore .yaml)
    md_files = sorted(source_dir.glob("*.md"))
    # Filter out non-node files (e.g. review_report.md, README.md)
    node_files: list[Path] = []
    for p in md_files:
        text = p.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        if fm.get("akms_schema") == "v2":
            node_files.append(p)

    if not node_files:
        print(f"No AKMS v2 node .md files found in {source_dir}")
        return 0

    print(
        f"{'DRY-RUN' if not args.execute else 'EXECUTING'}: "
        f"found {len(node_files)} node(s) in {source_dir.relative_to(repo)}"
    )
    print(f"Vault:  {vault}\n")

    moved = 0
    skipped = 0
    warnings: list[str] = []

    for src in node_files:
        text = src.read_text(encoding="utf-8")
        fm = parse_frontmatter(text)
        node_id = fm.get("id", src.stem)
        domain = fm.get("domain", "unknown")

        # Validate
        problems = validate_node(src, fm)

        # Determine destination: <vault>/<domain-subdir>/<filename>.md
        domain_path = domain_to_subdir(domain)
        dest_dir = vault / domain_path
        dest = dest_dir / src.name

        # Status line
        status_tag = fm.get("status", "?")
        promote_tag = ""
        if args.promote and status_tag == "tentative":
            promote_tag = " → established"

        print(f"  {src.name}")
        print(f"    id:     {node_id}")
        print(f"    domain: {domain}")
        print(f"    status: {status_tag}{promote_tag}")
        print(f"    dest:   {dest_dir}/")

        if problems:
            for p in problems:
                print(f"    ⚠  {p}")
            warnings.append(f"{src.name}: {'; '.join(problems)}")

        if dest.exists():
            print(f"    ⚠  destination exists — will overwrite")

        if args.execute:
            # Create destination directory
            dest_dir.mkdir(parents=True, exist_ok=True)

            # Optionally promote
            if args.promote and status_tag == "tentative":
                text = rewrite_status(text, "tentative", "established")

            # Write to destination
            dest.write_text(text, encoding="utf-8")

            src.unlink()

            print(f"    ✓  moved")
            moved += 1
        else:
            print(f"    (dry-run, no files moved)")
            moved += 1  # count for summary

        print()

    # Summary
    print("─" * 60)
    if args.execute:
        print(f"Moved:    {moved}")
    else:
        print(f"Would move: {moved}")
    print(f"Warnings: {len(warnings)}")

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(f"  • {w}")

    if not args.execute:
        print(f"\nThis was a dry-run.  Re-run with --execute to move files.")
        if args.promote:
            print(
                "The --promote flag will also rewrite status: tentative → established."
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
