---
name: akms
description: "Use AKMS to get the right domain knowledge into a coding task and to record what was learned. Compile a knowledge graph from a vault plus project-local nodes, resolve exact task context for changed paths, generate role-scoped loadouts, and update node confidence from outcomes. Use when a task needs established domain knowledge, when you must guarantee that specific files or symbols are covered by knowledge before editing them, or when finishing work that should feed knowledge back. Triggers on: 'akms', 'knowledge graph', 'resolve task context', 'generate loadout', 'what do we know about', 'load domain knowledge', 'required knowledge for these paths', 'update node confidence'."
---

## Goal

Put the knowledge a task actually needs in front of the agent doing it, and
feed the outcome back so the graph improves.

AKMS is not a search index you dip into. It is a compile → resolve → load →
update loop. Skipping the update step is the most common way teams get no value
from it.

## Before you start

```bash
uv pip install akms          # or: pip install akms
akms --help
```

Two facts that govern everything below:

- **The global vault is read-only.** Nothing you run may write to
  `~/.claude/akms/nodes/` (override with `$AKMS_GLOBAL_VAULT`). Project-local
  knowledge is the only thing that changes.
- **The v2 schema is frozen.** Node frontmatter fields are fixed. Adding or
  retyping a required field is a breaking change, not an edit.

## Repository layout

AKMS serves a project from that project's own directory:

```text
knowledge/
  local-nodes/      # project-owned knowledge nodes (markdown + v2 frontmatter)
  graph/graph.json  # compiled graph (generated)
  loadouts/         # generated per-task context files
  resolution-manifests/   # generated proof of what was resolved and why
  code-mirror/      # optional: projected code summaries for search
```

Create the minimum with:

```bash
mkdir -p knowledge/local-nodes knowledge/graph
```

## The loop

### 1. Compile

```bash
akms status --repo .
```

`status` compiles the graph if it is missing and reports health: low-confidence,
tentative, and orphaned nodes. Run it first — it tells you whether the graph is
worth querying at all. An empty or orphan-heavy graph means later steps will
return little, and that is a knowledge problem, not a tooling problem.

Python:

```python
from akms.graph.build_graph import build_graph
graph = build_graph(".")
```

### 2. Get context — pick the right path

This is the decision that matters most.

**Exploratory — "what do we know about X?"** Tag matching, ranked, best-effort:

```bash
akms query fem assembly --repo . --role implementer --max-depth 2
```

**Mandatory — "these paths must be covered before I touch them."** Exact
resolution against a route index, fail-closed:

```bash
akms resolve-task \
  --repo . \
  --task-json dev/tasks/fix-constitutive-update.json \
  --routes knowledge/task-routes.yaml \
  --base main --head HEAD \
  --role implementer \
  --mode routing
```

Use `resolve-task` whenever the task names files or symbols that *must* be
covered. It emits a loadout **and** a resolution manifest recording what was
selected and why, and it exits nonzero with a structured `error_code` rather
than quietly returning a partial match.

> A tag match is a ranking signal, not a guarantee. Do not treat
> `akms query` returning results as evidence that required knowledge exists.
> That inversion — "it returned something, so we're covered" — is the single
> most common misuse of this system.

Roles are `implementer`, `code_reviewer`, `physics_reviewer`, and they change
which nodes rank and how much content is pulled.

### 3. Load out

```bash
akms loadout assembly-demo \
  --repo . --phase 1 \
  --tags fem assembly \
  --role implementer \
  --mode routing
```

- `--mode routing` (default) writes references — cheap, and the agent reads
  what it needs.
- `--mode full` inlines node content subject to a token budget.

Default output: `knowledge/loadouts/<phase>-<task>-loadout.md`.

### 4. Update — do not skip this

When work finishes, feed the outcome back so nodes that helped gain confidence
and nodes that misled lose it:

```python
from akms.graph.update_graph import update_graph
update_graph(".", source_json="path/to/agent_memory.json")
```

Node lifecycle from the CLI:

```bash
akms promote <node-id> --repo .     # tentative -> established
akms suppress <node-id> --repo .    # -> draft, stops it surfacing
akms deprecate <node-id> --repo .   # retire it
```

