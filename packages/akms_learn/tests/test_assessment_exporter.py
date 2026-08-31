"""Tests for assessment exporter (assessment.md + assessment.json + rubric.md).

Covers all five acceptance criteria:

Three files emitted: ``assessment.md``, ``assessment.json``,
      ``rubric.md``.
Public items use a field-allowlist render; canary test confirms no
      ``hidden_answer`` content appears in ``assessment.md`` or
      ``assessment.json``.
``rubric.md`` keys answers by item id with stable ordering (sorted).
With ``"assessment"`` absent from ``request.exporters``, the
      exporter is not invoked by the compiler and no assessment files
      appear.
Exporter is independently registerable / unregisterable from the
      main pipeline.

Additional tests:
  - Allowlist enforcement: a synthetic ``_secret`` key on an item never
    leaks into the public surface.
  - Determinism: two runs against the same LSP produce byte-identical
    output for all three files.
  - LSP with no hidden_answer items: ``rubric.md`` written with a
    "no rubric items" header.
"""

from __future__ import annotations

import importlib.util
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from akms_learn.capability_gates import PreconditionError
from akms_learn.exporters import KNOWN_EXPORTERS
from akms_learn.exporters.assessment import _PUBLIC_FIELDS, export
from akms_learn.models import (
    AssessmentView,
    CompilerInfo,
    LearningRequestInfo,
    LearningSourcePacket,
    PacketBody,
    SourceInfo,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


# A long, distinctive hidden-answer sentinel.  Used by the canary test to
# substring-check the public output — if any byte of this string appears in
# assessment.md or assessment.json, the closure-gate has been breached.
ANSWER_SENTINEL_ALPHA = (
    "HIDDEN_SENTINEL_ALPHA — this answer-key text must NEVER appear in "
    "any public file. token=ZETA_42_KRYPTONITE."
)
ANSWER_SENTINEL_BETA = (
    "HIDDEN_SENTINEL_BETA — second secret answer, distinct enough that no "
    "fragment of it should ever leak. token=OMEGA_7_VANTABLACK."
)


def _make_item_dict(
    item_id: str,
    *,
    kind: str = "conceptual",
    prompt: str = "What is X?",
    hidden_answer: str | None = None,
    target_node_ids: tuple[str, ...] = ("node_a",),
    **extra: Any,
) -> dict[str, Any]:
    """Build a raw assessment item dict matching the AssessmentItem dump shape."""
    payload: dict[str, Any] = {
        "id": item_id,
        "kind": kind,
        "prompt": prompt,
        "hidden_answer": hidden_answer,
        "target_node_ids": list(target_node_ids),
        "provenance": {"derived_from": "test"},
    }
    payload.update(extra)
    return payload


def _make_packet(
    items: list[dict[str, Any]] | None = None,
    *,
    packet_id: str = "test-packet-p3-2",
    topic: str = "Toy Assessment Topic",
) -> LearningSourcePacket:
    """Build a minimal synthetic LSP that carries assessment items."""
    if items is None:
        items = []
    assessments = [AssessmentView.model_validate(it) for it in items]
    return LearningSourcePacket(
        packet_id=packet_id,
        created_at="2026-01-01T00:00:00+00:00",
        compiler=CompilerInfo(name="akms-learn", version="1.0"),
        source=SourceInfo(
            graph_hash="abc123",
            graph_path="toy://graph.json",
            graph_version="v2-test",
        ),
        request=LearningRequestInfo(
            topic=topic,
            request_hash="req-hash-001",
        ),
        body=PacketBody(
            nodes=[],
            edges=[],
            assessments=assessments,
            reading_order=[],
        ),
        warnings=[],
    )


@contextmanager
def _gate_open():
    """Patch ``find_spec`` so the ``html`` extra (``jinja2``) reports present."""
    original = importlib.util.find_spec

    def _patched(name: str, *args: Any, **kwargs: Any):
        if name == "jinja2":
            return object()
        return original(name, *args, **kwargs)

    with patch("importlib.util.find_spec", side_effect=_patched):
        yield


def _run_export(
    packet: LearningSourcePacket,
    output_dir: Path,
) -> list[Path]:
    with _gate_open():
        return export(packet, output_dir)


# ---------------------------------------------------------------------------
# Three files emitted
# ---------------------------------------------------------------------------


class TestThreeFilesEmitted:
    """Assessment.md + assessment.json + rubric.md."""

    @pytest.mark.unit
    def test_three_files_emitted_with_items(self, tmp_path: Path):
        packet = _make_packet(
            items=[
                _make_item_dict(
                    "alpha::conceptual",
                    prompt="Explain alpha.",
                    hidden_answer=ANSWER_SENTINEL_ALPHA,
                ),
                _make_item_dict(
                    "beta::derivation",
                    kind="derivation",
                    prompt="Derive beta.",
                    hidden_answer=ANSWER_SENTINEL_BETA,
                ),
            ]
        )
        paths = _run_export(packet, tmp_path)
        names = sorted(p.name for p in paths)
        assert names == ["assessment.json", "assessment.md", "rubric.md"]
        for p in paths:
            assert p.exists()
            assert p.read_text(encoding="utf-8")

    @pytest.mark.unit
    def test_three_files_emitted_with_no_items(self, tmp_path: Path):
        packet = _make_packet(items=[])
        paths = _run_export(packet, tmp_path)
        names = sorted(p.name for p in paths)
        assert names == ["assessment.json", "assessment.md", "rubric.md"]

    @pytest.mark.unit
    def test_export_returns_three_paths_in_deterministic_order(
        self, tmp_path: Path
    ):
        packet = _make_packet(
            items=[
                _make_item_dict(
                    "alpha::conceptual",
                    hidden_answer=ANSWER_SENTINEL_ALPHA,
                )
            ]
        )
        paths = _run_export(packet, tmp_path)
        assert len(paths) == 3
        assert paths[0].name == "assessment.md"
        assert paths[1].name == "assessment.json"
        assert paths[2].name == "rubric.md"


# ---------------------------------------------------------------------------
# Canary — hidden_answer never leaks into public files.
# ---------------------------------------------------------------------------


class TestCanaryHiddenAnswerSeparation:
    """Hidden_answer content never appears in assessment.md / assessment.json."""

    @pytest.mark.unit
    def test_canary_hidden_answer_absent_from_public_files(
        self, tmp_path: Path
    ):
        """Generate public files and substring-check for every hidden answer."""
        packet = _make_packet(
            items=[
                _make_item_dict(
                    "alpha::conceptual",
                    prompt="What is alpha?",
                    hidden_answer=ANSWER_SENTINEL_ALPHA,
                ),
                _make_item_dict(
                    "beta::derivation",
                    kind="derivation",
                    prompt="Derive beta.",
                    hidden_answer=ANSWER_SENTINEL_BETA,
                ),
            ]
        )
        paths = _run_export(packet, tmp_path)
        md = (tmp_path / "assessment.md").read_bytes()
        js = (tmp_path / "assessment.json").read_bytes()

        for sentinel in (ANSWER_SENTINEL_ALPHA, ANSWER_SENTINEL_BETA):
            assert sentinel.encode("utf-8") not in md, (
                f"Hidden answer sentinel leaked into assessment.md: {sentinel!r}"
            )
            assert sentinel.encode("utf-8") not in js, (
                f"Hidden answer sentinel leaked into assessment.json: {sentinel!r}"
            )

        # And confirm the rubric DOES carry the sentinels (so we know the
        # test setup actually populated hidden_answer).
        rubric = (tmp_path / "rubric.md").read_text(encoding="utf-8")
        assert ANSWER_SENTINEL_ALPHA in rubric
        assert ANSWER_SENTINEL_BETA in rubric

        # Confirm the returned paths match the on-disk files.
        assert [p.name for p in paths] == [
            "assessment.md",
            "assessment.json",
            "rubric.md",
        ]

    @pytest.mark.unit
    def test_allowlist_rejects_synthetic_secret_field(self, tmp_path: Path):
        """A synthetic ``_secret`` field must NOT appear in public output."""
        leak_sentinel = "LEAK_SENTINEL_DELTA_99 — never to be rendered."
        packet = _make_packet(
            items=[
                _make_item_dict(
                    "gamma::coding",
                    kind="coding",
                    prompt="Write code for gamma.",
                    hidden_answer=None,
                    _secret=leak_sentinel,
                ),
            ]
        )
        paths = _run_export(packet, tmp_path)
        md = (tmp_path / "assessment.md").read_bytes()
        js = (tmp_path / "assessment.json").read_bytes()
        rubric = (tmp_path / "rubric.md").read_bytes()
        for blob, name in ((md, "assessment.md"), (js, "assessment.json"), (rubric, "rubric.md")):
            assert leak_sentinel.encode("utf-8") not in blob, (
                f"Synthetic secret leaked into {name}"
            )
        # And the public surface must NOT enumerate any non-allowlisted key.
        data = json.loads((tmp_path / "assessment.json").read_text(encoding="utf-8"))
        for item in data["items"]:
            assert set(item.keys()) == set(_PUBLIC_FIELDS), (
                f"public item keys {set(item.keys())} != allowlist {set(_PUBLIC_FIELDS)}"
            )

    @pytest.mark.unit
    def test_public_json_keys_are_exactly_the_allowlist(self, tmp_path: Path):
        packet = _make_packet(
            items=[
                _make_item_dict(
                    "alpha::conceptual",
                    hidden_answer=ANSWER_SENTINEL_ALPHA,
                ),
            ]
        )
        _run_export(packet, tmp_path)
        data = json.loads((tmp_path / "assessment.json").read_text(encoding="utf-8"))
        assert "hidden_answer" not in json.dumps(data)
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert set(item.keys()) == set(_PUBLIC_FIELDS)


# ---------------------------------------------------------------------------
# rubric.md keyed by item_id, sorted.
# ---------------------------------------------------------------------------


class TestRubricSorted:
    """Rubric.md keys answers by item id with stable ordering."""

    @pytest.mark.unit
    def test_rubric_items_sorted_by_item_id(self, tmp_path: Path):
        # Deliberately unsorted input.
        packet = _make_packet(
            items=[
                _make_item_dict("zeta::coding", kind="coding", prompt="zp", hidden_answer="Z-ans"),
                _make_item_dict("alpha::conceptual", prompt="ap", hidden_answer="A-ans"),
                _make_item_dict("mu::derivation", kind="derivation", prompt="mp", hidden_answer="M-ans"),
            ]
        )
        _run_export(packet, tmp_path)
        rubric = (tmp_path / "rubric.md").read_text(encoding="utf-8")
        # Order of headers (## <id>) must be alpha < mu < zeta.
        idx_alpha = rubric.index("## alpha::conceptual")
        idx_mu = rubric.index("## mu::derivation")
        idx_zeta = rubric.index("## zeta::coding")
        assert idx_alpha < idx_mu < idx_zeta

    @pytest.mark.unit
    def test_rubric_only_includes_items_with_hidden_answer(
        self, tmp_path: Path
    ):
        packet = _make_packet(
            items=[
                _make_item_dict("alpha::conceptual", hidden_answer=ANSWER_SENTINEL_ALPHA),
                _make_item_dict("beta::derivation", kind="derivation", hidden_answer=None),
                _make_item_dict("gamma::coding", kind="coding", hidden_answer=""),
            ]
        )
        _run_export(packet, tmp_path)
        rubric = (tmp_path / "rubric.md").read_text(encoding="utf-8")
        assert "## alpha::conceptual" in rubric
        assert "## beta::derivation" not in rubric
        assert "## gamma::coding" not in rubric

    @pytest.mark.unit
    def test_rubric_with_no_hidden_answers_writes_header_only(
        self, tmp_path: Path
    ):
        packet = _make_packet(
            items=[
                _make_item_dict("alpha::conceptual", hidden_answer=None),
                _make_item_dict("beta::derivation", kind="derivation", hidden_answer=""),
            ]
        )
        _run_export(packet, tmp_path)
        rubric = (tmp_path / "rubric.md").read_text(encoding="utf-8")
        assert rubric.startswith("# Rubric")
        assert "no rubric items" in rubric
        # And contains no item headers.
        assert "## alpha::conceptual" not in rubric
        assert "## beta::derivation" not in rubric


# ---------------------------------------------------------------------------
# Independent disablement + registration.
# ---------------------------------------------------------------------------


class TestDisablement:
    """With assessment excluded, exporter writes nothing."""

    @pytest.mark.unit
    def test_compiler_dispatch_skips_exporter_when_not_requested(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Dispatching with ``exporters=["markdown"]`` skips assessment.*.

        Uses the compiler's Stage 9 dispatch end-to-end: when ``"assessment"``
        is absent from the requested exporters list, no ``assessment.*`` file
        appears, and the sibling markdown exporter still runs.
        """
        # Force capability gates open via find_spec patch (jinja2 + nbformat).
        import importlib.util as _iu

        original_find_spec = _iu.find_spec

        def _patched(name, *args, **kwargs):
            if name in ("jinja2", "nbformat"):
                return object()
            return original_find_spec(name, *args, **kwargs)

        monkeypatch.setattr(_iu, "find_spec", _patched)

        from akms_learn.compiler import compile_learning_source
        from akms_learn.graph_import import GraphSlice

        graph = GraphSlice(nodes=(), edges=(), metadata={"graph_version": "v"})
        request = {
            "topic": "toy",
            "exporters": ["markdown"],
            "seed_tags": [],
        }
        result = compile_learning_source(
            request=request,
            graph_slice=graph,
            output_dir=tmp_path,
        )
        # No assessment-prefixed file on disk.
        produced_names = {p.name for p in result.export_paths}
        assert not any(
            n.startswith("assessment.") or n == "rubric.md"
            for n in produced_names
        )
        # And no orphan files in tmp_path either.
        on_disk = {p.name for p in tmp_path.iterdir()}
        assert "assessment.md" not in on_disk
        assert "assessment.json" not in on_disk
        assert "rubric.md" not in on_disk
        # Sibling exporter still ran.
        assert "lesson.md" in on_disk


class TestIndependentRegistration:
    """Assessment is in KNOWN_EXPORTERS and dispatchable on its own."""

    @pytest.mark.unit
    def test_assessment_registered_in_known_exporters(self):
        assert "assessment" in KNOWN_EXPORTERS

    @pytest.mark.unit
    def test_compiler_dispatches_assessment_when_requested(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """End-to-end: ``exporters=["assessment"]`` produces the three files."""
        import importlib.util as _iu

        original_find_spec = _iu.find_spec

        def _patched(name, *args, **kwargs):
            if name in ("jinja2", "nbformat"):
                return object()
            return original_find_spec(name, *args, **kwargs)

        monkeypatch.setattr(_iu, "find_spec", _patched)

        from akms_learn.compiler import compile_learning_source
        from akms_learn.graph_import import GraphSlice

        graph = GraphSlice(nodes=(), edges=(), metadata={"graph_version": "v"})
        request = {
            "topic": "toy",
            "exporters": ["assessment"],
            "seed_tags": [],
        }
        result = compile_learning_source(
            request=request,
            graph_slice=graph,
            output_dir=tmp_path,
        )
        on_disk = {p.name for p in tmp_path.iterdir()}
        assert "assessment.md" in on_disk
        assert "assessment.json" in on_disk
        assert "rubric.md" in on_disk
        # And the result records them (alongside the canonical packet JSON).
        produced = {p.name for p in result.export_paths}
        assert "assessment.md" in produced
        assert "assessment.json" in produced
        assert "rubric.md" in produced


# ---------------------------------------------------------------------------
# Determinism + capability gate.
# ---------------------------------------------------------------------------


class TestDeterminism:
    """Two runs against the same LSP produce byte-identical output."""

    @pytest.mark.unit
    def test_byte_identical_output_across_runs(self, tmp_path: Path):
        packet = _make_packet(
            items=[
                _make_item_dict(
                    "alpha::conceptual",
                    hidden_answer=ANSWER_SENTINEL_ALPHA,
                ),
                _make_item_dict(
                    "beta::derivation",
                    kind="derivation",
                    hidden_answer=ANSWER_SENTINEL_BETA,
                ),
                _make_item_dict(
                    "gamma::coding",
                    kind="coding",
                    hidden_answer=None,
                ),
            ]
        )
        run_a = tmp_path / "a"
        run_b = tmp_path / "b"
        _run_export(packet, run_a)
        _run_export(packet, run_b)
        for name in ("assessment.md", "assessment.json", "rubric.md"):
            blob_a = (run_a / name).read_bytes()
            blob_b = (run_b / name).read_bytes()
            assert blob_a == blob_b, f"{name} differs between runs"

    @pytest.mark.unit
    def test_input_order_does_not_affect_output(self, tmp_path: Path):
        """Reordering items in the LSP does not change output bytes."""
        items_a = [
            _make_item_dict("alpha::conceptual", hidden_answer="A"),
            _make_item_dict("zeta::coding", kind="coding", hidden_answer="Z"),
        ]
        items_b = list(reversed(items_a))
        packet_a = _make_packet(items=items_a)
        packet_b = _make_packet(items=items_b)
        run_a = tmp_path / "a"
        run_b = tmp_path / "b"
        _run_export(packet_a, run_a)
        _run_export(packet_b, run_b)
        for name in ("assessment.md", "assessment.json", "rubric.md"):
            assert (run_a / name).read_bytes() == (run_b / name).read_bytes()


class TestCapabilityGate:
    """Exporter raises PreconditionError when the html extra is absent."""

    @pytest.mark.unit
    def test_raises_when_jinja2_extra_absent(self, tmp_path: Path):
        original = importlib.util.find_spec

        def _patched(name, *args, **kwargs):
            if name == "jinja2":
                return None
            return original(name, *args, **kwargs)

        packet = _make_packet(items=[])
        with patch("importlib.util.find_spec", side_effect=_patched):
            with pytest.raises(PreconditionError):
                export(packet, tmp_path)
