"""AKMS mirror rendering against committed golden fixtures, and atomic output writes."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import akms.repo_wiki.export.akms as akms_export
from akms.repo_wiki.export.akms import (
    CODE_MIRROR_FRONTMATTER_FIELDS,
    build_mirror_document,
    render_mirror_markdown,
    write_mirror_document,
)
from akms.repo_wiki.hashing import sha256_text
from akms.repo_wiki.models import Language, ParsedModule, SourceFile, SourceSpan, Symbol
from akms.repo_wiki.simple_yaml import load_yaml

REPO_ROOT = Path(__file__).resolve().parent
FIXTURE_CHECK = REPO_ROOT / "regenerate_akms_export_fixtures.py"
CI_WITHOUT_DOXYGEN = (
    os.environ.get("CI", "").strip().lower() in {"1", "true", "yes"}
    and shutil.which("doxygen") is None
)
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "akms_export"
GENERATED_AT = "2026-03-07T12:00:00+00:00"

PYTHON_SOURCE = '''"""Vector helpers."""

class Vector(BaseVector):
    """A tiny vector."""

    def scale(self, factor: float) -> float:
        """Scale one value."""
        return helper(factor)
'''

CPP_SOURCE = """#include <cmath>

struct Vec {
    double norm() const { return std::sqrt(4.0); }
};
"""


def _parsed_python(
    source: str = PYTHON_SOURCE, source_path: str = "src/vector.py"
) -> ParsedModule:
    source_file = SourceFile(
        path=source_path,
        abs_path=f"/not-read/{source_path}",
        language="python",
        size_bytes=len(source.encode("utf-8")),
        content_hash=sha256_text(source),
    )
    class_symbol = Symbol(
        symbol_id=f"python:{source_path}:Vector",
        path=source_path,
        module="src.vector",
        name="Vector",
        qualname="Vector",
        kind="class",
        parent_id=None,
        start_line=3,
        end_line=8,
        signature="class Vector(BaseVector)",
        docstring="A tiny vector.",
        span=SourceSpan(source_path, 3, 8),
        language=Language.PYTHON,
        bases=["BaseVector"],
    )
    method_symbol = Symbol(
        symbol_id=f"python:{source_path}:Vector.scale",
        path=source_path,
        module="src.vector",
        name="scale",
        qualname="Vector.scale",
        kind="method",
        parent_id=class_symbol.symbol_id,
        start_line=6,
        end_line=8,
        signature="def scale(self, factor: float) -> float",
        docstring="Scale one value.",
        span=SourceSpan(source_path, 6, 8),
        language=Language.PYTHON,
        calls=["helper"],
    )
    return ParsedModule(
        source_file=source_file,
        module="src.vector",
        docstring="Vector helpers.",
        imports=[],
        symbols=[method_symbol, class_symbol],
    )


def _parsed_cpp() -> ParsedModule:
    source_path = "src/vector.cpp"
    source_file = SourceFile(
        path=source_path,
        abs_path=f"/not-read/{source_path}",
        language="cpp",
        size_bytes=len(CPP_SOURCE.encode("utf-8")),
        content_hash=sha256_text(CPP_SOURCE),
    )
    symbol = Symbol(
        symbol_id="cpp:src/vector.cpp:Vec",
        path=source_path,
        module="src.vector",
        name="Vec",
        qualname="Vec",
        kind="class",
        parent_id=None,
        start_line=3,
        end_line=5,
        signature="struct Vec",
        docstring="Small vector type.",
        span=SourceSpan(source_path, 3, 5),
        language=Language.CPP,
        calls=["std::sqrt"],
    )
    return ParsedModule(source_file, "src.vector", None, ["cmath"], [symbol])


def _document(parsed: ParsedModule):
    return build_mirror_document(
        source_path=parsed.source_file.path,
        language=parsed.source_file.language,
        source_hash=parsed.source_file.content_hash,
        phase=2,
        generated_at=GENERATED_AT,
    )


def _split_frontmatter(markdown: str) -> tuple[dict[str, object], str]:
    assert markdown.startswith("---\n")
    frontmatter, separator, body = markdown[4:].partition("---\n")
    assert separator
    return load_yaml(frontmatter), body


def test_golden_frontmatter_and_body_rendering():
    """Golden mirrors contain only frozen AKMS v2 frontmatter and searchable symbol metadata."""
    python = _parsed_python()
    cpp = _parsed_cpp()
    rendered = {
        "python_mirror.md": render_mirror_markdown(
            python, PYTHON_SOURCE, _document(python)
        ),
        "cpp_mirror.md": render_mirror_markdown(cpp, CPP_SOURCE, _document(cpp)),
    }

    for fixture_name, markdown in rendered.items():
        assert markdown == (FIXTURE_DIR / fixture_name).read_text(encoding="utf-8")
        metadata, body = _split_frontmatter(markdown)
        assert set(metadata) == set(CODE_MIRROR_FRONTMATTER_FIELDS)
        assert '"symbol_id"' in body
        assert '"kind"' in body
        assert '"start_line"' in body
        assert '"end_line"' in body
        assert '"signature"' in body
        assert '"docstring"' in body
        assert '"calls"' in body
        assert '"bases"' in body
        assert '"parent_id"' in body


def test_rendered_frontmatter_round_trips_through_yaml():
    """Rendered YAML round-trips while preserving valid source paths and content_ref values."""
    source_path = "- module\u0085.py"
    parsed = _parsed_python("VALUE = 'yaml-safe'\n", source_path)
    document = _document(parsed)

    metadata, _ = _split_frontmatter(
        render_mirror_markdown(parsed, "VALUE = 'yaml-safe'\n", document)
    )

    assert metadata["source_file"] == source_path
    assert metadata["content_ref"] == document.content_ref
    assert metadata["title"] == f"Code Mirror: {source_path}"
    assert metadata["generated_at"] == GENERATED_AT
    assert metadata["auto_update"] is True
    assert metadata["generated_by_phase"] == 2
    assert metadata["akms_schema"] == "v2"


def test_complete_source_appears_exactly_once():
    """The complete source appears exactly once without duplication by symbol metadata."""
    parsed = _parsed_python()

    markdown = render_mirror_markdown(parsed, PYTHON_SOURCE, _document(parsed))

    assert markdown.count(PYTHON_SOURCE) == 1
    assert markdown.endswith(PYTHON_SOURCE + "```\n")
    assert markdown.index(class_symbol := parsed.symbols[1].symbol_id) < markdown.index(
        method_symbol := parsed.symbols[0].symbol_id
    )
    assert class_symbol != method_symbol


def test_atomic_write_failure_preserves_prior_output(tmp_path, monkeypatch):
    """An injected render or replace failure leaves the previously written mirror intact."""
    parsed = _parsed_python()
    document = _document(parsed)
    target = tmp_path / document.generated_path
    target.parent.mkdir(parents=True)
    target.write_text("prior mirror\n", encoding="utf-8")

    original_render = akms_export.render_mirror_markdown

    def fail_render(*_args, **_kwargs):
        raise RuntimeError("injected render failure")

    monkeypatch.setattr(akms_export, "render_mirror_markdown", fail_render)
    with pytest.raises(RuntimeError, match="injected render failure"):
        write_mirror_document(
            parsed=parsed,
            source_text=PYTHON_SOURCE,
            output_root=tmp_path,
            phase=2,
            generated_at=GENERATED_AT,
        )
    assert target.read_text(encoding="utf-8") == "prior mirror\n"

    monkeypatch.setattr(akms_export, "render_mirror_markdown", original_render)

    def fail_replace(_source, _target):
        raise OSError("injected replace failure")

    monkeypatch.setattr(akms_export.os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected replace failure"):
        write_mirror_document(
            parsed=parsed,
            source_text=PYTHON_SOURCE,
            output_root=tmp_path,
            phase=2,
            generated_at=GENERATED_AT,
        )

    assert target.read_text(encoding="utf-8") == "prior mirror\n"
    assert list(target.parent.glob(f".{target.name}.*.tmp")) == []


@pytest.mark.skipif(CI_WITHOUT_DOXYGEN, reason="fixture regeneration requires Doxygen")
def test_committed_fixtures_are_byte_stable_after_regeneration():
    completed = subprocess.run(
        [sys.executable, str(FIXTURE_CHECK), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "byte-stable" in completed.stdout
