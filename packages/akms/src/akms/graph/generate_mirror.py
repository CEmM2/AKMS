"""generate_mirror.py — Code Mirror Generation + Drift Check (§2.9 of system design).

Generates the code mirror — a **search index** that allows qmd to replace grep.
Mirror nodes exist in the graph as simple existence markers (no edges, no tags).

Runs as part of the write-back cycle after ``update_graph.py``. Only processes
files modified in the current phase (from ``git diff``).

**Generation algorithm (legacy provider):**
  1. Parse source file with ``ast`` module
  2. For each FunctionDef, AsyncFunctionDef, ClassDef:
     - Extract docstring → rendered as markdown (semantic search layer)
     - Extract full source → wrapped in ```python block (literal search layer)
  3. Write mirror file to ``knowledge/code-mirror/{module_path}.md``
  4. Write mirror node frontmatter (marker only)

**Provider routing (A2-4):**
  Public :func:`generate_mirror` dispatches through the mirror-provider
  protocol (default: legacy AST). The pure legacy body is
  :func:`generate_mirror_legacy`.

**Docstring drift detection** lives in :mod:`akms.graph.drift` and is
re-exported here for backward-compatible imports.
"""

from __future__ import annotations

import ast
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import frontmatter as fm

from akms import AKMS_SCHEMA_VERSION
from akms.graph.drift import (
    check_docstring_drift_llm,
    check_docstring_drift_structural,
)
from akms.telemetry import traced

logger = logging.getLogger(__name__)

__all__ = [
    "check_docstring_drift_llm",
    "check_docstring_drift_structural",
    "extract_definitions",
    "generate_mirror",
    "generate_mirror_legacy",
    "get_changed_files",
    "write_mirror_file",
]


# ═══════════════════════════════════════════════════════════════════════
#  AST Extraction
# ═══════════════════════════════════════════════════════════════════════


def _get_source_segment(source_lines: list[str], node: ast.AST) -> str:
    """Extract source text for an AST node from pre-split source lines."""
    start = node.lineno - 1
    end = getattr(node, "end_lineno", node.lineno)
    return "\n".join(source_lines[start:end])


def _get_docstring(node: ast.AST) -> str | None:
    """Extract docstring from a FunctionDef/ClassDef/AsyncFunctionDef."""
    return ast.get_docstring(node)


def _get_parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Extract parameter names from a function definition."""
    params = []
    for arg in node.args.args:
        params.append(arg.arg)
    for arg in node.args.posonlyargs:
        params.append(arg.arg)
    for arg in node.args.kwonlyargs:
        params.append(arg.arg)
    if node.args.vararg:
        params.append(f"*{node.args.vararg.arg}")
    if node.args.kwarg:
        params.append(f"**{node.args.kwarg.arg}")
    return params


def _get_return_annotation(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Extract return annotation as string, if present."""
    if node.returns:
        return ast.unparse(node.returns)
    return None


def _get_decorators(node: ast.AST) -> list[str]:
    """Extract decorator names from a function/class def."""
    decorators = []
    for dec in getattr(node, "decorator_list", []):
        try:
            decorators.append(ast.unparse(dec))
        except Exception:
            decorators.append("<unknown>")
    return decorators


