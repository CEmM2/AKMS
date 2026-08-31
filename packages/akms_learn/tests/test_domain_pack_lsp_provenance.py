"""LSP domain-pack provenance fields.

When :func:`compile_learning_source` is invoked with
``domain_pack_paths=[fixture]``, the resulting
:class:`~akms_learn.models.LearningSourcePacket` MUST surface the
descriptor's ``id`` and ``version`` somewhere consumers can find them.

The compiler stashes domain-pack descriptors on
``packet.body.domain_pack_provenance`` as a list of model-dump dicts (see
``compiler._resolve_domain_pack_provenance``); this test asserts the
fixture descriptor's identifying fields are present there.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from akms_learn.compiler import compile_learning_source
from akms_learn.graph_import import fixture_graph

_TESTS_DIR = Path(__file__).resolve().parent
_FIXTURE_ROOT = _TESTS_DIR / "fixtures" / "domain_packs" / "compmech_reference"
DOMAIN_PACK_YAML = _FIXTURE_ROOT / "domain_pack.yaml"


@pytest.mark.integration
def test_lsp_domain_pack_provenance_fields(tmp_path: Path) -> None:
    """Compile with --domain-pack and verify descriptor id/version on packet."""
    result = compile_learning_source(
        request={
            "topic": "j2_return_mapping",
            "goal": "Understand the j² return-mapping algorithm.",
            "audience": "engineer",
            "depth": "implementation",
            "generation_option": "deterministic_outline",
        },
        graph_slice=fixture_graph(),
        output_dir=tmp_path,
        domain_pack_paths=[DOMAIN_PACK_YAML],
    )
    packet = result.packet
    prov = packet.body.domain_pack_provenance
    assert isinstance(prov, list) and prov, (
        "Expected non-empty packet.body.domain_pack_provenance when "
        f"domain_pack_paths is supplied; got {prov!r}"
    )

    ids_and_versions = {(d.get("id"), d.get("version")) for d in prov}
    assert ("compmech.reference", "0.1.0") in ids_and_versions, (
        "Descriptor (id, version) not surfaced on the LSP — "
        f"got {ids_and_versions!r}"
    )

    # Pack id is stable across recompiles — re-run and confirm.
    again = compile_learning_source(
        request={
            "topic": "j2_return_mapping",
            "goal": "Understand the j² return-mapping algorithm.",
            "audience": "engineer",
            "depth": "implementation",
            "generation_option": "deterministic_outline",
        },
        graph_slice=fixture_graph(),
        output_dir=tmp_path / "recompile",
        domain_pack_paths=[DOMAIN_PACK_YAML],
    )
    prov2 = again.packet.body.domain_pack_provenance
    assert isinstance(prov2, list)
    assert {(d.get("id"), d.get("version")) for d in prov2} == ids_and_versions
