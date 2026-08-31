# Quickstart: compile, query, and load out one valid node

This example uses only project-local knowledge. It does not need a global vault,
an LLM, an MCP server, or the optional pipeline runner.

## 1. Create the repository layout

From the project you want AKMS to serve:

```bash
mkdir -p knowledge/local-nodes knowledge/graph
```

## 2. Add a valid v2 local node

Create `knowledge/local-nodes/fem-assembly.md`:

```markdown
---
id: fem-assembly
title: Finite-element global assembly
domain: computational-mechanics
subdomain: finite-elements
tags:
  - fem
  - assembly
  - sparse-matrices
status: established
confidence: 0.9
source: human
edges: []
load_with: []
context_size: medium
reading_priority: summary
content_ref: knowledge/local-nodes/fem-assembly.md
akms_schema: v2
---

# Finite-element global assembly

Map each element's local degrees of freedom to global indices, then scatter-add
its residual and tangent contributions into the global sparse system.

## Pitfalls

Apply essential boundary conditions consistently to both residual and tangent.
Do not silently mix local and global degree-of-freedom numbering.
```

The required v2 identity fields are `id`, `title`, `domain`, and at least one
tag. A human-authored local node may be established; an agent-authored local
node must enter as tentative.

## 3. Query the graph

```bash
akms query fem assembly --repo . --role implementer --max-depth 2
```

When the default graph file is absent, the command compiles:

```text
knowledge/graph/graph.json
```

The command prints machine-readable JSON with a ranked node list. The query
returns ranked `(node_id, node_data)` records internally, not a NetworkX
subgraph object.

## 4. Generate a loadout

```bash
akms loadout assembly-demo \
  --repo . \
  --phase 1 \
  --tags fem assembly \
  --role implementer \
  --mode routing
```

The default output is:

```text
knowledge/loadouts/1-assembly-demo-loadout.md
```

Use `--mode full` to inline available node content subject to the ordinary
advisory token budget.

## 5. Inspect graph health

```bash
akms status --repo .
```

## Equivalent Python API

```python
from pathlib import Path

from akms.graph.build_graph import build_graph
from akms.graph.query_subgraph import query_subgraph

root = Path(".")
graph = build_graph(root)
ranked = query_subgraph(
    graph,
    domain_tags=["fem", "assembly"],
    agent_role="implementer",
    max_depth=2,
)

for node_id, data in ranked:
    print(node_id, data.get("confidence"), data.get("content_ref"))
```

For path- or symbol-mandatory context, continue with
[exact task resolution](../../reference/akms/user-guide/task-resolution.md) rather than treating a
tag match as a requirement.
