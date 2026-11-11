"""generate_loadout.py — Loadout File Generator (§2.6 of system design).

Assembles the loadout .md file from subgraph query results.
All loadout artifact writes flow through this module (single-writer boundary).

Two modes:
  - routing: Node table with summaries + paths (~200 tok/node). Default.
  - full: Inline content with token budget enforcement.

Per-node reading_priority overrides mode selection:
  - full: include full content even in routing mode
  - summary: include summary only even in full mode (full when the node
    has no ``## Summary`` section)
  - pitfalls-only: include only pitfall warnings
Coactivated (load_with) nodes use ``loadout.coactivated_reading_priority``
(default summary) instead of their own reading_priority.

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

Code mirrors are whole source files, so a full-mode loadout that inlines them
is bounded by ``loadout.full_mode_max_tokens``: past it, the remaining mirrors
are served as summary and path, and the loadout names them.
"""

from __future__ import annotations

import logging
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

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
from akms.graph.record_projections import guard_projection_content
from akms._resources import seed_qmd_path
from akms.layout import local_knowledge_dir
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
_UNCAPPED_CLASSES = frozenset({_CLASS_REQUIRED, _CLASS_COACTIVATED})
_ORIGIN_CODE_MIRROR = "code-mirror"


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

    # The repository's copy wins over one the working directory happens to hold.
    candidates = [Path(content_ref)]
    if repo_root:
        candidates.insert(0, repo_root / content_ref)

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


def _has_summary_section(content: str) -> bool:
    """Return whether *content* has a non-empty ``## Summary`` section."""
    in_summary = False
    for line in content.split("\n"):
        if line.strip().lower().startswith("## summary"):
            in_summary = True
            continue
        if in_summary:
            if line.startswith("## "):
                return False
            if line.strip():
                return True
    return False


def _mirror_summary_source(node_data: dict[str, Any], repo_root: Path | None) -> str:
    """Return a code mirror's body when it was exported with a ``## Summary``.

    A mirror's ``content_ref`` is relative to the knowledge directory, so
    ``_load_node_content`` does not find it from the repository root. Routing
    mode reads it from there, and only the section ahead of the symbol index
    counts: the source text further down may hold such a line too. A mirror
    without the section yields "" and renders as it did before the section
    existed.
    """
    if repo_root is None or node_data.get("node_origin") != "code-mirror":
        return ""
    content = _load_node_content(
        node_data.get("content_ref"), local_knowledge_dir(repo_root)
    )
    head = content.split("\n## Symbol Index", 1)[0]
    return content if _has_summary_section(head) else ""


def _local_node_files(repo_root: Path | None) -> dict[str, list[Path]]:
    """Node files under ``<knowledge>/local-nodes/`` by file stem, nearest first.

    A file reached through a link that leaves the directory is left out, and so
    is anything under a ``content`` directory, which holds bodies, not nodes.
    """
    if repo_root is None:
        return {}
    directory = local_knowledge_dir(repo_root) / "local-nodes"
    if not directory.is_dir():
        return {}
    root = directory.resolve()
    files: dict[str, list[Path]] = {}
    for path in sorted(directory.rglob("*.md"), key=lambda p: (len(p.parts), p)):
        if "content" in path.relative_to(directory).parts[:-1]:
            continue
        if path.is_file() and path.resolve().is_relative_to(root):
            files.setdefault(path.stem, []).append(path)
    return files


def _local_node_ref(
    node_id: str,
    node_data: dict[str, Any],
    repo_root: Path | None,
    local_files: dict[str, list[Path]],
) -> str | None:
    """Repo-relative path of a local node written without ``content_ref``.

    Promotion writes ``<knowledge>/local-nodes/<id>.md`` and leaves
    ``content_ref`` empty. The graph then has the title and no body. The
    loadout reads that file, and an explicit ``content_ref`` is left alone.

    Only a project-local node has such a file: a global node of the same ID
    wins the collision at build time and must not take the local file's text.
    A file that names another node in its frontmatter is not this node's.
    """
    if repo_root is None or node_data.get("node_origin", "local") != "local":
        return None
    for candidate in local_files.get(node_id, ()):
        try:
            named = frontmatter.load(str(candidate)).metadata.get("id", node_id)
        except (OSError, ValueError, yaml.YAMLError):
            # Unreadable frontmatter cannot name another node; the caller
            # withholds a managed node it cannot parse.
            named = node_id
        if named != node_id:
            continue
        try:
            return candidate.relative_to(repo_root).as_posix()
        except ValueError:
            continue
    return None


