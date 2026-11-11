# Search index

!!! warning "Experimental"
    The index layout carries a format marker (`akms-records-index/v3`) and is
    rebuilt automatically when it changes. `v2` adds `review_cleared`, set when
    a later amend left a previously reviewed record `unreviewed`.

`recall` and `wake` read a derived SQLite database, one per store root, at
`<store root>/.index/records.sqlite`. It is never committed (the store's
`.gitignore` lists `.index/`), it can always be rebuilt from the event files,
and it belongs to one working tree: two worktrees of a repository each have
their own.

It needs the FTS5 module of the Python `sqlite3` library, which the
python.org, Homebrew, python-build-standalone and common Linux builds
include. Without it, `recall`, `wake` and `index` fail with
`fts5_unavailable`; writes still succeed and the event files are unaffected.

## Contents

| Table | Holds |
|---|---|
| `records` | One row per record that replays: record ID, head revision and event digest, scope, schema ref, name and digest, the digest of the extraction rules it was indexed with, review state, lifecycle, sensitivity, `recorded_at`, update time, the schema's time field (normalized to UTC) and the time used by `--since`/`--until`, origin, tags, source refs, `superseded_by`, the record IDs it names as `supersedes`, label, summary and `review_cleared` |
| `record_tags` | One row per tag, for exact tag filters |
| `records_fts` | FTS5 (`unicode61` tokenizer) over the summary, the tags and the search text the schema's `search_text` rules select |
| `files`, `months`, `rules`, `meta` | Bookkeeping for the staleness check |

Records that do not replay (a gap, a conflict, a broken seal), records named
in the erasure log, and [summaries](consolidation.md) whose current revision
cites a record named there are never indexed.

## Keeping it current

**Writes through the API** update the index right after the event file is
linked: `add`, `amend`, `supersede`, `retract`, `erase`, `import`, and
`schema register` or `schema rules set`. An update is accepted only when it
carries a higher revision than the one indexed, so two writers that race can
never move the index backwards.

A writer first drops a *pending marker* in `.index/pending/` and removes it
once the index row is written. If the writer dies in between, the marker stays
and the next read replays that record. Markers whose process has exited are
then removed.

**Before every read**, a cheap staleness check looks at:

- one `stat` per month directory;
- the pending markers;
- the worktree's git `index` and `HEAD` files (checkout, merge, reset,
  commit and pull all rewrite them);
- the erasure log;
- the rules file of every schema version that has indexed records.

Only what changed is reconciled. A changed month directory is rescanned with
one `stat` per record directory, and only records whose directory changed are
replayed. A changed git signature rescans every month directory, which costs
about one `stat` per record. A changed rules digest re-extracts the records
of that schema version. When nothing changed, nothing is replayed.

Directory times are coarse on some filesystems (two seconds on FAT, a few
milliseconds on ext4). A signature taken less than two seconds after its
directory changed is stored as unknown and checked again on the next read, so
a change made within the same clock tick is not missed.

**Changes the cheap check does not see.** Files copied in, restored or edited
by tools other than git and `akms-records`, without a new month directory.
After such a change run `akms-records index reconcile` (or `doctor --fix`).
You can also add `akms-records index reconcile --scope ...` to git
`post-checkout` and `post-merge` hooks, though the git signature already
covers those.

## Commands

| Command | Effect |
|---|---|
| `index rebuild --scope S` | Drop every table and index every record again. |
| `index check --scope S` | Replay every record and compare with the index. Changes nothing. `status` is `ok` or `drift` (exit 1), with `missing`, `extra` and `stale` record IDs and the `unindexable` ones that do not replay. |
| `index reconcile --scope S` | Replay every record and fix every difference. Reports the IDs `added`, `updated` and `removed`. |

The scope only selects the store root: each command covers every scope in it.

`doctor` reports a differing index under `index_drift` (one item per record,
with `problem` `missing`, `extra` or `stale`, or `format` when the index has
another format), and an index that cannot be opened under
`index_unavailable`. `doctor --fix` reconciles it and lists the changed IDs
under `repairs.index_reconciled`. A store without an index yet is not a
problem: the first read builds it.

**Rebuild parity is tested.** A rebuild produces exactly the rows that
incremental indexing produced, compared row by row (records, tags, FTS
content and rules digests) after a mix of creates, amends, supersessions,
retractions, erasures and several scopes.

## Erasure

`erase` removes the record's rows from this worktree's index so that none of
its bytes remain in the database files:

- the connection runs with `PRAGMA secure_delete=ON`, so SQLite overwrites
  deleted content;
- the FTS5 table has its `secure-delete` option on, so deleted tokens are
  removed from the full-text index instead of being marked deleted;
- the erasure ends with `PRAGMA wal_checkpoint(TRUNCATE)`, which empties the
  write-ahead log.

With an SQLite older than 3.42, which lacks FTS5 `secure-delete`, deletions
also run the FTS5 `optimize` command and `VACUUM`. The test erases a record
and scans `records.sqlite`, `-wal` and `-shm` for its text.

The result's `index` field says what happened: `purged` (with
`rows_removed` and `checkpoint`), `absent` (no index yet), or `deleted` (the
index could not be opened, so its files were removed; it is derived). If
another process held the write-ahead log open, `checkpoint` is `busy` and the
erasure report's `not_reached` says so: run `doctor --fix` when no other
process uses the store.

Each worktree has its own index. Erasing in one worktree does not clean
another's index; the erasure log reaches it through git, and its next read
(or `doctor --fix`) removes the record there. Records named in the erasure
log are never indexed, even when a merge brings their files back.

## Performance

Measured on an Apple M2 Ultra (macOS, APFS, warm cache, plain `fsync`) with
`packages/akms_records/tests/bench_index.py`: a synthetic corpus of
Zipf-weighted words in eight project scopes of one store root, spread over 24
months, 10 % of records amended; 200 queries (frequent words, rare words, two
words, word plus tag), 50 wakes with a 2,000-token budget, 300 timed creates
and amends with `fsync` and the index update.

| Metric | 10,000 records | 100,000 records | Target |
|---|---|---|---|
| Recall p95, query plus reading the top 10 records | 4.2 ms | 27.7 ms | 10 ms / 50 ms |
| Recall p95, query only | 2.6 ms | 27.2 ms | |
| Wake p95 | 43.9 ms | 472 ms | |
| Full rebuild | 2.2 s | 28.0 s | 60 s at 100,000 |
| Create p95 (file, `fsync`, index) | 1.4 ms | 2.1 ms | 5 ms |
| Amend p95 (file, `fsync`, index) | 2.0 ms | 3.1 ms | 15 ms / 40 ms |
| Index size | 24 MB | 195 MB | |
| Rebuild parity | equal | equal | equal |

`wake` reads every record row of the store roots it opens (to report what it
left out and why), so its cost grows with the root, not with the budget.
CI machines are slower; compare on similar hardware. Run it yourself:

```bash
uv run python packages/akms_records/tests/bench_index.py --sizes 10000,100000
```
