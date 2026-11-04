# CLI reference

```bash
failure-memory [--json-errors] <command> ...
```

Successful commands print JSON. Classified failures print a stable error code;
`--json-errors` emits the error as JSON.

## Project lifecycle

`--config` is optional on every command. When omitted it defaults to
`<repo>/.knowledge/failure-memory.toml`, the file `init` writes, so after `init`
most commands need only `--repo`. An explicit `--config` is read as given.

### `init`

```bash
failure-memory init [--repo .] [--config .knowledge/failure-memory.toml] \
  [--repository-id <id>] [--node-namespace <namespace>] [--force]
```

### `doctor`

```bash
failure-memory doctor [--config <path>] [--repo .]
```

### `migrate-check`

```bash
failure-memory migrate-check [--config <path>] [--repo .]
```

Reports legacy-layout conditions without moving canonical data.

### `generate-wrapper`

```bash
failure-memory generate-wrapper [--config <path>] --output <path> \
  [--repo .] [--force]
```

## Registry and compiler

### `registry migrate`

```bash
failure-memory registry migrate --to 2 [--check] [--config <path>] [--repo .]
```

`--to` accepts only `2`. Schema 2 is opt-in: the command splits a schema 1
registry file into a sibling directory (`lessons.json` becomes `lessons`) of
`<ID>.json` files plus `_registry.json`. It does not allocate new IDs and does
not delete the original file. `previous_registry` in the result is that file.
`--check` compiles both forms in a temporary directory outside the repository
and writes nothing. There is no `--global-vault`. This is not `migrate-check`.
A schema 1 annotations sidecar (`lessons.annotations.json`) is copied into
the directory as `_annotations.json`; `annotations` in the result names the
copy, or is `null`.

### `add`

Choose exactly one source:

```bash
failure-memory add --interactive [--config <path>] --global-vault <path> [--repo .]
failure-memory add --from-json lesson.json [--config <path>] \
  --global-vault <path> [--repo .]
```

### `validate`

```bash
failure-memory validate [--config <path>] [--repo .]
```

### `compile`

```bash
failure-memory compile [--config <path>] --global-vault <path> \
  [--repo .] [--output-root <path>]
```

With `[compatibility].lesson_index_version` set, `compile` also writes
`lesson_index.json` and `lesson_index.md` beside the route index.

### `check`

```bash
failure-memory check [--config <path>] --global-vault <path> \
  [--repo .] [--output-root <path>]
```

### `index`

```bash
failure-memory index [--area <area>] [--package <package>] \
  [--module <module>] [--grep <regex>] [--config <path>] [--repo .]
failure-memory index --expand <ID> [--config <path>] [--repo .]
```

Read-only. With no selector it lists the area, package and module groups;
with a selector it returns the matching lesson cards; `--expand` returns one
lesson's full record and annotations. See [Lesson index](lesson-index.md).

### `ci-check`

```bash
failure-memory ci-check [--config <path>] [--repo .]
```

## Refresh

```bash
failure-memory refresh <action> \
  [--config <path>] \
  --global-vault <path> \
  [--repo .] \
  [--phase 1] \
  [--generated-at <timezone-aware-ISO8601>] \
  [--force-lock]
```

Actions: `preflight`, `status`, `lessons`, `mirror`, `graph`, `all`, `clean`,
`if-stale`.

`clean` removes only paths marked disposable by project configuration.

### `refresh if-stale`

```bash
failure-memory refresh if-stale [--config <path>] --global-vault <path> \
  [--repo .] [--since <ref>] [--phase 1] [--force-lock]
```

Refreshes only what is out of date, in the same lessons, mirror, graph order:

- **Lessons** recompile only when `check` would report drift: the registry
  digest the generated nodes and route index embed no longer matches, a node
  is missing, or the compiler changed. Otherwise they are `current`.
- **Mirrors** are re-exported only for sources that changed. The bases are
  `--since` and the commit the previous `if-stale` run recorded, each with its
  merge base with `HEAD`. The exporter's own git selection
  (`export-akms --git-base`) picks the sources that differ between a base and
  the worktree, untracked files included, and removes the mirrors of deleted
  sources. When there is no usable base, there are no mirrors yet, the AKMS
  version, provider or `akms_repo_root` changed, the project root is not the
  git top level, or `.gitignore` or `.repo_wiki/config.yaml` changed, it runs
  the full configured `refresh mirror` instead. `selection` and `reason` in
  the result say which one ran and why. A source with uncommitted changes
  differs from every base, so it is re-exported on each run until it is
  committed.
- **The graph** is rebuilt when lessons or mirrors changed, or when it is
  missing.

