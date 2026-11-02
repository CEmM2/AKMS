"""Line-range source reads through read_source."""

from __future__ import annotations

from pathlib import Path

import pytest

from akms.repo_wiki.models import SourceSpan
from akms.repo_wiki.paths import read_source


def test_happy_path_returns_exact_slice(tmp_path: Path) -> None:
    """read_source returns the correct 1-indexed inclusive slice."""
    src = tmp_path / "example.py"
    src.write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")

    span = SourceSpan(path="example.py", start_line=2, end_line=4)
    result = read_source(span, tmp_path)

    assert result == "line2\nline3\nline4"


def test_happy_path_single_line(tmp_path: Path) -> None:
    """A span covering a single line returns just that line."""
    src = tmp_path / "single.py"
    src.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    span = SourceSpan(path="single.py", start_line=2, end_line=2)
    result = read_source(span, tmp_path)

    assert result == "beta"


def test_happy_path_accepts_str_repo_root(tmp_path: Path) -> None:
    """repo_root may be passed as a str; coercion is transparent."""
    src = tmp_path / "coerce.py"
    src.write_text("a\nb\nc\n", encoding="utf-8")

    span = SourceSpan(path="coerce.py", start_line=1, end_line=3)
    result = read_source(span, str(tmp_path))

    assert result == "a\nb\nc"


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    """Helper raises FileNotFoundError naming the resolved path."""
    span = SourceSpan(path="does_not_exist.py", start_line=1, end_line=5)

    with pytest.raises(FileNotFoundError) as exc_info:
        read_source(span, tmp_path)

    assert "does_not_exist.py" in str(exc_info.value)


def test_out_of_range_raises_value_error(tmp_path: Path) -> None:
    """Helper raises ValueError when end_line exceeds file length."""
    src = tmp_path / "short.py"
    src.write_text("only_line\n", encoding="utf-8")  # 1 line

    span = SourceSpan(path="short.py", start_line=1, end_line=99)

    with pytest.raises(ValueError) as exc_info:
        read_source(span, tmp_path)

    msg = str(exc_info.value)
    assert "99" in msg  # the requested end_line
    assert "1" in msg  # the actual line count


def test_subdirectory_path_resolves(tmp_path: Path) -> None:
    """span.path is joined with repo_root for nested files."""
    nested = tmp_path / "sub" / "nested"
    nested.mkdir(parents=True)
    (nested / "file.py").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    span = SourceSpan(path="sub/nested/file.py", start_line=2, end_line=3)
    assert read_source(span, tmp_path) == "beta\ngamma"


def test_start_line_below_one_raises(tmp_path: Path) -> None:
    """start_line < 1 must raise rather than silently misreading the slice."""
    src = tmp_path / "file.py"
    src.write_text("a\nb\n", encoding="utf-8")
    span = SourceSpan(path="file.py", start_line=0, end_line=2)
    with pytest.raises(ValueError):
        read_source(span, tmp_path)


def test_start_line_after_end_line_raises(tmp_path: Path) -> None:
    """Inverted span (start > end) must raise."""
    src = tmp_path / "file.py"
    src.write_text("a\nb\n", encoding="utf-8")
    span = SourceSpan(path="file.py", start_line=5, end_line=2)
    with pytest.raises(ValueError):
        read_source(span, tmp_path)
