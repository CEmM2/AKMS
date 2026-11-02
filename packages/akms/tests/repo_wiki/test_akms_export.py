from __future__ import annotations

import json
from pathlib import Path

import pytest

from akms.repo_wiki.export.akms import (
    build_mirror_document,
    normalize_source_path,
    render_mirror_markdown,
    write_mirror_document,
)
from akms.repo_wiki.hashing import sha256_text
from akms.repo_wiki.models import Language, ParsedModule, SourceFile, SourceSpan, Symbol


GENERATED_AT = "2026-03-07T12:00:00+00:00"


@pytest.mark.unit
def test_normalize_source_path_rejects_drive_qualified_windows_paths():
    """Drive-qualified Windows paths must not be treated as repo-relative."""

    assert normalize_source_path("src/pkg/mod.py") == "src/pkg/mod.py"
    assert normalize_source_path(r"src\pkg\mod.py") == "src/pkg/mod.py"

    for absolute in (
        "C:/project/file.py",
        r"C:\project\file.py",
        "c:/project/file.py",
        "C:foo.py",
        "/abs/file.py",
        "//server/share/file.py",
        "../escape.py",
        "pkg/../escape.py",
    ):
        with pytest.raises(ValueError, match="absolute|traverse|repository-relative"):
            normalize_source_path(absolute)


def _parsed(source_path: str, source_text: str, symbols: list[Symbol] | None = None):
    source_file = SourceFile(
        path=source_path,
        abs_path=f"/not-read/{source_path}",
        language="python",
        size_bytes=len(source_text.encode("utf-8")),
        content_hash=sha256_text(source_text),
    )
    return ParsedModule(source_file, "fixture", None, [], symbols or [])


def _parse_json_yaml_frontmatter(markdown: str) -> dict[str, object]:
    frontmatter = markdown[4:].partition("---\n")[0]
    return {
        key: json.loads(value)
        for line in frontmatter.splitlines()
        for key, separator, value in [line.partition(": ")]
        if separator
    }


@pytest.mark.unit
def test_write_returns_record_whose_content_ref_is_the_written_file(tmp_path: Path):
    source = "# no symbols are still mirrored\n"
    parsed = _parsed("src/empty.py", source)

    record = write_mirror_document(
        parsed=parsed,
        source_text=source,
        output_root=tmp_path,
        phase=2,
        generated_at=GENERATED_AT,
    )

    written_path = tmp_path / record.generated_path
    assert written_path == tmp_path / "knowledge" / record.content_ref
    assert written_path.is_file()
    assert written_path.read_text(encoding="utf-8").count(source) == 1
    assert list(written_path.parent.glob(f".{written_path.name}.*.tmp")) == []


@pytest.mark.unit
def test_source_backticks_select_a_longer_markdown_fence():
    source = 'TEXT = "```"\n'
    parsed = _parsed("src/fences.py", source)
    document = build_mirror_document(
        source_path=parsed.source_file.path,
        language=parsed.source_file.language,
        source_hash=parsed.source_file.content_hash,
        phase=2,
        generated_at=GENERATED_AT,
    )

    markdown = render_mirror_markdown(parsed, source, document)

    assert "````python\n" in markdown
    assert markdown.endswith(source + "````\n")
    assert markdown.count(source) == 1


@pytest.mark.unit
def test_symbol_from_another_file_is_rejected_before_rendering():
    source = "def local():\n    pass\n"
    foreign = Symbol(
        symbol_id="python:src/other.py:foreign",
        path="src/other.py",
        module="src.other",
        name="foreign",
        qualname="foreign",
        kind="function",
        parent_id=None,
        start_line=1,
        end_line=2,
        signature="def foreign()",
        docstring=None,
        span=SourceSpan("src/other.py", 1, 2),
        language=Language.PYTHON,
    )
    parsed = _parsed("src/local.py", source, [foreign])
    document = build_mirror_document(
        source_path=parsed.source_file.path,
        language=parsed.source_file.language,
        source_hash=parsed.source_file.content_hash,
        phase=2,
        generated_at=GENERATED_AT,
    )

    with pytest.raises(ValueError, match="belongs to"):
        render_mirror_markdown(parsed, source, document)


@pytest.mark.unit
def test_source_text_must_match_the_recorded_hash():
    source = "VALUE = 1\n"
    parsed = _parsed("src/value.py", source)
    document = build_mirror_document(
        source_path=parsed.source_file.path,
        language=parsed.source_file.language,
        source_hash=parsed.source_file.content_hash,
        phase=2,
        generated_at=GENERATED_AT,
    )

    with pytest.raises(ValueError, match="source_text"):
        render_mirror_markdown(parsed, "VALUE = 2\n", document)


@pytest.mark.unit
def test_source_path_is_markdown_safe_and_control_characters_are_visible():
    source = "VALUE = 1\n"
    source_path = "src/tick`line\nbreak\u0085.py"
    parsed = _parsed(source_path, source)
    document = build_mirror_document(
        source_path=source_path,
        language=parsed.source_file.language,
        source_hash=parsed.source_file.content_hash,
        phase=2,
        generated_at=GENERATED_AT,
    )

    markdown = render_mirror_markdown(parsed, source, document)

    assert "# <code>src/tick`line\\nbreak\\u0085.py</code>" in markdown
    assert "# `src/tick`line" not in markdown


@pytest.mark.unit
def test_frontmatter_ascii_escapes_yaml_line_break_characters():
    source = "VALUE = 1\n"
    source_path = "src/a\u0085b.py"
    parsed = _parsed(source_path, source)
    document = build_mirror_document(
        source_path=source_path,
        language=parsed.source_file.language,
        source_hash=parsed.source_file.content_hash,
        phase=2,
        generated_at=GENERATED_AT,
    )

    markdown = render_mirror_markdown(parsed, source, document)
    metadata = _parse_json_yaml_frontmatter(markdown)
    frontmatter = markdown[4:].partition("---\n")[0]

    assert "\\u0085" in markdown
    assert "\u0085" not in frontmatter
    assert metadata["source_file"] == source_path
    assert metadata["content_ref"] == document.content_ref
