---
name: deepwiki-nodes
description: "Generate AKMS domain knowledge nodes from a GitHub repository indexed by DeepWiki. Queries DeepWiki's MCP server for algorithms, formulations, and pitfalls, writes structured YAML, and converts it to schema-valid AKMS markdown. Use when the knowledge you need is embodied in a public codebase rather than in papers — a solver, a framework, a reference implementation. Triggers on: 'generate nodes from deepwiki', 'extract knowledge from a repo', 'akms nodes from github', 'deepwiki to akms', 'document this framework as nodes', 'what does this library know'."
---

> **Provenance.** Reworked from the internal `.claude/skills/deepwiki-eval/`, which
> scores DeepWiki output against expert ground truth to decide whether a repo is
> worth extracting from. That skill answers *"is this source good enough?"*. This
> one answers *"turn this source into nodes"* — the query engine is shared, the
> purpose is not. Run the internal eval skill first if you do not yet trust the
> source; run this one once you do.

## Goal

Turn a DeepWiki-indexed repository into schema-valid AKMS knowledge nodes.

This is the sibling of [`node-gen`](../node-gen/), which extracts from NotebookLM
notebooks (papers). Use `deepwiki-nodes` when the authoritative knowledge lives in
**code** — a solver's actual return-mapping loop, a framework's real assembly
path — and `node-gen` when it lives in **literature**.

**Success criterion (same bar as `node-gen`):** a first-year PhD student can
implement the node from its content alone, without opening the repository.

## Requirements

- Network access to `https://mcp.deepwiki.com/mcp` — free, no auth. (Or
  `https://mcp.devin.ai/mcp` with `--auth <key> --org <id>`.)
- The target repo must already be indexed by DeepWiki. Check with `--discover`.
- `akms` installed, for validation.

No MCP server registration is needed: the bundled engine speaks to the endpoint
over HTTP directly, which keeps the ~35-tool DeepWiki MCP surface out of your
context.

## Inputs

| Input | Description | Default |
|---|---|---|
| `REPO` | GitHub `owner/name`, indexed by DeepWiki | *(required)* |
| `NODE_PLAN` | Which nodes to create — see step 2 | *(required)* |
| `QUERY_FILE` | Working file holding queries and responses | `Sources_Evals/DeepWiki/{repo}.md` |
| `OUT_DIR` | Where YAML and markdown land | `knowledge/local-nodes/` |

## Workflow

### 1. Confirm the repo is indexed and see its shape

```bash
uv run python skills/deepwiki-nodes/scripts/deepwiki_query.py --discover
```

Then scaffold a query file and ask DeepWiki for the wiki structure:

```bash
bash skills/deepwiki-nodes/scripts/run_queries.sh Sources_Evals/DeepWiki/myrepo.md --repo owner/name
```

The first invocation **creates** the file from the template and exits. Fill in
topics and queries, then run the same command again to execute them. See
`references/query_file_format.md` for the format.

Start with one `[read_wiki_structure]` query. Its answer is your node plan input:
DeepWiki's own topic decomposition is usually a reasonable first cut at node
boundaries.

### 2. Decide the node boundaries — do not skip this

One node per **self-contained piece of knowledge**, not one per source file and
not one per wiki page. A node that says "this repo has a solver module" is
worthless; a node that says "how this solver's return mapping converges, and the
two ways it fails" is worth having.

Write the plan down before querying. For each intended node: `id`, `title`,
`domain`, `tags`, and one sentence on what it must let a reader do.

### 3. Query for node content, not for prose

Ask questions shaped like the node body you have to fill. The AKMS validator
requires `## Summary` and recognises `## Known Pitfalls`, so query for exactly
those. Use `references/extraction_queries.md` — it carries a query set per node
section, and the pitfall queries are the ones that pay for the exercise, because
pitfalls are what an agent cannot derive from first principles.

```bash
bash skills/deepwiki-nodes/scripts/run_queries.sh Sources_Evals/DeepWiki/myrepo.md
```

Responses are injected back into the query file beneath each query, so the file
becomes the audit trail of where each node claim came from.

### 4. Write YAML, then convert

Transform the responses into one YAML document per node, following
`../node-gen/references/akms_node_template.md` — the schema is identical
regardless of source. Then reuse `node-gen`'s converter rather than duplicating
it:

```bash
uv run python skills/node-gen/scripts/akms_node_convert.py {OUT_DIR}/{id}.yaml -v
uv run python skills/node-gen/scripts/akms_node_clean.py {OUT_DIR}/{id}.md --validate-only -v
```

### 5. Validate and compile

```bash
python -m akms.tools.node_validator knowledge/local-nodes/ --strict
akms status --repo .
```

`--strict` will flag a missing `## Summary` as an error and a node with no edges
as a warning. Both are real: the summary is the only text routing-mode loadouts
display, and an edgeless node is unreachable from any related node.

## Provenance and honesty rules

Every node generated this way is **agent-authored from a secondary source**.
DeepWiki is AI-generated documentation *about* a codebase — it is not the codebase
and not a paper.

- `source: agent` and `status: tentative`. Never `established` — that is a human
  judgement made after the node has proven correct in use.
- Record the repo and the query file in the node body so a reader can retrace the
  claim.
- If DeepWiki's answer is vague, hedged, or contradicts itself, **do not write the
  node**. A confidently-worded node built on a vague answer is worse than no node,
  because it will be retrieved and trusted.
- When a claim matters and DeepWiki is thin, read the actual source file it points
  at and cite that instead.

## When to use the eval skill first

If you do not already know that DeepWiki covers this repo well, run the internal
`deepwiki-eval` skill against a handful of topics with ground truth you can check.
It exists precisely to stop you building an extraction pipeline on a source that
cannot support one. This skill assumes that question is already settled.

## Bundled files

- `scripts/deepwiki_query.py` — query engine (HTTP to DeepWiki MCP, response injection)
- `scripts/run_queries.sh` — scaffold-or-run wrapper
- `references/extraction_queries.md` — query sets per node section
- `references/query_file_format.md` — query file specification
- `references/query_file_template.md` — scaffold template

Conversion and validation are deliberately **not** duplicated here — they live in
[`../node-gen/scripts/`](../node-gen/) and are shared, because the node schema does
not depend on where the knowledge came from.
