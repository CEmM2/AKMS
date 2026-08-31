"""Generate the akms_learn_mvp Generated Learning Source Review Bundle.

This script orchestrates four `akms-learn compile` CLI invocations (one per
generation mode listed in over the fixture graph and
assembles the canonical reviewer-facing bundle under::

    artifacts/review_bundles/akms_learn_mvp/

The bundle contains exactly the 6 artifacts:
`generated_lesson.md`, `generated_preview.html`, `source_packet.json`,
`traceability.md`, `warnings.md`, `feedback_form.md` -- plus `manifest.json`
matching the 9-key schema at and a `regenerate.sh`
runner.

Determinism contract
--------------------
The bundle is byte-stable across runs (excluding any `created_at`
timestamps inside the LSP itself, which are stripped before hashing per the packet-determinism convention). Two invocations into distinct output dirs MUST produce
identical artifact bytes after timestamp stripping.

Entry points
------------
* `generate_review_bundle(output_dir, *, work_dir=None)` -- Python API used by
  the test suite to assert reproducibility without spawning shells.
* `main(argv=None)` -- CLI entry; called by `regenerate.sh`.

"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt

# ``akms_learn`` is installed editable inside the workspace venv.
from akms_learn import LearningSourcePacket
from akms_learn.cli import main as cli_main

__all__ = ["generate_review_bundle", "main"]

# ---------------------------------------------------------------------------
# Constants -- bundle schema, NOT paraphrased.
# ---------------------------------------------------------------------------

#: The 4 learning modes the bundle must exercise.
LEARNING_MODES: tuple[str, ...] = (
    "deterministic_outline",
    "node_anthology",
    "pitfall_driven",
    "learning_source_bundle",
)

#: The 6 artifact filenames mirrored verbatim into manifest.artifacts.
BUNDLE_ARTIFACTS: tuple[str, ...] = (
    "generated_lesson.md",
    "generated_preview.html",
    "source_packet.json",
    "traceability.md",
    "warnings.md",
    "feedback_form.md",
)

#: Bundle id.
PLAN_ID: str = "akms_learn_mvp"

#: Generator identifier. Pinned to the akms-learn package
#: version; bumping the package SHOULD bump this too.
GENERATOR_NAME: str = "akms-learn"
GENERATOR_VERSION: str = "0.1.0"

#: Manifest status string emitted by the generator. The
#: closure rule is responsible for transitioning to later states.
MANIFEST_STATUS: str = "review_bundle_generated"

#: Canonical command string captured into manifest.json. The reviewer runs
#: this from the repo root.
CANONICAL_COMMAND: str = "bash artifacts/review_bundles/akms_learn_mvp/regenerate.sh"

#: Topic + goal used for every mode invocation. The fixture graph is built
#: around j2 return-mapping (see `fixture_graph` in graph_import.py).
_TOPIC = "j2 return mapping"
_GOAL = "Understand the j2 return-mapping algorithm"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_cli(mode: str, output_dir: Path) -> None:
    """Invoke ``akms-learn compile`` for *mode* into *output_dir*.

    Uses the in-process ``cli.main`` entry point (a thin wrapper around
    argparse + the Python API) so the test harness can re-run this exact
    code path without subprocess overhead. The CLI is the contract per the
    by design -- we do NOT call ``compile_learning_source`` directly.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    argv = [
        "compile",
        "--graph",
        "fixture",
        "--topic",
        _TOPIC,
        "--goal",
        _GOAL,
        "--generation-option",
        mode,
        "--export",
        "markdown",
        "--export",
        "bundle",
        "--output",
        str(output_dir),
        "--quiet",
    ]
    rc = cli_main(argv)
    if rc != 0:
        raise RuntimeError(f"akms-learn compile failed for mode={mode!r} (exit={rc})")


def _read_packet(mode_dir: Path) -> LearningSourcePacket:
    """Locate the LSP JSON in *mode_dir* and load it as a packet."""
    candidates = sorted(mode_dir.glob("*.json"))
    # Filter to top-level packet (excludes manifest.json, concept_map.json,
    # provenance.json, warnings.json which are bundle-exporter artifacts).
    packet_candidates = [
        p
        for p in candidates
        if p.name
        not in {"manifest.json", "concept_map.json", "provenance.json", "warnings.json"}
    ]
    if not packet_candidates:
        raise FileNotFoundError(f"No packet JSON file found in {mode_dir!r}")
    # Compiler writes a single <request_hash>.json per invocation.
    return LearningSourcePacket.model_validate_json(
        packet_candidates[0].read_text(encoding="utf-8")
    )


