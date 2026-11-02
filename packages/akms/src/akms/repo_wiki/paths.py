"""Path normalization utilities."""

from __future__ import annotations

from pathlib import Path

from akms.repo_wiki.models import SourceSpan


def read_source(span: SourceSpan, repo_root: Path | str) -> str:
    """Return lines ``start_line..end_line`` (1-indexed, inclusive) of ``span.path``.

    Raises FileNotFoundError, or ValueError for an inverted, sub-one or out-of-range span.
    """
    if span.start_line < 1:
        raise ValueError(
            f"Span start_line must be >= 1 (got {span.start_line}, span={span!r})"
        )
    if span.start_line > span.end_line:
        raise ValueError(
            f"Span start_line {span.start_line} exceeds end_line {span.end_line} "
            f"(span={span!r})"
        )
    root = Path(repo_root)
    resolved = root / span.path
    if not resolved.is_file():
        raise FileNotFoundError(f"Source file not found: {resolved!s} (span={span!r})")
    lines = resolved.read_text(encoding="utf-8").splitlines()
    actual = len(lines)
    if span.end_line > actual:
        raise ValueError(
            f"Span end_line {span.end_line} exceeds file length {actual} "
            f"for {resolved!s} (span={span!r})"
        )
    return "\n".join(lines[span.start_line - 1 : span.end_line])


def repo_relative(path: Path, root: Path) -> str:
    """Return ``path`` relative to ``root`` as POSIX text.

    Computed lexically when ``path`` is spelled under ``root``, so a symlink keeps its own
    name and one pointing outside the repository does not raise. Other paths are resolved.
    """
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.resolve().relative_to(root.resolve()).as_posix()


def safe_doc_name(value: str) -> str:
    cleaned = value.replace("/", ".").replace("\\", ".")
    return "".join(ch if ch.isalnum() or ch in "._-@" else "_" for ch in cleaned)


def module_name_from_path(path: str) -> str:
    without_suffix = path.rsplit(".", 1)[0] if "." in Path(path).name else path
    parts = Path(without_suffix).parts
    return ".".join(part for part in parts if part not in {"__init__"})


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
