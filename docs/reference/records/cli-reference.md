# Records CLI reference

!!! warning "Experimental"
    Command names and output fields may change before a stable release.

```text
akms-records [--version] [--json-errors] <command> ...
```

## Conventions

- **Output.** Every command prints one JSON object on stdout with a `status`
  field. `export` without `--output` prints the JSONL on stdout and its
  summary on stderr.
- **Exit status.** `0` on success; `1` when `status` is `drift` or `error`
  (for example `doctor` found problems, or `import` met a conflict); `2` when
  the command failed. A failure prints `error[<code>]: <message>` on stderr,
  or `{"status": "error", "error": {"code": ..., "message": ...}}` on stdout
  with `--json-errors`.
- **Scope.** Every command except `schema templates` takes
  `--scope project:<id>|agent:<id>|shared:<id>`, plus `--repo PATH` for
  project scope (default: the current directory).
- **Actor.** `--actor NAME` records who acted. The default is
  `$AKMS_RECORDS_ACTOR`, then the operating-system user name.
- **Idempotency.** Write commands take `--event-id ID`. Running the same
  write again with the same ID returns the first result with `"noop": true`
  and writes nothing. Without `--event-id` a random ID is used.
- **Revision preconditions.** `amend`, `supersede` and `retract` require
  `--expect-revision N`, the revision you last read. If the record has moved
  on, the command fails with `stale_revision` and writes nothing.

## Schemas

| Command | Purpose |
|---|---|
| `schema register PATH [--name N] [--version V]` | Register a schema file. Name and version come from the file's `x-akms-records` block or the flags. |
| `schema register --template NAME` | Register a built-in template. |
| `schema list` | Registered schemas, with an error entry for any that fail their digest check. |
| `schema show REF` | One schema with its content. `REF` is `name/vN`, or `name` for the newest version. |
| `schema templates` | Names of the built-in templates. |
| `schema policy set NAME --source human\|agent --status tentative\|established --confidence X [--yes]` | Set a schema's promotion policy. |
| `schema policy show NAME` | The current policy, the effective one (the default when none is set), and the change log. |

`schema policy set` is a **human operation**. It asks for confirmation on an
interactive terminal and refuses (`confirmation_required`) when standard input
is not a terminal. `--yes` skips the prompt for a person running it from a
script; an agent must never pass it. Every change is appended to the policy
log with the actor, the time and the previous value. An agent-sourced policy
cannot be `established`.

## Records

| Command | Purpose |
|---|---|
| `add --file DOC [--schema REF]` | Create a record. |
| `amend RECORD --expect-revision N [--file DOC]` | Amend fields; fields not given keep their value. |
| `supersede RECORD --expect-revision N (--by OTHER \| --file DOC [--schema REF]) [--reason TEXT]` | Mark a record superseded by an existing record, or by a new one created from `DOC`. |
| `retract RECORD --expect-revision N --reason TEXT` | Mark a record retracted. |
| `show RECORD` | The current state: `record` (envelope and payload) and `state` (update time, head digest, successor, reason). |
| `history RECORD` | Every event, oldest first. |
| `list` | The scope's records, by reading the files (no index yet), plus any that fail to replay. |

`add` and `amend` also take `--summary`, `--tag TAG` (repeatable),
`--sensitivity public|internal|sensitive`,
`--review-state unreviewed|agent_reviewed|user_confirmed|rejected` and
`--origin-kind human|human-confirmed|agent|tool|import`; these override the
document. The default origin is `agent` with the actor as `actor_id`.

A record document is a JSON object with any of `schema_ref`, `payload`,
`summary`, `tags`, `origin`, `source_refs`, `sensitivity` and `review_state`.
Payload fields go under `payload`. Fields the store sets (`record_id`,
`revision`, `schema_sha256`, `recorded_at`, `lifecycle`) are refused, and so
is a `scope` that differs from `--scope`. When `summary` is absent on create,
the schema's summary template fills it.

`supersede --file` creates the successor with the event ID `<event-id>.new`
and adds `{"kind": "supersedes", "ref": RECORD}` to its `source_refs`, so a
retry with the same `--event-id` repeats neither write. Only active records
can be amended, superseded or retracted.

## Maintenance

| Command | Purpose |
|---|---|
| `erase RECORD --reason TEXT [--force]` | Remove a record's files and log a content-free erasure line. |
| `doctor [--check] [--force-tmp]` | Check the store root and clean it up. |
| `export [--output FILE] [--include-sensitive] [--skip-broken]` | Write the scope as JSONL. |
| `import FILE` | Replay an export into the scope. |

**`erase`** writes `{record_id, scope, at, actor, reason}` to
`_erasures.jsonl` and then deletes the record directory. Never put protected
content in the reason. The result lists what erasure cannot reach (see
[limits](limits.md)). `--force` erases a record that does not replay and
whose scope cannot be read; a record that names another scope is never erased.

**`doctor`** covers every scope in the store root. By default it fixes what is
safe to fix and reports the rest; `--check` only reports.

| Fixed | Reported only |
|---|---|
| Temp files whose writer has exited (all of them with `--force-tmp`, safe only when no writer runs) | Replay errors: gaps, broken chains or seals, malformed events |
| Empty record directories older than a minute, and empty month directories | Git conflict markers (`conflicts`) |
| Erased records that came back, for example through a merge (`erasures_reapplied`) | Schemas that fail their digest check; records whose digest differs from the registry |
| | Stray files, non-canonical event bytes, policy files that disagree with their log |

`status` is `ok`, `drift` (only with `--check`: something needs fixing) or
`error` (something doctor never fixes).

**`export`** writes a header, every registered schema with its digest, the
scope's erasure lines, every event, and a footer with counts and a digest of
all preceding lines. Records whose current sensitivity is `sensitive` are left
out unless `--include-sensitive` is given. A scope with records that do not
replay is refused unless `--skip-broken` is given.

**`import`** checks the footer, schema digests, every event's seal and chain,
and every payload, before writing anything. It then registers missing
schemas, appends new erasure lines, and writes the missing event files.
Importing the same file again writes nothing. A record whose local history
diverges is reported under `conflicts` and left alone (`status: drift`). A
record in the local erasure log is never brought back. The export's scope must
equal `--scope`.

## Error codes

| Code | Meaning |
|---|---|
| `usage` | Missing or contradictory arguments |
| `invalid_scope`, `invalid_record_id`, `invalid_event_id` | Malformed identifiers |
| `invalid_record` | The record document breaks an envelope rule |
| `envelope_shadow` | A payload key or schema property reuses an envelope key |
| `payload_invalid` | The payload does not match its schema (`details.errors` lists paths) |
| `not_found`, `schema_not_found`, `template_not_found` | Nothing by that name in this store |
| `scope_violation` | The record belongs to another scope |
| `stale_revision` | `--expect-revision` is no longer the head; nothing written |
| `not_active` | The record is superseded or retracted |
| `event_id_reused` | The event ID was already used for a different kind of event, or in another scope |
| `replay_error` | The record's files do not replay (`details.replay_code` says why) |
| `invalid_schema`, `invalid_rules` | The schema or its extraction rules are not acceptable |
| `schema_ref_refused` | The schema has a non-local reference, `$id` or another dialect |
| `schema_exists` | That `name/vN` is registered with different content |
| `schema_tampered` | A registered schema no longer matches its digest |
| `invalid_policy`, `confirmation_required`, `not_confirmed` | Promotion-policy errors |
| `export_corrupt`, `digest_mismatch` | An export failed its integrity checks |
| `link_unsupported` | The filesystem has no hard links |
| `internal_error` | An unexpected failure |
