"""The ``akms-records`` command-line interface (experimental).

Every command prints one JSON object on stdout. Exit status: 0 on success,
1 when the result's ``status`` is ``error`` or ``drift`` (for example
``doctor`` found problems, or ``import`` met a conflict), and 2 when the
command failed; the error goes to stderr as ``error[<code>]: <message>``, or
to stdout as JSON with ``--json-errors``.
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
from akms_records.canonical import loads_strict
from akms_records.envelope import ORIGIN_KINDS, REVIEW_STATES, SENSITIVITY_LEVELS
from akms_records.errors import RecordsError
from akms_records.policy import POLICY_SOURCES, POLICY_STATUSES
from akms_records.schemas import load_template, template_names
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
    listing = schema_sub.add_parser("list", help="registered schemas")
    _store_options(listing)
    show = schema_sub.add_parser("show", help="one registered schema")
    _store_options(show)
    show.add_argument("ref", help="<name>/v<N>, or <name> for the newest version")
    schema_sub.add_parser("templates", help="the built-in templates")
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

    doctor = sub.add_parser("doctor", help="check and clean the store root")
    _store_options(doctor)
    doctor.add_argument(
        "--check", action="store_true", help="report only; change nothing"
    )
    doctor.add_argument(
        "--force-tmp",
        action="store_true",
        help="remove every temp file; only when no writer is running",
    )

    export = sub.add_parser("export", help="write the scope as portable JSONL")
    _store_options(export)
    export.add_argument("--output", "-o", help="file to write (default: stdout)")
    export.add_argument("--include-sensitive", action="store_true")
    export.add_argument("--skip-broken", action="store_true")

    imported = sub.add_parser("import", help="replay a JSONL export into the scope")
    _store_options(imported)
    imported.add_argument("path", type=Path)
    return parser


def _open(args: argparse.Namespace) -> RecordStore:
    scope = Scope.parse(args.scope)
    repo = args.repo if args.repo is not None else Path.cwd()
    return RecordStore.open(scope, repo=repo if scope.kind == "project" else None)


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
        registered, new = store.register_schema(
            document, actor=actor, name=args.name, version=args.schema_version
        )
        return {"status": "ok", "registered": new, "schema": registered.to_json()}
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
                rows.append(loaded.to_json())
        failed = any("error" in row for row in rows)
        return {"status": "error" if failed else "ok", "schemas": rows}
    if args.schema_command == "show":
        found = store.schemas.get(store.schemas.resolve_ref(args.ref))
        return {"status": "ok", "schema": found.to_json(include_schema=True)}
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
    store = _open(args)
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
        return store.doctor(fix=not args.check, force_tmp=args.force_tmp)
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
        from akms_records.portable import import_records

        return import_records(store, args.path, actor=actor)
    raise RecordsError(f"unknown command {args.command!r}", code="usage")


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
    if not result.pop("_quiet", False):
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") not in {"error", "drift"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
