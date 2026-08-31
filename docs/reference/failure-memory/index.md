# Failure Memory

`akms-failure-memory` is an optional sidecar for projects that need a canonical,
append-only record of failed approaches and lessons, plus deterministic AKMS
projections and task-context evidence.

It is deliberately separate from the ordinary graph overlay:

- The **project registry** is canonical history.
- Generated lesson nodes and route indexes are reproducible projections.
- AKMS core retains graph, exact-resolution, and loadout semantics.
- repo2md retains source-projection responsibility.
- No workflow automatically promotes a lesson to the global vault.

## Capabilities

- Initialize and diagnose a project configuration
- Record lessons interactively or from canonical JSON
- Validate, compile, or check generated lesson projections
- Refresh lessons, mirrors, graph, or the complete snapshot
- Resolve pre-task or post-diff provider context
- Validate provider fingerprints against a request
- Run a hermetic CI consistency gate
- Generate a compatibility wrapper without making it canonical

## Start

```bash
failure-memory init --repo . --config .failure-memory/config.toml \
  --repository-id example --node-namespace example-failure
failure-memory doctor --repo . --config .failure-memory/config.toml
```

Continue with [Getting Started](../../getting-started/failure-memory.md).
