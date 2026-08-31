# `akms_node_promote.py`

Moves verified AKMS domain nodes from a staging folder into the global
vault (`~/.claude/akms/nodes/`) with domain-based subdirectory nesting.

## Location

`Packages/AKMS_nodes_gen/src/akms_nodes_gen/akms_node_promote.py`

## Run it

```bash
# Dry-run (default) — show what would happen, touch nothing
python -m akms_nodes_gen.akms_node_promote \
    --source Sources_Evals/NLM/Outputs/fft_nodes

# Actually move the files
python -m akms_nodes_gen.akms_node_promote \
    --source Sources_Evals/NLM/Outputs/fft_nodes --execute

# Move and promote frontmatter status: tentative → established
python -m akms_nodes_gen.akms_node_promote \
    --source Sources_Evals/NLM/Outputs/fft_nodes --execute --promote

# Override vault location
python -m akms_nodes_gen.akms_node_promote \
    --source ... --vault /custom/vault/path --execute
```

## Destination layout

Nodes land at `<vault>/<domain>/<filename>.md`, where:

- `<vault>` defaults to `Packages/Nodes_Vault/` inside the repo (override
  with `--vault` or `$AKMS_NODES_VAULT`).
- `<domain>` comes from the node's frontmatter `domain:` field.
- Dotted domains (e.g. `computational-mechanics.fft-galerkin`) create
  nested folders (`computational-mechanics/fft-galerkin/`).

## Flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--source` | (required) | Folder of staged `.md` nodes |
| `--vault` | `Packages/Nodes_Vault/` (or `$AKMS_NODES_VAULT`) | Destination root |
| `--execute` | (off) | Apply moves; without it, the script is a dry-run |
| `--promote` | (off) | Rewrite `status: tentative` → `status: established` in frontmatter as part of the move |

## Invariants the script respects

- The global vault `~/.claude/akms/nodes/` is **read-only** to automation
  in normal operation. Use `--vault` to point at the staging vault inside
  the repo (`Packages/Nodes_Vault/`).
- v2 schema fields are not edited beyond `status` (under `--promote`).

## See also

- [`validate_nodes.py`](validate-nodes.md) — run before promoting
- [Pipeline integration](../batch-picker/pipeline-integration.md)
