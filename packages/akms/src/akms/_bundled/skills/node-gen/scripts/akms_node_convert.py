#!/usr/bin/env python3
"""akms_node_convert.py — Convert structured YAML node output to AKMS markdown.

The Gemini Gem outputs nodes as pure YAML. This script converts them to the
final AKMS .md format (YAML frontmatter + structured markdown body).

Usage:
    python akms_node_convert.py node.yaml                # → node.md
    python akms_node_convert.py node.yaml -o output.md
    python akms_node_convert.py nodes_yaml/              # Batch convert directory
    python akms_node_convert.py node.yaml -v
"""

import argparse
import sys
import yaml
from pathlib import Path


# ── YAML → Markdown conversion ────────────────────────────────────────


def convert_node(data: dict) -> tuple[str, list[str]]:
    """Convert a structured YAML node dict to AKMS markdown string.
    Returns (markdown_string, list_of_warnings).
    """
    warnings = []

    # ── Build frontmatter ──
    fm = {}
    fm["id"] = data["id"]
    fm["title"] = data["title"]
    fm["domain"] = data.get("domain", "computational-mechanics")
    if data.get("subdomain"):
        fm["subdomain"] = data["subdomain"]
    fm["tags"] = data.get("tags", [])
    fm["status"] = "tentative"
    fm["confidence"] = data.get("confidence", 0.90)
    fm["source"] = "hybrid"
    if data.get("confidence_floor"):
        fm["confidence_floor"] = data["confidence_floor"]
    fm["edges"] = data.get("edges", [])
    fm["context_size"] = data.get("context_size", "medium")
    fm["reading_priority"] = data.get("reading_priority", "full")
    if data.get("load_with"):
        fm["load_with"] = data["load_with"]
    fm["content_ref"] = None
    fm["akms_schema"] = "v2"

    # ── Build body ──
    lines = []

    # Title
    lines.append(f"# {data['title']}")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append(data.get("summary", "[MISSING — developer must supplement]"))
    lines.append("")

    # 1. Core Concept
    lines.append("## 1. Core Concept")
    lines.append(data.get("core_concept", "[MISSING — developer must supplement]"))
    lines.append("")

    # 2. Mathematical Formulation
    lines.append("## 2. Mathematical Formulation")
    math = data.get("math_formulation", {})
    if isinstance(math, str):
        # Simple string with inline LaTeX
        lines.append(math)
    elif isinstance(math, dict):
        # Structured: prose + equations list
        if math.get("prose"):
            lines.append(math["prose"])
            lines.append("")
        for eq in math.get("equations", []):
            if isinstance(eq, dict):
                if eq.get("label"):
                    lines.append(f"**{eq['label']}:**")
                    lines.append("")
                lines.append("$$")
                lines.append(eq["latex"].strip())
                lines.append("$$")
                lines.append("")
                if eq.get("where"):
                    lines.append(f"where {eq['where']}")
                    lines.append("")
            else:
                # Plain LaTeX string
                lines.append("$$")
                lines.append(str(eq).strip())
                lines.append("$$")
                lines.append("")

        # Notation table
        if math.get("notation"):
            lines.append("**Notation:**")
            lines.append("")
            for symbol, meaning in math["notation"].items():
                lines.append(f"- ${symbol}$ — {meaning}")
            lines.append("")
    lines.append("")

    # 3. Algorithmic Implementation
    lines.append("## 3. Algorithmic Implementation")
    algos = data.get("algorithms", [])
    if isinstance(algos, str):
        lines.append(algos)
    else:
        for algo in algos:
            if isinstance(algo, dict):
                label = algo.get("label", "Algorithm")
                lines.append(f"**Algorithm: {label}**")
                lines.append("")
                lines.append("$$")
                lines.append(r"\begin{algorithmic}")

                for step in algo.get("steps", []):
                    if isinstance(step, dict):
                        cmd = step.get("cmd", "State")
                        math_content = step.get("math", "")
                        indent = "    " * step.get("indent", 0)

                        if cmd == "State":
                            lines.append(f"{indent}\\State ${math_content}$")
                        elif cmd == "For":
                            lines.append(f"{indent}\\For{{${math_content}$}}")
                        elif cmd == "EndFor":
                            lines.append(f"{indent}\\EndFor")
                        elif cmd == "While":
                            lines.append(f"{indent}\\While{{${math_content}$}}")
                        elif cmd == "EndWhile":
                            lines.append(f"{indent}\\EndWhile")
                        elif cmd == "If":
                            lines.append(f"{indent}\\If{{${math_content}$}}")
                        elif cmd == "ElsIf":
                            lines.append(f"{indent}\\ElsIf{{${math_content}$}}")
                        elif cmd == "Else":
                            lines.append(f"{indent}\\Else")
                        elif cmd == "EndIf":
                            lines.append(f"{indent}\\EndIf")
                        elif cmd == "Return":
                            lines.append(f"{indent}\\Return ${math_content}$")
                        elif cmd == "Break":
                            lines.append(f"{indent}\\State \\textbf{{break}}")
                        else:
                            warnings.append(f"Unknown command: {cmd}")
                            lines.append(f"{indent}\\State ${math_content}$")
                    else:
                        # Raw string step — pass through
                        lines.append(f"\\State ${step}$")

                lines.append(r"\end{algorithmic}")
                lines.append("$$")
                lines.append("")

                # Taichi mapping
                if algo.get("taichi_mapping"):
                    lines.append("**Taichi Mapping:**")
                    lines.append(algo["taichi_mapping"])
                    lines.append("")
            else:
                lines.append(str(algo))
    lines.append("")

    # 4. Known Pitfalls
    lines.append("## 4. Known Pitfalls")
    pitfalls = data.get("pitfalls", [])
    for p in pitfalls:
        if isinstance(p, dict):
            lines.append(f"**{p.get('name', 'Pitfall')}:** {p.get('description', '')}")
            lines.append("")
        else:
            lines.append(f"**Pitfall:** {p}")
            lines.append("")

    # 5. Verification & Benchmarks (optional)
    if data.get("verification"):
        lines.append("## 5. Verification & Benchmarks")
        lines.append(data["verification"])
        lines.append("")

    # 6. References (optional)
    refs = data.get("references", [])
    if refs:
        next_section = 5 if not data.get("verification") else 6
        lines.append(f"## {next_section}. References")
        for ref in refs:
            lines.append(f"- {ref}")
        lines.append("")

    # ── Assemble ──
    frontmatter_str = yaml.dump(
        fm, default_flow_style=False, sort_keys=False, allow_unicode=True, width=120
    )
    body_str = "\n".join(lines)

    return f"---\n{frontmatter_str}---\n\n{body_str}\n", warnings


