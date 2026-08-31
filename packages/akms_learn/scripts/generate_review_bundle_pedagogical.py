"""Generate the akms_learn_pedagogical review bundle.

This script orchestrates the four the plan learning modes
(``pedagogical_template``, ``derivation_first``, ``implementation_first``,
``multi_granularity``) over the toy fixtures and assembles the
canonical reviewer-facing bundle under::

    artifacts/review_bundles/akms_learn_pedagogical/

The bundle contains exactly the 8 artifacts named in:
``pedagogical_template_lesson.md``, ``derivation_first_lesson.md``,
``implementation_first_lesson.md``, ``generated_preview.html``,
``source_packet.json``, ``traceability.md``, ``warnings.md``,
``feedback_form.md`` -- plus ``manifest.json`` matching the nine-key
schema and a ``regenerate.sh`` runner.

 emits the lesson markdown files, the HTML preview, the canonical
source_packet.json, the manifest and the regenerate.sh script in their
final form. ``traceability.md``, ``warnings.md`` and ``feedback_form.md``
are initial placeholders --  overwrites them with their final content
(the verbatim feedback seed, the section-level traceability table,
and the aggregated warnings list).

Determinism contract
--------------------
The bundle is byte-stable across runs (excluding any LSP ``created_at``
timestamps, which are stripped before hashing per the packet-determinism
convention). Two invocations into distinct output dirs MUST produce
identical artifact bytes after timestamp stripping.

The generator drives ``compile_learning_source`` directly (the Python
API path) because the ``akms-learn compile`` CLI does not yet expose a
flag to select the toy fixtures; the Python API is the contract
mandated by ("implemented akms-learn CLI/API").

`the internal plan`.
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

from akms_learn import LearningSourcePacket
from akms_learn.compiler import compile_learning_source
from akms_learn.requests import LearningRequest
from akms_learn.toy_fixtures import (
    fixture_graph_toy_concept_kit,
    fixture_graph_toy_derivation_gap,
    fixture_graph_toy_executable_bridge,
    fixture_graph_toy_multi_granularity,
)

__all__ = [
    "BUNDLE_ARTIFACTS",
    "LEARNING_MODES",
    "MANIFEST_STATUS",
    "PLAN_ID",
    "_build_closure_md",
    "_build_feedback_form",
    "_build_traceability",
    "_build_warnings",
    "generate_review_bundle_pedagogical",
    "main",
]

# ---------------------------------------------------------------------------
# Constants — schema, verbatim.
# ---------------------------------------------------------------------------

#: The 4 learning modes the bundle must exercise.
LEARNING_MODES: tuple[str, ...] = (
    "pedagogical_template",
    "derivation_first",
    "implementation_first",
    "multi_granularity",
)

#: The 8 artifact filenames mirrored verbatim into manifest.artifacts.
BUNDLE_ARTIFACTS: tuple[str, ...] = (
    "pedagogical_template_lesson.md",
    "derivation_first_lesson.md",
    "implementation_first_lesson.md",
    "generated_preview.html",
    "source_packet.json",
    "traceability.md",
    "warnings.md",
    "feedback_form.md",
)

#: Plan id.
PLAN_ID: str = "akms_learn_pedagogical"

#: Generator identifier. Pinned to the akms-learn package
#: version; bumping the package SHOULD bump this too.
GENERATOR_NAME: str = "akms-learn"
GENERATOR_VERSION: str = "0.1.0"

#: Manifest status string emitted by the generator. The
#: closure rule is responsible for transitioning to later states.
MANIFEST_STATUS: str = "review_bundle_generated"

#: Canonical command string captured into manifest.json. The reviewer runs
#: this from the repo root.
CANONICAL_COMMAND: str = (
    "bash artifacts/review_bundles/akms_learn_pedagogical/regenerate.sh"
)

#: The two granularity variants required by AC-5. ``standard`` is the
#: default fallback so the two explicit values give a clean contrast.
MULTI_GRANULARITY_VARIANTS: tuple[str, ...] = ("overview", "deep_dive")

# Per-mode invocation specs. The CLI cannot select the toy fixtures yet
# (--graph fixture resolves to fixture_graph()) so the generator drives
# the Python API path. Each spec is independent of the others and runs in
# its own work directory so per-mode lesson.md files don't collide.
_MODE_SPECS: dict[str, dict[str, Any]] = {
    "pedagogical_template": {
        "fixture": fixture_graph_toy_concept_kit,
        "topic": "toy concept kit",
        "goal": "Walk through the pedagogical_template 12-section layout.",
    },
    "derivation_first": {
        "fixture": fixture_graph_toy_derivation_gap,
        "topic": "toy derivation gap",
        "goal": "Exercise the derivation_first mode with explicit assumptions.",
    },
    "implementation_first": {
        "fixture": fixture_graph_toy_executable_bridge,
        "topic": "toy executable bridge",
        "goal": "Exercise the implementation_first mode with a code-link bridge.",
    },
    "multi_granularity": {
        "fixture": fixture_graph_toy_multi_granularity,
        "topic": "toy multi-granularity",
        "goal": "Compare overview vs deep_dive granularity variants.",
    },
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_request(
    *, mode: str, topic: str, goal: str, granularity: str | None = None
) -> LearningRequest:
    """Build a deterministic LearningRequest for *mode*.

    No timestamps, no random ids — the request is hash-stable across runs.
    """
    kwargs: dict[str, Any] = dict(
        topic=topic,
        goal=goal,
        audience="engineer",
        depth="implementation",
        generation_option=mode,
        seed_tags=[],
        exporters=["markdown"],
    )
    if granularity is not None:
        kwargs["granularity"] = granularity
    return LearningRequest(**kwargs)


def _run_mode(
    *,
    mode: str,
    output_dir: Path,
    granularity: str | None = None,
) -> LearningSourcePacket:
    """Invoke ``compile_learning_source`` for *mode* into *output_dir*.

    Returns the freshly-compiled :class:`LearningSourcePacket` so the caller
    can compose downstream artifacts (the canonical source_packet.json,
    the warnings list, the traceability surface).
    """
    spec = _MODE_SPECS[mode]
    output_dir.mkdir(parents=True, exist_ok=True)
    request = _build_request(
        mode=mode,
        topic=spec["topic"],
        goal=spec["goal"],
        granularity=granularity,
    )
    graph_slice = spec["fixture"]()
    result = compile_learning_source(
        request=request,
        graph_slice=graph_slice,
        output_dir=output_dir,
    )
    return result.packet


def _read_lesson(mode_dir: Path) -> str:
    """Read the markdown exporter's lesson.md from *mode_dir*."""
    path = mode_dir / "lesson.md"
    if not path.exists():
        raise FileNotFoundError(
            f"lesson.md missing in {mode_dir!r} — markdown exporter did not run"
        )
    return path.read_text(encoding="utf-8")