def _render_html(markdown_text: str) -> str:
    """Render *markdown_text* to a self-contained HTML document.

    Constraints:
      * Deterministic -- no timestamps, no random ids, no external resources.
      * No CSS/JS links (`<link>`, `<script>` tags absent by construction).
      * No generation timestamps in the body.

    markdown-it-py's default ruleset is deterministic for stable input.
    """
    md = MarkdownIt("commonmark")
    body = md.render(markdown_text)
    # Minimal HTML5 wrapper; no external stylesheets, no inline timestamps.
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{PLAN_ID} -- Generated Lesson Preview</title>\n"
        "</head>\n"
        "<body>\n"
        f"{body}"
        "</body>\n"
        "</html>\n"
    )


def _compose_lesson(mode_outputs: dict[str, Path]) -> str:
    """Combine per-mode markdown outputs into a single lesson body.

    Layout:
      * Canonical body = `lesson.md` from the deterministic_outline mode.
      * Appended sections (for traceability + reviewer surface area):
        - Node Anthology
        - Pitfall-Driven
        - Learning Source Bundle (only the lesson.md, not the YAML/JSON).
    """
    parts: list[str] = []
    canonical = mode_outputs["deterministic_outline"] / "lesson.md"
    parts.append(canonical.read_text(encoding="utf-8").rstrip())

    appendices = (
        ("node_anthology", "Node Anthology"),
        ("pitfall_driven", "Pitfall-Driven"),
        ("learning_source_bundle", "Learning Source Bundle"),
    )
    for mode, heading in appendices:
        lesson_path = mode_outputs[mode] / "lesson.md"
        if lesson_path.exists():
            parts.append("")
            parts.append(f"## Appendix: {heading}")
            parts.append("")
            parts.append(lesson_path.read_text(encoding="utf-8").rstrip())
    return "\n".join(parts) + "\n"


# Display label for each learning mode used in the section-level
# traceability table. The deterministic_outline mode is the canonical body of
# the lesson and uses no prefix; the other three contribute appendix sections.
_MODE_DISPLAY: dict[str, str | None] = {
    "deterministic_outline": None,
    "node_anthology": "Node Anthology",
    "pitfall_driven": "Pitfall-Driven",
    "learning_source_bundle": "Learning Source Bundle",
}

# Section titles whose body content is metadata (hashes, ids) about the
# packet rather than the lesson semantics — emit a synthetic per-mode id row
# rather than resolving the embedded node-id code spans.
_FORCE_SYNTHETIC_SECTIONS = frozenset({"Provenance"})

# Appendix sections (non-canonical modes) collapse each mode's lesson into a
# short summary; only the meaningful section labels per mode are surfaced.
_APPENDIX_SECTIONS: dict[str, tuple[str, ...]] = {
    "node_anthology": ("Learning goal", "Concept map", "Main path", "Pitfalls"),
    "pitfall_driven": ("Learning goal", "Concept map", "Pitfalls"),
    "learning_source_bundle": ("Learning goal", "Concept map", "Pitfalls"),
}

_NODE_ID_RE = re.compile(r"`([a-z0-9_]+)`")
_BULLET_RE = re.compile(r"^\s*-\s+(.+?)\s*$")
_HEADING_RE = re.compile(r"^(#{1,2})\s+(.+?)\s*$")
_SLUG_NONWORD_RE = re.compile(r"[^a-z0-9]+")
# Some section titles canonicalise to a shorter slug to keep synthetic ids
# readable (committed precedent in traceability).
_SLUG_ALIASES: dict[str, str] = {
    "implementation_derivation_explanation": "implementation",
}


def _section_slug(title: str) -> str:
    s = _SLUG_NONWORD_RE.sub("_", title.lower().strip()).strip("_")
    return _SLUG_ALIASES.get(s, s)


def _parse_lesson_sections(text: str) -> list[tuple[str, str]]:
    """Return ``[(section_title, body), ...]`` from a per-mode ``lesson.md``.

    Both ``#`` and ``##`` headings are treated as section boundaries; the
    ``# Topic: ...`` heading is normalised to the label ``Topic`` for table
    use.
    """
    sections: list[tuple[str, str]] = []
    current_title: str | None = None
    current_lines: list[str] = []
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            if current_title is not None:
                sections.append((current_title, "\n".join(current_lines)))
            title = m.group(2).strip()
            if title.lower().startswith("topic:"):
                title = "Topic"
            current_title = title
            current_lines = []
        else:
            current_lines.append(line)
    if current_title is not None:
        sections.append((current_title, "\n".join(current_lines)))
    return sections


