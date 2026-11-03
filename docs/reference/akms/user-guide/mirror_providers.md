# Code-mirror providers

AKMS projects repository source into `.knowledge/code-mirror/` for exact path
resolution, search, and review context. Projection is pluggable; graph and
loadout semantics remain in AKMS core.

A code mirror is **generated from your own repository**, not shipped with AKMS.
Nothing arrives pre-populated and there is nothing to download: you produce one
with `akms generate-mirror` and refresh it as the source changes. A mirror is
build output, and like build output it belongs to the tree it was projected
from.

## Defaults

| Setting | Default | Meaning |
|---|---|---|
| `mirror.provider` | `builtin` | The `repo-wiki` exporter shipped in akms |
| `mirror.fallback_on_error` | `false` | No silent provider substitution |
| `mirror.require_success` | `false` | When true, the caller blocks graph rebuild after failure |
| `mirror.selection_mode` | `changed` | Select changes against the parent branch |

## Configuration

```yaml
akms_schema: v2
mirror:
  provider: builtin
  timeout_seconds: 120
  fallback_on_error: false
  require_success: true
  generated_at_source: source_date_epoch
  selection_mode: full
  prune: false
  force_lock: false
  expected_export_schema_version: 1
  expected_akms_schema_version: v2
```

For `repo2md`, add `command: [repo-wiki]`: an argv prefix, not a shell string.
`builtin` ignores `command`.

## `builtin`

The default. Runs the `repo-wiki` exporter that ships in `akms`, as
`python -m akms.repo_wiki export-akms`, in a subprocess. Nothing else needs to
be installed for Python sources; C++ uses an installed `doxygen`, and Rust,
C++ (tree-sitter) and Julia need `akms[multilang]`.

- Writes mirrors into the knowledge directory the graph reads:
  `.knowledge/code-mirror/`, or `knowledge/code-mirror/` in a repository that
  only has the older `knowledge/` directory
- Same export contract, validation, timeout and output lock as `repo2md`
- `.repo_wiki/config.yaml` controls which sources and languages are exported
- With `selection_mode: changed`, it exports sources changed since the parent
  branch, as `git diff <parent>` sees them (committed and uncommitted changes
  to tracked files). In a directory that is not a git repository, or where the
  parent branch does not exist, it selects nothing and logs a warning, as
  `legacy` does

## `legacy`

The in-process Python AST generator, and the default before `builtin`. It
needs nothing installed beyond `akms` itself.

- Python-only AST projection
- In-process implementation
- Changed-file selection by default
- Structural drift analysis on the deterministic path

## `repo2md`

Requires a separately installed `repo-wiki` executable, which **AKMS does not
install**.
It is registered lazily and invoked only when you configure
`mirror.provider: repo2md`, so its absence costs nothing until then. Because
`mirror.fallback_on_error` defaults to `false`, configuring this provider
without the binary present fails loudly rather than silently reverting to
`legacy` — set that flag to `true` if you would rather it fell back.

- Invokes `repo-wiki export-akms` with `shell=False`
- Does not import repo2md as a Python package
- Validates export schema, AKMS v2 frontmatter, output containment,
  content/source consistency, duplicate IDs, and completeness

An external `repo-wiki` always writes its mirror to
`<repo>/knowledge/code-mirror/`, so a repository whose knowledge lives in
`.knowledge/` does not load that mirror into its graph. Use `builtin` there.

## CLI

```bash
akms mirror-status --repo . --json
akms generate-mirror --repo . --phase 1 --path src/foo.py --json
```

## Provider independence

After equivalent schema-valid mirrors exist on disk, provider choice must not
change route resolution or loadout semantics. Required/coactivated/advisory
selection belongs to graph/task-context services, not the projector.

## Failures and fallback

Provider timeout, nonzero exit, malformed JSON, path escape, schema mismatch,
duplicate IDs, and incomplete output are explicit failures. Fallback occurs only
when configured; it is never silent.