def _render_html(markdown_text: str) -> str:
    """Render *markdown_text* to a self-contained HTML document.

    Constraints +  spec):
      * No external resources (`<link>`, `<script>` absent by construction).
      * No timestamp strings anywhere in the body.
      * Deterministic — markdown-it-py's commonmark ruleset is pure.
    """
    md = MarkdownIt("commonmark")
    body = md.render(markdown_text)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{PLAN_ID} -- Generated Lesson Preview</title>\n"
        "<style>body{font-family:system-ui,sans-serif;max-width:48rem;"
        "margin:2rem auto;padding:0 1rem;line-height:1.5;}"
        "code{background:#f4f4f4;padding:0.1rem 0.3rem;border-radius:3px;}"
        "pre{background:#f4f4f4;padding:0.75rem;overflow-x:auto;}"
        "hr{border:0;border-top:1px solid #ddd;margin:2rem 0;}</style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}"
        "</body>\n"
        "</html>\n"
    )


def _compose_preview_markdown(
    mode_lessons: dict[str, str],
    multi_gran_variants: dict[str, str],
) -> str:
    """Concatenate per-mode lesson markdown into a single preview body.

    The preview is one human-readable document that surfaces all four
    modes plus both multi_granularity variants for side-by-side review.
    """
    parts: list[str] = []
    parts.append(f"# Review Bundle Preview: {PLAN_ID}")
    parts.append("")
    parts.append(
        "This preview concatenates the four the plan learning modes plus "
        "two granularity variants drawn from the same fixture. Each "
        "section is the verbatim markdown exporter output for that mode."
    )
    parts.append("")
    mode_headings = {
        "pedagogical_template": "Pedagogical template",
        "derivation_first": "Derivation-first",
        "implementation_first": "Implementation-first",
        "multi_granularity": "Multi-granularity",
    }
    for mode in ("pedagogical_template", "derivation_first", "implementation_first"):
        parts.append("---")
        parts.append("")
        parts.append(f"# Mode: {mode_headings[mode]}")
        parts.append("")
        parts.append(mode_lessons[mode].rstrip())
        parts.append("")
    parts.append("---")
    parts.append("")
    parts.append(f"# Mode: {mode_headings['multi_granularity']}")
    parts.append("")
    for variant in MULTI_GRANULARITY_VARIANTS:
        parts.append(f"## Variant: granularity = `{variant}`")
        parts.append("")
        parts.append(multi_gran_variants[variant].rstrip())
        parts.append("")
    return "\n".join(parts) + "\n"


