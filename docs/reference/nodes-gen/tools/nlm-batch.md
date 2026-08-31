# `nlm_batch.py`

Serial NotebookLM-backed batch generation for AKMS nodes.

Unlike `generate_nodes_pipeline.py`, this tool does not call Anthropic or a
second orchestration LLM. Python owns the batch orchestration and local gates;
NotebookLM owns source-grounded synthesis from the selected batch notebook.

## Location

`Packages/AKMS_nodes_gen/src/akms_nodes_gen/nlm_batch.py`

## When to use it

Use this when each AKMS batch already has its own NotebookLM notebook and you
want repeatable, resumable extraction from that notebook.

Prefer this path when:

- source grounding matters more than broad model knowledge
- the Batch Picker already recorded the notebook ID in the plan JSON
- you want the prompt, source IDs, timeout, and output format controlled outside
  the Python file
- you want local schema, edge, citation, cache, and retry gates before review

Use `generate_nodes_pipeline.py` when you need the older inventory-driven
Anthropic/MCP path.

## Run it

```bash
uv run python -m akms_nodes_gen.nlm_batch \
  --plan Sources_Evals/NLM/Inputs/R7_B2_pf_energy_solvers_plan.json \
  --batch-id R7_B2 \
  --out-dir Sources_Evals/NLM/Outputs/R7_B2_pf_energy_solvers \
  --prompt-file dev/AKMS_gen_prompts/notebooklm_node_prompt.md \
  --template-file .agents/skills/node-gen/references/akms_node_template.md \
  --source-ids source_a,source_b \
  --timeout 180 \
  --output-format yaml
```

If the selected cluster or top-level plan contains `nlm.notebook_id`, you can
omit `--notebook-id`. Use `--notebook-id` to override the plan.

## Inputs

| Flag | Required | Notes |
|------|----------|-------|
| `--plan` | yes | Batch plan JSON from the picker or hand-authored extraction plan |
| `--batch-id` | when plan has multiple clusters | Selects one cluster/batch to run serially |
| `--out-dir` | yes | Writes YAML, raw responses, cache, and state |
| `--prompt-file` | yes | NotebookLM prompt text; placeholders are supported |
| `--template-file` | no | Output schema/template text appended to each query |
| `--notebook-id` | no | Overrides `cluster.nlm.notebook_id`, `cluster.notebook_id`, or `plan.nlm.notebook_id` |
| `--source-id` | no | Repeatable source ID filter |
| `--source-ids` | no | Comma-separated source ID filter |
| `--source-ids-file` | no | One source ID per line; comments starting with `#` are ignored |
| `--timeout` | yes | Passed to `nlm notebook query --timeout` |
| `--output-format` | yes | `yaml` or `json` |
| `--profile` | no | `nlm` auth profile |

Prompt placeholders:

- `{node_id}` / `{{NODE_ID}}`
- `{node_title}` / `{{NODE_TITLE}}`
- `{node_source}` / `{{NODE_SOURCE}}`
- `{batch_id}` / `{{BATCH_ID}}`
- `{batch_name}` / `{{BATCH_NAME}}`
- `{notebook_id}` / `{{NOTEBOOK_ID}}`
- `{output_format}` / `{{OUTPUT_FORMAT}}`

## Local gates

The generator follows the mitigation strategy used for NLM-only generation:

- parses fenced YAML/JSON from `nlm notebook query --json`
- caches each exact prompt/options pair under `_nlm_cache/`
- writes raw NotebookLM answers under `_raw_responses/`
- keeps resumable progress in `_nlm_batch_state.json`
- requires schema defaults such as `status: tentative`, `source: hybrid`,
  `content_ref: null`, and `akms_schema: v2`
- validates edge types and blocks unknown edge targets unless
  `--allow-invented-edges` is set
- requires `source_ref`/`source`/`citation` on equations, algorithms, and
  pitfalls unless `--no-require-source-refs` is set
- retries invalid responses with a repair prompt up to `--max-retries`

## Optional conversion and validation

To derive Markdown and validate it after each YAML write:

```bash
uv run python -m akms_nodes_gen.nlm_batch \
  --plan Sources_Evals/NLM/Inputs/R7_B2_pf_energy_solvers_plan.json \
  --batch-id R7_B2 \
  --out-dir Sources_Evals/NLM/Outputs/R7_B2_pf_energy_solvers \
  --prompt-file dev/AKMS_gen_prompts/notebooklm_node_prompt.md \
  --template-file .agents/skills/node-gen/references/akms_node_template.md \
  --source-ids-file Sources_Evals/NLM/Inputs/R7_B2_sources.txt \
  --timeout 180 \
  --output-format yaml \
  --converter .agents/skills/node-gen/scripts/akms_node_convert.py \
  --validator .agents/skills/node-gen/scripts/akms_node_clean.py
```

## Outputs

| Path | Purpose |
|------|---------|
| `{out_dir}/{node_id}.yaml` | Canonical structured node output |
| `{out_dir}/{node_id}.md` | Optional converter output |
| `{out_dir}/_raw_responses/{node_id}.txt` | Raw NotebookLM response for audit |
| `{out_dir}/_nlm_cache/*.json` | Prompt/options response cache |
| `{out_dir}/_nlm_batch_state.json` | Completed and failed node state |

## Failure handling

Failures are recorded per node in `_nlm_batch_state.json`. Fix the prompt,
template, source IDs, or notebook sources, then rerun. Completed nodes are
skipped unless `--force` is provided.

For source gaps, prefer changing the notebook/source set over weakening local
validation. Use `--no-require-source-refs` only for exploratory dry runs or
manual triage.
