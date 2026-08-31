"""graph_status.py — Health Check & Review Report (§2.8 of system design).

Read-only health check tool. Run on demand or as part of review cycle.

Reports:
  - Degraded nodes (confidence < 0.5)
  - Coverage flags (missing-detail, outdated)
  - Tentative nodes awaiting promotion
  - Dedup events persisted in local overlay history
  - Blocked downstream tasks
  - Id collisions between global and local nodes
  - Orphaned nodes (no edges)
  - Stale nodes (last_activated > N days)
  - Orphaned overlay entries
  - Docstring drift warnings (consumed from generate_mirror output)

Does NOT modify anything — pure read-only reporting.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import frontmatter
import networkx as nx
import yaml

from akms.graph.build_graph import build_graph, load_graph, resolve_global_vault
from akms.schema.models import NodeStatus, PropagationConfig
from akms.schema.validators import parse_propagation_config
from akms.telemetry import traced

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Individual Check Functions
# ═══════════════════════════════════════════════════════════════════════


def _check_degraded_nodes(
    G: nx.DiGraph,
    overlay: dict,
    threshold: float = 0.5,
) -> list[dict]:
    """Find nodes with confidence below threshold.

    Shows both graph-level confidence and overlay override.
    """
    degraded = []
    overlay_nodes = overlay.get("nodes", {})

    for node_id, data in G.nodes(data=True):
        graph_conf = data.get("confidence", 0.0)
        overlay_entry = overlay_nodes.get(node_id, {})
        overlay_conf = overlay_entry.get("confidence")
        effective_conf = overlay_conf if overlay_conf is not None else graph_conf

        if effective_conf < threshold:
            degraded.append(
                {
                    "node_id": node_id,
                    "graph_confidence": graph_conf,
                    "overlay_confidence": overlay_conf,
                    "effective_confidence": effective_conf,
                    "origin": data.get("node_origin", "unknown"),
                }
            )

    return sorted(degraded, key=lambda x: x["effective_confidence"])


def _load_content_draft(
    node_id: str,
    data: dict,
    repo_root: Path | None,
    local_nodes_dir: Path | None,
    max_chars: int,
) -> str:
    """Load the markdown body (content_draft) for a node, truncated to a preview.

    FR-R05: the review interface SHOULD show the agent-written content_draft
    inline for quick inspection. The draft is the node's markdown body (the
    text after the YAML frontmatter), persisted by update_graph.py. Resolves
    the node file via its content_ref first, then local-nodes/<id>.md.
    Returns "" when no body can be located.
    """
    candidates: list[Path] = []
    content_ref = data.get("content_ref")
    if content_ref:
        candidates.append(Path(str(content_ref)))
        if repo_root is not None:
            candidates.append(repo_root / str(content_ref))
    if local_nodes_dir is not None:
        candidates.append(local_nodes_dir / f"{node_id}.md")

    for path in candidates:
        if not path.exists():
            continue
        try:
            post = frontmatter.load(str(path))
            body = (post.content or "").strip()
        except Exception:
            try:
                body = path.read_text(encoding="utf-8").strip()
            except Exception:
                continue
        if body:
            if len(body) > max_chars:
                return body[:max_chars].rstrip() + " …[truncated]"
            return body

    return ""


def _check_tentative_nodes(
    G: nx.DiGraph,
    repo_root: Path | None = None,
    local_nodes_dir: Path | None = None,
    draft_preview_chars: int = 600,
) -> list[dict]:
    """Find tentative nodes awaiting promotion.

    When ``repo_root`` / ``local_nodes_dir`` are provided, each entry also
    carries a ``content_draft`` preview (FR-R05) loaded from the node body.
    """
    tentative = []
    for node_id, data in G.nodes(data=True):
        status = data.get("status", "")
        if isinstance(status, NodeStatus):
            status = status.value
        if str(status) == "tentative":
            tentative.append(
                {
                    "node_id": node_id,
                    "origin": data.get("node_origin", "unknown"),
                    "domain": data.get("domain", ""),
                    "confidence": data.get("confidence", 0.0),
                    "content_draft": _load_content_draft(
                        node_id,
                        data,
                        repo_root,
                        local_nodes_dir,
                        draft_preview_chars,
                    ),
                }
            )

    return sorted(tentative, key=lambda x: x["node_id"])


def _check_id_collisions(
    global_vault: Path,
    local_nodes_dir: Path,
) -> list[dict]:
    """Detect id collisions between global and local nodes."""
    collisions: list[dict] = []
    global_paths_by_id: dict[str, list[Path]] = {}
    local_paths_by_id: dict[str, list[Path]] = {}

    if global_vault.exists():
        for md in sorted(global_vault.glob("**/*.md")):
            global_paths_by_id.setdefault(md.stem, []).append(md)

    if local_nodes_dir.exists():
        for md in sorted(local_nodes_dir.glob("**/*.md")):
            local_paths_by_id.setdefault(md.stem, []).append(md)

    for node_id in sorted(global_paths_by_id.keys() & local_paths_by_id.keys()):
        for global_path in global_paths_by_id[node_id]:
            for local_path in local_paths_by_id[node_id]:
                collisions.append(
                    {
                        "node_id": node_id,
                        "global_path": str(global_path),
                        "local_path": str(local_path),
                    }
                )

    return collisions


def _check_orphaned_nodes(G: nx.DiGraph) -> list[dict]:
    """Find nodes with no edges (neither in nor out)."""
    orphaned = []
    for node_id in G.nodes():
        in_deg = G.in_degree(node_id)
        out_deg = G.out_degree(node_id)
        if in_deg == 0 and out_deg == 0:
            data = G.nodes[node_id]
            # Skip session nodes and code-mirror (expected to be orphaned)
            domain = data.get("domain", "")
            if domain in ("session", "code-mirror"):
                continue
            orphaned.append(
                {
                    "node_id": node_id,
                    "domain": domain,
                    "origin": data.get("node_origin", "unknown"),
                }
            )

    return sorted(orphaned, key=lambda x: x["node_id"])


def _check_stale_nodes(
    G: nx.DiGraph,
    overlay: dict,
    stale_days: int = 90,
    today: date | None = None,
) -> list[dict]:
    """Find nodes not activated within stale_days.

    Only checks nodes that HAVE a last_activated date (either in overlay or graph).
    Nodes never activated are not flagged as stale.
    """
    if today is None:
        today = date.today()

    cutoff = today - timedelta(days=stale_days)
    stale = []
    overlay_nodes = overlay.get("nodes", {})

    for node_id, data in G.nodes(data=True):
        # Skip auto_update nodes
        if data.get("auto_update", False):
            continue

        overlay_entry = overlay_nodes.get(node_id, {})
        last_activated = overlay_entry.get("last_activated") or data.get(
            "last_activated"
        )

        if last_activated is None:
            continue

        if isinstance(last_activated, str):
            try:
                last_activated = date.fromisoformat(last_activated)
            except ValueError:
                continue

        if last_activated < cutoff:
            stale.append(
                {
                    "node_id": node_id,
                    "last_activated": str(last_activated),
                    "days_inactive": (today - last_activated).days,
                    "domain": data.get("domain", ""),
                }
            )

    return sorted(stale, key=lambda x: x["days_inactive"], reverse=True)


def _check_orphaned_overlay_entries(
    G: nx.DiGraph,
    overlay: dict,
) -> list[dict]:
    """Find overlay entries for nodes no longer in the graph."""
    orphaned = []
    overlay_nodes = overlay.get("nodes", {})

    for node_id in overlay_nodes:
        if node_id not in G:
            orphaned.append(
                {
                    "node_id": node_id,
                    "overlay_data": overlay_nodes[node_id],
                }
            )

    return sorted(orphaned, key=lambda x: x["node_id"])


def _check_coverage_flags(overlay: dict) -> list[dict]:
    """Return nodes flagged missing-detail/outdated from overlay history."""
    flags = overlay.get("coverage_flags", [])
    if not isinstance(flags, list):
        return []

    normalized: list[dict] = []
    for item in flags:
        if not isinstance(item, dict):
            continue
        coverage = str(item.get("coverage", ""))
        if coverage not in ("missing-detail", "outdated"):
            continue
        normalized.append(
            {
                "node_id": str(item.get("node_id", "")),
                "coverage": coverage,
                "source_id": str(item.get("source_id", "")),
                "phase": item.get("phase"),
                "date": str(item.get("date", "")),
            }
        )

    return sorted(
        normalized,
        key=lambda x: (x.get("node_id", ""), x.get("date", ""), x.get("coverage", "")),
    )


def _check_dedup_events(overlay: dict) -> list[dict]:
    """Return recorded dedup events from overlay history."""
    events = overlay.get("dedup_events", [])
    if not isinstance(events, list):
        return []

    normalized: list[dict] = []
    for item in events:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "action": str(item.get("action", "")),
                "merged_into": str(item.get("merged_into", item.get("node_id", ""))),
                "node_id": str(item.get("node_id", "")),
                "source_id": str(item.get("source_id", "")),
                "phase": item.get("phase"),
                "date": str(item.get("date", "")),
                "score": item.get("score"),
                "threshold": item.get("threshold"),
            }
        )

    return sorted(
        normalized,
        key=lambda x: (
            x.get("date", ""),
            x.get("merged_into", ""),
            x.get("node_id", ""),
        ),
    )


def _check_blocked_tasks(
    overlay: dict,
    blocked_tasks: list[dict | str] | None = None,
) -> list[dict]:
    """Return blocked downstream tasks from explicit input or overlay."""
    raw: list[dict | str] = (
        blocked_tasks if blocked_tasks is not None else overlay.get("blocked_tasks", [])
    )
    if not isinstance(raw, list):
        return []

    normalized: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            normalized.append(
                {
                    "task": str(item.get("task", "")),
                    "reason": str(item.get("reason", "")),
                    "source_id": str(item.get("source_id", "")),
                    "phase": item.get("phase"),
                }
            )
        elif isinstance(item, str):
            normalized.append(
                {
                    "task": item,
                    "reason": "",
                    "source_id": "",
                    "phase": None,
                }
            )

    return sorted(normalized, key=lambda x: (x.get("task", ""), x.get("source_id", "")))


# ═══════════════════════════════════════════════════════════════════════
#  Report Formatting
# ═══════════════════════════════════════════════════════════════════════


def format_report(report: dict[str, Any]) -> str:
    """Format a health report as human-readable text."""
    lines = ["═══ AKMS Graph Health Report ═══", ""]

    # Degraded nodes
    degraded = report.get("degraded_nodes", [])
    lines.append(f"## Degraded Nodes (confidence < 0.5): {len(degraded)}")
    for d in degraded:
        overlay_str = (
            f" (overlay: {d['overlay_confidence']:.2f})"
            if d.get("overlay_confidence") is not None
            else ""
        )
        lines.append(
            f"  - {d['node_id']}: {d['effective_confidence']:.2f}{overlay_str} [{d['origin']}]"
        )
    lines.append("")

    # Tentative
    tentative = report.get("tentative_nodes", [])
    lines.append(f"## Tentative Nodes Awaiting Promotion: {len(tentative)}")
    for t in tentative:
        lines.append(
            f"  - {t['node_id']} ({t['origin']}, domain={t['domain']}, conf={t['confidence']:.2f})"
        )
        # FR-R05: show the agent-written content_draft inline for quick review.
        draft = t.get("content_draft", "")
        if draft:
            lines.append("    ┌─ content_draft ─────────────────────────────")
            for draft_line in draft.splitlines():
                lines.append(f"    │ {draft_line}")
            lines.append("    └─────────────────────────────────────────────")
    lines.append("")

    # Id collisions
    collisions = report.get("id_collisions", [])
    lines.append(f"## Id Collisions: {len(collisions)}")
    for c in collisions:
        lines.append(f"  - {c['node_id']}: global + local both exist")
    lines.append("")

    # Orphaned nodes
    orphaned = report.get("orphaned_nodes", [])
    lines.append(f"## Orphaned Nodes (no edges): {len(orphaned)}")
    for o in orphaned:
        lines.append(f"  - {o['node_id']} ({o['domain']}, {o['origin']})")
    lines.append("")

    # Stale nodes
    stale = report.get("stale_nodes", [])
    lines.append(f"## Stale Nodes: {len(stale)}")
    for s in stale:
        lines.append(
            f"  - {s['node_id']}: {s['days_inactive']} days inactive (last: {s['last_activated']})"
        )
    lines.append("")

    # Orphaned overlay
    orphaned_overlay = report.get("orphaned_overlay_entries", [])
    lines.append(f"## Orphaned Overlay Entries: {len(orphaned_overlay)}")
    for o in orphaned_overlay:
        lines.append(f"  - {o['node_id']}: in overlay but not in graph")
    lines.append("")

    # Coverage flags
    coverage_flags = report.get("coverage_flags", [])
    lines.append(f"## Coverage Flags (missing-detail/outdated): {len(coverage_flags)}")
    for c in coverage_flags:
        phase_note = f", phase={c['phase']}" if c.get("phase") is not None else ""
        lines.append(
            f"  - {c['node_id']}: {c['coverage']} (source={c.get('source_id', '?')}{phase_note})"
        )
    lines.append("")

    # Dedup events
    dedup_events = report.get("dedup_events", [])
    lines.append(f"## Dedup Events: {len(dedup_events)}")
    for d in dedup_events:
        score_note = ""
        if d.get("score") is not None and d.get("threshold") is not None:
            score_note = f" (score={d['score']}, threshold={d['threshold']})"
        lines.append(
            f"  - {d.get('action', 'dedup')} merged into {d.get('merged_into', '?')}{score_note}"
        )
    lines.append("")

    # Blocked tasks
    blocked_tasks = report.get("blocked_tasks", [])
    lines.append(f"## Blocked Downstream Tasks: {len(blocked_tasks)}")
    for b in blocked_tasks:
        reason = f": {b['reason']}" if b.get("reason") else ""
        lines.append(f"  - {b.get('task', '?')}{reason}")
    lines.append("")

    # Drift warnings
    drift = report.get("drift_warnings", [])
    lines.append(f"## Docstring Drift Warnings: {len(drift)}")
    for d in drift:
        lines.append(f"  - {d.get('file', '?')}::{d['function']}: {d['detail']}")
    lines.append("")

    # Mirror provider identity (A2-6) — non-secret only
    mp = report.get("mirror_provider") or {}
    if mp:
        lines.append("## Mirror Provider")
        lines.append(
            f"  - provider: {mp.get('resolved_provider') or mp.get('provider', 'legacy')}"
        )
        if "success" in mp:
            lines.append(f"  - last_refresh_success: {mp.get('success')}")
        if mp.get("fallback_used"):
            lines.append("  - fallback_used: true")
        for err in mp.get("errors") or []:
            if isinstance(err, dict):
                lines.append(
                    f"  - error: [{err.get('code', '?')}] {err.get('message', '')}"
                )
            else:
                lines.append(f"  - error: {err}")
        lines.append("")

    # Skipped files (malformed frontmatter surfaced by build_graph)
    skipped = report.get("skipped_files", [])
    lines.append(f"## Skipped Files: {len(skipped)}")
    for s in skipped:
        lines.append(f"  - {s.get('path', '?')}: {s.get('reason', '')}")
    lines.append("")

    # Summary
    total_issues = (
        len(degraded)
        + len(tentative)
        + len(collisions)
        + len(orphaned)
        + len(stale)
        + len(orphaned_overlay)
        + len(coverage_flags)
        + len(dedup_events)
        + len(blocked_tasks)
        + len(drift)
    )
    lines.append(f"## Summary: {total_issues} total issues")
    lines.append(f"  Nodes in graph: {report.get('total_nodes', 0)}")
    lines.append(f"  Edges in graph: {report.get('total_edges', 0)}")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
#  Main Entry Point
# ═══════════════════════════════════════════════════════════════════════


@traced("akms.graph_status")
def graph_status(
    repo_root: str | Path,
    global_vault: str | Path | None = None,
    config: PropagationConfig | None = None,
    drift_warnings: list[dict] | None = None,
    blocked_tasks: list[dict | str] | None = None,
    today: date | None = None,
    mirror_provider: dict[str, Any] | None = None,
    *,
    allow_graph_rebuild: bool = True,
) -> dict[str, Any]:
    """Run the full health check and return structured report.

    Args:
        repo_root: Path to the repository root.
        global_vault: Override global vault path.
        config: PropagationConfig (loads from file or defaults if None).
        drift_warnings: Pre-computed drift warnings (from generate_mirror).
        blocked_tasks: Optional blocked-task entries to include in report.
        today: Override date for stale check (for testing).
        mirror_provider: Optional non-secret mirror provider identity / last
            refresh status (A2-6). When omitted, derived from config.mirror.
        allow_graph_rebuild: When False, skip ``build_graph`` if graph.json is
            missing (used after a required mirror-provider failure so a partial
            mirror set cannot enter the graph).

    Returns:
        Dict with all check results.
    """
    repo_root = Path(repo_root)
    knowledge_dir = repo_root / "knowledge"
    graph_dir = knowledge_dir / "graph"
    graph_json = graph_dir / "graph.json"
    overlay_path = graph_dir / "local_state.yaml"

    # Load config
    if config is None:
        config_path = graph_dir / "propagation_config.yaml"
        if config_path.exists():
            config = parse_propagation_config(config_path)
        else:
            config = PropagationConfig()

    # Resolve global vault via shared helper (F-06 precedence).
    # Subsumes the earlier `.expanduser()` patch — the helper expands `~`
    # on every branch (explicit > env > config > default).
    vault_path = resolve_global_vault(explicit=global_vault, config=config)

    # Load graph — pass the resolved vault + config so a rebuild here sees
    # the exact same source tree the health checks will read.
    if graph_json.exists():
        G = load_graph(graph_json)
    elif allow_graph_rebuild:
        G = build_graph(repo_root, global_vault=vault_path, config=config)
    else:
        G = nx.DiGraph()
        G.graph["skipped_files"] = []
        logger.warning(
            "graph_status: graph.json missing and allow_graph_rebuild=False; "
            "returning empty graph diagnostics"
        )

    # Load overlay
    overlay: dict = {}
    if overlay_path.exists():
        with open(overlay_path) as f:
            overlay = yaml.safe_load(f) or {}

    local_nodes_dir = knowledge_dir / "local-nodes"

    # Provider identity (non-secret) for status surfaces.
    if mirror_provider is None:
        try:
            from akms.graph.mirror_provider import (
                public_provider_identity,
                resolve_mirror_config,
            )

            mirror_provider = public_provider_identity(resolve_mirror_config(config))
        except Exception:
            mirror_provider = {"provider": "legacy"}

    report = {
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "degraded_nodes": _check_degraded_nodes(G, overlay),
        "tentative_nodes": _check_tentative_nodes(G, repo_root, local_nodes_dir),
        "id_collisions": _check_id_collisions(vault_path, local_nodes_dir),
        "orphaned_nodes": _check_orphaned_nodes(G),
        "stale_nodes": _check_stale_nodes(
            G,
            overlay,
            config.graph.stale_node_days,
            today,
        ),
        "orphaned_overlay_entries": _check_orphaned_overlay_entries(G, overlay),
        "coverage_flags": _check_coverage_flags(overlay),
        "dedup_events": _check_dedup_events(overlay),
        "blocked_tasks": _check_blocked_tasks(overlay, blocked_tasks),
        "drift_warnings": drift_warnings or [],
        # Malformed-frontmatter files skipped by build_graph, surfaced here so
        # health reports expose non-fatal parse failures instead of silently
        # omitting sources.
        "skipped_files": list(G.graph.get("skipped_files", [])),
        # A2-6: configured / last-refresh mirror provider identity (non-secret).
        "mirror_provider": mirror_provider,
    }

    logger.info(
        "graph_status: %d nodes, %d edges, %d degraded, %d tentative, "
        "%d collisions, %d orphaned, %d stale, %d orphaned overlay, "
        "%d coverage_flags, %d dedup_events, %d blocked_tasks",
        report["total_nodes"],
        report["total_edges"],
        len(report["degraded_nodes"]),
        len(report["tentative_nodes"]),
        len(report["id_collisions"]),
        len(report["orphaned_nodes"]),
        len(report["stale_nodes"]),
        len(report["orphaned_overlay_entries"]),
        len(report["coverage_flags"]),
        len(report["dedup_events"]),
        len(report["blocked_tasks"]),
    )

    return report