def _packet_to_canonical_json(packet: LearningSourcePacket) -> str:
    """Serialise *packet* to canonical JSON (sort_keys, indent=2)."""
    payload = packet.model_dump(by_alias=True, mode="json")
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _compose_source_packet(
    mode_packets: dict[str, LearningSourcePacket],
    multi_gran_packets: dict[str, LearningSourcePacket],
) -> str:
    """Build the canonical ``source_packet.json`` payload.

    Multiple modes drive multiple LSPs — the file is a top-level object
    keyed by mode (plus the two granularity variants), each value being
    the canonical packet payload. This is the surface  reads when
    building the section-level traceability table.
    """
    payload: dict[str, Any] = {"plan_id": PLAN_ID, "modes": {}}
    for mode in LEARNING_MODES:
        if mode == "multi_granularity":
            payload["modes"][mode] = {
                variant: multi_gran_packets[variant].model_dump(
                    by_alias=True, mode="json"
                )
                for variant in MULTI_GRANULARITY_VARIANTS
            }
        else:
            payload["modes"][mode] = mode_packets[mode].model_dump(
                by_alias=True, mode="json"
            )
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _slug(heading: str) -> str:
    """Convert a section heading to a URL-safe slug for synthetic ids."""
    return re.sub(r"[^a-z0-9]+", "_", heading.lower()).strip("_")


def _extract_sections_from_lesson(lesson_text: str) -> list[str]:
    """Return all ## section headings from *lesson_text* (first occurrence each)."""
    seen: set[str] = set()
    sections: list[str] = []
    for line in lesson_text.splitlines():
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            title = m.group(1).strip()
            if title not in seen:
                seen.add(title)
                sections.append(title)
    return sections


