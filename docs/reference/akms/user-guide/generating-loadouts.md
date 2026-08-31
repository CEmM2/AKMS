# Generate loadouts

A loadout is a Markdown knowledge artifact for one task, phase, and role.

## Modes

- **Routing:** summaries, paths, and compact metadata
- **Full:** inline content up to the ordinary advisory token budget

Per-node `reading_priority` can override the loadout-level mode with `full`,
`summary`, or `pitfalls-only`.

## CLI

```bash
akms loadout task-17 \
  --repo . \
  --phase 2 \
  --tags plasticity return-mapping \
  --role implementer \
  --mode routing \
  --max-depth 2 \
  --available-context 32000
```

Default output:

```text
knowledge/loadouts/2-task-17-loadout.md
```

Use `--output` for an exact repository-relative path.

## Python API

```python
from akms.graph.generate_loadout import generate_loadout

content = generate_loadout(
    G=graph,
    ranked_nodes=ranked,
    task_id="task-17",
    phase=2,
    graph_version=graph_version,
    seed_tags=["plasticity", "return-mapping"],
    agent_role="implementer",
    mode="routing",
    available_context=32000,
    config=config,
    output_path="knowledge/loadouts/2-task-17-loadout.md",
    repo_root=".",
)
```

## Required-aware loadouts

When `task_knowledge` and a `resolution_manifest` are supplied by the exact
resolver, the generator renders:

1. Required knowledge
2. Coactivated knowledge
3. Advisory domain knowledge
4. Pitfall warnings
5. Session history
6. Suggested reading order

Required and coactivated selections are not truncated by the ordinary advisory
budget. The manifest fingerprint is recorded in the header.

## Retrieval and timestamps

The generator may use the `qmd` wrapper for scoped content retrieval and records
whether the binary was available. It also writes `generated_at`. Selection and
ordering are deterministic, but raw loadout bytes can differ with timestamp or
environment-capability metadata.
