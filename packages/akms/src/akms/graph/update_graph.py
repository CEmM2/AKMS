"""update_graph.py — PCD/AgentMemory → Local State Mutations (§2.7 of system design).

Applies the persistent zone of Phase Completion Documents (or individual
AgentMemories) to the graph. Pure algorithmic mutation with deterministic
threshold-based dedup (token Jaccard + exact-id signal), no LLM calls.

**Writes exclusively to local_state.yaml and local-nodes/ — never touches
global node files.**

Mutation pipeline:
  1. Process nodes_used → confidence boost/decay + activations
  2. Propagate confidence hits to neighbors via edge weights
  3. Process pitfalls_discovered → local_edges
  4. Process new_knowledge → dedup check → local-nodes/
  5. Create session node entries
  6. Write local_state.yaml
  7. Call build_graph() to recompile graph.json
"""

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

import networkx as nx
import yaml

from akms import AKMS_SCHEMA_VERSION
from akms.graph.build_graph import build_graph, load_graph
from akms.schema.models import (
    AgentMemory,
    Coverage,
    EdgeType,
    ImpactOnNextPhase,
    NodeSource,
    NodeStatus,
    PCD,
    PropagationConfig,
)
from akms.schema.validators import parse_propagation_config
from akms.telemetry import traced

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Persistent Zone Extraction
# ═══════════════════════════════════════════════════════════════════════


def _extract_persistent_zone(source: AgentMemory | PCD | dict) -> dict:
    """Extract the persistent zone fields from an AgentMemory or PCD.

    Both types share the same persistent zone fields:
    nodes_used, nodes_missing, lessons, pitfalls_discovered, new_knowledge.
    """
    if isinstance(source, PCD):
        return source.extract_persistent_zone()
    elif isinstance(source, AgentMemory):
        return {
            "nodes_used": [n.model_dump() for n in source.nodes_used],
            "nodes_missing": [n.model_dump() for n in source.nodes_missing],
            "lessons": source.lessons.model_dump(),
            "pitfalls_discovered": [p.model_dump() for p in source.pitfalls_discovered],
            "new_knowledge": [k.model_dump() for k in source.new_knowledge],
        }
    elif isinstance(source, dict):
        # Already a persistent zone dict
        return source
    else:
        raise TypeError(f"Unsupported source type: {type(source)}")


def _get_source_id(source: AgentMemory | PCD | dict) -> str:
    """Get a unique identifier for the source (task_id or phase_id)."""
    if isinstance(source, AgentMemory):
        return source.task_id
    elif isinstance(source, PCD):
        return f"phase-{source.phase_id}"
    elif isinstance(source, dict):
        return str(source.get("task_id", source.get("phase_id", "unknown")))
    return "unknown"


# TaskStatus → SessionOutcome mapping (used when we only have a status string).
# Shared between the AgentMemory branch and the dict branch of _create_session_node
# so MCP callers that forward AgentMemory frontmatter as a dict get the same outcome
# a typed AgentMemory would produce.
_STATUS_TO_OUTCOME: dict[str, str] = {
    "complete": "success",
    "partial": "partial",
    "failed": "failed",
    "deferred": "partial",
}


def _status_to_outcome(status: str | None) -> str:
    """Map a TaskStatus string to a SessionOutcome string. Unknown → 'partial'."""
    if status is None:
        return "partial"
    return _STATUS_TO_OUTCOME.get(str(status), "partial")


def _get_source_phase(source: AgentMemory | PCD | dict) -> int:
    """Get the phase number from the source."""
    if isinstance(source, AgentMemory):
        return source.phase_id
    elif isinstance(source, PCD):
        return source.phase_id
    elif isinstance(source, dict):
        return source.get("phase_id", 0)
    return 0




