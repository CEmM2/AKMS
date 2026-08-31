# Nodes Generation from NotebookLM

> **Provenance.** Published copy of the internal asset at `.claude/commands/node-gen-invoker.md`. It is a copy
> rather than a move: consumers of this repository (Logic-Loom vendors it via git
> subtree) reference the internal path, so relocating it would change that
> integration surface. Treat the internal copy as the source of truth and update
> both when behaviour changes.


## Goal
Invoke the `node-gen` skill to generate self-contained AKMS domain knowledge nodes by querying NotebookLM notebooks, outputting structured YAML, and converting to validated markdown.

## Instructions

Use the `node-gen` skill (`skills/node-gen/SKILL.md`) with the `extract` command.

Read the skill's bundled references (schema_compliance, akms_node_template, query_strategies) before starting.

When `NODE_SELECTION` is "all" and `PARALLEL` is false (default), process clusters in alphabetical order. After each cluster, run the validator and fix any errors before proceeding to the next cluster.

When `NODE_SELECTION` is "all" and `PARALLEL` is true, use wave-based dispatch as described in the skill's Batching Rules: group clusters into waves of 2–3 subagents, spawn one subagent per cluster, wait for the wave to complete and validate before starting the next wave.

## Arguments

Parse `$ARGUMENTS` as positional parameters in this order:

| Position | Name | Description | Required |
|----------|------|-------------|----------|
| 1 | `NLM_ID` | NotebookLM notebook UUID | yes |
| 2 | `NODE_SELECTION` | Node id, cluster letter (A–H), or `"all"` | yes |
| 3 | `PLAN_PATH` | Path to extraction plan JSON | yes |
| 4 | `OUT_DIR` | Output directory for YAML + markdown | no — defaults to `Sources_Evals/NLM/Outputs/{plan_name}/` |
| 5 | `PARALLEL` | `true` or `false` — enable wave-based parallel dispatch | no — defaults to `false` |

## Examples

```
# Sequential extraction (default)
/node-gen-invoker abc-def-123 all Sources_Evals/NLM/Inputs/fft_node_extraction_plan.json Sources_Evals/NLM/Outputs/fft_nodes/

# Parallel extraction — wave-based dispatch with 2–3 agents per wave
/node-gen-invoker abc-def-123 all Sources_Evals/NLM/Inputs/fft_node_extraction_plan.json Sources_Evals/NLM/Outputs/fft_nodes/ true

# Single cluster
/node-gen-invoker abc-def-123 C Sources_Evals/NLM/Inputs/fft_node_extraction_plan.json
```

## Post-extraction review (separate session, Opus-tier)

After extraction completes, run the review in a new session:

```
Use the node-gen skill (skills/node-gen/SKILL.md).

Command: review
OUT_DIR: Sources_Evals/NLM/Outputs/fft_nodes/
PLAN_PATH: Sources_Evals/NLM/Inputs/fft_node_extraction_plan.json
REPORT_PATH: Sources_Evals/NLM/Outputs/fft_nodes/review_report.md
```

