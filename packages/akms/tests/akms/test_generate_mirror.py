"""Tests for generate_mirror.py — Phase 5: Code Mirror Generation + Drift Check.

Coverage:
- AST extraction: functions, async functions, classes, methods, docstrings
- Mirror file writing: content format, frontmatter fields
- Docstring drift detection: structural checks, LLM-based checks
- Git diff integration
- Full pipeline: generate_mirror() end-to-end
"""

from __future__ import annotations

import textwrap
from datetime import datetime
from pathlib import Path

import frontmatter as fm
import pytest

from akms.graph.generate_mirror import (
    check_docstring_drift_llm,
    check_docstring_drift_structural,
    extract_definitions,
    generate_mirror,
    write_mirror_file,
)


# ═══════════════════════════════════════════════════════════════════════
#  AST Extraction
# ═══════════════════════════════════════════════════════════════════════


class TestExtractDefinitions:
    """Tests for extract_definitions()."""

    def test_extracts_function(self):
        source = textwrap.dedent('''\
        def hello(name: str) -> str:
            """Say hello."""
            return f"Hello {name}"
        ''')
        defs = extract_definitions(source)
        assert len(defs) == 1
        assert defs[0]["name"] == "hello"
        assert defs[0]["type"] == "function"
        assert defs[0]["docstring"] == "Say hello."
        assert "name" in defs[0]["parameters"]
        assert defs[0]["return_annotation"] == "str"

    def test_extracts_async_function(self):
        source = textwrap.dedent('''\
        async def fetch(url: str) -> bytes:
            """Fetch URL."""
            pass
        ''')
        defs = extract_definitions(source)
        assert len(defs) == 1
        assert defs[0]["type"] == "async_function"

    def test_extracts_class(self):
        source = textwrap.dedent('''\
        class MyClass:
            """A class."""
            def method(self, x):
                """A method."""
                pass
        ''')
        defs = extract_definitions(source)
        assert len(defs) == 2
        assert defs[0]["name"] == "MyClass"
        assert defs[0]["type"] == "class"
        assert defs[1]["name"] == "MyClass.method"
        assert defs[1]["type"] == "function"

    def test_no_docstring(self):
        source = "def bare(x):\n    return x\n"
        defs = extract_definitions(source)
        assert len(defs) == 1
        assert defs[0]["docstring"] is None

    def test_decorators_extracted(self):
        source = textwrap.dedent('''\
        @staticmethod
        def static_fn():
            """Static."""
            pass
        ''')
        defs = extract_definitions(source)
        assert "staticmethod" in defs[0]["decorators"]

    def test_vararg_kwarg(self):
        source = "def fn(*args, **kwargs):\n    pass\n"
        defs = extract_definitions(source)
        assert "*args" in defs[0]["parameters"]
        assert "**kwargs" in defs[0]["parameters"]

    def test_syntax_error_returns_empty(self):
        defs = extract_definitions("def broken(")
        assert defs == []

    def test_empty_source(self):
        defs = extract_definitions("")
        assert defs == []

    def test_multiple_functions(self):
        source = textwrap.dedent("""\
        def a():
            pass

        def b():
            pass

        def c():
            pass
        """)
        defs = extract_definitions(source)
        assert len(defs) == 3
        assert [d["name"] for d in defs] == ["a", "b", "c"]


# ═══════════════════════════════════════════════════════════════════════
#  Mirror File Writing
# ═══════════════════════════════════════════════════════════════════════


