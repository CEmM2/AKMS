"""bundle manifest preserves domain-pack metadata.

When the compile pipeline is run with ``exporters=["bundle"]`` AND a
domain-pack path, ``manifest.json`` MUST carry a ``domain_packs`` block
listing each descriptor's identifying ``id`` and ``version``. Without this
field, downstream review tooling (Phase 6 Logic-Loom bundle consumer)
cannot reconstruct which packs were in scope for the compile.

Symmetric coverage for ``source_packs`` confirms the same invariant for
source-pack descriptors.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from akms_learn.compiler import compile_learning_source
from akms_learn.graph_import import fixture_graph

_TESTS_DIR = Path(__file__).resolve().parent
_FIXTURE_ROOT = _TESTS_DIR / "fixtures" / "domain_packs" / "compmech_reference"
DOMAIN_PACK_YAML = _FIXTURE_ROOT / "domain_pack.yaml"
SOURCE_PACK_DIR = _FIXTURE_ROOT / "source_packs"
CONSTKIT_YAML = SOURCE_PACK_DIR / "constkit.yaml"


def _base_request() -> dict[str, object]:
    return {
        "topic": "j2_return_mapping",
        "goal": "Generate a bundle artifact.",
        "audience": "engineer",
        "depth": "implementation",
        "generation_option": "deterministic_outline",
        "exporters": ["bundle"],
    }


@pytest.mark.integration
def test_bundle_manifest_preserves_domain_pack_metadata(tmp_path: Path) -> None:
    """manifest.json carries a ``domain_packs`` list with id+version per pack."""
    result = compile_learning_source(
        request=_base_request(),
        graph_slice=fixture_graph(),
        output_dir=tmp_path,
        domain_pack_paths=[DOMAIN_PACK_YAML],
    )
    assert result.packet_path is not None

    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.is_file(), "bundle exporter did not emit manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert "domain_packs" in manifest, (
        f"manifest.json missing 'domain_packs' key — got keys "
        f"{sorted(manifest.keys())!r}"
    )
    dp = manifest["domain_packs"]
    assert isinstance(dp, list) and dp, (
        f"Expected non-empty domain_packs list, got {dp!r}"
    )
    entry = next((d for d in dp if d.get("id") == "compmech.reference"), None)
    assert entry is not None, (
        f"compmech.reference missing from manifest.domain_packs: {dp!r}"
    )
    assert entry["version"] == "0.1.0", (
        f"Wrong version preserved in manifest entry: {entry!r}"
    )


@pytest.mark.integration
def test_bundle_manifest_includes_source_packs_when_supplied(
    tmp_path: Path,
) -> None:
    """When ``source_pack_paths`` is supplied, manifest.json's
    ``source_packs`` block also lists each descriptor's id + version."""
    result = compile_learning_source(
        request=_base_request(),
        graph_slice=fixture_graph(),
        output_dir=tmp_path,
        domain_pack_paths=[DOMAIN_PACK_YAML],
        source_pack_paths=[CONSTKIT_YAML],
    )
    assert result.packet_path is not None

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    sp = manifest.get("source_packs")
    assert isinstance(sp, list) and sp, (
        f"Expected non-empty source_packs list, got {sp!r}"
    )
    ids = {entry.get("id") for entry in sp}
    assert "compmech.constkit" in ids, (
        f"compmech.constkit missing from manifest.source_packs: {sp!r}"
    )


@pytest.mark.integration
def test_bundle_manifest_domain_packs_empty_when_not_supplied(
    tmp_path: Path,
) -> None:
    """No ``domain_pack_paths`` -> the manifest still carries the key (for
    schema stability) but as an empty list."""
    result = compile_learning_source(
        request=_base_request(),
        graph_slice=fixture_graph(),
        output_dir=tmp_path,
    )
    assert result.packet_path is not None

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest.get("domain_packs") == [], (
        f"Expected empty domain_packs list when no paths supplied, got "
        f"{manifest.get('domain_packs')!r}"
    )
    assert manifest.get("source_packs") == []
