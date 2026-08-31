"""Package-level integration tests for compile_learning_source.

These tests exercise the 9-stage pipeline end-to-end on the built-in fixture
graph. They are deterministic — no LLM calls, no network, no filesystem
writes outside ``tmp_path``.

AC covered: 1, 2, 3, 4, 5, 6, 7, 8.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from akms_learn import (
    STAGES,
    LearningCapabilityError,
    LearningRequest,
    LearningSourcePacket,
    compile_learning_source,
    fixture_graph,
    validate_packet,
)
from akms_learn.plugin import get_plugin

#   # Path to the compmech_reference fixture (domain-pack registry).
_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "domain_packs"
_COMPMECH_REFERENCE = _FIXTURE_ROOT / "compmech_reference"


def _make_request(**overrides) -> LearningRequest:
    """Build a minimal LearningRequest for the fixture graph."""
    defaults = dict(
        topic="j² return mapping",
        goal="Understand the j² return-mapping algorithm",
        audience="engineer",
        depth="implementation",
        generation_option="deterministic_outline",
        seed_tags=[],
        exporters=[],
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


class TestCompileIntegration:
    """Tests for compile_learning_source 9-stage orchestrator + domain-pack registry."""

    @pytest.mark.integration
    def test_compile_fixture_graph_produces_valid_lsp(self) -> None:
        """Runs the full 9-stage pipeline on the fixture graph and confirms validate_packet passes."""
        request = _make_request()
        result = compile_learning_source(
            request=request,
            graph_slice=fixture_graph(),
        )

        # The returned packet must be a LearningSourcePacket and round-trip.
        assert isinstance(result.packet, LearningSourcePacket)
        round_tripped = LearningSourcePacket.model_validate(
            result.packet.model_dump(by_alias=True)
        )
        assert round_tripped.packet_id == result.packet.packet_id

        # validate_packet must not raise; it only returns soft warnings.
        soft_warnings = validate_packet(result.packet)
        assert isinstance(soft_warnings, list)

        # Body should reflect every fixture node and edge.
        assert len(result.packet.body.nodes) == len(fixture_graph().nodes)
        assert len(result.packet.body.edges) == len(fixture_graph().edges)
        assert result.packet.body.reading_order, "reading_order must be populated"
        assert result.packet.source.graph_hash, "graph_hash must be set"
        assert result.packet.request.request_hash, "request_hash must be set"

    @pytest.mark.integration
    def test_compile_stage_order(self) -> None:
        """Instrumented run asserts every stage executed exactly once, in spec order."""
        request = _make_request()
        result = compile_learning_source(
            request=request,
            graph_slice=fixture_graph(),
        )
        assert tuple(result.stage_log) == STAGES
        assert len(result.stage_log) == 9

    @pytest.mark.integration
    def test_compile_with_domain_pack_paths_populates_metadata(self) -> None:
        """domain_pack_paths=[compmech_reference fixture] populates descriptor metadata in the LSP."""
        request = _make_request()
        result = compile_learning_source(
            request=request,
            graph_slice=fixture_graph(),
            domain_pack_paths=[_COMPMECH_REFERENCE],
        )
        provenance = result.packet.body.domain_pack_provenance
        assert provenance, "domain_pack_provenance must be populated"
        assert isinstance(provenance, list)
        # Compmech fixture has at least one descriptor with id 'compmech.reference'.
        ids = {d.get("id") for d in provenance}
        assert any("compmech" in (i or "") for i in ids), (
            f"Expected a compmech descriptor in provenance, got ids: {ids!r}"
        )

    @pytest.mark.integration
    def test_compile_required_unavailable_raises_capability_error(self) -> None:
        """Required-but-unavailable capability raises LearningCapabilityError.

        Builds a ``LearningRequest`` with
        ``required_capabilities=["nonexistent_capability"]`` and asserts the
        Stage 1 ``_check_required_capabilities`` helper raises
        :class:`LearningCapabilityError` referencing the missing capability.
        """
        request = _make_request(required_capabilities=["nonexistent_capability"])
        with pytest.raises(LearningCapabilityError, match="nonexistent_capability"):
            compile_learning_source(
                request=request,
                graph_slice=fixture_graph(),
            )

    @pytest.mark.integration
    def test_capabilities_extended_to_14(self) -> None:
        """plugin.capabilities() preserves the 18 baseline strings (append-only).

        The catalog added 3 exporter strings (notebook_export/quiz_export/html_export)
        and 4 adapter strings, sourcing the list from
        ``akms_learn.capabilities_catalog``. The catalog is append-only, so this
        test now uses a subset check rather than a fragile length-equality.
        """
        caps = get_plugin().capabilities()
        assert len(caps) >= 18
        for new_cap in (
            "domain_pack_registry",
            "static_domain_pack_descriptors",
            "source_pack_descriptors",
            "code_mirror_provenance",
            "pedagogical_template",
            "derivation_first",
            "implementation_first",
            "multi_granularity",
            # Notebook source compiler.
            "notebook_source",
            # Adaptive path compiler.
            "adaptive_path",
            # Assessment-first compiler.
            "assessment_first",
            # llm_expanded compiler.
            "llm_expanded",
        ):
            assert new_cap in caps

    @pytest.mark.integration
    def test_compile_byte_stable_except_timestamp(self) -> None:
        """Two identical invocations produce byte-equal packets except for ``created_at``.

        ``packet_id`` is now deterministic (derived from ``request_hash`` and
        ``graph_hash``), so the only legitimate per-call difference is the
        wall-clock ``created_at`` timestamp.
        """
        request = _make_request()
        slice_ = fixture_graph()

        result_a = compile_learning_source(request=request, graph_slice=slice_)
        result_b = compile_learning_source(request=request, graph_slice=slice_)

        # packet_id MUST be identical across calls.
        assert result_a.packet.packet_id == result_b.packet.packet_id

        json_a = result_a.packet.model_dump_json(by_alias=True)
        json_b = result_b.packet.model_dump_json(by_alias=True)

        ts_re = re.compile(r'"created_at":\s*"[^"]*"')
        stripped_a = ts_re.sub('"created_at":"X"', json_a)
        stripped_b = ts_re.sub('"created_at":"X"', json_b)

        assert stripped_a == stripped_b

    @pytest.mark.integration
    def test_compile_export_warnings_persisted(self, tmp_path: Path) -> None:
        """Exporter warnings appear in the on-disk JSON, not just the in-memory packet.

        Regression for the Stage 9 ordering bug where exporter warnings were
        appended to ``packet.warnings`` AFTER the canonical JSON had already
        been written, so the persisted file silently lost them.
        """
        request = _make_request(exporters=["nonexistent_exporter"])
        result = compile_learning_source(
            request=request,
            graph_slice=fixture_graph(),
            output_dir=tmp_path,
        )

        # In-memory packet carries the warning.
        codes = [w.code for w in result.packet.warnings]
        assert "exporter_unavailable" in codes

        # The written file must carry it too.
        assert result.packet_path is not None and result.packet_path.exists()
        payload = json.loads(result.packet_path.read_text(encoding="utf-8"))
        persisted_codes = [w.get("code") for w in payload.get("warnings", [])]
        assert "exporter_unavailable" in persisted_codes


# ---------------------------------------------------------------------------
# Regression: dict-shaped request handling
#
# The signature of ``compile_learning_source`` accepts either a
# ``LearningRequest`` instance OR a raw ``dict``. Before the PR-review fix,
# Stage 1 used bare ``getattr(request, ...)`` which silently returned the
# default on dict inputs — so ``required_capabilities`` checks no-op'd and
# ``akms_schema`` overrides were ignored. Two regression tests below pin both
# paths down via ``_request_get``.
# ---------------------------------------------------------------------------


def _make_request_dict(**overrides) -> dict:
    """Build a dict-shaped request that mirrors ``_make_request``."""
    payload: dict = dict(
        topic="j² return mapping",
        goal="Understand the j² return-mapping algorithm",
        audience="engineer",
        depth="implementation",
        generation_option="deterministic_outline",
        seed_tags=[],
        exporters=[],
    )
    payload.update(overrides)
    return payload


class TestCompileDictRequest:
    """Regression tests for dict-shaped ``request`` handling (PR #50 review)."""

    @pytest.mark.integration
    def test_dict_request_required_capabilities_enforced(self) -> None:
        """Dict-shaped ``required_capabilities`` raises LearningCapabilityError.

        Before the fix, ``getattr(dict_obj, "required_capabilities", [])``
        always returned ``[]`` and the check was skipped silently. The new
        ``_request_get`` helper handles both shapes.
        """
        request = _make_request_dict(required_capabilities=["nonexistent_capability"])
        with pytest.raises(LearningCapabilityError, match="nonexistent_capability"):
            compile_learning_source(
                request=request,
                graph_slice=fixture_graph(),
            )

    @pytest.mark.integration
    def test_dict_request_akms_schema_override_rejected(self) -> None:
        """Dict-shaped ``akms_schema="v3"`` is rejected by Stage 1.

        Before the fix, ``getattr(dict_obj, "akms_schema", "v2")`` always
        returned ``"v2"`` — so a dict request claiming an unsupported schema
        version would silently pass.
        """
        request = _make_request_dict(akms_schema="v3")
        with pytest.raises(LearningCapabilityError, match="Unsupported akms_schema"):
            compile_learning_source(
                request=request,
                graph_slice=fixture_graph(),
            )

    @pytest.mark.integration
    def test_dict_request_akms_schema_v2_accepted(self) -> None:
        """Dict-shaped ``akms_schema="v2"`` (explicit) compiles cleanly.

        Companion to the rejection test — ensures the helper doesn't
        accidentally over-reject the supported value.
        """
        request = _make_request_dict(akms_schema="v2")
        result = compile_learning_source(
            request=request,
            graph_slice=fixture_graph(),
        )
        assert tuple(result.stage_log) == STAGES
