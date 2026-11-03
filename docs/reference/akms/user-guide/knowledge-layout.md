# Moving to `.knowledge/`

New repositories keep their AKMS knowledge in `<repo>/.knowledge/`. A
repository that already has `<repo>/knowledge/`, and no `.knowledge/`, keeps
using `knowledge/`: every reader resolves the directory the same way, so
nothing has to move. Move it when you want the new layout.

## Projects without failure memory

```bash
akms migrate-layout --repo . --check   # show what would change
akms migrate-layout --repo .
```

`migrate-layout`:

- moves `knowledge/` to `.knowledge/`, with `git mv` when the directory is
  tracked so its history follows (ignored and untracked files inside it move
  too);
- rewrites `.gitignore` and `.gitattributes` lines anchored on the old
  directory, such as `knowledge/sessions/` or `/knowledge/graph/graph.json`, in
  the repository root and, when the knowledge directory is below it, in the
  git top level;
- deletes the compiled graph and the qmd cache, which hold the old paths; the
  next `akms` command that needs them rebuilds them;
- in a git repository, lists every other tracked line that still says
  `knowledge/` (a `CLAUDE.md`, a CI job, a script, a pattern such as
  `**/knowledge/`) without changing it.

Node `content_ref` values are relative to the knowledge directory, so nodes
and code mirrors need no edits.

The command refuses to run when `.knowledge/` already holds files, when
`knowledge/` is a symbolic link, or when there is no `knowledge/`. If a step
fails part-way, it moves the directory back and restores the files it edited.

## Projects with failure memory

```bash
failure-memory migrate-layout --repo . --check
failure-memory migrate-layout --repo . --global-vault /read-only/vault
```

This runs the same move for the directory under `akms_repo_root`, under the
project lock, and also updates the failure-memory configuration:

- `[paths]` entries inside the old directory point into `.knowledge/`;
- `generated_warning` names the new registry path;
- a configuration stored inside the old directory moves with it, so
  `knowledge/failure-memory.toml` becomes `.knowledge/failure-memory.toml`
  (the command finds the old location when `--config` is not given).

The configuration fingerprint changes once. With `--global-vault`, generated
lessons are recompiled straight away; without it, the result names the
`failure-memory compile` command to run. Running the command again after a
plain `akms migrate-layout` fixes up the configuration alone.

## Both directories present

When `.knowledge/` exists, AKMS reads only `.knowledge/`, and anything left in
`knowledge/` is ignored. `akms status` reports this under
**Knowledge Layout**. Move what `knowledge/` still holds into `.knowledge/` by
hand, then delete it.
