# Promotion and the failure-memory importer

!!! warning "Experimental"
    Command names, refusal codes and output fields may change before a stable
    release.

Records stay records until someone decides otherwise. This page covers the two
bridges to the rest of AKMS:

- [`promote`](#promote) writes a reviewed record as an AKMS **project-local**
  node. It needs the `akms-records[akms]` extra.
- [`import --from-failure-memory`](#import-from-failure-memory) reads an
  `akms-failure-memory` registry into records, read-only. It needs nothing else
  installed.

Neither calls an LLM. Neither writes to the global vault.

## promote

```text
akms-records promote RECORD --scope SCOPE [--repo PATH] [--actor NAME]
    --review approved
    [--min-review-state agent_reviewed|user_confirmed]
    [--scope-ok] [--allow-sensitive] [--allow-imported]
    [--update] [--domain DOMAIN]
```

`--review approved` is the explicit approval, and promotion is refused without
it. `--repo` names the project whose knowledge directory receives the node
(default: the current directory).

### Two paths

| Path | When | Written with | Labels |
|---|---|---|---|
| Default | No policy, an agent-sourced policy, or a record that is not `user_confirmed` | `update_graph` with a `NewKnowledge` | `source: agent`, `status: tentative`, `confidence: 0.50` |
| Human policy | The schema's [stored policy](schemas-and-templates.md#promotion-policy) is `source: human` and the record is `user_confirmed` | A validated `LocalNodeFrontmatter` file, then a graph rebuild | `source: human` with the policy's status and confidence |

The default path may report `dedup_appended` instead of `created`: `update_graph`
appends to a similar tentative node in the same domain when their similarity
exceeds its threshold. The record then links to that node. An agent-sourced
policy stays on this path, so its confidence does not raise the fixed `0.50`.

`promote` reads the policy and cannot change it. A policy file that disagrees
with its log is refused (`policy_drift`), since a change outside the log is what
the log exists to expose.

### What the node holds

The node's ID is the record ID, its title the record's label (or the start of
its summary), its tags the record's plus the schema name, and its domain the
scope's ID in lower case, unless `--domain` says otherwise. The body is:

- the record summary and a JSON rendering of the payload, each fenced, because
  [record text is data](recall-and-wake.md#rendering-is-data-not-instructions);
- a `Sources` section: record ID and revision (`rec-…@3`), schema reference and
  digest, scope, time, origin, review state, who promoted it, and the record's
  own source references.

The v2 node models have no field for a record ID, and they are unchanged. The
Sources section is the provenance.

### Refusals

Each is a typed error with exit status 2; nothing is written.

| Code | Why |
|---|---|
| `akms_unavailable` | `akms` is not installed: `pip install 'akms-records[akms]'` |
| `review_required` | `--review approved` was not given |
| `review_below_threshold` | The record is below the threshold. The default is `user_confirmed`; `--min-review-state agent_reviewed` lowers it, and nothing lowers it further |
| `scope_not_project` | The record is in an agent or shared scope; pass `--scope-ok` |
| `record_retracted`, `record_superseded`, `record_erased` | The record is not current |
| `schema_mismatch` | The schema is missing or tampered with, the record's digest differs, or the payload no longer validates |
| `record_sensitive` | The record is `sensitive`; pass `--allow-sensitive` |
| `summary_unreviewed`, `summary_stale` | A [summary](consolidation.md) below the threshold, or not currently valid |
| `imported_not_promotable` | An imported failure lesson; pass `--allow-imported` |
| `policy_drift` | The promotion policy disagrees with its log |
| `global_vault_target` | The knowledge directory overlaps the global vault |
| `already_promoted` | A newer revision of a promoted record; `details.node_id` names the node. Pass `--update` |
| `node_not_updatable` | `--update` met a node that left `tentative` and is not human-sourced |
| `node_exists` | The human path found a file with the node's name that does not hold this record |
| `source_refs_full` | The record has 64 source references, so the link would not fit |
| `promote_locked` | Another promote is running in this repository |
| `promote_graph_failed`, `promote_write_failed`, `node_not_loaded`, `promote_ledger_exhausted` | AKMS could not write or load the node. The record is unchanged, and a re-run is safe |

Why these defaults:

- **The threshold is `user_confirmed`.** The command says a person approved
  this, so the record should show it. A node also costs tokens in every loadout
  that selects it, so refusing is the cheap mistake.
- **Sensitive records need a flag.** Sensitive records are left out of recall,
  wake and exports by default. A node goes into loadouts and git, and `erase`
  cannot reach it.
- **Summaries need a review and must be valid.** A summary is `unreviewed` when
  written, and a provider's text can add claims. A stale one speaks for sources
  that have moved on. Its Sources section cites the summary, whose own assertions
  cite their revisions.
- **Imported lessons need a flag.** Failure-memory already compiles and routes
  them as nodes, so promoting one usually duplicates a node. With the flag, the
  threshold still applies: an import is no evidence of a review.

### Idempotency and newer revisions

| Run | Result |
|---|---|
| Same revision again | `already_promoted`, status `ok`: no second node, no second amend. `node_present` says whether the node file still exists; a node removed by hand is reported, not recreated |
| A newer revision | Refused with `already_promoted`, naming the node, because a node's readers may rely on what it said. `--update` appends the new revision to that node (action `updated`) and moves the link |
| A newer revision with `--update` on an agent node | Through `update_graph`'s exact-ID deduplication, while the node is `tentative` |
| A newer revision with `--update` on a human node | Appended directly. The node keeps its labels, whatever the policy now says |

### The link

`promote` ends with an `amend` event that adds one source reference:

```json
{"kind": "promoted-to", "ref": "<node_id>@<revision promoted>", "note": "default"}
```

`show` reports it as `state.promoted_to`. The kind is reserved: `add` and `amend`
refuse it (`reserved_source_ref`), and an amend that replaces the source
references keeps the link.

The link changes no content, so summaries that cite the record stay valid. It uses
the envelope's existing `source_refs`, so the event format and the envelope keys
are unchanged, existing records keep their bytes and seals, and export and import
carry the link like any other reference. See
[storage format](storage-format.md#promotion-links).

### If it crashes

The node is written first and the link last. A link without a node would drop the
record from `wake` with nothing serving it; a node without a link is found by
the next run.

| Crash | The next run |
|---|---|
| Before the node is written | Starts over |
| After the node, before `update_graph` finished its overlay or graph | Finds the node, rebuilds the graph, writes the link: action `link_completed` |
| After the graph, before the link | Finds the node, writes the link: action `link_completed` |
| After the link, before the result was printed | `already_promoted` |

The run finds the node by scanning `local-nodes` for the record's `Sources` line,
outside any code fence, so record text cannot forge it. Should a record be amended
between the crash and the next run, the node holds an older revision: that is
`already_promoted` again, and `--update` continues it.

`update_graph` skips a source its replay ledger already names. When the ledger
names a promotion but no node holds the record (the node was removed by hand before
the link), the bridge retries under a new source ID instead of reporting success.

### The global vault

`promote` writes under the project's knowledge directory only. It resolves the
vault as AKMS does (`AKMS_GLOBAL_VAULT`, the propagation config, then
`~/.claude/akms/nodes`), and refuses with `global_vault_target` when the knowledge
directory, `local-nodes` or `graph` overlaps it, following symlinks. Moving a node to
the global vault is a separate human action outside this package.

## import --from-failure-memory

```text
akms-records import --scope SCOPE [--repo PATH] [--actor NAME]
    --from-failure-memory CONFIG [--failure-memory-repo PATH]
```

`CONFIG` is a `failure-memory-project/v1` file. Its paths are relative to
`--failure-memory-repo`, which defaults to `--repo`. The registry may be schema 1
(one file) or schema 2 (a directory), with sequential or dated lesson IDs.

**Read-only.** It reads the config and the lessons, and opens nothing on that side
for writing: no lock, no generated file. Review annotations beside the lessons are
not lesson fields, and are not read.

**Its own reader.** This package parses the documented formats rather than import
`akms-failure-memory`, which would bring `akms` with it. The tests hold the reader
to that package's own loader, and the reader is strict: a lesson field the schema
does not know is refused, so a lesson never loses a field silently.

**The records.** Each lesson becomes a record of the built-in schema
`failure-lesson/v1`, registered on first use, whose payload is the lesson unchanged:

| Envelope field | Value |
|---|---|
| `source_refs` | `{"kind": "failure-lesson", "ref": "<lesson id>", "note": "<repository id>"}` |
| `origin` | `{"kind": "import", "actor_id": "failure-memory-import"}` |
| `review_state` | `unreviewed`: an import is no evidence of a review |
| `summary` | `<lesson id>: <symptom>` |
| `tags` | `failure-lesson`, plus the lesson's `area:`, `package:` and `module:` |

The name `failure-lesson` is reserved, as `consolidation` is.

**Re-running:**

| Upstream | Result |
|---|---|
| Same lesson, same content | No event (`unchanged`) |
| Changed lesson | An amend (`amended`), `unreviewed` again, since the review was of other text |
| New lesson | A new record (`created`) |
| Removed lesson | Reported (`removed_upstream`), not retracted. A missing lesson may be a checkout of another branch, and retracting is a decision for a person |
| The record was retracted or superseded here | Left alone (`skipped.inactive`) |
| The record was erased here | Not brought back (`skipped.erased`) |

Every lesson is validated before the first write, so a registry with one bad lesson
changes nothing. Errors are `failure_memory_config` and `failure_memory_registry`.

**Wake leaves them out.** Failure-memory routes its lessons by path into loadouts, so
`wake` excludes this schema by default; see
[token budget across systems](recall-and-wake.md#one-context-budget-across-systems).
`recall` reaches them.

## Python

```python
from akms_records import RecordStore, import_failure_memory, promote

store = RecordStore.open("project:example", repo=".")
promote(store, "rec-20261103-k3f9m2xa", review="approved", repo=".", actor="me")
import_failure_memory(store, ".knowledge/failure-memory.toml", repo=".", actor="me")
```