class TestWriteMirrorFile:
    """Tests for write_mirror_file()."""

    def test_writes_mirror_file(self, tmp_repo):
        source = textwrap.dedent('''\
        def compute(x: int) -> int:
            """Compute something."""
            return x * 2
        ''')
        result = write_mirror_file(
            tmp_repo,
            "src/module.py",
            source,
            phase=1,
            generated_at=datetime(2026, 3, 7, 12, 0, 0),
        )

        assert result is not None
        assert result["source_file"] == "src/module.py"
        assert result["definitions_count"] == 1

        mirror_path = tmp_repo / "knowledge" / "code-mirror" / "src" / "module.md"
        assert mirror_path.exists()

    def test_frontmatter_fields(self, tmp_repo):
        source = 'def fn():\n    """Doc."""\n    pass\n'
        write_mirror_file(
            tmp_repo,
            "src/module.py",
            source,
            phase=2,
            generated_at=datetime(2026, 3, 7, 12, 0, 0),
        )

        mirror_path = tmp_repo / "knowledge" / "code-mirror" / "src" / "module.md"
        post = fm.load(str(mirror_path))

        assert post.metadata["id"] == "mirror-src-module"
        assert post.metadata["domain"] == "code-mirror"
        assert post.metadata["source"] == "generated"
        assert post.metadata["auto_update"] is True
        assert post.metadata["source_file"] == "src/module.py"
        assert post.metadata["generated_by_phase"] == 2
        assert post.metadata["confidence"] == 1.0
        assert post.metadata["status"] == "established"
        assert post.metadata["akms_schema"] == "v2"

    def test_content_format(self, tmp_repo):
        source = textwrap.dedent('''\
        def hello(name: str) -> str:
            """Say hello to someone."""
            return f"Hello {name}"
        ''')
        write_mirror_file(
            tmp_repo,
            "src/greet.py",
            source,
            phase=1,
            generated_at=datetime(2026, 3, 7, 12, 0, 0),
        )

        mirror_path = tmp_repo / "knowledge" / "code-mirror" / "src" / "greet.md"
        post = fm.load(str(mirror_path))
        content = post.content

        assert "# `src/greet.py`" in content
        assert "## `hello`" in content
        assert "Say hello to someone." in content
        assert "```python" in content

    def test_no_definitions_returns_none(self, tmp_repo):
        result = write_mirror_file(
            tmp_repo,
            "src/empty.py",
            "# just a comment\n",
            phase=1,
        )
        assert result is None

    def test_nested_directory_created(self, tmp_repo):
        source = 'def fn():\n    """Doc."""\n    pass\n'
        write_mirror_file(
            tmp_repo,
            "src/deep/nested/module.py",
            source,
            phase=1,
        )

        mirror_path = (
            tmp_repo
            / "knowledge"
            / "code-mirror"
            / "src"
            / "deep"
            / "nested"
            / "module.md"
        )
        assert mirror_path.exists()


# ═══════════════════════════════════════════════════════════════════════
#  Docstring Drift Detection — Structural
# ═══════════════════════════════════════════════════════════════════════


class TestDriftStructural:
    """Tests for check_docstring_drift_structural()."""

    def test_no_drift_clean_function(self):
        defs = [
            {
                "name": "compute",
                "type": "function",
                "docstring": "Compute the result for the given value x.",
                "parameters": ["self", "x"],
                "return_annotation": "int",
                "decorators": [],
            }
        ]
        warnings = check_docstring_drift_structural(defs)
        assert len(warnings) == 0

    def test_missing_param_in_docstring(self):
        defs = [
            {
                "name": "compute",
                "type": "function",
                "docstring": "Compute something.",
                "parameters": ["self", "alpha_factor", "beta_range"],
                "return_annotation": None,
                "decorators": [],
            }
        ]
        warnings = check_docstring_drift_structural(defs)
        # alpha_factor and beta_range not mentioned
        assert len(warnings) >= 1
        assert any("alpha_factor" in w["detail"] for w in warnings)

    def test_return_type_contradiction(self):
        defs = [
            {
                "name": "compute",
                "type": "function",
                "docstring": "Returns None when done.",
                "parameters": ["self"],
                "return_annotation": "int",
                "decorators": [],
            }
        ]
        warnings = check_docstring_drift_structural(defs)
        assert any(w["type"] == "return_type_contradiction" for w in warnings)

    def test_class_defs_skipped(self):
        defs = [
            {
                "name": "MyClass",
                "type": "class",
                "docstring": "A class with no params.",
                "parameters": [],
                "return_annotation": None,
                "decorators": [],
            }
        ]
        warnings = check_docstring_drift_structural(defs)
        assert len(warnings) == 0

    def test_no_docstring_no_warning(self):
        defs = [
            {
                "name": "fn",
                "type": "function",
                "docstring": None,
                "parameters": ["x"],
                "return_annotation": "int",
                "decorators": [],
            }
        ]
        warnings = check_docstring_drift_structural(defs)
        assert len(warnings) == 0

    def test_short_param_names_not_flagged(self):
        """Parameters with <= 2 chars are not flagged (too many false positives)."""
        defs = [
            {
                "name": "fn",
                "type": "function",
                "docstring": "A function.",
                "parameters": ["x", "y"],
                "return_annotation": None,
                "decorators": [],
            }
        ]
        warnings = check_docstring_drift_structural(defs)
        assert len(warnings) == 0


# ═══════════════════════════════════════════════════════════════════════
#  Docstring Drift Detection — LLM
# ═══════════════════════════════════════════════════════════════════════


