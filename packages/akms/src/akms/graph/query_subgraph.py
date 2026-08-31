"""query_subgraph.py — Subgraph Query Engine (§2.4 of system design).

Given a task description, seed tags, and agent role, extracts a ranked
subgraph for loadout construction. Operates on the compiled graph.json —
unaware of the global/local split.

Algorithm (12 steps):
  1. Load query profile for agent_role from config
  2. Find seed nodes matching any tag in domain_tags
  3. Compute ego_graph of radius max_depth from each seed
  4. Union all ego_graphs
  5. Filter to LOADABLE_STATUSES (tentative, established)
  6. Keep seeds + strict seed-anchored traversal via profile edge_types only
  7. Apply prefer_domains boost (×1.5)
  8. Apply exclude_domains filter
  9. Exclude nodes below confidence threshold
  10. Rank nodes by profile's rank_formula
  11. Cap at MAX_NODES_PER_LOADOUT
  12. Inject pitfall nodes (always included up to MAX_PITFALL_NODES)
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import networkx as nx

from akms.schema.models import (
    LOADABLE_STATUSES,
    AgentRole,
    EdgeType,
    LoadoutConfig,
    NodeStatus,
    PropagationConfig,
    QueryRoleProfile,
)
from akms.telemetry import traced

logger = logging.getLogger(__name__)


def _get_node_tags(G: nx.DiGraph, node_id: str) -> set[str]:
    """Get the tags for a node, returning empty set if not present."""
    tags = G.nodes[node_id].get("tags", [])
    if isinstance(tags, str):
        return {tags}
    return set(tags) if tags else set()


def _get_node_status(G: nx.DiGraph, node_id: str) -> str | None:
    """Get the status string for a node."""
    status = G.nodes[node_id].get("status")
    if isinstance(status, NodeStatus):
        return status.value
    return str(status) if status else None


def _get_node_domain(G: nx.DiGraph, node_id: str) -> str:
    """Get the domain string for a node."""
    return str(G.nodes[node_id].get("domain", ""))


def _get_node_confidence(G: nx.DiGraph, node_id: str) -> float:
    """Get the confidence value for a node."""
    conf = G.nodes[node_id].get("confidence", 0.0)
    return float(conf) if conf is not None else 0.0


def _get_node_activations(G: nx.DiGraph, node_id: str) -> int:
    """Get the activations count for a node."""
    act = G.nodes[node_id].get("activations", 0)
    return int(act) if act is not None else 0


def _compute_rank(
    G: nx.DiGraph,
    node_id: str,
    rank_formula: str,
) -> float:
    """Compute node rank from formula string.

    Supported formulas:
      - "confidence * activations"  (implementer/code_reviewer)
      - "confidence"                (physics_reviewer)
    """
    confidence = _get_node_confidence(G, node_id)
    activations = _get_node_activations(G, node_id)

    if rank_formula == "confidence * activations":
        # Use activations + 1 to avoid zero-ranking for never-used nodes
        return confidence * (activations + 1)
    elif rank_formula == "confidence":
        return confidence
    else:
        # Fallback: try to evaluate safely
        logger.warning("Unknown rank formula '%s', using confidence", rank_formula)
        return confidence


def _find_seed_nodes(
    G: nx.DiGraph,
    domain_tags: list[str],
) -> set[str]:
    """Find seed nodes whose tags intersect with domain_tags.

    Step 2 of the algorithm.
    """
    tag_set = set(domain_tags)
    seeds = set()

    for node_id in G.nodes:
        node_tags = _get_node_tags(G, node_id)
        if node_tags & tag_set:
            seeds.add(node_id)

    return seeds


def _extract_ego_union(
    G: nx.DiGraph,
    seeds: set[str],
    max_depth: int,
) -> set[str]:
    """Compute union of ego_graphs from all seed nodes.

    Steps 3-4 of the algorithm.
    Uses undirected ego_graph to follow edges in both directions.
    """
    union = set()
    G_undirected = G.to_undirected()

    for seed in seeds:
        if seed not in G:
            continue
        ego = nx.ego_graph(G_undirected, seed, radius=max_depth)
        union.update(ego.nodes)

    return union


def _filter_by_status(
    G: nx.DiGraph,
    candidates: set[str],
) -> set[str]:
    """Filter to LOADABLE_STATUSES (tentative, established).

    Step 5 of the algorithm.
    """
    loadable_values = {s.value for s in LOADABLE_STATUSES}
    return {n for n in candidates if _get_node_status(G, n) in loadable_values}


def _filter_edges_by_type(
    G: nx.DiGraph,
    candidates: set[str],
    seeds: set[str],
    allowed_edge_types: list[str],
) -> set[str]:
    """Filter candidates with strict, seed-anchored allowed-edge traversal.

    Step 6 of the algorithm.
    Keeps all seed nodes plus nodes reachable from seeds via allowed edge
    types only. Traversal is undirected to match Step 3 ego extraction.
    """
    if not allowed_edge_types:
        return candidates

    if not candidates:
        return set()

    allowed = set(allowed_edge_types)
    candidate_set = set(candidates)
    seed_set = set(seeds) & candidate_set
    if not seed_set:
        return set()

    # Build adjacency over candidate nodes using only allowed edge types.
    adjacency: dict[str, set[str]] = {nid: set() for nid in candidate_set}

    for u, v, data in G.edges(data=True):
        if u not in candidate_set or v not in candidate_set:
            continue
        edge_type = data.get("type", "")
        if isinstance(edge_type, EdgeType):
            edge_type = edge_type.value
        if str(edge_type) in allowed:
            adjacency[u].add(v)
            adjacency[v].add(u)

    # Traverse from seeds through allowed-edge adjacency.
    reachable = set(seed_set)
    stack = list(seed_set)
    while stack:
        current = stack.pop()
        for neighbor in adjacency[current]:
            if neighbor not in reachable:
                reachable.add(neighbor)
                stack.append(neighbor)

    return reachable


def _find_pitfall_nodes(
    G: nx.DiGraph,
    candidates: set[str],
) -> set[str]:
    """Find nodes connected by pitfall edges within the candidate set.

    Pitfall-connected nodes get special treatment: always included
    regardless of rank, up to MAX_PITFALL_NODES.
    """
    pitfall_nodes = set()

    for u, v, data in G.edges(data=True):
        edge_type = data.get("type", "")
        if isinstance(edge_type, EdgeType):
            edge_type = edge_type.value
        if str(edge_type) == EdgeType.PITFALL.value:
            if u in candidates:
                pitfall_nodes.add(u)
            if v in candidates:
                pitfall_nodes.add(v)

    return pitfall_nodes


@traced("akms.query_subgraph")
def query_subgraph(
    G: nx.DiGraph,
    domain_tags: list[str],
    agent_role: AgentRole | str,
    config: PropagationConfig | None = None,
    max_depth: int = 2,
) -> list[tuple[str, dict[str, Any]]]:
    """Extract a ranked subgraph for loadout construction.

    Args:
        G: The compiled knowledge graph (from load_graph or build_graph).
        domain_tags: Tags to seed the search (e.g., ["taichi", "gpu"]).
        agent_role: The agent role selecting a query profile.
        config: PropagationConfig (uses defaults if None).
        max_depth: Maximum graph traversal depth from seeds.

    Returns:
        Ranked list of (node_id, node_data) tuples.
        Pitfall nodes are always included regardless of rank.
    """
    if config is None:
        config = PropagationConfig()

    # Normalize agent_role to string
    role_key = (
        agent_role.value if isinstance(agent_role, AgentRole) else str(agent_role)
    )

    # ── Step 1: Load query profile ───────────────────────────────────
    profile = config.query_roles.get(role_key)
    if profile is None:
        logger.warning(
            "No query profile for role '%s', using implementer defaults",
            role_key,
        )
        profile = config.query_roles.get("implementer", QueryRoleProfile())

    loadout_config = config.loadout
    max_nodes = loadout_config.max_nodes_per_loadout
    max_pitfall = loadout_config.max_pitfall_nodes
    min_confidence = loadout_config.min_confidence_threshold

    logger.info(
        "query_subgraph: role=%s, tags=%s, depth=%d, max_nodes=%d",
        role_key,
        domain_tags,
        max_depth,
        max_nodes,
    )

    # ── Step 2: Find seed nodes ──────────────────────────────────────
    seeds = _find_seed_nodes(G, domain_tags)
    logger.info("Found %d seed nodes for tags %s", len(seeds), domain_tags)

    if not seeds:
        logger.warning("No seed nodes found for tags %s", domain_tags)
        return []

    # ── Steps 3-4: Ego graph union ───────────────────────────────────
    candidates = _extract_ego_union(G, seeds, max_depth)
    logger.info("Ego union: %d candidates", len(candidates))

    # ── Step 5: Filter by loadable status ────────────────────────────
    candidates = _filter_by_status(G, candidates)
    logger.info("After status filter: %d candidates", len(candidates))

    # Session nodes are non-loadable by contract (FR-G11).
    candidates = {n for n in candidates if _get_node_domain(G, n) != "session"}
    logger.info("After session-domain exclusion: %d candidates", len(candidates))

    # ── Step 6: Strict seed-anchored traversal via allowed edge types ─
    if profile.edge_types:
        candidates = _filter_edges_by_type(G, candidates, seeds, profile.edge_types)
        logger.info("After edge type filter: %d candidates", len(candidates))

    # ── Step 12 (early): Identify pitfall nodes ──────────────────────
    # We identify them early so they're preserved through subsequent filters
    pitfall_nodes = _find_pitfall_nodes(G, candidates)
    logger.info("Pitfall nodes: %d", len(pitfall_nodes))

    # ── Step 7: Apply prefer_domains boost ───────────────────────────
    # (Applied during ranking, not filtering — just track which nodes get boost)
    prefer_domains = set(profile.prefer_domains)

    # ── Step 8: Apply exclude_domains filter ─────────────────────────
    if profile.exclude_domains:
        exclude = set(profile.exclude_domains)
        # Never exclude pitfall nodes
        candidates = {
            n
            for n in candidates
            if _get_node_domain(G, n) not in exclude or n in pitfall_nodes
        }
        logger.info("After domain exclusion: %d candidates", len(candidates))

    # ── Step 9: Exclude nodes below confidence threshold ─────────────
    # Pitfall nodes are exempt from confidence threshold
    candidates = {
        n
        for n in candidates
        if _get_node_confidence(G, n) >= min_confidence or n in pitfall_nodes
    }
    logger.info(
        "After confidence threshold (%.2f): %d candidates",
        min_confidence,
        len(candidates),
    )

    # ── Step 10: Rank nodes ──────────────────────────────────────────
    ranked = []
    for node_id in candidates:
        rank = _compute_rank(G, node_id, profile.rank_formula)

        # Step 7: Prefer domains boost (×1.5)
        if prefer_domains and _get_node_domain(G, node_id) in prefer_domains:
            rank *= 1.5

        ranked.append((node_id, rank))

    # Sort by rank descending, then by id for determinism
    ranked.sort(key=lambda x: (-x[1], x[0]))

    # ── Step 11: Cap at max_nodes ────────────────────────────────────
    # Separate pitfall nodes from regular nodes
    regular_ranked = [(nid, r) for nid, r in ranked if nid not in pitfall_nodes]
    pitfall_ranked = [(nid, r) for nid, r in ranked if nid in pitfall_nodes]

    # Cap pitfall nodes
    pitfall_ranked = pitfall_ranked[:max_pitfall]

    # Cap regular nodes (leaving room for pitfalls)
    regular_slots = max(0, max_nodes - len(pitfall_ranked))
    regular_ranked = regular_ranked[:regular_slots]

    # ── Step 12: Merge and return ────────────────────────────────────
    # Pitfall nodes come first (always included), then ranked regular nodes
    result_ids = [nid for nid, _ in pitfall_ranked] + [nid for nid, _ in regular_ranked]

    # Deduplicate while preserving order
    seen = set()
    unique_ids = []
    for nid in result_ids:
        if nid not in seen:
            seen.add(nid)
            unique_ids.append(nid)

    result = [(nid, dict(G.nodes[nid])) for nid in unique_ids]
    result = [
        (nid, data) for nid, data in result if _get_node_domain(G, nid) != "session"
    ]

    # ── FR-G10: load_with co-activation hints ────────────────────────
    # Promote nodes that selected nodes are flagged to co-load with.
    # These hints are *pragmatic* (almost-always-co-loaded) and, by spec,
    # are distinct from semantic edges — so they bypass the edge-type
    # traversal (Step 6) and confidence threshold (Step 9), like pitfalls.
    # Non-transitive: only one hop out from the already-selected nodes.
    selected_ids = {nid for nid, _ in result}
    loadable_values = {s.value for s in LOADABLE_STATUSES}
    coactivated_ids: set[str] = set()
    for nid, _ in result:
        hints = G.nodes[nid].get("load_with", []) or []
        if isinstance(hints, str):
            hints = [hints]
        for target in hints:
            target = str(target)
            if (
                target in G
                and target not in selected_ids
                and target not in coactivated_ids
                and _get_node_status(G, target) in loadable_values
                and _get_node_domain(G, target) != "session"
            ):
                coactivated_ids.add(target)

    # Append deterministically; tag the copied node_data so downstream
    # rendering (generate_loadout) can distinguish co-activated nodes.
    for target in sorted(coactivated_ids):
        data = dict(G.nodes[target])
        data["_coactivated"] = True
        result.append((target, data))

    logger.info(
        "query_subgraph result: %d nodes (%d pitfall, %d regular, %d co-activated)",
        len(result),
        len(pitfall_ranked),
        len(regular_ranked),
        len(coactivated_ids),
    )

    return result


def compute_query_hash(
    domain_tags: list[str],
    agent_role: str,
    max_depth: int,
) -> str:
    """Compute a deterministic hash for a query, used for caching.

    Args:
        domain_tags: Sorted list of tags.
        agent_role: Role string.
        max_depth: Traversal depth.

    Returns:
        SHA256 hex digest of the query parameters.
    """
    # Normalize and sort tags for determinism
    normalized_tags = sorted(set(t.lower().strip() for t in domain_tags))
    key = f"{','.join(normalized_tags)}|{agent_role}|{max_depth}"
    return hashlib.sha256(key.encode()).hexdigest()