def extract_definitions(source: str) -> list[dict[str, Any]]:
    """Parse Python source and extract all top-level and class-level definitions.

    Returns a list of dicts with keys:
        name, type (function|async_function|class), docstring, source,
        parameters, return_annotation, decorators
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        logger.warning("SyntaxError parsing source: %s", e)
        return []

    source_lines = source.splitlines()
    definitions = []

    def _process_node(node: ast.AST, prefix: str = "") -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
            full_name = f"{prefix}{node.name}" if prefix else node.name
            definitions.append({
                "name": full_name,
                "type": kind,
                "docstring": _get_docstring(node),
                "source": _get_source_segment(source_lines, node),
                "parameters": _get_parameters(node),
                "return_annotation": _get_return_annotation(node),
                "decorators": _get_decorators(node),
            })
        elif isinstance(node, ast.ClassDef):
            full_name = f"{prefix}{node.name}" if prefix else node.name
            definitions.append({
                "name": full_name,
                "type": "class",
                "docstring": _get_docstring(node),
                "source": _get_source_segment(source_lines, node),
                "parameters": [],
                "return_annotation": None,
                "decorators": _get_decorators(node),
            })
            # Process methods within the class
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _process_node(child, prefix=f"{full_name}.")

    for node in ast.iter_child_nodes(tree):
        _process_node(node)

    return definitions


# ═══════════════════════════════════════════════════════════════════════
#  Mirror File Generation
# ═══════════════════════════════════════════════════════════════════════


def _format_mirror_content(
    source_file: str,
    definitions: list[dict],
    phase: int,
    generated_at: datetime,
) -> str:
    """Format mirror file content per spec §2.9."""
    lines = [
        f"# `{source_file}`",
        f"_Mirror generated: {generated_at.strftime('%Y-%m-%dT%H:%M:%S')} · phase {phase}_",
        "",
    ]

    for defn in definitions:
        lines.append(f"## `{defn['name']}`")

        # Docstring as plain markdown
        if defn["docstring"]:
            lines.append(defn["docstring"])
            lines.append("")

        # Full source in code block
        lines.append("```python")
        lines.append(defn["source"])
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def _generate_mirror_frontmatter(
    source_file: str,
    phase: int,
    generated_at: datetime,
) -> dict:
    """Generate mirror node frontmatter (marker only)."""
    # Convert file path to node id: src/foo/bar.py → mirror-src-foo-bar
    node_id = "mirror-" + source_file.replace("/", "-").replace("\\", "-").replace(".py", "").replace(".", "-")
    content_ref = f"code-mirror/{source_file.replace('.py', '.md')}"

    return {
        "id": node_id,
        "title": f"Code Mirror: {source_file}",
        "domain": "code-mirror",
        "status": "established",
        "confidence": 1.0,
        "source": "generated",
        "auto_update": True,
        "content_ref": content_ref,
        "source_file": source_file,
        "generated_at": generated_at.isoformat(),
        "generated_by_phase": phase,
        "akms_schema": AKMS_SCHEMA_VERSION,
    }


def write_mirror_file(
    repo_root: Path,
    source_file: str,
    source_content: str,
    phase: int,
    generated_at: datetime | None = None,
) -> dict[str, Any] | None:
    """Generate and write a mirror file for a single source file.

    Args:
        repo_root: Path to the repository root.
        source_file: Relative path to the source file (e.g., 'src/module.py').
        source_content: Python source code to parse.
        phase: Phase number that generated this mirror.
        generated_at: Timestamp (defaults to now).

    Returns:
        Dict with mirror info or None if no definitions found.
    """
    if generated_at is None:
        generated_at = datetime.now()

    definitions = extract_definitions(source_content)
    if not definitions:
        logger.debug("No definitions found in %s — skipping mirror", source_file)
        return None

    # Format mirror content
    content = _format_mirror_content(source_file, definitions, phase, generated_at)

    # Generate frontmatter
    frontmatter_data = _generate_mirror_frontmatter(source_file, phase, generated_at)

    # Write mirror file
    mirror_path = repo_root / "knowledge" / "code-mirror" / source_file.replace(".py", ".md")
    mirror_path.parent.mkdir(parents=True, exist_ok=True)

    post = fm.Post(content)
    post.metadata = frontmatter_data
    with open(mirror_path, "wb") as f:
        fm.dump(post, f)

    logger.info("Wrote mirror: %s → %s", source_file, mirror_path)

    return {
        "source_file": source_file,
        "mirror_path": str(mirror_path),
        "node_id": frontmatter_data["id"],
        "definitions_count": len(definitions),
    }


# Docstring drift: re-exported from akms.graph.drift (imports at module top).


# ═══════════════════════════════════════════════════════════════════════
#  Git Diff Integration
# ═══════════════════════════════════════════════════════════════════════


def get_changed_files(
    repo_root: Path,
    parent_branch: str = "main",
    extensions: set[str] | None = None,
) -> list[str]:
    """Get files changed between parent_branch and HEAD.

    Args:
        repo_root: Repository root path.
        parent_branch: Branch to diff against (default 'main').
        extensions: Set of extensions to include (default {'.py'}).

    Returns:
        List of relative file paths.
    """
    if extensions is None:
        extensions = {".py"}

    try:
        result = subprocess.run(
            ["git", "diff", f"{parent_branch}..HEAD", "--name-only"],
            capture_output=True,
            text=True,
            cwd=str(repo_root),
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("git diff failed: %s", result.stderr.strip())
            return []

        files = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if any(line.endswith(ext) for ext in extensions):
                files.append(line)

        return sorted(files)

    except FileNotFoundError:
        logger.warning("git not found — cannot determine changed files")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("git diff timed out")
        return []
    except Exception as e:
        logger.warning("git diff error: %s", e)
        return []


# ═══════════════════════════════════════════════════════════════════════
#  Main Entry Point
# ═══════════════════════════════════════════════════════════════════════


def generate_mirror_legacy(
    repo_root: str | Path,
    phase: int,
    parent_branch: str = "main",
    source_files: list[str] | None = None,
    drift_check: bool = True,
    llm_fn: Any = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Legacy in-process Python AST mirror generation (provider implementation body).

    This is the historical algorithm, unchanged in behavior. Prefer the public
    :func:`generate_mirror` entry point which routes through the provider protocol.
    """
    repo_root = Path(repo_root)
    if generated_at is None:
        generated_at = datetime.now()

    # Get files to process
    if source_files is None:
        source_files = get_changed_files(repo_root, parent_branch)

    mirrors = []
    drift_warnings = []
    definitions_total = 0

    for source_file in source_files:
        source_path = repo_root / source_file
        if not source_path.exists():
            logger.warning("Source file not found: %s", source_path)
            continue

        if not source_file.endswith(".py"):
            logger.debug("Skipping non-Python file: %s", source_file)
            continue

        try:
            source_content = source_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to read %s: %s", source_path, e)
            continue

        # Write mirror
        mirror_info = write_mirror_file(
            repo_root, source_file, source_content, phase, generated_at,
        )
        if mirror_info:
            mirrors.append(mirror_info)
            definitions_total += mirror_info["definitions_count"]

        # Drift check (provider-neutral module; structural unless llm_fn set)
        if drift_check:
            definitions = extract_definitions(source_content)
            if llm_fn is not None:
                file_warnings = check_docstring_drift_llm(definitions, llm_fn)
            else:
                file_warnings = check_docstring_drift_structural(definitions)

            for w in file_warnings:
                w["file"] = source_file
            drift_warnings.extend(file_warnings)

    summary = {
        "mirrors": mirrors,
        "drift_warnings": drift_warnings,
        "files_processed": len(source_files),
        "definitions_total": definitions_total,
        "provider": "legacy",
        "success": True,
        "fallback_used": False,
        "errors": [],
        "provider_metadata": {
            "kind": "in_process",
            "language_coverage": ["python"],
        },
    }

    logger.info(
        "generate_mirror_legacy: %d files → %d mirrors, %d definitions, %d drift warnings",
        len(source_files), len(mirrors), definitions_total, len(drift_warnings),
    )

    return summary


