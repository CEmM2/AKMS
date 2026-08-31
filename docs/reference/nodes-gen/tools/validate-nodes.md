# `validate_nodes.py`

Cross-checks every generated AKMS node in `Packages/Nodes_Vault/` against
its source NotebookLM notebook by submitting the node content as a
validation query and recording the per-node JSON report.

## Location

`Packages/AKMS_nodes_gen/validate_nodes.py`

## Run it

```bash
# Validate every node
python Packages/AKMS_nodes_gen/validate_nodes.py

# Limit to one batch
python Packages/AKMS_nodes_gen/validate_nodes.py --batch R7_B2

# Preview without submitting
python Packages/AKMS_nodes_gen/validate_nodes.py --dry-run

# Concurrency knob
python Packages/AKMS_nodes_gen/validate_nodes.py --concurrency 4
```

## What it does

1. Walks `Packages/Nodes_Vault/<domain>/<id>.md` for every generated node.
2. Looks up the source notebook via the `generation_plan.md` tracker
   (the same plan the picker reads).
3. Submits the node content to the notebook as a validation query.
4. Saves a per-node JSON report.
5. Emits a summary CSV.

## Resumability

The script skips any node whose validation report already exists on disk.
Safe to interrupt and re-run.

## See also

- [Pipeline integration](../batch-picker/pipeline-integration.md)
- [`akms_node_promote.py`](akms-node-promote.md) — the next step once a node passes validation
