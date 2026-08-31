"""Command-line interface entry point: ``akms-learn``.

Plan §18 (L309-L327) defines the ``compile`` invocation; plan §23
(L530-L540) requires the CLI to reuse the Python API and surface packet
path, export paths, warnings, unavailable capabilities, and manifest
path. This module is a *thin* dispatcher: it parses argv, builds a
``LearningRequest`` (or raw dict — both shapes accepted by
:func:`compile_learning_source`), calls into the API, and presents the
result. No business logic lives here.

Exit codes (plan §18 + Phase 5 context summary L17):

* ``0`` — success.
* ``2`` — :class:`PacketValidationError` raised by the compiler.
* ``3`` — :class:`LearningCapabilityError` raised by the compiler.
* ``1`` — any other unhandled exception (printed to stderr).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from akms_learn.compiler import compile_learning_source
from akms_learn.domain_packs import LearningCapabilityError
from akms_learn.exporters import KNOWN_EXPORTERS
from akms_learn.graph_import import fixture_graph
from akms_learn.models import LearningSourcePacket
from akms_learn.validation import PacketValidationError, validate_packet

__all__ = ["build_parser", "main"]


# ---------------------------------------------------------------------------
# Argparse construction
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser for ``akms-learn``.

    Exposed for testing and for any caller that wants to inspect the
    flag set without invoking :func:`main`.
    """
    parser = argparse.ArgumentParser(
        prog="akms-learn",
        description=(
            "Compile Learning Source Packets from an AKMS graph. "
            "Exit codes: 0=success, 2=PacketValidationError, "
            "3=LearningCapabilityError, 1=other."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- compile -----------------------------------------------------------
    compile_parser = subparsers.add_parser(
        "compile",
        help="Compile a graph slice into a Learning Source Packet.",
        description=(
            "Compile a Learning Source Packet from a graph. The packet "
            "and any requested exporter artifacts are written under "
            "--output. Stdout reports packet_path, export_paths, "
            "warnings (count + per-line), unavailable_capabilities, "
            "and manifest_path."
        ),
    )
    compile_parser.add_argument(
        "--graph",
        required=True,
        help=(
            "Path to a graph JSON file, or the literal string 'fixture' "
            "to use the built-in fixture_graph()."
        ),
    )
    compile_parser.add_argument("--topic", required=True, help="Learning topic.")
    compile_parser.add_argument(
        "--goal",
        default=None,
        help="Learning goal (defaults to --topic when omitted).",
    )
    compile_parser.add_argument(
        "--audience",
        default="engineer",
        help="Audience (default: engineer).",
    )
    compile_parser.add_argument(
        "--depth",
        default="implementation",
        help="Depth (default: implementation).",
    )
    compile_parser.add_argument(
        "--generation-option",
        default="deterministic_outline",
        help="Generation option (default: deterministic_outline).",
    )
    compile_parser.add_argument(
        "--seed-tags",
        action="append",
        default=[],
        help="Seed tag (repeatable).",
    )
    compile_parser.add_argument(
        "--max-nodes",
        type=int,
        default=None,
        help="Maximum number of nodes to retain.",
    )
    compile_parser.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Maximum traversal depth.",
    )
    compile_parser.add_argument(
        "--include-pitfalls",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include pitfall sections (default: enabled).",
    )
    compile_parser.add_argument(
        "--include-code-links",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include code-link sections (default: enabled).",
    )
    compile_parser.add_argument(
        "--export",
        action="append",
        default=[],
        choices=list(KNOWN_EXPORTERS),
        help=(f"Exporter name (repeatable). Must be one of: {', '.join(KNOWN_EXPORTERS)}."),
    )
    compile_parser.add_argument(
        "--output",
        required=True,
        help="Output directory (created if missing).",
    )
    compile_parser.add_argument(
        "--domain-pack",
        action="append",
        default=[],
        help="Path to a domain_pack.yaml (repeatable).",
    )
    compile_parser.add_argument(
        "--source-pack",
        action="append",
        default=[],
        help="Path to a source_pack.yaml (repeatable).",
    )
    compile_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-key output.",
    )
    compile_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a single JSON object instead of key:value lines.",
    )
    compile_parser.add_argument(
        "--rich-html",
        action="store_true",
        help=(
            "Render the html export as a rich page (MathJax + typeset algorithm "
            "blocks) instead of the default self-contained offline preview. "
            "Adds a remote MathJax script, so the page is no longer offline."
        ),
    )

    # --- LLM expansion flags -----------------------------------------------
    compile_parser.add_argument(
        "--llm-enable",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable LLM expansion (default: disabled).",
    )
    compile_parser.add_argument(
        "--llm-provider",
        default=None,
        help="LLM provider registry name (akms | nlm | no_provider_stub).",
    )
    compile_parser.add_argument(
        "--llm-policy",
        default=None,
        help=("LLM expansion policy override (source_locked | explanatory_only | no_new_claims)."),
    )
    compile_parser.add_argument(
        "--llm-notebook-id",
        default=None,
        help="NotebookLM notebook id to use as grounded context source.",
    )
    compile_parser.add_argument(
        "--llm-pdf",
        action="append",
        default=[],
        help="PDF path to add as grounded context source (repeatable).",
    )
    compile_parser.add_argument(
        "--llm-profile",
        default=None,
        help="NotebookLM profile name for the grounded provider.",
    )

    # --- Learner-profile flags -----------------------------------------------
    compile_parser.add_argument(
        "--knows",
        action="append",
        default=[],
        dest="learner_knows",
        help=(
            "Concept, tag, or node-id the learner already knows (repeatable). "
            "Populates LearnerProfile.knows. Only effective with "
            "--generation-option adaptive_path."
        ),
    )
    compile_parser.add_argument(
        "--weak",
        action="append",
        default=[],
        dest="learner_weak",
        help=(
            "Topic the learner considers a weak area (repeatable). "
            "Populates LearnerProfile.weak. Surfaced in the adaptive summary "
            "but does not affect node selection."
        ),
    )
    compile_parser.add_argument(
        "--learner-goal",
        action="append",
        default=[],
        dest="learner_goals",
        help=(
            "High-level learning goal for the adaptive path (repeatable). "
            "Populates LearnerProfile.goals. Surfaced in the adaptive summary "
            "but does not affect node selection. (Not to be confused with "
            "--goal, which sets the top-level learning goal for the request.)"
        ),
    )
    compile_parser.add_argument(
        "--conservative",
        action=argparse.BooleanOptionalAction,
        default=None,
        dest="learner_conservative",
        help=(
            "Conservative prerequisite mode. When enabled (the default), no "
            "prerequisite node is ever skipped. Pass --no-conservative to allow "
            "skipping based on --knows. Populates LearnerProfile.conservative_mode."
        ),
    )

    # --- validate ----------------------------------------------------------
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate an existing LSP (YAML or JSON).",
        description=(
            "Load a Learning Source Packet from disk (YAML if the path "
            "ends in .yaml/.yml, JSON otherwise) and run validate_packet. "
            "Exit 0 on success, 2 on PacketValidationError."
        ),
    )
    validate_parser.add_argument(
        "--packet",
        required=True,
        help="Path to a Learning Source Packet YAML or JSON file.",
    )
    validate_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress non-key output.",
    )
    validate_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a single JSON object instead of key:value lines.",
    )

    return parser


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _format_warnings_lines(warnings_iter: Sequence[Any]) -> list[str]:
    """Render a warnings list as ``"  - code | source_ref | message"`` lines."""
    rendered: list[str] = []
    for w in warnings_iter:
        code = getattr(w, "code", None) or (w.get("code") if isinstance(w, dict) else "")
        source_ref = getattr(w, "source_ref", None) or (
            w.get("source_ref") if isinstance(w, dict) else ""
        )
        message = getattr(w, "message", None) or (w.get("message") if isinstance(w, dict) else "")
        rendered.append(f"  - {code} | {source_ref} | {message}")
    return rendered


