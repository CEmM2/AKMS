#!/usr/bin/env python3
"""Regenerate or byte-check the committed AKMS export fixture pack.

This is producer-side tooling.  Consumers validate the committed artifacts
directly and never need to import this script or ``akms.repo_wiki``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from akms.repo_wiki.export import export_akms  # noqa: E402


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "akms_export"
SOURCE_REPOSITORY = FIXTURE_ROOT / "source_repo"
EXPECTED_ROOT = FIXTURE_ROOT / "expected"
RESULT_PATH = FIXTURE_ROOT / "export_result.json"
MANIFEST_PATH = FIXTURE_ROOT / "fixture_manifest.json"
FIXTURE_CONTRACT_VERSION = 1
FIXTURE_PHASE = 1
FIXTURE_GENERATED_AT = "2026-07-26T00:00:00+00:00"
# The producer version recorded when the pack was frozen. The exporter now ships
# inside akms; this stays fixed so the pack bytes do not move on every release.
GENERATING_REPO2MD_VERSION = "0.2.0"


def _files(root: Path) -> dict[Path, bytes]:
    """Return every regular file below ``root`` keyed by its relative path."""

    return {
        path.relative_to(root): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _manifest(*, mirror_count: int) -> bytes:
    """Build the versioned metadata AKMS consumers use to pin this pack."""

    data = {
        "akms_schema_version": "v2",
        "export_schema_version": 1,
        "fixture_contract_version": FIXTURE_CONTRACT_VERSION,
        "generated_at": FIXTURE_GENERATED_AT,
        "generating_repo2md_version": GENERATING_REPO2MD_VERSION,
        "mirror_count": mirror_count,
        "phase": FIXTURE_PHASE,
    }
    return (json.dumps(data, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _generate_snapshot(workspace: Path) -> dict[Path, bytes]:
    """Render the complete fixture snapshot in an isolated temporary directory."""

    generated = workspace / "expected"
    result = export_akms(
        repo_root=SOURCE_REPOSITORY,
        output_root=generated,
        phase=FIXTURE_PHASE,
        generated_at=FIXTURE_GENERATED_AT,
        changed_only=False,
        prune=False,
    )
    if result.errors or result.skipped or result.removed:
        raise RuntimeError(f"fixture export did not fully succeed: {result.to_json()}")

    snapshot = {
        Path("expected") / path: content for path, content in _files(generated).items()
    }
    snapshot[RESULT_PATH.relative_to(FIXTURE_ROOT)] = (result.to_json() + "\n").encode(
        "utf-8"
    )
    snapshot[MANIFEST_PATH.relative_to(FIXTURE_ROOT)] = _manifest(
        mirror_count=len(result.written)
    )
    return snapshot


def _committed_snapshot() -> dict[Path, bytes]:
    """Return only the generated artifacts, excluding source inputs and old goldens."""

    committed = {
        Path("expected") / path: content
        for path, content in _files(EXPECTED_ROOT).items()
    }
    for path in (RESULT_PATH, MANIFEST_PATH):
        if path.is_file():
            committed[path.relative_to(FIXTURE_ROOT)] = path.read_bytes()
    return committed


def _describe_drift(
    expected: dict[Path, bytes], actual: dict[Path, bytes]
) -> list[str]:
    """Describe missing, stale, and byte-different generated artifact paths."""

    messages: list[str] = []
    for path in sorted(expected.keys() - actual.keys()):
        messages.append(f"missing committed artifact: {path.as_posix()}")
    for path in sorted(actual.keys() - expected.keys()):
        messages.append(f"unexpected committed artifact: {path.as_posix()}")
    for path in sorted(expected.keys() & actual.keys()):
        if expected[path] != actual[path]:
            messages.append(f"byte drift: {path.as_posix()}")
    return messages


def _write_snapshot(snapshot: dict[Path, bytes]) -> None:
    """Replace only producer-owned fixture artifacts with a generated snapshot."""

    if EXPECTED_ROOT.exists():
        shutil.rmtree(EXPECTED_ROOT)
    for path, content in snapshot.items():
        target = FIXTURE_ROOT / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when committed artifacts differ from regeneration",
    )
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory(prefix="repo-wiki-akms-fixtures-") as temporary:
        expected = _generate_snapshot(Path(temporary))
    actual = _committed_snapshot()
    drift = _describe_drift(expected, actual)
    if args.check:
        if drift:
            print("AKMS fixture drift detected:", file=sys.stderr)
            print("\n".join(f"- {message}" for message in drift), file=sys.stderr)
            return 1
        print("AKMS export fixtures are byte-stable.")
        return 0

    _write_snapshot(expected)
    print(f"Regenerated {len(expected)} AKMS fixture artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