def _resolve_section_node_refs(body: str, packet: LearningSourcePacket) -> list[Any]:
    """Return packet node-views referenced in *body*, in appearance order.

    Resolution walks two passes: (1) inline-code spans matching a known
    ``node_id``, then (2) bullet text matching a known node ``title``. The
    same node is never returned twice.
    """
    seen: set[str] = set()
    resolved: list[Any] = []
    nodes_by_id = {n.node_id: n for n in packet.body.nodes}
    nodes_by_title: dict[str, str] = {}
    for n in packet.body.nodes:
        title = getattr(n, "title", None)
        if title and title not in nodes_by_title:
            nodes_by_title[title] = n.node_id

    for m in _NODE_ID_RE.finditer(body):
        nid = m.group(1)
        node = nodes_by_id.get(nid)
        if node is not None and nid not in seen:
            seen.add(nid)
            resolved.append(node)

    for line in body.splitlines():
        bm = _BULLET_RE.match(line)
        if not bm:
            continue
        bullet_text = bm.group(1).strip().strip("`")
        nid = nodes_by_title.get(bullet_text)
        if nid and nid not in seen:
            seen.add(nid)
            resolved.append(nodes_by_id[nid])

    return resolved


def _pitfall_edge_refs(packet: LearningSourcePacket) -> list[Any]:
    """Return edges of type ``pitfall_of`` sorted by edge_id."""
    return [
        e
        for e in sorted(packet.body.edges, key=lambda e: e.edge_id)
        if e.type == "pitfall_of"
    ]


def _build_section_traceability(
    mode_dirs: dict[str, Path], packet: LearningSourcePacket
) -> list[str]:
    """Build the markdown rows for the section-level traceability table."""
    rows: list[str] = []
    for mode in LEARNING_MODES:
        lesson_path = mode_dirs[mode] / "lesson.md"
        if not lesson_path.exists():
            continue
        display = _MODE_DISPLAY[mode]
        sections = _parse_lesson_sections(lesson_path.read_text(encoding="utf-8"))

        if display is not None:
            # Appendix mode: emit one synthetic row per pre-declared section.
            section_label = f"Appendix: {display}"
            present_titles = {title for title, _ in sections}
            for title in _APPENDIX_SECTIONS[mode]:
                if title not in present_titles:
                    continue
                slug = _section_slug(title)
                rows.append(f"| {section_label} | {mode}:{slug} | unknown | 0-0 |")
            continue

        # Canonical mode: emit one row per resolved artifact, synthetic if
        # the section has no resolvable refs.
        for title, body in sections:
            if title in _FORCE_SYNTHETIC_SECTIONS:
                resolved_nodes: list[Any] = []
                resolved_edges: list[Any] = []
            else:
                resolved_nodes = _resolve_section_node_refs(body, packet)
                resolved_edges = (
                    _pitfall_edge_refs(packet) if title == "Pitfalls" else []
                )

            if resolved_nodes or resolved_edges:
                for n in resolved_nodes:
                    lr = f"{n.line_range[0]}-{n.line_range[1]}"
                    rows.append(f"| {title} | {n.node_id} | {n.source_path} | {lr} |")
                for e in resolved_edges:
                    lr = f"{e.line_range[0]}-{e.line_range[1]}"
                    rows.append(f"| {title} | {e.edge_id} | {e.source_path} | {lr} |")
            else:
                slug = _section_slug(title)
                rows.append(f"| {title} | {mode}:{slug} | unknown | 0-0 |")
    return rows