def _warning_to_dict(w: Any) -> dict[str, Any]:
    if isinstance(w, dict):
        return {
            "code": w.get("code", ""),
            "source_ref": w.get("source_ref", ""),
            "message": w.get("message", ""),
        }
    return {
        "code": getattr(w, "code", ""),
        "source_ref": getattr(w, "source_ref", ""),
        "message": getattr(w, "message", ""),
    }


def _print_compile_result(
    result: Any,
    packet_path: str,
    manifest_path: str,
    *,
    quiet: bool,
    as_json: bool,
) -> None:
    """Emit the compile-result summary to stdout in the chosen format."""
    export_paths = [str(p) for p in result.export_paths]
    warnings_list = list(result.warnings)
    unavailable = list(result.unavailable_capabilities)

    if as_json:
        payload = {
            "packet_path": packet_path,
            "export_paths": export_paths,
            "warnings": [_warning_to_dict(w) for w in warnings_list],
            "unavailable_capabilities": unavailable,
            "manifest_path": manifest_path,
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    # key:value lines mode (default + --quiet)
    print(f"packet_path: {packet_path}")
    # Per-line export paths so each is on its own line (greppable).
    if export_paths:
        for ep in export_paths:
            print(f"export_paths: {ep}")
    else:
        print("export_paths:")
    print(f"warnings: {len(warnings_list)}")
    if not quiet:
        for line in _format_warnings_lines(warnings_list):
            print(line)
    if unavailable:
        for cap in unavailable:
            print(f"unavailable_capabilities: {cap}")
    else:
        print("unavailable_capabilities:")
    print(f"manifest_path: {manifest_path}")


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _build_request_dict(args: argparse.Namespace) -> dict[str, Any]:
    """Map argparse namespace fields onto the LearningRequest dict.

    Returns a raw dict (not a :class:`LearningRequest`) so the compiler's
    own ``normalize_request`` handles defaulting and stripping in exactly
    the same way as the Python API path. This is the only place CLI
    flags meet request fields — keep mappings 1:1 with field names.

    The LLM expansion fields (``llm_enable``, ``llm_provider``, ``llm_policy``,
    ``sources``) are passthrough config excluded from ``NORMALIZED_FIELDS``; they
    pass through the dict unchanged and are consumed by the compiler's
    ``_build_llm_expansion_request`` adapter (the single mapping site).
    """
    d: dict[str, Any] = {
        "topic": args.topic,
        "goal": args.goal if args.goal is not None else args.topic,
        "audience": args.audience,
        "depth": args.depth,
        "generation_option": args.generation_option,
        "seed_tags": list(args.seed_tags or []),
        "max_nodes": args.max_nodes,
        "max_depth": args.max_depth,
        "include_pitfalls": args.include_pitfalls,
        "include_code_links": args.include_code_links,
        "exporters": list(args.export or []),
        # Opt-in rich html rendering (excluded from request_hash).
        "rich_html": args.rich_html,
        # LLM expansion passthrough fields.
        "llm_enable": args.llm_enable,
    }
    # Only include optional LLM fields when they carry a non-None value so the
    # LearningRequest defaults remain in effect when the flags are omitted.
    if args.llm_provider is not None:
        d["llm_provider"] = args.llm_provider
    if args.llm_policy is not None:
        d["llm_policy"] = args.llm_policy
    # Assemble the sources bundle from the individual --llm-* source flags.
    # The bundle is omitted entirely when none of the source flags were given.
    sources: dict[str, Any] = {}
    if args.llm_notebook_id is not None:
        sources["notebook_id"] = args.llm_notebook_id
    if args.llm_pdf:
        sources["pdf_paths"] = list(args.llm_pdf)
    if args.llm_profile is not None:
        sources["profile"] = args.llm_profile
    if sources:
        d["sources"] = sources
    # Assemble the learner_profile dict from the individual --knows/--weak/--goal/
    # --conservative flags.  The bundle is omitted entirely when none of the flags
    # were given so the LearningRequest default (learner_profile=None) is preserved,
    # keeping adaptive_path compilations without a profile strictly conservative.
    learner_knows: list[str] = list(args.learner_knows or [])
    learner_weak: list[str] = list(args.learner_weak or [])
    learner_goals: list[str] = list(args.learner_goals or [])
    learner_conservative: bool | None = args.learner_conservative
    profile_given = (
        bool(learner_knows)
        or bool(learner_weak)
        or bool(learner_goals)
        or learner_conservative is not None
    )
    if profile_given:
        profile_dict: dict[str, Any] = {
            "knows": learner_knows,
            "weak": learner_weak,
            "goals": learner_goals,
        }
        # Only override conservative_mode when explicitly passed; default=True is
        # enforced by LearnerProfile itself, so we can omit the key and let the
        # model default kick in when --conservative / --no-conservative is absent.
        if learner_conservative is not None:
            profile_dict["conservative_mode"] = learner_conservative
        d["learner_profile"] = profile_dict
    return d


def _run_compile(args: argparse.Namespace) -> int:
    """Dispatch ``compile`` to :func:`compile_learning_source`."""
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    request_dict = _build_request_dict(args)

    compile_kwargs: dict[str, Any] = {
        "request": request_dict,
        "output_dir": output_dir,
    }
    if args.graph == "fixture":
        compile_kwargs["graph_slice"] = fixture_graph()
    else:
        compile_kwargs["graph_path"] = Path(args.graph)

    if args.domain_pack:
        compile_kwargs["domain_pack_paths"] = [Path(p) for p in args.domain_pack]
    if args.source_pack:
        compile_kwargs["source_pack_paths"] = [Path(p) for p in args.source_pack]

    result = compile_learning_source(**compile_kwargs)

    packet_path = str(result.packet_path) if result.packet_path else ""
    manifest_candidate = output_dir / "manifest.json"
    manifest_path = str(manifest_candidate) if manifest_candidate.exists() else ""

    _print_compile_result(
        result,
        packet_path=packet_path,
        manifest_path=manifest_path,
        quiet=args.quiet,
        as_json=args.json,
    )
    return 0


def _load_packet_dict(packet_path: Path) -> dict[str, Any]:
    """Load a packet file (YAML if .yaml/.yml else JSON) as a plain dict."""
    suffix = packet_path.suffix.lower()
    text = packet_path.read_text(encoding="utf-8")
    if suffix in (".yaml", ".yml"):
        import yaml  # lazy import: only required for YAML packets

        return yaml.safe_load(text)
    return json.loads(text)


def _run_validate(args: argparse.Namespace) -> int:
    """Dispatch ``validate`` to :func:`validate_packet`."""
    packet_path = Path(args.packet)
    raw = _load_packet_dict(packet_path)
    packet = LearningSourcePacket.model_validate(raw)
    warnings_list = validate_packet(packet)

    if args.json:
        print(
            json.dumps(
                {
                    "packet_path": str(packet_path),
                    "warnings": [_warning_to_dict(w) for w in warnings_list],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"packet_path: {packet_path}")
        print(f"warnings: {len(warnings_list)}")
        if not args.quiet:
            for line in _format_warnings_lines(warnings_list):
                print(line)
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. ``argv`` defaults to :data:`sys.argv[1:]`.

    Returns an integer exit code (also passed to :func:`sys.exit` when
    invoked from the console script).
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "compile":
            return _run_compile(args)
        if args.command == "validate":
            return _run_validate(args)
        parser.error(f"Unknown command: {args.command!r}")
        return 1  # pragma: no cover — parser.error exits
    except PacketValidationError as exc:
        print(f"PacketValidationError: {exc}", file=sys.stderr)
        return 2
    except LearningCapabilityError as exc:
        print(f"LearningCapabilityError: {exc}", file=sys.stderr)
        return 3
    except SystemExit:
        # argparse uses SystemExit to signal --help / parse errors; surface
        # it unchanged so shells see the conventional argparse exit codes.
        raise
    # Intentional top-level CLI catch-all: any other error becomes exit code 1
    # with a stderr message, never a traceback dump to the user.
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
