"""Bundle exporter for Learning Source Packets (Mode 12).

Exporter Protocol conformance
-----------------------------
This module exposes a top-level :func:`export` function matching the
``Exporter`` callable protocol declared in :mod:`akms_learn.exporters`:

.. code-block:: python

    def export(
        packet: LearningSourcePacket,
        output_dir: Path,
        /,
    ) -> list[Path]: ...

The compiler dispatches this function from Stage 9 of
:func:`akms_learn.compiler.compile_learning_source` when ``"bundle"`` is in
``request.exporters``. Callers MUST NOT invoke this function directly — use
:func:`~akms_learn.compiler.compile_learning_source` with
``exporters=["bundle"]`` instead.

Bundle layout (plan §16, L279-L286)
-----------------------------------
Seven artifacts and two empty directories are emitted under ``output_dir``:

1. ``learning_source_packet.yaml`` — full LSP serialised as YAML
2. ``manifest.json`` — bundle index (compiler version + graph hash + artifact list)
3. ``lesson.md`` — rendered Markdown lesson (delegated to the markdown exporter)
4. ``concept_map.json`` — packet body nodes + edges subset
5. ``provenance.json`` — graph_hash, request_hash, per-node and per-edge provenance
6. ``warnings.json`` — serialised ``LearningWarning`` list
7. (paired) ``exports/`` and ``assets/`` directories, each kept under version
   control via a ``.gitkeep`` sentinel

Reproducibility invariant
-------------------------
**Non-negotiable.** Writing the same packet twice must produce byte-equal
artifacts (the LSP YAML's ``created_at`` timestamp is the sole exception
because it lives inside the packet itself, not in any other artifact).

* YAML: ``yaml.safe_dump(data, sort_keys=True, default_flow_style=False, allow_unicode=True)``
* JSON: ``json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False)``
* No ``uuid``, no ``random``, no ``datetime.now()`` — every value comes from
  the packet itself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from akms_learn.exporters import markdown as _markdown_exporter

if TYPE_CHECKING:
    from akms_learn.models import LearningSourcePacket

__all__ = ["MANIFEST_VERSION", "export"]

#: Manifest schema version. Pinned so future consumers can detect growth of
#: the manifest payload.
MANIFEST_VERSION: str = "v1"


# ---------------------------------------------------------------------------
# Serialisation helpers (deterministic)
# ---------------------------------------------------------------------------


def _dump_yaml(data: Any) -> str:
    """Deterministic YAML serialisation."""
    return yaml.safe_dump(
        data,
        sort_keys=True,
        default_flow_style=False,
        allow_unicode=True,
    )


def _dump_json(data: Any) -> str:
    """Deterministic JSON serialisation."""
    return json.dumps(
        data,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
    )


def _write_text(path: Path, text: str) -> None:
    """Write *text* to *path* with UTF-8 encoding."""
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Manifest builder
# ---------------------------------------------------------------------------


def _build_manifest(
    packet: "LearningSourcePacket",
    artifact_names: list[str],
) -> dict[str, Any]:
    """Construct the deterministic manifest dict.

    Parameters
    ----------
    packet:
        The compiled :class:`LearningSourcePacket`.
    artifact_names:
        Sorted list of artifact filenames (relative to the bundle directory)
        that this manifest indexes.

    Returns
    -------
    dict
        Manifest payload with deterministic key order (achieved by
        ``sort_keys=True`` at dump time).
    """
    compiler_name = packet.compiler.name
    compiler_version = packet.compiler.version
    plugin_api = packet.compiler.plugin_api

    warning_codes = sorted({w.code for w in packet.warnings})
    # Single mode per packet — list shape preserved for forward compatibility.
    learning_modes_used = [packet.request.generation_option]

    # Domain-pack / source-pack metadata blocks:
    # when the compiler is invoked with ``domain_pack_paths=[...]``, the bundle
    # manifest MUST preserve each descriptor's ``id`` and ``version`` so
    # downstream review tooling can reconstruct which packs were in scope. The
    # body's ``domain_pack_provenance`` is a list of full descriptor dumps —
    # we project just the stable identifying fields here. ``source_packs`` is
    # populated symmetrically when source-pack YAMLs are supplied.
    domain_packs_block: list[dict[str, str]] = []
    body_dp = getattr(packet.body, "domain_pack_provenance", None)
    if isinstance(body_dp, list):
        for d in body_dp:
            if isinstance(d, dict):
                pack_id = d.get("id") or d.get("pack_id") or ""
                version = d.get("version") or ""
                if pack_id:
                    domain_packs_block.append(
                        {"id": str(pack_id), "version": str(version)}
                    )
    domain_packs_block.sort(key=lambda d: d["id"])

    source_packs_block: list[dict[str, str]] = []
    body_sp = getattr(packet.body, "source_pack_provenance", None)
    if isinstance(body_sp, list):
        for d in body_sp:
            if isinstance(d, dict):
                sp_id = d.get("id") or d.get("source_pack_id") or ""
                version = d.get("version") or ""
                if sp_id:
                    source_packs_block.append(
                        {"id": str(sp_id), "version": str(version)}
                    )
    source_packs_block.sort(key=lambda d: d["id"])

    # Record the active generation mode and (when set) the
    # selected granularity variant.  Both are read from the LSP request block
    # so they are always consistent with the rest of the packet.
    # ``mode`` is always present; ``granularity`` is omitted entirely when
    # ``None`` (do not write null).
    mode_value = packet.request.generation_option or ""
    granularity_value = packet.request.granularity  # None → omit

    manifest: dict[str, Any] = {
        "manifest_version": MANIFEST_VERSION,
        "compiler_name": compiler_name,
        "compiler_version": compiler_version,
        "plugin_api": plugin_api,
        "graph_hash": packet.source.graph_hash,
        "request_hash": packet.request.request_hash,
        "learning_modes_used": learning_modes_used,
        "mode": mode_value,
        "artifacts": sorted(artifact_names),
        "warnings": warning_codes,
        # Placeholder — populated once soft capabilities are tracked.
        # Always emitted (as an empty list) for stable schema.
        "unavailable_capabilities": [],
        # Domain-pack metadata: empty list when no
        # ``domain_pack_paths`` were supplied to the compiler.
        "domain_packs": domain_packs_block,
        "source_packs": source_packs_block,
    }
    if granularity_value is not None:
        manifest["granularity"] = granularity_value
    return manifest


# ---------------------------------------------------------------------------
# Exporter Protocol entry point
# ---------------------------------------------------------------------------


def export(
    packet: "LearningSourcePacket",
    output_dir: Path,
    /,
) -> list[Path]:
    """Write the 7-artifact Mode 12 bundle to *output_dir*.

    Steps:

    1. ``lesson.md`` is rendered by delegating to
       :func:`akms_learn.exporters.markdown.export` (keeps a single source of
       truth for Markdown rendering).
    2. All remaining artifact payloads are built in memory before any second
       write hits disk. Manifest is built last because it lists the other
       artifacts.
    3. Artifacts are written in alphabetical order for visual consistency
       with ``manifest.json``'s ``artifacts`` field.
    4. Empty ``exports/`` and ``assets/`` directories are created and pinned
       with ``.gitkeep`` sentinels so git tracks them.

    Returns
    -------
    list[Path]
        Sorted (by path string) list of every file written, including the
        two ``.gitkeep`` sentinels.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. lesson.md (delegate to markdown exporter) ----------------------
    lesson_paths = _markdown_exporter.export(packet, out_dir)
    # markdown.export returns [<out_dir>/lesson.md] — capture for return list.

    # --- 2. Build all payloads in memory ----------------------------------
    lsp_payload = packet.model_dump(by_alias=True, mode="json")
    lsp_yaml_text = _dump_yaml(lsp_payload)

    concept_map_text = _dump_json(
        {
            "nodes": [n.model_dump(mode="json") for n in packet.body.nodes],
            "edges": [
                e.model_dump(by_alias=True, mode="json") for e in packet.body.edges
            ],
        }
    )

    provenance_text = _dump_json(
        {
            "graph_hash": packet.source.graph_hash,
            "request_hash": packet.request.request_hash,
            "nodes": sorted(
                [
                    {
                        "node_id": n.node_id,
                        "source_path": n.source_path,
                        "line_range": list(n.line_range),
                    }
                    for n in packet.body.nodes
                ],
                key=lambda d: d["node_id"],
            ),
            "edges": sorted(
                [
                    {
                        "edge_id": e.edge_id,
                        "source_path": e.source_path,
                        "line_range": list(e.line_range),
                    }
                    for e in packet.body.edges
                ],
                key=lambda d: d["edge_id"],
            ),
        }
    )

    warnings_text = _dump_json([w.model_dump(mode="json") for w in packet.warnings])

    # Artifact filenames (relative to out_dir), sorted alphabetically.
    artifact_names = sorted(
        [
            "concept_map.json",
            "learning_source_packet.yaml",
            "lesson.md",
            "manifest.json",
            "provenance.json",
            "warnings.json",
        ]
    )

    # Manifest is built LAST because it indexes the other six artifacts.
    manifest_payload = _build_manifest(packet, artifact_names)
    manifest_text = _dump_json(manifest_payload)

    # --- 3. Write artifacts (alphabetical order; lesson.md already written) -
    concept_map_path = out_dir / "concept_map.json"
    lsp_yaml_path = out_dir / "learning_source_packet.yaml"
    lesson_path = out_dir / "lesson.md"  # written by markdown exporter
    manifest_path = out_dir / "manifest.json"
    provenance_path = out_dir / "provenance.json"
    warnings_path = out_dir / "warnings.json"

    _write_text(concept_map_path, concept_map_text)
    _write_text(lsp_yaml_path, lsp_yaml_text)
    # lesson.md is already on disk via the markdown exporter.
    _write_text(manifest_path, manifest_text)
    _write_text(provenance_path, provenance_text)
    _write_text(warnings_path, warnings_text)

    # --- 4. Empty exports/ and assets/ directories with .gitkeep ----------
    exports_dir = out_dir / "exports"
    assets_dir = out_dir / "assets"
    exports_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    exports_gitkeep = exports_dir / ".gitkeep"
    assets_gitkeep = assets_dir / ".gitkeep"
    _write_text(exports_gitkeep, "")
    _write_text(assets_gitkeep, "")

    # --- 5. Return sorted absolute paths to every written artifact --------
    written: list[Path] = [
        concept_map_path,
        lsp_yaml_path,
        lesson_path,
        manifest_path,
        provenance_path,
        warnings_path,
        exports_gitkeep,
        assets_gitkeep,
    ]
    return sorted(set(written), key=str)
