# Installation

## Supported Python ranges

| Component | Declared range |
|---|---|
| `akms` | `>=3.11,<3.14` |
| `akms-nodes-gen` | `>=3.11,<3.14` |
| `akms-learn` | `>=3.11,<3.14` |
| `compmech-reference-pack` | `>=3.11,<3.14` |
| `akms-failure-memory` | `>=3.12,<3.13` |

Use Python 3.12 for a complete-workspace environment.

## Source checkout

The documentation currently assumes a repository checkout rather than a PyPI
release.

### Core package only

```bash
uv sync --project Packages/AKMS --all-extras --all-groups
uv run --project Packages/AKMS akms --help
```

### Complete workspace

```bash
uv sync --all-packages --all-extras --all-groups
```

The root workspace path-sources `mechdsl-core` and `algo2code` from the sibling
checkout `../MechDSL`. A complete all-extras sync therefore requires that
layout. Use the package-scoped command for core work when the sibling adapter
repository is absent.

## Global vault

The default global node directory is:

```text
~/.claude/akms/nodes/
```

Vault resolution precedence is:

1. Explicit Python argument
2. `AKMS_GLOBAL_VAULT`
3. `global_vault` in `knowledge/graph/propagation_config.yaml`
4. The default above

The graph compiler tolerates a missing or empty vault. Create it manually when
you intend to use shared nodes:

```bash
mkdir -p ~/.claude/akms/nodes
```

Automated AKMS operations treat this directory as read-only.

## Verify the core CLI

```bash
uv run --project Packages/AKMS akms --help
uv run --project Packages/AKMS akms status --repo .
```

`status` reports the graph inputs it can find; it does not require a non-empty
global vault.

## Optional external tools

- `qmd` is an external search binary. The core package pins the expected version
  in package metadata and falls back through its wrapper when unavailable.
- `repo2md` is invoked only through its configured CLI contract by the
  `repo2md` mirror provider.
- `nlm` is an external NotebookLM CLI used by selected node-generation and
  learning-provider workflows.
- Claude/Codex CLI executables are required only for their corresponding
  optional pipeline backends.