def _build_traceability(
    mode_packets: dict[str, LearningSourcePacket],
    multi_gran_packets: dict[str, LearningSourcePacket],
    mode_lessons: dict[str, str],
    multi_gran_lessons: dict[str, str],
) -> str:
    """Build the section-level traceability table for traceability.md.

    Produces one row per ## heading across the three named lesson files:
    - ``pedagogical_template_lesson.md``
    - ``derivation_first_lesson.md``
    - ``implementation_first_lesson.md`` (includes multi_granularity appendix)

    Columns: ``lesson | section | node_ids | source`` where *source* is
    ``<source_path>:<line_range>`` for nodes that have a direct packet
    anchor, or ``<mode>:<section-slug>`` for boilerplate sections without
    one.

    Plan ref: the internal plan; task  AC-2.
    """

    # Build a lookup: node_id -> (source_path, line_range) per mode.
    def _node_map(packet: LearningSourcePacket) -> dict[str, tuple[str, str]]:
        result: dict[str, tuple[str, str]] = {}
        for node in packet.body.nodes:
            nid = node.node_id or ""
            sp = node.source_path or ""
            lr = node.line_range
            lr_str = f"{lr[0]}-{lr[1]}" if lr and len(lr) == 2 else ""
            result[nid] = (sp, lr_str)
        return result

    # Per-mode: collect node map and provenance from the lesson's ## Provenance
    # section (which lists node_ids).
    def _provenance_node_ids(lesson_text: str) -> list[str]:
        """Extract node ids listed in the ## Provenance section."""
        in_prov = False
        ids: list[str] = []
        for line in lesson_text.splitlines():
            if re.match(r"^##\s+Provenance", line):
                in_prov = True
                continue
            if in_prov and re.match(r"^##\s+", line):
                break
            if in_prov:
                m = re.search(r"\*\*Node ids:\*\*\s+(.+)$", line)
                if m:
                    raw = m.group(1).strip()
                    ids = [
                        nid.strip().strip("`")
                        for nid in raw.split(",")
                        if nid.strip().strip("`")
                    ]
        return ids

    rows: list[str] = []

    # lesson name -> (packet, lesson_text, mode)
    lesson_specs: list[tuple[str, LearningSourcePacket, str, str]] = [
        (
            "pedagogical_template_lesson.md",
            mode_packets["pedagogical_template"],
            mode_lessons["pedagogical_template"],
            "pedagogical_template",
        ),
        (
            "derivation_first_lesson.md",
            mode_packets["derivation_first"],
            mode_lessons["derivation_first"],
            "derivation_first",
        ),
        (
            "implementation_first_lesson.md",
            # Use implementation_first packet for the primary lesson sections;
            # multi_granularity appendix sections reference multi_gran_packets.
            mode_packets["implementation_first"],
            # The full file includes the appendix — build it as the generator does.
            mode_lessons["implementation_first"],
            "implementation_first",
        ),
    ]

    # For the impl lesson the full on-disk file also includes multi_gran appendix
    # sections.  Collect those from multi_gran_lessons directly.
    impl_full_lessons: dict[str, str] = {}
    for variant in MULTI_GRANULARITY_VARIANTS:
        impl_full_lessons[variant] = multi_gran_lessons[variant]

    header = "| lesson | section | node_ids | source |"
    separator = "| --- | --- | --- | --- |"

    lines: list[str] = [
        f"# Traceability -- {PLAN_ID}",
        "",
        "Section-level provenance table mapping each generated-lesson section "
        "to the graph artifacts (packet nodes / source paths) that informed it. "
        "Sections without a direct packet anchor use a synthetic id of the form "
        "`<mode>:<section-slug>`.",
        "",
        "Plan ref: the internal plan; task ref: the internal plan.",
        "",
        header,
        separator,
    ]

    for lesson_name, packet, lesson_text, mode in lesson_specs:
        nmap = _node_map(packet)
        prov_ids = _provenance_node_ids(lesson_text)
        sections = _extract_sections_from_lesson(lesson_text)

        for section in sections:
            sl = _slug(section)
            # Try to find a packet node whose source_path + line_range we can cite.
            # Heuristic: pick the first provenance node (they all back the lesson).
            if prov_ids:
                first_id = prov_ids[0]
                sp, lr = nmap.get(first_id, ("", ""))
                if sp:
                    source = f"`{sp}`:{lr}" if lr else f"`{sp}`"
                    nids = ", ".join(f"`{nid}`" for nid in prov_ids)
                else:
                    source = f"`{mode}:{sl}`"
                    nids = (
                        ", ".join(f"`{nid}`" for nid in prov_ids)
                        if prov_ids
                        else f"`{mode}:{sl}`"
                    )
            else:
                source = f"`{mode}:{sl}`"
                nids = f"`{mode}:{sl}`"
            rows.append(
                f"| `{_md_escape_pipe(lesson_name)}`"
                f" | {_md_escape_pipe(section)}"
                f" | {_md_escape_pipe(nids)}"
                f" | {_md_escape_pipe(source)} |"
            )

    # The generator injects a static appendix heading into implementation_first_lesson.md.
    # Add a synthetic row for it so the traceability table covers every ## heading.
    rows.append(
        "| `implementation_first_lesson.md` | Appendix: multi_granularity variants (same fixture)"
        " | `implementation_first:appendix_multi_granularity_variants_same_fixture`"
        " | `implementation_first:appendix_multi_granularity_variants_same_fixture` |"
    )

    # Also cover multi_granularity appendix sections in implementation_first_lesson.md
    for variant in MULTI_GRANULARITY_VARIANTS:
        pkt = multi_gran_packets[variant]
        nmap = _node_map(pkt)
        lesson_text = impl_full_lessons[variant]
        prov_ids = _provenance_node_ids(lesson_text)
        sections = _extract_sections_from_lesson(lesson_text)
        for section in sections:
            sl = _slug(section)
            if prov_ids:
                first_id = prov_ids[0]
                sp, lr = nmap.get(first_id, ("", ""))
                if sp:
                    source = f"`{sp}`:{lr}" if lr else f"`{sp}`"
                    nids = ", ".join(f"`{nid}`" for nid in prov_ids)
                else:
                    source = f"`multi_granularity:{sl}`"
                    nids = ", ".join(f"`{nid}`" for nid in prov_ids)
            else:
                source = f"`multi_granularity:{sl}`"
                nids = f"`multi_granularity:{sl}`"
            rows.append(
                f"| `implementation_first_lesson.md` (appendix:{_md_escape_pipe(variant)}) "
                f"| {_md_escape_pipe(section)}"
                f" | {_md_escape_pipe(nids)}"
                f" | {_md_escape_pipe(source)} |"
            )

    lines.extend(rows)
    lines.append("")
    return "\n".join(lines)


