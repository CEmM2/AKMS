# CLI reference

The `akms` entry point is implemented with `argparse`.

```bash
akms --help
akms <command> --help
```

`--repo` defaults to the current directory and is accepted on the top-level
parser and on subcommands.

## Node lifecycle

### `promote`

```bash
akms promote <node_id> --repo .
```

Promotes a **local** node from tentative to established. Other current statuses
are rejected.

### `suppress`

```bash
akms suppress <node_id> --repo .
```

Sets a local node's status to draft.

### `deprecate`

```bash
akms deprecate <node_id> --repo .
```

Sets a local node's status to deprecated.

These commands edit `knowledge/local-nodes/<node_id>.md`. They do not claim to
recompile the graph automatically; rebuild through a query/loadout, Python API,
or explicit project workflow afterward.

## Graph inspection and selection

### `status`

```bash
akms status --repo .
```

Runs the graph health report using repository propagation configuration when
present.

### `query`

```bash
akms query <tag> [<tag> ...] \
  --repo . \
  --role implementer \
  --max-depth 2 \
  [--graph knowledge/graph/graph.json]
```

Roles: `implementer`, `code_reviewer`, `physics_reviewer`.

### `loadout`

```bash
akms loadout <task_id> \
  --repo . \
  --phase <n> \
  --tags <tag> [<tag> ...] \
  [--role implementer] \
  [--mode routing|full] \
  [--max-depth 2] \
  [--available-context <tokens>] \
  [--graph <path>] \
  [--output <path>]
```

## Exact task resolution

### `resolve-task`

```bash
akms resolve-task \
  --repo . \
  --task-json <task.json> \
  --routes <routes.json|routes.yaml> \
  [--role implementer] \
  [--phase <n>] \
  [--changed-paths <paths.json> | --base <rev> [--head <rev>]] \
  [--mode routing|full] \
  [--max-depth 2] \
  [--available-context <tokens>] \
  [--graph <path>] \
  [--output <loadout-path>] \
  [--manifest <manifest-path>]
```

Stdout is always machine-readable JSON. See
[Resolve exact task context](task-resolution.md).

## Mirror providers

### `mirror-status`

```bash
akms mirror-status --repo . [--config <path>] [--json]
```

Reports non-secret provider identity and known provider names.

### `generate-mirror`

```bash
akms generate-mirror \
  --repo . \
  [--config <path>] \
  [--phase 1] \
  [--parent-branch main] \
  [--path <path> ...] \
  [--provider legacy|repo2md] \
  [--json]
```

Repeated `--path` values override git-based changed-file selection.

## Optional staged runner

### `orchestrate`

```bash
akms orchestrate \
  --repo . \
  [--plan <name>] \
  [--config <path>] \
  [--backend claude-sdk|claude-cli|codex-sdk|codex-cli|local] \
  [--agent package.module.AgentClass] \
  [--model <model>] \
  [--resume] \
  [--terminal] \
  [--spec <path>] \
  [--goal <text>]
```

`--agent` overrides `--backend`. Omitting both uses the default `AKMSAgent`.
This command is optional; it is not needed for graph or task-context operations.

## Node validator

The validator remains a module entry point:

```bash
python -m akms.tools.node_validator <path>
```

Use its own `--help` output as the authoritative flag list.

## Environment

| Variable | Meaning |
|---|---|
| `AKMS_GLOBAL_VAULT` | Override global node-vault path |
| `AKMS_LLM_API_BASE` | Base URL used by the optional local runtime adapter |
| `AKMS_TELEMETRY` | Optional telemetry mode used by runtime instrumentation |

Provider- and CLI-specific external executables must be available on `PATH` only
when those optional commands are used.
