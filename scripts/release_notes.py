#!/usr/bin/env python3
"""Write one release's CHANGELOG.md section to a file, for the release page."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def release_notes(changelog: str, version: str) -> str:
    """Return the body under ``## [version]``, up to the next release heading.

    Raises ``ValueError`` when the heading is missing or its section is empty:
    a release must not go out with blank notes.
    """
    heading = re.compile(rf"^##\s+\[?{re.escape(version)}\]?(?!\S).*$", re.MULTILINE)
    found = heading.search(changelog)
    if found is None:
        raise ValueError(f"CHANGELOG.md has no release heading for version {version}")
    following = re.compile(r"^##\s+\S", re.MULTILINE).search(changelog, found.end())
    body = changelog[found.end() : following.start() if following else None].strip()
    if not body:
        raise ValueError(f"CHANGELOG.md has no entries for version {version}")
    return body + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="Release tag, for example v0.4.0")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        notes = release_notes(
            (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"),
            args.tag.removeprefix("v"),
        )
    except (OSError, ValueError) as error:
        print(f"Release notes failed: {error}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(notes, encoding="utf-8")
    print(f"Release notes written: {len(notes)} characters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