**Agent-authored local nodes must enter as `tentative`.** Only human-authored
nodes may start `established`. Promotion is a deliberate act after the node has
proven correct — not something to do at creation time because it ranks better.

## Writing a node

Minimum valid v2 local node — the required identity fields are `id`, `title`,
`domain`, and at least one tag:

```markdown
---
id: fem-assembly
title: Finite-element global assembly
domain: computational-mechanics
subdomain: finite-elements
tags: [fem, assembly, sparse-matrices]
status: tentative        # agent-authored nodes start here
confidence: 0.5
source: agent
edges: []
load_with: []
context_size: medium
reading_priority: summary
content_ref: knowledge/local-nodes/fem-assembly.md
akms_schema: v2
---

# Finite-element global assembly

## Summary

Global assembly maps each element's local degrees of freedom onto global
indices and scatter-adds its residual and tangent contributions into the global
sparse system. It is the step that turns independent element computations into
one solvable system, and it is where degree-of-freedom bookkeeping errors
usually enter.

## 1. Core Concept

Build a local-to-global index map per element, then accumulate.

## 4. Known Pitfalls

Apply essential boundary conditions consistently to both residual and tangent.
Do not silently mix local and global degree-of-freedom numbering.
```

`## Summary` is **required** — it is the text routing-mode loadouts display, so
for most retrievals it is the only part of the node an agent reads. The pitfalls
heading must be `## Known Pitfalls` (or `## 4.`/`## 5. Known Pitfalls`);
`## Pitfalls` is not recognised. `## 1. Core Concept` and
`## 2. Mathematical Formulation` are recommended.

A node earns its place by being implementable from its own content. If a reader
would still have to go find the paper, the node is not finished.

See `references/node_authoring.md` for the full field reference and
`scripts/new_node.py` to scaffold one.

## Full CLI surface

| Command | Purpose |
|---|---|
| `akms status` | Graph health report (compiles if needed) |
| `akms query <tags…>` | Ranked tag query |
| `akms loadout <task-id>` | Query + write a loadout |
| `akms resolve-task` | Exact resolution → loadout + manifest (fail-closed) |
| `akms promote/suppress/deprecate <id>` | Node lifecycle |
| `akms orchestrate` | Run the orchestrator pipeline |
| `akms mirror-status` | Show configured code-mirror provider identity |
| `akms generate-mirror` | Refresh code mirrors via that provider |

All accept `--repo/-r` (default: current directory). Most print JSON on stdout.

## Using AKMS over MCP instead

If you would rather call tools than shell commands, AKMS ships a stdio MCP
server exposing the same surfaces as `mcp__akms__akms_*`:

```bash
akms-mcp-stdio --repo-root .
```

See `references/mcp_setup.md` for registration and the full tool list. Note how
search degrades: `run_qmd.sh` ships with the package, so if the `qmd` binary is
missing the wrapper falls back to grep-style matching rather than failing; only
a broken install makes `akms_search_*` return an empty list. Either way an empty
result is not evidence that the knowledge is absent.

## Failure modes worth knowing

| Symptom | Likely cause |
|---|---|
| Query returns nothing | Graph never compiled, or local-nodes dir is empty. Run `akms status`. |
| Loadout is empty but the task clearly has knowledge | Tags didn't match. Use `resolve-task` with a route index instead of guessing tags. |
| `resolve-task` exits nonzero | Working as designed — read `error_code`. It refuses to emit a partial answer. |
| `akms_search_*` returns `[]` | `qmd` / `run_qmd.sh` missing. Absence of results here is not evidence of absence of knowledge. |
| Nodes never improve | Step 4 is being skipped. |

## Bundled helpers

- `scripts/akms_bootstrap.sh` — create the layout and compile a first graph
- `scripts/new_node.py` — scaffold a schema-valid v2 node
- `scripts/check_setup.py` — verify install, vault, layout, graph, and MCP entry point
- `references/node_authoring.md` — full v2 field reference
- `references/mcp_setup.md` — MCP registration and tool list
- `references/workflows.md` — worked end-to-end examples
