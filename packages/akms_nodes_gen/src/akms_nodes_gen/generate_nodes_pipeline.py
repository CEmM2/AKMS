#!/usr/bin/env python3
"""
AKMS Node Generation Pipeline (LLM-as-generator path)

Reads inventory JSON files, groups nodes into batches, generates each batch via
LiteLLM (provider: anthropic | openai-compatible/local | google), optionally
grounded in NotebookLM source material fetched through the `nlm` CLI, validates
output against the v2 schema, and writes clean .md files.

For NotebookLM-as-generator (no external LLM provider at all), use the canonical
CLI path instead: ``python -m akms_nodes_gen.nlm_batch`` — there NotebookLM does
the synthesis and no API key is required.

Usage:
    # Generate all nodes from all inventory JSONs
    python generate_nodes_pipeline.py --input json/ --output generated_nodes/

    # Generate only new nodes (skip exists/exists-enrich)
    python generate_nodes_pipeline.py --input json/ --output generated_nodes/ --status new

    # Generate a specific category
    python generate_nodes_pipeline.py --input json/2c_constit_plasticity.json --output generated_nodes/

    # Dry run: show batches without calling API
    python generate_nodes_pipeline.py --input json/ --dry-run

    # Resume from a specific batch (after partial run)
    python generate_nodes_pipeline.py --input json/ --output generated_nodes/ --resume-from 5

    # Use an OpenAI-compatible / local endpoint (vLLM, Ollama, LM Studio, …)
    python generate_nodes_pipeline.py --input json/ --output generated_nodes/ \
        --provider openai --model my-local-model --api-base http://localhost:8000/v1

    # Ground generation in a NotebookLM notebook via the `nlm` CLI (not MCP)
    python generate_nodes_pipeline.py --input json/ --output generated_nodes/ \
        --notebooklm-id <notebook-uuid>

Environment:
    AKMS_LLM_PROVIDER    — Provider: anthropic (default) | openai | google
    ANTHROPIC_API_KEY /
    OPENAI_API_KEY /
    GEMINI_API_KEY       — API key for the selected provider (openai/local: optional)
    AKMS_LLM_API_BASE    — Base URL for an OpenAI-compatible / local endpoint
    AKMS_MODEL           — Override model (default: provider-specific)
    AKMS_BATCH_SIZE      — Nodes per batch (default: 4)
    AKMS_MAX_TOKENS      — Max tokens per response (default: 16000)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# ─── Conditional imports ──────────────────────────────────────────────────────
# All LLM generation is routed through LiteLLM (one client; many hosted providers
# plus any OpenAI-compatible / local endpoint). It is an optional dependency —
# install with ``akms-nodes-gen[llm]``. Absent ⇒ the LLM path is unavailable at
# call time, never an ImportError.
try:
    import litellm

    HAS_LITELLM = True
except ImportError:
    HAS_LITELLM = False


# ═══════════════════════════════════════════════════════════════════════════════
#                          CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_PROVIDER = "anthropic"

# Each provider maps onto a LiteLLM model prefix + the API-key env var LiteLLM
# reads for it. ``openai`` is the OpenAI-compatible / local-model lane: the key
# is optional (most local servers ignore it) and an --api-base is expected.
PROVIDERS = {
    "anthropic": {
        "prefix": "anthropic/",
        "key_env": "ANTHROPIC_API_KEY",
        "key_required": True,
        "default_model": "claude-sonnet-4-20250514",
    },
    "openai": {  # OpenAI-compatible endpoints incl. local models (vLLM, Ollama, LM Studio…)
        "prefix": "openai/",
        "key_env": "OPENAI_API_KEY",
        "key_required": False,
        "default_model": "gpt-4o",
    },
    "google": {
        "prefix": "gemini/",
        "key_env": "GEMINI_API_KEY",  # LiteLLM convention; GOOGLE_API_KEY accepted as fallback
        "key_required": True,
        "default_model": "gemini-2.0-flash",
    },
}
DEFAULT_MODEL = PROVIDERS[DEFAULT_PROVIDER]["default_model"]
DEFAULT_BATCH_SIZE = 4
DEFAULT_MAX_TOKENS = 16000
DEFAULT_NLM_TIMEOUT = 180.0


def resolve_litellm_model(provider: str, model: str) -> str:
    """Build the LiteLLM model id. A model that already names a provider
    (contains '/') is passed through unchanged; otherwise the provider prefix
    is applied (e.g. anthropic + claude-… → 'anthropic/claude-…')."""
    if "/" in model:
        return model
    return PROVIDERS[provider]["prefix"] + model


BATCH_SEPARATOR_RE = re.compile(r"^═{3,}\s*FILE:\s*(.+?)\s*═{3,}$", re.MULTILINE)
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Tier 1 nodes that always exist
TIER1_IDS = {
    "skill-taichi-gpu-sim",
    "skill-computational-mechanics",
    "skill-gen-test",
    "skill-sim-setup",
    "skill-repo-documentor",
}


# ═══════════════════════════════════════════════════════════════════════════════
#                          SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = r"""You are an Expert Computational Mechanics Engineer and Knowledge Extraction Agent for the AKMS (Adaptive Knowledge Management System).

