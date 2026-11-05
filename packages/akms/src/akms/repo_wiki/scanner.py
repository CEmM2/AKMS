"""Repository scanner."""

from __future__ import annotations

import fnmatch
import json
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from akms.repo_wiki.config import PROTECTED_NAME_PATTERNS, effective_excludes
from akms.repo_wiki.hashing import sha256_file
from akms.repo_wiki.models import SkippedFile, SourceFile
from akms.repo_wiki.paths import repo_relative

LANGUAGE_BY_SUFFIX = {
    ".py": "python",
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".rs": "rust",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".h": "cpp",
    ".hxx": "cpp",
    ".jl": "julia",
}

# Extra include globs, added only for enabled languages (keeps new extensions opt-in).
LANGUAGE_INCLUDE_GLOBS = {
    "rust": ["**/*.rs"],
    "cpp": [
        "**/*.cpp",
        "**/*.cc",
        "**/*.cxx",
        "**/*.hpp",
        "**/*.hh",
        "**/*.h",
        "**/*.hxx",
    ],
    "julia": ["**/*.jl"],
}


def _enabled_language_globs(config: dict[str, object]) -> list[str]:
    """Include globs for the tree-sitter languages that are enabled in config."""
    languages = config.get("languages")
    if not isinstance(languages, dict):
        return []
    globs: list[str] = []
    for language, patterns in LANGUAGE_INCLUDE_GLOBS.items():
        entry = languages.get(language)
        enabled = (
            entry.get("enabled", False) if isinstance(entry, dict) else bool(entry)
        )
        if enabled:
            globs.extend(patterns)
    return globs


def scan_repository(
    repo_root: Path, config: dict[str, object]
) -> tuple[list[SourceFile], list[SkippedFile]]:
    root = repo_root.resolve()
    scanner = config["scanner"] if isinstance(config["scanner"], dict) else {}
    include = [str(v) for v in scanner.get("include", [])]
    # An empty include set already accepts everything; only extend a non-empty one.
    if include:
        include = include + _enabled_language_globs(config)
    exclude = effective_excludes(config)
    max_size = int(scanner.get("max_file_size_kb", 512)) * 1024
    gitignore_patterns = (
        read_gitignore(root) if scanner.get("respect_gitignore", True) else []
    )

    sources: list[SourceFile] = []
    skipped: list[SkippedFile] = []
    for path in iter_candidate_files(root, exclude + gitignore_patterns, skipped):
        rel = repo_relative(path, root)
        if is_excluded(rel, exclude, gitignore_patterns):
            skipped.append(
                SkippedFile(rel, "excluded", "matched exclude or gitignore pattern")
            )
            continue
        if include and not matches_any(rel, include):
            skipped.append(
                SkippedFile(rel, "not_included", "did not match include patterns")
            )
            continue
        size = path.stat().st_size
        if size > max_size:
            skipped.append(SkippedFile(rel, "too_large", f"{size} > {max_size} bytes"))
            continue
        if is_binary(path):
            skipped.append(SkippedFile(rel, "binary", "contains binary data"))
            continue
        language = LANGUAGE_BY_SUFFIX.get(path.suffix.lower(), "text")
        sources.append(SourceFile(rel, str(path), language, size, sha256_file(path)))
    return sources, skipped


def iter_candidate_files(
    root: Path, prune_patterns: list[str], skipped: list[SkippedFile]
) -> Iterator[Path]:
    pending = [root]
    while pending:
        current = pending.pop()
        dirs: list[Path] = []
        for path in sorted(current.iterdir(), key=lambda item: item.name):
            rel = repo_relative(path, root)
            # Symlinks are never followed: a link may leave the repository, loop, or
            # duplicate a file that is already scanned under its real path.
            if path.is_symlink():
                if matches_any_dir(rel, prune_patterns):
                    skipped.append(
                        SkippedFile(
                            rel, "excluded", "matched exclude or gitignore pattern"
                        )
                    )
                else:
                    skipped.append(
                        SkippedFile(rel, "symlink", "symbolic links are not followed")
                    )
                continue
            if path.is_dir():
                if matches_any_dir(rel, prune_patterns):
                    skipped.append(
                        SkippedFile(rel, "excluded", "pruned excluded directory")
                    )
                else:
                    dirs.append(path)
            elif path.is_file():
                yield path
        pending.extend(reversed(dirs))


def read_gitignore(root: Path) -> list[str]:
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        return []
    patterns: list[str] = []
    for raw in gitignore.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        patterns.append(line[1:] if line.startswith("/") else line)
    return patterns


def matches_any(path: str, patterns: list[str]) -> bool:
    return any(matches_pattern(path, pattern) for pattern in patterns)


def matches_protected_name(path: str) -> bool:
    """True when the file name, at any depth, matches a tool-state or secret pattern."""
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(name, pattern) for pattern in PROTECTED_NAME_PATTERNS)


def is_excluded(
    path: str, exclude: list[str], gitignore_patterns: list[str] | None = None
) -> bool:
    """The scanner's exclusion test: *exclude* patterns, protected names, gitignore."""
    return (
        matches_any(path, exclude)
        or matches_protected_name(path)
        or matches_any(path, gitignore_patterns or [])
    )


def matches_any_dir(path: str, patterns: list[str]) -> bool:
    return matches_any(path, patterns) or matches_any(f"{path}/__dir__", patterns)


def matches_pattern(path: str, pattern: str) -> bool:
    normalized = pattern.rstrip("/")
    if fnmatch.fnmatch(path, normalized) or fnmatch.fnmatch(path, f"{normalized}/**"):
        return True
    if "/" not in normalized and any(part == normalized for part in Path(path).parts):
        return True
    if normalized.startswith("*.") and fnmatch.fnmatch(Path(path).name, normalized):
        return True
    return False


def is_binary(path: Path) -> bool:
    data = path.read_bytes()[:8192]
    if b"\x00" in data:
        return True
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def scan_to_json(
    sources: list[SourceFile],
    skipped: list[SkippedFile],
    *,
    exclude: list[str] | None = None,
) -> str:
    """Serialize a scan; ``exclude`` adds the effective exclude patterns applied."""
    payload: dict[str, object] = {
        "files": [source.to_dict() for source in sources],
        "skipped": [item.to_dict() for item in skipped],
        "skipped_by_reason": dict(
            sorted(Counter(item.reason for item in skipped).items())
        ),
    }
    if exclude is not None:
        payload["exclude"] = list(exclude)
    return json.dumps(payload, indent=2, sort_keys=True)
