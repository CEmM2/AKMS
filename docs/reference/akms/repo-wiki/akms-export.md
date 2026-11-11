# AKMS export

`repo-wiki export-akms` projects repository source into AKMS code mirrors: one
Markdown document per source file, with AKMS v2 code-mirror frontmatter, a
symbol index and the complete source. It is the command behind the default
`builtin` [code-mirror provider](../user-guide/mirror_providers.md).

It reads sources, writes mirrors and nothing else. It does not summarize,
build or query the search index, or call any network service. The output is
deterministic: it never reads the wall clock, so the same source, options and
timestamp produce byte-identical files.

```bash
repo-wiki export-akms --output . --phase 1 --generated-at 2026-03-07T12:00:00+00:00
```

## Flags

`--output` and `--phase` are required, and so is a timestamp from either
`--generated-at` or `SOURCE_DATE_EPOCH`.

| Flag | Default | Meaning |
|---|---|---|
| `--output DIR` | required | Output root. Mirrors go to `DIR/<knowledge-dir>/code-mirror/`. A relative path is resolved against the repository root and must stay inside it; an absolute path may point anywhere. |
| `--knowledge-dir {.knowledge,knowledge}` | `.knowledge` | Knowledge directory under `--output`. Use `knowledge` for a repository that still has the older layout; see [Moving to `.knowledge/`](../user-guide/knowledge-layout.md). |
| `--phase N` | required | Positive integer recorded in each mirror as `generated_by_phase`. |
| `--generated-at TIMESTAMP` | none | ISO 8601 timestamp recorded in each mirror, such as `2026-03-07T12:00:00+00:00`. |
| `--full` | on | Write every selected mirror. This is the default; the flag only states it. |
| `--changed-only` | off | Skip a mirror whose rendered bytes already match the file on disk. It does not change which sources are selected. |
| `--path PATH` | none | Export only this repository-relative source file. Repeat the flag for several files. There is no globbing. Cannot be combined with `--git-base`. |
| `--git-base REF` | none | Export only sources changed since this git ref. |
| `--git-head REF` | none | With `--git-base`, compare the two refs instead of the worktree. Requires `--git-base`. |
| `--prune` | off | After a completely successful full export, delete mirrors whose source is no longer exported. Refused with `--path` or `--git-base`. |
| `--force-lock` | off | Reclaim a stale or unreadable [output lock](#output-lock). |
| `--json` | off | Print only the [JSON result](#json-result) on stdout. |

`--full` and `--changed-only` are mutually exclusive.

### Timestamps

Without `--generated-at`, the exporter uses the `SOURCE_DATE_EPOCH`
environment variable: a non-negative integer number of seconds since the Unix
epoch, converted to UTC.

```bash
SOURCE_DATE_EPOCH=1767225600 repo-wiki export-akms --output . --phase 1
```

If neither is set, or either is malformed, the command exits 2 without
writing. The timestamp is part of every mirror's bytes, so changing it
rewrites all mirrors even under `--changed-only`. Pin it to something stable,
such as a release or commit time, if you want rebuilds to be no-ops.

## What gets exported

The exporter scans the repository with the same rules as `repo-wiki scan`
([`scanner.*`](configuration.md#scanner) and
[`languages.*`](configuration.md#languages)), then keeps files in a supported
language: Python, Rust, C++ and Julia. Python is always supported; the others
must be enabled in `.repo_wiki/config.yaml` and need their
[extras](index.md#install). Other eligible files, such as Markdown and YAML,
appear in `skipped` with reason `unsupported_language`. The output tree
`<output>/<knowledge-dir>/code-mirror/` is never scanned as source.

### Selection

| Selection | Chosen by | Sources exported |
|---|---|---|
| `full` | no selection flag | Every eligible source. |
| `paths` | `--path` | Exactly the listed files. |
| `git_diff` | `--git-base` | Files changed since the ref. |

The selection mode is reported as `selection.mode` in the result.

**`--path`** is strict. Every path must be an eligible source, or the command
reports a `selection` error and exits 1. The exception is a path that no
longer exists but still has a mirror: that mirror is removed.

```bash
repo-wiki export-akms --output . --phase 1 --generated-at 2026-03-07T12:00:00+00:00 \
  --path src/pkg/a.py --path src/pkg/b.py
```

**`--git-base REF`** compares against the worktree, so it selects committed
and uncommitted changes to tracked files since `REF`, plus new files that git
does not ignore. Changed files that are not eligible sources, such as
documentation, are ignored rather than treated as errors. A source that was
deleted or renamed away has its mirror removed. `selection.dirty_worktree`
reports whether the worktree has uncommitted changes.

```bash
repo-wiki export-akms --output . --phase 1 --generated-at 2026-03-07T12:00:00+00:00 \
  --git-base origin/main
```

**`--git-base REF --git-head REF`** compares the two commits (`base...head`)
and so ignores the worktree. It refuses to run if the worktree is dirty.
Untracked files count as dirty, so keep an in-repository output directory
ignored by git, or put it outside the repository. Changes under `.repo_wiki/`
and the export lock files do not count.

```bash
repo-wiki export-akms --output . --phase 1 --generated-at 2026-03-07T12:00:00+00:00 \
  --git-base v1.0.0 --git-head HEAD
```

A ref that does not exist, or one that starts with `-`, is a `selection`
error that names the ref. A directory that is not a git work tree is also a
`selection` error. Git is called with an argument list, never through a shell.

### Pruning and deletions

Mirrors of deleted sources are removed under `--path` and `--git-base`
selection. `--prune` goes further and removes every mirror under
`code-mirror/` whose source was not part of this export, so it is only
allowed on a full export. Both remove only files that carry the exporter's
own markers (`domain: code-mirror`, `source: generated`, `auto_update: true`,
`akms_schema: v2`) and whose path and ID match their `source_file`. A file you
wrote by hand in the same directory is left alone. Neither runs if the export
reported any error.

## Output

For each source, one file is written at
`<output>/<knowledge-dir>/<content_ref>`:

| Language | Source | Mirror (under `<knowledge-dir>/`) | Node ID |
|---|---|---|---|
| Python | `src/pkg/greet.py` | `code-mirror/src/pkg/greet.md` | `mirror-src-pkg-greet` |
| Rust | `src/lib.rs` | `code-mirror/rust/src/lib.rs.md` | `mirror-rust-src_2flib_2ers` |

Python IDs replace `/` and `.` with `-` and drop the `.py`. Other languages
keep the whole file name, add the language as a directory, and encode every
byte of the path other than lowercase ASCII letters, digits and `-` as `_` plus
two hex digits, so distinct paths never collide.

Each document has the twelve frontmatter fields AKMS accepts for a code mirror
(`id`, `title`, `domain`, `status`, `confidence`, `source`, `auto_update`,
`content_ref`, `source_file`, `generated_at`, `generated_by_phase`,
`akms_schema`), then a `Symbol Index` section with each symbol's ID, kind,
line range, signature, docstring, calls, bases and parent as JSON, then a
`Complete Source` section with the file verbatim. `content_ref` is relative to
the knowledge directory, so it is the same for `.knowledge` and `knowledge`.

Each file is written to a temporary name and renamed into place, so a reader
never sees a half-written mirror.

### Mirror summary

With [`export.mirror_summary: true`](configuration.md#export), each mirror opens
with a `## Summary` section ahead of the symbol index, which routing-mode
[loadouts](../user-guide/generating-loadouts.md#code-mirrors-in-routing-mode)
load in place of the mirror:

```markdown
## Summary

Public, dependency-free contract for exporting repository-wiki mirrors to AKMS.

Classes: `MirrorDocument` (to_dict), `WrittenRecord` (from_document, to_dict)

Functions: `normalize_source_path(source_path: str) -> str`, +10 more
```

It holds the first paragraph of the module docstring, then the file's public
top-level classes, each with up to five public method names, and its public
top-level functions, with their signatures and in source order. What does not
fit is counted as `+N more`. A file with none of these says so, so the section
is never empty. It is built only from what the extractor found in that one file,
with no model call, so it stays deterministic, and a change elsewhere never
rewrites this mirror. It is capped at 800 characters, the 200 tokens routing mode
charges per node.

The option is off by default, and off means the bytes are unchanged. Mirror bytes
are pinned by the export fixture pack and by the `repo2md_fixture_sha256` that
projects record. Turning it on rewrites every mirror once, including under
`--changed-only`. On a large downstream project the section averaged 86 tokens
per mirror (at most 197) and made a mirror 1.4% larger when read in full.

You rarely need it. A loadout builds the same text from a mirror's symbol index
when the mirror has no section
([`loadout.derive_mirror_summary`](../user-guide/generating-loadouts.md#code-mirrors-in-routing-mode),
on by default), so loadouts show the summary without any mirror being rewritten.
Turn the export option on when something other than a loadout reads the section
from the mirror file.

## JSON result

With `--json`, stdout carries only this object, as compact JSON with sorted
keys and sorted records:

```json
{
  "export_schema_version": 1,
  "phase": 1,
  "generated_at": "2026-03-07T12:00:00+00:00",
  "selection": {
    "mode": "git_diff",
    "requested_paths": ["src/pkg/greet.py"],
    "dirty_worktree": true,
    "git_base": "HEAD",
    "git_head": null
  },
  "selected": [
    {"source_path": "src/pkg/greet.py", "language": "python", "source_hash": "sha256:..."}
  ],
  "written": [
    {
      "source_path": "src/pkg/greet.py",
      "language": "python",
      "source_hash": "sha256:...",
      "node_id": "mirror-src-pkg-greet",
      "content_ref": "code-mirror/src/pkg/greet.md",
      "generated_path": ".knowledge/code-mirror/src/pkg/greet.md"
    }
  ],
  "removed": [],
  "skipped": [],
  "errors": []
}
```

| Field | Meaning |
|---|---|
| `export_schema_version` | Version of this result and of the mirror contract. Currently `1`. Consumers should reject a version they do not know. |
| `selection` | How sources were chosen. `requested_paths` is `null` for `full`; `git_base`, `git_head` and `dirty_worktree` are `null` unless `git_diff` applies. A failed selection adds an `error` string. |
| `selected` | Every source that entered the export, with its content hash. |
| `written` | Mirrors written, with node ID, `content_ref` and `generated_path` (relative to `--output`). |
| `removed` | Mirrors deleted by `--prune` or because their source was deleted (same fields without `source_hash`). |
| `skipped` | Sources not written, with `reason`: `unsupported_language` or `unchanged`. |
| `errors` | Failures: `source_path` and `language` (either may be `null` for a whole-export failure), `stage` (where it failed, for example `selection`, `validation`, `decode`, `render`, `write` or `prune`) and `message`. |

Mirrors are written whether or not you use `--json`. Without it, stdout lists
`written:`, `removed:` and `skipped (<reason>):` lines instead.

### Exit status

| Code | Meaning |
|---|---|
| `0` | Finished with an empty `errors` list. |
| `1` | The export reported errors, or the output lock could not be taken. |
| `2` | Arguments were rejected before any work and nothing was written: missing or malformed timestamp, non-positive phase, `--git-head` without `--git-base`, `--path` with `--git-base`, an output path that is not a directory, or a relative `--output` outside the repository. |

Per-source errors are also printed on stderr as
`export-akms <stage> error [<source>]: <message>`, even with `--json`, so
stdout stays parseable. A lock failure prints `export-akms lock error: ...` on
stderr and produces no JSON.

## Output lock

An export holds a single-writer lock while it runs, so two exports into the
same output tree cannot interleave. The lock is a file beside the output
directory, not inside it:

```text
<parent of --output>/.repo2md-export-<16 hex digits>.lock
```

The digits are a hash of the resolved `--output` path, so the lock follows the
output tree, not the repository. With `--output .`, the lock sits in the
directory above the repository, which therefore must be writable. The name
keeps the prefix of the tool's earlier name. The file records the owner's process ID, host, user, start time
and command line as JSON, and is deleted when the export ends.

A second export to the same output while the first is running fails with exit
1 and names the holder. A lock left behind by a crash is reclaimed
automatically when:

- the owning process is no longer running on this host;
- the process ID has been reused by an unrelated process;
- the file is unreadable and more than five seconds old; or
- the lock is more than six hours old and its owner cannot be checked, such as
  one taken on another host.

`--force-lock` additionally reclaims an unreadable lock inside the five-second
window and a lock taken on another host. It never takes a lock from a live
exporter on this host, so it cannot create two concurrent writers.

```bash
repo-wiki export-akms --output . --phase 1 --generated-at 2026-03-07T12:00:00+00:00 --force-lock
```

## How the `builtin` provider uses it

When `mirror.provider` is `builtin` (the default), `akms generate-mirror` and
the staged runner start `python -m akms.repo_wiki` as a subprocess with an
argument list (never a shell), using the same Python interpreter as AKMS. The
arguments come from the request and the `mirror` settings:

| Argument | Source |
|---|---|
| `--repo-root` and `--output` | The repository root for both, unless the request names another output root. Mirrors land beside your other knowledge. |
| `--knowledge-dir` | `.knowledge`, or `knowledge` for a repository that still uses the older layout. |
| `--phase` and `--generated-at` | Supplied by AKMS, which picks the timestamp according to `mirror.generated_at_source`. The subprocess does not read `SOURCE_DATE_EPOCH` itself. |
| `--json` | Always, so AKMS can parse the result. |
| `--path` per file | When the request names source files. |
| `--full` | `mirror.selection_mode: full`. |
| `--git-base` (and `--git-head`) | `mirror.selection_mode: changed`, the default, against the parent branch. |
| `--prune`, `--force-lock` | `mirror.prune`, `mirror.force_lock`. |

`mirror.timeout_seconds` bounds the subprocess. AKMS then validates the JSON
result and every written document before it accepts the mirror: export schema
version, AKMS v2 frontmatter, output containment, consistency between content
and source, duplicate IDs and completeness. Any failure, including a timeout,
a nonzero exit or malformed JSON, is an explicit provider error. The settings,
their defaults, the `changed` fallback outside a git repository, and the
separate external `repo2md` provider are described in
[Code-mirror providers](../user-guide/mirror_providers.md).

To produce the same mirrors by hand, run `export-akms` with the arguments in
the table. Consumers read only the Markdown files and the JSON result.
