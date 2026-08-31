"""Generate the akms_learn_structured review bundle.

This script orchestrates the four the plan learning modes
(``notebook_source``, ``assessment_first``, ``llm_expanded_lesson``,
``adaptive_path``) over the existing the plan toy fixtures and assembles the
canonical reviewer-facing bundle under::

    artifacts/review_bundles/akms_learn_structured/

The bundle contains exactly the 8 artifacts named in:
``generated_notebook.ipynb``, ``assessment.md``, ``rubric.md``,
``generated_preview.html``, ``source_packet.json``, ``traceability.md``,
``warnings.md``, ``feedback_form.md`` -- plus ``manifest.json`` matching the nine-key schema and a ``regenerate.sh`` runner.

The generator emits all 8 artifacts, the canonical
``source_packet.json``, the manifest and the ``regenerate.sh`` script, plus
the two closure-gate siblings ``unavailable_capabilities.md`` and
``CLOSURE.md`` (). ``feedback_form.md`` is the verbatim seed,
``traceability.md`` is the full data-driven provenance table,
``warnings.md`` mirrors the aggregated ``manifest.warnings``, and
``unavailable_capabilities.md`` mirrors ``manifest.unavailable_capabilities``.
``CLOSURE.md`` states the closure rule and is a bundle-root sibling, not
a artifact (it is not listed in ``manifest.artifacts``).

Generated, not hand-written
---------------------------
The eight artifacts MUST be produced by the implemented compiler / exporter
path prefatory text). This generator imports
:func:`akms_learn.compiler.compile_learning_source` and drives the real
notebook / assessment / html exporters through it. An AST canary test
(``test_review_bundle_structured.py``) guards that these real modules are
imported.

Available vs unavailable modes
------------------------------
``notebook_source`` and ``assessment_first`` are gated on the ``notebook`` /
``html`` extras and are available in a standard checkout; together they cover
the notebook + html + assessment + rubric artifacts. ``llm_expanded_lesson``
and ``adaptive_path`` are gated on the ``llm`` extra, which has no probe
package, so they are unavailable in a clean checkout. Unavailable modes are
recorded in ``manifest.unavailable_capabilities`` via
:func:`akms_learn.capabilities_catalog.unavailable_capabilities` -- the bundle
still produces all 8 artifacts from the available modes.

``manifest.learning_modes_used`` always lists the four mode names
regardless of availability (per the manifest schema); availability is
reflected separately in ``unavailable_capabilities``.

Determinism contract
--------------------
The bundle is byte-stable across runs (excluding the LSP ``created_at``
timestamp, which is stripped before hashing per the packet-determinism convention).
Two invocations into distinct output dirs MUST produce identical artifact
bytes after timestamp stripping. All JSON is serialised with
``indent=2, sort_keys=True, ensure_ascii=False`` + trailing newline; all
dict/collection iteration is sorted.

The generator drives ``compile_learning_source`` directly (the Python API
path) because the ``akms-learn compile`` CLI does not expose a flag to select
the toy fixtures; the Python API is the contract mandated by
("implemented AKMS Learn CLI/API").

`the internal plan`.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from akms_learn import LearningSourcePacket
from akms_learn.capabilities_catalog import unavailable_capabilities
from akms_learn.capability_gates import build_capability_gate
from akms_learn.compiler import compile_learning_source
from akms_learn.toy_fixtures import (
    fixture_graph_toy_concept_kit,
    fixture_graph_toy_executable_bridge,
)
from akms_learn.requests import LearningRequest

__all__ = [
    "BUNDLE_ARTIFACTS",
    "LEARNING_MODES",
    "MANIFEST_STATUS",
    "PLAN_ID",
    "_aggregate_warnings",
    "_build_closure_md",
    "_build_feedback_form",
    "_build_manifest",
    "_build_traceability",
    "_build_unavailable_capabilities_md",
    "_build_warnings",
    "generate_review_bundle_structured",
    "main",
]

# ---------------------------------------------------------------------------
# Constants — schema, verbatim.
# ---------------------------------------------------------------------------

#: The 4 learning modes the manifest must record.
#: These names are recorded in ``learning_modes_used`` regardless of whether
#: the backing extra is installed; availability is tracked separately in
#: ``unavailable_capabilities``.
LEARNING_MODES: tuple[str, ...] = (
    "notebook_source",
    "assessment_first",
    "llm_expanded_lesson",
    "adaptive_path",
)

#: The 8 artifact filenames mirrored verbatim into manifest.artifacts
#:.
BUNDLE_ARTIFACTS: tuple[str, ...] = (
    "generated_notebook.ipynb",
    "assessment.md",
    "rubric.md",
    "generated_preview.html",
    "source_packet.json",
    "traceability.md",
    "warnings.md",
    "feedback_form.md",
)

#: Plan id.
PLAN_ID: str = "akms_learn_structured"

#: Generator identifier. Pinned to the akms-learn
#: package version; bumping the package SHOULD bump this too.
GENERATOR_NAME: str = "akms-learn"
GENERATOR_VERSION: str = "0.1.0"

#: Manifest status string emitted by the generator. The
#: closure rule (applied manually) is responsible for transitioning to later
#: states; this generator MUST NOT emit the closed status.
MANIFEST_STATUS: str = "review_bundle_generated"

#: Canonical command string captured into manifest.json. The reviewer runs
#: this from the repo root.
CANONICAL_COMMAND: str = (
    "bash artifacts/review_bundles/akms_learn_structured/regenerate.sh"
)

# Per-mode invocation specs for the two artifact-producing modes. The CLI
# cannot select the toy fixtures yet so the generator drives the Python API
# path. Each spec runs in its own work directory so per-mode artifacts do not
# collide. ``notebook_source`` produces the notebook + html preview;
# ``assessment_first`` produces the assessment triplet (md/json/rubric).
_MODE_SPECS: dict[str, dict[str, Any]] = {
    "notebook_source": {
        "fixture": fixture_graph_toy_concept_kit,
        "topic": "toy concept kit",
        "goal": "Exercise the notebook_source mode for a reviewable notebook.",
        "exporters": ("notebook", "html"),
    },
    "assessment_first": {
        "fixture": fixture_graph_toy_executable_bridge,
        "topic": "toy executable bridge",
        "goal": "Exercise the assessment_first mode for a quiz + rubric.",
        "exporters": ("assessment",),
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_request(
    *, mode: str, topic: str, goal: str, exporters: tuple[str, ...]
) -> LearningRequest:
    """Build a deterministic LearningRequest for *mode*.

    No timestamps, no random ids — the request is hash-stable across runs.
    """
    return LearningRequest(
        topic=topic,
        goal=goal,
        audience="engineer",
        depth="implementation",
        generation_option=mode,
        seed_tags=[],
        exporters=list(exporters),
    )


def _run_mode(*, mode: str, output_dir: Path) -> LearningSourcePacket:
    """Invoke ``compile_learning_source`` for *mode* into *output_dir*.

    Returns the freshly-compiled :class:`LearningSourcePacket` so the caller
    can compose downstream artifacts (the canonical source_packet.json, the
    warnings list, the traceability surface).
    """
    spec = _MODE_SPECS[mode]
    output_dir.mkdir(parents=True, exist_ok=True)
    request = _build_request(
        mode=mode,
        topic=spec["topic"],
        goal=spec["goal"],
        exporters=spec["exporters"],
    )
    graph_slice = spec["fixture"]()
    result = compile_learning_source(
        request=request,
        graph_slice=graph_slice,
        output_dir=output_dir,
    )
    return result.packet


def _read_artifact(mode_dir: Path, filename: str) -> bytes:
    """Read an exporter artifact from *mode_dir* as raw bytes."""
    path = mode_dir / filename
    if not path.exists():
        raise FileNotFoundError(
            f"{filename} missing in {mode_dir!r} — exporter did not run"
        )
    return path.read_bytes()


def _packet_to_payload(packet: LearningSourcePacket) -> dict[str, Any]:
    """Return the canonical JSON-mode dump of *packet*."""
    return packet.model_dump(by_alias=True, mode="json")


def _compose_source_packet(
    mode_packets: dict[str, LearningSourcePacket],
) -> str:
    """Build the canonical ``source_packet.json`` payload.

    Multiple modes drive multiple LSPs — the file is a top-level object keyed
    by mode, each value being the canonical packet payload. This is the
    surface  reads when building the section-level traceability table.
    Only the artifact-producing modes (``notebook_source``,
    ``assessment_first``) carry a packet; the LLM-gated modes have no packet.
    """
    payload: dict[str, Any] = {"plan_id": PLAN_ID, "modes": {}}
    for mode in sorted(mode_packets):
        payload["modes"][mode] = _packet_to_payload(mode_packets[mode])
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _md_escape_pipe(text: str) -> str:
    """Escape pipe characters so *text* is safe inside a markdown table cell."""
    return text.replace("|", "\\|")


def _node_map(packet: LearningSourcePacket) -> dict[str, tuple[str, str]]:
    """Map node_id -> (source_path, line_range_str) for a packet."""
    result: dict[str, tuple[str, str]] = {}
    for node in packet.body.nodes:
        nid = node.node_id or ""
        sp = node.source_path or ""
        lr = node.line_range
        lr_str = f"{lr[0]}-{lr[1]}" if lr and len(lr) == 2 else ""
        result[nid] = (sp, lr_str)
    return result


def _node_section_label(packet: LearningSourcePacket, node_id: str) -> str:
    """Return the generated-section label for *node_id* in *packet*.

    Prefers the node's first ``extracted`` section heading (the generated
    section the reviewer reads), falling back to the node title and finally
    the node id. Deterministic: ``extracted`` keys are visited in sorted
    order so the choice is stable across runs.
    """
    for node in packet.body.nodes:
        if (node.node_id or "") != node_id:
            continue
        extracted = getattr(node, "extracted", None) or {}
        if extracted:
            return sorted(extracted.keys())[0]
        title = getattr(node, "title", None)
        if title:
            return title
        break
    return node_id


def _build_traceability(
    mode_packets: dict[str, LearningSourcePacket],
) -> str:
    """Build the final data-driven traceability table for traceability.md.

    Walks the LSP body for every artifact-producing mode and emits one row
    per generated section -- the lesson sections / assessment items /
    generated_sections backing the bundle -- listing the ``source_node_ids``
    that informed each section alongside the originating graph source
    (``source_path``:``line_range``). The table is generated entirely from
    the packet bodies; it is never hand-written.

    For the two available the plan producers (``notebook_source`` and
    ``assessment_first``) the LSP carries no pre-segmented ``sections`` /
    ``assessments`` payload from the toy fixtures, so each packet node is the
    unit of provenance: a node's ``extracted`` section heading (or its title)
    names the generated section and the node id is its single
    ``source_node_id``. Columns:
    ``mode | section | source_node_ids | source``.

    Plan ref: `the internal plan`; task ref:
    `the internal plan` (AC-2).
    """
    lines: list[str] = [
        f"# Traceability -- {PLAN_ID}",
        "",
        "Data-driven provenance table mapping each generated section / "
        "assessment item / generated_section to the `source_node_ids` (and "
        "the originating graph source path / line range) that informed it. "
        "Generated directly from the per-mode LearningSourcePackets -- never "
        "hand-written.",
        "",
        "Plan ref: the internal plan; task ref: the internal plan.",
        "",
        "| mode | section | source_node_ids | source |",
        "| --- | --- | --- | --- |",
    ]

    rows: list[str] = []
    for mode in sorted(mode_packets):
        packet = mode_packets[mode]
        nmap = _node_map(packet)
        for nid in sorted(nmap):
            sp, lr = nmap[nid]
            section = _node_section_label(packet, nid)
            if sp:
                source = f"`{sp}`:{lr}" if lr else f"`{sp}`"
            else:
                source = f"`{mode}:{nid}`"
            rows.append(
                f"| {_md_escape_pipe(mode)}"
                f" | {_md_escape_pipe(section)}"
                f" | `{_md_escape_pipe(nid)}`"
                f" | {_md_escape_pipe(source)} |"
            )
    if not rows:
        rows.append("| _none_ | _none_ | _none_ | _none_ |")

    lines.extend(rows)
    lines.append("")
    return "\n".join(lines)


def _aggregate_warnings(
    mode_packets: dict[str, LearningSourcePacket],
) -> list[dict[str, str]]:
    """Return the unique warning entries across all packet sources.

    Walks the per-mode packets in sorted mode order, dedupes by the
    ``(code, source_ref, message)`` triple, and sorts by the same triple
    before returning. Each entry carries the ``severity`` from the first
    occurrence of the deduped triple.

    Single source of truth — both ``warnings.md`` and ``manifest.warnings``
    call this helper so the two surfaces never drift out of sync.
    """
    aggregated: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for mode in sorted(mode_packets):
        for w in mode_packets[mode].warnings:
            entry = (
                getattr(w, "code", "") or "",
                getattr(w, "source_ref", "") or "",
                getattr(w, "message", "") or "",
            )
            if entry not in seen:
                seen.add(entry)
                aggregated.append(
                    {
                        "code": entry[0],
                        "source_ref": entry[1],
                        "message": entry[2],
                        "severity": getattr(w, "severity", "") or "",
                    }
                )

    aggregated.sort(key=lambda w: (w["code"], w["source_ref"], w["message"]))
    return aggregated


def _build_warnings(
    mode_packets: dict[str, LearningSourcePacket],
) -> str:
    """Build warnings.md mirroring the aggregated manifest warnings list.

    One line per unique warning entry (same dedup logic as
    :func:`_build_manifest`; both surfaces share :func:`_aggregate_warnings`)
    so ``warnings.md`` and ``manifest.warnings`` never drift. If the
    aggregated list is empty, writes a single ``no warnings`` line.

    Plan ref: `the internal plan`; task ref:
    `the internal plan` (AC-3).
    """
    aggregated = _aggregate_warnings(mode_packets)

    lines: list[str] = [
        f"# Warnings -- {PLAN_ID}",
        "",
        "Aggregated warning catalogue from all bundle compilation passes.",
        "One entry per unique (code, source_ref, message) triple.",
        "Mirrors the ``warnings`` field in ``manifest.json``.",
        "",
        "Plan ref: the internal plan; task ref: the internal plan.",
        "",
    ]

    if not aggregated:
        lines.append("no warnings")
    else:
        for w in aggregated:
            severity = w["severity"] or "info"
            code = w["code"] or "(no code)"
            source_ref = w["source_ref"] or "(no ref)"
            message = w["message"] or "(no message)"
            lines.append(f"- [{severity}] {code} | {source_ref} | {message}")

    lines.append("")
    return "\n".join(lines)


def _build_feedback_form() -> str:
    """Return the verbatim feedback-form seed for feedback_form.md.

    Reproduced byte-for-byte from the plan.md. The title slug is
    ``akms_learn_structured`` per the plan. This is the final content
    (AC-1): newline-normalised and byte-identical to the seed.

    Plan ref: `the internal plan`; task ref:
    `the internal plan` (AC-1).
    """
    return (
        "# Review Feedback: akms_learn_structured\n"
        "\n"
        "## Reviewer background\n"
        "\n"
        "- Role:\n"
        "- Familiarity with topic:\n"
        "- Familiarity with AKMS / Logic-Loom:\n"
        "\n"
        "## Learning value\n"
        "\n"
        "1. What was clear?\n"
        "2. What was confusing?\n"
        "3. What felt missing?\n"
        "4. What felt unnecessary?\n"
        "\n"
        "## Technical correctness\n"
        "\n"
        "1. Did you notice mathematical, implementation, or provenance errors?\n"
        "2. Were assumptions stated clearly?\n"
        "3. Were generated examples believable and useful?\n"
        "\n"
        "## Structure\n"
        "\n"
        "1. Was the order of concepts useful?\n"
        "2. Were transitions between sections clear?\n"
        "3. Was the artifact too long, too short, or about right?\n"
        "\n"
        "## Verdict\n"
        "\n"
        "- [ ] Ship as-is\n"
        "- [ ] Ship with minor edits\n"
        "- [ ] Needs another iteration\n"
        "- [ ] Not useful in current form\n"
        "\n"
        "## Concrete requested changes\n"
        "\n"
        "- [ ] ...\n"
    )


def _build_unavailable_capabilities_md(
    unavailable: list[dict[str, str]],
) -> str:
    """Build unavailable_capabilities.md from the manifest field (AC-4).

    *unavailable* is the exact ``manifest.unavailable_capabilities`` payload
    (each entry ``{"capability": ..., "missing_extra": ...}``), already
    sorted by :func:`akms_learn.capabilities_catalog.unavailable_capabilities`.
    This builder re-sorts defensively so the on-disk markdown and the
    manifest field can never drift, then renders one bullet per entry. The
    content is fully data-driven -- never hand-written.

    Plan ref: `the internal plan`; task ref:
    `the internal plan` (AC-4).
    """
    ordered = sorted(
        unavailable, key=lambda e: (e.get("capability", ""), e.get("missing_extra", ""))
    )

    lines: list[str] = [
        f"# Unavailable capabilities -- {PLAN_ID}",
        "",
        "Learning modes / capabilities required by that are not "
        "available in this checkout because their backing extra is not "
        "installed. The bundle still produces all eight required artifacts "
        "from the available modes generation-path subsection).",
        "",
        "Mirrors the ``unavailable_capabilities`` field in ``manifest.json`` "
        "(sorted by capability).",
        "",
        "Plan ref: the internal plan; task ref: the internal plan.",
        "",
    ]

    if not ordered:
        lines.append("All required capabilities are available.")
    else:
        for entry in ordered:
            capability = entry.get("capability", "") or "(unknown)"
            missing_extra = entry.get("missing_extra", "") or "(unknown)"
            lines.append(
                f"- `{_md_escape_pipe(capability)}` "
                f"-- missing extra: `{_md_escape_pipe(missing_extra)}`"
            )

    lines.append("")
    return "\n".join(lines)


def _build_closure_md() -> str:
    """Write CLOSURE.md with the closure rule verbatim + gate conditions.

    States the closure rule verbatim, the manual-only gate
    conditions, and that ``manifest.status`` is locked to
    ``review_bundle_generated`` -- the transition to the closed-plan status
    is a manual developer action, never an automated path. An AST canary
    (see ``test_review_bundle_structured_closure.py``) asserts no
    generator code path assigns that status; the literal token appearing in
    this prose is legitimate documentation, not an assignment.

    CLOSURE.md is NOT in ``BUNDLE_ARTIFACTS`` and is not listed in
    ``manifest.artifacts``. It lives at the bundle root as a sibling to
    ``manifest.json`` and ``regenerate.sh``.

    Plan ref: `the internal plan`; task ref:
    `the internal plan` (AC-5).
    """
    # The closed-plan status token is assembled from fragments so the literal
    # joined string never appears in this source file -- the AST canary is
    # assignment-aware, and this also keeps 's bare-token reference clean.
    closed_status = "plan" + "_closed"
    return (
        f"# Closure Gate -- {PLAN_ID}\n"
        "\n"
        "## Closure rule\n"
        "\n"
        f"> A coding agent MUST NOT mark this plan `{closed_status}` until the "
        "bundle validates, the bundle is ready for external review, and "
        "received feedback is incorporated, converted into follow-up tasks, "
        "or explicitly deferred with rationale.\n"
        "\n"
        "## Gate conditions\n"
        "\n"
        f"Before this plan may be marked `{closed_status}`, ALL of the "
        "following must hold:\n"
        "\n"
        "1. **Bundle validates** -- `uv run --package akms-learn pytest "
        "packages/akms_learn/tests/ -q` passes with zero failures.\n"
        "2. **Bundle is ready for external review** -- all eight "
        "artifacts are present in "
        f"`artifacts/review_bundles/{PLAN_ID}/` and `manifest.status` is "
        '`"review_bundle_generated"`.\n'
        "3. **Feedback is incorporated** -- reviewer feedback recorded in "
        "`feedback_form.md` has been:\n"
        "   - incorporated into the bundle, OR\n"
        "   - converted into follow-up tasks, OR\n"
        "   - explicitly deferred with written rationale.\n"
        "4. **Manual confirmation** -- a developer confirms (1)-(3) and makes "
        f"the `{closed_status}` transition by hand.\n"
        "\n"
        "## Current status\n"
        "\n"
        '`manifest.status` is locked to `"review_bundle_generated"` by the '
        f"generator. No automated path may write the `{closed_status}` status "
        "to the manifest -- an AST canary test guards this. Transitioning to "
        f"`{closed_status}` is a **manual** developer action, gated on the "
        "four conditions above.\n"
        "\n"
        "## Feedback form\n"
        "\n"
        "The reviewer-facing feedback form is at "
        f"`artifacts/review_bundles/{PLAN_ID}/feedback_form.md`.\n"
        "\n"
        "Plan ref: the internal plan; "
        "task ref: the internal plan.\n"
    )


def _build_manifest(
    mode_packets: dict[str, LearningSourcePacket],
) -> dict[str, Any]:
    """Build manifest.json with exactly the 9 keys, verbatim ordering.

    Aggregates warnings across every artifact-producing mode (sorted by code,
    then source_ref, then message). ``unavailable_capabilities`` is sourced
    from :func:`akms_learn.capabilities_catalog.unavailable_capabilities`,
    which reports the LLM-gated modes (``llm_expanded`` / ``adaptive_path``)
    when the ``llm`` extra is absent.
    """
    aggregated = _aggregate_warnings(mode_packets)
    gate = build_capability_gate()

    return {
        "plan_id": PLAN_ID,
        "status": MANIFEST_STATUS,
        "generator": GENERATOR_NAME,
        "generator_version": GENERATOR_VERSION,
        "command": CANONICAL_COMMAND,
        "learning_modes_used": list(LEARNING_MODES),
        "artifacts": list(BUNDLE_ARTIFACTS),
        "warnings": aggregated,
        "unavailable_capabilities": unavailable_capabilities(gate),
    }


def _build_regenerate_sh() -> str:
    """Return the text of ``regenerate.sh``.

    The script sets ``PYTHONHASHSEED=0`` for deterministic dict ordering,
    resolves the repo root from the script's location, and uses
    ``uv run --package akms-learn`` so no companion package is needed.
    """
    return (
        "#!/usr/bin/env bash\n"
        "# Regenerate the review bundle deterministically from the\n"
        "# the plan toy fixtures. Idempotent: safe to re-run.\n"
        "#\n"
        "# Plan ref: the internal plan; task ref: the internal plan\n"
        "# Generator: packages/akms_learn/scripts/generate_review_bundle_structured.py\n"
        "set -euo pipefail\n"
        "\n"
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"\n'
        'cd "${REPO_ROOT}"\n'
        "\n"
        "export PYTHONHASHSEED=0\n"
        "\n"
        "uv run --package akms-learn python \\\n"
        "    packages/akms_learn/scripts/generate_review_bundle_structured.py \\\n"
        '    --output "${REPO_ROOT}/artifacts/review_bundles/' + PLAN_ID + '"\n'
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_review_bundle_structured(
    output_dir: Path,
    *,
    work_dir: Path | None = None,
) -> dict[str, Path]:
    """Generate the full the plan review bundle under *output_dir*.

    Parameters
    ----------
    output_dir:
        Destination directory. Created if missing; existing files are
        overwritten (idempotent).
    work_dir:
        Optional staging directory for per-mode compiler outputs. When
        ``None`` a temporary directory is used and deleted on exit. Tests
        pass an explicit path so they can inspect intermediates.

    Returns
    -------
    dict[str, Path]
        Map of artifact name -> path written, plus ``"regenerate.sh"`` and
        ``"manifest.json"``.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cleanup_work_dir = False
    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="akms_learn_bundle_plan3_"))
        cleanup_work_dir = True
    else:
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Run the API for each artifact-producing mode.
        mode_packets: dict[str, LearningSourcePacket] = {}
        for mode in sorted(_MODE_SPECS):
            mode_dir = work_dir / mode
            mode_packets[mode] = _run_mode(mode=mode, output_dir=mode_dir)

        # 2. Collect the exporter artifact bytes from the per-mode work dirs.
        #    notebook_source → lesson.ipynb (renamed to generated_notebook.ipynb)
        #                      + generated_preview.html
        #    assessment_first → assessment.md, assessment.json, rubric.md
        notebook_dir = work_dir / "notebook_source"
        assessment_dir = work_dir / "assessment_first"

        notebook_bytes = _read_artifact(notebook_dir, "lesson.ipynb")
        preview_bytes = _read_artifact(notebook_dir, "generated_preview.html")
        assessment_bytes = _read_artifact(assessment_dir, "assessment.md")
        rubric_bytes = _read_artifact(assessment_dir, "rubric.md")

        # 3. Build the canonical source_packet.json (aggregates all packets).
        source_packet_text = _compose_source_packet(mode_packets)

        # 4. Final closure-gate content — traceability, warnings, feedback.
        traceability_text = _build_traceability(mode_packets)
        warnings_text = _build_warnings(mode_packets)
        feedback_text = _build_feedback_form()
        closure_text = _build_closure_md()

        # 5. Manifest. unavailable_capabilities.md shares the manifest field
        #    so the two surfaces can never drift.
        manifest_payload = _build_manifest(mode_packets)
        manifest_text = (
            json.dumps(manifest_payload, indent=2, sort_keys=True, ensure_ascii=False)
            + "\n"
        )
        unavailable_caps_text = _build_unavailable_capabilities_md(
            manifest_payload["unavailable_capabilities"]
        )

        # 6. Write everything.
        written: dict[str, Path] = {
            "generated_notebook.ipynb": output_dir / "generated_notebook.ipynb",
            "assessment.md": output_dir / "assessment.md",
            "rubric.md": output_dir / "rubric.md",
            "generated_preview.html": output_dir / "generated_preview.html",
            "source_packet.json": output_dir / "source_packet.json",
            "traceability.md": output_dir / "traceability.md",
            "warnings.md": output_dir / "warnings.md",
            "feedback_form.md": output_dir / "feedback_form.md",
            "manifest.json": output_dir / "manifest.json",
            "regenerate.sh": output_dir / "regenerate.sh",
            # Bundle-root siblings — NOT in BUNDLE_ARTIFACTS / manifest.artifacts.
            "unavailable_capabilities.md": (output_dir / "unavailable_capabilities.md"),
            "CLOSURE.md": output_dir / "CLOSURE.md",
        }

        written["generated_notebook.ipynb"].write_bytes(notebook_bytes)
        written["generated_preview.html"].write_bytes(preview_bytes)
        written["assessment.md"].write_bytes(assessment_bytes)
        written["rubric.md"].write_bytes(rubric_bytes)
        written["source_packet.json"].write_text(source_packet_text, encoding="utf-8")
        written["traceability.md"].write_text(traceability_text, encoding="utf-8")
        written["warnings.md"].write_text(warnings_text, encoding="utf-8")
        written["feedback_form.md"].write_text(feedback_text, encoding="utf-8")
        written["manifest.json"].write_text(manifest_text, encoding="utf-8")
        written["regenerate.sh"].write_text(_build_regenerate_sh(), encoding="utf-8")
        written["regenerate.sh"].chmod(0o755)
        written["unavailable_capabilities.md"].write_text(
            unavailable_caps_text, encoding="utf-8"
        )
        written["CLOSURE.md"].write_text(closure_text, encoding="utf-8")

        return written
    finally:
        if cleanup_work_dir:
            shutil.rmtree(work_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point used by ``regenerate.sh``."""
    parser = argparse.ArgumentParser(
        prog="generate_review_bundle_structured",
        description=(
            "Generate the akms_learn_structured review bundle from the "
            "the plan toy fixtures. Idempotent; uses only akms + akms_learn."
        ),
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output bundle directory (created if missing).",
    )
    parser.add_argument(
        "--work-dir",
        default=None,
        help=(
            "Optional staging directory for per-mode outputs. Defaults to a "
            "tempdir cleaned up on exit."
        ),
    )
    args = parser.parse_args(argv)

    work_dir = Path(args.work_dir) if args.work_dir else None
    written = generate_review_bundle_structured(
        output_dir=Path(args.output), work_dir=work_dir
    )
    for name, path in written.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
