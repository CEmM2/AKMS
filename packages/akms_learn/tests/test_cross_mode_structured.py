"""Cross-mode sweep over the four structured compiler modes.

For each of the four modes (``notebook_source``, ``assessment_first``,
``llm_expanded``, ``adaptive_path``) this suite runs the public
``compile_learning_source`` pipeline against the existing toy fixture domain
pack and asserts that the appropriate exporter artefact is produced and
contains non-empty bytes.

Coverage:

* ``notebook_source`` → ``lesson.ipynb`` (notebook exporter, ``notebook`` extra).
* ``assessment_first`` → ``assessment.md``, ``assessment.json``, ``rubric.md``
  (assessment exporter, ``html`` + ``notebook`` extras).
* ``llm_expanded`` → ``lesson.md`` (markdown exporter, no extras required).
* ``adaptive_path`` → ``lesson.md`` (markdown exporter, ``llm`` extra forced
  open via :func:`probe_optional_extras` patch).

The sweep mirrors ``test_cross_mode_pedagogical.py``; every test uses
``tmp_path`` for isolation, and the
extras gate is opened via :func:`importlib.util.find_spec` / ``probe_optional_extras``
patches so the suite runs even when the optional packages are not installed.
"""

from __future__ import annotations

import importlib.util as _iu
from pathlib import Path
from typing import Any

import pytest

import akms_learn.capability_gates as _cap_gates
from akms_learn import LearningRequest, compile_learning_source
from akms_learn.toy_fixtures import (
    fixture_graph_toy_concept_kit,
    fixture_graph_toy_executable_bridge,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def open_all_extras(monkeypatch: pytest.MonkeyPatch) -> None:
    """Open the ``notebook``, ``html``, and ``llm`` extras for the test.

    * ``nbformat`` / ``jinja2`` are faked via ``find_spec`` returning a
      non-None sentinel.
    * The ``llm`` extra has no probe package — we patch
      :func:`probe_optional_extras` so the gate reports ``llm: True``.
    """
    original_find = _iu.find_spec

    def _patched_find(name: str, *args: Any, **kwargs: Any):
        if name in ("nbformat", "jinja2"):
            return object()
        return original_find(name, *args, **kwargs)

    monkeypatch.setattr(_iu, "find_spec", _patched_find)

    original_probe = _cap_gates.probe_optional_extras

    def _patched_probe() -> dict[str, bool]:
        result = original_probe()
        result["llm"] = True
        return result

    monkeypatch.setattr(_cap_gates, "probe_optional_extras", _patched_probe)


def _make_request(
    generation_option: str,
    *,
    exporters: tuple[str, ...],
    **overrides: Any,
) -> LearningRequest:
    """Construct a :class:`LearningRequest` for cross-mode sweep use.

    Mirrors the helper in ``test_cross_mode_pedagogical``.
    """
    defaults: dict[str, Any] = dict(
        topic="cross-mode sweep",
        goal="Exercise structured modes end-to-end through compile + export.",
        audience="engineer",
        depth="implementation",
        generation_option=generation_option,
        seed_tags=[],
        exporters=list(exporters),
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


def _assert_nonempty_artifact(path: Path) -> None:
    """Assert an exporter artefact exists and is non-empty."""
    assert path.exists(), f"expected exporter artefact at {path}"
    assert path.is_file(), f"{path} is not a regular file"
    assert path.stat().st_size > 0, f"{path} was produced but is zero bytes"


# ---------------------------------------------------------------------------
# Cross-mode sweep
# ---------------------------------------------------------------------------


class TestStructuredCrossModeSweep:
    """For each structured mode, compile + export against a toy fixture pack."""

    @pytest.mark.integration
    def test_notebook_source_produces_ipynb(
        self, tmp_path: Path, open_all_extras: None
    ) -> None:
        """``notebook_source`` compile + ``notebook`` exporter → ``lesson.ipynb``."""
        request = _make_request("notebook_source", exporters=("notebook",))
        result = compile_learning_source(
            request=request,
            graph_slice=fixture_graph_toy_concept_kit(),
            output_dir=tmp_path,
        )
        ipynb = tmp_path / "lesson.ipynb"
        _assert_nonempty_artifact(ipynb)
        assert any(p.name == "lesson.ipynb" for p in result.export_paths), (
            f"compiler did not record lesson.ipynb in export_paths: "
            f"{[p.name for p in result.export_paths]}"
        )

    @pytest.mark.integration
    def test_assessment_first_produces_assessment_triplet(
        self, tmp_path: Path, open_all_extras: None
    ) -> None:
        """``assessment_first`` compile + ``assessment`` exporter → triplet."""
        request = _make_request(
            "assessment_first", exporters=("assessment",)
        )
        result = compile_learning_source(
            request=request,
            graph_slice=fixture_graph_toy_executable_bridge(),
            output_dir=tmp_path,
        )

        for name in ("assessment.md", "assessment.json", "rubric.md"):
            _assert_nonempty_artifact(tmp_path / name)

        produced = {p.name for p in result.export_paths}
        assert {"assessment.md", "assessment.json", "rubric.md"} <= produced, (
            f"compiler did not record the assessment triplet in export_paths: "
            f"{sorted(produced)}"
        )

    @pytest.mark.integration
    def test_llm_expanded_produces_lesson_md(
        self, tmp_path: Path, open_all_extras: None
    ) -> None:
        """``llm_expanded`` compile + ``markdown`` exporter → ``lesson.md``.

        With no LLM provider configured the mode falls back to the
        deterministic-only path.  The markdown exporter must
        still produce a non-empty ``lesson.md``.
        """
        request = _make_request("llm_expanded", exporters=("markdown",))
        result = compile_learning_source(
            request=request,
            graph_slice=fixture_graph_toy_concept_kit(),
            output_dir=tmp_path,
        )
        lesson = tmp_path / "lesson.md"
        _assert_nonempty_artifact(lesson)
        assert any(p.name == "lesson.md" for p in result.export_paths)

    @pytest.mark.integration
    def test_adaptive_path_produces_lesson_md(
        self, tmp_path: Path, open_all_extras: None
    ) -> None:
        """``adaptive_path`` compile + ``markdown`` exporter → ``lesson.md``.

        Uses the default conservative-mode :class:`LearnerProfile` (the mode
        applies ``conservative_mode=True`` when no profile is supplied via the
        request).  The markdown exporter must produce a non-empty file.
        """
        request = _make_request("adaptive_path", exporters=("markdown",))
        result = compile_learning_source(
            request=request,
            graph_slice=fixture_graph_toy_concept_kit(),
            output_dir=tmp_path,
        )
        lesson = tmp_path / "lesson.md"
        _assert_nonempty_artifact(lesson)
        assert any(p.name == "lesson.md" for p in result.export_paths)


# ---------------------------------------------------------------------------
# Sanity: the sweep covers exactly the four structured modes.
# ---------------------------------------------------------------------------


PLAN3_MODE_KEYS: tuple[str, ...] = (
    "notebook_source",
    "assessment_first",
    "llm_expanded",
    "adaptive_path",
)


@pytest.mark.integration
def test_sweep_covers_every_structured_mode() -> None:
    """Canary: TestStructuredCrossModeSweep references every structured mode by key.

    Reading the class source ensures the four mode names appear at least
    once each, so a future refactor that accidentally drops one mode from
    the sweep will fail this canary.
    """
    import inspect

    src = inspect.getsource(TestStructuredCrossModeSweep)
    for mode in PLAN3_MODE_KEYS:
        assert mode in src, (
            f"cross-mode sweep is missing coverage for mode {mode!r}"
        )