Your job is to generate concise, highly actionable "Domain Knowledge Nodes" in Markdown format based on your deep expertise in computational mechanics, FEM, constitutive modeling, solvers, and related domains.

═══════════════════════════════════════════════════════════════
                      BATCH MODE
═══════════════════════════════════════════════════════════════

I will submit BATCHES of nodes as a table. Each row has: id, title, and optionally a hint (key concepts to focus on, or explicit edge targets).

For each row, generate the complete .md file content. Separate each node file with:

═══ FILE: {id}.md ═══

Generate ALL nodes in the batch before stopping. Do not ask for confirmation between nodes.

═══════════════════════════════════════════════════════════════
                   EDGE COHERENCE RULES
═══════════════════════════════════════════════════════════════

Because you are generating multiple related nodes at once, you MUST cross-reference them:

1. WITHIN-BATCH EDGES: When node A in this batch depends on node B in this batch, use the exact id from the batch table in the `edges` block.
2. CROSS-BATCH EDGES: I will provide a list of "already existing node ids" with the batch. Reference these by their exact id when a dependency exists.
3. EDGE TYPES (use exactly these):
   - requires    → hard dependency (must understand B before A)
   - feeds-into  → A's output is input to B (but B can be understood alone)
   - refines     → A is a more detailed/specialized version of B
   - contradicts → A and B present conflicting formulations (rare, flag explicitly)
4. EDGE WEIGHTS: 1.0 = hard prerequisite, 0.8 = strong, 0.5 = loose, 0.3 = tangential
5. AIM for 2–4 edges per node. Every node should have at least one edge.

═══════════════════════════════════════════════════════════════
                    SCHEMA (STRICT)
═══════════════════════════════════════════════════════════════

You MUST include this exact YAML frontmatter. Do not invent new fields.

---
id: {exact id from my table}
title: "{exact title from my table}"
domain: {one of: computational-mechanics | gpu-simulation | theoretical-physics | project-meta}
subdomain: {finer category}
tags:
  - {3 to 6 relevant conceptual tags, snake_case}
status: tentative
confidence: 0.90
source: hybrid
confidence_floor: 0.70 # OPTIONAL - set for foundational nodes
edges:
  - to: {target-node-id}
    type: {requires | feeds-into | refines | contradicts}
    weight: {0.3 | 0.5 | 0.8 | 1.0}
    note: "{one sentence why this edge exists}"
context_size: {small | medium | large}
reading_priority: {full | summary | pitfalls-only}
load_with: # OPTIONAL list of nodes to coload
content_ref: null
akms_schema: v2
---

═══════════════════════════════════════════════════════════════
                 MARKDOWN CONTENT RULES
═══════════════════════════════════════════════════════════════

Below the frontmatter, use EXACTLY these sections:

# {Title}

## Summary
3–5 sentences. Self-contained. Include the key equation or concept name. MANDATORY.

## 1. Core Concept
Brief theoretical definition. State physical assumptions explicitly.

## 2. Mathematical Formulation
Governing equations using LaTeX blocks ($$). Include notation table if >5 symbols.

