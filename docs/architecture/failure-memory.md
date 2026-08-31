# Architecture and ownership

## Dependency direction

```text
project registry/config
        │
        ▼
akms-failure-memory
        ├── documented, pinned AKMS public API
        └── pinned repo2md CLI contract (subprocess argv)
```

AKMS core never imports failure memory. Failure memory never imports a consumer
repository or repo2md as a Python package.

## Ownership table

| Artifact | Owner | Policy |
|---|---|---|
| Lesson registry | Project | Canonical append-only IDs/history |
| Project configuration | Project | Canonical identity, paths, taxonomy, and toolchain policy |
| Generated lesson nodes/routes | Project policy | Reproducible projection; committed or disposable |
| Recorder/compiler/refresh/provider | Package | Reusable implementation |
| Source mirrors | repo2md product | Invoked through pinned CLI contract |
| Graph/query/loadouts | AKMS core | Invoked through public API pin |
| Compatibility wrappers | Project | Thin forwarding only |
| Global promotion | Human operator | Separate explicit action |

## Project contract

`failure-memory-project/v1` binds:

- Repository identity and node namespace
- Canonical and generated paths
- Generated-file policy
- Validation and taxonomy rules
- Compatibility renderer identifiers
- Exact AKMS and repo2md toolchain pins

Paths are repository-relative POSIX paths and are containment-checked through
symlink components before mutation.

## Transaction and lock model

Recording, compilation, refresh, and provider resolution coordinate through the
same project-local reentrant lock. Compiler publication is transactional across
lesson nodes and route indexes. Graph publication validates all inputs before
atomically replacing the previous artifact.

On validation failure, existing graph and local-state bytes survive unchanged.
An absent local-state file remains absent; failure memory does not manufacture
experiential state.

## Repository identity

The validated project configuration's `repository_id` is authoritative for the
failure-memory graph publication. It does not rewrite the core overlay's
informational `repo_id` field.

## Refresh policies

- `never`: resolve the existing snapshot without asserting freshness
- `require-current`: fail-closed toolchain preflight plus compiler/graph drift
  checks under the shared lock; it verifies but does not mutate shared state

Changing project identity makes an old graph stale until an explicit graph
refresh publishes the new identity.
