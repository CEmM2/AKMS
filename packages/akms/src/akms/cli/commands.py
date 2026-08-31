"""CLI commands for AKMS developer operations.

Commands:
  akms promote <node_id>   — tentative → established (local nodes only)
  akms suppress <node_id>  — → draft
  akms deprecate <node_id> — → deprecated
  akms status              — run graph_status health report
  akms query <tags...>     — query the compiled knowledge graph
  akms loadout <task_id>   — query and generate a task loadout
  akms resolve-task        — deterministic task knowledge → loadout + manifest
  akms mirror-status       — show configured code-mirror provider identity
  akms generate-mirror     — refresh code mirrors via configured provider
  akms orchestrate         — run the orchestrator pipeline
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import frontmatter as fm

from akms.graph.graph_status import format_report, graph_status

if TYPE_CHECKING:
    import networkx as nx

    from akms.schema.models import PropagationConfig


def _find_local_node(repo_root: Path, node_id: str) -> Path | None:
    """Find a local node file by id."""
    local_nodes_dir = repo_root / "knowledge" / "local-nodes"
    candidate = local_nodes_dir / f"{node_id}.md"
    if candidate.exists():
        return candidate
    return None


def _update_node_status(node_path: Path, new_status: str) -> bool:
    """Update the status field in a node's frontmatter.

    Returns True if updated, False on error.
    """
    try:
        post = fm.load(str(node_path))
        old_status = post.metadata.get("status", "unknown")
        post.metadata["status"] = new_status
        with open(node_path, "wb") as f:
            fm.dump(post, f)
        print(f"Updated {node_path.stem}: {old_status} → {new_status}")
        return True
    except Exception as e:
        print(f"Error updating {node_path}: {e}", file=sys.stderr)
        return False


def cmd_promote(args: argparse.Namespace) -> int:
    """Promote a tentative node to established (local nodes only)."""
    repo_root = Path(args.repo).resolve()
    node_path = _find_local_node(repo_root, args.node_id)

    if node_path is None:
        print(f"Local node '{args.node_id}' not found in {repo_root}/knowledge/local-nodes/",
              file=sys.stderr)
        return 1

    # Verify current status is tentative
    post = fm.load(str(node_path))
    current = post.metadata.get("status", "")
    if current != "tentative":
        print(f"Cannot promote: node '{args.node_id}' is '{current}', not 'tentative'",
              file=sys.stderr)
        return 1

    return 0 if _update_node_status(node_path, "established") else 1


def cmd_suppress(args: argparse.Namespace) -> int:
    """Suppress a node (set to draft)."""
    repo_root = Path(args.repo).resolve()
    node_path = _find_local_node(repo_root, args.node_id)

    if node_path is None:
        print(f"Local node '{args.node_id}' not found in {repo_root}/knowledge/local-nodes/",
              file=sys.stderr)
        return 1

    return 0 if _update_node_status(node_path, "draft") else 1


def cmd_deprecate(args: argparse.Namespace) -> int:
    """Deprecate a node."""
    repo_root = Path(args.repo).resolve()
    node_path = _find_local_node(repo_root, args.node_id)

    if node_path is None:
        print(f"Local node '{args.node_id}' not found in {repo_root}/knowledge/local-nodes/",
              file=sys.stderr)
        return 1

    return 0 if _update_node_status(node_path, "deprecated") else 1


def cmd_status(args: argparse.Namespace) -> int:
    """Run graph_status health report."""
    from akms.schema.validators import parse_propagation_config

    repo_root = Path(args.repo).resolve()

    # F-06: honor config.global_vault as the third step in the precedence
    # chain (explicit arg > env > config > default). `cmd_status` has no
    # --vault flag today; env var and config are the only sources.
    config_path = repo_root / "knowledge" / "graph" / "propagation_config.yaml"
    config = parse_propagation_config(config_path) if config_path.exists() else None

    report = graph_status(repo_root, config=config)
    print(format_report(report))

    return 0


def _load_cli_config(repo_root: Path) -> PropagationConfig:
    """Load the repo propagation config, falling back to schema defaults."""
    from akms.schema.models import PropagationConfig
    from akms.schema.validators import parse_propagation_config

    config_path = repo_root / "knowledge" / "graph" / "propagation_config.yaml"
    return parse_propagation_config(config_path) if config_path.exists() else PropagationConfig()


def _resolve_cli_path(repo_root: Path, value: str | None, default: Path) -> Path:
    """Resolve an optional CLI path relative to the selected repository."""
    if value is None:
        return default
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def _load_cli_graph(
    repo_root: Path,
    graph_arg: str | None,
    config: PropagationConfig,
) -> tuple[nx.DiGraph, Path]:
    """Load a requested graph, compiling the default graph when absent."""
    from akms.graph.build_graph import build_graph, load_graph

    default_path = repo_root / "knowledge" / "graph" / "graph.json"
    graph_path = _resolve_cli_path(repo_root, graph_arg, default_path)
    if graph_path.exists():
        return load_graph(graph_path), graph_path
    if graph_arg is not None:
        raise FileNotFoundError(f"Graph file not found: {graph_path}")
    return build_graph(repo_root, output_path=graph_path, config=config), graph_path


def _serialize_ranked_nodes(ranked_nodes: list[tuple[str, dict]]) -> list[dict]:
    """Convert ranked query tuples into stable JSON-facing summaries."""
    result = []
    for node_id, data in ranked_nodes:
        entry = {
            "confidence": data.get("confidence") if data.get("confidence") is not None else 0.0,
            "domain": data.get("domain") or "",
            "id": node_id,
            "node_origin": data.get("node_origin") or "",
            "title": data.get("title") or "",
        }
        tags = data.get("tags")
        if tags:
            entry["tags"] = sorted([tags] if isinstance(tags, str) else tags)
        result.append(entry)
    return result



def _display_path(path: Path, repo_root: Path) -> str:
    """Render *path* relative to *repo_root* for shareable output.

    Falls back to abbreviating the home directory to ``~`` for paths outside
    the repo, so command output never embeds the local username.
    """
    try:
        return str(Path(path).resolve().relative_to(Path(repo_root).resolve()))
    except ValueError:
        pass
    try:
        return "~/" + str(Path(path).resolve().relative_to(Path.home()))
    except ValueError:
        return str(path)


def cmd_query(args: argparse.Namespace) -> int:
    """Query the compiled graph and print ranked node summaries as JSON."""
    from akms.graph.query_subgraph import query_subgraph

    repo_root = Path(args.repo).resolve()
    try:
        config = _load_cli_config(repo_root)
        graph, graph_path = _load_cli_graph(repo_root, args.graph, config)
        ranked = query_subgraph(
            graph,
            args.tags,
            args.role,
            config=config,
            max_depth=args.max_depth,
        )
    except Exception as exc:
        print(f"Query failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({
        "count": len(ranked),
        # Relative to the repo when inside it: the JSON output is shareable,
        # and an absolute path would leak the local directory layout.
        "graph_path": _display_path(graph_path, repo_root),
        "nodes": _serialize_ranked_nodes(ranked),
    }, indent=2, sort_keys=True))
    return 0


def _validate_task_id(task_id: str) -> None:
    """Reject task identifiers that could be interpreted as paths."""
    if not task_id or task_id in {".", ".."} or "/" in task_id or "\\" in task_id:
        raise ValueError("task_id must be a non-empty identifier without path separators")


def _canonical_loadout_path(repo_root: Path, phase: int, task_id: str) -> Path:
    """Return the canonical loadout path for a validated task identifier."""
    _validate_task_id(task_id)
    return repo_root / "knowledge" / "loadouts" / f"{phase}-{task_id}-loadout.md"


def cmd_loadout(args: argparse.Namespace) -> int:
    """Query the graph and write a canonical task loadout."""
    from akms.graph.generate_loadout import generate_loadout
    from akms.graph.qmd_cache import compute_graph_version
    from akms.graph.query_subgraph import query_subgraph

    repo_root = Path(args.repo).resolve()
    try:
        _validate_task_id(args.task_id)
        config = _load_cli_config(repo_root)
        graph, graph_path = _load_cli_graph(repo_root, args.graph, config)
        ranked = query_subgraph(
            graph,
            args.tags,
            args.role,
            config=config,
            max_depth=args.max_depth,
        )
        if args.output:
            output_path = _resolve_cli_path(repo_root, args.output, Path(args.output))
        else:
            output_path = _canonical_loadout_path(repo_root, args.phase, args.task_id)
        graph_version = compute_graph_version(graph_path)
        generate_loadout(
            G=graph,
            ranked_nodes=ranked,
            task_id=args.task_id,
            phase=args.phase,
            graph_version=graph_version,
            seed_tags=args.tags,
            agent_role=args.role,
            mode=args.mode,
            available_context=args.available_context,
            config=config,
            output_path=output_path,
            repo_root=repo_root,
        )
    except Exception as exc:
        print(f"Loadout generation failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({
        "graph_version": graph_version,
        "loadout_path": str(output_path),
        "mode": args.mode,
        "node_count": len(ranked),
    }, indent=2, sort_keys=True))
    return 0


#   # ── resolve-task (thin CLI adapter over resolve_task_service) ──


def cmd_resolve_task(args: argparse.Namespace) -> int:
    """Resolve exact task knowledge and write loadout + resolution manifest.

    Stdout is **always** machine-readable JSON (no human logs mixed in). Errors
    are reported via ``status: error`` with a non-zero exit code.
    """
    from akms.task_context.resolve_task_service import resolve_task

    repo_root = Path(args.repo).resolve()
    result = resolve_task(
        repo_root=repo_root,
        task=args.task_json,
        route_index=args.routes,
        agent_role=args.role,
        changed_paths=getattr(args, "changed_paths", None),
        base=getattr(args, "base", None),
        head=getattr(args, "head", None),
        graph_path=getattr(args, "graph", None),
        loadout_path=getattr(args, "output", None),
        manifest_path=getattr(args, "manifest", None),
        mode=getattr(args, "mode", "routing"),
        available_context=getattr(args, "available_context", 0),
        max_depth=getattr(args, "max_depth", 2),
        phase=getattr(args, "phase", None),
    )
    # Pure JSON on stdout — never mix human logs here.
    print(json.dumps(result.to_json_dict(), indent=2, sort_keys=True))
    return 0 if result.status == "ok" else 1


# Friendly --backend names → dotted AKMSAgent subclass paths. ``--agent`` (an
# explicit dotted path) overrides this and is the escape hatch for external
# agents. The CLI backends (claude-cli) drive subagents via the `claude` binary
# rather than the SDK; see akms/agents/.
BACKENDS = {
    "claude-sdk": "akms.agents.base.AKMSAgent",
    "claude-cli": "akms.agents.cli_claude.AKMSClaudeCliAgent",
    "codex-sdk": "akms.agents.base_codex.AKMSCodexAgent",
    "codex-cli": "akms.agents.cli_codex.AKMSCodexCliAgent",
    "local": "akms.agents.local.AKMSLocalAgent",
}

# Per-backend runtime prerequisite, checked before the pipeline starts.
#
# SDK backends need an importable Python package shipped by an optional extra;
# the CLI backends need an external binary on PATH and deliberately need *no*
# SDK. ``DEFAULT_BACKEND`` is what ``cmd_orchestrate`` falls back to when
# neither --backend nor --agent is given.
DEFAULT_BACKEND = "claude-sdk"

# backend → (python module, extra that provides it)
BACKEND_PY_MODULES = {
    "claude-sdk": ("claude_agent_sdk", "agents"),
    "codex-sdk": ("agents", "agents"),
    "local": ("agents", "agents"),
}

# backend → external CLI binary discovered on PATH (never a pip dependency)
BACKEND_BINARIES = {
    "claude-cli": "claude",
    "codex-cli": "codex",
}


def _backend_unavailable_reason(backend: str) -> str | None:
    """Return an actionable message if ``backend``'s runtime is missing.

    Cheap by construction: ``find_spec`` / ``shutil.which`` only, so the heavy
    provider SDKs are never imported merely to test for them.

    Args:
        backend: A key of ``BACKENDS``.

    Returns:
        The error message, or None when the backend can run.
    """
    binary = BACKEND_BINARIES.get(backend)
    if binary is not None:
        if shutil.which(binary) is None:
            return (
                f"The '{backend}' backend drives the '{binary}' CLI, which was "
                f"not found on PATH. Install it (and ensure '{binary}' is "
                f"runnable), or select a different --backend."
            )
        return None

    requirement = BACKEND_PY_MODULES.get(backend)
    if requirement is None:
        return None
    module, extra = requirement
    try:
        installed = importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        installed = False
    if not installed:
        return (
            f"The '{backend}' backend requires the '{module}' package, which is "
            f'not installed. Install it with: pip install "akms[{extra}]" '
            f'(or "akms[orchestration]" for the complete embedded runtime).'
        )
    return None


def _import_agent_class(dotted_path: str) -> type:
    """Import an agent class from a dotted module path.

    Args:
        dotted_path: e.g. ``tifem.akms_agent.TiFEMAgent``. TiFEM is a package
            inside the NumerixWeave project, not a standalone repository; the
            path appears only as an example of a consumer-supplied agent class.

    Returns:
        The imported class.

    Raises:
        ImportError: If the module cannot be imported.
        AttributeError: If the class doesn't exist in the module.
        TypeError: If the class is not a subclass of AKMSAgent.
    """
    from akms.agents.base import AKMSAgent

    module_path, _, class_name = dotted_path.rpartition(".")
    if not module_path:
        raise ImportError(
            f"Invalid agent path '{dotted_path}': expected 'module.ClassName'"
        )

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)

    if not isinstance(cls, type) or not issubclass(cls, AKMSAgent):
        raise TypeError(
            f"'{dotted_path}' is not a subclass of AKMSAgent. "
            f"Got {cls!r} which is {type(cls).__name__}."
        )

    return cls


def cmd_orchestrate(args: argparse.Namespace) -> int:
    """Run the orchestrator pipeline."""
    import asyncio

    # Fail fast, before the pipeline starts and before anything is written to
    # disk. Without this the first stage dispatches an agent, hits the missing
    # SDK deep inside execute(), writes a failed AgentMemory, and then blocks
    # on the stage checkpoint gate. The deep ImportError in akms/agents/base.py
    # stays as defense for library users; this only short-circuits the CLI.
    # --agent (an external class) is exempt: only its author knows its deps.
    if not args.agent:
        reason = _backend_unavailable_reason(
            getattr(args, "backend", None) or DEFAULT_BACKEND
        )
        if reason:
            print(reason, file=sys.stderr)
            return 1

    from akms.agents.base import AKMSAgent
    from akms.orchestrator.checkpoint import FileCheckpointHandler, TerminalCheckpointHandler
    from akms.orchestrator.orchestrator import run_pipeline
    from akms.schema.validators import parse_propagation_config

    repo_root = Path(args.repo).resolve()

    # Load config
    config_path = Path(args.config) if args.config else (
        repo_root / "knowledge" / "graph" / "propagation_config.yaml"
    )
    if config_path.exists():
        config = parse_propagation_config(config_path)
    else:
        print(f"Config not found at {config_path}, using defaults", file=sys.stderr)
        from akms.schema.models import PropagationConfig
        config = PropagationConfig()

    # Resolve agent class. --agent (explicit dotted path) wins; otherwise
    # --backend maps a friendly name to a built-in runtime; default = AKMSAgent.
    dotted_path = args.agent or (
        BACKENDS.get(args.backend) if getattr(args, "backend", None) else None
    )
    if dotted_path:
        try:
            agent_cls = _import_agent_class(dotted_path)
        except (ImportError, AttributeError) as exc:
            print(f"Failed to import agent class '{dotted_path}': {exc}", file=sys.stderr)
            return 1
        except TypeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    else:
        agent_cls = AKMSAgent

    # Override plan_name if provided
    if args.plan:
        config.orchestrator.plan_name = args.plan

    # Select checkpoint handler
    checkpoint_handler = (
        TerminalCheckpointHandler() if args.terminal
        else FileCheckpointHandler()
    )

    # Run the pipeline. Preflight and stage failures surface as short
    # messages with a nonzero exit; an aborted pipeline (developer abort or
    # checkpoint timeout) is a failure too — only a completed run exits 0.
    from akms.agents.base import AgentPreflightError
    from akms.orchestrator.orchestrator import StageFailedError

    try:
        state = asyncio.run(run_pipeline(
            repo_root=repo_root,
            spec_path=args.spec or "",
            goal=args.goal or "",
            plan_name=args.plan or config.orchestrator.plan_name,
            resume=args.resume,
            config=config,
            agent_cls=agent_cls,
            model=args.model,
            checkpoint_handler=checkpoint_handler,
        ))
    except AgentPreflightError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except StageFailedError as exc:
        print(f"{exc} — state saved; resume with --resume.", file=sys.stderr)
        return 1

    if getattr(state, "aborted", False):
        print("Pipeline aborted — state saved; resume with --resume.", file=sys.stderr)
        return 1
    return 0


def _add_repo_argument(parser: argparse.ArgumentParser, *, top_level: bool = False) -> None:
    """Add ``--repo`` without overwriting a value parsed by a parent parser."""
    parser.add_argument(
        "--repo", "-r",
        default="." if top_level else argparse.SUPPRESS,
        help="Repository root path (default: current directory)",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="akms",
        description="AKMS — Adaptive Knowledge Management System CLI",
    )
    _add_repo_argument(parser, top_level=True)

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # promote
    promote_parser = subparsers.add_parser(
        "promote", help="Promote tentative node to established",
    )
    _add_repo_argument(promote_parser)
    promote_parser.add_argument("node_id", help="Node ID to promote")
    promote_parser.set_defaults(func=cmd_promote)

    # suppress
    suppress_parser = subparsers.add_parser(
        "suppress", help="Suppress node (set to draft)",
    )
    _add_repo_argument(suppress_parser)
    suppress_parser.add_argument("node_id", help="Node ID to suppress")
    suppress_parser.set_defaults(func=cmd_suppress)

    # deprecate
    deprecate_parser = subparsers.add_parser(
        "deprecate", help="Deprecate a node",
    )
    _add_repo_argument(deprecate_parser)
    deprecate_parser.add_argument("node_id", help="Node ID to deprecate")
    deprecate_parser.set_defaults(func=cmd_deprecate)

    # status
    status_parser = subparsers.add_parser(
        "status", help="Run graph health report",
    )
    _add_repo_argument(status_parser)
    status_parser.set_defaults(func=cmd_status)

    # query
    query_parser = subparsers.add_parser(
        "query", help="Query the compiled graph by seed tags",
    )
    _add_repo_argument(query_parser)
    query_parser.add_argument("tags", nargs="+", help="One or more seed tags")
    query_parser.add_argument(
        "--role",
        choices=("implementer", "code_reviewer", "physics_reviewer"),
        default="implementer",
        help="Agent role query profile (default: implementer)",
    )
    query_parser.add_argument(
        "--max-depth", type=int, default=2,
        help="Maximum traversal depth from seed nodes (default: 2)",
    )
    query_parser.add_argument(
        "--graph", default=None,
        help="Compiled graph path relative to repo (default: knowledge/graph/graph.json)",
    )
    query_parser.set_defaults(func=cmd_query)

    # loadout
    loadout_parser = subparsers.add_parser(
        "loadout", help="Query the graph and generate a task loadout",
    )
    _add_repo_argument(loadout_parser)
    loadout_parser.add_argument("task_id", help="Task identifier for the loadout")
    loadout_parser.add_argument("--phase", type=int, required=True, help="Task phase number")
    loadout_parser.add_argument(
        "--tags", nargs="+", required=True, help="One or more query seed tags",
    )
    loadout_parser.add_argument(
        "--role",
        choices=("implementer", "code_reviewer", "physics_reviewer"),
        default="implementer",
        help="Agent role query profile (default: implementer)",
    )
    loadout_parser.add_argument(
        "--mode", choices=("routing", "full"), default="routing",
        help="Loadout content mode (default: routing)",
    )
    loadout_parser.add_argument(
        "--max-depth", type=int, default=2,
        help="Maximum traversal depth from seed nodes (default: 2)",
    )
    loadout_parser.add_argument(
        "--available-context", type=int, default=0,
        help="Estimated available context tokens recorded in the header",
    )
    loadout_parser.add_argument(
        "--graph", default=None,
        help="Compiled graph path relative to repo (default: knowledge/graph/graph.json)",
    )
    loadout_parser.add_argument(
        "--output", default=None,
        help="Exact output path relative to repo (default: canonical loadout path)",
    )
    loadout_parser.set_defaults(func=cmd_loadout)

    #   # ── resolve-task ─────────────────────────────────────────────────
    resolve_parser = subparsers.add_parser(
        "resolve-task",
        help="Resolve exact task knowledge into a loadout and resolution manifest",
    )
    _add_repo_argument(resolve_parser)
    resolve_parser.add_argument(
        "--task-json",
        required=True,
        help="Path to the task JSON file",
    )
    resolve_parser.add_argument(
        "--routes",
        required=True,
        help="Path to the task route index (JSON or YAML)",
    )
    resolve_parser.add_argument(
        "--role",
        choices=("implementer", "code_reviewer", "physics_reviewer"),
        default="implementer",
        help="Agent role query profile (default: implementer)",
    )
    resolve_parser.add_argument(
        "--phase",
        type=int,
        default=None,
        help="Phase number for output filenames (default: task.phase or 1)",
    )
    resolve_parser.add_argument(
        "--output",
        default=None,
        help="Loadout output path relative to repo "
        "(default: knowledge/loadouts/<phase>-<task>-<role>-loadout.md)",
    )
    resolve_parser.add_argument(
        "--manifest",
        default=None,
        help="Resolution manifest output path relative to repo "
        "(default: knowledge/resolution-manifests/<phase>-<task>-<role>-manifest.json)",
    )
    resolve_parser.add_argument(
        "--changed-paths",
        default=None,
        help="JSON file with a list (or {changed_paths: [...]}) of changed paths. "
        "A bare single path string is rejected — always pass a sequence.",
    )
    resolve_parser.add_argument(
        "--base",
        default=None,
        help="Git base revision for changed-path discovery (mutually exclusive "
        "with --changed-paths)",
    )
    resolve_parser.add_argument(
        "--head",
        default=None,
        help="Git head revision for changed-path discovery (default: HEAD)",
    )
    resolve_parser.add_argument(
        "--mode",
        choices=("routing", "full"),
        default="routing",
        help="Loadout content mode (default: routing)",
    )
    resolve_parser.add_argument(
        "--max-depth",
        type=int,
        default=2,
        help="Advisory query ego-graph depth (default: 2)",
    )
    resolve_parser.add_argument(
        "--available-context",
        type=int,
        default=0,
        help="Estimated available context tokens recorded in the loadout header",
    )
    resolve_parser.add_argument(
        "--graph",
        default=None,
        help="Compiled graph path relative to repo (default: knowledge/graph/graph.json)",
    )
    resolve_parser.set_defaults(func=cmd_resolve_task)

    # orchestrate
    orch_parser = subparsers.add_parser(
        "orchestrate", help="Run the orchestrator pipeline",
    )
    _add_repo_argument(orch_parser)
    orch_parser.add_argument(
        "--plan", "-p",
        default="",
        help="Plan name (used for branch naming)",
    )
    orch_parser.add_argument(
        "--config", "-c",
        default=None,
        help="Path to propagation_config.yaml (default: knowledge/graph/propagation_config.yaml)",
    )
    orch_parser.add_argument(
        "--backend", "-B",
        default=None,
        choices=sorted(BACKENDS),
        help=(
            "Built-in agent runtime: claude-sdk (default, Claude Agent SDK), "
            "claude-cli (drives the `claude` CLI headless — needs the claude "
            "binary on PATH, not the SDK), codex-sdk (OpenAI Agents SDK), "
            "codex-cli (drives `codex exec` — needs the codex binary on PATH), "
            "or local (openai-agents against a local OpenAI-compatible endpoint "
            "via AKMS_LLM_API_BASE). Overridden by --agent."
        ),
    )
    orch_parser.add_argument(
        "--agent", "-a",
        default=None,
        help=(
            "Dotted import path to an AKMSAgent subclass "
            "(e.g. tifem.akms_agent.TiFEMAgent or "
            "akms.agents.base_codex.AKMSCodexAgent). Overrides --backend. "
            "When both are omitted, uses the default AKMSAgent."
        ),
    )
    orch_parser.add_argument(
        "--model", "-m",
        default=None,
        help="Model override (e.g. claude-opus-4-6 for high-risk tasks)",
    )
    orch_parser.add_argument(
        "--resume", "-R",
        action="store_true",
        default=False,
        help="Resume from saved pipeline state",
    )
    orch_parser.add_argument(
        "--terminal", "-t",
        action="store_true",
        default=False,
        help="Use terminal checkpoint mode instead of file-based",
    )
    orch_parser.add_argument(
        "--spec", "-s",
        default=None,
        help="Path to specification file",
    )
    orch_parser.add_argument(
        "--goal", "-g",
        default=None,
        help="Goal description for the pipeline",
    )
    orch_parser.set_defaults(func=cmd_orchestrate)

    #   # Mirror provider status / refresh (separate module).
    from akms.cli.provider_commands import register_provider_commands

    register_provider_commands(subparsers)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point for the AKMS CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
