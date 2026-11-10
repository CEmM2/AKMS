# Authoring, search and review

These workflows work with **your registered JSON Schema**. They prescribe no
record kinds or writing policy. Bundled templates are optional examples, not a
prerequisite. Nothing captures conversations, runs at startup, or promotes a
record automatically.

## Discover the schema, then draft

Register your schema using `schema register`, then inspect it and its extraction
rules. Examples below use a schema named `observation` that **you have defined**;
replace its name, scope and payload fields with your own.

```bash
akms-records schema list --scope project:example
akms-records schema show observation --scope project:example
akms-records schema rules show observation --scope project:example
akms-records draft --schema observation --scope project:example
```

`draft` returns `document`, `schema_ref`, `schema_sha256`, `valid`, `errors` and
`missing_fields`. The schema name is pinned to its current version. No record
is written. The payload starts empty unless you supply values. Defaults, enum
choices and example values in the schema are **not** inserted as facts.

For a file you can edit directly:

```bash
akms-records draft --schema observation --scope project:example \
  --format document > draft.json
# Fill draft.json with known values and a summary if required.
akms-records validate --scope project:example --file draft.json
akms-records add --scope project:example --file draft.json --event-id observation-001
```

`--format document` emits only the writer document, not the validation report.
Drafting succeeds even when the draft is incomplete. `validate` exits 0 if valid,
1 if invalid, or 2 for an execution error (such as an unknown schema). Invalid
reports include required-field JSON pointers, for example `/payload/measurement`
and `/summary`, plus schema validation errors. Pointers escape `~` and `/` using
JSON Pointer rules. Local references and conditional requirements are validated;
remote references are never fetched. A union such as `oneOf` reports the failed
constraint, rather than pretending every branch's fields are mandatory. Read
the full schema and errors instead of treating the pointer list as a complete form.

Use `--file -` to read a writer document from stdin. When you already have a
payload-only JSON file, `draft`, `validate`, `add` and `amend` accept `--payload`:

```bash
akms-records validate --scope project:example --schema observation \
  --payload payload.json --summary "A summary supported by the supplied evidence"
akms-records add --scope project:example --schema observation \
  --payload payload.json --summary "A summary supported by the supplied evidence"
```

`--file` and `--payload` are mutually exclusive. Existing envelope flags apply
with either input. `amend --payload` replaces the **whole** payload, not a nested
merge. Validation is a creation preflight, not an amendment validator, and does
not reserve a schema or guarantee a later write. `add` still validates normally.

Unknown facts should remain unknown: ask for them, or leave the draft incomplete.
A schema-valid record is not necessarily true. The caller remains responsible
for evidence, source references, sensitivity and authorization to save it.

## Search and inspect

`search` is an alias of `recall` with all the same scope, privacy and ranking
behavior. Both accept positional text as an alternative to `--query`:

```bash
akms-records search "mesh experiment" --scope project:example --format text
akms-records search "mesh experiment" --scope project:example --schema observation --full
akms-records show RECORD_ID --scope project:example --format text
```

JSON remains the default for automation. Human `show --format text` displays
the ID, revision, schema and review state followed by the full JSON record,
including payload and source references. A search match is a lead, not a review
of the full record. See [recall](recall-and-wake.md) for search details.

## Review a specific revision

```bash
akms-records review queue --scope project:example --format text
akms-records review queue --scope project:example --schema observation --limit 10
akms-records show RECORD_ID --scope project:example
akms-records review set RECORD_ID --scope project:example \
  --state agent_reviewed --expect-revision 1 --actor reviewer --event-id review-001
```

The queue scans source files, so it works without an index. It returns active
records in exactly the requested state (`unreviewed` by default), oldest first,
with full payloads. Sensitive records require `--include-sensitive`. Use
`--state agent_reviewed`, `user_confirmed` or `rejected` to inspect that state.
Unlike recall's minimum-state filter, this filter is exact. JSON includes `total`
and `has_more` after filtering, plus any `replay_errors`. The text display also
includes these scan results. A damaged record makes the result exit 1; do not
mistake a partial scan for an empty or complete queue.

`review set` changes only review state through an ordinary audited amendment.
It needs the revision you inspected; concurrent changes fail with
`stale_revision`. Read the changed record and review again before retrying.
Repeated writes with the same event ID are idempotent. Review never changes the
payload, promotes a record, or updates an AKMS node.

`user_confirmed` records a caller's assertion that a person confirmed the
inspected content. It is **not authentication**. Agents must not select it simply
to clear a queue. `rejected` expresses rejection, not deletion. For a content
correction, use `amend` first and review the resulting revision separately.

## Python and agent use

```python
from akms_records.workflows import (
    draft_document, validate_document, review_queue, review_record,
)

report = draft_document(store, "observation", document={"payload": known_values})
validation = validate_document(store, completed_document)
queue = review_queue(store, schema="observation", limit=10)
result = review_record(
    store, record_id, state="agent_reviewed", expected_revision=revision,
    actor="reviewer", event_id="review-001",
)
```

The installable `akms-records` package bundles an opt-in schema-neutral skill at
`akms_records/skills/akms-records/SKILL.md`. Retrieve it without relying on the
source checkout:

```python
from importlib.resources import files
skill_text = files("akms_records").joinpath("skills/akms-records/SKILL.md").read_text()
```

Copy it into your agent host's skill directory if desired; installing the package
does not install hooks or enable automatic capture. It describes discovery,
explicit authoring, search, revision-checked review and the boundary to promotion.
