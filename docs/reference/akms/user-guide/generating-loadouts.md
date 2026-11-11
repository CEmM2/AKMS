# Generate loadouts

A loadout is a Markdown knowledge artifact for one task, phase, and role.

## Modes

- **Routing:** summaries, paths, and compact metadata
- **Full:** inline content up to the ordinary advisory token budget, with
  required and coactivated content bounded separately (see
  [Full-mode budget](#full-mode-budget))

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
without a `## Summary` section is still rendered in full, except a code mirror,
whose summary is [built from its symbol index](#code-mirrors-in-routing-mode).
Set the priority to `full` for the earlier behaviour.

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

In either mode a mirror's `**Path:**` line names it from the repository root, for
example `.knowledge/code-mirror/src/foo.md`, so a reader can open it from there.

A mirror exported without the section, the default, gets the same summary built
when the loadout is generated, from the mirror's own `## Symbol Index`: the
public top-level classes and functions with their signatures, after the first
paragraph of the module docstring, which a Python mirror takes from the source
it holds. The text is what the exporter would have written, so no mirror has to
be exported again. A mirror from another generator, with no symbol index that
parses, keeps its old entry: the path, with `(no content available)` as the
summary.

```yaml
loadout:
  derive_mirror_summary: true   # false: mirrors without the section show only a path
```

Full mode reads the whole mirror from the knowledge directory; see
[Full-mode budget](#full-mode-budget).

## Full-mode budget

Required and coactivated selections are not truncated, and a code mirror is a
whole source file. With every required mirror's body inlined, a large downstream
project reaches about 315,000 tokens at the 90th percentile and 1.3 million at
most. `loadout.full_mode_max_tokens` bounds that:

```yaml
loadout:
  full_mode_max_tokens: 40000   # null turns the guard off
```

In a required-aware loadout in full mode:

1. Inline content other than code mirrors is charged first and always stays
   inline, even when it passes the budget alone. A required lesson can carry a
   constraint; a mirror can be read again from its path.
2. Code mirrors follow in loadout order: selection class, then node id. Each is
   inlined while it fits. The first that does not fit, and every mirror after
   it, is served the way routing mode serves it: summary and path, read mode
   `routing`.
3. No node is dropped. A downgraded mirror stays in its section with its reasons
   and a `**Downgraded:**` line giving its size in full. A notice under the
   title and a `full_mode_guard` header entry (`downgraded_nodes`, `max_tokens`,
   `unguarded_inline_tokens`) name what happened, and a warning is logged.

A loadout within the budget is byte-identical to one with the guard off. Routing
mode and loadouts without `task_knowledge` are not affected; the latter already
honour `max_loadout_tokens`.

The budget covers inline required and coactivated content only. Summaries,
reasons and advisory content (capped by `max_loadout_tokens`) come on top, so a
guarded loadout can be larger than the budget, and a loadout selecting hundreds
of files is still as long as its routing-mode entries.

The default of 40,000 sits above the largest required-lesson cost measured on
that project (about 32,000 tokens), so lessons alone leave room for a mirror.
It left 48 of 103 replayed tasks untouched and lowered the 90th percentile of the
whole loadout from about 315,000 tokens to about 52,000.

Full mode reads a code mirror from the knowledge directory when its
`content_ref` does not resolve from the working directory or the repository root,
which is the case for an exported mirror. A mirror the guard downgrades is
summarized as in routing mode: by its own `## Summary` section, or by the one
built from its symbol index. A coactivated mirror is summarized the same way, so
it does not count toward the budget. With `loadout.derive_mirror_summary: false`,
a mirror without the section reads `(no content available)` when downgraded, and
a coactivated one falls back to full, as any summary-priority node does. Routing
mode does not inline mirror bodies.

## Retrieval and timestamps

The generator may use the `qmd` wrapper for scoped content retrieval and records
whether the binary was available. It also writes `generated_at`. Selection and
ordering are deterministic, but raw loadout bytes can differ with timestamp or
environment-capability metadata.