@traced("akms.generate_mirror")
def generate_mirror(
    repo_root: str | Path,
    phase: int,
    parent_branch: str = "main",
    source_files: list[str] | None = None,
    drift_check: bool = True,
    llm_fn: Any = None,
    *,
    config: Any = None,
    provider_name: str | None = None,
) -> dict[str, Any]:
    """Generate code mirror files via the configured mirror provider.

    Default provider is ``legacy`` (Python AST), preserving historical behavior
    for callers that omit *config* / *provider_name*.

    Args:
        repo_root: Path to the repository root.
        phase: Current phase number.
        parent_branch: Branch to diff against (default 'main').
        source_files: Explicit list of source files (overrides git diff).
        drift_check: Whether to run drift detection.
        llm_fn: Optional LLM callable for semantic drift check.
        config: Optional ``PropagationConfig`` or ``MirrorConfig``.
        provider_name: Override provider name (default from config / legacy).

    Returns:
        Dict with keys:
        {
            "mirrors": [...],
            "drift_warnings": [...],
            "files_processed": int,
            "definitions_total": int,
            # additive provider fields:
            "provider": str,
            "provider_metadata": dict,
            "errors": list,
            "success": bool,
            "fallback_used": bool,
        }
    """
    # Local import: mirror_provider imports providers which call back into
    # generate_mirror_legacy — keep the cycle at function scope.
    from akms.graph.mirror_provider import (
        MirrorProviderError,
        MirrorRequest,
        resolve_mirror_config,
        run_mirror_provider,
    )

    mirror_cfg = resolve_mirror_config(config)
    # Fast path: pure legacy with no config override keeps the historical
    # call shape and avoids registry overhead for the default case.
    name = (provider_name or mirror_cfg.provider or "legacy").strip().lower()
    if name == "legacy" and config is None and provider_name is None:
        return generate_mirror_legacy(
            repo_root=repo_root,
            phase=phase,
            parent_branch=parent_branch,
            source_files=source_files,
            drift_check=drift_check,
            llm_fn=llm_fn,
        )

    request = MirrorRequest(
        repo_root=Path(repo_root),
        phase=phase,
        parent_branch=parent_branch,
        source_files=source_files,
        selection_mode=mirror_cfg.selection_mode or "changed",
        drift_check=drift_check,
        llm_fn=llm_fn,
        prune=mirror_cfg.prune,
        force_lock=mirror_cfg.force_lock,
    )
    try:
        result = run_mirror_provider(
            request,
            mirror_cfg,
            provider_name=provider_name,
        )
    except MirrorProviderError:
        raise
    return result.to_dict()