def _process_nodes_used(
    G: nx.DiGraph,
    overlay: dict,
    nodes_used: list[dict],
    config: PropagationConfig,
    source_id: str,
    today: date,
) -> list[dict]:
    """Process nodes_used feedback → confidence boost/decay + activations.

    Mutation rules per spec §2.7:
    - useful == true → boost confidence by activation_boost
    - coverage == missing-detail → apply local_decay
    - coverage == outdated → apply local_decay
    - auto_update == true → skip entirely
    - Clamp to [confidence_floor, max_confidence]

    Returns list of mutation events for logging.
    """
    conf_config = config.confidence
    events = []

    nodes_section = overlay.setdefault("nodes", {})

    for feedback in nodes_used:
        node_id = feedback["id"]

        # Check if node exists in graph
        if node_id not in G:
            logger.warning("Node '%s' from nodes_used not in graph — skipping", node_id)
            continue

        node_data = G.nodes[node_id]

        # Skip auto_update nodes (code-mirror, session nodes)
        if node_data.get("auto_update", False):
            logger.debug("Skipping auto_update node '%s'", node_id)
            continue

        # Get or create overlay entry
        node_overlay = nodes_section.setdefault(node_id, {})

        # Current confidence: overlay value > graph value > 0.0
        current_conf = node_overlay.get(
            "confidence",
            node_data.get("confidence", 0.0),
        )

        # Determine confidence floor
        conf_floor = node_data.get("confidence_floor")
        if conf_floor is None:
            conf_floor = conf_config.min_confidence

        useful = feedback.get("useful", False)
        coverage = feedback.get("coverage", "sufficient")

        new_conf = current_conf

        if useful:
            # Boost
            new_conf = current_conf + conf_config.activation_boost
            events.append({
                "node_id": node_id,
                "action": "boost",
                "old": current_conf,
                "new": new_conf,
                "reason": f"useful=true from {source_id}",
            })

        if coverage in ("missing-detail", "outdated"):
            # Decay
            new_conf = new_conf * conf_config.local_decay
            events.append({
                "node_id": node_id,
                "action": "decay",
                "old": current_conf,
                "new": new_conf,
                "reason": f"coverage={coverage} from {source_id}",
            })

        # Clamp to [confidence_floor, max_confidence]
        new_conf = max(conf_floor, min(conf_config.max_confidence, new_conf))

        node_overlay["confidence"] = round(new_conf, 6)

        # Increment activations
        activations = node_overlay.get("activations", node_data.get("activations", 0))
        node_overlay["activations"] = activations + 1

        # Update last_activated
        node_overlay["last_activated"] = str(today)

        # Update activated_by_tasks
        activated_by = node_overlay.get(
            "activated_by_tasks",
            list(node_data.get("activated_by_tasks", [])),
        )
        if source_id not in activated_by:
            activated_by.append(source_id)
        node_overlay["activated_by_tasks"] = activated_by

        # Update session_refs
        session_refs = node_overlay.get(
            "session_refs",
            list(node_data.get("session_refs", [])),
        )
        session_ref = f"sessions/{source_id}.md"
        if session_ref not in session_refs:
            session_refs.append(session_ref)
        node_overlay["session_refs"] = session_refs

    return events




