# Record schemas and templates

!!! warning "Experimental"
    The registration rules and the `x-akms-records` block may change before a
    stable release.

A schema describes a record's **payload**. It is a JSON Schema
[Draft 2020-12](https://json-schema.org/draft/2020-12) document whose root is
`"type": "object"`. Schemas are registered per store root, under `name/vN`.

## Registering

```bash
akms-records schema register ./research-decision.schema.json --scope project:example
akms-records schema register --template idea --scope project:example
```

Registration stores the schema's canonical JSON and the SHA-256 of it. Every
record written against the schema carries that digest. Loading a schema
recomputes it, and a schema whose content no longer matches is refused
(`schema_tampered`); a formatting-only edit keeps the digest. Registering the
same content again does nothing. Different content under an existing
`name/vN` is refused: register it as `name/v(N+1)`. Records keep the schema
version they were written with.

## What a schema may contain

- Required fields, types, enums, nested objects and arrays.
- References to its own definitions: `{"$ref": "#/$defs/source"}`.

Refused at registration, by a static scan of the whole document:

- any `$ref` or `$dynamicRef` that is not a local `#...` pointer, including
  `http:`, `https:` and `file:` references and relative file names;
- `$id` anywhere, which would change how references resolve;
- `$schema` other than `https://json-schema.org/draft/2020-12/schema`, or
  anywhere but the root; `$vocabulary`;
- top-level `properties` named like an envelope field (`record_id`,
  `revision`, `schema_ref`, `schema_sha256`, `scope`, `recorded_at`,
  `origin`, `source_refs`, `summary`, `tags`, `sensitivity`, `review_state`,
  `lifecycle`, `payload`).

Validation never fetches anything either: every validator gets a reference
registry that refuses all URIs, so even a reference the scan missed fails
instead of reaching the network or the filesystem.

`format` is an annotation only. No format checker runs, so a record validates
the same way on every machine whatever optional packages are installed.

## The `x-akms-records` block

A schema may carry its name, version and extraction rules:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["decision", "rationale"],
  "properties": {
    "decision": {"type": "string"},
    "rationale": {"type": "string"},
    "decided_at": {"type": "string", "format": "date-time"}
  },
  "x-akms-records": {
    "name": "research-decision",
    "version": 1,
    "title": "Research decision",
    "rules": {
      "search_text": ["/decision", "/rationale"],
      "label": "/decision",
      "time_field": "/decided_at",
      "summary_template": "Decision: {decision}"
    }
  }
}
```

The block is part of the schema, so it is covered by the digest. If it gives
no name or version, pass `--name` and `--version`.

| Rule | Value | Use |
|---|---|---|
| `search_text` | JSON pointers into the payload | Fields to index as full text |
| `label` | a JSON pointer | A short display label |
| `time_field` | a JSON pointer to a string property | The record's own time, as opposed to when it was recorded |
| `summary_template` | text with `{field}` or `{/json/pointer}` placeholders; `{{` and `}}` for literal braces | Fills `summary` when a create gives none |

Every pointer must name a property the schema declares (following local
`$ref`s). Placeholders cannot call methods, index, or format: `{a.b}`,
`{a[0]}` and `{a!r}` are refused. Rules are data; nothing in a schema runs.
This release validates and stores the rules and uses `summary_template`;
`search_text`, `label` and `time_field` are for the index a later release
adds.

## Built-in templates

The templates are plain schema files shipped in `akms_records/templates/`.
They are examples, not privileged types; copy and change them freely (under a
new name).

| Template | Required fields | Summary |
|---|---|---|
| `decision` | `decision`, `rationale` | `Decision: {decision}` |
| `experiment-observation` | `experiment`, `observation` | `{experiment}: {observation}` |
| `research-finding` | `claim`, `evidence` | `Finding: {claim}` |
| `idea` | `idea` | `Idea: {idea}` |
| `preference` | `subject`, `preference` | `{subject}: {preference}` |
| `successful-approach` | `task`, `approach` | `Worked for {task}: {approach}` |
| `failed-approach` | `task`, `approach`, `failure` | `Failed for {task}: {approach}` |
| `workflow-lesson` | `lesson` | `Lesson: {lesson}` |

`akms-records schema show <name> --scope ...` prints a registered template in
full. All templates set `additionalProperties: false`.

## The envelope

| Field | Set by | Values |
|---|---|---|
| `record_id`, `revision` | the store | see [storage format](storage-format.md) |
| `schema_ref`, `schema_sha256` | writer, store | `name/vN`; the registered digest |
| `scope` | the request | `{"kind": "project"\|"agent"\|"shared", "id": ...}` |
| `recorded_at` | the store | time of the create event (UTC) |
| `origin` | writer | `{"kind": "human"\|"human-confirmed"\|"agent"\|"tool"\|"import", "actor_id": ...}`; default `agent` |
| `source_refs` | writer | `[{"kind": "issue", "ref": "#42", "note": "..."}]` |
| `summary` | writer or template | one line of text |
| `tags` | writer | distinct short strings without spaces |
| `sensitivity` | writer | `public`, `internal` (default), `sensitive` |
| `review_state` | writer | `unreviewed` (default), `agent_reviewed`, `user_confirmed`, `rejected` |
| `lifecycle` | the store | `active`, `superseded`, `retracted` |
| `payload` | writer | validated against the schema |

Source references are recorded as given. A missing or wrong reference stays
visible; it is never upgraded into verified evidence.

## Promotion policy

A person may give a schema a promotion policy:

```bash
akms-records schema policy set research-decision --scope project:example \
  --source human --status established --confidence 0.8
akms-records schema policy show research-decision --scope project:example
```

The policy is stored beside the schema (`_schemas/<name>/_policy.json`), not
in it, so setting or changing it never needs a new schema version and never
changes existing records. Every change is appended to `_policy_log.jsonl` with
the actor, the time and the previous value. Without a policy the default is
`source: agent`, `status: tentative`. An agent-sourced policy can never be
`established`.

This release only stores policies. Promotion into AKMS project-local nodes,
which will apply them only to human-confirmed records with explicit approval,
is not implemented yet.
