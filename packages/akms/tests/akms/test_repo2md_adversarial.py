"""Adversarial repo2md export validation (A2-7).

Hermetic: uses committed contract fixtures under tests/contracts/repo2md/
and synthetic on-disk mirrors. Never imports or runs real repo2md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from akms.graph.mirror_provider import MirrorProviderError
from akms.graph.providers.repo2md import _parse_export_json, validate_repo2md_export
from akms.schema.models import MirrorConfig

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts" / "repo2md"


def _load(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


class TestAdversarialContracts:
    def test_partial_output_fixture(self, tmp_path: Path):
        export = _load("adversarial_export_partial.json")
        with pytest.raises(MirrorProviderError) as ei:
            validate_repo2md_export(
                export,
                repo_root=tmp_path,
                output_root=tmp_path,
                config=MirrorConfig(),
            )
        assert ei.value.code == "partial_output"

    def test_unknown_export_schema(self):
        export = _load("adversarial_export_unknown_schema.json")
        with pytest.raises(MirrorProviderError) as ei:
            _parse_export_json(
                json.dumps(export),
                config=MirrorConfig(expected_export_schema_version=1),
            )
        assert ei.value.code == "schema_mismatch"

    def test_path_escape_fixture(self, tmp_path: Path):
        export = _load("adversarial_export_path_escape.json")
        with pytest.raises(MirrorProviderError) as ei:
            validate_repo2md_export(
                export,
                repo_root=tmp_path,
                output_root=tmp_path,
                config=MirrorConfig(),
            )
        assert ei.value.code == "path_escape"

    def test_duplicate_ids(self, tmp_path: Path):
        mirror = tmp_path / "knowledge" / "code-mirror" / "src" / "a.md"
        mirror.parent.mkdir(parents=True)
        body = """---
akms_schema: "v2"
auto_update: true
confidence: 1.0
content_ref: "code-mirror/src/a.md"
domain: "code-mirror"
generated_at: "2026-07-26T00:00:00+00:00"
generated_by_phase: 1
id: "mirror-dup"
source: "generated"
source_file: "src/a.py"
status: "established"
title: "Code Mirror: src/a.py"
---
# a
"""
        mirror.write_text(body, encoding="utf-8")
        b = tmp_path / "knowledge" / "code-mirror" / "src" / "b.md"
        b.write_text(
            body.replace("code-mirror/src/a.md", "code-mirror/src/b.md")
            .replace("src/a.py", "src/b.py")
            .replace("src/a", "src/b"),
            encoding="utf-8",
        )
        # Keep same id in both frontmatters
        b.write_text(
            b.read_text(encoding="utf-8").replace(
                'id: "mirror-dup"', 'id: "mirror-dup"'
            ),
            encoding="utf-8",
        )
        export = {
            "export_schema_version": 1,
            "written": [
                {
                    "generated_path": "knowledge/code-mirror/src/a.md",
                    "content_ref": "code-mirror/src/a.md",
                    "source_path": "src/a.py",
                    "node_id": "mirror-dup",
                },
                {
                    "generated_path": "knowledge/code-mirror/src/b.md",
                    "content_ref": "code-mirror/src/b.md",
                    "source_path": "src/b.py",
                    "node_id": "mirror-dup",
                },
            ],
            "errors": [],
        }
        with pytest.raises(MirrorProviderError) as ei:
            validate_repo2md_export(
                export,
                repo_root=tmp_path,
                output_root=tmp_path,
                config=MirrorConfig(),
            )
        assert ei.value.code == "duplicate_id"

    def test_stale_content_ref_in_frontmatter(self, tmp_path: Path):
        path = tmp_path / "knowledge" / "code-mirror" / "src" / "a.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            """---
akms_schema: "v2"
auto_update: true
confidence: 1.0
content_ref: "code-mirror/src/STALE.md"
domain: "code-mirror"
generated_at: "2026-07-26T00:00:00+00:00"
generated_by_phase: 1
id: "mirror-src-a"
source: "generated"
source_file: "src/a.py"
status: "established"
title: "Code Mirror: src/a.py"
---
# a
""",
            encoding="utf-8",
        )
        export = {
            "export_schema_version": 1,
            "written": [
                {
                    "generated_path": "knowledge/code-mirror/src/a.md",
                    "content_ref": "code-mirror/src/a.md",
                    "source_path": "src/a.py",
                    "node_id": "mirror-src-a",
                }
            ],
            "errors": [],
        }
        with pytest.raises(MirrorProviderError) as ei:
            validate_repo2md_export(
                export,
                repo_root=tmp_path,
                output_root=tmp_path,
                config=MirrorConfig(),
            )
        assert ei.value.code in {"content_ref_mismatch", "frontmatter_invalid"}

    def test_unknown_akms_schema_in_frontmatter(self, tmp_path: Path):
        path = tmp_path / "knowledge" / "code-mirror" / "src" / "a.md"
        path.parent.mkdir(parents=True)
        path.write_text(
            """---
akms_schema: "v999"
auto_update: true
confidence: 1.0
content_ref: "code-mirror/src/a.md"
domain: "code-mirror"
generated_at: "2026-07-26T00:00:00+00:00"
generated_by_phase: 1
id: "mirror-src-a"
source: "generated"
source_file: "src/a.py"
status: "established"
title: "Code Mirror: src/a.py"
---
# a
""",
            encoding="utf-8",
        )
        export = {
            "export_schema_version": 1,
            "written": [
                {
                    "generated_path": "knowledge/code-mirror/src/a.md",
                    "content_ref": "code-mirror/src/a.md",
                    "source_path": "src/a.py",
                    "node_id": "mirror-src-a",
                }
            ],
            "errors": [],
        }
        with pytest.raises(MirrorProviderError) as ei:
            validate_repo2md_export(
                export,
                repo_root=tmp_path,
                output_root=tmp_path,
                config=MirrorConfig(),
            )
        assert ei.value.code in {"frontmatter_invalid", "schema_mismatch"}

    def test_pin_file_present(self):
        pin = _load("pin.json")
        assert pin["export_schema_version"] == 1
        assert pin["akms_schema_version"] == "v2"
        assert pin["fixture_pack_sha256"].startswith("5d2e398b")
