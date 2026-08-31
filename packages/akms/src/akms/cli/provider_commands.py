"""CLI commands for mirror-provider status and refresh (A2-6).

Kept separate from ``commands.py`` resolve-task sections owned by A2-α.
Registered via :func:`register_provider_commands`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_mirror_status(args: argparse.Namespace) -> int:
    """Print non-secret mirror provider identity from config."""
    from akms.graph.mirror_provider import (
        public_provider_identity,
        resolve_mirror_config,
    )
    from akms.schema.models import PropagationConfig
    from akms.schema.validators import parse_propagation_config

    repo = Path(args.repo).resolve()
    config_path = (
        Path(args.config)
        if args.config
        else (repo / "knowledge" / "graph" / "propagation_config.yaml")
    )
    if config_path.is_file():
        config = parse_propagation_config(config_path)
    else:
        config = PropagationConfig()
    mirror_cfg = resolve_mirror_config(config)
    identity = public_provider_identity(mirror_cfg)
    identity["known_providers"] = _known_providers()
    if args.json:
        print(json.dumps(identity, indent=2, sort_keys=True))
    else:
        print("AKMS mirror provider")
        for key in sorted(identity):
            print(f"  {key}: {identity[key]}")
    return 0


def cmd_generate_mirror(args: argparse.Namespace) -> int:
    """Refresh code mirrors via the configured provider (CLI smoke)."""
    from akms.graph.generate_mirror import generate_mirror
    from akms.graph.mirror_provider import MirrorProviderError
    from akms.schema.models import PropagationConfig
    from akms.schema.validators import parse_propagation_config

    repo = Path(args.repo).resolve()
    config_path = (
        Path(args.config)
        if args.config
        else (repo / "knowledge" / "graph" / "propagation_config.yaml")
    )
    if config_path.is_file():
        config = parse_propagation_config(config_path)
    else:
        config = PropagationConfig()

    source_files = list(args.path) if args.path else None
    try:
        result = generate_mirror(
            repo,
            phase=args.phase,
            parent_branch=args.parent_branch,
            source_files=source_files,
            config=config,
            provider_name=args.provider,
            llm_fn=None,
        )
    except MirrorProviderError as exc:
        payload = {
            "error": str(exc),
            "code": exc.code,
            "provider": exc.provider,
        }
        print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
    else:
        print(
            f"provider={result.get('provider')} "
            f"mirrors={len(result.get('mirrors') or [])} "
            f"drift={len(result.get('drift_warnings') or [])} "
            f"success={result.get('success')} "
            f"fallback={result.get('fallback_used')}"
        )
    return 0 if result.get("success", True) else 1


def _known_providers() -> list[str]:
    from akms.graph.mirror_provider import list_providers

    return list_providers()


def register_provider_commands(subparsers: argparse._SubParsersAction) -> None:
    """Register ``mirror-status`` and ``generate-mirror`` subcommands."""

    def _add_repo(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--repo",
            "-r",
            default=".",
            help="Repository root (default: cwd)",
        )

    status = subparsers.add_parser(
        "mirror-status",
        help="Show configured code-mirror provider identity (non-secret)",
    )
    _add_repo(status)
    status.add_argument(
        "--config",
        "-c",
        default=None,
        help="Path to propagation_config.yaml",
    )
    status.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON",
    )
    status.set_defaults(func=cmd_mirror_status)

    gen = subparsers.add_parser(
        "generate-mirror",
        help="Refresh code mirrors via the configured provider",
    )
    _add_repo(gen)
    gen.add_argument(
        "--config",
        "-c",
        default=None,
        help="Path to propagation_config.yaml",
    )
    gen.add_argument(
        "--phase",
        type=int,
        default=1,
        help="Generating phase number (default: 1)",
    )
    gen.add_argument(
        "--parent-branch",
        default="main",
        help="Git parent branch for changed-file selection (default: main)",
    )
    gen.add_argument(
        "--path",
        action="append",
        default=None,
        metavar="PATH",
        help="Explicit source path (repeatable; overrides git selection)",
    )
    gen.add_argument(
        "--provider",
        default=None,
        help="Override provider name (default: from config / legacy)",
    )
    gen.add_argument(
        "--json",
        action="store_true",
        help="Emit full result JSON",
    )
    gen.set_defaults(func=cmd_generate_mirror)