# ── Validation ────────────────────────────────────────────────────────


def validate_yaml_node(data: dict) -> list[str]:
    """Validate required fields in the YAML input."""
    errors = []

    for field in ["id", "title", "summary", "core_concept", "math_formulation"]:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    if "algorithms" not in data or not data["algorithms"]:
        errors.append("Missing or empty algorithms field")

    if "pitfalls" not in data or not data["pitfalls"]:
        errors.append("Missing or empty pitfalls field")

    if "edges" not in data or not data["edges"]:
        errors.append("Missing or empty edges field")

    # Self-containedness check on string fields
    for field in ["core_concept", "summary"]:
        val = data.get(field, "")
        if isinstance(val, str):
            import re

            eq_refs = re.findall(r"(?:Eq\.|Equation)\s*[\(\[]?\d+", val)
            for ref in eq_refs:
                errors.append(f'Equation reference in {field}: "{ref}"')

    return errors


# ── CLI ───────────────────────────────────────────────────────────────


def process_file(filepath: Path, output: Path | None, verbose: bool) -> bool:
    text = filepath.read_text(encoding="utf-8")

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        print(f"  ✗ YAML parse error in {filepath}: {e}")
        return False

    if not isinstance(data, dict):
        print(f"  ✗ {filepath}: Expected YAML mapping, got {type(data).__name__}")
        return False

    # Validate
    errors = validate_yaml_node(data)
    if errors:
        print(f"\n{'─' * 60}")
        print(f"  {filepath.name}")
        print(f"{'─' * 60}")
        for e in errors:
            print(f"  ✗ {e}")
        print()

    # Convert
    md, warnings = convert_node(data)

    if warnings and verbose:
        for w in warnings:
            print(f"  ⚠ {w}")

    # Write
    target = output or filepath.with_suffix(".md")
    target.write_text(md, encoding="utf-8")
    if verbose:
        print(f"  → {target}")

    return len(errors) == 0


def main():
    parser = argparse.ArgumentParser(description="Convert YAML AKMS nodes to markdown")
    parser.add_argument("input", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=None)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.input.is_dir():
        files = sorted(args.input.glob("*.yaml")) + sorted(args.input.glob("*.yml"))
        if not files:
            print(f"No YAML files in {args.input}")
            sys.exit(1)
        ok = all(process_file(f, None, args.verbose) for f in files)
        print(f"\n{'✓ All converted' if ok else '✗ Errors found'}")
        sys.exit(0 if ok else 1)
    else:
        if not args.input.exists():
            print(f"Not found: {args.input}")
            sys.exit(1)
        ok = process_file(args.input, args.output, args.verbose)
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