def _knowledge_dir_mirror(
    node_data: dict[str, Any], repo_root: Path | None
) -> Path | None:
    """Return a code mirror's file when only the knowledge directory holds it.

    None for other nodes, and for a mirror whose ``content_ref`` resolves as
    given or from the repository root, which load as they always have.
    """
    content_ref = node_data.get("content_ref")
    if (
        repo_root is None
        or not content_ref
        or node_data.get("node_origin") != _ORIGIN_CODE_MIRROR
    ):
        return None
    if Path(content_ref).exists() or (repo_root / content_ref).exists():
        return None
    path = local_knowledge_dir(repo_root) / content_ref
    return path if path.is_file() else None


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


def _node_reading_priority(
    node_data: dict[str, Any],
    selection_class: str | None,
    loadout_config: LoadoutConfig,
) -> str | None:
    """Return a node's reading priority; coactivated nodes take the loadout's."""
    reading_priority = node_data.get("reading_priority")
    if isinstance(reading_priority, ReadingPriority):
        reading_priority = reading_priority.value
    coactivated = (
        selection_class == _CLASS_COACTIVATED
        if selection_class is not None
        else bool(node_data.get("_coactivated"))
    )
    if coactivated:
        # Coactivated nodes take the loadout's coactivated priority.
        reading_priority = loadout_config.coactivated_reading_priority.value
    return reading_priority


def _effective_read_mode(
    reading_priority: str | None,
    mode_str: str,
    content: str,
) -> str:
    """Resolve how one node renders; per-node priority wins over the mode (FR-L10c)."""
    effective_mode = (reading_priority or mode_str) or "routing"
    # FR-L10c: a summary-priority node without a `## Summary` section
    # falls back to full; its first lines are not a summary.
    if reading_priority == "summary" and content and not _has_summary_section(content):
        effective_mode = "full"
    return effective_mode


