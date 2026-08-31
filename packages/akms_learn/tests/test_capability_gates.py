"""Tests for capability_gates.py.

Covers all five acceptance criteria:

* pyproject.toml exposes notebook, html, llm optional-dependency groups
      (verified by inspection; not testable in pure Python — see workspace
      mirror test for static checks).
* probe_optional_extras() reports True/False per extra without eager imports.
* Missing extra causes capability omission OR PreconditionError, never ImportError.
* PreconditionError message names the missing extra and the affected capability.
* Tests cover both extra-present and extra-absent paths via monkeypatched find_spec.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from akms_learn.capability_gates import (
    CapabilityGate,
    PreconditionError,
    available_capabilities,
    build_capability_gate,
    probe_optional_extras,
    require_capability,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_find_spec(present: set[str]):
    """Return a fake find_spec that returns a truthy object iff name is in *present*."""

    def _fake(name, *args, **kwargs):
        # Return a sentinel (any truthy value) when present, else None.
        return object() if name in present else None

    return _fake


# ---------------------------------------------------------------------------
# probe_optional_extras
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProbeOptionalExtras:
    """probe_optional_extras() uses importlib.util.find_spec, no eager imports."""

    def test_probe_returns_all_three_keys(self):
        """Result always contains notebook, html, and llm keys."""
        result = probe_optional_extras()
        assert set(result.keys()) == {"notebook", "html", "llm"}

    def test_probe_reports_true_when_extra_installed(self):
        """probe returns True for notebook when nbformat is findable."""
        with patch(
            "importlib.util.find_spec",
            side_effect=_make_find_spec({"nbformat"}),
        ):
            result = probe_optional_extras()
        assert result["notebook"] is True

    def test_probe_reports_false_when_extra_absent(self):
        """probe returns False for notebook when find_spec returns None."""
        with patch(
            "importlib.util.find_spec",
            side_effect=_make_find_spec(set()),
        ):
            result = probe_optional_extras()
        assert result["notebook"] is False

    def test_probe_html_true_when_jinja2_present(self):
        """probe reports True for html when jinja2 is findable."""
        with patch(
            "importlib.util.find_spec",
            side_effect=_make_find_spec({"jinja2"}),
        ):
            result = probe_optional_extras()
        assert result["html"] is True

    def test_probe_html_false_when_jinja2_absent(self):
        """probe reports False for html when jinja2 not findable."""
        with patch(
            "importlib.util.find_spec",
            side_effect=_make_find_spec(set()),
        ):
            result = probe_optional_extras()
        assert result["html"] is False

    def test_probe_llm_false_without_configured_provider(self, monkeypatch):
        """llm probes False when no provider is configured.

        The ``llm`` extra is package-less, so find_spec is irrelevant; the probe
        now resolves it via configured-provider detection. With no env key and
        no nlm notebook/CLI, it stays False (graceful default).
        """
        for var in (
            "ANTHROPIC_API_KEY",
            "OPENAI_API_KEY",
            "GOOGLE_API_KEY",
            "NLM_NOTEBOOK_ID",
            "AKMS_LEARN_NLM_NOTEBOOK_ID",
        ):
            monkeypatch.delenv(var, raising=False)
        with (
            patch("akms_learn.capability_gates.shutil.which", return_value=None),
            patch("importlib.util.find_spec", side_effect=_make_find_spec({"anything"})),
        ):
            result = probe_optional_extras()
        assert result["llm"] is False

    def test_probe_returns_dict_of_bools(self):
        """All values are Python booleans."""
        result = probe_optional_extras()
        for key, val in result.items():
            assert isinstance(val, bool), f"Expected bool for {key!r}, got {type(val)}"

    def test_probe_is_not_eagerly_cached(self):
        """Monkeypatching find_spec after module load still takes effect (no cache)."""
        with patch(
            "importlib.util.find_spec",
            side_effect=_make_find_spec({"nbformat"}),
        ):
            result_present = probe_optional_extras()

        with patch(
            "importlib.util.find_spec",
            side_effect=_make_find_spec(set()),
        ):
            result_absent = probe_optional_extras()

        assert result_present["notebook"] is True
        assert result_absent["notebook"] is False


# ---------------------------------------------------------------------------
# CapabilityGate / build_capability_gate
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildCapabilityGate:
    """build_capability_gate() maps extras to capability flags correctly."""

    def _gate_with(self, present_packages: set[str]) -> CapabilityGate:
        # The `llm` capability is gated on a configured provider. These
        # find_spec-driven assertions model "no provider configured", so pin the
        # provider probe to False for determinism regardless of ambient env.
        with (
            patch("akms_learn.capability_gates._llm_provider_configured", return_value=False),
            patch("importlib.util.find_spec", side_effect=_make_find_spec(present_packages)),
        ):
            return build_capability_gate()

    def test_all_false_when_no_extras(self):
        gate = self._gate_with(set())
        assert gate.notebook_source is False
        assert gate.notebook_export is False
        assert gate.assessment_first is False
        assert gate.quiz_export is False
        assert gate.llm_expanded is False
        assert gate.adaptive_path is False

    def test_notebook_capabilities_true_when_nbformat_present(self):
        gate = self._gate_with({"nbformat"})
        assert gate.notebook_source is True
        assert gate.notebook_export is True
        assert gate.assessment_first is True
        # html and llm capabilities remain False
        assert gate.quiz_export is False
        assert gate.llm_expanded is False
        assert gate.adaptive_path is False

    def test_html_capability_true_when_jinja2_present(self):
        gate = self._gate_with({"jinja2"})
        assert gate.quiz_export is True
        # notebook capabilities remain False
        assert gate.notebook_source is False

    def test_gate_is_frozen(self):
        """CapabilityGate is a frozen dataclass — attributes cannot be mutated."""
        gate = self._gate_with(set())
        with pytest.raises((AttributeError, TypeError)):
            gate.notebook_source = True  # type: ignore[misc]

    def test_gate_has_all_six_capabilities(self):
        """CapabilityGate exposes all six Plan-3 optional capabilities."""
        gate = CapabilityGate()
        expected = {
            "notebook_source",
            "notebook_export",
            "assessment_first",
            "quiz_export",
            "llm_expanded",
            "adaptive_path",
        }
        for cap in expected:
            assert hasattr(gate, cap), f"CapabilityGate missing attribute {cap!r}"


# ---------------------------------------------------------------------------
# available_capabilities
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAvailableCapabilities:
    """available_capabilities() returns a sorted list of present capabilities."""

    def test_empty_when_no_extras(self):
        with patch(
            "importlib.util.find_spec",
            side_effect=_make_find_spec(set()),
        ):
            caps = available_capabilities()
        assert caps == []

    def test_notebook_caps_present_when_nbformat_installed(self):
        with patch(
            "importlib.util.find_spec",
            side_effect=_make_find_spec({"nbformat"}),
        ):
            caps = available_capabilities()
        assert "notebook_source" in caps
        assert "notebook_export" in caps
        assert "assessment_first" in caps

    def test_result_is_sorted(self):
        """Capability listing must be deterministically sorted (cross-phase warning)."""
        with patch(
            "importlib.util.find_spec",
            side_effect=_make_find_spec({"nbformat", "jinja2"}),
        ):
            caps = available_capabilities()
        assert caps == sorted(caps), "available_capabilities() must return a sorted list"

    def test_accepts_pre_built_gate(self):
        """Caller can pass an already-built gate to avoid double probing."""
        gate = CapabilityGate(notebook_source=True, quiz_export=True)
        caps = available_capabilities(gate=gate)
        assert "notebook_source" in caps
        assert "quiz_export" in caps
        assert caps == sorted(caps)


# ---------------------------------------------------------------------------
# PreconditionError
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPreconditionError:
    """PreconditionError is raised (not ImportError) when extra is absent; message names both."""

    def _gate_without_notebook(self) -> CapabilityGate:
        with patch(
            "importlib.util.find_spec",
            side_effect=_make_find_spec(set()),
        ):
            return build_capability_gate()

    def _gate_with_notebook(self) -> CapabilityGate:
        with patch(
            "importlib.util.find_spec",
            side_effect=_make_find_spec({"nbformat"}),
        ):
            return build_capability_gate()

    def test_require_notebook_source_raises_precondition_error_not_importerror(self):
        """Requesting notebook_source without nbformat raises PreconditionError."""
        gate = self._gate_without_notebook()
        with pytest.raises(PreconditionError):
            require_capability("notebook_source", gate=gate)

    def test_require_capability_does_not_raise_importerror(self):
        """require_capability never propagates ImportError."""
        gate = self._gate_without_notebook()
        try:
            require_capability("notebook_source", gate=gate)
        except PreconditionError:
            pass
        except ImportError as exc:
            pytest.fail(f"ImportError was raised instead of PreconditionError: {exc}")

    def test_precondition_error_names_capability(self):
        """PreconditionError message includes the capability name."""
        gate = self._gate_without_notebook()
        with pytest.raises(PreconditionError) as exc_info:
            require_capability("notebook_source", gate=gate)
        assert "notebook_source" in str(exc_info.value)

    def test_precondition_error_names_extra(self):
        """PreconditionError message includes the missing extra name."""
        gate = self._gate_without_notebook()
        with pytest.raises(PreconditionError) as exc_info:
            require_capability("notebook_source", gate=gate)
        assert "notebook" in str(exc_info.value)

    def test_precondition_error_names_both_capability_and_extra(self):
        """PreconditionError message names BOTH capability and extra."""
        gate = self._gate_without_notebook()
        with pytest.raises(PreconditionError) as exc_info:
            require_capability("notebook_source", gate=gate)
        msg = str(exc_info.value)
        assert "notebook_source" in msg, "capability name missing from error message"
        assert "notebook" in msg, "extra name missing from error message"

    def test_precondition_error_has_capability_attribute(self):
        """PreconditionError.capability attribute is set."""
        gate = self._gate_without_notebook()
        with pytest.raises(PreconditionError) as exc_info:
            require_capability("notebook_export", gate=gate)
        assert exc_info.value.capability == "notebook_export"

    def test_precondition_error_has_extra_attribute(self):
        """PreconditionError.extra attribute is set."""
        gate = self._gate_without_notebook()
        with pytest.raises(PreconditionError) as exc_info:
            require_capability("quiz_export", gate=gate)
        assert exc_info.value.extra == "html"

    def test_require_capability_no_error_when_present(self):
        """require_capability does not raise when extra is installed."""
        gate = self._gate_with_notebook()
        # Should not raise
        require_capability("notebook_source", gate=gate)
        require_capability("notebook_export", gate=gate)
        require_capability("assessment_first", gate=gate)

    def test_quiz_export_error_names_html_extra(self):
        """quiz_export PreconditionError names 'html' extra."""
        with patch(
            "importlib.util.find_spec",
            side_effect=_make_find_spec(set()),
        ):
            gate = build_capability_gate()
        with pytest.raises(PreconditionError) as exc_info:
            require_capability("quiz_export", gate=gate)
        msg = str(exc_info.value)
        assert "quiz_export" in msg
        assert "html" in msg

    def test_llm_capabilities_raise_without_configured_provider(self):
        """llm_expanded and adaptive_path raise when no provider is configured."""
        with (
            patch("akms_learn.capability_gates._llm_provider_configured", return_value=False),
            patch("importlib.util.find_spec", side_effect=_make_find_spec({"nbformat", "jinja2"})),
        ):
            gate = build_capability_gate()
        with pytest.raises(PreconditionError) as exc_info:
            require_capability("llm_expanded", gate=gate)
        assert "llm_expanded" in str(exc_info.value)
        assert "llm" in str(exc_info.value)

    def test_unknown_capability_raises_value_error(self):
        """require_capability raises ValueError for unrecognised capability names."""
        gate = CapabilityGate()
        with pytest.raises(ValueError, match="Unknown capability"):
            require_capability("does_not_exist", gate=gate)


# ---------------------------------------------------------------------------
# Module-level safety check — no eager optional imports
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNoEagerImports:
    """capability_gates module must not import nbformat, jinja2, or any LLM
    provider package at module level.

    Implementation note: this class uses a static AST analysis of the source
    file rather than a reload-based runtime check.  The reload approach was
    replaced because ``importlib.reload`` replaces the module-level
    ``PreconditionError`` class object, which breaks ``pytest.raises``
    assertions in any subsequently-run test that imported the *original*
    class reference — regardless of execution order.  The AST approach is also
    strictly stronger: it catches eager imports even when the optional package
    is already in ``sys.modules`` (the reload canary silently no-ops in that
    case).
    """

    _FORBIDDEN_MODULES = frozenset({"nbformat", "jinja2", "openai", "anthropic"})

    def _get_source_path(self) -> pathlib.Path:
        import importlib
        import pathlib

        spec = importlib.util.find_spec("akms_learn.capability_gates")
        assert spec is not None, "akms_learn.capability_gates is not importable"
        assert spec.origin is not None, "capability_gates has no origin path"
        return pathlib.Path(spec.origin)

    def _collect_top_level_imports(self, source: str) -> list[str]:
        """Return the module names referenced by top-level import statements."""
        import ast

        tree = ast.parse(source)
        found: list[str] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # Take the root package name (e.g. "nbformat.reader" → "nbformat").
                    found.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    found.append(node.module.split(".")[0])
        return found

    def test_no_eager_optional_imports_at_module_level(self):
        """AST check: capability_gates.py must not have top-level imports of
        optional packages (nbformat, jinja2, openai, anthropic).

        This test replaces the previous ``importlib.reload``-based canary.
        It is immune to ``sys.modules`` caching and cannot disturb module
        identity for other tests in the session.
        """
        source = self._get_source_path().read_text(encoding="utf-8")
        top_level_imports = self._collect_top_level_imports(source)
        violations = [mod for mod in top_level_imports if mod in self._FORBIDDEN_MODULES]
        assert violations == [], (
            f"capability_gates.py has eager module-level import(s) of optional "
            f"package(s): {violations!r}.  These must only be imported inside "
            f"functions or guarded by try/except, not at module top-level."
        )