## 3. Algorithmic Implementation
All algorithms MUST be written in algpseudocode LaTeX format inside $$ blocks.
No Python, C++, or raw pseudocode allowed.
After each algorithm block, add a brief "Taichi Mapping:" note.

## 4. Known Pitfalls
CRITICAL. Warnings, numerical stability issues, boundary condition gotchas, convergence traps.

═══════════════════════════════════════════════════════════════
                    QUALITY RULES
═══════════════════════════════════════════════════════════════

1. CONCISENESS: medium node = ~800–1200 words. Every sentence must earn its place.
2. PHYSICAL ASSUMPTIONS: Explicitly state in §1 for every model.
3. ALGORITHMS: ONLY algpseudocode LaTeX in §3. Use standard LaTeX variable names, e.g. \boldsymbol{\sigma}.
4. CROSS-REFERENCES: Use `→ see: {node-id}` in body text when referencing other nodes.
"""


# ═══════════════════════════════════════════════════════════════════════════════
#                          DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class NodeSpec:
    id: str
    title: str
    key_content: str
    tags: list[str]
    notes: str | None
    status: str
    domain: str | None = None
    subdomain: str | None = None

    @property
    def hint(self) -> str:
        parts = [self.key_content]
        if self.notes:
            parts.append(self.notes)
        return " | ".join(parts)


@dataclass
class BatchResult:
    batch_index: int
    category: str
    node_ids: list[str]
    raw_response: str
    files: dict[str, str]  # filename → content
    errors: list[str]
    duration_s: float


@dataclass
class PipelineState:
    """Tracks progress for resumption."""

    completed_batches: list[int] = field(default_factory=list)
    generated_ids: set[str] = field(default_factory=set)
    failed_batches: list[int] = field(default_factory=list)

    def save(self, path: Path) -> None:
        data = {
            "completed_batches": self.completed_batches,
            "generated_ids": sorted(self.generated_ids),
            "failed_batches": self.failed_batches,
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "PipelineState":
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            completed_batches=data.get("completed_batches", []),
            generated_ids=set(data.get("generated_ids", [])),
            failed_batches=data.get("failed_batches", []),
        )


# ═══════════════════════════════════════════════════════════════════════════════
#                     INVENTORY LOADING & BATCHING
# ═══════════════════════════════════════════════════════════════════════════════


def load_inventory(
    paths: list[Path], status_filter: set[str] | None = None
) -> list[tuple[str, list[NodeSpec]]]:
    """Load inventory JSONs, return list of (category_name, nodes) pairs."""
    categories: list[tuple[str, list[NodeSpec]]] = []

    for p in sorted(paths):
        if p.is_dir():
            files = sorted(p.glob("*.json"))
        else:
            files = [p]

        for f in files:
            data = json.loads(f.read_text(encoding="utf-8"))
            cat_name = data.get("category", f.stem)
            nodes = []
            for n in data.get("nodes", []):
                status = n.get("status", "new")
                if status_filter and status not in status_filter:
                    continue
                nodes.append(
                    NodeSpec(
                        id=n["id"],
                        title=n["title"],
                        key_content=n.get("key_content", ""),
                        tags=n.get("tags", []),
                        notes=n.get("notes"),
                        status=status,
                        domain=n.get("domain"),
                        subdomain=n.get("subdomain"),
                    )
                )
            if nodes:
                categories.append((cat_name, nodes))

    return categories


def make_batches(
    categories: list[tuple[str, list[NodeSpec]]],
    batch_size: int,
) -> list[tuple[int, str, list[NodeSpec]]]:
    """
    Create batches respecting category boundaries.
    Returns list of (batch_index, category_name, nodes).
    """
    batches: list[tuple[int, str, list[NodeSpec]]] = []
    idx = 0
    for cat_name, nodes in categories:
        for i in range(0, len(nodes), batch_size):
            chunk = nodes[i : i + batch_size]
            batches.append((idx, cat_name, chunk))
            idx += 1
    return batches


# ═══════════════════════════════════════════════════════════════════════════════
#                     PROMPT CONSTRUCTION
# ═══════════════════════════════════════════════════════════════════════════════


def build_user_message(
    category: str,
    nodes: list[NodeSpec],
    existing_ids: set[str],
) -> str:
    """Build the user message with batch table + existing ids."""
    lines = [f"### Batch: {category}"]
    lines.append(f"Already existing node ids: {', '.join(sorted(existing_ids))}")
    lines.append("")
    lines.append("| id | title | hint |")
    lines.append("|---|---|---|")
    for n in nodes:
        lines.append(f"| {n.id} | {n.title} | {n.hint} |")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
#                  LLM PROVIDER LAYER (routed through LiteLLM)
# ═══════════════════════════════════════════════════════════════════════════════


class LLMClient:
    """One client over every provider, via LiteLLM. ``api_base`` targets an
    OpenAI-compatible / local endpoint (vLLM, Ollama, LM Studio, …). LiteLLM is
    an optional dependency — install ``akms-nodes-gen[llm]``."""

    def __init__(
        self,
        model: str,
        max_tokens: int,
        api_key: str | None = None,
        api_base: str | None = None,
    ):
        self.model = model  # already a resolved LiteLLM model id
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.api_base = api_base

    def complete(self, system: str, user: str) -> str:
        """Single-turn completion via ``litellm.completion``; returns the text."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": self.max_tokens,
        }
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.api_base:
            kwargs["api_base"] = self.api_base
        resp = litellm.completion(**kwargs)
        return resp.choices[0].message.content or ""


