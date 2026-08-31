"""Provider-neutral docstring drift tests (A2-6).

Ensures structural drift survives provider switches and that the
deterministic path never requires an LLM.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

from akms.graph.drift import (
    check_docstring_drift_llm,
    check_docstring_drift_structural,
    check_python_sources_drift,
    extract_definitions_from_source,
)
from akms.graph.generate_mirror import (
    check_docstring_drift_structural as reexported_structural,
    generate_mirror,
)
from akms.schema.models import MirrorConfig, PropagationConfig


class TestStructuralDrift:
    def test_missing_param_warning(self):
        source = textwrap.dedent(
            '''\
            def add(alpha: int, beta: int) -> int:
                """Return the sum (does not name parameters)."""
                return alpha + beta
            '''
        )
        defs = extract_definitions_from_source(source)
        warnings = check_docstring_drift_structural(defs)
        assert any(w["type"] == "missing_param_in_docstring" for w in warnings)

    def test_return_none_contradiction(self):
        source = textwrap.dedent(
            '''\
            def value() -> int:
                """Returns None always."""
                return 1
            '''
        )
        defs = extract_definitions_from_source(source)
        warnings = check_docstring_drift_structural(defs)
        assert any(w["type"] == "return_type_contradiction" for w in warnings)

    def test_reexport_matches(self):
        assert reexported_structural is check_docstring_drift_structural


class TestNoLLMPath:
    def test_llm_fn_none_is_structural(self):
        source = textwrap.dedent(
            '''\
            def f(unique_param_xyz: int) -> int:
                """No params listed."""
                return unique_param_xyz
            '''
        )
        defs = extract_definitions_from_source(source)
        # Must not call any LLM; structural fallback only.
        warnings = check_docstring_drift_llm(defs, llm_fn=None)
        assert any("unique_param_xyz" in w.get("detail", "") for w in warnings)

    def test_generate_mirror_default_no_llm(self, tmp_path: Path):
        (tmp_path / "knowledge" / "code-mirror").mkdir(parents=True)
        src = tmp_path / "src" / "m.py"
        src.parent.mkdir(parents=True)
        src.write_text(
            textwrap.dedent(
                '''\
                def f(unique_param_xyz: int) -> int:
                    """No params listed."""
                    return unique_param_xyz
                '''
            ),
            encoding="utf-8",
        )
        result = generate_mirror(
            tmp_path,
            phase=1,
            source_files=["src/m.py"],
            config=PropagationConfig(mirror=MirrorConfig(provider="legacy")),
            llm_fn=None,
        )
        assert result["success"] is True
        assert any(
            w.get("type") == "missing_param_in_docstring"
            for w in result["drift_warnings"]
        )

    def test_check_python_sources_drift(self, tmp_path: Path):
        src = tmp_path / "a.py"
        src.write_text(
            'def f(unique_param_xyz: int) -> int:\n    """x"""\n    return unique_param_xyz\n',
            encoding="utf-8",
        )
        warnings = check_python_sources_drift(tmp_path, ["a.py"], llm_fn=None)
        assert warnings
