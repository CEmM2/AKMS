#!/usr/bin/env python3
"""Built-in YAML -> Markdown converter for generated AKMS nodes.

The ``nlm_batch`` generator emits one YAML file per node combining v2 schema
frontmatter fields (``id``, ``title``, ``edges``, …) with structured body
content (``summary``, ``core_concept``, ``math_formulation``, ``algorithms``,
``pitfalls``, ``references``). This converter splits that single document into a
canonical AKMS ``.md`` node: YAML frontmatter (``---`` fenced) followed by the
markdown sections the v2 schema/validator expects.

Usage:
    python -m akms_nodes_gen.tools.yaml_to_markdown <node.yaml> [-v]
    python yaml_to_markdown.py <node.yaml> [--output other.md] [-v]

It writes a sibling ``<node>.md`` (same basename) by default and exits 0 on
success, non-zero with a message on failure. This matches the call contract in
``nlm_batch._run_postprocessors`` (``python <converter> <yaml_path> -v``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

# Frontmatter keys recognized by the AKMS v2 schema / node_validator. Everything
# else in the source YAML is treated as body content (or dropped, e.g. helper
# scaffolding). Order here is the order they are emitted in the frontmatter.
FRONTMATTER_KEYS: tuple[str, ...] = (
    "id",
    "title",
    "domain",
    "subdomain",
    "tags",
    "status",
    "confidence",
    "source",
    "confidence_floor",
    "edges",
    "load_with",
    "context_size",
    "reading_priority",
    "content_ref",
    "akms_schema",
)

# Body keys consumed for section rendering (so they are not mistaken for unknown).
_BODY_KEYS = {
    "summary",
    "core_concept",
    "math_formulation",
    "algorithms",
    "pitfalls",
    "references",
}


def _as_text(value: Any) -> str:
    """Best-effort render a scalar/sequence value as markdown text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple)):
        return "\n".join(f"- {_as_text(item)}" for item in value if item is not None)
    return str(value).strip()


def _render_equations(math: Any) -> list[str]:
    lines: list[str] = []
    if isinstance(math, dict):
        notation = math.get("notation") or math.get("symbols")
        equations = math.get("equations") or []
        if isinstance(equations, list):
            for eq in equations:
                if isinstance(eq, dict):
                    label = eq.get("label") or eq.get("name")
                    latex = eq.get("latex") or eq.get("equation") or ""
                    src = eq.get("source_ref") or eq.get("source") or eq.get("citation")
                    if label:
                        lines.append(f"**{label}**")
                    if latex:
                        lines.append(f"$$\n{str(latex).strip()}\n$$")
                    if src:
                        lines.append(f"_Source: {src}_")
                    lines.append("")
                else:
                    lines.append(f"$$\n{_as_text(eq)}\n$$")
                    lines.append("")
        if notation:
            lines.append("**Notation:**")
            lines.append(_as_text(notation))
            lines.append("")
    elif math:
        lines.append(_as_text(math))
    return lines


def _render_algorithms(algorithms: Any) -> list[str]:
    lines: list[str] = []
    if not isinstance(algorithms, list):
        if algorithms:
            lines.append(_as_text(algorithms))
        return lines
    for algo in algorithms:
        if not isinstance(algo, dict):
            lines.append(_as_text(algo))
            continue
        label = algo.get("label") or algo.get("name")
        if label:
            lines.append(f"**{label}**")
        steps = algo.get("steps")
        if isinstance(steps, list) and steps:
            step_lines: list[str] = ["$$", "\\begin{algorithmic}"]
            for step in steps:
                if isinstance(step, dict):
                    cmd = str(step.get("cmd") or step.get("command") or "State").strip()
                    math = str(step.get("math") or step.get("expr") or "").strip()
                    if cmd in {"State", "Return"}:
                        text = f"\\{cmd} ${math}$" if math else f"\\{cmd}"
                    elif cmd in {"For", "While", "If", "ElsIf"}:
                        text = f"\\{cmd}{{${math}$}}"
                    elif cmd in {"Else", "EndIf", "EndFor", "EndWhile"}:
                        text = f"\\{cmd}"
                    else:
                        # Backward compatibility for older generated nodes whose
                        # ``cmd`` value was a descriptive label rather than an
                        # algpseudocode command.
                        label = cmd.replace("\\", r"\\textbackslash{}")
                        text = f"\\State \\text{{{label}}}"
                        if math:
                            text += f": ${math}$"
                else:
                    text = f"\\State \\text{{{_as_text(step)}}}"
                step_lines.append(text)
            step_lines.extend(["\\end{algorithmic}", "$$"])
            lines.extend(step_lines)
        body = algo.get("body") or algo.get("description")
        if body:
            lines.append(_as_text(body))
        mapping = algo.get("taichi_mapping") or algo.get("mapping")
        if mapping:
            lines.append(f"Taichi Mapping: {_as_text(mapping)}")
        src = algo.get("source_ref") or algo.get("source") or algo.get("citation")
        if src:
            lines.append(f"_Source: {src}_")
        lines.append("")
    return lines