def _propagate_to_neighbors(
    G: nx.DiGraph,
    overlay: dict,
    mutation_events: list[dict],
    config: PropagationConfig,
) -> list[dict]:
    """Propagate confidence hits to predecessor nodes via edge weights.

    For each decayed node, propagate to predecessors:
      hit = propagation_factor × edge_type_multiplier × decay_magnitude
    Limited by hop_limit (default 1).

    contradicts, pitfall, implements edges have multiplier 0.0 (no propagation).

    Returns list of propagation events for logging.
    """
    conf_config = config.confidence
    edge_multipliers = config.edge_type_propagation
    nodes_section = overlay.setdefault("nodes", {})
    prop_events = []

    # Only propagate from decay events
    decay_events = [e for e in mutation_events if e["action"] == "decay"]

    for event in decay_events:
        node_id = event["node_id"]
        decay_magnitude = abs(event["old"] - event["new"])

        if decay_magnitude < 1e-6:
            continue

        # Find predecessors (nodes that have edges TO this node)
        predecessors = list(G.predecessors(node_id))

        for pred_id in predecessors:
            pred_data = G.nodes.get(pred_id, {})

            # Skip auto_update nodes
            if pred_data.get("auto_update", False):
                continue

            # Get edge data
            edge_data = G.edges.get((pred_id, node_id), {})
            edge_type = edge_data.get("type", "")
            if isinstance(edge_type, EdgeType):
                edge_type = edge_type.value
            edge_type = str(edge_type)
            edge_weight = float(edge_data.get("weight", 1.0))

            # Get multiplier for this edge type
            multiplier = edge_multipliers.get(edge_type, 0.0)
            if multiplier <= 0.0:
                continue

            # Compute propagated hit
            hit = (
                conf_config.propagation_factor
                * multiplier
                * edge_weight
                * decay_magnitude
            )

            if hit < 1e-6:
                continue

            # Get current pred confidence
            pred_overlay = nodes_section.setdefault(pred_id, {})
            current_conf = pred_overlay.get(
                "confidence",
                pred_data.get("confidence", 0.0),
            )

            # Determine confidence floor
            conf_floor = pred_data.get("confidence_floor")
            if conf_floor is None:
                conf_floor = conf_config.min_confidence

            # Apply decay propagation
            new_conf = current_conf - hit
            new_conf = max(conf_floor, min(conf_config.max_confidence, new_conf))

            pred_overlay["confidence"] = round(new_conf, 6)

            prop_events.append({
                "node_id": pred_id,
                "action": "propagated_decay",
                "from_node": node_id,
                "edge_type": edge_type,
                "edge_weight": edge_weight,
                "multiplier": multiplier,
                "hit": round(hit, 6),
                "old": current_conf,
                "new": new_conf,
            })

    return prop_events




def _process_pitfalls(
    overlay: dict,
    pitfalls: list[dict],
    session_node_id: str,
    source_id: str = "",
) -> list[dict]:
    """Process pitfalls_discovered → local_edges.

    Each pitfall with a node_ref creates a pitfall edge:
      node_ref → session_node_id (type: pitfall)

    Edges are deduplicated by the composite key
    ``(from, to, note, source_id)``. Two different source_ids that cite the
    same pitfall on the same node still produce distinct edges (NFR-C05:
    additive pitfall evidence), but a replay of the same source_id does not.

    Returns list of pitfall events (including skipped-duplicate markers).
    """
    local_edges = overlay.setdefault("local_edges", [])
    existing_keys = {
        (
            str(e.get("from", "")),
            str(e.get("to", "")),
            str(e.get("note", "")),
            str(e.get("source_id", "")),
        )
        for e in local_edges
        if isinstance(e, dict) and e.get("type") == "pitfall"
    }
    events = []

    for pitfall in pitfalls:
        node_ref = pitfall.get("node_ref")
        if not node_ref:
            # Pitfall without node_ref — no edge to create
            # (The pitfall is still recorded in lessons/session notes)
            continue

        description = pitfall.get("description", "")
        severity = pitfall.get("severity", "medium")
        key = (str(node_ref), str(session_node_id), str(description), str(source_id))

        if key in existing_keys:
            events.append({
                "action": "pitfall_edge_duplicate_skipped",
                "from": node_ref,
                "to": session_node_id,
                "description": description,
                "source_id": source_id,
            })
            continue

        edge = {
            "from": node_ref,
            "to": session_node_id,
            "type": "pitfall",
            "weight": 0.8 if severity == "high" else 0.5,
            "note": description,
            "source_id": source_id,
        }

        local_edges.append(edge)
        existing_keys.add(key)
        events.append({
            "action": "pitfall_edge",
            "from": node_ref,
            "to": session_node_id,
            "description": description,
            "source_id": source_id,
        })

    return events


