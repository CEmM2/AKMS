"""mcp_tools.py — MCP Server Exposing AKMS Graph Tools to Agents.

Creates a FastMCP server instance with 8 tools wrapping the deterministic
graph functions. The server is consumed by the Claude Agent SDK via
``McpSdkServerConfig(type="sdk", name="akms-tools", instance=server)``.

Usage::

    from akms.orchestrator.mcp_tools import create_mcp_server

    server = create_mcp_server(repo_root="/path/to/repo")

    # Pass to Claude Agent SDK:
    options = ClaudeAgentOptions(
        mcp_servers={
            "akms-tools": {
                "type": "sdk",
                "name": "akms-tools",
                "instance": server,
            }
        }
    )

All tools are **sync** (the underlying graph functions are sync).
All tools return JSON-serializable dicts. Errors are caught and returned
as ``{"error": str}`` so agents can handle them gracefully.

The factory ``create_mcp_server(repo_root, global_vault)`` binds these
paths at creation time via closure — agents never pass repo paths.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from akms.graph.build_graph import build_graph, load_graph
from akms.graph.generate_loadout import generate_loadout, select_loadout_mode
from akms.graph.generate_mirror import generate_mirror
from akms.graph.graph_status import graph_status
from akms.graph.qmd_cache import compute_graph_version
from akms.graph.query_subgraph import query_subgraph
from akms.graph.re_evaluate import re_evaluate
from akms.graph.tag_derivation import derive_tags
from akms.graph.update_graph import update_graph
from akms.schema.models import AgentRole, PropagationConfig
from akms.schema.validators import parse_propagation_config

logger = logging.getLogger(__name__)

# ── Helpers ──────────────────────────────────────────────────────────


def _load_graph_from_repo(repo_root: Path, global_vault: str | None):
    """Load graph.json if it exists, otherwise compile from sources."""
    graph_json = repo_root / "knowledge" / "graph" / "graph.json"
    if graph_json.exists():
        return load_graph(graph_json), graph_json
    G = build_graph(str(repo_root), global_vault=global_vault)
    return G, graph_json


def _serialize_ranked_nodes(ranked_nodes: list[tuple]) -> list[dict]:
    """Convert query_subgraph tuples to JSON-serializable dicts."""
    result = []
    for node_id, data in ranked_nodes:
        entry = {
            "id": node_id,
            "domain": data.get("domain", ""),
            "confidence": data.get("confidence", 0.0),
            "node_origin": data.get("node_origin", ""),
            "title": data.get("title", ""),
        }
        # Include tags if present
        tags = data.get("tags")
        if tags:
            entry["tags"] = list(tags) if not isinstance(tags, list) else tags
        result.append(entry)
    return result


# ── Factory ──────────────────────────────────────────────────────────


def build_fastmcp_app(
    repo_root: str | Path,
    global_vault: str | Path | None = None,
) -> "FastMCP":
    """Build the AKMS FastMCP app (graph tools bound to a repo).

    Shared by the in-process SDK server (:func:`create_mcp_server`) and the
    stdio entrypoint (:mod:`akms.orchestrator.mcp_stdio`), so external CLI
    backends (``claude --mcp-config``) get the same ``mcp__akms__akms_*`` tools.

    Args:
        repo_root: Path to the repository root.
        global_vault: Override global vault path (default: ``$AKMS_GLOBAL_VAULT``
            or ``~/.claude/akms/nodes/``).

    Returns:
        The :class:`~mcp.server.fastmcp.FastMCP` application instance.
    """
    _repo = Path(repo_root)
    config_path = _repo / "knowledge" / "graph" / "propagation_config.yaml"
    if config_path.exists():
        _config = parse_propagation_config(config_path)
    else:
        _config = PropagationConfig()

    # F-06: resolve the vault once through the shared helper
    # (explicit arg > env > config > default). When nothing is set we keep
    # `_vault = None` so every downstream `build_graph` / `graph_status`
    # call falls through to its own default resolution.
    from akms.graph.build_graph import resolve_global_vault
    _vault: str | None
    if global_vault is not None or _config.global_vault:
        _vault = str(resolve_global_vault(explicit=global_vault, config=_config))
    else:
        _vault = None

    app = FastMCP("akms-tools")

    # ── Tool 1: Build Graph ──────────────────────────────────────

    @app.tool()
    def akms_build_graph() -> dict:
        """Compile the knowledge graph from global vault + local state into graph.json.

        Runs the 5-step merge compiler: load global nodes, load local nodes,
        load code-mirror markers, apply overlay, serialize. Call this when you
        need a fresh compiled graph.
        """
        try:
            G = build_graph(str(_repo), global_vault=_vault)
            graph_json = _repo / "knowledge" / "graph" / "graph.json"
            return {
                "node_count": G.number_of_nodes(),
                "edge_count": G.number_of_edges(),
                "graph_json_path": str(graph_json),
            }
        except Exception as e:
            logger.exception("akms_build_graph failed")
            return {"error": str(e)}

    # ── Tool 2: Query Subgraph ───────────────────────────────────

    @app.tool()
    def akms_query_subgraph(
        seed_tags: list[str],
        agent_role: str = "implementer",
        max_depth: int = 2,
    ) -> dict:
        """Extract a ranked subgraph for loadout construction.

        Given seed tags (domain keywords) and an agent role, finds matching
        nodes, expands via ego_graph, filters, ranks, and returns the top
        nodes for inclusion in a loadout.

        Args:
            seed_tags: Domain tags to seed the query (e.g. ["taichi", "gpu"]).
            agent_role: One of "implementer", "code_reviewer", "physics_reviewer".
            max_depth: Ego graph expansion depth (default 2).
        """
        try:
            G, _ = _load_graph_from_repo(_repo, _vault)
            ranked = query_subgraph(
                G, seed_tags, agent_role, config=_config, max_depth=max_depth,
            )
            return {
                "nodes": _serialize_ranked_nodes(ranked),
                "count": len(ranked),
            }
        except Exception as e:
            logger.exception("akms_query_subgraph failed")
            return {"error": str(e)}

    # ── Tool 3: Generate Loadout ─────────────────────────────────

    @app.tool()
    def akms_generate_loadout(
        task_id: str,
        phase: int,
        seed_tags: list[str],
        agent_role: str = "implementer",
        mode: str = "routing",
    ) -> dict:
        """Generate a loadout markdown file for an agent task.

        Queries the subgraph, selects content mode, and writes the loadout
        file to ``knowledge/loadouts/``.

        Args:
            task_id: Task identifier for the loadout header.
            phase: Current phase number.
            seed_tags: Domain tags for the subgraph query.
            agent_role: Role profile (implementer, code_reviewer, physics_reviewer).
            mode: Content mode ("routing" or "full").
        """
        try:
            G, graph_json = _load_graph_from_repo(_repo, _vault)
            graph_version = compute_graph_version(graph_json)
            ranked = query_subgraph(G, seed_tags, agent_role, config=_config)
            loadout_dir = _repo / "knowledge" / "loadouts"
            loadout_path = loadout_dir / f"{phase}-{task_id}-loadout.md"
            generate_loadout(
                G=G,
                ranked_nodes=ranked,
                task_id=task_id,
                phase=phase,
                graph_version=graph_version,
                seed_tags=seed_tags,
                agent_role=agent_role,
                mode=mode,
                config=_config,
                output_path=loadout_path,
                repo_root=str(_repo),
            )
            return {
                "loadout_path": str(loadout_path),
                "node_count": len(ranked),
                "mode": mode,
                "graph_version": graph_version,
            }
        except Exception as e:
            logger.exception("akms_generate_loadout failed")
            return {"error": str(e)}

    # ── Tool 4: Update Graph ─────────────────────────────────────

    @app.tool()
    def akms_update_graph(source_json: str) -> dict:
        """Process AgentMemory or PCD data to update local state and recompile.

        Accepts a JSON string containing the persistent zone data (nodes_used,
        pitfalls_discovered, new_knowledge, etc.). Updates local_state.yaml
        and recompiles graph.json.

        Args:
            source_json: JSON string of the source data (AgentMemory/PCD dict).
        """
        try:
            source = json.loads(source_json)
            result = update_graph(
                source, str(_repo), config=_config, global_vault=_vault,
            )
            return result
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON: {e}"}
        except Exception as e:
            logger.exception("akms_update_graph failed")
            return {"error": str(e)}

    # ── Tool 5: Generate Mirror ──────────────────────────────────

    @app.tool()
    def akms_generate_mirror(
        phase: int,
        parent_branch: str = "main",
    ) -> dict:
        """Generate code mirror files via the configured mirror provider.

        Default provider is the legacy Python AST generator. When
        ``propagation_config.mirror.provider`` is ``repo2md``, invokes the
        pinned external CLI (argv only; never imports repo2md).

        Args:
            phase: Current phase number.
            parent_branch: Git branch to diff against (default "main").
        """
        try:
            result = generate_mirror(
                str(_repo),
                phase,
                parent_branch=parent_branch,
                config=_config,
                llm_fn=None,  # deterministic MCP path never invokes LLM drift
            )
            return result
        except Exception as e:
            logger.exception("akms_generate_mirror failed")
            return {
                "error": str(e),
                "provider": getattr(getattr(_config, "mirror", None), "provider", "legacy"),
            }

    # ── Tool 6: Graph Status ─────────────────────────────────────

    @app.tool()
    def akms_graph_status() -> dict:
        """Run health check on the knowledge graph.

        Returns diagnostics: degraded nodes, tentative awaiting promotion,
        id collisions, orphaned nodes, stale nodes, orphaned overlay entries.
        """
        try:
            result = graph_status(str(_repo), global_vault=_vault, config=_config)
            return result
        except Exception as e:
            logger.exception("akms_graph_status failed")
            return {"error": str(e)}

    # ── Tool 7: Derive Tags ──────────────────────────────────────

    @app.tool()
    def akms_derive_tags(task_json: str) -> dict:
        """Derive AKMS tags for a task using hybrid scope + text matching.

        Takes a task JSON with title, objective, scope, and optionally
        existing akms_tags. Returns derived tags (union of scope-based
        and text-based matching).

        Args:
            task_json: JSON string of the task dict.
        """
        try:
            task = json.loads(task_json)
            G, _ = _load_graph_from_repo(_repo, _vault)
            tags = derive_tags(G, task)
            return {
                "tags": tags,
                "task_id": task.get("task_id", task.get("id", "")),
            }
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON: {e}"}
        except Exception as e:
            logger.exception("akms_derive_tags failed")
            return {"error": str(e)}

    # ── Tool 8: Re-evaluate ──────────────────────────────────────

    @app.tool()
    def akms_re_evaluate(
        task_id: str,
        phase: int,
        seed_tags: list[str],
        agent_role: str = "implementer",
    ) -> dict:
        """Regenerate loadout with updated graph state.

        Called after update_graph + generate_mirror to produce a fresh loadout
        reflecting new confidence values and code mirrors.

        Args:
            task_id: Task identifier.
            phase: Next phase number.
            seed_tags: Domain tags for subgraph query.
            agent_role: Role profile (default: implementer).
        """
        try:
            result = re_evaluate(
                str(_repo),
                task_id=task_id,
                phase=phase,
                seed_tags=seed_tags,
                agent_role=agent_role,
                global_vault=_vault,
                config=_config,
            )
            return result
        except Exception as e:
            logger.exception("akms_re_evaluate failed")
            return {"error": str(e)}

    # ── Tools 9–12: qmd-backed search (F-01b) ───────────────────────
    #
    # These four tools replace the forbidden Grep runtime affordance with
    # qmd-backed (with grep fallback) search tools that the frozen spec
    # (FR-C05, FR-Q05) mandates. They shell out to seed/qmd/run_qmd.sh
    # so the wrapper logic (qmd detection, collection naming, grep fallback)
    # stays in one place.

    # Locate seed/qmd/run_qmd.sh via the shared resource helper so every
    # caller uses the same precedence (importlib.resources → repo-root
    # candidates → package-root fallback).
    from akms._resources import seed_qmd_path
    _seed_qmd = seed_qmd_path(
        "run_qmd.sh",
        repo_root_candidates=[
            _repo.parent / "Packages" / "AKMS",
            _repo / "Packages" / "AKMS",
            _repo.parents[0] if len(_repo.parents) > 0 else _repo,
            _repo,
        ],
    )

    def _run_qmd(subcmd: str, query: str) -> list[dict]:
        """Thin adapter to :func:`akms.orchestrator.qmd_shell.run_qmd`.

        Kept as a closure so the surrounding tools can call it as before
        without re-threading ``_repo`` at every call site. The actual
        shell-out, parsing, and fallback logic lives in the shared helper
        so the Codex function-tool registry can share the same surface.
        """
        from akms.orchestrator.qmd_shell import run_qmd as _run
        return _run(subcmd, query, repo_root=_repo)

    @app.tool()
    def akms_search_nodes(query: str, limit: int = 20) -> list[dict]:
        """Search knowledge nodes (global vault + local-nodes) via qmd.

        Returns up to ``limit`` hits as a list of ``{path, line, snippet}``
        dicts. The search is scoped to global + local node directories by
        the qmd wrapper — callers don't pass paths.
        """
        return _run_qmd("search_nodes", query)[: max(1, int(limit))]

    @app.tool()
    def akms_search_mirror(query: str, limit: int = 20) -> list[dict]:
        """Search the code mirror (``knowledge/code-mirror/``) via qmd.

        This is the designated replacement for Grep in agent workflows per
        FR-C05 / FR-Q05. Returns up to ``limit`` ``{path, line, snippet}``
        dicts.
        """
        return _run_qmd("search_mirror", query)[: max(1, int(limit))]

    @app.tool()
    def akms_search_sessions(query: str, limit: int = 20) -> list[dict]:
        """Search session files (AgentMemory / PCD markdown) via qmd.

        Returns up to ``limit`` ``{path, line, snippet}`` dicts.
        """
        return _run_qmd("search_sessions", query)[: max(1, int(limit))]

    @app.tool()
    def akms_get_pitfalls(node_ids: list[str]) -> list[dict]:
        """Return pitfall-edge entries whose ``from`` node is in ``node_ids``.

        Read directly from ``local_state.yaml`` (no qmd call required — this
        is structural graph data). Returns a list of
        ``{from, to, type, weight, note, source_id}`` dicts. The ``source_id``
        field is optional and only present on edges produced by the Phase 3
        replay-ledger changes.
        """
        import yaml as _yaml
        overlay_path = _repo / "knowledge" / "graph" / "local_state.yaml"
        if not overlay_path.exists():
            return []
        try:
            overlay = _yaml.safe_load(overlay_path.read_text(encoding="utf-8")) or {}
        except Exception:
            logger.exception("failed to parse %s", overlay_path)
            return []
        local_edges = overlay.get("local_edges") or []
        node_set = {str(n) for n in node_ids}
        hits: list[dict] = []
        for edge in local_edges:
            if not isinstance(edge, dict):
                continue
            if edge.get("type") != "pitfall":
                continue
            src = str(edge.get("from", ""))
            if node_set and src not in node_set:
                continue
            hits.append({
                "from": src,
                "to": str(edge.get("to", "")),
                "type": "pitfall",
                "weight": float(edge.get("weight", 0.5) or 0.5),
                "note": str(edge.get("note", "") or ""),
                "source_id": str(edge.get("source_id", "") or ""),
            })
        hits.sort(key=lambda h: (h["from"], h["to"], h["note"]))
        return hits

    #   # ── optional resolve-task wrapper (shared service) ────────────────

    @app.tool()
    def akms_resolve_task(
        task_json_path: str,
        routes_path: str,
        agent_role: str = "implementer",
        phase: int | None = None,
        changed_paths: list[str] | None = None,
        base: str | None = None,
        head: str | None = None,
        mode: str = "routing",
        loadout_path: str | None = None,
        manifest_path: str | None = None,
    ) -> dict:
        """Resolve exact task knowledge into a loadout and resolution manifest.

        Supplementary inspection surface over the same deterministic
        ``resolve_task`` implementation used by ``akms resolve-task``. Does
        **not** call an LLM or the network. Callers must not treat this tool as
        a substitute for orchestrator-driven pre-dispatch delivery of required
        context.

        Args:
            task_json_path: Path to the task JSON (absolute or repo-relative).
            routes_path: Path to the task route index (JSON or YAML).
            agent_role: ``implementer``, ``code_reviewer``, or ``physics_reviewer``.
            phase: Optional phase number for output filenames.
            changed_paths: Optional sequence of repository-relative paths.
                Must be a list — a single path string is rejected.
            base: Optional git base revision (mutually exclusive with changed_paths).
            head: Optional git head revision (default HEAD when base is set).
            mode: Loadout content mode (``routing`` or ``full``).
            loadout_path: Optional loadout output path.
            manifest_path: Optional resolution-manifest output path.
        """
        from akms.task_context.resolve_task_service import resolve_task

        result = resolve_task(
            repo_root=_repo,
            task=task_json_path,
            route_index=routes_path,
            agent_role=agent_role,
            changed_paths=changed_paths,
            base=base,
            head=head,
            loadout_path=loadout_path,
            manifest_path=manifest_path,
            mode=mode,
            phase=phase,
            config=_config,
        )
        return result.to_json_dict()

    return app


def create_mcp_server(
    repo_root: str | Path,
    global_vault: str | Path | None = None,
) -> Any:
    """Create the lowlevel MCP server for in-process SDK consumption.

    Thin wrapper over :func:`build_fastmcp_app`; contract unchanged.

    Returns:
        ``mcp.server.lowlevel.Server`` instance suitable for
        ``McpSdkServerConfig(type="sdk", instance=...)``.
    """
    return build_fastmcp_app(repo_root, global_vault)._mcp_server