class TestDriftLLM:
    """Tests for check_docstring_drift_llm()."""

    def test_falls_back_to_structural_without_llm(self):
        """When llm_fn is None, falls back to structural check."""
        defs = [
            {
                "name": "fn",
                "type": "function",
                "docstring": "Returns None.",
                "parameters": ["self"],
                "return_annotation": "int",
                "decorators": [],
            }
        ]
        warnings = check_docstring_drift_llm(defs, llm_fn=None)
        assert any(w["type"] == "return_type_contradiction" for w in warnings)

    def test_llm_says_no_creates_warning(self):
        def mock_llm(prompt: str) -> str:
            return "NO — the docstring is inaccurate."

        defs = [
            {
                "name": "fn",
                "type": "function",
                "docstring": "Does X.",
                "parameters": ["y"],
                "return_annotation": "str",
                "decorators": [],
            }
        ]
        warnings = check_docstring_drift_llm(defs, llm_fn=mock_llm)
        assert len(warnings) == 1
        assert warnings[0]["type"] == "llm_drift"

    def test_llm_says_yes_no_warning(self):
        def mock_llm(prompt: str) -> str:
            return "YES — the docstring is accurate."

        defs = [
            {
                "name": "fn",
                "type": "function",
                "docstring": "Does X.",
                "parameters": ["x"],
                "return_annotation": "str",
                "decorators": [],
            }
        ]
        warnings = check_docstring_drift_llm(defs, llm_fn=mock_llm)
        assert len(warnings) == 0

    def test_llm_error_graceful(self):
        def failing_llm(prompt: str) -> str:
            raise RuntimeError("API error")

        defs = [
            {
                "name": "fn",
                "type": "function",
                "docstring": "Doc.",
                "parameters": ["x"],
                "return_annotation": None,
                "decorators": [],
            }
        ]
        warnings = check_docstring_drift_llm(defs, llm_fn=failing_llm)
        assert len(warnings) == 0  # Gracefully handles error


# ═══════════════════════════════════════════════════════════════════════
#  Full Pipeline
# ═══════════════════════════════════════════════════════════════════════


class TestGenerateMirror:
    """End-to-end tests for generate_mirror()."""

    def test_full_pipeline_with_explicit_files(self, tmp_repo):
        """Processes explicit source files, writes mirrors, returns summary."""
        src_dir = tmp_repo / "src"
        src_dir.mkdir(exist_ok=True)
        (src_dir / "module.py").write_text(
            textwrap.dedent('''\
        def compute(x: int) -> int:
            """Compute x squared."""
            return x ** 2

        class Processor:
            """Processes data."""
            def run(self, data):
                """Run the processor."""
                pass
        ''')
        )

        result = generate_mirror(
            tmp_repo,
            phase=1,
            source_files=["src/module.py"],
            drift_check=True,
        )

        assert result["files_processed"] == 1
        assert result["definitions_total"] >= 3
        assert len(result["mirrors"]) == 1

        # Verify mirror file exists
        mirror = tmp_repo / "knowledge" / "code-mirror" / "src" / "module.md"
        assert mirror.exists()

    def test_nonexistent_file_skipped(self, tmp_repo):
        result = generate_mirror(
            tmp_repo,
            phase=1,
            source_files=["nonexistent.py"],
        )
        assert result["files_processed"] == 1
        assert len(result["mirrors"]) == 0

    def test_non_python_file_skipped(self, tmp_repo):
        (tmp_repo / "readme.md").write_text("# Readme")
        result = generate_mirror(
            tmp_repo,
            phase=1,
            source_files=["readme.md"],
        )
        assert len(result["mirrors"]) == 0

    def test_drift_warnings_collected(self, tmp_repo):
        src_dir = tmp_repo / "src"
        src_dir.mkdir(exist_ok=True)
        (src_dir / "drifty.py").write_text(
            textwrap.dedent('''\
        def process(alpha_factor: float, beta_range: list) -> dict:
            """Process something generic."""
            return {}
        ''')
        )

        result = generate_mirror(
            tmp_repo,
            phase=1,
            source_files=["src/drifty.py"],
            drift_check=True,
        )

        # alpha_factor and beta_range not mentioned in docstring
        assert len(result["drift_warnings"]) >= 1
        assert any("file" in w for w in result["drift_warnings"])

    def test_drift_check_disabled(self, tmp_repo):
        src_dir = tmp_repo / "src"
        src_dir.mkdir(exist_ok=True)
        (src_dir / "module.py").write_text(
            textwrap.dedent('''\
        def process(alpha_factor: float) -> dict:
            """Process something."""
            return {}
        ''')
        )

        result = generate_mirror(
            tmp_repo,
            phase=1,
            source_files=["src/module.py"],
            drift_check=False,
        )

        assert len(result["drift_warnings"]) == 0

    def test_multiple_files(self, tmp_repo):
        src_dir = tmp_repo / "src"
        src_dir.mkdir(exist_ok=True)
        (src_dir / "a.py").write_text('def fn_a():\n    """A."""\n    pass\n')
        (src_dir / "b.py").write_text('def fn_b():\n    """B."""\n    pass\n')

        result = generate_mirror(
            tmp_repo,
            phase=1,
            source_files=["src/a.py", "src/b.py"],
        )

        assert len(result["mirrors"]) == 2
        assert result["definitions_total"] == 2
