#!/usr/bin/env python3
"""
AKMS Node Validator — validate drafted .md node files against the v2 schema.

Usage:
    # Validate a single file
    python validate_nodes.py path/to/node.md

    # Validate all .md files in a directory
    python validate_nodes.py path/to/nodes/

    # Validate with cross-reference checking against known inventory
    python validate_nodes.py path/to/nodes/ --inventory inventory.json [inventory2.json ...]

    # Validate a raw NotebookLM output file (multiple nodes separated by ═══ FILE: ... ═══)
    python validate_nodes.py --raw-batch output.txt --split-dir ./split_nodes/

    # Strict mode: treat warnings as errors
    python validate_nodes.py path/to/nodes/ --strict

    # Quiet mode: only show errors
    python validate_nodes.py path/to/nodes/ --quiet

    # JSON output to stdout (for CI / MCP tool consumption)
    python validate_nodes.py path/to/nodes/ --json

    # JSON output to file
    python validate_nodes.py path/to/nodes/ -o report.json

    # Auto-fix mechanical issues (schema version, experiential fields, etc.)
    python validate_nodes.py path/to/nodes/ --fix

    # Preview fixes without writing
    python validate_nodes.py path/to/nodes/ --fix --dry-run

    # Fix, then re-validate to confirm clean output
    python validate_nodes.py path/to/nodes/ --fix --revalidate

    # Rename files to match node ids (separate from --fix)
    python validate_nodes.py path/to/nodes/ --fix-filenames
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Any

import frontmatter as fm_lib  # python-frontmatter (same lib used by schema/validators.py)
from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

from akms import AKMS_SCHEMA_VERSION
from akms.schema.models import (
    ContextSize,
    EdgeType,
    NodeSource,
    NodeStatus,
    ReadingPriority,
)
from akms.schema.models import EXPERIENTIAL_FIELDS


# ═══════════════════════════════════════════════════════════════════════════════
#                          ENUMS & CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

# Derived from canonical enums — stays in sync automatically
VALID_STATUSES = {e.value for e in NodeStatus}
VALID_SOURCES = {e.value for e in NodeSource}
VALID_EDGE_TYPES = {e.value for e in EdgeType}
VALID_CONTEXT_SIZES = {e.value for e in ContextSize}
VALID_READING_PRIORITIES = {e.value for e in ReadingPriority}

# Required markdown sections for content validation
REQUIRED_SECTIONS = {"## Summary"}
RECOMMENDED_SECTIONS = {
    "## 1. Core Concept",
    "## 2. Mathematical Formulation",
}

# ── Tunable thresholds ────────────────────────────────────────────────
# These control the sensitivity of WARNING/INFO-level content checks.
# The word-to-token ratio is ~1.2 for English prose, higher for equations.
SUMMARY_MIN_WORDS = 15  # below this → WARNING on summary length
MIN_RECOMMENDED_TAGS = 3  # below this → INFO on tag count
SMALL_MAX_WORDS = 600  # context_size "small" mismatch threshold (~500 tokens)
MEDIUM_MAX_WORDS = 1800  # context_size "medium" mismatch threshold (~1500 tokens)

# Regex for the batch file separator
BATCH_SEPARATOR = re.compile(r"^═{3,}\s*FILE:\s*(.+?)\s*═{3,}$", re.MULTILINE)


# ═══════════════════════════════════════════════════════════════════════════════
#                          PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class Issue(BaseModel):
    """A single validation issue."""

    severity: Severity
    field: str | None = None
    message: str

    def __str__(self) -> str:
        prefix = f"[{self.severity.value}]"
        loc = f" {self.field}:" if self.field else ""
        return f"  {prefix}{loc} {self.message}"


class EdgeModel(BaseModel):
    """Schema for a single structural edge.

    Mirrors akms.schema.models.StructuralEdge but without extra="forbid",
    so that unknown edge fields produce warnings rather than hard errors.
    """

    to: str
    type: str
    weight: float
    note: str = ""  # matches canonical StructuralEdge default

    @field_validator("type")
    @classmethod
    def valid_edge_type(cls, v: str) -> str:
        if v not in VALID_EDGE_TYPES:
            raise ValueError(
                f"Invalid edge type '{v}'. Must be one of: {', '.join(sorted(VALID_EDGE_TYPES))}"
            )
        return v

    @field_validator("weight")
    @classmethod
    def valid_weight(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"Edge weight {v} out of range [0.0, 1.0]")
        return v

    @field_validator("to")
    @classmethod
    def valid_target_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Edge target 'to' cannot be empty")
        if " " in v:
            raise ValueError(
                f"Edge target '{v}' contains spaces — use snake-case or kebab-case"
            )
        return v


class NodeFrontmatter(BaseModel):
    """Full schema for an AKMS v2 global or local node frontmatter.

    Mirrors akms.schema.models.GlobalNodeFrontmatter for field names and types.

    IMPORTANT: Unlike GlobalNodeFrontmatter, this model deliberately does NOT
    use ``model_config = {"extra": "forbid"}``.  Unknown fields are instead
    detected by ``validate_frontmatter()`` and surfaced as WARNING-level issues
    rather than hard Pydantic errors.  This graduated feedback is the whole
    point of the validator — do NOT add ``extra="forbid"`` here.
    """

    # ── Identity ──────────────────────────────────────────────────────
    id: str
    title: str
    domain: str
    subdomain: str | None = None
    tags: list[str]

    # ── Graph Status ──────────────────────────────────────────────────
    status: str
    confidence: float
    source: str
    confidence_floor: float | None = None

    # ── Structural Edges ──────────────────────────────────────────────
    edges: list[EdgeModel] = Field(default_factory=list)

    # ── Loadout Hints ─────────────────────────────────────────────────
    load_with: list[str] | None = None
    context_size: str | None = None
    reading_priority: str | None = None
    content_ref: str | None = None

    # ── Schema Version ────────────────────────────────────────────────
    akms_schema: str

    # ── Validators ────────────────────────────────────────────────────

    @field_validator("id")
    @classmethod
    def valid_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Node id cannot be empty")
        if " " in v:
            raise ValueError(
                f"Node id '{v}' contains spaces — use snake-case or kebab-case"
            )
        # Allow kebab-case (most common) and snake_case
        if not re.match(r"^[a-z0-9][a-z0-9_-]*$", v):
            raise ValueError(
                f"Node id '{v}' has invalid characters. Use lowercase alphanumeric + hyphens/underscores"
            )
        return v

    @field_validator("tags")
    @classmethod
    def valid_tags(cls, v: list[str]) -> list[str]:
        if len(v) < 1:
            raise ValueError("At least one tag is required")
        return v

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        if v not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{v}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}"
            )
        return v

    @field_validator("confidence")
    @classmethod
    def valid_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"Confidence {v} out of range [0.0, 1.0]")
        return v

    @field_validator("confidence_floor")
    @classmethod
    def valid_confidence_floor(cls, v: float | None) -> float | None:
        if v is not None and not 0.0 <= v <= 1.0:
            raise ValueError(f"confidence_floor {v} out of range [0.0, 1.0]")
        return v

    @field_validator("source")
    @classmethod
    def valid_source(cls, v: str) -> str:
        if v not in VALID_SOURCES:
            raise ValueError(
                f"Invalid source '{v}'. Must be one of: {', '.join(sorted(VALID_SOURCES))}"
            )
        return v

    @field_validator("akms_schema")
    @classmethod
    def valid_schema_version(cls, v: str) -> str:
        if v != AKMS_SCHEMA_VERSION:
            raise ValueError(
                f"Schema version mismatch: expected '{AKMS_SCHEMA_VERSION}', got '{v}'"
            )
        return v

    @field_validator("context_size")
    @classmethod
    def valid_context_size(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_CONTEXT_SIZES:
            raise ValueError(
                f"Invalid context_size '{v}'. Must be one of: {', '.join(sorted(VALID_CONTEXT_SIZES))}"
            )
        return v

    @field_validator("reading_priority")
    @classmethod
    def valid_reading_priority(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_READING_PRIORITIES:
            raise ValueError(
                f"Invalid reading_priority '{v}'. Must be one of: {', '.join(sorted(VALID_READING_PRIORITIES))}"
            )
        return v

    @model_validator(mode="after")
    def cross_field_checks(self) -> "NodeFrontmatter":
        if (
            self.confidence_floor is not None
            and self.confidence_floor > self.confidence
        ):
            # Not an error per se, but worth flagging
            pass  # handled in soft checks
        return self


# ═══════════════════════════════════════════════════════════════════════════════
#                          PARSING
# ═══════════════════════════════════════════════════════════════════════════════


def parse_md_file(path: Path) -> tuple[dict[str, Any] | None, str, list[Issue]]:
    """Parse a .md file into (frontmatter_dict, body_text, parse_issues).

    Uses the ``python-frontmatter`` library (same as ``schema/validators.py``)
    for robust YAML extraction — handles BOM, leading whitespace, and edge
    cases that the previous hand-rolled regex could miss.

    Returns ``(None, "", issues)`` if the file cannot be parsed.
    """
    issues: list[Issue] = []

    try:
        post = fm_lib.load(str(path))
    except Exception as e:
        issues.append(
            Issue(
                severity=Severity.ERROR,
                field="frontmatter",
                message=f"Failed to parse file: {e}",
            )
        )
        return None, "", issues

    fm = dict(post.metadata)
    body = post.content

    if not fm:
        issues.append(
            Issue(
                severity=Severity.ERROR,
                message="No YAML frontmatter found. Expected file to start with --- ... ---",
            )
        )
        return None, body, issues

    if not isinstance(fm, dict):
        issues.append(
            Issue(
                severity=Severity.ERROR,
                field="frontmatter",
                message=f"Frontmatter parsed as {type(fm).__name__}, expected dict",
            )
        )
        return None, body, issues

    return fm, body, issues


def split_raw_batch(text: str) -> list[tuple[str, str]]:
    """
    Split a raw NotebookLM batch output into (filename, content) pairs.
    Expects separator lines like: ═══ FILE: node-id.md ═══
    """
    parts = BATCH_SEPARATOR.split(text)
    # parts[0] = preamble (before first separator), then alternating: filename, content
    results = []
    if len(parts) < 3:
        # No separators found — treat the whole text as one file
        return [("unknown.md", text)]

    for i in range(1, len(parts), 2):
        filename = parts[i].strip()
        content = parts[i + 1] if i + 1 < len(parts) else ""
        results.append((filename, content.strip()))
    return results


# ═══════════════════════════════════════════════════════════════════════════════
#                          VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════


def validate_frontmatter(
    fm: dict[str, Any],
    body: str,
    known_ids: set[str] | None = None,
) -> tuple[NodeFrontmatter | None, list[Issue]]:
    """
    Validate a parsed frontmatter dict against the AKMS v2 schema.
    Returns (parsed_model_or_None, issues).
    """
    issues: list[Issue] = []

    # ── Check for experiential fields that don't belong ──
    for field in EXPERIENTIAL_FIELDS:
        if field in fm:
            issues.append(
                Issue(
                    severity=Severity.ERROR,
                    field=field,
                    message=(
                        f"Experiential field '{field}' found in node frontmatter. "
                        "This belongs in local_state.yaml, not in node files (v2 schema)."
                    ),
                )
            )

    # ── Check for unknown fields ──
    known_frontmatter_fields = {
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
    }
    for key in fm:
        if key not in known_frontmatter_fields and key not in EXPERIENTIAL_FIELDS:
            issues.append(
                Issue(
                    severity=Severity.WARNING,
                    field=key,
                    message=f"Unknown frontmatter field '{key}'. Not in v2 schema — will be ignored by tooling.",
                )
            )

    # ── Pydantic validation ──
    model: NodeFrontmatter | None = None
    try:
        model = NodeFrontmatter(**fm)
    except Exception as e:
        # Extract all validation errors
        error_str = str(e)
        # Pydantic v2 raises ValidationError with structured messages
        if hasattr(e, "errors"):
            for err in e.errors():  # type: ignore
                loc = " → ".join(str(l) for l in err["loc"])
                issues.append(
                    Issue(severity=Severity.ERROR, field=loc, message=err["msg"])
                )
        else:
            issues.append(
                Issue(
                    severity=Severity.ERROR, message=f"Validation failed: {error_str}"
                )
            )
        return None, issues

    # ── Soft checks (warnings, not errors) ──
    # Note: akms_schema version mismatch is already caught as an ERROR
    # by the Pydantic field validator during model construction above.

    # Confidence floor > confidence
    if model.confidence_floor is not None and model.confidence_floor > model.confidence:
        issues.append(
            Issue(
                severity=Severity.WARNING,
                field="confidence_floor",
                message=(
                    f"confidence_floor ({model.confidence_floor}) > confidence ({model.confidence}). "
                    "This means the node's intrinsic confidence is below its own floor."
                ),
            )
        )

    # Source = hybrid for NotebookLM-generated nodes (expected)
    if model.source not in ("hybrid", "agent", "human"):
        issues.append(
            Issue(
                severity=Severity.WARNING,
                field="source",
                message=f"Unexpected source '{model.source}' for a drafted node.",
            )
        )

    # No edges
    if len(model.edges) == 0:
        issues.append(
            Issue(
                severity=Severity.WARNING,
                field="edges",
                message="Node has no edges. Every node should have at least one structural edge.",
            )
        )

    # Too few tags
    if len(model.tags) < MIN_RECOMMENDED_TAGS:
        issues.append(
            Issue(
                severity=Severity.INFO,
                field="tags",
                message=f"Only {len(model.tags)} tag(s). Recommend {MIN_RECOMMENDED_TAGS}–6 for effective seed matching.",
            )
        )

    # Duplicate tags
    seen_tags: set[str] = set()
    dupe_tags = [t for t in model.tags if t in seen_tags or seen_tags.add(t)]  # type: ignore[func-returns-value]
    if dupe_tags:
        issues.append(
            Issue(
                severity=Severity.INFO,
                field="tags",
                message=f"Duplicate tags: {', '.join(dupe_tags)}. Consider deduplicating.",
            )
        )

    # Missing context_size
    if model.context_size is None:
        issues.append(
            Issue(
                severity=Severity.INFO,
                field="context_size",
                message="No context_size set. Loadout generator will use default token allocation.",
            )
        )

    # Self-referencing edge check
    for edge in model.edges:
        if edge.to == model.id:
            issues.append(
                Issue(
                    severity=Severity.WARNING,
                    field=f"edges[to={edge.to}]",
                    message=f"Self-referencing edge: node '{model.id}' points to itself.",
                )
            )

    # Edge target cross-reference check
    if known_ids is not None:
        for edge in model.edges:
            if edge.to not in known_ids:
                # Check if the edge note contains "guessed"
                is_guessed = edge.note and "guessed" in edge.note.lower()
                issues.append(
                    Issue(
                        severity=Severity.INFO if is_guessed else Severity.WARNING,
                        field=f"edges[to={edge.to}]",
                        message=(
                            f"Edge target '{edge.to}' not found in known inventory. "
                            f"{'(marked as guessed)' if is_guessed else 'Verify this id exists or will be created.'}"
                        ),
                    )
                )

    # ── Content body checks ──
    validate_body(body, model, issues)

    return model, issues


def validate_body(body: str, model: NodeFrontmatter, issues: list[Issue]) -> None:
    """Check markdown body for required/recommended sections."""

    # Check for ## Summary (mandatory for routing mode loadouts)
    if "## Summary" not in body:
        issues.append(
            Issue(
                severity=Severity.ERROR,
                field="body",
                message=(
                    "Missing '## Summary' section. This is REQUIRED — "
                    "it provides the text shown in routing-mode loadouts."
                ),
            )
        )
    else:
        # Check summary is not too short
        summary_match = re.search(r"## Summary\s*\n(.*?)(?=\n## |\Z)", body, re.DOTALL)
        if summary_match:
            summary_text = summary_match.group(1).strip()
            word_count = len(summary_text.split())
            if word_count < SUMMARY_MIN_WORDS:
                issues.append(
                    Issue(
                        severity=Severity.WARNING,
                        field="body/Summary",
                        message=f"Summary is only {word_count} words. Aim for 3–5 sentences (40–80 words).",
                    )
                )

    # Check for recommended sections
    for section in RECOMMENDED_SECTIONS:
        if section not in body:
            issues.append(
                Issue(
                    severity=Severity.INFO,
                    field="body",
                    message=f"Missing recommended section '{section}'.",
                )
            )

    # Check for Known Pitfalls section
    pitfall_variants = [
        "## 4. Known Pitfalls",
        "## 5. Known Pitfalls",
        "## Known Pitfalls",
    ]
    if not any(pv in body for pv in pitfall_variants):
        issues.append(
            Issue(
                severity=Severity.INFO,
                field="body",
                message="No 'Known Pitfalls' section found. Consider adding one — pitfalls are high-value content.",
            )
        )

    # Check for raw code blocks (should be pseudo-code only)
    code_block_re = re.compile(
        r"```(python|cpp|c\+\+|c|java|rust|julia)", re.IGNORECASE
    )
    code_matches = code_block_re.findall(body)
    if code_matches:
        langs = ", ".join(set(code_matches))
        issues.append(
            Issue(
                severity=Severity.WARNING,
                field="body",
                message=(
                    f"Found code blocks tagged as real language(s): {langs}. "
                    "Nodes should contain pseudo-code only — task agents write the actual implementation."
                ),
            )
        )

    # Check title heading matches frontmatter title
    title_match = re.search(r"^# (.+)$", body, re.MULTILINE)
    if not title_match:
        issues.append(
            Issue(
                severity=Severity.WARNING,
                field="body",
                message="No '# Title' heading found at the start of the body.",
            )
        )

    # Estimate content size vs context_size hint
    word_count = len(body.split())
    if model.context_size == "small" and word_count > SMALL_MAX_WORDS:
        issues.append(
            Issue(
                severity=Severity.WARNING,
                field="context_size",
                message=f"context_size is 'small' (~500 tokens) but body is ~{word_count} words. Consider 'medium' or 'large'.",
            )
        )
    elif model.context_size == "medium" and word_count > MEDIUM_MAX_WORDS:
        issues.append(
            Issue(
                severity=Severity.WARNING,
                field="context_size",
                message=f"context_size is 'medium' (~1500 tokens) but body is ~{word_count} words. Consider 'large'.",
            )
        )


# ═══════════════════════════════════════════════════════════════════════════════
#                        BATCH-LEVEL CHECKS
# ═══════════════════════════════════════════════════════════════════════════════


def check_batch_consistency(
    results: dict[str, tuple[NodeFrontmatter | None, list[Issue]]],
) -> list[Issue]:
    """
    Cross-file checks: duplicate ids, orphaned within-batch edge targets, etc.
    """
    batch_issues: list[Issue] = []
    all_ids: dict[str, list[str]] = {}  # id → [file_paths]

    for filepath, (model, _) in results.items():
        if model is None:
            continue
        all_ids.setdefault(model.id, []).append(filepath)

    # Duplicate ids
    for nid, files in all_ids.items():
        if len(files) > 1:
            batch_issues.append(
                Issue(
                    severity=Severity.ERROR,
                    field="id",
                    message=f"Duplicate node id '{nid}' in files: {', '.join(files)}",
                )
            )

    # Filename vs id mismatch
    for filepath, (model, _) in results.items():
        if model is None:
            continue
        stem = Path(filepath).stem
        if stem != model.id:
            batch_issues.append(
                Issue(
                    severity=Severity.INFO,
                    field="id",
                    message=f"Filename '{stem}.md' does not match node id '{model.id}'. Consider renaming for consistency.",
                )
            )

    return batch_issues


# ═══════════════════════════════════════════════════════════════════════════════
#                        INVENTORY LOADING
# ═══════════════════════════════════════════════════════════════════════════════


def load_known_ids(inventory_paths: list[str] | None) -> set[str]:
    """Load known node ids from inventory JSON files and/or existing .md files."""
    known: set[str] = set()

    if not inventory_paths:
        return known

    for path_str in inventory_paths:
        p = Path(path_str)
        if p.suffix == ".json":
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "nodes" in data:
                    for node in data["nodes"]:
                        if "id" in node:
                            known.add(node["id"])
                elif isinstance(data, list):
                    for node in data:
                        if isinstance(node, dict) and "id" in node:
                            known.add(node["id"])
            except Exception as e:
                print(f"  Warning: Could not load inventory {p}: {e}", file=sys.stderr)
        elif p.is_dir():
            # Scan directory for .md files and extract ids from frontmatter
            for md_file in p.glob("**/*.md"):
                fm, _, _ = parse_md_file(md_file)
                if fm and "id" in fm:
                    known.add(fm["id"])

    return known


# ═══════════════════════════════════════════════════════════════════════════════
#                          REPORTING
# ═══════════════════════════════════════════════════════════════════════════════

COLORS = {
    Severity.ERROR: "\033[91m",  # red
    Severity.WARNING: "\033[93m",  # yellow
    Severity.INFO: "\033[96m",  # cyan
}
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[92m"


def format_issue(issue: Issue, use_color: bool = True) -> str:
    if use_color:
        color = COLORS.get(issue.severity, "")
        return f"  {color}[{issue.severity.value}]{RESET} {issue.field + ': ' if issue.field else ''}{issue.message}"
    return str(issue)


def print_report(
    results: dict[str, tuple[NodeFrontmatter | None, list[Issue]]],
    batch_issues: list[Issue],
    quiet: bool = False,
    use_color: bool = True,
) -> tuple[int, int, int]:
    """Print the full validation report. Returns (error_count, warning_count, info_count)."""
    total_errors = 0
    total_warnings = 0
    total_infos = 0
    valid_count = 0

    for filepath, (model, issues) in sorted(results.items()):
        errors = [i for i in issues if i.severity == Severity.ERROR]
        warnings = [i for i in issues if i.severity == Severity.WARNING]
        infos = [i for i in issues if i.severity == Severity.INFO]

        total_errors += len(errors)
        total_warnings += len(warnings)
        total_infos += len(infos)

        if not errors and not warnings:
            valid_count += 1

        if quiet and not errors:
            continue

        # File header
        node_id = model.id if model else "???"
        status_icon = (
            f"{GREEN}✓{RESET}" if not errors else f"{COLORS[Severity.ERROR]}✗{RESET}"
        )
        if use_color:
            print(f"\n{status_icon} {BOLD}{filepath}{RESET}  (id: {node_id})")
        else:
            icon = "✓" if not errors else "✗"
            print(f"\n{icon} {filepath}  (id: {node_id})")

        for issue in errors:
            print(format_issue(issue, use_color))
        if not quiet:
            for issue in warnings:
                print(format_issue(issue, use_color))
            for issue in infos:
                print(format_issue(issue, use_color))

    # Batch-level issues
    if batch_issues:
        total_errors += sum(1 for i in batch_issues if i.severity == Severity.ERROR)
        total_warnings += sum(1 for i in batch_issues if i.severity == Severity.WARNING)
        total_infos += sum(1 for i in batch_issues if i.severity == Severity.INFO)

        if use_color:
            print(f"\n{BOLD}── Batch-Level Issues ──{RESET}")
        else:
            print("\n── Batch-Level Issues ──")
        for issue in batch_issues:
            print(format_issue(issue, use_color))

    # Summary
    total_files = len(results)
    print(f"\n{'─' * 60}")
    summary = (
        f"Files: {total_files}  |  "
        f"Valid: {valid_count}  |  "
        f"Errors: {total_errors}  |  "
        f"Warnings: {total_warnings}  |  "
        f"Info: {total_infos}"
    )
    if use_color:
        if total_errors == 0:
            print(f"{GREEN}{BOLD}{summary}{RESET}")
        else:
            print(f"{COLORS[Severity.ERROR]}{BOLD}{summary}{RESET}")
    else:
        print(summary)

    return total_errors, total_warnings, total_infos


def build_json_report(
    results: dict[str, tuple[NodeFrontmatter | None, list[Issue]]],
    batch_issues: list[Issue],
) -> dict[str, Any]:
    """Build a machine-readable JSON report from validation results.

    The output schema is stable and suitable for CI pipelines and MCP tools.
    """
    files: dict[str, Any] = {}
    total_errors = 0
    total_warnings = 0
    total_infos = 0
    valid_count = 0

    for filepath, (model, issues) in sorted(results.items()):
        file_errors = sum(1 for i in issues if i.severity == Severity.ERROR)
        file_warnings = sum(1 for i in issues if i.severity == Severity.WARNING)
        file_infos = sum(1 for i in issues if i.severity == Severity.INFO)

        total_errors += file_errors
        total_warnings += file_warnings
        total_infos += file_infos

        is_valid = file_errors == 0 and file_warnings == 0
        if is_valid:
            valid_count += 1

        files[filepath] = {
            "id": model.id if model else None,
            "valid": is_valid,
            "issues": [
                {
                    "severity": issue.severity.value,
                    "field": issue.field,
                    "message": issue.message,
                }
                for issue in issues
            ],
        }

    # Add batch-level issues to totals
    total_errors += sum(1 for i in batch_issues if i.severity == Severity.ERROR)
    total_warnings += sum(1 for i in batch_issues if i.severity == Severity.WARNING)
    total_infos += sum(1 for i in batch_issues if i.severity == Severity.INFO)

    return {
        "files": files,
        "batch_issues": [
            {
                "severity": issue.severity.value,
                "field": issue.field,
                "message": issue.message,
            }
            for issue in batch_issues
        ],
        "summary": {
            "total_files": len(results),
            "valid": valid_count,
            "errors": total_errors,
            "warnings": total_warnings,
            "info": total_infos,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
#                          AUTO-FIX
# ═══════════════════════════════════════════════════════════════════════════════

# Fields that can be auto-corrected without human judgment
_FIXABLE_SCHEMA_KEY = "akms_schema"
_FIXABLE_SOURCE_VALUE = "hybrid"  # NotebookLM-drafted nodes should be hybrid


def apply_fixes(
    path: Path,
    dry_run: bool = False,
) -> list[str]:
    """Apply deterministic auto-corrections to a node file.

    Returns a list of human-readable change descriptions.
    Does NOT write to disk if ``dry_run=True``.

    Auto-fixable issues (no human judgment needed):
    - ``akms_schema`` missing or != v2 → set to v2
    - Experiential fields in frontmatter → strip them
    - ``source: generated`` → change to ``hybrid``
    - Trailing whitespace in ``id`` or edge ``to`` → strip
    - Duplicate tags → deduplicate (preserve order)
    - Missing ``note`` on edges → set to ``""``
    """
    changes: list[str] = []

    try:
        post = fm_lib.load(str(path))
    except Exception:
        return changes  # unparseable files can't be fixed

    fm = post.metadata
    if not fm or not isinstance(fm, dict):
        return changes

    # ── Fix akms_schema ──
    if fm.get(_FIXABLE_SCHEMA_KEY) != AKMS_SCHEMA_VERSION:
        old = fm.get(_FIXABLE_SCHEMA_KEY, "<missing>")
        fm[_FIXABLE_SCHEMA_KEY] = AKMS_SCHEMA_VERSION
        changes.append(f"akms_schema: '{old}' → '{AKMS_SCHEMA_VERSION}'")

    # ── Strip experiential fields ──
    for field in list(fm.keys()):
        if field in EXPERIENTIAL_FIELDS:
            del fm[field]
            changes.append(f"Removed experiential field '{field}'")

    # ── Fix source: generated → hybrid ──
    if fm.get("source") == "generated":
        fm["source"] = _FIXABLE_SOURCE_VALUE
        changes.append(f"source: 'generated' → '{_FIXABLE_SOURCE_VALUE}'")

    # ── Strip whitespace from id ──
    node_id = fm.get("id", "")
    if isinstance(node_id, str) and node_id != node_id.strip():
        fm["id"] = node_id.strip()
        changes.append(f"id: stripped trailing whitespace ('{node_id}' → '{fm['id']}')")

    # ── Deduplicate tags ──
    tags = fm.get("tags")
    if isinstance(tags, list) and len(tags) != len(set(tags)):
        seen: set[str] = set()
        deduped = []
        for t in tags:
            if t not in seen:
                seen.add(t)
                deduped.append(t)
        removed = len(tags) - len(deduped)
        fm["tags"] = deduped
        changes.append(f"tags: removed {removed} duplicate(s)")

    # ── Fix edges ──
    edges = fm.get("edges")
    if isinstance(edges, list):
        for i, edge in enumerate(edges):
            if not isinstance(edge, dict):
                continue
            # Strip whitespace from edge targets
            to_val = edge.get("to", "")
            if isinstance(to_val, str) and to_val != to_val.strip():
                edge["to"] = to_val.strip()
                changes.append(f"edges[{i}].to: stripped whitespace")
            # Add missing note field
            if "note" not in edge:
                edge["note"] = ""
                changes.append(f"edges[{i}].note: added missing field (set to '')")

    # ── Write back ──
    if changes and not dry_run:
        post.metadata = fm
        path.write_text(fm_lib.dumps(post) + "\n", encoding="utf-8")

    return changes


def fix_filenames(
    results: dict[str, tuple[NodeFrontmatter | None, list[Issue]]],
    dry_run: bool = False,
) -> list[tuple[str, str]]:
    """Rename files to match their node id.

    Returns list of (old_path, new_path) pairs.
    Separated from ``apply_fixes`` because renames change file paths
    and would confuse batch tracking if mixed with content fixes.
    """
    renames: list[tuple[str, str]] = []

    for filepath, (model, _) in results.items():
        if model is None:
            continue
        p = Path(filepath)
        expected_name = f"{model.id}.md"
        if p.name != expected_name:
            new_path = p.parent / expected_name
            if new_path.exists():
                # Don't overwrite existing files
                continue
            renames.append((filepath, str(new_path)))
            if not dry_run:
                p.rename(new_path)

    return renames


# ═══════════════════════════════════════════════════════════════════════════════
#                            MAIN
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AKMS Node Validator — validate drafted .md node files against the v2 schema.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Paths to .md files or directories containing .md files to validate",
    )
    parser.add_argument(
        "--inventory",
        "-i",
        nargs="*",
        default=None,
        help="Inventory JSON files or directories of existing .md nodes for cross-reference checking",
    )
    parser.add_argument(
        "--raw-batch",
        default=None,
        help="Path to a raw NotebookLM batch output file to split and validate",
    )
    parser.add_argument(
        "--split-dir",
        default=None,
        help="Directory to write split node files from --raw-batch (default: ./split_nodes/)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (exit code 1 on any warning)",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only show errors, suppress warnings and info",
    )
    parser.add_argument(
        "--no-color", action="store_true", help="Disable colored output"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON report instead of human-readable text",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Write JSON report to file (implies --json)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-correct fixable issues (schema version, experiential fields, source, whitespace, duplicate tags)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview fixes without writing (requires --fix)",
    )
    parser.add_argument(
        "--revalidate",
        action="store_true",
        help="Run a second validation pass after applying fixes (requires --fix)",
    )
    parser.add_argument(
        "--fix-filenames",
        action="store_true",
        help="Rename files to match their node id (separate from --fix to avoid path confusion)",
    )

    args = parser.parse_args()

    # -o implies --json
    use_json = args.json or args.output is not None
    if use_json and args.quiet:
        parser.error("--json and --quiet are mutually exclusive")

    use_color = not args.no_color and not use_json and sys.stdout.isatty()

    if args.dry_run and not (args.fix or args.fix_filenames):
        parser.error("--dry-run requires --fix or --fix-filenames")
    if args.revalidate and not args.fix:
        parser.error("--revalidate requires --fix")

    # ── Collect .md files to validate ──
    md_files: list[Path] = []

    # Handle raw batch splitting
    if args.raw_batch:
        raw_path = Path(args.raw_batch)
        if not raw_path.exists():
            print(f"Error: raw batch file not found: {raw_path}", file=sys.stderr)
            return 1

        split_dir = Path(args.split_dir) if args.split_dir else Path("./split_nodes")
        split_dir.mkdir(parents=True, exist_ok=True)

        raw_text = raw_path.read_text(encoding="utf-8")
        parts = split_raw_batch(raw_text)

        if use_color:
            print(
                f"{BOLD}Splitting batch file into {len(parts)} node(s) → {split_dir}/{RESET}"
            )
        else:
            print(f"Splitting batch file into {len(parts)} node(s) → {split_dir}/")

        for filename, content in parts:
            if not filename.endswith(".md"):
                filename += ".md"
            out_path = split_dir / filename
            out_path.write_text(f"{content}\n", encoding="utf-8")
            md_files.append(out_path)
            print(f"  → {out_path}")

    # Handle explicit paths
    for path_str in args.paths or []:
        p = Path(path_str)
        if p.is_file() and p.suffix == ".md":
            md_files.append(p)
        elif p.is_dir():
            md_files.extend(sorted(p.glob("**/*.md")))
        else:
            print(
                f"Warning: skipping '{p}' (not a .md file or directory)",
                file=sys.stderr,
            )

    if not md_files:
        print(
            "No .md files to validate. Provide paths or use --raw-batch.",
            file=sys.stderr,
        )
        parser.print_help()
        return 1

    # ── Apply fixes (before validation) ──
    if args.fix:
        fix_label = "DRY-RUN" if args.dry_run else "FIX"
        any_fixes = False
        for md_file in md_files:
            changes = apply_fixes(md_file, dry_run=args.dry_run)
            if changes:
                any_fixes = True
                if not use_json:
                    print(f"\n[{fix_label}] {md_file}")
                    for change in changes:
                        print(f"  → {change}")

        if not any_fixes and not use_json:
            print("\nNo auto-fixable issues found.")

        if args.dry_run:
            # After dry-run preview, continue to normal validation of the original files
            pass
        elif args.revalidate and not use_json:
            print(f"\n{'─' * 60}")
            print("Re-validating after fixes...\n")

    # ── Rename files if requested (separate pass) ──
    if args.fix_filenames:
        # We need a preliminary parse to know the node ids
        prelim_results: dict[str, tuple[NodeFrontmatter | None, list[Issue]]] = {}
        for md_file in md_files:
            fm, body, parse_issues = parse_md_file(md_file)
            if fm is not None:
                try:
                    model = NodeFrontmatter(**fm)
                    prelim_results[str(md_file)] = (model, [])
                except Exception:
                    prelim_results[str(md_file)] = (None, [])
            else:
                prelim_results[str(md_file)] = (None, [])

        renames = fix_filenames(prelim_results, dry_run=args.dry_run)
        if renames and not use_json:
            label = "DRY-RUN" if args.dry_run else "RENAME"
            for old, new in renames:
                print(f"  [{label}] {old} → {new}")
            # Update md_files list to use new paths
            if not args.dry_run:
                new_set = {old: new for old, new in renames}
                md_files = [Path(new_set.get(str(f), str(f))) for f in md_files]
        elif not renames and not use_json:
            print("No filename mismatches to fix.")

    # ── Load known ids for cross-reference ──
    known_ids = load_known_ids(args.inventory)

    # Add ids from the current batch for within-batch cross-referencing
    batch_ids: set[str] = set()
    preflight: dict[Path, dict | None] = {}
    for md_file in md_files:
        fm, _, _ = parse_md_file(md_file)
        preflight[md_file] = fm
        if fm and "id" in fm:
            batch_ids.add(fm["id"])

    all_known = known_ids | batch_ids

    # ── Validate each file ──
    results: dict[str, tuple[NodeFrontmatter | None, list[Issue]]] = {}

    for md_file in md_files:
        fm, body, parse_issues = parse_md_file(md_file)

        if fm is None:
            results[str(md_file)] = (None, parse_issues)
            continue

        model, validation_issues = validate_frontmatter(
            fm,
            body,
            known_ids=all_known if all_known else None,
        )
        all_issues = parse_issues + validation_issues
        results[str(md_file)] = (model, all_issues)

    # ── Batch-level checks ──
    batch_issues = check_batch_consistency(results)

    # ── Report ──
    if use_json:
        report = build_json_report(results, batch_issues)
        json_text = json.dumps(report, indent=2, ensure_ascii=False)
        if args.output:
            Path(args.output).write_text(json_text + "\n", encoding="utf-8")
        else:
            print(json_text)
        error_count = report["summary"]["errors"]
        warning_count = report["summary"]["warnings"]
    else:
        error_count, warning_count, _ = print_report(
            results,
            batch_issues,
            quiet=args.quiet,
            use_color=use_color,
        )

    if args.strict:
        return 1 if (error_count + warning_count) > 0 else 0
    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
