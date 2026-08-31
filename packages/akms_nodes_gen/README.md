# AKMS Node Generation

Tooling for turning NotebookLM-curated paper batches into validated AKMS
knowledge nodes.

The package has two complementary flows:

- **Batch Picker**: a local UI for assigning papers to one NotebookLM notebook
  per AKMS batch.
- **NLM batch generator**: a serial CLI that asks a batch's NotebookLM notebook
  for structured YAML/JSON node output, then validates and writes the results
  locally.

## Install

From the AKMS repo root:

```bash
uv sync --project packages/akms_nodes_gen
```

If you also want the documentation toolchain:

```bash
uv sync --project packages/akms_nodes_gen --group docs
```

## Batch picker

```bash
uv --project Packages/AKMS_nodes_gen run akms-pick
```

The picker runs a local FastAPI UI for selecting papers, staging PDFs, creating
NotebookLM notebooks, and writing batch plan JSON files under
`Sources_Evals/NLM/Inputs/`.

## Serial NotebookLM batch generation

`nlm_batch.py` runs one selected batch/cluster at a time. It does not hardcode
the NotebookLM prompt, source IDs, timeout, or output format; pass those at the
CLI boundary.

```bash
uv run python -m akms_nodes_gen.nlm_batch \
  --plan Sources_Evals/NLM/Inputs/R7_B2_pf_energy_solvers_plan.json \
  --batch-id R7_B2 \
  --out-dir Sources_Evals/NLM/Outputs/R7_B2_pf_energy_solvers \
  --prompt-file path/to/notebooklm_prompt.md \
  --template-file path/to/output_template.yaml \
  --source-ids source_a,source_b \
  --timeout 180 \
  --output-format yaml
```

Useful safety controls:

- `--require-source-refs` is on by default and requires citations/source refs on
  equations, algorithms, pitfalls, and references.
- `--allow-invented-edges` is off by default; edge targets must match known plan
  IDs or Tier-1 node IDs.
- `--max-retries` controls local repair attempts when NotebookLM returns invalid
  structure.
- `--converter` and `--validator` can run the existing YAML-to-Markdown and node
  validation scripts after each YAML write.

The generator writes:

- `{node_id}.yaml`
- `_raw_responses/{node_id}.txt`
- `_nlm_cache/*.json`
- `_nlm_batch_state.json`

## Docs

Build the docs locally:

```bash
uv --project Packages/AKMS_nodes_gen run --group docs \
  mkdocs build -f Packages/AKMS_nodes_gen/mkdocs.yml
```

Main docs live in `Packages/AKMS_nodes_gen/docs/`.
