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

```bash
uv tool install akms-nodes-gen      # akms-pick on your PATH
# or
pip install "akms[nodes-gen]"
```

## Batch picker

```bash
akms-pick --plan path/to/generation_plan.md --bibtex-json path/to/library.json
```

The picker is a local web UI for assigning papers from a Zotero library to the
batches of a generation plan, staging their PDFs, creating one NotebookLM
notebook per batch, and writing per-batch plan JSON. It needs:

- a **generation plan**, anywhere on disk (`--plan`);
- a **Zotero library export** in Better BibTeX JSON format (`--bibtex-json`).

[zsum](https://github.com/CEmM2/zotero-summarizer) is optional. It keeps the
export current and adds per-paper summaries that improve search. Without it,
the picker says so in a banner and works from titles, abstracts and tags.

Its own files go in a workspace, by default the plan's directory
(`--workspace` to change it). Nothing needs an AKMS checkout. See the
[picker documentation](https://cemm2.github.io/AKMS/reference/nodes-gen/batch-picker/)
for the plan format and every option.

## Serial NotebookLM batch generation

`nlm_batch.py` runs one selected batch/cluster at a time. It does not hardcode
the NotebookLM prompt, source IDs, timeout, or output format; pass those at the
CLI boundary.

```bash
uv run python -m akms_nodes_gen.nlm_batch \
  --plan path/to/workspace/plans/R7_B2_pf_energy_solvers_plan.json \
  --batch-id R7_B2 \
  --out-dir outputs/R7_B2_pf_energy_solvers \
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
uv --project packages/akms_nodes_gen run --group docs \
  mkdocs build -f packages/akms_nodes_gen/mkdocs.yml
```

Main docs live in `packages/akms_nodes_gen/docs/`.
