# Other tools

Beyond the [Batch Picker](../batch-picker/index.md), the package ships a
handful of CLI scripts that handle other stages of the AKMS node lifecycle.

| Script | Stage | Page |
|--------|-------|------|
| `nlm_batch.py` | Serially generate one batch from its NotebookLM notebook | [nlm-batch](nlm-batch.md) |
| `generate_nodes_pipeline.py` | Batch-extract nodes from inventory JSONs | [generate-nodes-pipeline](generate-nodes-pipeline.md) |
| `validate_nodes.py` | Cross-check generated nodes against their source notebook | [validate-nodes](validate-nodes.md) |
| `akms_node_promote.py` | Move verified nodes from staging into the global vault | [akms-node-promote](akms-node-promote.md) |
| `extract_framework_nodes.py` | Convert deepwiki-eval results into framework nodes | [extract-framework-nodes](extract-framework-nodes.md) |

The picker writes the plan JSON and NotebookLM notebook metadata consumed by
`nlm_batch.py`. The older tools pre-date the picker and remain available for
the inventory-driven and promotion/validation stages. See
[Pipeline integration](../batch-picker/pipeline-integration.md) for how the
pieces connect.
