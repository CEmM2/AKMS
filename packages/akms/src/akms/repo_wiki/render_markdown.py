"""Deterministic Markdown rendering."""

from __future__ import annotations

import subprocess
from pathlib import Path

from akms.repo_wiki.hashing import sha256_text
from akms.repo_wiki.models import ParsedModule, Symbol
from akms.repo_wiki.paths import ensure_parent, read_source, safe_doc_name


def repo_commit(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def render_all(
    parsed_modules: list[ParsedModule], repo_root: Path, config: dict[str, object]
) -> tuple[list[Path], list[Path], Path | None]:
    generation = config["generation"] if isinstance(config["generation"], dict) else {}
    output_dir = repo_root / str(generation.get("output_dir", ".repo_wiki/generated"))
    commit = repo_commit(repo_root)
    module_docs: list[Path] = []
    symbol_docs: list[Path] = []
    if generation.get("generate_module_docs", True):
        for parsed in parsed_modules:
            module_docs.append(
                write_module_doc(parsed, output_dir, commit, repo_root.name, repo_root)
            )
    if generation.get("generate_symbol_docs", True):
        for parsed in parsed_modules:
            for symbol in parsed.symbols:
                symbol_docs.append(
                    write_symbol_doc(
                        symbol, output_dir, commit, repo_root.name, None, repo_root
                    )
                )
    repo_map = (
        write_repo_map(parsed_modules, output_dir, commit, repo_root.name, repo_root)
        if generation.get("generate_repo_map", True)
        else None
    )
    return module_docs, symbol_docs, repo_map


def frontmatter(data: dict[str, object]) -> str:
    lines = ["---"]
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif value is None:
            lines.append(f"{key}: null")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def write_module_doc(
    parsed: ParsedModule, output_dir: Path, commit: str, repo_name: str, repo_root: Path
) -> Path:
    path = output_dir / "modules" / f"{safe_doc_name(parsed.module)}.md"
    ensure_parent(path)
    symbols = [symbol.symbol_id for symbol in parsed.symbols]
    lines = [
        frontmatter(
            {
                "doc_type": "module",
                "repo": repo_name,
                "path": parsed.source_file.path,
                "module": parsed.module,
                "language": parsed.source_file.language,
                "repo_commit": commit,
                "source_hash": parsed.source_file.content_hash,
                "symbols": symbols,
            }
        ),
        f"# Module: {parsed.module}\n",
        f"Source: `{parsed.source_file.path}`\n",
        "## Module Docstring\n",
        (parsed.docstring or "_No module docstring._") + "\n",
        "## Imports\n",
        "\n".join(f"- `{item}`" for item in parsed.imports) or "_No imports._",
        "\n## Code Structure\n",
    ]
    for symbol in parsed.symbols:
        level = "##" if symbol.kind in {"class", "function", "constant"} else "###"
        lines.extend(render_symbol_section(symbol, level, repo_root))
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def write_symbol_doc(
    symbol: Symbol,
    output_dir: Path,
    commit: str,
    repo_name: str,
    summary: str | None,
    repo_root: Path,
) -> Path:
    path = output_dir / "symbols" / f"{safe_doc_name(symbol.symbol_id)}.md"
    ensure_parent(path)
    source_text = read_source(symbol.span, repo_root)
    fm: dict[str, object] = {
        "doc_type": "symbol",
        "repo": repo_name,
        "path": symbol.path,
        "module": symbol.module,
        "symbol_id": symbol.symbol_id,
        "kind": symbol.kind,
        "parent_id": symbol.parent_id,
        "language": symbol.language.value,
        "start_line": symbol.start_line,
        "end_line": symbol.end_line,
        "repo_commit": commit,
        "source_hash": sha256_text(source_text),
        "calls": symbol.calls,
    }
    # Generic metadata (e.g. C++ visibility); empty for Python symbols.
    for key, value in symbol.metadata.items():
        fm[key] = value
    lines = [
        frontmatter(fm),
        f"# {symbol.symbol_id}\n",
        f"Source: `{symbol.path}`  \nLines: `{symbol.start_line}-{symbol.end_line}`  \nKind: `{symbol.kind}`\n",
    ]
    if symbol.parent_id:
        lines.append(f"Parent: `{symbol.parent_id}`\n")
    fence = symbol.language.value
    if symbol.signature:
        lines.append(f"## Signature\n```{fence}\n" + symbol.signature + "\n```\n")
    if symbol.docstring:
        lines.append("## Docstring\n" + symbol.docstring + "\n")
    lines.append(
        "## Generated Summary\n" + (summary or "_Summary not generated yet._") + "\n"
    )
    lines.append(
        "## Calls\n"
        + ("\n".join(f"- `{call}`" for call in symbol.calls) or "_No calls detected._")
        + "\n"
    )
    lines.append(f"## Source Code\n```{fence}\n" + source_text.rstrip() + "\n```\n")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def render_symbol_section(symbol: Symbol, level: str, repo_root: Path) -> list[str]:
    title = f"{level} {symbol.kind.title()}: {symbol.qualname}"
    lines = [title, f"Lines: `{symbol.start_line}-{symbol.end_line}`"]
    fence = symbol.language.value
    if symbol.signature:
        lines.append(f"Signature:\n```{fence}\n" + symbol.signature + "\n```")
    if symbol.docstring:
        lines.append("Docstring:\n> " + symbol.docstring.replace("\n", "\n> "))
    source_text = read_source(symbol.span, repo_root)
    lines.append(f"```{fence}\n" + source_text.rstrip() + "\n```")
    return lines


def write_repo_map(
    parsed_modules: list[ParsedModule],
    output_dir: Path,
    commit: str,
    repo_name: str,
    repo_root: Path,
) -> Path:
    path = output_dir / "repo_map.md"
    ensure_parent(path)
    python_files = len(
        [p for p in parsed_modules if p.source_file.language == "python"]
    )
    symbols = [symbol for parsed in parsed_modules for symbol in parsed.symbols]
    classes = len([symbol for symbol in symbols if symbol.kind == "class"])
    functions = len(
        [symbol for symbol in symbols if symbol.kind in {"function", "method"}]
    )
    # Probe reads whole files, not cached spans, which may exceed a file that failed to parse.
    entrypoints: list[str] = []
    for parsed in parsed_modules:
        rel = parsed.source_file.path
        if rel.startswith("scripts/"):
            entrypoints.append(rel)
            continue
        try:
            text = (repo_root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if 'if __name__ == "__main__"' in text:
            entrypoints.append(rel)
    lines = [
        "# Repository Map",
        f"Repo: `{repo_name}`",
        f"Commit: `{commit}`",
        "## Modules",
    ]
    lines.extend(
        f"- `{parsed.module}` — `{parsed.source_file.path}`"
        for parsed in parsed_modules
    )
    lines.append("## Likely Entrypoints")
    lines.extend(
        f"- `{entry}`" for entry in sorted(set(entrypoints))
    ) if entrypoints else lines.append("- _None detected._")
    lines.extend(
        [
            "## Statistics",
            f"- Python files: {python_files}",
            f"- Classes: {classes}",
            f"- Functions/methods: {functions}",
            f"- Generated symbol docs: {len(symbols)}",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