def _aggregate_warnings(
    mode_packets: dict[str, LearningSourcePacket],
    multi_gran_packets: dict[str, LearningSourcePacket],
) -> list[dict[str, str]]:
    """Return the unique warning entries across all packet sources.

    Walks the per-mode packets and the multi_granularity variant packets in
    a deterministic order (`LEARNING_MODES` then `MULTI_GRANULARITY_VARIANTS`),
    dedupes by the ``(code, source_ref, message)`` triple, and sorts by the
    same triple before returning. Each entry also carries the ``severity``
    string taken from the first occurrence of the deduped triple.

    Single source of truth — both ``warnings.md`` and ``manifest.warnings``
    call this helper so the two surfaces never drift out of sync.
    """
    aggregated: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(packet: LearningSourcePacket) -> None:
        for w in packet.warnings:
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

    for mode in LEARNING_MODES:
        if mode == "multi_granularity":
            for variant in MULTI_GRANULARITY_VARIANTS:
                _add(multi_gran_packets[variant])
        else:
            _add(mode_packets[mode])

    aggregated.sort(key=lambda w: (w["code"], w["source_ref"], w["message"]))
    return aggregated


def _md_escape_pipe(text: str) -> str:
    """Escape pipe characters so *text* is safe inside a markdown table cell.

    A bare ``|`` inside a cell breaks the surrounding table layout. Section
    titles, source paths, and node ids all come from fixture / packet data
    that we don't fully control, so defensive escaping here keeps the
    traceability table well-formed against any future fixture content.
    """
    return text.replace("|", "\\|")