# ═══════════════════════════════════════════════════════════════════════════════
#         NOTEBOOKLM GROUNDING (via the `nlm` CLI — not MCP, not a Python dep)
# ═══════════════════════════════════════════════════════════════════════════════


def fetch_nlm_context(
    notebook_id: str,
    nodes: "list[NodeSpec]",
    timeout: float,
    profile: str | None,
) -> str:
    """Query the `nlm` CLI for source material on a batch's topics and return the
    answer text, to be prepended to the prompt. Shells out exactly like
    ``nlm_batch.py`` — so a missing `nlm` binary surfaces as a runtime error here,
    never an import error. Reuses the canonical CLI query helper."""
    from akms_nodes_gen.nlm_batch import (
        QueryOptions,
        extract_answer_text,
        run_nlm_query,
    )

    topics = "; ".join(f"{n.id} ({n.title})" for n in nodes)
    question = (
        "From the notebook's source material, summarize the key definitions, "
        "governing equations, algorithms, and citations relevant to these topics. "
        "Be specific and cite sources where possible. Topics: " + topics
    )
    options = QueryOptions(
        notebook_id=notebook_id,
        source_ids=[],
        timeout=timeout,
        output_format="json",
        profile=profile,
    )
    return extract_answer_text(run_nlm_query(question, options)).strip()


# ═══════════════════════════════════════════════════════════════════════════════
#                     RESPONSE PARSING
# ═══════════════════════════════════════════════════════════════════════════════


def split_batch_response(raw: str) -> dict[str, str]:
    """Split a batch response into {filename: content} dict."""
    parts = BATCH_SEPARATOR_RE.split(raw)
    files: dict[str, str] = {}

    if len(parts) < 3:
        # No separators — try to extract a single file from the whole response
        if "---" in raw:
            files["unknown.md"] = raw.strip()
        return files

    for i in range(1, len(parts), 2):
        filename = parts[i].strip()
        if not filename.endswith(".md"):
            filename += ".md"
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if content:
            files[filename] = content

    return files


