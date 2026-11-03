"""AKMS mirror identities (node id, content_ref, paths) and the versioned export contract."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from akms.repo_wiki.export.akms import (
    AKMS_SCHEMA_VERSION,
    EXPORT_SCHEMA_VERSION,
    ErrorRecord,
    ExportResult,
    RemovedRecord,
    SkippedRecord,
    WrittenRecord,
    build_mirror_document,
    mirror_content_ref,
    mirror_document_path,
    mirror_node_id,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "akms_export" / "contract_v1.json"
)


def test_python_legacy_id_and_content_ref_compatibility():
    """Python mirror IDs and content_ref paths remain legacy-compatible."""
    document = build_mirror_document(
        source_path="src/tifem/fft/green.py",
        language="python",
        source_hash="sha256:" + "a" * 64,
        phase=2,
        generated_at=datetime(2026, 3, 7, 12, 0, tzinfo=UTC),
    )

    assert document.node_id == "mirror-src-tifem-fft-green"
    assert document.content_ref == "code-mirror/src/tifem/fft/green.md"
    assert document.generated_path == ".knowledge/code-mirror/src/tifem/fft/green.md"
    assert document.source_path == "src/tifem/fft/green.py"
    assert document.generated_at == "2026-03-07T12:00:00+00:00"
    assert document.phase == 2
    assert document.source_hash == "sha256:" + "a" * 64

    duplicate = build_mirror_document(
        source_path="src/tifem/fft/green.py",
        language="python",
        source_hash="sha256:" + "a" * 64,
        phase=2,
        generated_at=datetime(2026, 3, 7, 12, 0, tzinfo=UTC),
    )
    assert document == duplicate
    assert document.to_dict() == duplicate.to_dict()


def test_multilanguage_same_stem_sources_do_not_collide():
    """Same-stem sources with different language extensions cannot collide."""
    cases = [
        ("src/solver/kernel.cpp", "cpp"),
        ("src/solver/kernel.rs", "rust"),
        ("src/solver/kernel.jl", "julia"),
    ]
    node_ids = {mirror_node_id(path, language) for path, language in cases}
    content_refs = {mirror_content_ref(path, language) for path, language in cases}
    document_paths = {mirror_document_path(path, language) for path, language in cases}

    assert len(node_ids) == len(cases)
    assert len(content_refs) == len(cases)
    assert len(document_paths) == len(cases)
    assert content_refs == {
        "code-mirror/cpp/src/solver/kernel.cpp.md",
        "code-mirror/rust/src/solver/kernel.rs.md",
        "code-mirror/julia/src/solver/kernel.jl.md",
    }
    assert document_paths == {
        f".knowledge/{content_ref}" for content_ref in content_refs
    }
    assert all(source_path not in document_paths for source_path, _ in cases)


def test_contract_matches_golden_json_fixture():
    """The versioned export contract matches the committed golden JSON fixture."""
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    generated_at = "2026-03-07T12:00:00+00:00"
    python_document = build_mirror_document(
        source_path="src/tifem/fft/green.py",
        language="python",
        source_hash="sha256:" + "a" * 64,
        phase=2,
        generated_at=generated_at,
        # The golden contract fixture is frozen with mirrors under knowledge/.
        knowledge_dir="knowledge",
    )
    cpp_document = build_mirror_document(
        source_path="src/tifem/fft/green.cpp",
        language="cpp",
        source_hash="sha256:" + "b" * 64,
        phase=2,
        generated_at=generated_at,
        knowledge_dir="knowledge",
    )
    result = ExportResult(
        phase=2,
        generated_at=generated_at,
        written=[WrittenRecord.from_document(python_document)],
        removed=[
            RemovedRecord(
                source_path="src/obsolete.rs",
                language="rust",
                node_id=mirror_node_id("src/obsolete.rs", "rust"),
                content_ref=mirror_content_ref("src/obsolete.rs", "rust"),
                generated_path=mirror_document_path(
                    "src/obsolete.rs", "rust", "knowledge"
                ),
            )
        ],
        skipped=[
            SkippedRecord(
                source_path="README.md",
                language="markdown",
                source_hash="sha256:" + "c" * 64,
                reason="unsupported-language",
            )
        ],
        errors=[
            ErrorRecord(
                source_path="src/broken.jl",
                language="julia",
                stage="render",
                message="fixture render failure",
            )
        ],
    )

    assert fixture == {
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "akms_schema_version": AKMS_SCHEMA_VERSION,
        "documents": [python_document.to_dict(), cpp_document.to_dict()],
        "result": result.to_dict(),
    }
    assert json.loads(result.to_json()) == fixture["result"]
    assert result.to_json() == result.to_json()
