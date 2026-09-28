#!/usr/bin/env python3
"""Check that public packages, the release tag, and changelog agree."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PACKAGE_FILES = {
    "akms": ROOT / "packages" / "akms" / "pyproject.toml",
    "akms-learn": ROOT / "packages" / "akms_learn" / "pyproject.toml",
    "akms-nodes-gen": ROOT / "packages" / "akms_nodes_gen" / "pyproject.toml",
    "akms-failure-memory": ROOT / "packages" / "akms_failure_memory" / "pyproject.toml",
    "compmech-reference-pack": (
        ROOT / "packages" / "compmech_reference_pack" / "pyproject.toml"
    ),
}

# Packages whose `__version__` literal is meant to mirror the distribution
# version: `akms.__version__` feeds failure-memory toolchain fingerprints and
# `akms --version`; `akms_failure_memory.__version__` backs
# `failure-memory --version`. 0.3.1 bumped the pyproject files and left both
# literals at 0.3.0, so this check exists to make that drift a release error.
# `compmech_reference_pack.__version__` is deliberately absent: it is the
# domain-pack contract version reported to akms-learn, not the wheel version.
INIT_FILES = {
    "akms": ROOT / "packages" / "akms" / "src" / "akms" / "__init__.py",
    "akms-failure-memory": (
        ROOT
        / "packages"
        / "akms_failure_memory"
        / "src"
        / "akms_failure_memory"
        / "__init__.py"
    ),
}

_DUNDER_VERSION = re.compile(r'^__version__\s*=\s*"([^"]+)"', re.MULTILINE)


def read_version(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", help="Expected tag, for example v0.1.0")
    args = parser.parse_args()

    errors: list[str] = []
    versions: dict[str, str] = {}

    for name, path in PACKAGE_FILES.items():
        try:
            versions[name] = read_version(path)
        except (FileNotFoundError, KeyError, tomllib.TOMLDecodeError) as exc:
            errors.append(f"{name}: unable to read version from {path}: {exc}")

    for name, path in INIT_FILES.items():
        if name not in versions:
            continue
        if not path.exists():
            errors.append(f"{name}: {path} is missing")
            continue
        match = _DUNDER_VERSION.search(path.read_text(encoding="utf-8"))
        if not match:
            errors.append(f'{name}: no `__version__ = "..."` literal in {path}')
        elif match.group(1) != versions[name]:
            errors.append(
                f"{name}: __version__ {match.group(1)!r} in {path.name} does not "
                f"match pyproject version {versions[name]!r}"
            )

    unique_versions = sorted(set(versions.values()))
    if len(unique_versions) > 1:
        errors.append(f"package versions differ: {versions}")

    expected = unique_versions[0] if len(unique_versions) == 1 else None

    if args.tag and expected:
        normalized_tag = args.tag.removeprefix("v")
        if normalized_tag != expected:
            errors.append(
                f"tag {args.tag!r} does not match package version {expected!r}"
            )

    changelog = ROOT / "CHANGELOG.md"
    if expected and changelog.exists():
        text = changelog.read_text(encoding="utf-8")
        heading = re.compile(
            rf"^##\s+\[?{re.escape(expected)}\]?\b",
            re.MULTILINE,
        )
        if not heading.search(text):
            errors.append(f"CHANGELOG.md has no release heading for version {expected}")
    elif expected:
        errors.append("CHANGELOG.md is missing")

    if errors:
        print("Version audit failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"Version audit passed: {expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
