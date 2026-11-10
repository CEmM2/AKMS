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
    [--update] [--domain DOMAIN] [--yes]
```

`--review approved` is the explicit approval, and promotion is refused without
it. A record must be `user_confirmed`; `--min-review-state agent_reviewed` is an
opt-in to promoting records that only an agent has reviewed. `--repo` names the project whose knowledge directory receives the node
(default: the current directory).

### Two paths

| Path | When | Written with | Labels |
|---|---|---|---|
| Default | No policy, an agent-sourced policy, or a record that is not `user_confirmed` | `update_graph` with a `NewKnowledge` | `source: agent`, `status: tentative`, `confidence: 0.50` |
| Human policy | The schema's [stored policy](schemas-and-templates.md#promotion-policy) is `source: human` and the record is `user_confirmed`; [needs confirmation](#confirming-a-human-policy-write) | A validated `LocalNodeFrontmatter` file, then a graph rebuild | `source: human` with the policy's status and confidence |

The default path may report `dedup_appended` instead of `created`: `update_graph`
appends to a similar tentative node in the same domain when their similarity
exceeds its threshold. The record then links to that node. An agent-sourced
policy stays on this path, so its confidence does not raise the fixed `0.50`.

`promote` reads the policy and cannot change it. A policy file that disagrees
with its log is refused (`policy_drift`), since a change outside the log is what
the log exists to expose.

### Confirming a human-policy write

A write that labels text `source: human` needs one more step than `--review
approved`, the same step as `schema policy set`:

- **On an interactive terminal**, promote shows what it will write and asks. Only
  `y` or `yes` goes ahead; anything else is `not_confirmed` and writes nothing.

  ```text
  Write node rec-20261103-k3f9m2xa from rec-20261103-k3f9m2xa@2 with source=human, status=established, confidence=0.8? [y/N]
  ```

- **`--yes`** confirms without a prompt.
- **Neither** is `confirmation_required`, before anything is written.

The refusal names both options, and it does not fall back to the default path. If
it did, the same command would quietly write a different kind of node depending on
where it ran. The way to the default path is the record and the policy themselves:
a schema with no `source: human` policy, or a record that is not `user_confirmed`.
That path needs no confirmation.

Replacing a managed block in a human-sourced node with `--update`, or withdrawing
one, needs the same confirmation. Completing the link of a node that is already written
is not, because nothing new gets the label, so
[crash recovery](#if-it-crashes) works without a terminal. If the record, its node
or its policy changes while the prompt waits, the run stops with
`confirmation_stale`, so a person never approves one thing and gets another.

For promotion and refresh, the node's Sources section records the method
(`- confirmation: tty` or `yes`), and the result reports it as `confirmation`.
Withdrawal removes that block rather than writing new source content.

!!! warning "What confirmation proves"
    `--yes` makes the step deliberate. It does not prove a person took it: any
    process that can run the CLI can pass it, and one driving a terminal can answer
    the prompt. Like the policy log, this holds for cooperating agents and leaves a
    trace; it is not a security boundary.

### What the node holds

A newly created node's ID is the record ID, its title the record's label (or the
start of its summary), its tags the record's plus the schema name, and its domain
the scope's ID in lower case, unless `--domain` says otherwise. Deduplication may
instead place the record's block in an existing node. The body is:

- the record summary and a JSON rendering of the payload, each fenced, because
  [record text is data](recall-and-wake.md#rendering-is-data-not-instructions);
- a `Sources` section: record ID and revision (`rec-…@3`), schema reference and
  digest, scope, time, origin, review state, who promoted it, how a human-policy
  write was confirmed, and the record's own source references.

The body is enclosed in managed projection markers. These carry the record and
scope, a locator for its source event directory, and fingerprints of both the
source event stream and the rendered body. The fingerprints detect changes;
they are not authentication. Project sources use repository-relative locators;
agent/shared sources outside the repository use absolute paths.

The v2 node models have no field for a record ID, and they are unchanged. The
Sources section and managed block carry provenance. The file has no `content_ref`. A loadout
reads `<knowledge>/local-nodes/<node id>.md` in that case and prints that path.
An explicit `content_ref` is left as it is.

### Refusals

Each is a typed error with exit status 2. Eligibility and confirmation refusals
happen before writing. A failure during a multi-step write may leave a node
changed; follow [crash recovery](#if-it-crashes) rather than assuming rollback.

| Code | Why |
|---|---|
| `akms_unavailable` | `akms` is not installed: `pip install 'akms-records[akms]'` |
| `review_required` | `--review approved` was not given |
| `review_below_threshold` | The record is below the threshold, `user_confirmed` by default. `--min-review-state agent_reviewed` is the only opt-in; nothing lowers it further |
| `confirmation_required`, `not_confirmed`, `confirmation_stale` | A [human-policy write](#confirming-a-human-policy-write) had no terminal and no `--yes`, was not answered yes, or changed during the prompt |
| `scope_not_project` | The record is in an agent or shared scope; pass `--scope-ok` |
| `record_retracted`, `record_superseded`, `record_erased` | The record is not current |
| `schema_mismatch` | The schema is missing or tampered with, the record's digest differs, or the payload no longer validates |
| `record_sensitive` | The record is `sensitive`; pass `--allow-sensitive` |
| `summary_unreviewed`, `summary_stale` | A [summary](consolidation.md) below the threshold, or not currently valid |
| `imported_not_promotable` | An imported failure lesson; pass `--allow-imported` |
| `policy_drift` | The promotion policy disagrees with its log |
| `global_vault_target` | The knowledge directory overlaps the global vault |
| `already_promoted` | A known projection needs reconciliation (a newer revision, legacy block or changed source fingerprint); `details.node_id` names the node. Inspect it before passing `--update` |
| `node_not_updatable` | `--update` met a node that left `tentative` and is not human-sourced |
| `node_exists` | The human path found a file with the node's name that does not hold this record |
| `source_refs_full` | The record has 64 source references, so the link would not fit |
| `promote_locked` | Another promote is running in this repository |
| `projection_conflict` | The managed block was edited, is malformed, or cannot be safely distinguished from legacy/manual content; reconcile it by hand |
| `projection_source_mismatch`, `scope_violation` | The managed projection belongs to a different source directory or scope |
| `projection_source_changed` | The source changed while promotion was being completed; inspect and review the current revision before retrying |
| `stale_revision` | Withdrawal did not name the source's current revision |
| `source_not_erased` | `--erased` has no matching scoped erasure entry, or was combined with a revision |
| `promote_graph_failed`, `promote_write_failed`, `node_not_loaded`, `promote_ledger_exhausted` | AKMS could not write or load the node. Node writes may already have happened; inspect status and retry the appropriate operation |

Why these defaults:

- **The threshold is `user_confirmed`.** The command says a person approved
  this, so the record should show it. A node also costs tokens in every loadout
  that selects it, so refusing is the cheap mistake. A project that wants agents to
  promote their own reviewed records opts in with `--min-review-state
  agent_reviewed`; those nodes stay `source: agent`, `status: tentative`.
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
| Same managed revision again | `already_promoted`, status `ok`: no second node or link event. A pending final source fingerprint can be completed. `node_present` reports a missing node; it is not silently recreated |
| A newer revision without `--update` | Refused with `already_promoted`, naming the node |
| A newer revision with `--update` | Replaces this record's intact managed block, action `updated`, and moves its link. Old claims are not appended beside the correction |
| `--update` on an agent node | Allowed while the node is `tentative`; unrelated prose and other records' blocks remain |
| `--update` on a human node | Requires [confirmation](#confirming-a-human-policy-write); the node keeps its source, status and confidence, whatever the policy now says |

Generated titles may follow the updated source; manually changed titles remain.
Body edits within a managed block cause a refusal rather than being overwritten.
Edit the source record, review it and refresh explicitly. Other authored node prose
is preserved.

Legacy promotions have no bounded managed block. `--update` upgrades them only
when their text exactly matches generated text reconstructed from validated
historical record events. Edited or ambiguous legacy text is refused. An erased
legacy source cannot be reconstructed: reconcile its node manually.

### Check freshness and withdraw a projection

```bash
akms-records promotion status --scope project:example --repo .
akms-records promotion status RECORD --scope project:example --repo .
akms-records promotion withdraw RECORD --scope project:example --repo . \
  --expect-revision 4 --reason "No longer belongs in project knowledge"