Outputs whose `[generated]` policy is `committed` are never rewritten; their
stage reports `skipped`. Every output is stamped with the current UTC time:
`akms status` reports a mirror stale when its source was committed or modified
after the mirror's `generated_at`, so `--generated-at` is refused here. The
recorded commit lives in the worktree's git directory
(`git rev-parse --git-path akms-failure-memory/refresh-state.json`), never in a
tracked file.

## Git hooks

```bash
failure-memory hooks install [--repo .] [--config <path>] [--global-vault <path>]
failure-memory hooks status [--repo .]
failure-memory hooks uninstall [--repo .]
```

`install` adds a managed block to the `post-checkout`, `post-commit`,
`post-merge` and `post-rewrite` hooks in the directory git runs hooks from
(`git rev-parse --git-path hooks`, which follows `core.hooksPath` and is shared
by linked worktrees). The block calls `failure-memory hooks run <hook> "$@"`
with the Python that ran `install`; run `install` again after moving that
environment. `--global-vault` is required the first time and remembered after
that. `install` is idempotent: it reports each hook as `created`, `inserted`,
`updated` or `unchanged`. Running it again over an install that predates the
`post-commit` hook adds that hook and leaves the other three unchanged;
`status` reports such an install as `partial`.

- A hook that does not exist is created holding only the block, with mode
  `0700` (only its owner can read or run it). A shared repository whose hooks
  must also run for other users has to widen the mode itself (for example
  `chmod 755`); `install` and `uninstall` keep an existing hook's mode.
- An existing POSIX shell hook (`sh`, `bash`, `dash`, `ash`, `ksh`, `mksh`,
  `zsh`) gets the block inserted directly after its `#!` line, so an `exit`
  later in the hook cannot skip it. The block leaves `$@` and the hook's stdin
  to the rest of the hook, and everything outside its markers is kept byte for
  byte.
- A hook in another language, a symlinked hook, a hook git would not run
  (not executable), and a hook file tracked by git are refused with
  `hook_unsupported`, `hook_disabled` or `hook_tracked`, and no hook is
  changed. Call `failure-memory hooks run <hook> "$@"` from such a hook by hand.

`uninstall` removes exactly the block from each hook, deletes a hook only when
`install` created it and nothing was added to it since, and removes the git
config keys. `status` reports, per hook, whether the block is installed and
current, and the recorded settings.

The settings are kept in the repository's git config, not in a tracked file:

| Key | Value |
| --- | --- |
| `akms-failure-memory.globalVault` | the read-only global vault, absolute |
| `akms-failure-memory.root` | the project root, relative to the worktree top level |
| `akms-failure-memory.config` | the project config, relative to the project root |

The hooks never write to the global vault.

### `hooks run`

```bash
failure-memory hooks run post-checkout|post-commit|post-merge|post-rewrite [<hook arguments>...]
```

What the installed hooks call; it runs `refresh if-stale` from the hook's
arguments and **always exits 0**. It prints nothing when nothing was stale, one
summary line when it refreshed something, and one warning line when it could
not (a broken config, a missing vault, a busy project lock).

| Hook | Runs when | Base for mirrors |
| --- | --- | --- |
| `post-checkout` | a branch checkout (flag `1`); a file checkout (flag `0`) and the checkout that starts a rebase are skipped | the previous `HEAD`; after a clone or `worktree add` there is none, so a full export |
| `post-commit` | after `git commit`, including the commit that concludes a conflicted merge, and a single `cherry-pick` or `revert`; skipped while a rebase or `git am` is in progress and for an amend (`post-rewrite` covers both), and for every commit of a multi-commit `cherry-pick` or `revert` but the last | the commit's first parent; for the last commit of a `cherry-pick`/`revert` sequence, the commit the sequence started from; a root commit has none, so the recorded commit or a full export |
| `post-merge` | after `merge` and `pull` (a merge that stops on a conflict runs no hook; the `git commit` that concludes it runs `post-commit`) | `ORIG_HEAD` |
| `post-rewrite` | once at the end of a rebase; an `amend` outside a rebase | `ORIG_HEAD` for a rebase, `HEAD@{1}` for an amend |

Each git command therefore refreshes at most once: a rebase runs
`post-commit` for every commit it makes, but those runs are skipped and its
`post-rewrite` refreshes once at the end; an amend runs `post-commit` and then
`post-rewrite amend`, and only the second refreshes.

The hook does not wait for the project lock: if another failure-memory command
holds it, the hook warns and skips, and the next run catches up from the
recorded commit. Set `AKMS_FAILURE_MEMORY_HOOKS=0` to skip the hooks for one
command or a whole shell. A repository that shares a `core.hooksPath` with
this one but never ran `install` is left alone.

## Provider

### `resolve`

```bash
failure-memory resolve [--config <path>] --request request.json [--repo .]
```

### `validate-fingerprint`

```bash
failure-memory validate-fingerprint [--config <path>] \
  --request request.json --result result.json [--repo .]
```
