# Update local knowledge explicitly

`update_graph()` applies the persistent zone from an `AgentMemory`, phase
completion document (`PCD`), or compatible mapping.

It is an explicit operation. Merely running a query or finishing an agent chat
does not mutate the graph.

## Write boundary

The update pipeline writes only:

- `knowledge/graph/local_state.yaml`
- `knowledge/local-nodes/*.md`
- `knowledge/graph/graph.json` when recompilation is enabled

It never writes global node files.

## Python API

```python
from akms.graph.update_graph import update_graph

summary = update_graph(
    source=agent_memory_or_pcd,
    repo_root=".",
    config=None,
    global_vault=None,
    recompile=True,
)
```

The summary contains confidence, propagation, pitfall, and knowledge events plus
the generated session-node ID.

## Mutation stages

1. Replay guard checks whether the source was already processed.
2. Useful-node feedback adjusts local confidence and activation state.
3. Missing-detail/outdated feedback can decay confidence.
4. Bounded predecessor propagation uses edge weights and configured
   multipliers.
5. Pitfalls become project-local edges.
6. New knowledge is matched deterministically against tentative candidates; it
   is appended or created as a tentative agent node.
7. A session record is registered.
8. The overlay is written and the graph is optionally rebuilt.

## Review and promotion

Agent-created local nodes enter as tentative. A human can review the file and
then use:

```bash
akms promote <node-id> --repo .
```

Suppress or deprecate misleading local nodes with the corresponding lifecycle
commands. These commands edit local-node frontmatter; they do not promote
content into the global vault.

## Failure memory is separate

Use `akms-failure-memory` when the project needs an append-only canonical lesson
registry, deterministic generated routes/nodes, pinned refreshes, or provider
fingerprints. Do not use the graph overlay as an accidental substitute for that
ownership model.