# If the source has already been erased:
akms-records promotion withdraw RECORD --scope project:example --repo . \
  --erased --reason "Remove the erased source's projection"
```

`promotion status` is read-only. Its JSON has `status`, `count` and `results`,
including each record's state, matching nodes and suggested next step. It exits 1
for drift (such as changed, erased or inactive sources, missing nodes, or stale
projections), 0 for a consistent report, and 2 for an execution error. Without a
record ID it scans the scope's records and scoped erasure log. It is not a search
for every arbitrary copy of record content in the repository.

`promotion withdraw` removes only verified, intact managed blocks. It requires
exactly one of `--expect-revision N` (inspect the source first) or `--erased`
(which requires that record's entry in this scope's erasure log), plus a reason.
Human-sourced nodes require the same terminal confirmation or deliberate `--yes`
as a refresh. Missing, damaged or ambiguous provenance is not permission to erase
other node content.

Withdrawal preserves unrelated prose and other records' blocks. A node with no
remaining substantive body becomes a withdrawal notice rather than being deleted.
Generated titles are replaced where recognized; do not assume arbitrary manually
copied text or metadata has been scrubbed. After rebuilding the graph, withdrawal
clears an active record's live promotion link through an audited amendment, so the
record can be considered by ordinary wake rules again. Inactive records retain
historical links. The source record itself is never deleted by withdrawal.

### Freshness in newly generated loadouts

The loadout generator checks managed body integrity and source-event fingerprints
against disk, rather than trusting cached content. An amendment, retraction,
supersession or erasure invalidates the old projection immediately for **newly
generated loadouts**. Missing or unreadable sources fail closed too. A node with
an invalid projection is replaced by a neutral review-needed notice, including
when other prose shares that node; stale text and its title are not served. This
is an integrity check, not a background synchronization process. A stale projection
does not automatically clear its live link or return the source to default `wake`:
refresh it, explicitly withdraw it, or deliberately read with `--include-promoted`.

A valid managed block does not make an adjacent legacy promotion safe. Legacy
content remains unavailable until explicitly upgraded or manually reconciled.

**After upgrading, rebuild the graph** to add derived provenance hints. These
hints let loadouts recognize previously promoted nodes even if their Markdown
file subsequently disappears. A graph created by an older version may not have
those hints. For an explicit rebuild:

```python
from pathlib import Path
from akms.graph.build_graph import build_graph
build_graph(Path("."))
```

Then run `promotion status`, review changed sources and use `promote --update` or
`promotion withdraw` as appropriate. No startup hook or automatic capture is
installed. Ordinary record edits do not rewrite nodes, and explicit withdrawal
does not rewrite already emitted loadouts, git history, exports or backups.

An absolute source locator makes an external-scope projection host-dependent.
Moving the repository to a machine without that source makes it unavailable,
not trusted from its cached body. Review and re-establish the projection from an
authorized available source instead of bypassing the guard.

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
| After the node, before `update_graph` finished its overlay or graph | Finds the node, rebuilds the graph, writes the link: action `link_completed`, no confirmation needed |
| After the graph, before the link | Finds the node, writes the link: action `link_completed`, no confirmation needed |
| After the link, before the final source fingerprint or result | Re-run to finalize the managed block; then `already_promoted` |

The run scans `local-nodes` for managed provenance and legacy `Sources` markers
outside payload fences, and verifies the source before replacing a block. Should a record be amended
between the crash and the next run, the node holds an older revision: that is
`already_promoted` again, and `--update` continues it.

`update_graph` skips a source its replay ledger already names. When the ledger
names a promotion but no node holds the record (the node was removed by hand before
the link), the bridge retries under a new source ID instead of reporting success.

Withdrawal writes node changes before rebuilding the graph and clearing an
active source's link. If rebuilding fails, those node changes remain; retry
withdrawal to repair the graph and finish the link change. A stale revision or
changed node requires fresh inspection. There is no transaction spanning record
files, node files and the graph, and no rollback promise.

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
does not know is refused, so a lesson never loses a field silently. An extra
top-level key on a schema 1 registry, or on a schema 2 `_registry.json`, is
ignored. The required keys stay required, and a stray file in a schema 2
directory is still refused.

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
from akms_records import (
    RecordStore, confirm_yes, import_failure_memory, promote,
    promotion_status, withdraw_promotion,
)

store = RecordStore.open("project:example", repo=".")
promote(store, "rec-20261103-k3f9m2xa", review="approved", repo=".", actor="me")
promotion_status(store, repo=".")
# After inspecting the actual source revision:
withdraw_promotion(
    store, "rec-20261103-k3f9m2xa", repo=".", actor="me",
    expected_revision=2, reason="No longer project knowledge",
)
import_failure_memory(store, ".knowledge/failure-memory.toml", repo=".", actor="me")
```

