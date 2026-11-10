# akms-records

> **Experimental.** The storage format, Python API and CLI may change before
> a stable release. Do not rely on them for data you cannot re-create.

A schema-driven, provenance-aware record store for AKMS. It keeps typed
experiences and observations (decisions, research findings, failed and
successful approaches, preferences, ideas, workflow lessons) as an append-only
history of plain files.

- **Open payload, fixed envelope.** You register JSON Schemas (Draft 2020-12)
  for your payloads. A fixed envelope carries identity, schema reference and
  digest, scope, time, origin, source references, summary, tags, sensitivity,
  review state and lifecycle. Payloads cannot shadow envelope fields.
- **Git-mergeable history.** One directory per record and one immutable file
  per revision, hash-chained and sealed. Work on different records merges
  without conflicts; a conflict on the same record is detected, never resolved
  silently.
- **No lock, no network, no LLM.** Writes use an exclusive hard link, schema
  references never leave the schema, and nothing calls a provider unless you
  hand `consolidate` one.
- **Fast recall and wake.** A derived, rebuildable SQLite FTS5 index answers
  scoped `recall` and token-budgeted `wake`, rendering record text as fenced
  data under a fixed layout.
- **Source-linked summaries (opt-in).** `consolidate` writes topic summaries
  whose every assertion cites the record revisions it came from; they turn
  stale when a source changes. Extractive by default; a provider can be a
  callable or an external command.
- **Explicit promotion.** With the `[akms]` extra, `promote` writes a reviewed
  record as an AKMS project-local node, never to the global vault. A promoted
  record then leaves `wake`, because the loadout serves its node.
- **A read-only failure-memory importer.** `import --from-failure-memory` reads a
  registry into records, writes nothing back and needs no other package.
- **Host-neutral.** Without the extra it does not need or import `akms`.

A record is not a fact: records stay records unless a person promotes them.

## Requirements

- Python `>=3.12,<3.13`
- `jsonschema` and `referencing`
- SQLite with FTS5 in Python's `sqlite3` (standard builds) for `recall` and
  `wake`
- A filesystem with hard links (any local disk on Linux, macOS and Windows)
- Optional: the `qmd` command and its embedding model, for `recall --semantic`

## Explicit authoring and review

Start with your own registered schema. `draft` prepares an editable document
without inventing values; `validate` reports missing fields without saving.
`search` accepts plain text, and `review queue` / `review set` support explicit,
revision-checked review. JSON remains the default; `show` and the queue also
offer `--format text`. See the [workflow guide](https://cemm2.github.io/AKMS/reference/records/authoring-and-review.html).
The package includes an opt-in, schema-neutral agent skill; it installs no hooks.

## First commands

```bash
pip install akms-records

akms-records schema register --template decision --scope project:example
akms-records add --scope project:example --schema decision/v1 --file decision.json
akms-records list --scope project:example
akms-records show rec-20261103-k3f9m2xa --scope project:example
akms-records recall --scope project:example --query surrogate
akms-records wake --agent scout --task "review the model" --budget-tokens 1200 \
  --scope project:example
akms-records doctor --scope project:example
```

`decision.json`:

```json
{
  "payload": {
    "decision": "Keep the existing surrogate model",
    "rationale": "Its validation error is within budget"
  },
  "tags": ["surrogate"]
}
```

Project-scope records live in `<repo>/.knowledge/records/` and are meant to be
committed. Agent and shared scopes live under `~/.knowledge/records/`
(override with `AKMS_RECORDS_HOME`).

Documentation: <https://cemm2.github.io/AKMS/reference/records/index.html>