def quick_validate(content: str) -> list[str]:
    """
    Fast validation of a single node file. Returns list of error strings.
    Uses pydantic if available, falls back to basic checks.
    """
    errors: list[str] = []

    # Extract frontmatter
    match = FRONTMATTER_RE.match(content)
    if not match:
        return ["No YAML frontmatter found"]

    yaml_text = match.group(1)
    body = content[match.end() :]

    try:
        fm = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"]

    if not isinstance(fm, dict):
        return ["Frontmatter is not a dict"]

    # Required fields
    for field_name in (
        "id",
        "title",
        "domain",
        "tags",
        "status",
        "confidence",
        "source",
        "akms_schema",
    ):
        if field_name not in fm:
            errors.append(f"Missing required field: {field_name}")

    # Schema version
    if fm.get("akms_schema") != "v2":
        errors.append(f"akms_schema is '{fm.get('akms_schema')}', expected 'v2'")

    # Status
    if fm.get("status") not in ("draft", "tentative", "established", "deprecated"):
        errors.append(f"Invalid status: {fm.get('status')}")

    # For generation specifically, it MUST be tentative and hybrid
    if fm.get("status") != "tentative":
        errors.append(
            f"Generated node status must be 'tentative', got '{fm.get('status')}'"
        )

    if fm.get("source") != "hybrid":
        errors.append(
            f"Generated node source must be 'hybrid', got '{fm.get('source')}'"
        )

    # Content_ref MUST be in the dictionary and its value MUST be None
    if "content_ref" not in fm:
        errors.append("Missing required field: content_ref")
    elif fm.get("content_ref") is not None:
        errors.append(
            f"Generated node content_ref must be null, got '{fm.get('content_ref')}'"
        )

    # Confidence range
    conf = fm.get("confidence")
    if conf is not None and not (0.0 <= float(conf) <= 1.0):
        errors.append(f"Confidence {conf} out of range")

    # Tags
    tags = fm.get("tags", [])
    if not tags or len(tags) < 1:
        errors.append("No tags")

    # Summary section
    if "## Summary" not in body:
        errors.append("Missing ## Summary section")

    # Experiential fields that shouldn't be here
    for bad_field in ("activations", "last_activated", "session_refs", "auto_update"):
        if bad_field in fm:
            errors.append(f"Experiential field '{bad_field}' in frontmatter")

    return errors


# ═══════════════════════════════════════════════════════════════════════════════
#                          PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════


