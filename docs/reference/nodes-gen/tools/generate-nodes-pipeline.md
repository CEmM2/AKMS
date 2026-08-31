# `generate_nodes_pipeline.py`

Batch-runs the node-extraction step over inventory JSONs. Reads a folder of
inventory files, groups their nodes into batches, calls the Anthropic API
(or a NotebookLM MCP endpoint) per batch, validates the output against the
v2 schema, and writes clean Markdown files.

## Location

`Packages/AKMS_nodes_gen/src/akms_nodes_gen/generate_nodes_pipeline.py`

## Run it

```bash
# All inventory JSONs in a folder
python -m akms_nodes_gen.generate_nodes_pipeline \
    --input json/ --output generated_nodes/

# New nodes only (skip exists / exists-enrich)
python -m akms_nodes_gen.generate_nodes_pipeline \
    --input json/ --output generated_nodes/ --status new

# A specific inventory file
python -m akms_nodes_gen.generate_nodes_pipeline \
    --input json/2c_constit_plasticity.json --output generated_nodes/

# Preview only (no API calls)
python -m akms_nodes_gen.generate_nodes_pipeline --input json/ --dry-run

# Resume from a specific batch index
python -m akms_nodes_gen.generate_nodes_pipeline \
    --input json/ --output generated_nodes/ --resume-from 5

# Drive a NotebookLM MCP endpoint
python -m akms_nodes_gen.generate_nodes_pipeline \
    --input json/ --output generated_nodes/ \
    --notebooklm-id <notebook-uuid> \
    --notebooklm-url https://your-nlm-mcp/sse
```

## Required env

| Variable | Required | Notes |
|----------|----------|-------|
| `ANTHROPIC_API_KEY` | yes | Anthropic API auth for batch generation |

## Where it fits

This is the **automated** alternative to running `node-gen-invoker` from
the AKMS skill. The Batch Picker writes its plan JSONs in a different
shape (consumed by the skill); `generate_nodes_pipeline.py` consumes
inventory JSONs from `Packages/AKMS_nodes_gen/Inventory_files/` directly.

## See also

- [Pipeline integration](../batch-picker/pipeline-integration.md) — how the picker hands off to `node-gen-invoker`
- [`validate_nodes.py`](validate-nodes.md) — the natural follow-up step