def _create_session_node(
    overlay: dict,
    source_id: str,
    source: AgentMemory | PCD | dict,
    phase: int,
) -> str:
    """Create a session node entry in local_state.yaml.

    PCDs create one session node per phase; AgentMemories create one per task.
    Returns the session node id.
    """
    session_nodes = overlay.setdefault("session_nodes", {})
    session_id = f"session-{source_id}"

    if session_id in session_nodes:
        logger.debug("Session node '%s' already exists", session_id)
        return session_id

    # Determine title and outcome
    if isinstance(source, AgentMemory):
        title = f"Session: {source.task_id} — {source.task_description}"
        status = source.status.value if hasattr(source.status, "value") else str(source.status)
        outcome = _status_to_outcome(status)
        tags = [f"phase{phase}"]
        content_ref = f"sessions/{source.task_id}.md"
    elif isinstance(source, PCD):
        title = f"Session: Phase {source.phase_id}"
        tags = [f"phase{phase}"]
        content_ref = f"sessions/handoff_phase_{phase}.md"
        # Determine outcome from overall test status
        if source.overall_test_status:
            if source.overall_test_status.dedicated_passing == source.overall_test_status.dedicated_total:
                outcome = "success"
            else:
                outcome = "partial"
        else:
            outcome = "partial"
    elif isinstance(source, dict):
        title = f"Session: {source_id}"
        #   # Prefer explicit outcome if caller set it; otherwise derive from status.
        #           # MCP callers that forward AgentMemory frontmatter as a dict carry
        #           # `status` but no `outcome`; defaulting to 'partial' here would mark
        #           # every completed task partial.
        if "outcome" in source:
            outcome = source["outcome"]
        else:
            outcome = _status_to_outcome(source.get("status"))
        tags = [f"phase{phase}"]
        content_ref = f"sessions/{source_id}.md"
    else:
        title = f"Session: {source_id}"
        outcome = "partial"
        tags = [f"phase{phase}"]
        content_ref = f"sessions/{source_id}.md"

    session_nodes[session_id] = {
        "title": title,
        "tags": tags,
        "outcome": outcome,
        "content_ref": content_ref,
        "phase": phase,
    }

    logger.info("Created session node: %s", session_id)
    return session_id


