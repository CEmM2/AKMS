"""Versioned ``failure-memory`` command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from akms_failure_memory import __version__
from akms_failure_memory.errors import FailureMemoryError


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="failure-memory")
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument("--json-errors", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("validate", "compile", "check", "doctor", "migrate-check", "ci-check"):
        command = sub.add_parser(name)
        command.add_argument("--config", type=Path, required=True)
        command.add_argument("--repo", type=Path, default=Path.cwd())
        if name in {"compile", "check"}:
            command.add_argument("--output-root", type=Path)
            command.add_argument("--global-vault", type=Path, required=True)

    init = sub.add_parser("init")
    init.add_argument("--repo", type=Path, default=Path.cwd())
    init.add_argument(
        "--config", type=Path, default=Path(".failure-memory/config.toml")
    )
    init.add_argument("--force", action="store_true")
    init.add_argument("--repository-id")
    init.add_argument("--node-namespace")

    add = sub.add_parser("add")
    add.add_argument("--config", type=Path, required=True)
    add.add_argument("--repo", type=Path, default=Path.cwd())
    source = add.add_mutually_exclusive_group(required=True)
    source.add_argument("--interactive", action="store_true")
    source.add_argument("--from-json", type=Path)
    add.add_argument("--global-vault", type=Path, required=True)

    wrapper = sub.add_parser("generate-wrapper")
    wrapper.add_argument("--config", type=Path, required=True)
    wrapper.add_argument("--repo", type=Path, default=Path.cwd())
    wrapper.add_argument("--output", type=Path, required=True)
    wrapper.add_argument("--force", action="store_true")

    refresh = sub.add_parser("refresh")
    refresh.add_argument(
        "action",
        choices=("preflight", "status", "lessons", "mirror", "graph", "all", "clean"),
    )
    refresh.add_argument("--config", type=Path, required=True)
    refresh.add_argument("--repo", type=Path, default=Path.cwd())
    refresh.add_argument("--global-vault", type=Path, required=True)
    refresh.add_argument("--phase", type=int, default=1)
    refresh.add_argument("--generated-at", required=False)
    refresh.add_argument("--force-lock", action="store_true")

    resolve = sub.add_parser("resolve")
    resolve.add_argument("--config", type=Path, required=True)
    resolve.add_argument("--repo", type=Path, default=Path.cwd())
    resolve.add_argument("--request", type=Path, required=True)

    stale = sub.add_parser("validate-fingerprint")
    stale.add_argument("--config", type=Path, required=True)
    stale.add_argument("--repo", type=Path, default=Path.cwd())
    stale.add_argument("--request", type=Path, required=True)
    stale.add_argument("--result", type=Path, required=True)
    return parser


def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command in {"compile", "check", "validate"}:
        from akms_failure_memory.compiler import run_compiler

        mode = (
            "check"
            if args.command == "check"
            else "validate"
            if args.command == "validate"
            else "write"
        )
        return run_compiler(
            config_path=args.config,
            repository_root=args.repo,
            global_vault=getattr(args, "global_vault", None),
            output_root=getattr(args, "output_root", None),
            mode=mode,
        )
    if args.command == "add":
        from akms_failure_memory.record import add_lesson

        return add_lesson(
            config_path=args.config,
            repository_root=args.repo,
            request_path=args.from_json,
            interactive=args.interactive,
            global_vault=args.global_vault,
        )
    if args.command in {"init", "doctor", "migrate-check", "generate-wrapper"}:
        from akms_failure_memory.project import run_project_command

        return run_project_command(args.command, args)
    if args.command == "refresh":
        from akms_failure_memory.refresh import refresh_project

        return refresh_project(
            action=args.action,
            config_path=args.config,
            repository_root=args.repo,
            global_vault=args.global_vault,
            phase=args.phase,
            generated_at=args.generated_at,
            force_lock=args.force_lock,
        )
    if args.command in {"resolve", "validate-fingerprint"}:
        from akms_failure_memory.provider import run_provider_command

        return run_provider_command(args.command, args)
    if args.command == "ci-check":
        from akms_failure_memory.ci import ci_check

        return ci_check(config_path=args.config, repository_root=args.repo)
    raise FailureMemoryError(f"Unknown command {args.command!r}", code="usage")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        result = _dispatch(args)
    except FailureMemoryError as exc:
        if args.json_errors:
            print(json.dumps(exc.to_json(), ensure_ascii=False, sort_keys=True))
        else:
            print(f"error[{exc.code}]: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        error = FailureMemoryError(str(exc), code="internal_error")
        if args.json_errors:
            print(json.dumps(error.to_json(), ensure_ascii=False, sort_keys=True))
        else:
            print(f"error[{error.code}]: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") not in {"error", "drift"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