def _render_pitfalls(pitfalls: Any) -> list[str]:
    lines: list[str] = []
    if not isinstance(pitfalls, list):
        if pitfalls:
            lines.append(_as_text(pitfalls))
        return lines
    for pitfall in pitfalls:
        if isinstance(pitfall, dict):
            name = pitfall.get("name") or pitfall.get("title")
            desc = pitfall.get("description") or pitfall.get("detail") or ""
            src = (
                pitfall.get("source_ref")
                or pitfall.get("source")
                or pitfall.get("citation")
            )
            head = f"- **{name}**: {_as_text(desc)}" if name else f"- {_as_text(desc)}"
            if src:
                head = f"{head} _(Source: {src})_"
            lines.append(head)
        else:
            lines.append(f"- {_as_text(pitfall)}")
    return lines


def build_markdown(data: dict[str, Any]) -> str:
    """Render an AKMS node ``.md`` string from a generated YAML mapping."""
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping, got {type(data).__name__}")
    if not data.get("id"):
        raise ValueError("Source YAML is missing required field 'id'")
    if not data.get("title"):
        raise ValueError("Source YAML is missing required field 'title'")

    frontmatter = {key: data[key] for key in FRONTMATTER_KEYS if key in data}
    fm_yaml = yaml.safe_dump(
        frontmatter,
        sort_keys=False,
        allow_unicode=True,
        width=120,
        default_flow_style=False,
    ).rstrip()

    parts: list[str] = ["---", fm_yaml, "---", "", f"# {data['title']}", ""]

    summary = _as_text(data.get("summary"))
    parts.extend(["## Summary", "", summary or "_No summary provided._", ""])

    core = _as_text(data.get("core_concept"))
    if core:
        parts.extend(["## 1. Core Concept", "", core, ""])

    math_lines = _render_equations(data.get("math_formulation"))
    if math_lines:
        parts.extend(["## 2. Mathematical Formulation", ""])
        parts.extend(math_lines)
        parts.append("")

    algo_lines = _render_algorithms(data.get("algorithms"))
    if algo_lines:
        parts.extend(["## 3. Algorithmic Implementation", ""])
        parts.extend(algo_lines)
        parts.append("")

    pitfall_lines = _render_pitfalls(data.get("pitfalls"))
    if pitfall_lines:
        parts.extend(["## 4. Known Pitfalls", ""])
        parts.extend(pitfall_lines)
        parts.append("")

    references = data.get("references")
    if references:
        parts.extend(["## References", "", _as_text(references), ""])

    text = "\n".join(parts).rstrip() + "\n"
    return text


def convert_file(yaml_path: Path, output_path: Path | None = None) -> Path:
    """Convert a single YAML node file to a sibling ``.md`` and return its path."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"YAML file not found: {yaml_path}")
    raw = yaml_path.read_text(encoding="utf-8")
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ValueError(f"Could not parse YAML {yaml_path}: {exc}") from exc
    markdown = build_markdown(data)
    out = output_path or yaml_path.with_suffix(".md")
    out.write_text(markdown, encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert a generated AKMS node YAML to a schema-shaped .md."
    )
    parser.add_argument(
        "yaml_path", type=Path, help="Path to the generated node YAML file"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output .md path (default: sibling .md)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print the written path"
    )
    args = parser.parse_args(argv)

    try:
        out = convert_file(args.yaml_path, args.output)
    except Exception as exc:  # noqa: BLE001 - surface a clean message + nonzero exit
        print(f"yaml_to_markdown: conversion failed: {exc}", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"yaml_to_markdown: wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