def _build_warnings(
    mode_packets: dict[str, LearningSourcePacket],
    multi_gran_packets: dict[str, LearningSourcePacket],
) -> str:
    """Build warnings.md mirroring the aggregated manifest warnings list.

    One line per unique warning entry (same dedup logic as _build_manifest;
    both surfaces share :func:`_aggregate_warnings`). If the aggregated list
    is empty, writes a single ``no warnings`` line.

    Plan ref: the internal plan; task  AC-3.
    """
    aggregated = _aggregate_warnings(mode_packets, multi_gran_packets)

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

    The content is reproduced byte-for-byte from the plan.md.
    The title slug is ``akms_learn_pedagogical`` per the plan.

    Plan ref: the internal plan; task  AC-1.
    """
    return (
        "# Review Feedback: akms_learn_pedagogical\n"
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


def _build_closure_md() -> str:
    """Write CLOSURE.md with the closure-rule quote and gate conditions.

    Contains both canary tokens checked by AC-5:
      - ``plan_closed``
      - ``MUST NOT``

    CLOSURE.md is NOT in BUNDLE_ARTIFACTS and is not listed in manifest.artifacts.
    It lives at the bundle root as a sibling to manifest.json and regenerate.sh.

    Plan ref: the internal plan; task  AC-5.
    """
    return (
        f"# Closure Gate -- {PLAN_ID}\n"
        "\n"
        "## Closure rule\n"
        "\n"
        "> A coding agent MUST NOT mark this plan `plan_closed` until the bundle "
        "validates, the bundle is ready for external review, and received feedback "
        "is incorporated, converted into follow-up tasks, or explicitly deferred "
        "with rationale.\n"
        "\n"
        "## Gate conditions\n"
        "\n"
        "Before this plan may be marked `plan_closed`, ALL of the following must hold:\n"
        "\n"
        "1. **Bundle validates** — `uv run pytest packages/akms_learn/tests/ -q` "
        "passes with zero failures.\n"
        "2. **Bundle is ready for external review** — "
        "all eight artifacts are present in "
        "`artifacts/review_bundles/akms_learn_pedagogical/` and "
        '`manifest.status` is `"review_bundle_generated"`.\n'
        "3. **Feedback is incorporated** — reviewer feedback recorded in "
        "`feedback_form.md` has been:\n"
        "   - incorporated into the bundle, OR\n"
        "   - converted into follow-up tasks, OR\n"
        "   - explicitly deferred with written rationale.\n"
        "\n"
        "## Current status\n"
        "\n"
        '``manifest.status`` is locked to ``"review_bundle_generated"`` by the '
        'generator. No automated path may write ``"plan_closed"`` to the manifest. '
        "Transitioning to ``plan_closed`` is a **manual** developer action, gated "
        "on the three conditions above.\n"
        "\n"
        "## Feedback form\n"
        "\n"
        "The reviewer-facing feedback form is at "
        "`artifacts/review_bundles/akms_learn_pedagogical/feedback_form.md`.\n"
        "\n"
        "Plan ref: the internal plan; "
        "task ref: the internal plan.\n"
    )


def _build_manifest(
    mode_packets: dict[str, LearningSourcePacket],
    multi_gran_packets: dict[str, LearningSourcePacket],
) -> dict[str, Any]:
    """Build manifest.json with exactly the 9 keys, verbatim ordering.

    Aggregates warnings across every mode + variant (sorted by code,
    then source_ref, then message) so the reviewer sees a single
    consolidated list. ``unavailable_capabilities`` is empty because
    every required the plan mode is implemented (..).
    """
    aggregated = _aggregate_warnings(mode_packets, multi_gran_packets)

    return {
        "plan_id": PLAN_ID,
        "status": MANIFEST_STATUS,
        "generator": GENERATOR_NAME,
        "generator_version": GENERATOR_VERSION,
        "command": CANONICAL_COMMAND,
        "learning_modes_used": list(LEARNING_MODES),
        "artifacts": list(BUNDLE_ARTIFACTS),
        "warnings": aggregated,
        "unavailable_capabilities": [],
    }


def _build_regenerate_sh() -> str:
    """Return the text of ``regenerate.sh``.

    The script:
      * sets ``PYTHONHASHSEED=0`` for deterministic dict ordering
        (defensive — the compiler is already determinism-tested),
      * resolves the repo root from the script's location,
      * uses ``uv run --package akms-learn`` so no companion package is
        needed.
    """
    return (
        "#!/usr/bin/env bash\n"
        "# Regenerate the review bundle deterministically from the\n"
        "# the plan toy fixtures. Idempotent: safe to re-run.\n"
        "#\n"
        "# Plan ref: the internal plan; task ref: the internal plan\n"
        "# Generator: packages/akms_learn/scripts/generate_review_bundle_pedagogical.py\n"
        "set -euo pipefail\n"
        "\n"
        'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"\n'
        'cd "${REPO_ROOT}"\n'
        "\n"
        "export PYTHONHASHSEED=0\n"
        "\n"
        "uv run --package akms-learn python \\\n"
        "    packages/akms_learn/scripts/generate_review_bundle_pedagogical.py \\\n"
        '    --output "${REPO_ROOT}/artifacts/review_bundles/' + PLAN_ID + '"\n'
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_review_bundle_pedagogical(
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
        ``None`` a temporary directory is used and deleted on exit.
        Tests pass an explicit path so they can inspect intermediates.

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
        work_dir = Path(tempfile.mkdtemp(prefix="akms_learn_bundle_plan2_"))
        cleanup_work_dir = True
    else:
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 1. Run the API once per single-variant mode.
        mode_packets: dict[str, LearningSourcePacket] = {}
        mode_lessons: dict[str, str] = {}
        for mode in (
            "pedagogical_template",
            "derivation_first",
            "implementation_first",
        ):
            mode_dir = work_dir / mode
            mode_packets[mode] = _run_mode(mode=mode, output_dir=mode_dir)
            mode_lessons[mode] = _read_lesson(mode_dir)

        # 2. Run multi_granularity twice, once per granularity variant.
        multi_gran_packets: dict[str, LearningSourcePacket] = {}
        multi_gran_lessons: dict[str, str] = {}
        for variant in MULTI_GRANULARITY_VARIANTS:
            mode_dir = work_dir / f"multi_granularity_{variant}"
            multi_gran_packets[variant] = _run_mode(
                mode="multi_granularity",
                output_dir=mode_dir,
                granularity=variant,
            )
            multi_gran_lessons[variant] = _read_lesson(mode_dir)

        # 3. Compose preview markdown + HTML.
        preview_markdown = _compose_preview_markdown(mode_lessons, multi_gran_lessons)
        html_text = _render_html(preview_markdown)

        # 4. Build the canonical source_packet.json (aggregates all packets).
        source_packet_text = _compose_source_packet(mode_packets, multi_gran_packets)

        # 5. Per-mode lesson files — these are 's three final outputs.
        ped_lesson_text = mode_lessons["pedagogical_template"]
        der_lesson_text = mode_lessons["derivation_first"]
        # implementation_first folds in both multi_granularity variants so
        # AC-5 (two variants from the same fixture) is satisfied by an
        # artifact reviewers will read end-to-end.
        impl_lesson_text = mode_lessons["implementation_first"].rstrip() + "\n"
        impl_lesson_text += (
            "\n---\n"
            "\n## Appendix: multi_granularity variants (same fixture)\n"
            "\n"
            "The two sections below were generated from the same "
            "`fixture_graph_toy_multi_granularity` slice; they differ only "
            "in the request's `granularity` field. `granularity` is excluded "
            "from `NORMALIZED_FIELDS`, so the two requests hash identically — "
            "but it does select the rendered node subset: `overview` drops "
            "`fine`-marked nodes (keeping coarse/standard), while `deep_dive` "
            "keeps every node. Compare the Concept map and reading order "
            "between the variants — the `overview` body omits the "
            "`fine_detail_*` nodes that `deep_dive` includes (AC-5).\n"
        )
        for variant in MULTI_GRANULARITY_VARIANTS:
            impl_lesson_text += (
                f"\n### Variant: granularity = `{variant}`\n\n"
                + multi_gran_lessons[variant].rstrip()
                + "\n"
            )

        # 6.  final content — traceability, warnings, feedback form, closure.
        traceability_text = _build_traceability(
            mode_packets, multi_gran_packets, mode_lessons, multi_gran_lessons
        )
        warnings_text = _build_warnings(mode_packets, multi_gran_packets)
        feedback_text = _build_feedback_form()
        closure_text = _build_closure_md()

        # 7. Manifest.
        manifest_payload = _build_manifest(mode_packets, multi_gran_packets)
        manifest_text = (
            json.dumps(manifest_payload, indent=2, sort_keys=True, ensure_ascii=False)
            + "\n"
        )

        # 8. Write everything.
        written: dict[str, Path] = {}
        written["pedagogical_template_lesson.md"] = (
            output_dir / "pedagogical_template_lesson.md"
        )
        written["derivation_first_lesson.md"] = (
            output_dir / "derivation_first_lesson.md"
        )
        written["implementation_first_lesson.md"] = (
            output_dir / "implementation_first_lesson.md"
        )
        written["generated_preview.html"] = output_dir / "generated_preview.html"
        written["source_packet.json"] = output_dir / "source_packet.json"
        written["traceability.md"] = output_dir / "traceability.md"
        written["warnings.md"] = output_dir / "warnings.md"
        written["feedback_form.md"] = output_dir / "feedback_form.md"
        written["manifest.json"] = output_dir / "manifest.json"
        written["regenerate.sh"] = output_dir / "regenerate.sh"
        # CLOSURE.md is a bundle-root sibling — NOT in BUNDLE_ARTIFACTS / manifest.artifacts.
        written["CLOSURE.md"] = output_dir / "CLOSURE.md"

        written["pedagogical_template_lesson.md"].write_text(
            ped_lesson_text, encoding="utf-8"
        )
        written["derivation_first_lesson.md"].write_text(
            der_lesson_text, encoding="utf-8"
        )
        written["implementation_first_lesson.md"].write_text(
            impl_lesson_text, encoding="utf-8"
        )
        written["generated_preview.html"].write_text(html_text, encoding="utf-8")
        written["source_packet.json"].write_text(source_packet_text, encoding="utf-8")
        written["traceability.md"].write_text(traceability_text, encoding="utf-8")
        written["warnings.md"].write_text(warnings_text, encoding="utf-8")
        written["feedback_form.md"].write_text(feedback_text, encoding="utf-8")
        written["manifest.json"].write_text(manifest_text, encoding="utf-8")
        written["regenerate.sh"].write_text(_build_regenerate_sh(), encoding="utf-8")
        written["regenerate.sh"].chmod(0o755)
        written["CLOSURE.md"].write_text(closure_text, encoding="utf-8")

        return written
    finally:
        if cleanup_work_dir:
            shutil.rmtree(work_dir, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point used by ``regenerate.sh``."""
    parser = argparse.ArgumentParser(
        prog="generate_review_bundle_pedagogical",
        description=(
            "Generate the akms_learn_pedagogical review bundle "
            "from the toy fixtures. Idempotent; uses only "
            "akms + akms_learn."
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
            "Optional staging directory for per-mode outputs. Defaults to "
            "a tempdir cleaned up on exit."
        ),
    )
    args = parser.parse_args(argv)

    work_dir = Path(args.work_dir) if args.work_dir else None
    written = generate_review_bundle_pedagogical(
        output_dir=Path(args.output), work_dir=work_dir
    )
    for name, path in written.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
