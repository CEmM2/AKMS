"""generate_loadout.py — Loadout File Generator (§2.6 of system design).

Assembles the loadout .md file from subgraph query results.
All loadout artifact writes flow through this module (single-writer boundary).

Two modes:
  - routing: Node table with summaries + paths (~200 tok/node). Default.
  - full: Inline content with token budget enforcement.

Per-node reading_priority overrides mode selection:
  - full: include full content even in routing mode
  - summary: include summary only even in full mode
  - pitfalls-only: include only pitfall warnings

Loadout structure (fixed):
  1. Header (YAML frontmatter)
  2. Domain knowledge table + content
     (or Required / Coactivated / Domain sections when task knowledge is provided)
  3. Pitfall warnings (structural; independent of qmd availability)
  4. Session history
  5. Suggested reading order (from requires edges)

Optional :class:`~akms.task_context.query.TaskKnowledgeQueryResult` and
:class:`~akms.task_context.manifest.ResolutionManifest` inputs render required
knowledge first (uncapped), coactivated next, and advisory last under the
ordinary token budget. Omitting those arguments preserves legacy output.
"""

from __future__ import annotations

import logging
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import frontmatter
import networkx as nx
import yaml

from akms.schema.models import (
    AgentRole,
    ContextSize,
    EdgeType,
    LoadoutConfig,
    LoadoutMode,
    PropagationConfig,
    ReadingPriority,
)
from akms.graph.qmd_cache import get_cached, put_cached
from akms._resources import seed_qmd_path
from akms.graph.query_subgraph import compute_query_hash
from akms.telemetry import traced

if TYPE_CHECKING:
    from akms.task_context.manifest import ResolutionManifest
    from akms.task_context.query import TaskKnowledgeQueryResult

logger = logging.getLogger(__name__)

_CLASS_REQUIRED = "required"
_CLASS_COACTIVATED = "coactivated"
_CLASS_ADVISORY = "advisory"
_CLASS_ORDER = {
    _CLASS_REQUIRED: 0,
    _CLASS_COACTIVATED: 1,
    _CLASS_ADVISORY: 2,
}


def _retrieve_node_content_qmd(
    query: str,
    scoped_paths: list[str],
    repo_root: Path | None,
) -> list[dict]:
    """Retrieve content via the `seed/qmd/run_qmd.sh` wrapper.

    Returns a **deterministically sorted** list of ``{path, line, content}``
    dicts. Sorting is by ``(path, line)`` per FR-L13. Scoping to the caller's
    ranked-node paths is applied post-retrieval because the run_qmd.sh
    wrapper already scopes to the canonical directories (global vault +
    local-nodes + code-mirror).
    """
    if not scoped_paths:
        return []

    #   # Prefer the repo-local run_qmd.sh dispatcher so qmd binary detection,
    #       # collection naming, and grep fallback live in one place.
    #       #
    #       # Resolution is delegated to akms._resources, the single place that knows
    #       # where the wrapper lives. A hand-rolled candidate list here would be
    #       # relative to a source checkout and resolve nothing in an installed
    #       # wheel — qmd retrieval would be dead while appearing to return no hits.
    seed_qmd = seed_qmd_path(
        "run_qmd.sh",
        repo_root_candidates=(
            [repo_root / "Packages" / "AKMS", repo_root]
            if repo_root is not None
            else None
        ),
    )

    cmd = ["bash", str(seed_qmd), "search_nodes", query]
    logger.info(
        "qmd retrieval invoked: tool=run_qmd.sh query=%s scoped_paths=%s",
        query,
        ",".join(sorted(scoped_paths)),
    )
    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo_root) if repo_root else None,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except Exception as exc:
        logger.warning("run_qmd.sh unavailable at execution time: %s", exc)
        return []
    if result.returncode != 0:
        logger.warning(
            "run_qmd.sh failed (code=%s): %s",
            result.returncode,
            (result.stderr or "").strip(),
        )
        return []

    # Parse the wrapper output: it prints prose headers + qmd JSON lines OR
    # grep-style file paths. Handle both uniformly.
    scoped_set = set(scoped_paths)
    hits: list[dict] = []
    import json as _json

    for raw_line in (result.stdout or "").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("===") or stripped.startswith("("):
            continue
        # qmd JSON row
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                row = _json.loads(stripped)
                path = str(row.get("path", ""))
                if path and path in scoped_set:
                    hits.append(
                        {
                            "path": path,
                            "line": int(row.get("line", 0) or 0),
                            "content": str(
                                row.get("content") or row.get("snippet") or ""
                            ).strip(),
                        }
                    )
                continue
            except Exception:
                pass
        # Grep-style file path (no explicit content; read the file body).
        if "/" in stripped and "." in stripped and stripped in scoped_set:
            # The wrapper emits paths relative to the repo root; resolve them
            # against `repo_root` so the read is not cwd-dependent.
            full_path = Path(stripped)
            if repo_root is not None and not full_path.is_absolute():
                full_path = repo_root / full_path
            try:
                body = full_path.read_text(encoding="utf-8").strip()
            except Exception:
                body = ""
            hits.append({"path": stripped, "line": 0, "content": body})

    # FR-L13: sort deterministically by (path, line).
    hits.sort(key=lambda h: (h["path"], h["line"]))
    return hits


