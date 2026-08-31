# akms-failure-memory

Optional, independently installable deterministic failure-memory workflows for
AKMS projects.

A project repository owns its canonical lesson registry and configuration. This
package owns validation, recording, deterministic projection, refresh
orchestration, a neutral resolve provider, fingerprint validation, and CI checks.
AKMS core does not depend on this package.

## Requirements

- Python `>=3.12,<3.13`
- `akms>=0.1.0,<0.2.0` as declared by distribution metadata
- A read-only global-vault path for compile/refresh operations that need it
- The pinned repo2md CLI checkout for mirror preflight/refresh workflows

## First commands

```bash
failure-memory --help
failure-memory --version

failure-memory init \
  --repo . \
  --config .failure-memory/config.toml \
  --repository-id example \
  --node-namespace example-failure

failure-memory doctor --repo . --config .failure-memory/config.toml
```

Then follow `docs/adoption.md` or the unified site under
`docs/failure-memory/`.

## Ownership rules

- Registry IDs and records are canonical project history.
- Generated nodes, routes, graph, mirrors, loadouts, manifests, and provider
  results are projections; do not hand-edit them.
- Global-vault promotion is never automatic.
- Compiler, recorder, refresh, and provider operations share the project lock.
- Deterministic compiler/query paths do not call an LLM or network service.
