"""build_graph.py — The Merge Compiler (§2.3 of system design).

Compiles the unified NetworkX DiGraph from all sources:
  1. Global nodes from ~/.claude/akms/nodes/ (or $AKMS_GLOBAL_VAULT)
  2. Local nodes from <repo>/knowledge/local-nodes/
  3. Code-mirror nodes from <repo>/knowledge/code-mirror/ (canonical schema-validated)
  4. Local state overlay from local_state.yaml
  5. Serialize to graph.json

All operations are deterministic. Output is stable across runs.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import frontmatter
import networkx as nx

from akms import AKMS_SCHEMA_VERSION
from akms.schema.errors import SchemaValidationError, SchemaVersionError
from akms.schema.validators import (
    parse_local_state,
    parse_node_frontmatter_from_dict,
)
from akms.telemetry import traced

logger = logging.getLogger(__name__)


def resolve_global_vault(
    explicit: str | Path | None = None,
    config: Any | None = None,
) -> Path:
    """Resolve the global vault path with documented precedence (F-06).

    Precedence (highest wins):
      1. ``explicit`` — a caller-supplied path (CLI flag, test override).
      2. ``AKMS_GLOBAL_VAULT`` environment variable.
      3. ``config.global_vault`` when ``config`` is supplied.
      4. Default ``~/.claude/akms/nodes``.

    All returned paths have ``~`` expanded. This is the single source of
    truth for vault resolution across ``build_graph``, ``graph_status``,
    and any orchestrator handler that needs to pre-resolve a vault path.
    """
    if explicit is not None:
        return Path(explicit).expanduser()
    env = os.environ.get("AKMS_GLOBAL_VAULT")
    if env:
        return Path(env).expanduser()
    config_vault = getattr(config, "global_vault", None) if config is not None else None
    if config_vault:
        return Path(str(config_vault)).expanduser()
    return Path("~/.claude/akms/nodes").expanduser()


# Back-compat shim for any caller that imported the private helper.
# Preserves the old env > config_path > default precedence exactly.
def _resolve_global_vault(config_path: str | None = None) -> Path:
    """Deprecated: use :func:`resolve_global_vault`."""
    env = os.environ.get("AKMS_GLOBAL_VAULT")
    if env:
        return Path(env).expanduser()
    if config_path:
        return Path(config_path).expanduser()
    return Path("~/.claude/akms/nodes").expanduser()


def _collect_md_files(directory: Path) -> list[Path]:
    """Collect node .md files in a directory recursively (deterministic sort).

    Files beneath a ``content/`` directory are payload bodies addressed by a
    node's ``content_ref`` (always a ``content/...`` path), not nodes in their
    own right. They carry frontmatter of their own — a skill's ``name`` and
    ``description``, say — but no ``akms_schema``, and the loader treats a
    missing ``akms_schema`` as a schema error that is re-raised regardless of
    ``strict``. Collecting them would abort every build over a vault that
    ships payloads inline, which is exactly the layout of the bundled corpus
    at ``akms/_bundled/global_nodes/``.
    """
    if not directory.exists():
        return []
    return sorted(
        p
        for p in directory.glob("**/*.md")
        if "content" not in p.relative_to(directory).parts[:-1]
    )


def _load_node_frontmatter(
    path: Path,
    strict: bool = False,
    skipped_accumulator: list | None = None,
) -> dict[str, Any] | None:
    """Load YAML frontmatter from a .md file.

    In ``strict`` mode any parse failure re-raises so the
    build halts. In non-strict mode the failure is logged AND appended to
    ``skipped_accumulator`` (when provided) so ``graph_status`` can surface
    it in the health report.
    """
    try:
        post = frontmatter.load(str(path))
        return dict(post.metadata)
    except Exception as e:
        msg = f"Failed to parse frontmatter from {path}: {e}"
        if strict:
            raise
        logger.warning(msg)
        if skipped_accumulator is not None:
            skipped_accumulator.append({"path": str(path), "reason": str(e)})
        return None


@traced("akms.build_graph")
def build_graph(
    repo_root: str | Path,
    global_vault: str | Path | None = None,
    output_path: str | Path | None = None,
    config: Any | None = None,
    strict: bool = False,
) -> nx.DiGraph:
    """Compile the unified knowledge graph from all sources.

    Args:
        repo_root: Path to the repository root (contains knowledge/).
        global_vault: Override path to global vault. If None, resolved via
                      precedence: AKMS_GLOBAL_VAULT env var > ``config.global_vault``
                      (when ``config`` is supplied) > default ``~/.claude/akms/nodes``.
        output_path: Override path for graph.json output. If None, writes to
                     <repo_root>/knowledge/graph/graph.json.
        config: Optional PropagationConfig. When provided, ``config.global_vault``
                becomes the third step in the precedence chain (honored if no
                explicit arg and no env var is set).

    Returns:
        The compiled NetworkX DiGraph.

    Raises:
        SchemaVersionError: If any source has wrong schema version.
        SchemaValidationError: If any source has invalid schema.
    """
    repo_root = Path(repo_root)
    knowledge_dir = repo_root / "knowledge"
    graph_dir = knowledge_dir / "graph"

    vault_path = resolve_global_vault(explicit=global_vault, config=config)

    if output_path is None:
        output_path = graph_dir / "graph.json"
    else:
        output_path = Path(output_path)

    G = nx.DiGraph()
    warnings: list[str] = []
    skipped_files: list[dict] = []  # surfaced by graph_status
    repo_id = repo_root.name

    # ── Step 1: Load Global Nodes ────────────────────────────────────
    global_files = _collect_md_files(vault_path)
    for md_path in global_files:
        data = _load_node_frontmatter(
            md_path, strict=strict, skipped_accumulator=skipped_files
        )
        if data is None:
            continue

        try:
            node = parse_node_frontmatter_from_dict(
                data, is_local=False, path=str(md_path)
            )
        except (SchemaVersionError, SchemaValidationError):
            raise  # Fatal — halt on schema errors per FR-G08

        node_id = node.id
        attrs = node.model_dump()

        # Extract edges before adding node
        edges = attrs.pop("edges", [])

        # Add origin marker
        attrs["node_origin"] = "global"
        # confidence_default = the global seed value (for inspectability)
        attrs["confidence_default"] = attrs["confidence"]
        # Default experiential state (may be overridden by overlay in step 4)
        attrs["activations"] = 0
        attrs["last_activated"] = None

        G.add_node(node_id, **attrs)

        # Add structural edges
        for edge in edges:
            G.add_edge(
                node_id,
                edge["to"],
                type=edge["type"],
                weight=edge["weight"],
                note=edge.get("note", ""),
                edge_origin="global",
            )

    logger.info("Loaded %d global nodes from %s", len(global_files), vault_path)

    # ── Step 2: Load Local Nodes ─────────────────────────────────────
    local_nodes_dir = knowledge_dir / "local-nodes"
    local_files = _collect_md_files(local_nodes_dir)
    local_count = 0

    for md_path in local_files:
        data = _load_node_frontmatter(
            md_path, strict=strict, skipped_accumulator=skipped_files
        )
        if data is None:
            continue

        try:
            node = parse_node_frontmatter_from_dict(
                data, is_local=True, path=str(md_path)
            )
        except (SchemaVersionError, SchemaValidationError):
            raise

        node_id = node.id

        # Skip on id collision with global node
        if node_id in G and G.nodes[node_id].get("node_origin") == "global":
            msg = (
                f"Local node '{node_id}' collides with global node — "
                f"skipping local (file: {md_path})"
            )
            warnings.append(msg)
            logger.warning(msg)
            continue

        attrs = node.model_dump()
        edges = attrs.pop("edges", [])
        attrs["node_origin"] = "local"
        attrs["confidence_default"] = attrs["confidence"]
        attrs["activations"] = 0
        attrs["last_activated"] = None

        G.add_node(node_id, **attrs)

        for edge in edges:
            G.add_edge(
                node_id,
                edge["to"],
                type=edge["type"],
                weight=edge["weight"],
                note=edge.get("note", ""),
                edge_origin="local",
            )

        local_count += 1

    logger.info("Loaded %d local nodes", local_count)

    # ── Step 3: Load Code-Mirror Nodes ───────────────────────────────
    mirror_dir = knowledge_dir / "code-mirror"
    mirror_files = _collect_md_files(mirror_dir)
    mirror_count = 0

    for md_path in mirror_files:
        data = _load_node_frontmatter(
            md_path, strict=strict, skipped_accumulator=skipped_files
        )
        if data is None:
            continue

        try:
            node = parse_node_frontmatter_from_dict(
                data,
                is_code_mirror=True,
                path=str(md_path),
            )
        except (SchemaVersionError, SchemaValidationError):
            raise

        attrs = node.model_dump()
        node_id = attrs["id"]
        attrs["node_origin"] = "code-mirror"
        attrs["confidence_default"] = attrs.get("confidence", 1.0)
        attrs["activations"] = 0
        attrs["last_activated"] = None

        G.add_node(node_id, **attrs)
        mirror_count += 1

    logger.info("Loaded %d code-mirror nodes", mirror_count)

    # ── Step 4: Apply Local Overlay ──────────────────────────────────
    overlay_path = graph_dir / "local_state.yaml"
    if overlay_path.exists():
        overlay = parse_local_state(overlay_path)
        repo_id = overlay.repo_id or repo_root.name

        # 4a. Override per-node state
        for node_id, state in overlay.nodes.items():
            if node_id not in G:
                msg = (
                    f"Orphaned overlay entry: node '{node_id}' in "
                    f"local_state.yaml but not in graph"
                )
                warnings.append(msg)
                logger.warning(msg)
                continue

            state_dict = state.model_dump(exclude_none=True)
            # Convert date to string for JSON serialization
            if "last_activated" in state_dict and state_dict["last_activated"]:
                state_dict["last_activated"] = str(state_dict["last_activated"])

            G.nodes[node_id].update(state_dict)

        # 4b. Add local edges
        for edge in overlay.local_edges:
            G.add_edge(
                edge.from_node,
                edge.to,
                type=edge.type,
                weight=edge.weight,
                note=edge.note,
                edge_origin="local",
            )

        # 4c. Create session nodes
        for session_id, session in overlay.session_nodes.items():
            attrs = {
                "id": session_id,
                "title": session.title,
                "domain": "session",
                "tags": session.tags,
                "status": "established",
                "confidence": 1.0,
                "confidence_default": 1.0,
                "source": "generated",
                "auto_update": True,
                "node_origin": "local",
                "outcome": session.outcome,
                "content_ref": session.content_ref,
                "phase": session.phase,
                "akms_schema": AKMS_SCHEMA_VERSION,
                "activations": 0,
                "last_activated": None,
            }
            G.add_node(session_id, **attrs)

        logger.info(
            "Applied overlay: %d node overrides, %d local edges, %d session nodes",
            len(overlay.nodes),
            len(overlay.local_edges),
            len(overlay.session_nodes),
        )

    # ── Step 5: Serialize ────────────────────────────────────────────
    graph_data = _serialize_graph(G, vault_path, repo_id)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(graph_data, f, sort_keys=True, indent=2, default=str)

    logger.info(
        "Compiled graph: %d nodes, %d edges → %s",
        G.number_of_nodes(),
        G.number_of_edges(),
        output_path,
    )

    if warnings:
        logger.info("Build warnings (%d):", len(warnings))
        for w in warnings:
            logger.info("  - %s", w)

    # Preserve skipped-file details through graph.graph attrs so
    # graph_status can report non-fatal parse failures instead of
    # silently omitting sources.
    G.graph["skipped_files"] = list(skipped_files)

    return G


def _sanitize_vault_path(vault: Path) -> str:
    """Return the vault path with the user's home directory abbreviated to ``~``.

    The compiled graph is a shareable artifact; serializing an absolute home
    path (the default vault lives under ``~/.claude/akms/nodes``) would leak
    the local username into anything built from it. The field is informational
    — nothing reads it back — so the abbreviated form loses nothing.
    """
    try:
        return "~/" + str(Path(vault).resolve().relative_to(Path.home())).replace(
            "\\", "/"
        )
    except ValueError:
        return str(vault)


def _serialize_graph(
    G: nx.DiGraph,
    global_vault: Path,
    repo_id: str,
) -> dict:
    """Serialize the graph to NetworkX node-link format (§8 of spec)."""
    now = datetime.now().isoformat(timespec="seconds")

    # Build node list with stable key ordering
    nodes = []
    for node_id in sorted(G.nodes):
        node_data = dict(G.nodes[node_id])
        node_data["id"] = node_id
        nodes.append(node_data)

    # Build link list with stable ordering
    links = []
    for u, v, edge_data in sorted(G.edges(data=True), key=lambda e: (e[0], e[1])):
        link = {
            "source": u,
            "target": v,
        }
        link.update(edge_data)
        links.append(link)

    return {
        "directed": True,
        "multigraph": False,
        "graph": {
            "akms_schema": AKMS_SCHEMA_VERSION,
            "generated_at": now,
            "node_count": G.number_of_nodes(),
            "edge_count": G.number_of_edges(),
            "global_vault": _sanitize_vault_path(global_vault),
            "repo_id": repo_id,
        },
        "nodes": nodes,
        "links": links,
    }


def load_graph(path: str | Path) -> nx.DiGraph:
    """Load a compiled graph.json back into a NetworkX DiGraph.

    Args:
        path: Path to graph.json.

    Returns:
        The reconstructed DiGraph.
    """
    path = Path(path)
    with open(path) as f:
        data = json.load(f)

    G = nx.DiGraph()

    for node_data in data.get("nodes", []):
        node_id = node_data.pop("id")
        G.add_node(node_id, id=node_id, **node_data)

    for link_data in data.get("links", []):
        source = link_data.pop("source")
        target = link_data.pop("target")
        G.add_edge(source, target, **link_data)

    return G
