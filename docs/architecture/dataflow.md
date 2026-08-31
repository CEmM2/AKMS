# Graph and task dataflows

## Graph compilation

```text
global nodes
+ local nodes
+ code-mirror nodes
+ knowledge/graph/local_state.yaml
        │
        ▼
   validate v2 inputs
        │
        ▼
 NetworkX DiGraph
        │
        ▼
knowledge/graph/graph.json
```

Compilation is a merge, not a database synchronization process. Source Markdown
and the overlay remain authoritative inputs.

## Ranked advisory query

```text
seed tags + role profile + graph
        │
        ├─ match seed tags
        ├─ bounded ego union
        ├─ filter loadable status
        ├─ traverse allowed edge types
        ├─ apply domain/confidence policy
        ├─ rank and cap
        └─ inject relevant pitfalls
        ▼
ranked (node_id, node_data) list
```

## Exact task resolution

```text
task JSON + changed paths/base-head + route index + graph + role
        │
        ├─ canonicalize task paths/symbols
        ├─ match exact code-mirror source_file values
        ├─ add route-bound required nodes
        ├─ derive advisory tags
        ├─ expand load_with coactivations
        ├─ validate required availability
        ├─ role-aware advisory query
        └─ create canonical fingerprint
        ▼
loadout + resolution manifest + machine-readable result
```

## Explicit local update

```text
AgentMemory / PCD / persistent-zone mapping
        │
        ├─ replay guard
        ├─ confidence and activation updates
        ├─ bounded neighbor propagation
        ├─ local pitfall edges
        ├─ deterministic tentative-node dedup/create
        ├─ session registration
        └─ write local overlay/local nodes
        ▼
optional graph recompile
```

Nothing in this flow writes the global vault.

## Mirror refresh

```text
selected provider + repository paths/config
        │
        ├─ project source selection
        ├─ provider projection
        ├─ path/schema/completeness validation
        ├─ optional explicit fallback policy
        └─ write knowledge/code-mirror/
        ▼
subsequent graph build
```

The provider creates source markers. AKMS remains responsible for graph and
route/loadout semantics.
