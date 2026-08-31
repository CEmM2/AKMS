"""re_evaluate.py — Loadout Regeneration After Updates (§2.6 follow-up).

Thin orchestration wrapper that regenerates loadouts for the next phase
after ``update_graph()`` and ``generate_mirror()`` have been run.

Calls ``query_subgraph()`` + ``generate_loadout()`` with next-phase parameters.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import networkx as nx

from akms.graph.build_graph import build_graph, load_graph
from akms.graph.generate_loadout import generate_loadout, select_loadout_mode
from akms.graph.qmd_cache import compute_graph_version
from akms.graph.query_subgraph import query_subgraph
from akms.schema.models import AgentRole, LoadoutMode, PropagationConfig
from akms.schema.validators import parse_propagation_config
from akms.telemetry import traced

logger = logging.getLogger(__name__)


@traced("akms.re_evaluate")
def re_evaluate(
    repo_root: str | Path,
    task_id: str,
    phase: int,
    seed_tags: list[str],
    agent_role: AgentRole | str = AgentRole.IMPLEMENTER,
    available_context: int = 50000,
    global_vault: str | Path | None = None,
    config: PropagationConfig | None = None,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """Regenerate a loadout with updated graph state.

    This is typically called after:
      1. ``update_graph()`` has processed PCDs/AgentMemories
      2. ``generate_mirror()`` has updated code mirrors
      3. ``build_graph()`` has recompiled graph.json

    Args:
        repo_root: Path to the repository root.
        task_id: Task identifier for the loadout header.
        phase: Next phase number.
        seed_tags: Domain tags for subgraph query.
        agent_role: Role profile for query (default: implementer).
        available_context: Available context tokens for mode selection.
        global_vault: Override global vault path.
        config: PropagationConfig (loads from file or defaults if None).
        output_path: Override output file path.

    Returns:
        Dict with keys:
        {
            "loadout_path": str,
            "mode": str,
            "node_count": int,
            "graph_version": str,
        }
    """
    repo_root = Path(repo_root)
    knowledge_dir = repo_root / "knowledge"
    graph_dir = knowledge_dir / "graph"
    graph_json = graph_dir / "graph.json"

    # Load config
    if config is None:
        config_path = graph_dir / "propagation_config.yaml"
        if config_path.exists():
            config = parse_propagation_config(config_path)
        else:
            config = PropagationConfig()

    # Load or build graph
    if graph_json.exists():
        G = load_graph(graph_json)
    else:
        G = build_graph(repo_root, global_vault=global_vault)

    # Compute graph version
    graph_version = compute_graph_version(graph_json)

    # Query subgraph
    ranked_nodes = query_subgraph(
        G, seed_tags, agent_role, config=config,
    )

    # Select mode
    mode = select_loadout_mode(ranked_nodes, available_context, config)

    # generate_loadout writes files as: {output_dir}/{phase}-{task_id}-loadout.md
    if output_path is not None:
        # User specified a full file path — we write there directly
        output_path = Path(output_path)
        output_dir = output_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = knowledge_dir / "loadouts"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{phase}-{task_id}-loadout.md"

    # Generate loadout content
    content = generate_loadout(
        G=G,
        ranked_nodes=ranked_nodes,
        task_id=task_id,
        phase=phase,
        graph_version=graph_version,
        seed_tags=seed_tags,
        agent_role=agent_role,
        mode=mode,
        available_context=available_context,
        config=config,
        output_path=output_path,
        repo_root=str(repo_root),
    )

    result = {
        "loadout_path": str(output_path),
        "mode": mode.value if isinstance(mode, LoadoutMode) else str(mode),
        "node_count": len(ranked_nodes),
        "graph_version": graph_version,
    }

    logger.info(
        "re_evaluate: generated loadout %s (%d nodes, %s mode)",
        output_path, len(ranked_nodes), result["mode"],
    )

    return result
