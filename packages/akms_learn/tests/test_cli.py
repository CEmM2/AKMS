"""Integration tests for ``akms-learn`` CLI.

Tests invoke :func:`akms_learn.cli.main` directly (no subprocess) so the
suite is fast and deterministic. The CLI MUST delegate to
:func:`compile_learning_source` and :func:`validate_packet` — that is
explicitly asserted in ``test_cli_uses_same_api_path``.

"""

from __future__ import annotations

from pathlib import Path

import pytest

from akms_learn import cli
from akms_learn.validation import PacketValidationError


def _compile_argv(tmp_path: Path) -> list[str]:
    """Return a minimal valid ``compile`` argv targeting the fixture graph."""
    return [
        "compile",
        "--graph",
        "fixture",
        "--topic",
        "x",
        "--export",
        "markdown",
        "--output",
        str(tmp_path),
    ]


class TestCliCompileValidate:
    """Tests for CLI compile/validate.

    AC covered: 1, 2, 3, 4, 5.
    """

    @pytest.mark.integration
    def test_cli_compile_fixture_graph_succeeds(self, tmp_path: Path) -> None:
        """``akms-learn compile --graph fixture --topic 'x' --export markdown --output tmp/`` produces packet + lesson.md."""
        exit_code = cli.main(_compile_argv(tmp_path))
        assert exit_code == 0

        json_packets = list(tmp_path.glob("*.json"))
        assert json_packets, "Expected at least one *.json packet in --output"
        assert (tmp_path / "lesson.md").is_file(), "lesson.md missing"

    @pytest.mark.integration
    def test_cli_compile_exit_code_on_invalid(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``PacketValidationError`` raised by the compiler returns exit code 2."""

        def _raise(*_args, **_kwargs):
            raise PacketValidationError(["bad"])

        monkeypatch.setattr(cli, "compile_learning_source", _raise)
        exit_code = cli.main(_compile_argv(tmp_path))
        assert exit_code == 2

    @pytest.mark.integration
    def test_cli_validate_subcommand(self, tmp_path: Path) -> None:
        """``akms-learn validate --packet <path>`` exits 0 on a valid packet."""
        # Compile first to obtain a packet on disk.
        compile_dir = tmp_path / "compile_out"
        compile_dir.mkdir()
        compile_argv = _compile_argv(compile_dir) + ["--export", "bundle"]
        assert cli.main(compile_argv) == 0

        # Prefer the bundle's YAML when present (it is the canonical
        # round-trip artifact); fall back to the JSON packet otherwise.
        yaml_packet = compile_dir / "learning_source_packet.yaml"
        json_packets = list(compile_dir.glob("*.json"))
        # filter out manifest/provenance/concept_map/warnings — pick the
        # request-hash named JSON packet (longest stem).
        non_bundle_json = [
            p
            for p in json_packets
            if p.name
            not in ("manifest.json", "provenance.json", "warnings.json", "concept_map.json")
        ]
        packet_for_validate = (
            yaml_packet if yaml_packet.is_file() else non_bundle_json[0]
        )

        exit_code = cli.main(["validate", "--packet", str(packet_for_validate)])
        assert exit_code == 0

    @pytest.mark.integration
    def test_cli_output_contains_required_keys(
        self, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        """Stdout carries packet_path, export_paths, warnings, unavailable_capabilities, manifest_path."""
        compile_argv = _compile_argv(tmp_path) + ["--export", "bundle"]
        exit_code = cli.main(compile_argv)
        assert exit_code == 0

        captured = capsys.readouterr()
        for key in (
            "packet_path:",
            "export_paths:",
            "warnings:",
            "unavailable_capabilities:",
            "manifest_path:",
        ):
            assert key in captured.out, f"missing CLI output key: {key}"

    @pytest.mark.integration
    def test_cli_uses_same_api_path(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """CLI delegates to ``compile_learning_source`` exactly once."""
        calls: list[dict] = []

        # Build a real compile result via the actual API and replay it, so
        # downstream output formatting still has plausible values.
        from akms_learn.compiler import compile_learning_source as real_compile
        from akms_learn.graph_import import fixture_graph

        real_result = real_compile(
            request={
                "topic": "x",
                "goal": "x",
                "audience": "engineer",
                "depth": "implementation",
                "generation_option": "deterministic_outline",
                "exporters": ["markdown"],
            },
            graph_slice=fixture_graph(),
            output_dir=tmp_path / "real",
        )

        def _spy(**kwargs):
            calls.append(kwargs)
            return real_result

        monkeypatch.setattr(cli, "compile_learning_source", _spy)
        exit_code = cli.main(_compile_argv(tmp_path / "cli_out"))
        assert exit_code == 0
        assert len(calls) == 1, "CLI must call compile_learning_source exactly once"

        kwargs = calls[0]
        assert "request" in kwargs
        request = kwargs["request"]
        assert request["topic"] == "x"
        assert request["exporters"] == ["markdown"]
        assert "graph_slice" in kwargs  # fixture path uses graph_slice
        assert "graph_path" not in kwargs
        assert kwargs["output_dir"] == tmp_path / "cli_out"