def _process_new_knowledge(
    G: nx.DiGraph,
    repo_root: Path,
    new_knowledge: list[dict],
    config: PropagationConfig,
) -> list[dict]:
    """Process new_knowledge → dedup check → create in local-nodes/.

    Dedup algorithm per spec §2.7:
    1. Fetch all tentative nodes in same domain
    2. Score lexical similarity (token Jaccard) with exact-id hard match
    3. If match > threshold: append content_draft to existing node
    4. Else: create new tentative node in local-nodes/

    This implementation uses deterministic lexical similarity (token Jaccard)
    plus exact-id matching, making dedup_threshold operational without LLMs.

    Returns list of knowledge events.
    """
    events = []
    local_nodes_dir = repo_root / "knowledge" / "local-nodes"
    local_nodes_dir.mkdir(parents=True, exist_ok=True)

    dedup_threshold = config.graph.dedup_threshold

    def _tokenize(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9]+", text.lower()))

    def _safe_load_markdown_content(path: Path) -> str:
        try:
            import frontmatter as fm
            post = fm.load(str(path))
            return str(post.content or "")
        except Exception:
            try:
                return path.read_text()
            except Exception:
                return ""

    def _score_similarity(
        *,
        suggested_id: str,
        new_title: str,
        new_content: str,
        candidate_id: str,
        candidate_title: str,
        candidate_content: str,
    ) -> float:
        # Exact-id remains a hard dedup signal.
        if suggested_id and suggested_id == candidate_id:
            return 1.0

        lhs = _tokenize(f"{new_title}\n{new_content}")
        rhs = _tokenize(f"{candidate_title}\n{candidate_content}")
        if not lhs or not rhs:
            return 0.0

        intersection = lhs & rhs
        union = lhs | rhs
        return len(intersection) / len(union)

    def _collect_tentative_candidates() -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []

        # Local tentative nodes from local-nodes/ with appendable file paths.
        for local_path in sorted(local_nodes_dir.glob("**/*.md")):
            try:
                import frontmatter as fm
                post = fm.load(str(local_path))
                metadata = dict(post.metadata)
            except Exception:
                continue

            status = str(metadata.get("status", ""))
            if status != "tentative":
                continue

            candidates.append({
                "node_id": str(metadata.get("id", local_path.stem)),
                "domain": str(metadata.get("domain", "")),
                "title": str(metadata.get("title", "")),
                "content": str(post.content or ""),
                "origin": "local",
                "path": local_path,
            })

        # Global tentative nodes from graph (cannot be appended in place).
        for node_id, node_data in G.nodes(data=True):
            status = node_data.get("status", "")
            if isinstance(status, NodeStatus):
                status = status.value
            if str(status) != "tentative":
                continue

            origin = str(node_data.get("node_origin", ""))
            if origin == "local":
                # Already represented by file-backed candidates above.
                continue

            content_ref = node_data.get("content_ref")
            candidate_content = ""
            if content_ref:
                content_ref_path = Path(str(content_ref))
                search_paths = [content_ref_path, repo_root / content_ref_path]
                for p in search_paths:
                    if p.exists():
                        candidate_content = _safe_load_markdown_content(p)
                        break

            candidates.append({
                "node_id": node_id,
                "domain": str(node_data.get("domain", "")),
                "title": str(node_data.get("title", "")),
                "content": candidate_content,
                "origin": "global",
            })

        return candidates

    for entry in new_knowledge:
        suggested_id = entry.get("suggested_id", "")
        if not suggested_id:
            continue

        domain = entry.get("domain", "")
        title = entry.get("title", suggested_id)
        content_draft = entry.get("content_draft", "")
        tags = entry.get("tags", [])

        # ── Dedup check ──────────────────────────────────────────────
        matched_existing = False
        tentative_candidates = _collect_tentative_candidates()
        if domain:
            tentative_candidates = [
                c for c in tentative_candidates
                if c.get("domain") == domain
            ]

        best_match: dict[str, Any] | None = None
        best_score = 0.0
        for candidate in tentative_candidates:
            score = _score_similarity(
                suggested_id=suggested_id,
                new_title=title,
                new_content=content_draft,
                candidate_id=str(candidate.get("node_id", "")),
                candidate_title=str(candidate.get("title", "")),
                candidate_content=str(candidate.get("content", "")),
            )
            if score > best_score:
                best_score = score
                best_match = candidate

        if best_match is not None and best_score > dedup_threshold:
            match_id = str(best_match.get("node_id", ""))
            if best_match.get("origin") == "local":
                local_path = Path(best_match["path"])
                try:
                    import frontmatter as fm
                    post = fm.load(str(local_path))
                    post.content += f"\n\n---\n\n{content_draft}"
                    with open(local_path, "wb") as f:
                        fm.dump(post, f)
                    events.append({
                        "action": "dedup_append",
                        "node_id": match_id,
                        "merged_into": match_id,
                        "score": round(best_score, 6),
                        "threshold": dedup_threshold,
                        "reason": "similarity exceeded dedup_threshold",
                    })
                    matched_existing = True
                except Exception as e:
                    logger.warning("Failed to append to %s: %s", local_path, e)
            else:
                # Cannot modify global tentative node — create local variant.
                suggested_id = f"{match_id}-local"
                events.append({
                    "action": "dedup_global_skip",
                    "node_id": suggested_id,
                    "merged_into": match_id,
                    "score": round(best_score, 6),
                    "threshold": dedup_threshold,
                    "reason": "best dedup match is global tentative node",
                })

        if not matched_existing:
            # ── Create new tentative node ────────────────────────────
            node_path = local_nodes_dir / f"{suggested_id}.md"
            if node_path.exists():
                suffix = 1
                while True:
                    candidate_id = f"{suggested_id}-{suffix}"
                    candidate_path = local_nodes_dir / f"{candidate_id}.md"
                    if not candidate_path.exists():
                        suggested_id = candidate_id
                        node_path = candidate_path
                        break
                    suffix += 1

            frontmatter_data = {
                "id": suggested_id,
                "title": title,
                "domain": domain,
                "tags": tags if tags else [domain],
                "status": "tentative",
                "confidence": 0.50,
                "source": "agent",
                "edges": [],
                "akms_schema": AKMS_SCHEMA_VERSION,
            }

            try:
                import frontmatter as fm
                post = fm.Post(content_draft)
                post.metadata = frontmatter_data
                node_path.parent.mkdir(parents=True, exist_ok=True)
                with open(node_path, "wb") as f:
                    fm.dump(post, f)

                events.append({
                    "action": "new_node",
                    "node_id": suggested_id,
                    "domain": domain,
                    "path": str(node_path),
                })
            except Exception as e:
                logger.error("Failed to create node %s: %s", suggested_id, e)

    return events




