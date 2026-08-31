# Task context, route indexes, and manifests

Task-context resolution combines advisory tags with exact path/symbol evidence.
It exists because “probably relevant” and “required for this task” are not the
same contract, despite software documentation's historic enthusiasm for
pretending otherwise.

## Route-index schema

```yaml
schema_version: v1
source_hash: "sha256:9d87..."
by_path:
  src/solver.py:
    - node_id: solver-update-contract
      reason: Exact implementation constraints for the solver update path
      provenance: knowledge/task-routes.yaml
by_symbol:
  Solver.step:
    - node_id: consistent-tangent-contract
      reason: Symbol-specific tangent requirements
      provenance:
        source: knowledge/symbol-routes.yaml
        generator: manual
```

Each record requires a non-empty `node_id`, `reason`, and `provenance`.
`by_symbol` is optional.

## Canonical path rules

Keys normalize to repository-relative POSIX paths. The parser rejects absolute
paths, drive prefixes, parent traversal, NUL bytes, and empty paths. Duplicate or
conflicting records within one route fail validation.

Plain task paths match exactly. A trailing slash declares a directory input;
glob metacharacters declare a glob. Changed-file inputs are always exact paths.
Documentation-only path tasks intentionally do not pull code mirrors unless
symbols or non-documentation paths provide code evidence.

## Selection classes

1. **Required:** exact mirror and route-bound nodes; unavailable required nodes
   fail the operation.
2. **Coactivated:** nodes pulled by `load_with` from exact selections.
3. **Advisory:** role-aware tag/query matches.

Required and coactivated content is rendered before advisory content and is not
hidden by the ordinary advisory token cap.

## Manifest boundary

The resolution manifest binds:

- Canonical task inputs and changed paths
- Agent role
- Graph version
- Canonical route-index hash
- Exact/advisory seed reasons
- Required, coactivated, and advisory selections
- Resolver version and fingerprint

Use the fingerprint when a reviewer or provider result must prove it consumed
the same task baseline and knowledge snapshot.

## Validation APIs

- `parse_route_index()` validates and canonicalizes mapping, JSON, or YAML input.
- `validate_route_index_nodes()` verifies every routed node exists in the graph.
- `resolve_task()` is the shared service behind CLI and MCP.
- `resolve_reviewer_context()` derives reviewer context from actual changed paths.