def _build_traceability(
    packet: LearningSourcePacket, mode_dirs: dict[str, Path]
) -> str:
    """Render `traceability.md` with section-level and node/edge tables.

    The section-level table maps each generated-lesson section to the graph
    artifacts (nodes / edges) that informed it; sections that emit
    boilerplate get a synthetic ``<mode>:<slug>`` id. The node/edge
    reference table lists every packet artifact with its provenance.
    """
    lines: list[str] = [
        "# Traceability -- akms_learn_mvp",
        "",
        (
            "Each row maps a generated-lesson section to the graph artifact "
            "(node or edge) it was derived from. The `source_path` + "
            "`line_range` columns reflect the values stored in the fixture "
            "graph nodes; fixture nodes carry `source_path=unknown` and "
            "`line_range=0-0` because they are in-memory test fixtures with "
            "no backing file."
        ),
        "",
        "## Section-level traceability",
        "",
        "| section_title | node_id / edge_id | source_path | line_range |",
        "| --- | --- | --- | --- |",
    ]
    lines.extend(_build_section_traceability(mode_dirs, packet))
    lines.extend(
        [
            "",
            "## Node/edge reference table",
            "",
            (
                "Full list of packet nodes and edges with their provenance "
                "as recorded in `source_packet.json`."
            ),
            "",
            "| section_title | node_id / edge_id | source_path | line_range |",
            "| --- | --- | --- | --- |",
        ]
    )
    nodes = sorted(packet.body.nodes, key=lambda n: n.node_id)
    edges = sorted(packet.body.edges, key=lambda e: e.edge_id)
    for n in nodes:
        title = getattr(n, "title", None) or n.node_id
        lr = f"{n.line_range[0]}-{n.line_range[1]}"
        lines.append(f"| {title} | {n.node_id} | {n.source_path} | {lr} |")
    for e in edges:
        lr = f"{e.line_range[0]}-{e.line_range[1]}"
        lines.append(f"| edge:{e.type} | {e.edge_id} | {e.source_path} | {lr} |")
    lines.append("")
    return "\n".join(lines)


def _build_warnings(packet: LearningSourcePacket) -> str:
    """Render `warnings.md`: one line per packet warning, in order.

    Empty case is handled with an explicit "no warnings" header so the file
    is never zero-byte (AC-1 requires non-empty deliverables).
    """
    warnings = list(packet.warnings)
    if not warnings:
        return (
            "# Warnings -- akms_learn_mvp\n"
            "\n"
            "No warnings were emitted by the compiler for this bundle.\n"
        )
    lines: list[str] = [
        "# Warnings -- akms_learn_mvp",
        "",
    ]
    for w in warnings:
        code = getattr(w, "code", "") or ""
        source_ref = getattr(w, "source_ref", "") or ""
        message = getattr(w, "message", "") or ""
        severity = getattr(w, "severity", "") or ""
        lines.append(f"- [{severity}] {code} | {source_ref} | {message}")
    lines.append("")
    return "\n".join(lines)