def _prune_session_refs(overlay: dict, max_refs: int) -> None:
    """Prune session_refs to max_session_refs most recent entries."""
    nodes_section = overlay.get("nodes", {})
    for _node_id, node_data in nodes_section.items():
        refs = node_data.get("session_refs", [])
        if len(refs) > max_refs:
            node_data["session_refs"] = refs[-max_refs:]


def _write_overlay(overlay: dict, overlay_path: Path) -> None:
    """Write local_state.yaml from overlay dict."""
    overlay_path.parent.mkdir(parents=True, exist_ok=True)
    with open(overlay_path, "w") as f:
        yaml.dump(overlay, f, default_flow_style=False, sort_keys=True)
    logger.info("Wrote local_state.yaml: %s", overlay_path)


def _load_overlay(overlay_path: Path) -> dict:
    """Load existing local_state.yaml or return empty overlay."""
    if overlay_path.exists():
        with open(overlay_path) as f:
            data = yaml.safe_load(f)
        if data is None:
            data = {}
        return data

    return {
        "akms_schema": AKMS_SCHEMA_VERSION,
        "repo_id": "",
        "nodes": {},
        "local_edges": [],
        "session_nodes": {},
        "suppressed_edges": [],
    }


# ═══════════════════════════════════════════════════════════════════════
#  Main Entry Point
# ═══════════════════════════════════════════════════════════════════════


