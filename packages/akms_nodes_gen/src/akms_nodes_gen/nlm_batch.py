#!/usr/bin/env python3
"""Serial NotebookLM batch generator for AKMS node YAML.

This module is intentionally separate from ``generate_nodes_pipeline.py``:
Python orchestrates the batch, NotebookLM performs source-grounded synthesis,
and local gates handle parsing, schema checks, edge checks, cache/resume, and
optional conversion/validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Literal

import yaml  # type: ignore[import-untyped]

from akms_nodes_gen.tools import CONVERTER_PATH as DEFAULT_CONVERTER
from akms_nodes_gen.tools import VALIDATOR_PATH as DEFAULT_VALIDATOR

OutputFormat = Literal["yaml", "json"]

#: Sentinel meaning "the caller did not specify a converter/validator", so the
#: built-in default should be used. Distinct from ``None``, which means the user
#: explicitly opted out (``--no-converter`` / ``--no-validator``).
_USE_DEFAULT = object()

TIER1_IDS = {
    "skill-taichi-gpu-sim",
    "skill-computational-mechanics",
    "skill-gen-test",
    "skill-sim-setup",
    "skill-repo-documentor",
}

SOURCE_REF_KEYS = {"source", "source_ref", "citation", "reference", "references"}
EDGE_TYPES = {
    "requires",
    "feeds-into",
    "refines",
    "contradicts",
    "pitfall",
    "implements",
}
EDGE_DEFAULT_WEIGHTS = {
    "requires": 1.0,
    "feeds-into": 0.5,
    "refines": 0.7,
    "contradicts": 0.0,
    "pitfall": 0.0,
    "implements": 0.0,
}
CONTEXT_SIZES = {"small", "medium", "large"}
READING_PRIORITIES = {"full", "summary", "pitfalls-only"}


@dataclass(frozen=True)
class NodeRequest:
    """A single node request from a batch plan."""

    id: str
    title: str
    source: str = ""
    status: str = ""
    hint: str = ""


@dataclass(frozen=True)
class BatchSpec:
    """Resolved batch metadata and node list."""

    plan_name: str
    batch_id: str
    name: str
    notebook_id: str
    nodes: list[NodeRequest]
    known_edge_targets: set[str]


@dataclass(frozen=True)
class QueryOptions:
    """Runtime options passed to ``nlm notebook query``."""

    notebook_id: str
    source_ids: list[str]
    timeout: float
    output_format: OutputFormat
    profile: str | None = None


@dataclass(frozen=True)
class BatchRunConfig:
    """Top-level run configuration."""

    plan_path: Path
    out_dir: Path
    prompt_file: Path
    output_format: OutputFormat
    timeout: float
    source_ids: list[str] = field(default_factory=list)
    template_file: Path | None = None
    batch_id: str | None = None
    notebook_id: str | None = None
    profile: str | None = None
    cache_dir: Path | None = None
    max_retries: int = 2
    require_source_refs: bool = True
    allow_invented_edges: bool = False
    force: bool = False
    dry_run: bool = False
    # Default to the built-in post-processors (sentinel resolved in __post_init__).
    # Pass an explicit Path to override, or None to opt out of that step.
    converter: Path | None = _USE_DEFAULT  # type: ignore[assignment]
    validator: Path | None = _USE_DEFAULT  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.converter is _USE_DEFAULT:
            object.__setattr__(self, "converter", DEFAULT_CONVERTER)
        if self.validator is _USE_DEFAULT:
            object.__setattr__(self, "validator", DEFAULT_VALIDATOR)


@dataclass
class BatchRunResult:
    ok: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: dict[str, list[str]] = field(default_factory=dict)


QueryRunner = Callable[[str, QueryOptions], str]


def load_batch(
    plan_path: Path, batch_id: str | None, notebook_id: str | None
) -> BatchSpec:
    """Load one batch/cluster from a node extraction plan."""
    data = json.loads(plan_path.read_text(encoding="utf-8"))
    clusters = data.get("clusters") or []
    if not isinstance(clusters, list) or not clusters:
        raise ValueError(f"No clusters found in {plan_path}")

    selected = _select_cluster(clusters, batch_id or data.get("batch_id"))
    resolved_notebook = (
        notebook_id
        or (selected.get("nlm") or {}).get("notebook_id")
        or selected.get("notebook_id")
        or (data.get("nlm") or {}).get("notebook_id")
    )
    if not resolved_notebook:
        raise ValueError(
            "Notebook ID is required: pass --notebook-id or set plan.nlm.notebook_id"
        )

    nodes = [_node_request(raw) for raw in selected.get("nodes", [])]
    if not nodes:
        raise ValueError(f"No nodes found in selected batch {selected.get('cluster')}")

    known_targets = set(TIER1_IDS)
    for cluster in clusters:
        for raw_node in cluster.get("nodes", []):
            if isinstance(raw_node, dict) and raw_node.get("id"):
                known_targets.add(str(raw_node["id"]))

    return BatchSpec(
        plan_name=str(data.get("plan") or plan_path.stem),
        batch_id=str(selected.get("cluster") or data.get("batch_id") or plan_path.stem),
        name=str(selected.get("name") or data.get("batch_title") or ""),
        notebook_id=str(resolved_notebook),
        nodes=nodes,
        known_edge_targets=known_targets,
    )


def parse_structured_response(raw: str, output_format: OutputFormat) -> dict:
    """Extract and parse a fenced YAML/JSON object from a NotebookLM answer."""
    answer = extract_answer_text(raw)
    body = extract_fenced_block(answer, output_format) or answer.strip()
    try:
        if output_format == "json":
            parsed = json.loads(body)
        else:
            parsed = yaml.safe_load(body)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        if output_format != "yaml":
            raise ValueError(
                f"Could not parse {output_format} response: {exc}"
            ) from exc
        # NotebookLM occasionally double-quotes LaTeX but emits literal single
        # backslashes (for example ``\mathrm``). YAML then treats ``\m`` as an
        # invalid escape. Retry once after protecting only backslashes inside
        # double-quoted YAML scalars; valid YAML never enters this fallback.
        repaired_body = _protect_double_quoted_yaml_backslashes(
            _quote_flow_style_latex_mapping_keys(
                _quote_plain_yaml_values_with_colons(body)
            )
        )
        try:
            parsed = yaml.safe_load(repaired_body)
        except yaml.YAMLError as repaired_exc:
            raise ValueError(
                f"Could not parse {output_format} response: {exc}; "
                f"LaTeX backslash repair also failed: {repaired_exc}"
            ) from exc
    if not isinstance(parsed, dict):
        raise ValueError(
            f"Expected a {output_format} mapping/object, got {type(parsed).__name__}"
        )
    return parsed


def _protect_double_quoted_yaml_backslashes(text: str) -> str:
    """Make literal LaTeX backslashes safe in YAML double-quoted scalars."""
    output: list[str] = []
    in_double_quote = False
    in_comment = False
    last_nonspace: str | None = None
    index = 0
    while index < len(text):
        char = text[index]
        if in_comment:
            output.append(char)
            if char == "\n":
                in_comment = False
                last_nonspace = None
            index += 1
            continue

        if not in_double_quote:
            if char == "#":
                in_comment = True
            elif char == '"' and last_nonspace in {None, ":", "-", "[", "{", ","}:
                in_double_quote = True
            output.append(char)
            if char == "\n":
                last_nonspace = None
            elif not char.isspace():
                last_nonspace = char
            index += 1
            continue

        if char == "\\":
            next_char = text[index + 1] if index + 1 < len(text) else ""
            if next_char in {'"', "\\"}:
                output.extend((char, next_char))
                index += 2
                continue
            output.extend(("\\", "\\"))
            index += 1
            continue
        output.append(char)
        if char == '"':
            in_double_quote = False
            last_nonspace = char
        index += 1
    return "".join(output)


def _quote_flow_style_latex_mapping_keys(text: str) -> str:
    """Quote LaTeX keys such as ``[D^{e}]`` that YAML reads as flow syntax."""

    def _quote(match: re.Match[str]) -> str:
        key = match.group("key").replace("'", "''")
        return f"{match.group('indent')}'{key}':"

    return re.sub(
        r"^(?P<indent>\s*)(?P<key>\[[^\]\n]+\]|\{[^}\n]+\})\s*:",
        _quote,
        text,
        flags=re.MULTILINE,
    )


def _quote_plain_yaml_values_with_colons(text: str) -> str:
    """Quote plain scalar values whose embedded ``: `` breaks YAML parsing."""
    pattern = re.compile(
        r"^(?P<prefix>\s*(?:-\s+)?[A-Za-z_][A-Za-z0-9_-]*:\s+)(?P<value>.+)$"
    )
    repaired_lines: list[str] = []
    for line in text.splitlines(keepends=True):
        ending = "\n" if line.endswith("\n") else ""
        content = line[:-1] if ending else line
        match = pattern.match(content)
        if match is None:
            repaired_lines.append(line)
            continue
        value = match.group("value")
        if ": " not in value or value.lstrip().startswith(
            ('"', "'", "|", ">", "[", "{")
        ):
            repaired_lines.append(line)
            continue
        quoted = value.replace("'", "''")
        repaired_lines.append(f"{match.group('prefix')}'{quoted}'{ending}")
    return "".join(repaired_lines)


def extract_answer_text(raw: str) -> str:
    """Return the answer text from either plain output or ``nlm --json`` output."""
    try:
        wrapper = json.loads(raw)
    except json.JSONDecodeError:
        return raw

    if not isinstance(wrapper, dict):
        return raw

    scopes: list[object] = []
    value = wrapper.get("value")
    if isinstance(value, dict):
        scopes.append(value)
    scopes.append(wrapper)

    for scope in scopes:
        if not isinstance(scope, dict):
            continue
        for key in ("answer", "response", "text", "content"):
            value = scope.get(key)
            if isinstance(value, str):
                return value
    return raw


def extract_fenced_block(text: str, output_format: OutputFormat) -> str | None:
    """Extract the first matching fenced block, preferring the requested format."""
    labels = ("yaml|yml",) if output_format == "yaml" else ("json",)
    patterns = [rf"```(?:{label})?\s*(.*?)\s*```" for label in labels]
    patterns.append(r"```\s*(.*?)\s*```")
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _apply_plan_owned_metadata(data: dict, spec: NodeRequest) -> dict:
    """Restore immutable metadata when a repair plan explicitly locks it.

    Claim-repair prompts ask NotebookLM to regenerate scientific content, not
    graph identity. Models can still omit edge weights or paraphrase titles, so
    repair plans opt into deterministic restoration via ``lock_plan_metadata``.
    Ordinary generation plans are unchanged.
    """
    try:
        hint = json.loads(spec.hint)
    except (json.JSONDecodeError, TypeError):
        return data
    if not isinstance(hint, dict) or hint.get("lock_plan_metadata") is not True:
        return data
    identity = hint.get("identity")
    if not isinstance(identity, dict):
        return data

    normalized = dict(data)
    normalized["id"] = spec.id
    normalized["title"] = spec.title
    for key in ("domain", "subdomain", "tags", "reading_priority"):
        if key in identity and identity[key] is not None:
            normalized[key] = identity[key]
    edges = identity.get("edges")
    if isinstance(edges, list):
        normalized_edges: list[object] = []
        for edge in edges:
            if not isinstance(edge, dict):
                normalized_edges.append(edge)
                continue
            normalized_edge = dict(edge)
            edge_type = normalized_edge.get("type")
            if (
                normalized_edge.get("weight") is None
                and edge_type in EDGE_DEFAULT_WEIGHTS
            ):
                normalized_edge["weight"] = EDGE_DEFAULT_WEIGHTS[str(edge_type)]
            normalized_edges.append(normalized_edge)
        normalized["edges"] = normalized_edges
    normalized.update(
        {
            "status": "tentative",
            "confidence": 0.90,
            "source": "hybrid",
            "content_ref": None,
            "akms_schema": "v2",
        }
    )
    return normalized


def validate_node_data(
    data: dict,
    spec: NodeRequest,
    known_edge_targets: set[str],
    require_source_refs: bool,
    allow_invented_edges: bool = False,
) -> list[str]:
    """Validate local AKMS constraints before writing output."""
    errors: list[str] = []
    required = [
        "id",
        "title",
        "domain",
        "tags",
        "status",
        "confidence",
        "source",
        "edges",
        "context_size",
        "reading_priority",
        "content_ref",
        "akms_schema",
        "summary",
        "core_concept",
        "math_formulation",
        "algorithms",
        "pitfalls",
    ]
    for field_name in required:
        if field_name not in data:
            errors.append(f"Missing required field: {field_name}")

    if data.get("id") != spec.id:
        errors.append(f"id must be {spec.id!r}, got {data.get('id')!r}")
    if data.get("title") != spec.title:
        errors.append(f"title must be {spec.title!r}, got {data.get('title')!r}")
    if data.get("status") != "tentative":
        errors.append("status must be tentative")
    if data.get("source") != "hybrid":
        errors.append("source must be hybrid")
    if data.get("akms_schema") != "v2":
        errors.append("akms_schema must be v2")
    if data.get("content_ref") is not None:
        errors.append("content_ref must be null")
    if data.get("context_size") not in CONTEXT_SIZES:
        errors.append("context_size must be one of small, medium, large")
    if data.get("reading_priority") not in READING_PRIORITIES:
        errors.append("reading_priority must be full, summary, or pitfalls-only")

    tags = data.get("tags")
    if not isinstance(tags, list) or not tags:
        errors.append("tags must be a non-empty list")

    errors.extend(
        _validate_edges(data.get("edges"), known_edge_targets, allow_invented_edges)
    )

    if require_source_refs:
        errors.extend(_validate_source_refs(data))

    return errors


def build_generation_prompt(
    spec: NodeRequest,
    batch: BatchSpec,
    prompt_file: Path,
    output_format: OutputFormat,
    template_file: Path | None,
) -> str:
    """Build a NotebookLM prompt from external prompt/template files and node metadata."""
    prompt_text = _render_prompt_template(
        prompt_file.read_text(encoding="utf-8"),
        spec=spec,
        batch=batch,
        output_format=output_format,
    )
    template_text = template_file.read_text(encoding="utf-8") if template_file else ""

    sections = [
        prompt_text.strip(),
        "NODE SPEC:",
        json.dumps(
            {
                "id": spec.id,
                "title": spec.title,
                "source": spec.source,
                "status": spec.status,
                "hint": spec.hint,
                "batch_id": batch.batch_id,
                "batch_name": batch.name,
            },
            indent=2,
            ensure_ascii=False,
        ),
        "KNOWN EDGE TARGET IDS:",
        "\n".join(sorted(batch.known_edge_targets)),
        f"REQUESTED OUTPUT FORMAT: {output_format}",
    ]
    if template_text.strip():
        sections.extend(["OUTPUT TEMPLATE:", template_text.strip()])
    return "\n\n".join(sections).strip()


def run_nlm_query(question: str, options: QueryOptions) -> str:
    """Run ``nlm notebook query`` and return stdout."""
    cmd = [
        "nlm",
        "notebook",
        "query",
        options.notebook_id,
        question,
        "--json",
        "--timeout",
        str(options.timeout),
    ]
    if options.source_ids:
        cmd.extend(["--source-ids", ",".join(options.source_ids)])
    if options.profile:
        cmd.extend(["--profile", options.profile])

    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=options.timeout + 30,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "The `nlm` CLI was not found on PATH. Node generation queries "
            "NotebookLM through the external `nlm` tool; install it "
            "(`uv tool install notebooklm-mcp-cli`) and authenticate before "
            "running a batch."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"nlm query timed out after {options.timeout}s") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"nlm query failed with rc={completed.returncode}: {detail}")
    return completed.stdout


def run_batch(
    config: BatchRunConfig, query_runner: QueryRunner = run_nlm_query
) -> BatchRunResult:
    """Run one batch serially and write canonical YAML outputs."""
    batch = load_batch(config.plan_path, config.batch_id, config.notebook_id)
    config.out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = config.cache_dir or (config.out_dir / "_nlm_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    state_path = config.out_dir / "_nlm_batch_state.json"
    state = _load_state(state_path)
    result = BatchRunResult()

    query_options = QueryOptions(
        notebook_id=batch.notebook_id,
        source_ids=config.source_ids,
        timeout=config.timeout,
        output_format=config.output_format,
        profile=config.profile,
    )

    for spec in batch.nodes:
        out_path = config.out_dir / f"{spec.id}.yaml"
        if not config.force and spec.id in state["completed"] and out_path.exists():
            result.skipped.append(spec.id)
            continue
        if config.dry_run:
            result.skipped.append(spec.id)
            continue

        base_prompt = build_generation_prompt(
            spec,
            batch,
            config.prompt_file,
            config.output_format,
            config.template_file,
        )
        errors: list[str] = []
        data: dict | None = None
        raw_response = ""

        for attempt in range(config.max_retries + 1):
            question = (
                base_prompt
                if attempt == 0
                else _repair_prompt(
                    base_prompt, raw_response, errors, config.output_format
                )
            )
            try:
                raw_response = _cached_query(
                    question, query_options, cache_dir, query_runner
                )
                data = parse_structured_response(raw_response, config.output_format)
                data = _apply_plan_owned_metadata(data, spec)
                errors = validate_node_data(
                    data,
                    spec=spec,
                    known_edge_targets=batch.known_edge_targets,
                    require_source_refs=config.require_source_refs,
                    allow_invented_edges=config.allow_invented_edges,
                )
            except Exception as exc:  # noqa: BLE001 - errors are persisted for manual repair.
                errors = [str(exc)]
                data = None
            if not errors and data is not None:
                break

        if errors or data is None:
            result.failed[spec.id] = errors or ["Unknown generation failure"]
            state["failed"][spec.id] = result.failed[spec.id]
            _save_state(state_path, state)
            continue

        _write_raw_response(config.out_dir, spec.id, raw_response)
        _write_yaml(out_path, data)

        post_errors = _run_postprocessors(out_path, config.converter, config.validator)
        if post_errors:
            result.failed[spec.id] = post_errors
            state["failed"][spec.id] = post_errors
            _save_state(state_path, state)
            continue

        result.ok.append(spec.id)
        if spec.id not in state["completed"]:
            state["completed"].append(spec.id)
        state["failed"].pop(spec.id, None)
        _save_state(state_path, state)

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate one NotebookLM-backed AKMS batch serially."
    )
    parser.add_argument("--plan", required=True, type=Path, help="Batch plan JSON path")
    parser.add_argument(
        "--out-dir",
        required=True,
        type=Path,
        help="Output directory for YAML and audit files",
    )
    parser.add_argument(
        "--prompt-file", required=True, type=Path, help="NotebookLM prompt file"
    )
    parser.add_argument("--template-file", type=Path, help="YAML output template file")
    parser.add_argument(
        "--notebook-id",
        help="NotebookLM notebook ID override; defaults to plan.nlm.notebook_id",
    )
    parser.add_argument(
        "--batch-id",
        help="Cluster/batch id to run; required when the plan has multiple clusters",
    )
    parser.add_argument(
        "--source-id",
        action="append",
        default=[],
        help="NotebookLM source ID; repeatable",
    )
    parser.add_argument(
        "--source-ids", default="", help="Comma-separated NotebookLM source IDs"
    )
    parser.add_argument(
        "--source-ids-file", type=Path, help="File containing source IDs, one per line"
    )
    parser.add_argument(
        "--timeout",
        required=True,
        type=float,
        help="NotebookLM query timeout in seconds",
    )
    parser.add_argument(
        "--output-format",
        required=True,
        choices=("yaml", "json"),
        help="Structured format to request",
    )
    parser.add_argument("--profile", help="nlm auth profile")
    parser.add_argument("--cache-dir", type=Path, help="Response cache directory")
    parser.add_argument(
        "--max-retries", type=int, default=2, help="Repair retries per node"
    )
    parser.add_argument(
        "--require-source-refs", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--allow-invented-edges", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate nodes even if state marks them complete",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve batch only; do not call NotebookLM",
    )
    parser.add_argument(
        "--converter",
        type=Path,
        default=_USE_DEFAULT,
        help="YAML-to-Markdown converter script (default: built-in yaml_to_markdown.py)",
    )
    parser.add_argument(
        "--no-converter",
        dest="converter",
        action="store_const",
        const=None,
        help="Disable the YAML-to-Markdown conversion step",
    )
    parser.add_argument(
        "--validator",
        type=Path,
        default=_USE_DEFAULT,
        help="Markdown validator script (default: built-in validate_markdown.py)",
    )
    parser.add_argument(
        "--no-validator",
        dest="validator",
        action="store_const",
        const=None,
        help="Disable the Markdown validation step",
    )

    args = parser.parse_args(argv)
    source_ids = _parse_source_ids(
        args.source_id, args.source_ids, args.source_ids_file
    )
    # An explicit empty value also opts out of that post-processor.
    converter = (
        None
        if (isinstance(args.converter, Path) and str(args.converter) in ("", "."))
        else args.converter
    )
    validator = (
        None
        if (isinstance(args.validator, Path) and str(args.validator) in ("", "."))
        else args.validator
    )
    result = run_batch(
        BatchRunConfig(
            plan_path=args.plan,
            out_dir=args.out_dir,
            prompt_file=args.prompt_file,
            template_file=args.template_file,
            output_format=args.output_format,
            timeout=args.timeout,
            source_ids=source_ids,
            batch_id=args.batch_id,
            notebook_id=args.notebook_id,
            profile=args.profile,
            cache_dir=args.cache_dir,
            max_retries=args.max_retries,
            require_source_refs=args.require_source_refs,
            allow_invented_edges=args.allow_invented_edges,
            force=args.force,
            dry_run=args.dry_run,
            converter=converter,
            validator=validator,
        )
    )
    _print_summary(result)
    return 1 if result.failed else 0


def _select_cluster(clusters: list[dict], batch_id: str | None) -> dict:
    if batch_id:
        for cluster in clusters:
            if str(cluster.get("cluster")) == str(batch_id):
                return cluster
        raise ValueError(f"Batch/cluster {batch_id!r} not found")
    if len(clusters) == 1:
        return clusters[0]
    raise ValueError("Plan has multiple clusters; pass --batch-id")


def _node_request(raw: dict) -> NodeRequest:
    if not isinstance(raw, dict):
        raise ValueError(f"Node entry must be an object, got {type(raw).__name__}")
    return NodeRequest(
        id=str(raw["id"]),
        title=str(raw["title"]),
        source=str(raw.get("source") or ""),
        status=str(raw.get("status") or ""),
        hint=str(raw.get("hint") or raw.get("key_content") or raw.get("notes") or ""),
    )


def _render_prompt_template(
    text: str, spec: NodeRequest, batch: BatchSpec, output_format: OutputFormat
) -> str:
    replacements = {
        "{node_id}": spec.id,
        "{node_title}": spec.title,
        "{node_source}": spec.source,
        "{batch_id}": batch.batch_id,
        "{batch_name}": batch.name,
        "{notebook_id}": batch.notebook_id,
        "{output_format}": output_format,
        "{{NODE_ID}}": spec.id,
        "{{NODE_TITLE}}": spec.title,
        "{{NODE_SOURCE}}": spec.source,
        "{{BATCH_ID}}": batch.batch_id,
        "{{BATCH_NAME}}": batch.name,
        "{{NOTEBOOK_ID}}": batch.notebook_id,
        "{{OUTPUT_FORMAT}}": output_format,
    }
    rendered = text
    for needle, value in replacements.items():
        rendered = rendered.replace(needle, value)
    return rendered


def _validate_edges(
    edges: object, known_edge_targets: set[str], allow_invented_edges: bool
) -> list[str]:
    errors: list[str] = []
    if not isinstance(edges, list) or not edges:
        return ["edges must be a non-empty list"]
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            errors.append(f"edges[{index}] must be a mapping")
            continue
        target = edge.get("to")
        edge_type = edge.get("type")
        if not target:
            errors.append(f"edges[{index}].to is required")
        elif not allow_invented_edges and str(target) not in known_edge_targets:
            errors.append(f"Unknown edge target: {target}")
        if edge_type not in EDGE_TYPES:
            errors.append(f"Invalid edge type for {target}: {edge_type}")
        weight_value = edge.get("weight")
        if weight_value is None:
            errors.append(f"Invalid edge weight for {target}: {weight_value!r}")
            continue
        try:
            weight = float(weight_value)
        except (TypeError, ValueError):
            errors.append(f"Invalid edge weight for {target}: {weight_value!r}")
        else:
            if not 0.0 <= weight <= 1.0:
                errors.append(f"Edge weight out of range for {target}: {weight}")
    return errors


def _validate_source_refs(data: dict) -> list[str]:
    errors: list[str] = []
    refs = data.get("references")
    if not isinstance(refs, list) or not refs:
        errors.append(
            "references must be a non-empty list when source refs are required"
        )

    math = data.get("math_formulation")
    equations = math.get("equations", []) if isinstance(math, dict) else []
    for index, equation in enumerate(equations):
        if isinstance(equation, dict) and not _has_source_ref(equation):
            errors.append(
                f"math_formulation.equations[{index}] must include source_ref/source/citation"
            )

    algorithms = data.get("algorithms", [])
    for index, algorithm in enumerate(
        algorithms if isinstance(algorithms, list) else []
    ):
        if isinstance(algorithm, dict) and not _has_source_ref(algorithm):
            errors.append(
                f"algorithms[{index}] must include source_ref/source/citation"
            )

    pitfalls = data.get("pitfalls", [])
    for index, pitfall in enumerate(pitfalls if isinstance(pitfalls, list) else []):
        if isinstance(pitfall, dict) and not _has_source_ref(pitfall):
            errors.append(f"pitfalls[{index}] must include source_ref/source/citation")

    return errors


def _has_source_ref(mapping: dict) -> bool:
    return any(mapping.get(key) for key in SOURCE_REF_KEYS)


def _repair_prompt(
    base_prompt: str, raw_response: str, errors: list[str], output_format: OutputFormat
) -> str:
    return "\n\n".join(
        [
            base_prompt,
            "The previous response failed local validation.",
            "Return a complete corrected response only. Do not include commentary.",
            f"Output format: {output_format}",
            "Validation errors:",
            "\n".join(f"- {error}" for error in errors),
            "Previous response:",
            extract_answer_text(raw_response)[:12000],
        ]
    )


def _cached_query(
    question: str, options: QueryOptions, cache_dir: Path, query_runner: QueryRunner
) -> str:
    cache_key = _cache_key(question, options)
    cache_path = cache_dir / f"{cache_key}.json"
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        return str(cached["raw"])
    raw = query_runner(question, options)
    cache_path.write_text(
        json.dumps(
            {
                "notebook_id": options.notebook_id,
                "source_ids": options.source_ids,
                "timeout": options.timeout,
                "output_format": options.output_format,
                "raw": raw,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return raw


def _cache_key(question: str, options: QueryOptions) -> str:
    payload = json.dumps(
        {
            "question": question,
            "notebook_id": options.notebook_id,
            "source_ids": options.source_ids,
            "output_format": options.output_format,
            "profile": options.profile,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_raw_response(out_dir: Path, node_id: str, raw: str) -> None:
    raw_dir = out_dir / "_raw_responses"
    raw_dir.mkdir(exist_ok=True)
    (raw_dir / f"{node_id}.txt").write_text(raw, encoding="utf-8")


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )


def _run_postprocessors(
    yaml_path: Path, converter: Path | None, validator: Path | None
) -> list[str]:
    errors: list[str] = []
    if converter:
        errors.extend(
            _run_script(
                [sys.executable, str(converter), str(yaml_path), "-v"], "converter"
            )
        )
    if validator:
        md_path = yaml_path.with_suffix(".md")
        errors.extend(
            _run_script(
                [sys.executable, str(validator), str(md_path), "--validate-only", "-v"],
                "validator",
            )
        )
    return errors


def _run_script(cmd: list[str], label: str) -> list[str]:
    completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if completed.returncode == 0:
        return []
    detail = completed.stderr.strip() or completed.stdout.strip()
    return [f"{label} failed with rc={completed.returncode}: {detail}"]


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {"completed": [], "failed": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"completed": [], "failed": {}}
    completed = data.get("completed")
    failed = data.get("failed")
    return {
        "completed": completed if isinstance(completed, list) else [],
        "failed": failed if isinstance(failed, dict) else {},
    }


def _save_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _parse_source_ids(
    source_id_items: Iterable[str], source_ids: str, source_ids_file: Path | None
) -> list[str]:
    ids: list[str] = []
    ids.extend(item.strip() for item in source_id_items if item and item.strip())
    if source_ids:
        ids.extend(item.strip() for item in source_ids.split(",") if item.strip())
    if source_ids_file:
        ids.extend(
            line.strip()
            for line in source_ids_file.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    return list(dict.fromkeys(ids))


def _print_summary(result: BatchRunResult) -> None:
    print("NLM batch generation summary")
    print(f"  OK:      {len(result.ok)}")
    print(f"  SKIPPED: {len(result.skipped)}")
    print(f"  FAILED:  {len(result.failed)}")
    for node_id, errors in result.failed.items():
        print(f"  - {node_id}: {'; '.join(errors)}")


if __name__ == "__main__":
    sys.exit(main())
