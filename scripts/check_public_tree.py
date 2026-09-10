#!/usr/bin/env python3
"""Reject private-development residue, obvious secrets, and local paths."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def publishable_paths() -> set[Path] | None:
    """Every path git would publish: tracked, plus untracked-but-not-ignored.

    The audit is about what reaches the public repository, so asking git is
    both more accurate and quieter than walking the filesystem. A gitignored
    file cannot be published — flagging one is a false positive, and a gate
    that cries wolf locally is one people learn to skip. Untracked files that
    are *not* ignored stay in scope: they are one `git add .` from shipping.

    Returns None when git cannot answer — no repository, no git on PATH, an
    extracted tarball — so the caller falls back to walking the tree, which is
    the conservative direction.
    """
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ],
            capture_output=True,
            check=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    names = result.stdout.decode("utf-8", "replace").split("\0")
    return {ROOT / name for name in names if name}


FORBIDDEN_TOP_LEVEL = {
    ".agents",
    ".claude",
    ".codex",
    ".orchestra",
    "AKMS",  # historical nested working area
    "Sources_Evals",
    "artifacts",
    "dev",
}

FORBIDDEN_NAME_FRAGMENTS = (
    "Handoff_Phase",
    "SUPERSEDED",
    "session-state",
    "session-log",
    "tasks-tracker",
    "migrate-to-codex-report",
)

TEXT_ROOTS = (
    "packages",
    "docs",
    "examples",
    "tests",
)

TEXT_FILES_AT_ROOT = (
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "SUPPORT.md",
    "CODE_OF_CONDUCT.md",
    "CHANGELOG.md",
    "CITATION.cff",
    "pyproject.toml",
    "mkdocs.yml",
)

HISTORY_PATTERNS = {
    # Any repository under the private account, not just SOSOVSKI/AKMS. The
    # narrower pattern would have waved through `SOSOVSKI/MechDSL`,
    # `SOSOVSKI/ConstKit` and `SOSOVSKI/SymbolicFemWorkbench`, which are named
    # in compmech-reference-pack's shipped source packs and are not public.
    "private repository reference": re.compile(r"\bSOSOVSKI/[\w.-]+", re.I),
    "plan or task identifier": re.compile(
        r"\b(?:ADM|AO|CAR)-\d+\b|"
        r"\bTask\s+P\d+(?:[-_]\d+)+\b|"
        r"\bPlan\s+\d+\b|"
        r"\bHandoff_Phase\b",
        re.I,
    ),
    "absolute macOS path": re.compile(r"/Users/[^/\s]+/"),
    "absolute Linux home path": re.compile(r"/home/[^/\s]+/"),
    "absolute Windows user path": re.compile(r"[A-Za-z]:\\Users\\[^\\\s]+\\"),
}

SECRET_PATTERNS = {
    "GitHub classic token": re.compile(r"\bghp_[A-Za-z0-9]{30,}\b"),
    "GitHub fine-grained token": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "Devin-style key": re.compile(r"\bcog_[A-Za-z0-9_-]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}

SKIP_DIRS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "dist",
    "site",
}

BINARY_SUFFIXES = {
    ".7z",
    ".bz2",
    ".class",
    ".dmg",
    ".docx",
    ".gz",
    ".ico",
    ".jar",
    ".jpeg",
    ".jpg",
    ".lock",
    ".pdf",
    ".png",
    ".pyc",
    ".so",
    ".tar",
    ".tgz",
    ".webp",
    ".whl",
    ".xlsx",
    ".zip",
}


def iter_public_text_files(publishable: set[Path] | None) -> list[Path]:
    paths: list[Path] = []
    for rel in TEXT_FILES_AT_ROOT:
        path = ROOT / rel
        if path.is_file():
            paths.append(path)

    for rel in TEXT_ROOTS:
        base = ROOT / rel
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if publishable is not None and path not in publishable:
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.suffix.lower() in BINARY_SUFFIXES:
                continue
            paths.append(path)
    return sorted(set(paths))


def scan_text(path: Path, patterns: dict[str, re.Pattern[str]]) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    findings: list[str] = []
    for label, pattern in patterns.items():
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append(f"{path.relative_to(ROOT)}:{line}: {label}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--security-only",
        action="store_true",
        help="Scan only for secrets and absolute local paths.",
    )
    args = parser.parse_args()

    findings: list[str] = []
    publishable = publishable_paths()

    if not args.security_only:
        for name in sorted(FORBIDDEN_TOP_LEVEL):
            candidate = ROOT / name
            if not candidate.exists():
                continue
            # A gitignored working directory (`.claude/`, `.orchestra/`) is not
            # part of the public tree, so its presence on disk is not a finding.
            if publishable is not None and not any(
                path == candidate or candidate in path.parents for path in publishable
            ):
                continue
            findings.append(f"{name}: forbidden top-level public path")

        for path in ROOT.rglob("*"):
            if publishable is not None and path not in publishable:
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if any(
                fragment.lower() in path.name.lower()
                for fragment in FORBIDDEN_NAME_FRAGMENTS
            ):
                findings.append(
                    f"{path.relative_to(ROOT)}: private-development filename"
                )

    patterns = dict(SECRET_PATTERNS)
    patterns.update(
        {
            key: value
            for key, value in HISTORY_PATTERNS.items()
            if args.security_only and "path" in key
        }
    )
    if not args.security_only:
        patterns.update(HISTORY_PATTERNS)

    for path in iter_public_text_files(publishable):
        findings.extend(scan_text(path, patterns))

    if findings:
        print("Public-tree audit failed:", file=sys.stderr)
        for finding in sorted(set(findings)):
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print("Public-tree audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
