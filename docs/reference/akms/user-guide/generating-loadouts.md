# Generate loadouts

A loadout is a Markdown knowledge artifact for one task, phase, and role.

## Modes

- **Routing:** summaries, paths, and compact metadata
- **Full:** inline content up to the ordinary advisory token budget

Per-node `reading_priority` can override the loadout-level mode with `full`,
`summary`, or `pitfalls-only`. A `summary` node renders its `## Summary`
section; a node without one is rendered in full instead, as the specification
requires (FR-L10c).

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
.knowledge/loadouts/2-task-17-loadout.md
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
    output_path=".knowledge/loadouts/2-task-17-loadout.md",
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

Coactivated nodes, the one-hop `load_with` companions, are rendered at
`loadout.coactivated_reading_priority`, which defaults to `summary` and
overrides the node's own `reading_priority`: the entry shows its `## Summary`
section and path, and the full node is read on demand. A coactivated node
without a `## Summary` section is still rendered in full. Set the priority to
`full` for the earlier behaviour.

The exact resolver follows `load_with` from required nodes only. Set
`loadout.coactivate_from_advisory: true` to follow it from advisory nodes
too.

```yaml
loadout:
  coactivated_reading_priority: summary   # full | summary | pitfalls-only
  coactivate_from_advisory: false
```

## Code mirrors in routing mode

A code mirror's `content_ref` is relative to the knowledge directory. A mirror
exported with a [`## Summary` section](../repo-wiki/akms-export.md#mirror-summary)
is read from there, and that section is what routing mode loads for it, whether
the mirror is required or coactivated. Only a section ahead of `## Symbol Index`
counts, because the source text further down may hold such a line too.

A mirror exported without the section, the default, renders as it always has:
its entry is the path, with `(no content available)` as the summary. Full mode
does not read mirrors this way and is not affected.

## Retrieval and timestamps

The generator may use the `qmd` wrapper for scoped content retrieval and records
whether the binary was available. It also writes `generated_at`. Selection and
ordering are deterministic, but raw loadout bytes can differ with timestamp or
environment-capability metadata.
