# Data model

## Global and local knowledge nodes

The common v2 frontmatter fields are:

```yaml
id: return-mapping
title: J2 return mapping
domain: computational-mechanics
subdomain: plasticity
tags: [plasticity, constitutive-update]
status: established
confidence: 0.9
source: human
confidence_floor: 0.5
edges:
  - to: consistent-tangent
    type: feeds-into
    weight: 0.8
    note: The algorithm supplies the state used by the tangent.
load_with: [yield-surface-conventions]
context_size: medium
reading_priority: summary
content_ref: knowledge/local-nodes/return-mapping.md
akms_schema: v2
```

Required fields include `id`, `title`, `domain`, at least one tag, `status`,
`confidence`, and `source`. Unknown frontmatter fields are rejected.

### Local-node constraints

- `source: generated` is reserved for code-mirror/session artifacts and is not
  valid for a local knowledge node.
- `source: agent` must enter with `status: tentative`.
- Human-authored local nodes may use the ordinary lifecycle statuses.

### Loadable statuses

Ranked graph queries load tentative and established nodes. Draft and deprecated
nodes remain in the source history but are not ordinary query candidates.

## Code-mirror nodes

Code mirrors are intentionally smaller existence/provenance markers:

```yaml
id: code-src-solver-py
title: src/solver.py
domain: code-mirror
status: established
confidence: 1.0
source: generated
auto_update: true
content_ref: knowledge/code-mirror/code-src-solver-py.md
source_file: src/solver.py
generated_at: 2026-08-16T00:00:00Z
generated_by_phase: 1
akms_schema: v2
```

They do not carry ordinary tags or structural edges. Fields such as `name` are
not part of this schema. Exact path matching uses `source_file`, not advisory
tag derivation.

## Local experiential overlay

Default path:

```text
knowledge/graph/local_state.yaml
```

The overlay can contain:

- Per-node confidence and activation state
- Project-local edges, commonly pitfalls
- Session-node registrations
- A replay ledger of processed update sources
- Reserved `suppressed_edges`, which must remain empty in v2

`repo_id` in the core overlay is informational. The failure-memory project
configuration has its own canonical repository identity during its publication
workflow.

## Compiled graph

The graph JSON uses NetworkX node-link form:

- `graph`: schema, timestamp, counts, vault path, repository identity
- `nodes`: deterministically ordered node records
- `links`: deterministically ordered directed edges

The graph is generated. Edit source nodes, route indexes, mirror inputs, or the
explicit overlay through their owning workflows rather than hand-editing
`graph.json`.
