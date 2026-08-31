# Code-mirror providers

AKMS projects repository source into `knowledge/code-mirror/` for exact path
resolution, search, and review context. Projection is pluggable; graph and
loadout semantics remain in AKMS core.

## Defaults

| Setting | Default | Meaning |
|---|---|---|
| `mirror.provider` | `legacy` | In-process Python AST generator |
| `mirror.fallback_on_error` | `false` | No silent provider substitution |
| `mirror.require_success` | `false` | When true, the caller blocks graph rebuild after failure |
| `mirror.selection_mode` | `changed` | Select changes against the parent branch |

## Configuration

```yaml
akms_schema: v2
mirror:
  provider: repo2md
  command: [repo-wiki]
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

The command is an argv prefix, not a shell string.

## `legacy`

- Python-only AST projection
- In-process implementation
- Changed-file selection by default
- Structural drift analysis on the deterministic path

## `repo2md`

- Invokes `repo-wiki export-akms` with `shell=False`
- Does not import repo2md as a Python package
- Validates export schema, AKMS v2 frontmatter, output containment,
  content/source consistency, duplicate IDs, and completeness
- Uses a pinned consumer contract under `Packages/AKMS/release/`

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
