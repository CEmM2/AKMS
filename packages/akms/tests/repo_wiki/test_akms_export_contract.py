"""Independent, consumer-oriented validation of the committed AKMS fixture pack.

This module deliberately imports neither ``akms.repo_wiki`` nor its renderer.  It
validates only committed files with the Python standard library so an AKMS
consumer can port the checks without acquiring a producer dependency.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures" / "akms_export"
SOURCE_ROOT = FIXTURE_ROOT / "source_repo"
EXPECTED_ROOT = FIXTURE_ROOT / "expected"
RESULT_PATH = FIXTURE_ROOT / "export_result.json"
MANIFEST_PATH = FIXTURE_ROOT / "fixture_manifest.json"
AKMS_V2_FIELDS = {
    "id",
    "title",
    "domain",
    "status",
    "confidence",
    "source",
    "auto_update",
    "content_ref",
    "source_file",
    "generated_at",
    "generated_by_phase",
    "akms_schema",
}


def _frontmatter(markdown: str) -> dict[str, object]:
    """Parse the JSON-scalar YAML frontmatter without a YAML dependency."""

    assert markdown.startswith("---\n")
    block, delimiter, _body = markdown[4:].partition("---\n")
    assert delimiter == "---\n"
    metadata: dict[str, object] = {}
    for line in block.splitlines():
        key, separator, value = line.partition(": ")
        assert separator, f"malformed frontmatter line: {line!r}"
        metadata[key] = json.loads(value)
    return metadata


def _source_from_mirror(markdown: str) -> str:
    """Extract the source fence, retaining its original trailing newline."""

    _before, marker, after = markdown.partition("## Complete Source\n\n")
    assert marker
    opener, separator, remainder = after.partition("\n")
    assert separator and opener.startswith("```")
    fence = opener.removesuffix(opener[3:])
    assert fence
    closing = f"{fence}\n"
    body, separator, _after = remainder.rpartition(closing)
    assert separator
    return body


def _expected_mirrors() -> list[Path]:
    return sorted(path for path in EXPECTED_ROOT.rglob("*.md") if path.is_file())


def test_fixture_manifest_records_independent_contract_and_generator_versions():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest == {
        "akms_schema_version": "v2",
        "export_schema_version": 1,
        "fixture_contract_version": 1,
        "generated_at": "2026-07-26T00:00:00+00:00",
        "generating_repo2md_version": "0.2.0",
        "mirror_count": 6,
        "phase": 1,
    }


def test_each_committed_mirror_has_exact_akms_v2_frontmatter_shape():
    for path in _expected_mirrors():
        metadata = _frontmatter(path.read_text(encoding="utf-8"))
        assert set(metadata) == AKMS_V2_FIELDS
        assert metadata["domain"] == "code-mirror"
        assert metadata["status"] == "established"
        assert metadata["confidence"] == 1.0
        assert metadata["source"] == "generated"
        assert metadata["auto_update"] is True
        assert metadata["generated_by_phase"] == 1
        assert metadata["generated_at"] == "2026-07-26T00:00:00+00:00"
        assert metadata["akms_schema"] == "v2"


def test_mirrors_agree_with_canonical_source_bytes_and_export_result():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    raw_written = result["written"]
    assert result["export_schema_version"] == manifest["export_schema_version"]
    assert result["phase"] == manifest["phase"]
    assert result["generated_at"] == manifest["generated_at"]
    assert len(raw_written) == manifest["mirror_count"] == len(_expected_mirrors())
    assert result["errors"] == []
    assert result["removed"] == []
    assert result["skipped"] == []
    written_by_path = {entry["source_path"]: entry for entry in raw_written}
    assert len(written_by_path) == len(raw_written)
    for field in ("node_id", "content_ref", "generated_path"):
        assert len({entry[field] for entry in raw_written}) == len(raw_written)

    for mirror in _expected_mirrors():
        markdown = mirror.read_bytes().decode("utf-8")
        metadata = _frontmatter(markdown)
        source_path = metadata["source_file"]
        assert isinstance(source_path, str)
        source = (SOURCE_ROOT / source_path).read_bytes().decode("utf-8")
        source_hash = "sha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest()
        record = written_by_path[source_path]
        assert record["source_hash"] == source_hash
        assert record["node_id"] == metadata["id"]
        assert record["content_ref"] == metadata["content_ref"]
        assert mirror.relative_to(EXPECTED_ROOT).as_posix() == record["generated_path"]
        assert _source_from_mirror(markdown) == source


def test_fixture_cases_cover_legacy_nested_collision_and_no_symbol_contracts():
    result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    written = {entry["source_path"]: entry for entry in result["written"]}
    assert written["src/legacy/vector.py"]["node_id"] == "mirror-src-legacy-vector"
    assert (
        written["cpp/vector.hpp"]["content_ref"]
        != written["cpp/vector.cpp"]["content_ref"]
    )
    assert written["cpp/vector.hpp"]["node_id"] != written["cpp/vector.cpp"]["node_id"]

    vector = EXPECTED_ROOT / written["src/legacy/vector.py"]["generated_path"]
    vector_symbols = json.loads(
        vector.read_text(encoding="utf-8")
        .partition("## Symbol Index\n\n```json\n")[2]
        .partition("\n```\n")[0]
    )
    assert any(symbol["parent_id"] for symbol in vector_symbols)

    no_symbols = EXPECTED_ROOT / written["src/legacy/no_symbols.py"]["generated_path"]
    assert "## Symbol Index\n\n```json\n[]\n```" in no_symbols.read_text(
        encoding="utf-8"
    )


def test_unsafe_paths_stay_safe_in_yaml_frontmatter_and_markdown_heading():
    result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    for source_path in ("src/unsafe/ab.py", "src/unsafe/name&unsafe.py"):
        record = next(
            item for item in result["written"] if item["source_path"] == source_path
        )
        markdown = (EXPECTED_ROOT / record["generated_path"]).read_text(
            encoding="utf-8"
        )
        frontmatter, _delimiter, _body = markdown[4:].partition("---\n")
        assert "\u0085" not in frontmatter
        assert _frontmatter(markdown)["source_file"] == source_path
    unsafe_markdown = (
        EXPECTED_ROOT
        / next(
            item
            for item in result["written"]
            if item["source_path"] == "src/unsafe/name&unsafe.py"
        )["generated_path"]
    ).read_text(encoding="utf-8")
    assert "# <code>src/unsafe/name&amp;unsafe.py</code>" in unsafe_markdown
