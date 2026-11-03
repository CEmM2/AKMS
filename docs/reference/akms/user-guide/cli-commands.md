# CLI reference

The `akms` entry point is implemented with `argparse`.

```bash
akms --help
akms <command> --help
```

`--repo` defaults to the current directory and is accepted on the top-level
parser and on subcommands.

`--version` prints `akms <version>`, where the version is read from the
installed distribution's metadata, and exits 0. Host adapters probe it before
`--help` to decide whether they can enforce a supported-version range.

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

These commands edit `.knowledge/local-nodes/<node_id>.md`, then delete the
compiled `.knowledge/graph/graph.json` and the qmd cache. They do not recompile
the graph themselves: the next `query`, `loadout` or `resolve-task` rebuilds it
from the node files, so a deprecated or suppressed node can no longer be
resolved as required from a stale graph. If the graph cannot be deleted, the
command exits 1 and tells you which file to remove.

## Graph inspection and selection

### `status`

```bash
akms status --repo . [--routes PATH ...]
```

Runs the graph health report using repository propagation configuration when
present. It warns under **Knowledge Layout** when `.knowledge/` exists next to
a non-empty `knowledge/`, whose contents are then ignored. Under **Stale Code
Mirrors** it lists mirrors older than their source, or says that all of them
are current or that the check was skipped; see
[mirror freshness](mirror_providers.md#freshness).

**Orphaned Nodes** lists nodes nothing reaches: no edge in or out, no
`load_with` hint naming them or named by them, and no route to them in the task
route index. A node loaded only through `load_with` (such as a failure-memory
lesson with related lessons) or only through an exact route is not an orphan.
Session nodes and code mirrors are never listed.

The section names the route index it used. Without `--routes`, `status` looks
for one in the same places as reviewer required-knowledge, in this order:
`task-routes.{yaml,yml,json}`, `graph/task-routes.{yaml,yml,json}`,
`routes/task-routes.{yaml,json}` and `failure-routes.{yaml,json}` under
`.knowledge/`, then the same under `knowledge/`, then
`generated/failure_routes.json` (the `akms-failure-memory` default) under
`.knowledge/` and then `knowledge/`. The first file found is used.
`--routes PATH` uses the given route index instead, relative to `--repo`; repeat
it to combine several. A route index that cannot be read or parsed is listed
under **Route Index Warnings** and ignored; the report still runs.

### `migrate-layout`

```bash
akms migrate-layout --repo . [--check] [--json]
```

Moves `<repo>/knowledge/` to `<repo>/.knowledge/`, re-anchors `.gitignore` and
`.gitattributes` lines on it, drops the compiled graph and qmd cache, and lists
other tracked lines that still mention `knowledge/`. `--check` changes nothing.
Projects using failure memory run `failure-memory migrate-layout` instead. See
[Moving to `.knowledge/`](knowledge-layout.md).

### `query`

```bash
akms query <tag> [<tag> ...] \
  --repo . \
  --role implementer \
  --max-depth 2 \
  [--graph .knowledge/graph/graph.json]
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
  [--provider legacy|builtin|repo2md] \
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