def run_pipeline(args: argparse.Namespace) -> int:
    """Main pipeline execution."""

    # ── Load inventory ──
    input_paths = [Path(p) for p in args.input]
    status_filter = set(args.status.split(",")) if args.status else None
    categories = load_inventory(input_paths, status_filter)

    if not categories:
        print("No nodes found matching the filter.", file=sys.stderr)
        return 1

    total_nodes = sum(len(nodes) for _, nodes in categories)
    print(f"Loaded {total_nodes} nodes across {len(categories)} categories")

    # ── Create batches ──
    batch_size = int(
        os.environ.get("AKMS_BATCH_SIZE", args.batch_size or DEFAULT_BATCH_SIZE)
    )
    batches = make_batches(categories, batch_size)
    print(f"Created {len(batches)} batches (size {batch_size})")

    # ── Dry run ──
    if args.dry_run:
        print("\n═══ DRY RUN — Batch Plan ═══\n")
        for idx, cat, nodes in batches:
            node_list = ", ".join(n.id for n in nodes)
            print(f"  Batch {idx:2d} [{cat}]: {node_list}")
        print(f"\nTotal: {len(batches)} API calls for {total_nodes} nodes")
        return 0

    # ── Setup output ──
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "_raw_responses"
    raw_dir.mkdir(exist_ok=True)

    # ── Load state for resumption ──
    state_path = output_dir / "_pipeline_state.json"
    state = PipelineState.load(state_path)

    resume_from = args.resume_from or 0
    if state.completed_batches:
        last_done = max(state.completed_batches)
        if resume_from <= last_done:
            resume_from = last_done + 1
            print(f"Resuming from batch {resume_from} (last completed: {last_done})")

    # ── LLM provider, routed through LiteLLM (anthropic | openai-compatible | google) ──
    provider = (
        os.environ.get("AKMS_LLM_PROVIDER") or args.provider or DEFAULT_PROVIDER
    ).lower()
    if provider not in PROVIDERS:
        print(
            f"ERROR: unknown provider '{provider}' (choose: {', '.join(PROVIDERS)})",
            file=sys.stderr,
        )
        return 1
    if not HAS_LITELLM:
        print(
            "ERROR: litellm not installed. Install with: pip install 'akms-nodes-gen[llm]'",
            file=sys.stderr,
        )
        return 1

    pcfg = PROVIDERS[provider]
    # api_base: explicit flag/env wins; for the openai lane also accept OPENAI_API_BASE.
    api_base = (
        args.api_base
        or os.environ.get("AKMS_LLM_API_BASE")
        or (os.environ.get("OPENAI_API_BASE") if provider == "openai" else None)
    )
    api_key = os.environ.get(pcfg["key_env"])
    if provider == "google" and not api_key:
        api_key = os.environ.get("GOOGLE_API_KEY")  # accepted fallback
    if not api_key and pcfg["key_required"]:
        print(f"ERROR: {pcfg['key_env']} environment variable not set", file=sys.stderr)
        return 1

    model = resolve_litellm_model(
        provider, os.environ.get("AKMS_MODEL") or args.model or pcfg["default_model"]
    )
    max_tokens = int(
        os.environ.get("AKMS_MAX_TOKENS", args.max_tokens or DEFAULT_MAX_TOKENS)
    )
    client = LLMClient(model, max_tokens, api_key=api_key, api_base=api_base)
    print(
        f"LLM via LiteLLM: provider={provider} model={model}"
        + (f" api_base={api_base}" if api_base else "")
    )

    # ── NotebookLM grounding (optional; via the `nlm` CLI, not MCP) ──
    nlm_id = args.notebooklm_id
    nlm_timeout = args.nlm_timeout or DEFAULT_NLM_TIMEOUT
    if nlm_id:
        print(f"NotebookLM grounding enabled via `nlm` CLI: notebook={nlm_id}")

    # ── Track existing ids (grows as batches complete) ──
    existing_ids: set[str] = set(TIER1_IDS) | state.generated_ids
    # Add all ids from the inventory (so within-batch and cross-batch edges resolve)
    for _, nodes in categories:
        for n in nodes:
            existing_ids.add(n.id)

    # ── Run batches ──
    results: list[BatchResult] = []
    errors_total = 0

    for idx, cat, nodes in batches:
        if idx < resume_from:
            continue
        if idx in state.completed_batches:
            continue

        node_ids = [n.id for n in nodes]
        print(f"\n{'─' * 60}")
        print(f"Batch {idx}/{len(batches) - 1}: {cat}")
        print(f"  Nodes: {', '.join(node_ids)}")

        # Build prompt
        user_msg = build_user_message(cat, nodes, existing_ids)

        # Optionally ground the batch in NotebookLM source material (via `nlm` CLI)
        if nlm_id:
            try:
                ctx = fetch_nlm_context(nlm_id, nodes, nlm_timeout, args.nlm_profile)
                if ctx:
                    user_msg = (
                        "SOURCE CONTEXT FROM NOTEBOOKLM "
                        "(ground every node in this and cite it):\n"
                        + ctx
                        + "\n\n"
                        + user_msg
                    )
            except Exception as e:
                print(
                    f"  ⚠ NotebookLM grounding unavailable ({e}); generating without it"
                )

        # Call the selected LLM provider
        t0 = time.time()
        try:
            raw = client.complete(SYSTEM_PROMPT, user_msg)
        except Exception as e:
            duration = time.time() - t0
            print(f"  ✗ API error ({duration:.1f}s): {e}")
            state.failed_batches.append(idx)
            state.save(state_path)
            errors_total += 1
            # Rate limit backoff
            if "rate" in str(e).lower() or "429" in str(e):
                wait = 60
                print(f"  Rate limited. Waiting {wait}s...")
                time.sleep(wait)
            continue

        duration = time.time() - t0
        print(f"  API call: {duration:.1f}s")

        # Save raw response
        raw_path = raw_dir / f"batch_{idx:03d}_raw.txt"
        raw_path.write_text(raw, encoding="utf-8")

        # Split response into files
        files = split_batch_response(raw)
        batch_errors: list[str] = []

        if not files:
            batch_errors.append("No files extracted from response")
            print("  ✗ No files extracted!")
        else:
            print(f"  Extracted {len(files)} file(s)")

        # Validate and write each file
        for filename, content in files.items():
            errs = quick_validate(content)
            if errs:
                batch_errors.extend([f"{filename}: {e}" for e in errs])
                print(f"  ⚠ {filename}: {len(errs)} validation error(s)")
                for e in errs:
                    print(f"      {e}")

            # Write regardless (even with warnings — human reviews)
            out_path = output_dir / filename
            out_path.write_text(content + "\n", encoding="utf-8")

            # Extract id for state tracking
            fm_match = FRONTMATTER_RE.match(content)
            if fm_match:
                try:
                    fm = yaml.safe_load(fm_match.group(1))
                    if isinstance(fm, dict) and "id" in fm:
                        state.generated_ids.add(fm["id"])
                        existing_ids.add(fm["id"])
                except yaml.YAMLError:
                    pass

        result = BatchResult(
            batch_index=idx,
            category=cat,
            node_ids=node_ids,
            raw_response=raw,
            files=files,
            errors=batch_errors,
            duration_s=duration,
        )
        results.append(result)
        errors_total += len(batch_errors)

        # Update state
        state.completed_batches.append(idx)
        state.save(state_path)

        # Polite delay between API calls
        if idx < len(batches) - 1:
            time.sleep(2)

    # ── Final report ──
    print(f"\n{'═' * 60}")
    print("PIPELINE COMPLETE")
    print(f"{'═' * 60}")
    print(f"Batches run:      {len(results)}")
    print(f"Nodes generated:  {len(state.generated_ids)}")
    print(f"Failed batches:   {len(state.failed_batches)}")
    print(f"Validation errors: {errors_total}")
    print(f"Output directory:  {output_dir}")
    print(f"State file:        {state_path}")

    if state.failed_batches:
        print(f"\nFailed batches (re-run with --resume-from): {state.failed_batches}")

    # Write summary
    summary = {
        "total_batches": len(batches),
        "completed": len(state.completed_batches),
        "failed": state.failed_batches,
        "generated_ids": sorted(state.generated_ids),
        "provider": provider,
        "model": model,
        "batch_size": batch_size,
        "notebooklm": bool(nlm_id),
    }
    (output_dir / "_generation_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )

    return 1 if errors_total > 0 else 0


# ═══════════════════════════════════════════════════════════════════════════════
#                          CLI
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AKMS Node Generation Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--input",
        "-i",
        nargs="+",
        required=True,
        help="Path(s) to inventory JSON files or directories containing them",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="generated_nodes",
        help="Output directory for generated .md files (default: generated_nodes/)",
    )
    parser.add_argument(
        "--status",
        "-s",
        default=None,
        help="Comma-separated status filter (e.g., 'new' or 'new,exists-enrich'). Default: all",
    )
    parser.add_argument(
        "--batch-size",
        "-b",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Nodes per batch (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--provider",
        "-p",
        default=None,
        choices=sorted(PROVIDERS),
        help=f"LLM provider routed via LiteLLM (default: {DEFAULT_PROVIDER}, "
        "or AKMS_LLM_PROVIDER env). 'openai' = any OpenAI-compatible/local endpoint.",
    )
    parser.add_argument(
        "--model",
        "-m",
        default=None,
        help="Model id (default: provider-specific, or AKMS_MODEL env). "
        "A value containing '/' is passed to LiteLLM verbatim.",
    )
    parser.add_argument(
        "--api-base",
        default=None,
        help="Base URL for an OpenAI-compatible / local endpoint "
        "(or AKMS_LLM_API_BASE / OPENAI_API_BASE env)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help=f"Max tokens per response (default: {DEFAULT_MAX_TOKENS})",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show batch plan without calling API"
    )
    parser.add_argument(
        "--resume-from",
        type=int,
        default=None,
        help="Resume from a specific batch index",
    )
    parser.add_argument(
        "--notebooklm-id",
        default=None,
        help="NotebookLM notebook id; grounds generation in its sources via the `nlm` CLI",
    )
    parser.add_argument(
        "--nlm-profile",
        default=None,
        help="nlm auth profile to use for NotebookLM grounding",
    )
    parser.add_argument(
        "--nlm-timeout",
        type=float,
        default=None,
        help=f"Per-query timeout (s) for `nlm` grounding (default: {DEFAULT_NLM_TIMEOUT:g})",
    )

    args = parser.parse_args()
    return run_pipeline(args)


if __name__ == "__main__":
    sys.exit(main())
