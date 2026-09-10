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

## Install from PyPI

```bash
pip install akms
akms --help
```

That is the deterministic core: graph compilation, task-context resolution,
loadouts and the CLI. The companion packages are independent installs:

```bash
pip install akms-learn                # learning-packet compiler
pip install akms-nodes-gen            # node generation and validation tooling
pip install akms-failure-memory       # project-owned failure memory
pip install compmech-reference-pack   # computational-mechanics companion adapter
```

`compmech-reference-pack` bridges computational-mechanics learning packets to
the [MechDSL](https://github.com/CEmM2/MechDSL) executable backend. The compile
and verify path is an extra, so the backend is not pulled in unless you ask
for it:

```bash
pip install "compmech-reference-pack[mechdsl]"
```

The optional embedded coding-agent runtime is an extra rather than a separate
package:

```bash
pip install "akms[orchestration]"
```

## Global vault

AKMS compiles a graph from two inputs: nodes local to your repository, and a
**global vault** of shared nodes. The vault is a directory of Markdown nodes
resolved in this order:

1. Explicit Python argument
2. `AKMS_GLOBAL_VAULT`
3. `global_vault` in `knowledge/graph/propagation_config.yaml`
4. `~/.claude/akms/nodes/`

**No vault ships inside the `akms` package.** A vault is content with its own
life cycle — nodes are added, corrected and forked far more often than code is
released — so vaults are distributed separately and installed deliberately.
Check what you have:

```bash
akms vault status
```

To install one from a directory, a `.tar.gz`, or an https URL to a released
vault archive:

```bash
akms vault install ./my-vault
akms vault install https://example.org/vault-v1.0.0.tar.gz
```

`vault install` refuses to replace a vault that already holds nodes unless you
pass `--force`, and refuses a source whose Markdown declares no `akms_schema`.
Use `--dest` to install somewhere other than the resolved location.

The graph compiler tolerates a missing or empty vault, so AKMS is usable
against repository-local nodes alone. Aside from `vault install`, which you run
yourself, automated AKMS operations treat this directory as read-only.

## Source checkout

For contributing, or to run against unreleased code:

```bash
git clone https://github.com/CEmM2/AKMS
cd AKMS
uv sync --all-packages --all-extras --all-groups
```

To work on the core package alone:

```bash
uv sync --project packages/akms --all-extras --all-groups
uv run --project packages/akms akms --help
```

## Verify

```bash
akms --help
akms status --repo .
akms vault status
```

`status` reports the graph inputs it can find; it does not require a non-empty
global vault.

## Optional external tools

None of these are installed by AKMS, and none are required.

- **`qmd`** — an external search binary used to rank node and mirror content.
  The wrappers detect it and fall back to `grep` when it is absent.
- **`repo-wiki`** — required only by the `repo2md` mirror provider. Code mirrors
  default to the `legacy` provider, an in-process Python AST projection that
  needs nothing external, so this matters only if you explicitly configure
  `mirror.provider: repo2md`. See
  [Code-mirror providers](../../reference/akms/user-guide/mirror_providers.md).
- **`nlm`** — an external NotebookLM CLI used by selected node-generation and
  learning-provider workflows.
- **Claude / Codex CLI** — required only by their corresponding optional
  pipeline backends.
