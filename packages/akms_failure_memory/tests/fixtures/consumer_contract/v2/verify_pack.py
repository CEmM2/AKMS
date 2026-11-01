#!/usr/bin/env python3
"""Verify a consumer-contract pack against its own fixture-manifest.json.

Standard library only, no third-party imports, no AKMS import: a consumer that
has vendored or fetched the pack can run this before installing anything.

    python3 verify_pack.py [PACK_DIR]            # verify (consumers)
    python3 verify_pack.py [PACK_DIR] --update   # re-freeze (maintainers only)

PACK_DIR defaults to the directory containing this script. Exit code 0 means the
pack is byte-identical to the one this manifest describes; any non-zero exit
means the pack MUST NOT be used.

Checks (all fail-closed -- an unreadable or missing input is a FAIL, never a
skip):

  1. Every path in fixture-manifest.json -> checksum.files exists and matches its
     recorded sha256.
  2. No file exists in the pack outside that closed allowlist (ignoring the
     documented scratch paths), so a pack cannot be extended silently.
  3. The recomputed pack digest equals fixture-manifest.json -> checksum.pack_sha256.

Digest definition (reimplement it if you do not trust this script):

    sha256 over the allowlisted files sorted by POSIX relative path, feeding
    for each file:  relpath.encode("utf-8") + b"\\x00" + file_bytes + b"\\x00"

fixture-manifest.json itself is excluded from the digest -- it carries the
digest, so including it would be circular. Pin the manifest's own sha256
out-of-band (it is recorded in the integration lock) if you need to detect
tampering with the manifest.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

MANIFEST_NAME = "fixture-manifest.json"

# Scratch paths a consumer may legitimately create by staging the pack IN PLACE
# (which the pack tells you not to do -- copy it to a scratch root instead).
IGNORED_PREFIXES = ("runtime/", "__pycache__/")
IGNORED_NAMES = (".DS_Store",)


def _iter_pack_files(root: Path) -> list[str]:
    found = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative == MANIFEST_NAME:
            continue
        if relative.startswith(IGNORED_PREFIXES) or path.name in IGNORED_NAMES:
            continue
        if "/__pycache__/" in f"/{relative}":
            continue
        found.append(relative)
    return found


def pack_digest(root: Path, relative_paths: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(relative_paths):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update((root / relative).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def verify(root: Path) -> tuple[bool, list[str]]:
    problems: list[str] = []
    manifest_path = root / MANIFEST_NAME
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        checksum = manifest["checksum"]
        expected_files = dict(checksum["files"])
        expected_pack = str(checksum["pack_sha256"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return False, [f"cannot read {manifest_path}: {exc}"]

    for relative, recorded in sorted(expected_files.items()):
        path = root / relative
        if not path.is_file():
            problems.append(f"missing file: {relative}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != recorded:
            problems.append(
                f"digest mismatch: {relative}\n  recorded {recorded}\n  actual   {actual}"
            )

    for relative in _iter_pack_files(root):
        if relative not in expected_files:
            problems.append(f"unlisted file present in pack: {relative}")

    if not problems:
        actual_pack = pack_digest(root, list(expected_files))
        if actual_pack != expected_pack:
            problems.append(
                f"pack digest mismatch\n  recorded {expected_pack}\n  actual   {actual_pack}"
            )
    return not problems, problems


def update(root: Path) -> str:
    """Rewrite the manifest's checksum block from the pack's current bytes.

    Maintainer-only. Running this makes any edit to the pack 'verify', so it is
    a deliberate re-freeze of the contract, not a repair: the new pack_sha256
    must be re-announced to every consumer.
    """
    manifest_path = root / MANIFEST_NAME
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    relative_paths = _iter_pack_files(root)
    manifest["checksum"]["files"] = {
        relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
        for relative in sorted(relative_paths)
    }
    manifest["checksum"]["file_count"] = len(relative_paths)
    manifest["checksum"]["pack_sha256"] = pack_digest(root, relative_paths)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(manifest["checksum"]["pack_sha256"])


def main(argv: list[str]) -> int:
    arguments = [item for item in argv[1:] if item != "--update"]
    root = (
        Path(arguments[0]).resolve() if arguments else Path(__file__).resolve().parent
    )
    if "--update" in argv[1:]:
        print(f"UPDATED pack_sha256 = {update(root)}")
        return 0
    ok, problems = verify(root)
    if ok:
        print(f"PASS consumer-contract pack verified: {root}")
        return 0
    print(
        f"FAIL consumer-contract pack is NOT the pinned pack: {root}", file=sys.stderr
    )
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
