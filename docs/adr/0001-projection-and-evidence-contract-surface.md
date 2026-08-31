# ADR 0001 — Projection and evidence contract surface

**Status**: accepted (2026-08-18)

## Context

AKMS must expose stable contracts that external consumers can use without
adopting the embedded first-party runtime: a **projection contract** (request a
task-scoped slice of the knowledge graph) and an **evidence contract** (return
structured outcomes for ingestion). An earlier release plan sketched dedicated
`akms.projections` and `akms.evidence` packages for this purpose.

The implementation already carries both capabilities under different names, and
they are already runtime-independent: the evidence models (`AgentMemory`,
`PCD`) live in `akms.schema.models`, and nothing in the modules below imports
`akms.orchestrator` or `akms.agents`. Introducing new packages before the first
public release would move a large amount of settled code, churn every import,
docs page, and test path, and add review risk without changing any behavior.

## Decision

The public projection and evidence contracts are documented **under their
current module names** rather than extracted into new packages:

| Contract | Public surface |
|---|---|
| Projection | `akms.task_context` (task-knowledge queries, seed resolution, route indexes, resolution manifests) and `akms.graph.query_subgraph` / `akms.graph.generate_loadout` |
| Evidence | `akms.graph.update_graph.update_graph`, accepting `AgentMemory`, `PCD`, or a plain persistent-zone `dict`; models in `akms.schema.models` |

Everything not listed here is internal. The embedded runtime
(`akms.orchestrator`, `akms.agents`) is one consumer of these contracts and is
never a dependency of them.

## Consequences

- External consumers depend only on the surface above; the dependency
  direction *core contracts ← runtime* is enforced, never reversed.
- `tests/integration/external_consumer/` proves the full
  compile → project → ingest-evidence workflow runs with neither
  `akms.orchestrator` nor `akms.agents` ever entering `sys.modules`, and runs
  it in a subprocess against the installed minimal package.
- Renaming this surface to `projections`/`evidence` later is a breaking change
  that requires a deprecation cycle; adopting it now was rejected as churn
  without behavior change.
- The plain-`dict` evidence path is part of the contract: producers other than
  `AgentMemory` and `PCD` are supported, while both remain first-class.
