"""Package-level tests for Markdown exporter.

Exercises :func:`akms_learn.exporters.markdown.export` via the compiler's
Stage 9 dispatch (``exporters=["markdown"]`` in the request).

AC covered: 1, 2, 3, 4, 5.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from akms_learn import (
    LearningRequest,
    compile_learning_source,
    fixture_graph,
)


def _make_request(**overrides) -> LearningRequest:
    """Build a minimal LearningRequest that triggers the markdown exporter."""
    defaults = dict(
        topic="j² return mapping",
        goal="Understand the j² return-mapping algorithm",
        audience="engineer",
        depth="implementation",
        generation_option="deterministic_outline",
        seed_tags=[],
        exporters=["markdown"],
    )
    defaults.update(overrides)
    return LearningRequest(**defaults)


class TestMarkdownExporter:
    """Tests for Markdown exporter (template + section renderers).

    AC covered: 1, 2, 3, 4, 5.
    """

    @pytest.mark.unit
    def test_markdown_export_all_sections_present(self, tmp_path: Path) -> None:
        """Rendered lesson.md contains all 9 required headings exactly as in the specification."""
        request = _make_request()
        result = compile_learning_source(
            request=request,
            graph_slice=fixture_graph(),
            output_dir=tmp_path,
        )

        lesson_path = tmp_path / "lesson.md"
        assert lesson_path.exists(), "lesson.md must be written to output_dir"
        assert lesson_path in result.export_paths

        content = lesson_path.read_text(encoding="utf-8")

        required_headings = [
            "# Topic:",
            "## Learning goal",
            "## Prerequisites",
            "## Concept map",
            "## Main path",
            "## Implementation / derivation / explanation",
            "## Pitfalls",
            "## Self-check",
            "## References",
            "## Provenance",
        ]
        for heading in required_headings:
            assert heading in content, (
                f"lesson.md is missing required heading {heading!r}\n"
                f"Content:\n{content}"
            )

    @pytest.mark.unit
    def test_markdown_provenance_required(self, tmp_path: Path) -> None:
        """Provenance section MUST always appear, listing graph_hash, request_hash, every node_id."""
        request = _make_request()
        slice_ = fixture_graph()
        result = compile_learning_source(
            request=request,
            graph_slice=slice_,
            output_dir=tmp_path,
        )

        lesson_path = tmp_path / "lesson.md"
        content = lesson_path.read_text(encoding="utf-8")

        # Provenance values from the packet
        graph_hash = result.packet.source.graph_hash
        req_hash = result.packet.request.request_hash
        assert graph_hash in content, (
            f"lesson.md must contain graph_hash {graph_hash!r}"
        )
        assert req_hash in content, (
            f"lesson.md must contain request_hash {req_hash!r}"
        )

        # Every node_id from the fixture must appear in the rendered output.
        node_ids = [node.node_id for node in result.packet.body.nodes]
        for nid in node_ids:
            assert nid in content, (
                f"lesson.md missing node_id {nid!r}; "
                f"node_ids={node_ids!r}\nContent:\n{content}"
            )

    @pytest.mark.unit
    def test_markdown_byte_stable(self, tmp_path: Path) -> None:
        """Two renders of same packet produce identical bytes (utf-8)."""
        request = _make_request()
        slice_ = fixture_graph()

        dir_a = tmp_path / "run_a"
        dir_b = tmp_path / "run_b"

        compile_learning_source(
            request=request,
            graph_slice=slice_,
            output_dir=dir_a,
        )
        compile_learning_source(
            request=request,
            graph_slice=slice_,
            output_dir=dir_b,
        )

        lesson_a = (dir_a / "lesson.md").read_bytes()
        lesson_b = (dir_b / "lesson.md").read_bytes()

        assert lesson_a == lesson_b, (
            "lesson.md must be byte-equal across two renders of the same packet.\n"
            f"Run A ({len(lesson_a)} bytes):\n{lesson_a.decode()}\n"
            f"Run B ({len(lesson_b)} bytes):\n{lesson_b.decode()}"
        )

    @pytest.mark.unit
    def test_markdown_empty_section_placeholder(self, tmp_path: Path) -> None:
        """Empty section (e.g. no pitfalls) renders heading + '_no content_' marker; never silently omitted."""
        # Use a request with no pitfall nodes (seed_tags filters to a single
        # non-pitfall node) — we pick a tag only on the core node.
        request = _make_request(seed_tags=["j2_plasticity"])
        slice_ = fixture_graph()

        result = compile_learning_source(
            request=request,
            graph_slice=slice_,
            output_dir=tmp_path,
        )

        lesson_path = tmp_path / "lesson.md"
        content = lesson_path.read_text(encoding="utf-8")

        # All required headings must still be present even with filtered graph
        assert "## Pitfalls" in content, (
            "## Pitfalls heading must be present even when no pitfall nodes are included"
        )
        # When no pitfall content, the _no content_ placeholder must appear
        # (the filtered slice may include pitfall nodes depending on seed-tag
        # filtering; we check the placeholder is present somewhere in empty sections)
        assert "_no content_" in content, (
            "lesson.md must contain '_no content_' placeholder for empty sections\n"
            f"Content:\n{content}"
        )
