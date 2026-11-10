# Records limits

!!! warning "Experimental"
    These limits describe the current release.

## Scope isolation is a policy, not a security boundary

The API keeps scopes apart: a store opened for `agent:scout` cannot read or
write `agent:critic`'s records, and a project store opened for
`project:alpha` refuses `project:beta`'s records in the same repository. That
protects cooperating agents from mistakes. It does not protect against a
process that reads the files directly: anyone who can read a store directory
can read every record in it. Agents that must not see each other's records
need separate store roots (agent scopes already get one each) with operating
system permissions that keep them apart.

`recall` and `wake` follow the same rule: given an agent, `recall` refuses
another agent's scope, and `wake` reads only the agent's own scope plus the
project and shared scopes it is given. Sensitive records are left out unless
asked for, and rejected records are never shown. The index of a store root
holds every scope in that root, like the files do.

`doctor` is store-wide maintenance and covers every scope in its root.

Setting a promotion policy asks for interactive confirmation, but a process
that can drive a terminal could answer it. That is why every change is
logged.


## Review state

An agent's content change resets a review, and only `origin` tells a person from an
agent; see the [CLI reference](cli-reference.md#records). After such a reset the
record is `unreviewed`, so other agents no longer get it from `wake` until someone
reviews it again, while `recall` still finds it. Old revisions stay in `history`.

This rests on the actor name. `--actor` and `AKMS_RECORDS_ACTOR` are trusted as given, so
an agent that claims the name in `origin` keeps the review. Like scope isolation, this
protects cooperating agents from mistakes; it is a policy, not a security boundary. Each
event records the actor, so a claim can be traced, but not disproved.

## Promotion

- **The approval is a statement, not a proof.** `--review approved`, `--yes` and
  `amend --review-state user_confirmed` or `review set --state user_confirmed`
  are for cooperating agents and people. They
  make each step deliberate, but a process that can run the CLI can pass them, and
  one driving a terminal can answer the prompt. The node's Sources section and the
  link event name the actor and how a write was confirmed, so a wrong promotion
  can be traced.
- **Freshness is not synchronization.** Record edits do not rewrite nodes.
  Newly generated loadouts check managed projections against the current source
  event stream and suppress the whole node when a projection is stale, edited,
  missing or unreadable. This includes retracted, superseded and erased sources.
  Explicit `promote --update` replaces the record's verified block; it does not
  append a contradictory new claim. Existing loadout files are not rewritten.
  A stale promotion does not automatically clear the source's live link or return
  it to default `wake`; refresh or explicitly withdraw it. `--include-promoted`
  remains an explicit option when reading records.
- **Upgrade requires a graph rebuild.** Derived provenance hints identify promoted
  nodes whose Markdown file later disappears. Older graph files lack these hints;
  rebuild after upgrading, then inspect `promotion status`. Legacy unbounded
  promotions remain unavailable until safely upgraded or manually reconciled.
- **A fingerprint is not authentication.** Body and source-event digests detect
  changed bytes, not truth or an authorized author. A process that rewrites all
  files and their hashes can defeat them. A valid schema or review label is not
  proof of the content either.
- **Manual edits are not guessed away.** Refresh and withdrawal preserve unrelated
  prose and other records' blocks, and refuse damaged managed blocks. Legacy
  upgrades require an exact reconstruction from historical events; erased or
  edited legacy text needs manual reconciliation. Arbitrarily copied text and
  metadata may still contain the old source.
- **Erasure and withdrawal are separate.** `erase` removes source records, causing
  new loadouts to fail closed, but cannot remove their node files. Explicit
  `promotion withdraw --erased` requires the matching scoped erasure log and
  removes verified managed projections. It does not clean previous loadouts,
  pushed git history, exports, backups, or arbitrary copies. Avoid putting erased
  content in the withdrawal reason.
- **External sources are host-dependent.** Agent/shared stores outside the project
  are recorded with an absolute source locator. A missing source on another host
  makes its projection unavailable. The locator itself is stored in the node's
  managed metadata, so review it before sharing that file.
- **A lock, not a transaction.** Promotion and withdrawal take a per-repository
  lock. It cannot stop a process that edits files or calls AKMS directly without
  that lock. Record, node and graph changes are not atomic together. A rebuild
  failure may leave node changes on disk; inspect status and retry to finish.
  A lock left by a dead process is removed by the next operation.
- **Payload size.** A node holds the whole payload rendering. A large payload means
  a large node, which every loadout that selects it pays for.
- **Sessions.** `update_graph` adds a session entry and a ledger line to
  `local_state.yaml` for each default-path promotion. The human path adds neither.

## The failure-memory importer

- **A copy, not a source.** The registry stays the authority. A record can be behind
  the registry until the next import, and a lesson removed upstream stays until a
  person retracts it.
- **Annotations and `_field_spec` are not imported**, since they are not lesson
  fields.
- **Two clones importing on different days** create separate records for one lesson;
  later imports report the extra under `duplicate_records`.
- **Erased lessons are recognized by their record ID**, which derives from the
  lesson. An ID that took more than four allocation attempts is not recognized,
  and a re-import would create the record again; 40 random bits make that rare.

## Summaries are derived content

A [summary](consolidation.md) is written by a tool, `unreviewed`, from records
that are themselves not facts. Treat it as a convenience, not a source:

- **Citations limit a summary; they do not prove it.** The validator checks
  that every assertion cites real source revisions in the same scope. For the
  extractive method it also checks that the text is the source's own summary
  or an extracted field, so an extractive summary can only drop nuance, not
  add claims. A provider's text is free: it can paraphrase badly, merge two
  sources into a claim neither makes, or cite the wrong one, and still pass.
  Review a provider summary before you rely on it; `wake` will not show one
  until it is reviewed.
- **Staleness is about the inputs**, not the world: a summary is valid while
  its sources and its topic's gather are unchanged, however old they are.
- **At most 64 sources** per summary, the envelope's source-reference limit.
  Summaries do not summarize summaries, so there is no hierarchy to work
  around it; narrow the topic.
- **The erasure cascade finds summaries through the index.** A summary the
  index has never seen (for example files copied in by hand) is erased by
  `doctor --fix`, which reads every record.

## Erasure and git history

`erase` removes a record's files from the store and logs the erasure without
its content. For project-scope records that were already committed, that is
not the end:

- **Git history keeps the record.** Earlier commits, packs, and every remote
  and clone that fetched them still contain it. Removing it from history needs
  a history rewrite outside AKMS (for example `git filter-repo`) and a forced
  update of every copy.
- **Branches can bring it back.** An amendment made on another branch before
  the erasure merges back cleanly and restores a revision file, payload
  included. `doctor` reports records named in the erasure log, and
  `doctor --fix` erases them again; run it after merges.
- **Exports and backups** made before the erasure are not touched. `import`
  never brings back a record named in the local erasure log.
- **Other worktrees' indexes.** Each worktree has its own search index.
  Erasure cleans this worktree's index; another worktree's index drops the
  record on its next read after the erasure log reaches it, or on
  `doctor --fix`.

The erasure log holds the record ID, scope, time, actor and reason. Do not
put the content you are erasing into the reason.

## Merging

Records merge per file. Two branches that change the same record to the same
revision produce a conflict on that file, which replay and `doctor` report. A
resolution that takes one side drops the other side's event without any
error; re-add it as a new amendment instead. A binary-style resolution
(choosing a file wholesale) leaves no markers to detect.

## Single host, local disk

Temp-file cleanup decides that a writer is gone by checking its process ID on
this machine. Stores on network or cloud-synced folders are not supported:
several hosts can share process IDs, and sync tools are not transactional.
The filesystem must support hard links (any local disk on Linux and macOS,
NTFS on Windows; on Windows a filesystem without hard links falls back to an
exclusive rename).

## Scale

Every record is a directory and every revision a file of about 1–2 KB, which
occupies a whole filesystem block. Commands without an index (`list`,
`export`, `doctor`, `index check`) read every record. `recall` and `wake` use
the index; after a git checkout or merge their first read stats every record
directory once.

## The index only sees changes made through the API or git

The staleness check before each read catches writes through `akms-records`
and changes made by git. Files copied in or restored by other tools, inside an
existing month directory, are not noticed until `akms-records index
reconcile` or `doctor --fix`. See [search index](search-index.md). Keep project stores well below 100,000
records: at that size `git add` and `git status` slow down noticeably.

## A deleted newest revision goes unnoticed

The store detects an edit to any revision of a record, but not the deletion
of its newest revision file: the record then replays one revision earlier,
without an error. A per-record head file would catch it, but every write would
update that file, so two branches touching the same record would always
conflict on it in git. That trade-off is deliberate. In a project store, git
history is the remedy: the deletion shows in `git status` and `git log`, and
the file can be restored from any commit that has it.

## Canonical JSON

Digests depend on Python's JSON number spelling (`1` and `1.0` differ) and do
not normalize Unicode. Tools in other languages that rewrite event files must
keep values exactly as they are.

## Durability

Writes `fsync` the event file and its directory. On macOS `fsync` does not
flush the drive's cache; set `AKMS_RECORDS_FULL_FSYNC=1` for a full flush.
Crash safety is tested against killed processes, not against power loss.

## Semantic search

`recall --semantic` is opt-in and depends on an external tool, and on settings that tool
describes as being for its tests: `INDEX_PATH` and `QMD_CONFIG_DIR` keep qmd inside the store, and the
`vec:` query form with `--no-rerank` keeps it from running a text-generating model. It
was checked against qmd 2.1.0, with the network denied and the user's qmd folders
read-only. A later version of qmd could change either, so check again before relying
on it.

On one 597-record evaluation corpus of three store roots, with 134 queries and a limit
of 5, measured on one laptop:

| Query | Search | Recall@5 | MRR | Median time |
|---|---|---|---|---|
| keywords | text | 0.828 | 0.935 | 5 ms |
| keywords | text + vectors | 0.850 | 0.590 | 3.9 s |
| questions | text | 0.679 | 0.462 | 8 ms |
| questions | text + vectors | 0.746 | 0.494 | 3.2 s |

So vectors found somewhat more for questions, and put the right record much lower for
keywords, at several hundred times the latency: each store root costs one `qmd` process
that loads the model. The first build took 15 s and about 16 MB across the three
roots. This is weak evidence, since the queries were written with the corpus in mind,
and it is not a recommendation either way.

An erasure means a full rebuild at the next semantic recall, and so does a record
becoming sensitive. qmd's vector search considers at most 20 chunks per query per store
root, so a very large root, or one shared by many scopes, can crowd out a scope's
records before recall filters them.