def _build_feedback_form() -> str:
    """Return the feedback-form seed for this bundle id.

    The heading, prompt order,
    verdict checkboxes, and concrete-changes placeholder are byte-stable
    contracts that downstream reviewer tooling and tests rely on.
    """
    return (
        f"# Review Feedback: {PLAN_ID}\n"
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


def _build_manifest(packet: LearningSourcePacket) -> dict[str, Any]:
    """Build manifest.json payload with exactly the 9 keys.

    Key list (verbatim from:
      plan_id, status, generator, generator_version, command,
      learning_modes_used, artifacts, warnings, unavailable_capabilities.

    No extra top-level keys are added -- additive metadata (e.g.
    manifest_version, domain_packs) lives on the per-mode bundle manifest,
    not on this reviewer-facing manifest.
    """
    warnings_list = [
        {
            "code": getattr(w, "code", "") or "",
            "severity": getattr(w, "severity", "") or "",
            "message": getattr(w, "message", "") or "",
            "source_ref": getattr(w, "source_ref", "") or "",
        }
        for w in packet.warnings
    ]
    return {
        "plan_id": PLAN_ID,
        "status": MANIFEST_STATUS,
        "generator": GENERATOR_NAME,
        "generator_version": GENERATOR_VERSION,
        "command": CANONICAL_COMMAND,
        "learning_modes_used": list(LEARNING_MODES),
        "artifacts": list(BUNDLE_ARTIFACTS),
        "warnings": warnings_list,
        "unavailable_capabilities": [],
    }


def _build_regenerate_sh() -> str:
    """Return the text of `regenerate.sh`.

    The script:
      * sets `PYTHONHASHSEED=0` for deterministic dict ordering (defensive --
        the compiler is already determinism-tested),
      * runs from the repo root,
      * uses `uv run --package akms-learn` so no companion package is needed.
    """
    return (
        "#!/usr/bin/env bash\n"
        "# Regenerate the akms-learn review bundle deterministically from\n"
        "# the fixture graph. Idempotent: safe to re-run.\n"
        "#\n"
        "# Generator: packages/akms_learn/scripts/generate_review_bundle.py\n"
        "set -euo pipefail\n"
        "\n"
        "# Resolve repo root from this script's location so the command is\n"
        "# runnable from any cwd.\n"
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"\n'
        'cd "${REPO_ROOT}"\n'
        "\n"
        "export PYTHONHASHSEED=0\n"
        "\n"
        "uv run --package akms-learn python \\\n"
        "    packages/akms_learn/scripts/generate_review_bundle.py \\\n"
        '    --output "${REPO_ROOT}/artifacts/review_bundles/' + PLAN_ID + '"\n'
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_review_bundle(
    output_dir: Path,
    *,
    work_dir: Path | None = None,
) -> dict[str, Path]:
    """Generate the full review bundle under *output_dir*.

    Parameters
    ----------
    output_dir:
        Destination directory. Created if missing; existing files are
        overwritten (idempotent).
    work_dir:
        Optional staging directory for per-mode CLI outputs. When ``None``
        a temporary directory is used and deleted on exit. Tests pass an
        explicit path so they can inspect intermediates.

    Returns
    -------
    dict[str, Path]
        Map of artifact name -> path written, plus the key ``"regenerate.sh"``
        and ``"manifest.json"``.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cleanup_work_dir = False
    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="akms_learn_bundle_"))
        cleanup_work_dir = True
    else:
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Run the CLI once per mode into a dedicated subdirectory.
        mode_dirs: dict[str, Path] = {}
        for mode in LEARNING_MODES:
            mode_dir = work_dir / mode
            _run_cli(mode, mode_dir)
            mode_dirs[mode] = mode_dir

        # 2. Use the deterministic_outline packet as the canonical packet
        #    for traceability + warnings (it covers all nodes/edges by
        #    construction; the other modes are appended for surface area).
        canonical_packet = _read_packet(mode_dirs["deterministic_outline"])

        # 3. Compose the lesson body and render HTML preview.
        lesson_md_text = _compose_lesson(mode_dirs)
        html_text = _render_html(lesson_md_text)

        # 4. Serialise the canonical LSP to source_packet.json (canonical
        #    JSON: sort_keys=True, indent=2, ensure_ascii=False).
        packet_payload = canonical_packet.model_dump(by_alias=True, mode="json")
        source_packet_text = (
            json.dumps(packet_payload, indent=2, sort_keys=True, ensure_ascii=False)
            + "\n"
        )

        # 5. Build the markdown sidecars.
        traceability_text = _build_traceability(canonical_packet, mode_dirs)
        warnings_text = _build_warnings(canonical_packet)
        feedback_text = _build_feedback_form()

        # 6. Build manifest.json with exactly the 9 schema keys.
        manifest_payload = _build_manifest(canonical_packet)
        manifest_text = (
            json.dumps(manifest_payload, indent=2, sort_keys=True, ensure_ascii=False)
            + "\n"
        )

        # 7. Write all artifacts atomically (overwrite-in-place is fine --
        #    the directory has no other consumers during regen).
        written: dict[str, Path] = {}
        written["generated_lesson.md"] = output_dir / "generated_lesson.md"
        written["generated_preview.html"] = output_dir / "generated_preview.html"
        written["source_packet.json"] = output_dir / "source_packet.json"
        written["traceability.md"] = output_dir / "traceability.md"
        written["warnings.md"] = output_dir / "warnings.md"
        written["feedback_form.md"] = output_dir / "feedback_form.md"
        written["manifest.json"] = output_dir / "manifest.json"
        written["regenerate.sh"] = output_dir / "regenerate.sh"

        written["generated_lesson.md"].write_text(lesson_md_text, encoding="utf-8")
        written["generated_preview.html"].write_text(html_text, encoding="utf-8")
        written["source_packet.json"].write_text(source_packet_text, encoding="utf-8")
        written["traceability.md"].write_text(traceability_text, encoding="utf-8")
        written["warnings.md"].write_text(warnings_text, encoding="utf-8")
        written["feedback_form.md"].write_text(feedback_text, encoding="utf-8")
        written["manifest.json"].write_text(manifest_text, encoding="utf-8")
        written["regenerate.sh"].write_text(_build_regenerate_sh(), encoding="utf-8")
        # Make regenerate.sh executable so a reviewer can run it directly.
        written["regenerate.sh"].chmod(0o755)

        return written
    finally:
        if cleanup_work_dir:
            shutil.rmtree(work_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point used by `regenerate.sh`."""
    parser = argparse.ArgumentParser(
        prog="generate_review_bundle",
        description=(
            "Generate the akms_learn_mvp review bundle from the "
            "fixture graph. Idempotent; uses only akms + akms_learn."
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
            "Optional staging directory for per-mode CLI outputs. Defaults "
            "to a tempdir cleaned up on exit."
        ),
    )
    args = parser.parse_args(argv)

    work_dir = Path(args.work_dir) if args.work_dir else None
    written = generate_review_bundle(output_dir=Path(args.output), work_dir=work_dir)
    for name, path in written.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
