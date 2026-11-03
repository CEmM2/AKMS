# Records storage format

!!! warning "Experimental"
    The format carries version markers (`akms-records-event/v1` and others)
    so that a later change can be detected, but it is not frozen yet.

## Layout

```text
<store root>/
  .gitattributes                 * -text; union merge for the two logs
  .gitignore                     .index/ and *.tmp
  _erasures.jsonl                content-free erasure log (append-only)
  _schemas/
    <name>/
      v<N>/schema.json           the schema, canonical JSON
      v<N>/registration.json     ref, digest, who and when
      _policy.json               current promotion policy (optional)
      _policy_log.jsonl          every policy change (append-only)
  <YYYY-MM>/
    <record_id>/
      000001.json                the create event
      000002.json                the next event, and so on
```

A store root holds one directory per record and one immutable file per
revision. The month directory comes from the record ID's date. `.index/` is
reserved for a derived index that is never committed.

## Record IDs

`rec-<YYYYMMDD>-<8 characters>`, for example `rec-20261103-k3f9m2xa`. The date
is the UTC day of the creating event. The eight characters are Crockford
base32 (`0-9a-z` without `i l o u`), 40 bits taken from
`sha256("<event_id>:<k>")`, where `k` counts allocation attempts.

Because the ID derives from the event ID, a retried create with the same event
ID lands in the same directory and is recognised as already done, even when
the retry crosses midnight UTC. Forty bits keep two clones from picking the
same ID for unrelated records: with five clones each creating 40 records a
day, the expected time to the first clash is tens of millions of days.

## Event files

Each event is canonical JSON: keys sorted, UTF-8 without escaping, two-space
indent and one trailing newline.

```json
{
  "actor": "me",
  "at": "2026-11-03T16:00:00.000000Z",
  "body": {"envelope": {"...": "..."}, "payload": {"...": "..."}},
  "event_id": "decision-keep-it",
  "event_sha256": "<digest of this event without this field>",
  "format": "akms-records-event/v1",
  "kind": "create",
  "prev_sha256": null,
  "record_id": "rec-20261103-k3f9m2xa",
  "revision": 1
}
```

| Kind | Body |
|---|---|
| `create`, `amend` | `envelope` (schema ref and digest, scope, origin, source refs, summary, tags, sensitivity, review state) and `payload`; an amend carries the full new state |
| `supersede` | `superseded_by` (a record ID in the same scope) and `reason` |
| `retract` | `reason` |

Revision 1 is always `create`. After `supersede` or `retract` the record
accepts no further events. The scope never changes.

## Digests

- **Chain.** `prev_sha256` is the SHA-256 of the previous event's canonical
  JSON (`null` at revision 1). Editing any revision that has a successor
  breaks the chain at the successor.
- **Seal.** `event_sha256` is the SHA-256 of the event's canonical JSON with
  `event_sha256` left out. It covers the newest revision, which the chain
  alone does not.
- **Canonical, not raw.** Digests are computed over a re-serialization of the
  parsed JSON. A line-ending conversion or re-indentation leaves them valid;
  `doctor` lists such files as `noncanonical` without failing.
- **What they are not.** The digests detect accidental and naive edits and
  merge mistakes. They are not signatures: someone who rewrites a whole
  history can recompute them. Deleting the newest revision is not detected by
  the store; git history shows it.

## Writing a revision

1. Write the event to `.<name>.<pid>.<random>.tmp` in the record directory and
   `fsync` it.
2. `os.link` the temp file to `<revision>.json`. The link fails if that file
   exists, so of several writers racing for the same revision exactly one
   wins; the others get `stale_revision`.
3. Remove the temp file and `fsync` the directory (not possible on Windows).

There is no lock. Readers only see complete files. A writer killed at any
point leaves at most a temp file or an empty record directory. `doctor`
removes both once the writer's process has exited, and the next write to the
record removes such temp files too (on Windows the owner check never sends a
console signal). An acknowledged
write is never lost to a process crash.

`fsync` does not flush the drive cache on macOS. Set
`AKMS_RECORDS_FULL_FSYNC=1` to use `F_FULLFSYNC` there, at roughly 15 ms per
write. Power-loss durability has not been tested.

## Replay

The current state is a fold over the events in revision order. Replay checks
that revisions are contiguous, files parse, each event's format, record ID,
revision, kind, chain and seal are right, and that no event follows a
supersede or retract. It never repairs anything. Failures carry a code:

| Code | Meaning |
|---|---|
| `gap` | A revision is missing |
| `conflict` | A file contains git conflict markers |
| `parse` | A file is not valid JSON (or repeats a key) |
| `format`, `mismatch`, `kind` | The event's fields, revision or kind are wrong |
| `chain` | `prev_sha256` does not match the previous event |
| `digest` | `event_sha256` does not match the event |
| `sequence` | An event follows a supersede or retract, or changes the scope |

## Git

The store writes `.gitattributes` with:

```text
* -text
_erasures.jsonl merge=union
_schemas/*/_policy_log.jsonl merge=union
```

`* -text` stops `core.autocrlf` from rewriting event files. The two logs merge
by union, so two branches that each erase a record, or each change a policy,
do not conflict on the log.

| On two branches | Result of the merge |
|---|---|
| Different records created or amended | Clean, in either order, with the same tree |
| The same record amended to the same revision | An add/add conflict on that revision file; replay and `doctor` report `conflict` for that record only |
| A record erased on one branch, amended on the other | Clean merge that brings the amendment back; `doctor` re-applies the erasure |

Resolve a same-revision conflict by keeping one side's file and re-adding the
other side's change as a new amendment. Taking one side alone silently drops
the other side's event.

## Export format

`akms-records export` writes JSON Lines in this order: a `header` (format
`akms-records-export/v1`, scope, time), one `schema` line per registered
schema, one `erasure` line per logged erasure in the scope, one `event` line
per event, and a `footer` with counts and the SHA-256 of all preceding lines.
