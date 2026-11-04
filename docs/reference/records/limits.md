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

`doctor` is store-wide maintenance and covers every scope in its root.

Setting a promotion policy asks for interactive confirmation, but a process
that can drive a terminal could answer it. That is why every change is
logged.

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
`export`, `doctor`) read every record. Keep project stores well below 100,000
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