`promote` and `withdraw_promotion` take `confirm`, which defaults to not confirmed, so a human-policy write
from Python is refused unless the caller asks otherwise. It is a callable that gets
what will be written and returns how it was confirmed, or raises to refuse;
`confirm_yes` is the `--yes` of the API. The library never reads a terminal: only
the CLI turns one into a confirmation.

### Dependency snapshots and restoring withdrawn nodes

Managed blocks now declare dependency snapshots. Built-in consolidations include
all cited records and a collection witness; other schemas declare an empty
dependency list and no collection witness. Core checks these event fingerprints
without interpreting user schemas. An amendment,
retraction, erasure, missing event, or event-file edit in a cited source withholds
the projected summary. The collection witness covers all other numbered event
streams in the store, detecting new records and amendments of uncited records
that might enter the topic. It deliberately invalidates on unrelated store changes
too, rather than interpreting schemas or topic predicates in core. The summary
itself is excluded from that witness and protected by its own source fingerprint.
Even a link-only source event conservatively invalidates the snapshot; explicitly re-promote the still-valid summary to reseal it.
Existing blocks without dependency and collection declarations are withheld until
explicit promotion refresh. A stale consolidation must be refreshed and reviewed first.

Fresh managed loadouts take their titles from the node file, not a cached graph.
When a node also names a separate `content_ref`, full loadouts include that authored
content alongside the verified local projection. Neither file is rewritten by a
loadout read.

An active withdrawn record can be promoted again. Its matching withdrawal marker
is replaced in the existing node; a generated empty-node notice is removed, while
unrelated prose and manually chosen titles remain. Human-labelled nodes still
require confirmation. Older withdrawal markers are accepted only with matching
scope and validated historical promotion linkage. No automatic capture, wake,
refresh, or re-promotion is installed.

Malformed YAML in a managed node withholds that node instead of aborting the
whole loadout. Other valid nodes remain available.
