"""Package-level byte-stability test for compiler outputs.

Contract: the full pipeline produces identical non-timestamp outputs when
run twice with the same inputs.

Rather than literally re-running the unit suite twice (which pytest itself
exercises every CI run), we run the full compile pipeline twice into two
distinct ``tmp_path`` subdirectories with ``exporters=["markdown", "bundle"]``
and assert that every produced artifact is byte-identical after stripping the
single permitted source of drift: the ISO ``created_at`` timestamp. The
existing unit/integration tests cover the per-stage behaviour; this
harness is the global stability gate.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from akms_learn import (
    compile_learning_source,
    fixture_graph,
)


# Match both JSON ("created_at": "...") and YAML (created_at: '...') styles.
_TS_RE_JSON = re.compile(rb'"created_at"\s*:\s*"[^"]*"')
_TS_RE_YAML = re.compile(rb"(^|\n)(\s*)created_at\s*:\s*'[^']*'")


def _strip_timestamps(payload: bytes) -> bytes:
    """Replace every ``created_at`` literal with a fixed sentinel.

    Handles both JSON quoting (``"created_at": "..."``) and the YAML form
    Pydantic emits via ruamel (``created_at: '...'``). ``manifest.json``,
    ``concept_map.json``, ``provenance.json``, the ``<request_hash>.json``
    packet, and the LSP YAML are all covered by one of the two patterns.
    """
    payload = _TS_RE_JSON.sub(b'"created_at":"<STRIPPED>"', payload)
    payload = _TS_RE_YAML.sub(rb"\1\2created_at: '<STRIPPED>'", payload)
    return payload


def _sha256_stripped(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha256(_strip_timestamps(data)).hexdigest()


# Default LearningRequest now comes from the ``make_request`` conftest fixture
# (see ``packages/akms_learn/tests/conftest.py``) so the helper is shared
# across the suite and stays in sync.


def _all_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


class TestPacketDeterminism:
    """Byte-stable compiler outputs across runs.

    AC covered: 1.
    """

    @pytest.mark.integration
    def test_outputs_byte_stable_across_runs(
        self, tmp_path: Path, make_request
    ) -> None:
        """Two compiles with ``exporters=[markdown, bundle]`` produce identical
        non-timestamp bytes for every artifact.
        """
        out_a = tmp_path / "run_a"
        out_b = tmp_path / "run_b"

        result_a = compile_learning_source(
            request=make_request(),
            graph_slice=fixture_graph(),
            output_dir=out_a,
        )
        result_b = compile_learning_source(
            request=make_request(),
            graph_slice=fixture_graph(),
            output_dir=out_b,
        )

        assert result_a.packet.packet_id == result_b.packet.packet_id, (
            "packet_id must be deterministic across compiles"
        )

        files_a = _all_files(out_a)
        files_b = _all_files(out_b)
        rel_a = [p.relative_to(out_a) for p in files_a]
        rel_b = [p.relative_to(out_b) for p in files_b]
        assert rel_a == rel_b, (
            f"Run produced different artifact sets:\n  A: {rel_a!r}\n  B: {rel_b!r}"
        )
        assert rel_a, "Compile should have written at least one artifact"

        mismatches: list[tuple[str, str, str]] = []
        for rel, path_a, path_b in zip(rel_a, files_a, files_b):
            digest_a = _sha256_stripped(path_a)
            digest_b = _sha256_stripped(path_b)
            if digest_a != digest_b:
                mismatches.append((str(rel), digest_a, digest_b))

        assert not mismatches, (
            "Non-timestamp content drifted across runs:\n  "
            + "\n  ".join(f"{r}: {a} != {b}" for r, a, b in mismatches)
        )