def _estimate_content_tokens(content: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(1, len(content) // 4)


def _get_context_size_tokens(
    context_size: str | ContextSize | None,
    config: LoadoutConfig,
) -> int:
    """Get the token allocation for a context_size hint."""
    if context_size is None:
        return config.context_size_tokens.medium  # default

    if isinstance(context_size, ContextSize):
        context_size = context_size.value

    tokens = config.context_size_tokens
    mapping = {
        "small": tokens.small,
        "medium": tokens.medium,
        "large": tokens.large,
    }
    return mapping.get(str(context_size), tokens.medium)


def _load_node_content(content_ref: str | None, repo_root: Path | None = None) -> str:
    """Load the markdown content of a node from its content_ref path.

    Returns empty string if unavailable.
    """
    if not content_ref:
        return ""

    # Try the path as-is first, then relative to repo_root
    candidates = [Path(content_ref)]
    if repo_root:
        candidates.append(repo_root / content_ref)

    for path in candidates:
        if path.exists():
            try:
                post = frontmatter.load(str(path))
                return post.content.strip()
            except Exception:
                try:
                    return path.read_text().strip()
                except Exception:
                    pass

    return ""


def _extract_summary(content: str, max_sentences: int = 5) -> str:
    """Extract a brief summary from content (first N sentences).

    Used in routing mode for the ~200 token/node summaries.
    """
    if not content:
        return "(no content available)"

    # Look for a ## Summary section first
    lines = content.split("\n")
    in_summary = False
    summary_lines = []

    for line in lines:
        if line.strip().lower().startswith("## summary"):
            in_summary = True
            continue
        if in_summary:
            if line.startswith("## "):
                break
            if line.strip():
                summary_lines.append(line.strip())

    if summary_lines:
        return " ".join(summary_lines[:max_sentences])

    # Fallback: first non-heading, non-empty lines
    text_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("---"):
            continue
        text_lines.append(stripped)
        if len(text_lines) >= max_sentences:
            break

    if text_lines:
        return " ".join(text_lines)

    return "(content available at path)"


def _extract_pitfall_sections(content: str) -> str:
    """Extract pitfall/warning sections from node content."""
    if not content:
        return ""

    lines = content.split("\n")
    pitfall_lines = []
    in_pitfall = False

    for line in lines:
        lower = line.strip().lower()
        # Match common pitfall section headers
        if any(
            kw in lower
            for kw in [
                "## pitfall",
                "## warning",
                "## gotcha",
                "## caution",
                "### pitfall",
            ]
        ):
            in_pitfall = True
            pitfall_lines.append(line)
            continue
        if in_pitfall:
            if line.startswith("## ") and "pitfall" not in line.lower():
                in_pitfall = False
                continue
            pitfall_lines.append(line)

    return "\n".join(pitfall_lines).strip()


def _build_reading_order(
    G: nx.DiGraph,
    node_ids: list[str],
) -> list[str]:
    """Derive suggested reading order from requires edge topology.

    Nodes that are required by others should be read first.
    Uses topological sort on the requires-subgraph.
    """
    # Build a sub-DAG with only requires edges among our nodes
    node_set = set(node_ids)
    sub = nx.DiGraph()
    sub.add_nodes_from(node_ids)

    for u, v, data in G.edges(data=True):
        edge_type = data.get("type", "")
        if isinstance(edge_type, EdgeType):
            edge_type = edge_type.value
        if str(edge_type) == EdgeType.REQUIRES.value:
            if u in node_set and v in node_set:
                # u requires v → v should be read before u
                sub.add_edge(v, u)

    try:
        order = list(nx.topological_sort(sub))
    except nx.NetworkXUnfeasible:
        # Cycle in requires graph — fall back to input order
        logger.warning("Cycle in requires subgraph, using input order")
        order = node_ids

    return order


def _normalize_selection_class(raw: Any) -> str | None:
    """Return a canonical selection-class string, or None when absent."""
    if raw is None:
        return None
    value = getattr(raw, "value", raw)
    text = str(value).strip().lower()
    if text in _CLASS_ORDER:
        return text
    return None


def _ranked_nodes_from_task_knowledge(
    task_knowledge: TaskKnowledgeQueryResult,
    ranked_nodes: list[tuple[str, dict[str, Any]]],
) -> list[tuple[str, dict[str, Any]]]:
    """Materialize ordered (node_id, data) pairs from a task-knowledge result.

    Existing ranked-node data is merged when present so content_ref and similar
    fields survive even if the selection carried a thinner node_data payload.
    """
    existing = {nid: dict(data) for nid, data in ranked_nodes}
    materialised: list[tuple[str, dict[str, Any]]] = []
    for selection in task_knowledge.selections:
        node_data = dict(existing.get(selection.node_id, {}))
        node_data.update(dict(selection.node_data))
        node_data["_selection_class"] = selection.selection_class.value
        node_data["_reasons"] = tuple(selection.reasons)
        if selection.selection_class.value == _CLASS_COACTIVATED:
            node_data["_coactivated"] = True
        materialised.append((selection.node_id, node_data))
    return materialised


def _sort_ranked_nodes(
    ranked_nodes: list[tuple[str, dict[str, Any]]],
    *,
    required_aware: bool,
) -> list[tuple[str, dict[str, Any]]]:
    """Stable deterministic ordering for rendering.

    Legacy mode sorts by node id. Required-aware mode preserves the
    required → coactivated → advisory class order, then node id within class.
    """
    if not required_aware:
        return sorted(
            ranked_nodes,
            key=lambda pair: (pair[0], str(pair[1].get("content_ref", ""))),
        )
    return sorted(
        ranked_nodes,
        key=lambda pair: (
            _CLASS_ORDER.get(
                _normalize_selection_class(pair[1].get("_selection_class"))
                or _CLASS_ADVISORY,
                99,
            ),
            pair[0],
            str(pair[1].get("content_ref", "")),
        ),
    )


def _render_node_detail(entry: dict[str, Any], parts: list[str]) -> None:
    """Append one node detail block to the markdown parts list."""
    parts.append(f"### `{entry['id']}` — {entry.get('title', '')}")
    parts.append("")

    if entry.get("selection_class"):
        parts.append(f"**Selection class:** {entry['selection_class']}")
        parts.append("")

    reasons = entry.get("reasons") or ()
    if reasons:
        parts.append("**Reasons:**")
        for reason in reasons:
            parts.append(f"- {reason}")
        parts.append("")

    if "content_ref" in entry:
        parts.append(f"**Path:** `{entry['content_ref']}`")
        parts.append("")

    if "content" in entry:
        parts.append(entry["content"])
        parts.append("")
    elif "summary" in entry:
        parts.append(f"**Summary:** {entry['summary']}")
        parts.append("")


def _render_knowledge_section(
    title: str,
    entries: list[dict[str, Any]],
    parts: list[str],
    *,
    include_class_column: bool,
) -> None:
    """Render a knowledge table plus detail blocks for one selection class."""
    if not entries:
        return
    parts.append(f"## {title}")
    parts.append("")
    if include_class_column:
        parts.append("| # | Node | Class | Domain | Confidence | Origin | Read Mode |")
        parts.append("|---|------|-------|--------|------------|--------|-----------|")
        for i, entry in enumerate(entries, 1):
            parts.append(
                f"| {i} | `{entry['id']}` | {entry.get('selection_class', '')} | "
                f"{entry['domain']} | {entry['confidence']:.2f} | "
                f"{entry['origin']} | {entry['reading_priority']} |"
            )
    else:
        parts.append("| # | Node | Domain | Confidence | Origin | Read Mode |")
        parts.append("|---|------|--------|------------|--------|-----------|")
        for i, entry in enumerate(entries, 1):
            parts.append(
                f"| {i} | `{entry['id']}` | {entry['domain']} | "
                f"{entry['confidence']:.2f} | {entry['origin']} | "
                f"{entry['reading_priority']} |"
            )
    parts.append("")
    for entry in entries:
        _render_node_detail(entry, parts)


@traced("akms.generate_loadout")
def generate_loadout(
    G: nx.DiGraph,
    ranked_nodes: list[tuple[str, dict[str, Any]]],
    task_id: str,
    phase: int,
    graph_version: str,
    seed_tags: list[str],
    agent_role: AgentRole | str,
    mode: LoadoutMode | str = LoadoutMode.ROUTING,
    available_context: int = 0,
    config: PropagationConfig | None = None,
    output_dir: str | Path | None = None,
    output_path: str | Path | None = None,
    repo_root: str | Path | None = None,
    task_knowledge: TaskKnowledgeQueryResult | None = None,
    resolution_manifest: ResolutionManifest | None = None,
) -> str:
    """Generate a loadout markdown file from ranked subgraph nodes.

    Args:
        G: The compiled knowledge graph.
        ranked_nodes: Output of query_subgraph (node_id, node_data) pairs.
            When ``task_knowledge`` is supplied, selection order and reasons
            take precedence; ranked node data is still merged for content refs.
        task_id: Task identifier.
        phase: Phase number.
        graph_version: SHA256 of graph.json.
        seed_tags: Tags used for the query.
        agent_role: Agent role.
        mode: Loadout mode (routing or full).
        available_context: Estimated available tokens used for mode selection.
        config: PropagationConfig (defaults if None).
        output_dir: Directory where canonical loadout filename is written.
        output_path: Exact loadout file path to write. Mutually exclusive with output_dir.
        repo_root: Repository root for resolving content_ref paths.
        task_knowledge: Optional exact task-knowledge query result. When set,
            required / coactivated / advisory nodes render as distinct sections
            with reasons, and required content is never truncated by the token
            budget. When omitted, legacy output is preserved.
        resolution_manifest: Optional resolution manifest. When set, its
            fingerprint is recorded in the loadout header for audit linkage.

    Returns:
        The loadout markdown content string.
        If output_path or output_dir is provided, also writes the file.
    """
    if config is None:
        config = PropagationConfig()
    if output_dir is not None and output_path is not None:
        raise ValueError("output_dir and output_path are mutually exclusive")

    # Local import keeps the hot path free of task_context when unused and
    # avoids any import-cycle risk at module load.
    if task_knowledge is not None:
        from akms.task_context.query import TaskKnowledgeQueryResult as _TKQR

        if not isinstance(task_knowledge, _TKQR):
            raise TypeError("task_knowledge must be TaskKnowledgeQueryResult")
    if resolution_manifest is not None:
        from akms.task_context.manifest import ResolutionManifest as _RM

        if not isinstance(resolution_manifest, _RM):
            raise TypeError("resolution_manifest must be ResolutionManifest")

    loadout_config = config.loadout
    role_str = (
        agent_role.value if isinstance(agent_role, AgentRole) else str(agent_role)
    )
    mode_str = mode.value if isinstance(mode, LoadoutMode) else str(mode)
    qmd_available = shutil.which("qmd") is not None
    repo_path = Path(repo_root) if repo_root else None
    required_aware = task_knowledge is not None

    now = datetime.now().isoformat(timespec="seconds")

    # Materialise required-aware ranked nodes before header/counts.
    if task_knowledge is not None:
        ranked_nodes = _ranked_nodes_from_task_knowledge(task_knowledge, ranked_nodes)

    # Deterministic insertion order (class-aware when required knowledge present).
    ranked_nodes = _sort_ranked_nodes(ranked_nodes, required_aware=required_aware)

    # ── Section 1: Header ────────────────────────────────────────────
    header: dict[str, Any] = {
        "task_id": task_id,
        "phase": phase,
        "generated_at": now,
        "graph_version": graph_version,
        "seed_tags": seed_tags,
        "agent_role": role_str,
        "node_count": len(ranked_nodes),
        "loadout_mode": mode_str,
        "available_context": int(available_context),
        "qmd_available": qmd_available,
        "akms_schema": "v2",
    }

    # FR-G10: surface co-activated nodes (promoted via load_with hints) in the
    # header so consumers can distinguish them from seed-anchored nodes. Only
    # emitted when present, to keep loadouts byte-identical when unused.
    coactivated_ids = sorted(
        nid for nid, node_data in ranked_nodes if node_data.get("_coactivated")
    )
    if coactivated_ids:
        header["coactivated_nodes"] = coactivated_ids

    if required_aware:
        required_ids = [
            nid
            for nid, data in ranked_nodes
            if _normalize_selection_class(data.get("_selection_class"))
            == _CLASS_REQUIRED
        ]
        advisory_ids = [
            nid
            for nid, data in ranked_nodes
            if _normalize_selection_class(data.get("_selection_class"))
            == _CLASS_ADVISORY
        ]
        header["required_node_count"] = len(required_ids)
        header["coactivated_node_count"] = len(coactivated_ids)
        header["advisory_node_count"] = len(advisory_ids)
        header["required_nodes"] = required_ids
        # Coactivated already emitted via FR-G10 when non-empty.

    if resolution_manifest is not None:
        header["resolution_fingerprint"] = resolution_manifest.fingerprint

    # ── Section 2: Domain Knowledge ──────────────────────────────────
    scoped_paths = sorted(
        {
            str(node_data.get("content_ref"))
            for _, node_data in ranked_nodes
            if node_data.get("content_ref")
        },
    )
    # qmd retrieval returns list[{path, line, content}] sorted by
    # (path, line). Legacy caches (dict-shaped) are transparently
    # invalidated rather than migrated.
    #
    # We always attempt retrieval: `_retrieve_node_content_qmd` shells out
    # to `seed/qmd/run_qmd.sh`, which transparently falls back to grep when
    # the `qmd` binary is missing. Gating on `qmd_available` would make the
    # fallback unreachable.
    qmd_content_by_path: dict[str, str] = {}
    if scoped_paths:
        query = " ".join(sorted(set(t.strip() for t in seed_tags if t and t.strip())))
        query_hash = compute_query_hash(seed_tags, role_str, max_depth=0)
        cached = get_cached(repo_path, graph_version, query_hash) if repo_path else None
        hits_list: list[dict] = []
        if (
            isinstance(cached, list)
            and cached
            and isinstance(cached[0], dict)
            and "line" in cached[0]
        ):
            # New cache shape — preserve line info.
            hits_list = [
                {
                    "path": str(item.get("path", "")),
                    "line": int(item.get("line", 0) or 0),
                    "content": str(item.get("content", "")),
                }
                for item in cached
                if isinstance(item, dict) and item.get("path")
            ]
        else:
            if isinstance(cached, list):
                logger.info(
                    "qmd cache shape outdated — re-retrieving and upgrading to (path,line) entries"
                )
            hits_list = _retrieve_node_content_qmd(query, scoped_paths, repo_path)
            if repo_path and hits_list:
                # FR-L13: hits are already sorted by (path, line) inside
                # `_retrieve_node_content_qmd`; write directly to cache.
                put_cached(repo_path, graph_version, query_hash, hits_list)

        # Collapse to {path: content} for downstream rendering; first hit wins
        # when a path appears twice (deterministic because list is sorted).
        for item in hits_list:
            path = item["path"]
            if path and path not in qmd_content_by_path and item.get("content"):
                qmd_content_by_path[path] = item["content"]

    node_entries: list[dict[str, Any]] = []
    total_tokens = 0
    max_tokens = loadout_config.max_loadout_tokens

    for node_id, node_data in ranked_nodes:
        selection_class = _normalize_selection_class(node_data.get("_selection_class"))
        uncapped = required_aware and selection_class in {
            _CLASS_REQUIRED,
            _CLASS_COACTIVATED,
        }

        entry: dict[str, Any] = {
            "id": node_id,
            "origin": node_data.get("node_origin", "unknown"),
            "confidence": node_data.get("confidence", 0.0),
            "domain": node_data.get("domain", ""),
            "title": node_data.get("title", node_id),
        }
        if selection_class is not None:
            entry["selection_class"] = selection_class
        reasons = node_data.get("_reasons") or ()
        if reasons:
            entry["reasons"] = tuple(reasons)

        content_ref = node_data.get("content_ref")
        reading_priority = node_data.get("reading_priority")

        # Determine effective read mode for this node
        if reading_priority:
            if isinstance(reading_priority, ReadingPriority):
                reading_priority = reading_priority.value
            entry["reading_priority"] = str(reading_priority)
        else:
            entry["reading_priority"] = mode_str

        # Load content based on mode and reading_priority
        content = ""
        if content_ref:
            entry["content_ref"] = str(content_ref)
            content = qmd_content_by_path.get(str(content_ref), "")
            if not content:
                content = _load_node_content(content_ref, repo_path)

        # Resolve effective_mode once per node so per-node
        # reading_priority wins over the loadout-level mode_str per FR-L10c.
        # Precedence: reading_priority (if set) > mode_str.
        effective_mode = (reading_priority or mode_str) or "routing"

        if effective_mode == "pitfalls-only":
            pitfall_content = _extract_pitfall_sections(content)
            entry["content"] = (
                pitfall_content if pitfall_content else "(no pitfall sections found)"
            )
            total_tokens += _estimate_content_tokens(entry["content"])
        elif effective_mode == "full":
            # Full content. Required / coactivated content is uncapped so
            # ordinary advisory budgets cannot hide mandatory constraints.
            if content:
                tokens = _estimate_content_tokens(content)
                if uncapped or total_tokens + tokens <= max_tokens:
                    entry["content"] = content
                    total_tokens += tokens
                else:
                    # Truncate advisory content only.
                    remaining = max(0, max_tokens - total_tokens)
                    char_budget = remaining * 4  # reverse of token estimate
                    entry["content"] = (
                        content[:char_budget]
                        + "\n\n[... truncated to fit token budget]"
                    )
                    total_tokens = max_tokens
            else:
                entry["content"] = "(content not available — read from path)"
        else:
            # Routing / summary mode: summary + path. Required summaries are
            # always included (they are small); budget still tracks totals.
            summary = _extract_summary(content)
            entry["summary"] = summary
            total_tokens += loadout_config.routing_tokens_per_node

        node_entries.append(entry)

    # ── Section 3: Pitfall Warnings ──────────────────────────────────
    pitfall_warnings = []
    node_id_set = {nid for nid, _ in ranked_nodes}

    for u, v, data in G.edges(data=True):
        edge_type = data.get("type", "")
        if isinstance(edge_type, EdgeType):
            edge_type = edge_type.value
        if str(edge_type) == EdgeType.PITFALL.value:
            if u in node_id_set or v in node_id_set:
                warning = {
                    "from": u,
                    "to": v,
                    "note": data.get("note", ""),
                    "weight": data.get("weight", 0.5),
                }
                pitfall_warnings.append(warning)

    # Deterministic pitfall order for stable loadouts.
    pitfall_warnings.sort(key=lambda pw: (pw["from"], pw["to"], pw["note"]))

    # ── Section 4: Session History ───────────────────────────────────
    session_refs = []
    for node_id, node_data in ranked_nodes:
        refs = node_data.get("session_refs", [])
        if refs:
            for ref in refs:
                session_refs.append(
                    {
                        "node_id": node_id,
                        "session_ref": ref,
                    }
                )

    # ── Section 5: Reading Order ─────────────────────────────────────
    node_ids_ordered = [nid for nid, _ in ranked_nodes]
    reading_order = _build_reading_order(G, node_ids_ordered)

    # ── Assemble Markdown ────────────────────────────────────────────
    parts: list[str] = []

    # Header as YAML frontmatter
    parts.append("---")
    parts.append(yaml.dump(header, default_flow_style=False, sort_keys=True).strip())
    parts.append("---")
    parts.append("")

    # Title
    parts.append(f"# Loadout: {task_id}")
    parts.append("")

    if required_aware:
        required_entries = [
            e for e in node_entries if e.get("selection_class") == _CLASS_REQUIRED
        ]
        coactivated_entries = [
            e for e in node_entries if e.get("selection_class") == _CLASS_COACTIVATED
        ]
        advisory_entries = [
            e for e in node_entries if e.get("selection_class") == _CLASS_ADVISORY
        ]
        # Required first (uncapped), then coactivated, then advisory/domain.
        _render_knowledge_section(
            "Required Knowledge",
            required_entries,
            parts,
            include_class_column=True,
        )
        _render_knowledge_section(
            "Coactivated Knowledge",
            coactivated_entries,
            parts,
            include_class_column=True,
        )
        _render_knowledge_section(
            "Domain Knowledge",
            advisory_entries,
            parts,
            include_class_column=True,
        )
        # When every selection class is empty, still emit Domain Knowledge so
        # consumers always have a stable section header.
        if not required_entries and not coactivated_entries and not advisory_entries:
            parts.append("## Domain Knowledge")
            parts.append("")
            parts.append("| # | Node | Domain | Confidence | Origin | Read Mode |")
            parts.append("|---|------|--------|------------|--------|-----------|")
            parts.append("")
    else:
        # Legacy single Domain Knowledge section (byte-compatible layout).
        parts.append("## Domain Knowledge")
        parts.append("")
        parts.append("| # | Node | Domain | Confidence | Origin | Read Mode |")
        parts.append("|---|------|--------|------------|--------|-----------|")

        for i, entry in enumerate(node_entries, 1):
            parts.append(
                f"| {i} | `{entry['id']}` | {entry['domain']} | "
                f"{entry['confidence']:.2f} | {entry['origin']} | "
                f"{entry['reading_priority']} |"
            )

        parts.append("")

        for entry in node_entries:
            parts.append(f"### `{entry['id']}` — {entry.get('title', '')}")
            parts.append("")

            if "content_ref" in entry:
                parts.append(f"**Path:** `{entry['content_ref']}`")
                parts.append("")

            if "content" in entry:
                parts.append(entry["content"])
                parts.append("")
            elif "summary" in entry:
                parts.append(f"**Summary:** {entry['summary']}")
                parts.append("")

    # Pitfall Warnings — structural graph edges. Always rendered so required
    # constraints are not hidden when the qmd binary is absent.
    if pitfall_warnings:
        parts.append("## Pitfall Warnings")
        parts.append("")
        for pw in pitfall_warnings:
            note = pw["note"] if pw["note"] else "(no description)"
            parts.append(f"- **{pw['from']}** → **{pw['to']}**: {note}")
        parts.append("")

    # Session History (still gated: session refs are qmd-oriented enrichment)
    if qmd_available and session_refs:
        parts.append("## Session History")
        parts.append("")
        for sr in session_refs:
            parts.append(f"- Node `{sr['node_id']}`: see `{sr['session_ref']}`")
        parts.append("")

    # Reading Order — always emit when required-aware so reviewers get order
    # even without qmd; legacy path keeps the historical qmd gate.
    if qmd_available or required_aware:
        parts.append("## Suggested Reading Order")
        parts.append("")
        for i, nid in enumerate(reading_order, 1):
            parts.append(f"{i}. `{nid}`")
        parts.append("")

    content = "\n".join(parts)

    # Write file through this single writer when output pathing is requested.
    file_path: Path | None = None
    if output_path is not None:
        file_path = Path(output_path)
    elif output_dir is not None:
        out_path = Path(output_dir)
        filename = f"{phase}-{task_id}-loadout.md"
        file_path = out_path / filename

    if file_path is not None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content)

        logger.info(
            "Loadout written: %s (%d nodes, %s mode, ~%d tokens)",
            file_path,
            len(ranked_nodes),
            mode_str,
            total_tokens,
        )

    return content


def select_loadout_mode(
    ranked_nodes: list[tuple[str, dict[str, Any]]],
    available_context: int,
    config: PropagationConfig | None = None,
) -> LoadoutMode:
    """Select loadout mode based on available context and node cost.

    Implements the mode selection logic from §2.1:
      if available < low_threshold: routing
      elif full_cost > available * budget_fraction: routing
      else: full

    Args:
        ranked_nodes: The ranked subgraph nodes.
        available_context: Estimated available tokens after system/task prompts.
        config: PropagationConfig (defaults if None).

    Returns:
        LoadoutMode.ROUTING or LoadoutMode.FULL.
    """
    if config is None:
        config = PropagationConfig()

    mode_config = config.loadout.mode_selection
    loadout_config = config.loadout

    if available_context < mode_config.low_threshold:
        return LoadoutMode.ROUTING

    # Estimate full cost
    full_cost = 0
    for _node_id, node_data in ranked_nodes:
        context_size = node_data.get("context_size")
        full_cost += _get_context_size_tokens(context_size, loadout_config)

    if full_cost > available_context * mode_config.budget_fraction:
        return LoadoutMode.ROUTING

    return LoadoutMode.FULL
