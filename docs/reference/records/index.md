# Records (experimental)

!!! warning "Experimental"
    `akms-records` is an experimental package. Its storage format, Python API
    and CLI may change before a stable release. Keep data you cannot re-create
    elsewhere as well.

`akms-records` is an optional, independently installable record store for
agents and people working with AKMS. It keeps typed experiences and
observations (decisions, research findings, successful and failed approaches,
preferences, ideas, workflow lessons) as an append-only history of plain JSON
files.

A record is **not** a fact. It is something someone recorded, with its origin,
sources and review state. Records stay records until a person approves one for
[promotion](promotion-and-import.md) into an AKMS project-local node.

## What it gives you

- **Your own schemas.** Register JSON Schema (Draft 2020-12) documents for
  record payloads, or start from eight built-in
  [templates](schemas-and-templates.md). No AKMS source changes needed.
- **A fixed envelope.** Every record carries the same AKMS-controlled fields:
  ID, revision, schema reference and digest, scope, time, origin, source
  references, summary, tags, sensitivity, review state and lifecycle. A
  payload cannot shadow them.
- **History, not edits.** Changes append `create`, `amend`, `supersede` and
  `retract` events. The current state is a replay of those events.
- **Git-friendly project memory.** Project records are files inside the
  repository. Parallel work on different records merges without conflicts; a
  conflict on the same record is detected and reported, never resolved
  silently. See the [storage format](storage-format.md).
- **Safe writes without a lock.** Each revision is linked into place
  exclusively, so two writers can never both win the same revision, and a
  crashed writer leaves only a temp file that `doctor --fix` removes.
- **Portable.** `export` and `import` move a scope as JSONL with digest checks.
- **Fast recall and wake.** A derived SQLite index (FTS5) answers scoped
  `recall` queries and a token-budgeted `wake` for an agent starting a task,
  with provenance on every result and record text rendered as fenced data.
  It is never committed, catches up with git checkouts and merges on its own,
  and can always be rebuilt. See [recall and wake](recall-and-wake.md) and the
  [search index](search-index.md).

- **Source-linked summaries (opt-in).** `consolidate` writes topic summaries
  whose every assertion cites the record revisions it came from. The default
  method is extractive and uses no model; a provider can be plugged in as a
  callable or a command. A summary turns stale when a source changes, and is
  erased with any source that is erased. See [consolidation](consolidation.md).

- **Explicit promotion and a read-only importer.** `promote` writes a reviewed
  record as an AKMS project-local node, never to the global vault, and
  `import --from-failure-memory` reads a failure-memory registry into records
  without writing back. See [promotion and import](promotion-and-import.md).

## Install

```bash
pip install akms-records
akms-records --help
```

The package needs Python `>=3.12,<3.13`, `jsonschema` and `referencing`. It
does not depend on `akms`. Only [`promote`](promotion-and-import.md) needs it,
through the extra:

```bash
pip install 'akms-records[akms]'
```

## Scopes and where records live

Every command names a scope with `--scope kind:id`.

| Scope | Store root | Typical use |
|---|---|---|
| `project:<id>` | `<repo>/.knowledge/records/` (or `<repo>/knowledge/records/` in a repository that only has `knowledge/`) | Committed with the project |
| `agent:<id>` | `~/.knowledge/records/agent/<id>/` | One agent's own memory |
| `shared:<id>` | `~/.knowledge/records/shared/<id>/` | Shared by several agents on one machine |

`AKMS_RECORDS_HOME` replaces `~/.knowledge/records` for agent and shared
scopes. Project scope uses `--repo` (default: the current directory).

Scope isolation is enforced by the API: a store opened for one scope refuses
to read or write another scope's records. It is a rule for cooperating agents,
not a security boundary; see [limits](limits.md).

## A first session

```bash
akms-records schema register --template decision --scope project:example

cat > decision.json <<'JSON'
{
  "payload": {
    "decision": "Keep the existing surrogate model",
    "rationale": "Its validation error is within budget",
    "alternatives": ["Train a new architecture"]
  },
  "tags": ["surrogate"],
  "source_refs": [{"kind": "issue", "ref": "#42"}]
}
JSON

akms-records add --scope project:example --schema decision/v1 --file decision.json
# {"event_id": "...", "kind": "create", "noop": false,
#  "record_id": "rec-20261103-k3f9m2xa", "revision": 1, "status": "ok"}

akms-records amend rec-20261103-k3f9m2xa --scope project:example \
  --expect-revision 1 --review-state user_confirmed
akms-records show rec-20261103-k3f9m2xa --scope project:example
akms-records history rec-20261103-k3f9m2xa --scope project:example
akms-records recall --scope project:example --query surrogate
akms-records wake --agent scout --task "review the surrogate model" \
  --budget-tokens 1200 --scope project:example --format markdown
akms-records doctor --scope project:example   # reports; --fix repairs
```

Commit `.knowledge/records/` with the rest of the repository.

## Python API

```python
from akms_records import RecordStore
from akms_records.schemas import load_template

store = RecordStore.open("project:example", repo=".")
store.register_schema(load_template("decision"), actor="me")
created = store.create(
    {"schema_ref": "decision/v1",
     "payload": {"decision": "Keep it", "rationale": "Works"}},
    actor="me",
    event_id="decision-keep-it",  # retrying with this ID writes nothing
)
record = store.get(created.record_id)
store.amend(created.record_id, {"tags": ["model"]},
            expected_revision=record.revision, actor="me")
hits = store.recall("keep", tags=["model"]).hits
```

## Pages

- [CLI reference](cli-reference.md)
- [Recall and wake](recall-and-wake.md)
- [Consolidation](consolidation.md)
- [Search index](search-index.md)
- [Storage format](storage-format.md)
- [Schemas and templates](schemas-and-templates.md)
- [Limits](limits.md)

- [Authoring, search and review](authoring-and-review.md): schema-aware drafts,
  no-write validation, explicit review and the bundled agent workflow.
