"""The ``akms-records`` command-line interface (experimental).

Every command prints one JSON object on stdout, except ``recall --format
text`` and ``wake --format markdown``, which print the rendered text. Exit
status: 0 on success, 1 when the result's ``status`` is ``error`` or
``drift`` (for example ``doctor`` or ``index check`` found a problem,
``import`` met a conflict, or ``consolidate status`` found a stale summary),
and 2 when the command failed; the error goes to
stderr as ``error[<code>]: <message>``, or to stdout as JSON with
``--json-errors``.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from typing import Any

from akms_records import __version__
from akms_records.bridge import DEFAULT_MIN_REVIEW, MIN_REVIEW_CHOICES, REVIEW_CHOICES
from akms_records.canonical import loads_strict
from akms_records.consolidate import (
    DEFAULT_TIMEOUT,
    METHODS,
    command_summarizer,
    consolidate,
    describe,
    list_consolidations,
    refresh_consolidation,
    status_report,
)
from akms_records.envelope import ORIGIN_KINDS, REVIEW_STATES, SENSITIVITY_LEVELS
from akms_records.errors import RecordsError
from akms_records.policy import POLICY_SOURCES, POLICY_STATUSES
from akms_records.query import MIN_REVIEW_STATES
from akms_records.schemas import (
    RULE_KEYS,
    RegisteredSchema,
    load_template,
    template_names,
)
from akms_records.scope import Scope
from akms_records.store import RecordStore

ACTOR_ENV = "AKMS_RECORDS_ACTOR"


def default_actor() -> str:
    actor = os.environ.get(ACTOR_ENV)
    if actor:
        return actor
    try:
        return getpass.getuser() or "unknown"
    except (KeyError, OSError):
        return "unknown"


def _store_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--scope",
        required=True,
        help="project:<id>, agent:<id> or shared:<id>",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="repository root for project scope (default: the current directory)",
    )
    parser.add_argument(
        "--actor",
        default=None,
        help=f"who is acting (default: ${ACTOR_ENV}, then the user name)",
    )


def _record_fields(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--file",
        help="a JSON record document (schema_ref, payload, summary, tags, ...); "
        "- reads stdin",
    )
    parser.add_argument("--summary")
    parser.add_argument("--tag", action="append", dest="tags", metavar="TAG")
    parser.add_argument("--sensitivity", choices=SENSITIVITY_LEVELS)
    parser.add_argument("--review-state", choices=REVIEW_STATES)
    parser.add_argument(
        "--origin-kind",
        choices=ORIGIN_KINDS,
        help="origin.kind; origin.actor_id is the actor",
    )
    parser.add_argument(
        "--event-id",
        help="idempotency key: a retry with the same event ID writes nothing",
    )


def _rule_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--search-text",
        action="append",
        metavar="POINTER",
        help="payload field to index as text, as a JSON pointer (repeatable)",
    )
    parser.add_argument("--label", metavar="POINTER", help="display-label field")
    parser.add_argument("--time-field", metavar="POINTER", help="the record's own time")
    parser.add_argument(
        "--summary-template", help="summary text with {field} placeholders"
    )


def _rules_from_args(
    args: argparse.Namespace, base: dict[str, Any] | None
) -> dict[str, Any] | None:
    """Rules from --rules/--file and the rule flags; None when none are given."""
    rules: dict[str, Any] | None = None
    if getattr(args, "rules_file", None):
        loaded = _read_json(str(args.rules_file))
        if not isinstance(loaded, dict):
            raise RecordsError("rules must be a JSON object", code="invalid_rules")
        rules = dict(loaded)
    flags = {
        "search_text": args.search_text,
        "label": args.label,
        "time_field": args.time_field,
        "summary_template": args.summary_template,
    }
    given = {key: value for key, value in flags.items() if value is not None}
    unset = getattr(args, "unset", [])
    if rules is None and (given or unset):
        rules = dict(base or {})
    if rules is not None:
        rules.update(given)
        for key in unset:
            rules.pop(key, None)
    return rules


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="akms-records",
        description="Experimental schema-driven record store for AKMS.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--json-errors", action="store_true", help="print errors as JSON on stdout"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    schema = sub.add_parser("schema", help="register and inspect record schemas")
    schema_sub = schema.add_subparsers(dest="schema_command", required=True)
    register = schema_sub.add_parser("register", help="register a JSON Schema")
    _store_options(register)
    source = register.add_mutually_exclusive_group(required=True)
    source.add_argument("path", nargs="?", type=Path, help="schema file")
    source.add_argument("--template", help="a built-in template name")
    register.add_argument(
        "--name", help="schema name, if the file does not declare one"
    )
    register.add_argument(
        "--version", type=int, dest="schema_version", help="schema version number"
    )
    register.add_argument(
        "--rules", type=Path, dest="rules_file", help="extraction rules (JSON file)"
    )
    _rule_flags(register)
    listing = schema_sub.add_parser("list", help="registered schemas")
    _store_options(listing)
    show = schema_sub.add_parser("show", help="one registered schema")
    _store_options(show)
    show.add_argument("ref", help="<name>/v<N>, or <name> for the newest version")
    schema_sub.add_parser("templates", help="the built-in templates")
    rules = schema_sub.add_parser(
        "rules", help="a schema's extraction rules (kept beside the schema)"
    )
    rules_sub = rules.add_subparsers(dest="rules_command", required=True)
    rules_set = rules_sub.add_parser(
        "set", help="change the rules; the schema and its digest stay the same"
    )
    _store_options(rules_set)
    rules_set.add_argument("ref", help="<name>/v<N>, or <name> for the newest version")
    rules_set.add_argument(
        "--file",
        type=Path,
        dest="rules_file",
        help="replace the rules with this JSON object",
    )
    _rule_flags(rules_set)
    rules_set.add_argument(
        "--unset",
        action="append",
        choices=RULE_KEYS,
        default=[],
        help="remove one rule (repeatable)",
    )
    rules_show = rules_sub.add_parser("show", help="the rules and their change log")
    _store_options(rules_show)
    rules_show.add_argument("ref", help="<name>/v<N>, or <name> for the newest version")
    policy = schema_sub.add_parser("policy", help="per-schema promotion policy")
    policy_sub = policy.add_subparsers(dest="policy_command", required=True)
    policy_set = policy_sub.add_parser(
        "set",
        help="set a schema's promotion policy (a human operation; asks to confirm)",
    )
    _store_options(policy_set)
    policy_set.add_argument("name", help="schema name")
    policy_set.add_argument("--source", required=True, choices=POLICY_SOURCES)
    policy_set.add_argument("--status", required=True, choices=POLICY_STATUSES)
    policy_set.add_argument("--confidence", required=True, type=float)
    policy_set.add_argument(
        "--yes",
        action="store_true",
        help="confirm without a prompt; for a person running it without a "
        "terminal, never for an agent",
    )
    policy_show = policy_sub.add_parser("show", help="a schema's promotion policy")
    _store_options(policy_show)
    policy_show.add_argument("name", help="schema name")

    add = sub.add_parser("add", help="create a record")
    _store_options(add)
    _record_fields(add)
    add.add_argument("--schema", help="schema ref, if the document does not give one")

    amend = sub.add_parser("amend", help="amend a record")
    _store_options(amend)
    amend.add_argument("record_id")
    amend.add_argument("--expect-revision", type=int, required=True)
    _record_fields(amend)
    amend.add_argument("--schema", help="move the record to another schema ref")

    supersede = sub.add_parser("supersede", help="supersede a record by another")
    _store_options(supersede)
    supersede.add_argument("record_id")
    supersede.add_argument("--expect-revision", type=int, required=True)
    successor = supersede.add_mutually_exclusive_group(required=True)
    successor.add_argument("--by", help="an existing record in the same scope")
    successor.add_argument("--file", help="a record document for a new successor")
    supersede.add_argument("--schema", help="schema ref for the new successor")
    supersede.add_argument("--reason")
    supersede.add_argument("--event-id")

    retract = sub.add_parser("retract", help="retract a record")
    _store_options(retract)
    retract.add_argument("record_id")
    retract.add_argument("--expect-revision", type=int, required=True)
    retract.add_argument("--reason", required=True)
    retract.add_argument("--event-id")

    for name, text in (
        ("show", "a record's current state"),
        ("history", "a record's events"),
    ):
        command = sub.add_parser(name, help=text)
        _store_options(command)
        command.add_argument("record_id")

    listing = sub.add_parser("list", help="the scope's records (no index; scans files)")
    _store_options(listing)

    erase = sub.add_parser("erase", help="remove a record's files (privacy erasure)")
    _store_options(erase)
    erase.add_argument("record_id")
    erase.add_argument("--reason", required=True, help="logged; never put content here")
    erase.add_argument(
        "--force",
        action="store_true",
        help="erase a record that does not replay and whose scope is unknown",
    )

    doctor = sub.add_parser(
        "doctor", help="check the store root (reports only, unless --fix)"
    )
    _store_options(doctor)
    doctor.add_argument(
        "--fix",
        action="store_true",
        help="remove stale temp files and empty directories, re-apply erasures "
        "and erase summaries that cite erased records",
    )
    doctor.add_argument(
        "--force-tmp",
        action="store_true",
        help="with --fix, remove every temp file; only when no writer is running",
    )

    export = sub.add_parser("export", help="write the scope as portable JSONL")
    _store_options(export)
    export.add_argument("--output", "-o", help="file to write (default: stdout)")
    export.add_argument("--include-sensitive", action="store_true")
    export.add_argument("--skip-broken", action="store_true")

    imported = sub.add_parser(
        "import",
        help="replay a JSONL export into the scope, or read failure-memory lessons",
    )
    _store_options(imported)
    imported.add_argument("path", type=Path, nargs="?", help="a JSONL export")
    imported.add_argument(
        "--from-failure-memory",
        type=Path,
        metavar="CONFIG",
        help="read the lessons of this failure-memory project config (read-only)",
    )
    imported.add_argument(
        "--failure-memory-repo",
        type=Path,
        metavar="PATH",
        help="the root CONFIG's paths are relative to (default: --repo)",
    )

    promote = sub.add_parser(
        "promote",
        help="write a reviewed record as an AKMS project-local node (needs [akms])",
    )
    _store_options(promote)
    promote.add_argument("record_id")
    promote.add_argument(
        "--review",
        choices=REVIEW_CHOICES,
        help="explicit approval; promotion is refused without it",
    )
    promote.add_argument(
        "--min-review-state",
        choices=MIN_REVIEW_CHOICES,
        default=DEFAULT_MIN_REVIEW,
        help=f"the review state a record needs (default: {DEFAULT_MIN_REVIEW})",
    )
    promote.add_argument(
        "--scope-ok",
        action="store_true",
        help="allow a record of an agent or shared scope",
    )
    promote.add_argument(
        "--allow-sensitive", action="store_true", help="allow a sensitive record"
    )
    promote.add_argument(
        "--allow-imported",
        action="store_true",
        help="allow an imported failure lesson (failure-memory already routes it)",
    )
    promote.add_argument(
        "--update",
        action="store_true",
        help="append a newer revision to the node that holds an older one",
    )
    promote.add_argument(
        "--domain", help="the node's domain (default: the scope's ID, in lower case)"
    )

    recall = sub.add_parser("recall", help="search the scope's records (index)")
    _store_options(recall)
    recall.add_argument(
        "--agent", help="the reading agent; refuses another agent's scope"
    )
    recall.add_argument("--query", help="words that must all occur (plain text)")
    recall.add_argument("--schema", help="<name> or <name>/v<N>")
    recall.add_argument(
        "--tag",
        action="append",
        dest="tags",
        default=[],
        metavar="TAG",
        help="a tag the record must carry (repeatable; all must match)",
    )
    recall.add_argument(
        "--since", help="time field (or recorded_at) at or after this ISO time"
    )
    recall.add_argument("--until", help="time field (or recorded_at) before this")
    recall.add_argument(
        "--review-state",
        choices=MIN_REVIEW_STATES,
        default="unreviewed",
        help="minimum review state (rejected records are never shown)",
    )
    recall.add_argument("--include-retracted", action="store_true")
    recall.add_argument(
        "--include-superseded",
        action="store_true",
        help="also superseded records (default: chain heads only)",
    )
    recall.add_argument("--include-sensitive", action="store_true")
    recall.add_argument("--limit", type=int, default=20)
    recall.add_argument("--full", action="store_true", help="add each full record")
    recall.add_argument("--format", choices=("json", "text"), default="json")

    wake = sub.add_parser(
        "wake", help="records for an agent starting a task, within a token budget"
    )
    wake.add_argument("--agent", required=True, help="the agent's ID")
    wake.add_argument("--task", required=True, help="what the agent is about to do")
    wake.add_argument("--budget-tokens", type=int, required=True)
    wake.add_argument(
        "--scope",
        action="append",
        dest="scopes",
        default=[],
        help="a project:<id> or shared:<id> scope to include (repeatable); "
        "agent:<agent> is always included",
    )
    wake.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="repository root for project scope (default: the current directory)",
    )
    wake.add_argument("--include-sensitive", action="store_true")
    wake.add_argument(
        "--include-unreviewed",
        action="store_true",
        help="also unreviewed records of other agents and tools (default: only "
        "reviewed records plus the agent's own unreviewed ones)",
    )
    wake.add_argument(
        "--review-state",
        choices=MIN_REVIEW_STATES,
        default="unreviewed",
        help="minimum review state (rejected records are never included)",
    )
    wake.add_argument(
        "--include-promoted",
        action="store_true",
        help="also records promoted into AKMS nodes (default: the loadout serves them)",
    )
    wake.add_argument(
        "--include-imported",
        action="store_true",
        help="also imported failure lessons (default: failure-memory routes them)",
    )
    wake.add_argument(
        "--exclude-nodes",
        type=Path,
        metavar="MANIFEST",
        help="an AKMS resolution manifest: drop records whose promoted node it selected",
    )
    wake.add_argument("--format", choices=("json", "markdown"), default="json")
    wake.add_argument(
        "--generated-at",
        action="store_true",
        help="add a generated_at time to the JSON (makes output time-dependent)",
    )

    _consolidate_parser(sub)

    index = sub.add_parser("index", help="the derived search index of a store root")
    index_sub = index.add_subparsers(dest="index_command", required=True)
    for name, text in (
        ("rebuild", "rebuild the index from the event files"),
        ("check", "compare the index with the files; changes nothing"),
        ("reconcile", "replay every record and fix what differs"),
    ):
        command = index_sub.add_parser(name, help=text)
        _store_options(command)
    return parser


def _summarizer_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--summarizer-timeout",
        type=float,
        default=DEFAULT_TIMEOUT,
        metavar="SECONDS",
        help=f"how long the summarizer may run (default {DEFAULT_TIMEOUT:g})",
    )
    parser.add_argument(
        "--summarizer-cmd",
        nargs=argparse.REMAINDER,
        metavar="ARGV",
        help="run this command (no shell) as the provider: topic and sources as "
        "JSON on stdin, assertions as JSON on stdout; must be the last option",
    )


def _consolidate_parser(sub: Any) -> None:
    consolidate = sub.add_parser(
        "consolidate", help="source-linked summaries of records (opt-in)"
    )
    commands = consolidate.add_subparsers(dest="consolidate_command", required=True)
    create = commands.add_parser("create", help="summarize the records of a topic")
    _store_options(create)
    create.add_argument(
        "--tag",
        action="append",
        dest="tags",
        default=[],
        metavar="TAG",
        help="a tag every source carries (repeatable)",
    )
    create.add_argument("--query", help="words every source contains (plain text)")
    create.add_argument("--topic-name", help="a display name for the topic")
    create.add_argument(
        "--review-state",
        choices=MIN_REVIEW_STATES,
        default="unreviewed",
        help="minimum review state of a source",
    )
    create.add_argument("--method", choices=METHODS)
    create.add_argument(
        "--agent", help="the acting agent; refuses another agent's scope"
    )
    create.add_argument("--event-id")
    _summarizer_options(create)
    status = commands.add_parser(
        "status", help="valid or stale, with reasons (exit 1 when any is not valid)"
    )
    _store_options(status)
    status.add_argument(
        "record_id", nargs="?", help="one summary (default: all active)"
    )
    refresh = commands.add_parser(
        "refresh", help="write a new revision of a stale summary"
    )
    _store_options(refresh)
    refresh.add_argument("record_id")
    refresh.add_argument(
        "--expect-revision",
        type=int,
        help="the revision you last read (default: the head when the command starts)",
    )
    refresh.add_argument("--event-id")
    _summarizer_options(refresh)
    listing = commands.add_parser("list", help="the scope's summaries")
    _store_options(listing)


def _summarizer(args: argparse.Namespace) -> Any:
    if args.summarizer_cmd is None:
        return None
    return command_summarizer(args.summarizer_cmd, timeout=args.summarizer_timeout)


def _consolidate_command(args: argparse.Namespace) -> dict[str, Any]:
    store = _open(args)
    command = args.consolidate_command
    if command == "list":
        return {
            "status": "ok",
            "scope": str(store.scope),
            "summaries": [describe(record) for record in list_consolidations(store)],
        }
    if command == "status":
        return status_report(store, args.record_id)
    actor = _actor(args)
    if command == "create":
        return consolidate(
            store,
            actor=actor,
            tags=args.tags,
            query=args.query,
            topic_name=args.topic_name,
            method=args.method,
            summarizer=_summarizer(args),
            review_state=args.review_state,
            agent=args.agent,
            event_id=args.event_id,
        )
    return refresh_consolidation(
        store,
        args.record_id,
        actor=actor,
        expected_revision=args.expect_revision,
        summarizer=_summarizer(args),
        event_id=args.event_id,
    )


_OPENED: list[RecordStore] = []


def _open(args: argparse.Namespace) -> RecordStore:
    scope = Scope.parse(args.scope)
    repo = args.repo if args.repo is not None else Path.cwd()
    store = RecordStore.open(scope, repo=repo if scope.kind == "project" else None)
    _OPENED.append(store)
    return store


def _wake(args: argparse.Namespace) -> dict[str, Any]:
    from akms_records.canonical import utc_now
    from akms_records.query import manifest_nodes, wake

    repo = args.repo if args.repo is not None else Path.cwd()
    result = wake(
        agent=args.agent,
        task=args.task,
        budget_tokens=args.budget_tokens,
        scopes=args.scopes,
        repo=repo,
        include_sensitive=args.include_sensitive,
        review_state=args.review_state,
        include_unreviewed=args.include_unreviewed,
        include_promoted=args.include_promoted,
        include_imported=args.include_imported,
        exclude_nodes=(
            manifest_nodes(args.exclude_nodes) if args.exclude_nodes else frozenset()
        ),
    )
    if args.format == "markdown":
        return {"status": "ok", "_text": result.render_markdown()}
    return result.to_json(generated_at=utc_now() if args.generated_at else None)


def _index_command(args: argparse.Namespace) -> dict[str, Any]:
    store = _open(args)
    if not store.root.is_dir():
        raise RecordsError(f"no store at {store.root}", code="not_found")
    index = store.open_index()
    if args.index_command == "rebuild":
        return {"status": "ok", "rebuilt": index.rebuild()}
    if args.index_command == "check":
        return index.compare()
    changes = index.reconcile()
    return {"status": "ok", **changes}


def _actor(args: argparse.Namespace) -> str:
    return args.actor or default_actor()


def _read_json(source: str) -> Any:
    try:
        raw = sys.stdin.read() if source == "-" else Path(source).read_text("utf-8")
    except OSError as exc:
        raise RecordsError(f"cannot read {source}: {exc}", code="io_error") from None
    try:
        return loads_strict(raw)
    except ValueError as exc:
        raise RecordsError(
            f"{source} is not valid JSON: {exc}", code="invalid_json"
        ) from None


def _document(args: argparse.Namespace, *, actor: str) -> dict[str, Any]:
    document: dict[str, Any] = {}
    if getattr(args, "file", None):
        loaded = _read_json(args.file)
        if not isinstance(loaded, dict):
            raise RecordsError(
                "a record document must be a JSON object", code="invalid_record"
            )
        document = dict(loaded)
    overrides = {
        "schema_ref": getattr(args, "schema", None),
        "summary": getattr(args, "summary", None),
        "tags": getattr(args, "tags", None),
        "sensitivity": getattr(args, "sensitivity", None),
        "review_state": getattr(args, "review_state", None),
    }
    document.update(
        {key: value for key, value in overrides.items() if value is not None}
    )
    if getattr(args, "origin_kind", None):
        document["origin"] = {"kind": args.origin_kind, "actor_id": actor}
    return document


def _confirm_policy(args: argparse.Namespace) -> None:
    if args.yes:
        return
    if not sys.stdin.isatty():
        raise RecordsError(
            "schema policy set is a human operation and needs an interactive "
            "terminal to confirm; a person may pass --yes instead",
            code="confirmation_required",
        )
    prompt = (
        f"Set the promotion policy of {args.name} to source={args.source}, "
        f"status={args.status}, confidence={args.confidence}? [y/N] "
    )
    print(prompt, end="", file=sys.stderr, flush=True)
    answer = sys.stdin.readline().strip().lower()
    if answer not in ("y", "yes"):
        raise RecordsError("not confirmed; nothing changed", code="not_confirmed")


def _describe(
    store: RecordStore, schema: RegisteredSchema, *, include_schema: bool = False
) -> dict[str, Any]:
    out = schema.to_json(include_schema=include_schema)
    try:
        record = store.schemas.rules_record(schema.ref)
    except RecordsError as exc:
        out["rules_error"] = {"code": exc.code, "message": str(exc)}
        return out
    out["rules"] = record["rules"] if record else {}
    out["rules_sha256"] = record["rules_sha256"] if record else None
    return out


def _schema_command(args: argparse.Namespace) -> dict[str, Any]:
    if args.schema_command == "templates":
        return {"status": "ok", "templates": template_names()}
    store = _open(args)
    if args.schema_command == "register":
        actor = _actor(args)
        if args.template:
            document = load_template(args.template)
        else:
            document = _read_json(str(args.path))
        outcome = store.register_schema(
            document,
            actor=actor,
            name=args.name,
            version=args.schema_version,
            rules=_rules_from_args(args, None),
        )
        return {
            "status": "ok",
            "registered": outcome.new,
            "rules": outcome.rules,
            "schema": _describe(store, outcome.schema),
        }
    if args.schema_command == "list":
        rows = []
        for ref, loaded in store.schemas.iter_checked():
            if isinstance(loaded, RecordsError):
                rows.append(
                    {
                        "schema_ref": ref,
                        "error": {"code": loaded.code, "message": str(loaded)},
                    }
                )
            else:
                rows.append(_describe(store, loaded))
        failed = any("error" in row for row in rows)
        return {"status": "error" if failed else "ok", "schemas": rows}
    if args.schema_command == "show":
        found = store.schemas.get(store.schemas.resolve_ref(args.ref))
        return {"status": "ok", "schema": _describe(store, found, include_schema=True)}
    if args.schema_command == "rules":
        ref = store.schemas.resolve_ref(args.ref)
        if args.rules_command == "show":
            record = store.schemas.rules_record(ref)
            return {
                "status": "ok",
                "schema_ref": ref,
                "rules": record["rules"] if record else {},
                "rules_sha256": record["rules_sha256"] if record else None,
                "set_at": record["set_at"] if record else None,
                "set_by": record["set_by"] if record else None,
                "log": store.schemas.rules_log(ref),
            }
        rules = _rules_from_args(args, store.schemas.rules(ref))
        if rules is None:
            raise RecordsError("give --file, a rule option, or --unset", code="usage")
        return {"status": "ok", **store.set_rules(ref, rules, actor=_actor(args))}
    if args.schema_command == "policy":
        if args.policy_command == "show":
            return {"status": "ok", **store.policies.show(args.name)}
        _confirm_policy(args)
        result = store.policies.set(
            args.name,
            source=args.source,
            status=args.status,
            confidence=args.confidence,
            actor=_actor(args),
            at=store.now(),
        )
        return {"status": "ok", **result}
    raise RecordsError(f"unknown schema command {args.schema_command!r}", code="usage")


def _dispatch(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "schema":
        return _schema_command(args)
    if args.command == "wake":
        return _wake(args)
    if args.command == "index":
        return _index_command(args)
    if args.command == "consolidate":
        return _consolidate_command(args)
    store = _open(args)
    if args.command == "recall":
        result = store.recall(
            args.query,
            schema=args.schema,
            tags=args.tags,
            since=args.since,
            until=args.until,
            review_state=args.review_state,
            include_retracted=args.include_retracted,
            include_superseded=args.include_superseded,
            include_sensitive=args.include_sensitive,
            agent=args.agent,
            limit=args.limit,
            full=args.full,
        )
        if args.format == "text":
            return {"status": "ok", "_text": result.render_text()}
        return result.to_json()
    actor = _actor(args)
    if args.command == "add":
        if not args.file:
            raise RecordsError("add needs --file", code="usage")
        result = store.create(
            _document(args, actor=actor), actor=actor, event_id=args.event_id
        )
        return {"status": "ok", **result.to_json()}
    if args.command == "amend":
        result = store.amend(
            args.record_id,
            _document(args, actor=actor),
            expected_revision=args.expect_revision,
            actor=actor,
            event_id=args.event_id,
        )
        return {"status": "ok", **result.to_json()}
    if args.command == "supersede":
        document = None
        if args.file:
            document = _document(args, actor=actor)
        result = store.supersede(
            args.record_id,
            expected_revision=args.expect_revision,
            actor=actor,
            by=args.by,
            document=document,
            reason=args.reason,
            event_id=args.event_id,
        )
        return {"status": "ok", **result}
    if args.command == "retract":
        result = store.retract(
            args.record_id,
            expected_revision=args.expect_revision,
            reason=args.reason,
            actor=actor,
            event_id=args.event_id,
        )
        return {"status": "ok", **result.to_json()}
    if args.command == "show":
        record = store.get(args.record_id)
        return {
            "status": "ok",
            "record": record.envelope_json(),
            "state": record.state_json(),
        }
    if args.command == "history":
        return {
            "status": "ok",
            "record_id": args.record_id,
            "events": store.history(args.record_id),
        }
    if args.command == "list":
        rows, errors = [], []
        for item in store.iter_records():
            if isinstance(item, RecordsError):
                errors.append(
                    {
                        "record_id": item.record_id,
                        "code": item.replay_code,
                        "detail": item.detail,
                    }
                )
            else:
                rows.append(
                    {
                        "record_id": item.record_id,
                        "revision": item.revision,
                        "schema_ref": item.schema_ref,
                        "lifecycle": item.lifecycle,
                        "review_state": item.review_state,
                        "summary": item.summary,
                    }
                )
        return {
            "status": "error" if errors else "ok",
            "records": rows,
            "replay_errors": errors,
        }
    if args.command == "erase":
        result = store.erase(
            args.record_id, reason=args.reason, actor=actor, force=args.force
        )
        return {"status": "ok", **result}
    if args.command == "doctor":
        if args.force_tmp and not args.fix:
            raise RecordsError("--force-tmp needs --fix", code="usage")
        return store.doctor(fix=args.fix, force_tmp=args.force_tmp, actor=actor)
    if args.command == "export":
        from akms_records.portable import export_records

        exporter = f"akms-records {__version__}"
        if args.output and args.output != "-":
            output = Path(args.output)
            partial = output.with_name(output.name + ".partial")
            with partial.open("w", encoding="utf-8", newline="\n") as handle:
                summary = export_records(
                    store,
                    handle,
                    include_sensitive=args.include_sensitive,
                    skip_broken=args.skip_broken,
                    exporter=exporter,
                )
            os.replace(partial, output)
            return {**summary, "output": str(output)}
        # The JSONL goes to stdout, so the summary goes to stderr.
        summary = export_records(
            store,
            sys.stdout,
            include_sensitive=args.include_sensitive,
            skip_broken=args.skip_broken,
            exporter=exporter,
        )
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True), file=sys.stderr)
        return {"status": summary["status"], "_quiet": True}
    if args.command == "import":
        return _import_command(args, store, actor=actor)
    if args.command == "promote":
        from akms_records.bridge import promote

        return promote(
            store,
            args.record_id,
            review=args.review,
            repo=args.repo if args.repo is not None else Path.cwd(),
            actor=actor,
            min_review_state=args.min_review_state,
            scope_ok=args.scope_ok,
            allow_sensitive=args.allow_sensitive,
            allow_imported=args.allow_imported,
            update=args.update,
            domain=args.domain,
        )
    raise RecordsError(f"unknown command {args.command!r}", code="usage")


def _import_command(
    args: argparse.Namespace, store: RecordStore, *, actor: str
) -> dict[str, Any]:
    if (args.path is None) == (args.from_failure_memory is None):
        raise RecordsError(
            "give exactly one of an export file or --from-failure-memory",
            code="usage",
        )
    if args.path is not None:
        if args.failure_memory_repo is not None:
            raise RecordsError(
                "--failure-memory-repo needs --from-failure-memory", code="usage"
            )
        from akms_records.portable import import_records

        return import_records(store, args.path, actor=actor)
    from akms_records.failure_memory import import_failure_memory

    root = args.failure_memory_repo or args.repo or Path.cwd()
    return import_failure_memory(
        store, args.from_failure_memory, repo=root, actor=actor
    )


def _print_error(error: RecordsError, as_json: bool) -> None:
    if as_json:
        print(json.dumps(error.to_json(), ensure_ascii=False, sort_keys=True))
    else:
        print(f"error[{error.code}]: {error}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = _dispatch(args)
    except RecordsError as exc:
        _print_error(exc, args.json_errors)
        return 2
    except Exception as exc:  # noqa: BLE001 - the CLI reports every failure the same way
        _print_error(RecordsError(str(exc), code="internal_error"), args.json_errors)
        return 2
    finally:
        while _OPENED:
            _OPENED.pop().close()
    text = result.pop("_text", None)
    if text is not None:
        sys.stdout.write(text)
    elif not result.pop("_quiet", False):
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") not in {"error", "drift"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
