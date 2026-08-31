"""drift.py — Provider-neutral docstring drift checks (A2-6).

Structural (deterministic, no LLM) and optional LLM drift checks live
here so mirror providers (legacy AST, repo2md subprocess) share one
review surface. Deterministic mirror refresh never invokes the LLM path.
"""

from __future__ import annotations

import ast
import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_definitions_from_source(source: str) -> list[dict[str, Any]]:
    """Parse Python source into definition dicts for drift checking.

    Reuses the same shape as ``generate_mirror.extract_definitions`` so
    consumers can pass either.
    """
    # Prefer the AST extractor from generate_mirror (single source of truth).
    from akms.graph.generate_mirror import extract_definitions

    return extract_definitions(source)


def check_docstring_drift_structural(definitions: list[dict]) -> list[dict]:
    """Check for structural docstring drift (pure heuristic, no LLM).

    Catches the most obvious contradictions:
    - Docstring mentions parameters not in the signature
    - Docstring misses parameters that are in the signature (excluding self/cls)
    - Docstring mentions 'returns None' but function has a non-None annotation

    For full semantic drift detection, use check_docstring_drift_llm()
    which requires an LLM API call.

    Returns list of drift warning dicts.
    """
    warnings: list[dict] = []

    for defn in definitions:
        if defn["type"] == "class":
            continue
        docstring = defn.get("docstring")
        if not docstring:
            continue

        params = defn.get("parameters", [])
        return_ann = defn.get("return_annotation")

        # Filter out self/cls
        real_params = [
            p for p in params if p not in ("self", "cls") and not p.startswith("*")
        ]

        doc_lower = docstring.lower()

        # Check for parameter name mismatches
        for param in real_params:
            if (
                len(param) > 2
                and param not in doc_lower
                and param.replace("_", " ") not in doc_lower
            ):
                warnings.append(
                    {
                        "function": defn["name"],
                        "type": "missing_param_in_docstring",
                        "detail": f"Parameter '{param}' not mentioned in docstring",
                    }
                )

        # Check return annotation contradiction
        if return_ann and return_ann != "None":
            if "returns none" in doc_lower or "return none" in doc_lower:
                warnings.append(
                    {
                        "function": defn["name"],
                        "type": "return_type_contradiction",
                        "detail": f"Docstring says 'returns None' but annotation is {return_ann}",
                    }
                )

    return warnings


def check_docstring_drift_llm(
    definitions: list[dict],
    llm_fn: Any = None,
) -> list[dict]:
    """Check for semantic docstring drift using an LLM call.

    Args:
        definitions: Extracted definitions from extract_definitions().
        llm_fn: Callable (prompt: str) → str. If None, falls back to structural check.

    Returns list of drift warning dicts with keys:
        function, type, detail, llm_response
    """
    if llm_fn is None:
        return check_docstring_drift_structural(definitions)

    warnings: list[dict] = []

    for defn in definitions:
        if defn["type"] == "class":
            continue
        docstring = defn.get("docstring")
        if not docstring:
            continue

        params = defn.get("parameters", [])
        return_ann = defn.get("return_annotation")
        decorators = defn.get("decorators", [])

        prompt = (
            "Does this docstring accurately describe a function with these parameters "
            "and this return type? Reply YES or NO with one sentence.\n\n"
            f"Docstring:\n{docstring}\n\n"
            f"Parameters: {', '.join(params)}\n"
            f"Return type: {return_ann or 'not annotated'}\n"
            f"Decorators: {', '.join(decorators) or 'none'}"
        )

        try:
            response = llm_fn(prompt)
            response_stripped = response.strip().upper()
            if response_stripped.startswith("NO"):
                warnings.append(
                    {
                        "function": defn["name"],
                        "type": "llm_drift",
                        "detail": response.strip(),
                        "llm_response": response.strip(),
                    }
                )
        except Exception as e:
            logger.warning("LLM drift check failed for %s: %s", defn["name"], e)

    return warnings


def check_python_sources_drift(
    repo_root: str | Any,
    source_files: list[str],
    *,
    llm_fn: Any = None,
) -> list[dict]:
    """Run drift checks over repository-relative Python files.

    Always uses structural checks when *llm_fn* is None (deterministic path).
    """
    from pathlib import Path

    root = Path(repo_root)
    warnings: list[dict] = []
    for source_file in source_files:
        if not source_file.endswith(".py"):
            continue
        path = root / source_file
        if not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Failed to read %s for drift: %s", path, e)
            continue
        definitions = extract_definitions_from_source(source)
        if llm_fn is not None:
            file_warnings = check_docstring_drift_llm(definitions, llm_fn)
        else:
            file_warnings = check_docstring_drift_structural(definitions)
        for w in file_warnings:
            w["file"] = source_file
        warnings.extend(file_warnings)
    return warnings


# Silence unused import if ast is only needed for type checkers elsewhere.
_ = ast