def _full_mode_downgrades(
    ranked_nodes: list[tuple[str, dict[str, Any]]],
    mode_str: str,
    loadout_config: LoadoutConfig,
    body_of: Callable[[Any], str],
) -> tuple[dict[str, int], int]:
    """Pick the code mirrors a full-mode loadout serves as summary and path.

    Only required and coactivated content is uncapped, so only it can balloon.
    Everything except code mirrors is charged first and stays inline: a mirror
    can be re-read from its path, a required constraint must not be hidden.
    Mirrors then take what is left in ranked order, class then node id; the
    first one that does not fit is downgraded and so is every mirror after it.

    Returns ``({node_id: full_tokens}, inline_tokens_without_the_guard)``. The
    mapping is empty for every loadout within the budget, so those stay
    byte-identical.
    """
    budget = loadout_config.full_mode_max_tokens
    if budget is None or mode_str != LoadoutMode.FULL.value:
        return {}, 0

    fixed_tokens = 0
    mirrors: list[tuple[str, int]] = []
    for node_id, node_data in ranked_nodes:
        selection_class = _normalize_selection_class(node_data.get("_selection_class"))
        if selection_class not in _UNCAPPED_CLASSES:
            continue
        content = body_of(node_data.get("content_ref"))
        reading_priority = _node_reading_priority(
            node_data, selection_class, loadout_config
        )
        if not content or (
            _effective_read_mode(reading_priority, mode_str, content) != "full"
        ):
            continue
        tokens = _estimate_content_tokens(content)
        if node_data.get("node_origin") == _ORIGIN_CODE_MIRROR:
            mirrors.append((node_id, tokens))
        else:
            fixed_tokens += tokens

    inline_tokens = fixed_tokens + sum(tokens for _, tokens in mirrors)
    if inline_tokens <= budget:
        return {}, inline_tokens

    downgraded: dict[str, int] = {}
    spent = fixed_tokens
    for node_id, tokens in mirrors:
        if not downgraded and spent + tokens <= budget:
            spent += tokens
        else:
            downgraded[node_id] = tokens
    return downgraded, inline_tokens


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

    if "full_mode_downgrade_tokens" in entry:
        parts.append(
            "**Downgraded:** over `loadout.full_mode_max_tokens`, so this mirror "
            f"(~{entry['full_mode_downgrade_tokens']} tokens in full) is summary "
            "and path only. Read the path for its full content."
        )
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
            budget. In full mode, ``loadout.full_mode_max_tokens`` bounds inline
            content by serving code mirrors as summary and path past it. When
            omitted, legacy output is preserved.
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

    # Disk is authoritative for managed projections: caches may predate a
    # record amendment, retraction, erasure, or a manual edit to its block.
    local_files = _local_node_files(repo_path)
    projection_bodies: dict[str, str] = {}
    projection_refs: dict[str, str] = {}
    projection_titles: dict[str, str] = {}
    blocked_projections: set[str] = set()
    for node_id, node_data in ranked_nodes:
        # The managed block lives in the node file, even when content_ref
        # points at a separate authored document. Do not test the latter for
        # markers known to exist only in the former.
        local_ref = node_data.get("_record_projection_ref") or _local_node_ref(
            node_id, node_data, repo_path, local_files
        )
        ref = local_ref or node_data.get("content_ref")
        if not ref:
            if node_data.get("_record_projection"):
                blocked_projections.add(node_id)
            continue
        disk_ref = repo_path / str(ref) if repo_path is not None else Path(ref)
        disk_body = _load_node_content(str(disk_ref))
        guard = guard_projection_content(disk_body, repo_path)
        if (
            not guard.managed
            and not node_data.get("_record_projection")
            and node_data.get("content_ref")
        ):
            ref = node_data["content_ref"]
            disk_ref = repo_path / str(ref) if repo_path is not None else Path(ref)
            guard = guard_projection_content(
                _load_node_content(str(disk_ref)), repo_path
            )
        if guard.managed or node_data.get("_record_projection"):
            projection_refs[node_id] = str(ref)
            content = guard.content
            if not guard.current or not guard.managed:
                blocked_projections.add(node_id)
            else:
                try:
                    disk_post = frontmatter.load(str(disk_ref))
                    projection_titles[node_id] = str(
                        disk_post.metadata.get("title", node_id)
                    )
                except (OSError, KeyError, ValueError, yaml.YAMLError):
                    blocked_projections.add(node_id)
                external_ref = node_data.get("content_ref")
                if external_ref and str(external_ref) != str(ref):
                    external_path = (
                        repo_path / str(external_ref)
                        if repo_path
                        else Path(external_ref)
                    )
                    if external_path.resolve() != disk_ref.resolve():
                        external = guard_projection_content(
                            _load_node_content(str(external_path)), repo_path
                        )
                        if not external.current:
                            blocked_projections.add(node_id)
                        content = external.content + "\n\n" + content
            projection_bodies[str(ref)] = content

    # ── Section 2: Domain Knowledge ──────────────────────────────────
    scoped_paths = sorted(
        {
            str(node_data.get("content_ref"))
            for _, node_data in ranked_nodes
            if node_data.get("content_ref")
            and str(node_data["content_ref"]) not in projection_bodies
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

    mirror_files: dict[str, Path] = {}
    for _node_id, node_data in ranked_nodes:
        mirror_file = _knowledge_dir_mirror(node_data, repo_path)
        if mirror_file is not None:
            mirror_files[str(node_data["content_ref"])] = mirror_file

    node_bodies: dict[str, str] = {}

    def body_of(content_ref: Any) -> str:
        """Return a node's body, from qmd when it had a hit, else its file."""
        if not content_ref:
            return ""
        ref = str(content_ref)
        if ref in projection_bodies:
            return projection_bodies[ref]
        if ref not in node_bodies:
            body = qmd_content_by_path.get(ref, "") or _load_node_content(
                content_ref, repo_path
            )
            if not body and ref in mirror_files and mode_str == LoadoutMode.FULL.value:
                # Full mode inlines a mirror from the knowledge directory;
                # full_mode_max_tokens bounds how many. Routing mode does not.
                body = _load_node_content(str(mirror_files[ref]))
            cached_guard = guard_projection_content(body, repo_path)
            if cached_guard.managed:
                # A cached marker alone cannot establish what is now on disk.
                body = ""
                for candidate_id, candidate_data in ranked_nodes:
                    if str(candidate_data.get("content_ref")) == ref:
                        blocked_projections.add(candidate_id)
            node_bodies[ref] = body
        return node_bodies[ref]

    downgrades, unguarded_inline_tokens = _full_mode_downgrades(
        ranked_nodes, mode_str, loadout_config, body_of
    )
    if downgrades:
        header["full_mode_guard"] = {
            "downgraded_nodes": sorted(downgrades),
            "max_tokens": loadout_config.full_mode_max_tokens,
            "unguarded_inline_tokens": unguarded_inline_tokens,
        }
        logger.warning(
            "Loadout %s: code mirrors served as summary and path: %d; inline "
            "content would be ~%d tokens, over full_mode_max_tokens=%s",
            task_id,
            len(downgrades),
            unguarded_inline_tokens,
            loadout_config.full_mode_max_tokens,
        )

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
            "title": projection_titles.get(node_id, node_data.get("title", node_id)),
        }
        if selection_class is not None:
            entry["selection_class"] = selection_class
        reasons = node_data.get("_reasons") or ()
        if reasons:
            entry["reasons"] = tuple(reasons)

        content_ref = projection_refs.get(node_id) or node_data.get("content_ref")
        if not content_ref:
            content_ref = _local_node_ref(node_id, node_data, repo_path, local_files)
        reading_priority = _node_reading_priority(
            node_data, selection_class, loadout_config
        )
        if reading_priority:
            entry["reading_priority"] = str(reading_priority)
        else:
            entry["reading_priority"] = mode_str

        # Load content based on mode and reading_priority
        if content_ref:
            entry["content_ref"] = str(content_ref)
            mirror_file = mirror_files.get(str(content_ref))
            if mirror_file is not None and repo_path is not None:
                # The path a reader at the repository root can open.
                entry["content_ref"] = mirror_file.relative_to(repo_path).as_posix()
        content = body_of(content_ref)

        if node_id in blocked_projections:
            # Do not expose cached titles, source paths, or authored prose from
            # a mixed node when any record-derived part is no longer current.
            entry = {
                "id": node_id,
                "origin": "local",
                "confidence": 0.0,
                "domain": "",
                "title": "Record projection needs review",
                "reading_priority": "review",
                "content": "Record projection unavailable: review and refresh this node before using it.",
            }
            if selection_class is not None:
                entry["selection_class"] = selection_class
            node_entries.append(entry)
            continue

        # Resolve effective_mode once per node so per-node
        # reading_priority wins over the loadout-level mode_str per FR-L10c.
        # Precedence: reading_priority (if set) > mode_str.
        effective_mode = _effective_read_mode(reading_priority, mode_str, content)
        if node_id in downgrades:
            # Over the full-mode budget: serve this mirror as routing mode would.
            effective_mode = LoadoutMode.ROUTING.value
            entry["reading_priority"] = effective_mode
            entry["full_mode_downgrade_tokens"] = downgrades[node_id]

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
            # A mirror read from the knowledge directory is summarized only by
            # its own section, as in routing mode, not by its source text.
            source = "" if str(content_ref) in mirror_files else content
            summary = _extract_summary(
                source or _mirror_summary_source(node_data, repo_path)
            )
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
            if (u in node_id_set or v in node_id_set) and not (
                {u, v} & blocked_projections
            ):
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
        refs = (
            [] if node_id in blocked_projections else node_data.get("session_refs", [])
        )
        if refs:
            for ref in refs:
                session_refs.append(
                    {
                        "node_id": node_id,
                        "session_ref": ref,
                    }
                )

    # ── Section 5: Reading Order ─────────────────────────────────────
    node_ids_ordered = [
        nid for nid, _ in ranked_nodes if nid not in blocked_projections
    ]
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

    if downgrades:
        parts.append(
            f"**Full-mode budget exceeded:** inline content would be "
            f"~{unguarded_inline_tokens} tokens, over "
            f"`loadout.full_mode_max_tokens` "
            f"({loadout_config.full_mode_max_tokens}). Code mirrors served as "
            f"summary and path only: {len(downgrades)}, each marked **Downgraded** "
            "below and listed under `full_mode_guard` in the header. No node was "
            "dropped."
        )
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