@traced("akms.update_graph")
def update_graph(
    source: AgentMemory | PCD | dict,
    repo_root: str | Path,
    config: PropagationConfig | None = None,
    global_vault: str | Path | None = None,
    recompile: bool = True,
) -> dict:
    """Apply persistent zone mutations from a PCD or AgentMemory to the graph.

    This is the main entry point for Phase 4. It:
    1. Loads the current compiled graph
    2. Processes nodes_used → confidence mutations
    3. Propagates decay to neighbors
    4. Processes pitfalls → local_edges
    5. Creates session node entry
    6. Processes new_knowledge → local-nodes/
    7. Writes local_state.yaml
    8. Recompiles graph.json via build_graph()

    Args:
        source: AgentMemory, PCD, or persistent zone dict.
        repo_root: Path to the repository root.
        config: PropagationConfig (loads from file or uses defaults if None).
        global_vault: Override path to global vault.
        recompile: Whether to call build_graph() after mutations. Default True.

    Returns:
        Dict with mutation summary:
        {
            "confidence_events": [...],
            "propagation_events": [...],
            "pitfall_events": [...],
            "knowledge_events": [...],
            "session_node_id": str,
        }
    """
    repo_root = Path(repo_root)
    knowledge_dir = repo_root / "knowledge"
    graph_dir = knowledge_dir / "graph"
    overlay_path = graph_dir / "local_state.yaml"
    graph_json = graph_dir / "graph.json"

    # Load config
    if config is None:
        config_path = graph_dir / "propagation_config.yaml"
        if config_path.exists():
            config = parse_propagation_config(config_path)
        else:
            config = PropagationConfig()

    # Load compiled graph
    if graph_json.exists():
        G = load_graph(graph_json)
    else:
        # Build first if no graph exists
        G = build_graph(repo_root, global_vault=global_vault)

    # Load overlay
    overlay = _load_overlay(overlay_path)

    # Ensure required sections exist
    overlay.setdefault("akms_schema", AKMS_SCHEMA_VERSION)
    overlay.setdefault("nodes", {})
    overlay.setdefault("local_edges", [])
    overlay.setdefault("session_nodes", {})
    overlay.setdefault("suppressed_edges", [])

    # Extract persistent zone
    persistent = _extract_persistent_zone(source)
    source_id = _get_source_id(source)
    phase = _get_source_phase(source)
    today = date.today()

    # Replay ledger — same source_id applied twice is a no-op
    # (NFR-D03). Check before mutating anything; append post-commit. If the
    # ledger is missing (legacy overlay files), treat as empty and continue.
    processed_sources: list[str] = list(overlay.get("processed_sources") or [])
    if source_id and source_id in processed_sources:
        logger.info(
            "update_graph: source_id=%r already processed — no-op (replay ledger)",
            source_id,
        )
        return {
            "confidence_events": [],
            "propagation_events": [],
            "pitfall_events": [],
            "knowledge_events": [],
            "session_node_id": f"session-{source_id}",
            "replayed": True,
        }

    logger.info("update_graph: processing %s (phase %d)", source_id, phase)

    confidence_events = _process_nodes_used(
        G, overlay, persistent.get("nodes_used", []),
        config, source_id, today,
    )

    propagation_events = _propagate_to_neighbors(
        G, overlay, confidence_events, config,
    )

    session_node_id = _create_session_node(overlay, source_id, source, phase)

    pitfall_events = _process_pitfalls(
        overlay, persistent.get("pitfalls_discovered", []),
        session_node_id, source_id=source_id,
    )

    knowledge_events = _process_new_knowledge(
        G, repo_root, persistent.get("new_knowledge", []),
        config,
    )

    # Persist review/report categories consumed by graph_status().
    coverage_flags = overlay.setdefault("coverage_flags", [])
    for feedback in persistent.get("nodes_used", []):
        coverage_val = feedback.get("coverage", "")
        if isinstance(coverage_val, Coverage):
            coverage = coverage_val.value
        else:
            coverage = str(coverage_val)
        if coverage not in (Coverage.MISSING_DETAIL.value, Coverage.OUTDATED.value):
            continue
        coverage_flags.append({
            "node_id": str(feedback.get("id", "")),
            "coverage": coverage,
            "source_id": source_id,
            "phase": phase,
            "date": str(today),
        })

    dedup_events = overlay.setdefault("dedup_events", [])
    for event in knowledge_events:
        action = str(event.get("action", ""))
        if action not in ("dedup_append", "dedup_global_skip"):
            continue
        dedup_events.append({
            "action": action,
            "merged_into": str(event.get("merged_into", event.get("node_id", ""))),
            "node_id": str(event.get("node_id", "")),
            "score": event.get("score"),
            "threshold": event.get("threshold"),
            "source_id": source_id,
            "phase": phase,
            "date": str(today),
        })

    blocked_tasks = overlay.setdefault("blocked_tasks", [])
    if isinstance(source, dict):
        for item in source.get("blocked_tasks", []):
            if isinstance(item, dict):
                blocked_tasks.append(dict(item))
            elif isinstance(item, str):
                blocked_tasks.append({"task": item})
    elif isinstance(source, PCD):
        for issue in source.known_issues.failing_tests:
            if issue.impact_on_next_phase != ImpactOnNextPhase.BLOCKING:
                continue
            blocked_tasks.append({
                "task": issue.tests,
                "reason": issue.reason,
                "source_id": source_id,
                "phase": phase,
                "date": str(today),
            })

    _prune_session_refs(overlay, config.graph.max_session_refs)

    # Append to the replay ledger post-commit so a crash mid-
    # write leaves the ledger intact and a clean retry can re-execute.
    if source_id and source_id not in processed_sources:
        processed_sources.append(source_id)
        overlay["processed_sources"] = processed_sources

    # Write overlay
    _write_overlay(overlay, overlay_path)

    # Recompile graph
    if recompile:
        build_graph(repo_root, global_vault=global_vault)
        logger.info("Graph recompiled after update")

    summary = {
        "confidence_events": confidence_events,
        "propagation_events": propagation_events,
        "pitfall_events": pitfall_events,
        "knowledge_events": knowledge_events,
        "session_node_id": session_node_id,
    }

    logger.info(
        "update_graph complete: %d confidence, %d propagation, "
        "%d pitfall, %d knowledge events",
        len(confidence_events),
        len(propagation_events),
        len(pitfall_events),
        len(knowledge_events),
    )

    return summary
