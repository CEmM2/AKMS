# Contributing

Thanks for considering a contribution. AKMS is research software with a small
maintainer team; focused, well-tested changes land fastest.

## Development setup

Python 3.12 and [uv](https://docs.astral.sh/uv/) are required.

```bash
git clone <repository>
cd AKMS
uv sync --locked --all-packages
uv run python -m pytest packages/akms/tests -q
```

The workspace has four packages under `packages/`; each has its own tests.

## Test categories

Markers are defined at the workspace root:

| Marker | Meaning |
|---|---|
| `unit` | fast, isolated |
| `contract` | public schema/API/CLI/runtime/plugin contracts |
| `integration` | cross-component, external services mocked |
| `runtime` | embedded first-party runtime |
| `external_consumer` | core contracts without the runtime |
| `regression` | previously observed defects |
| `e2e` | installed-package user workflows |
| `slow`, `live_provider` | excluded from default CI |

The default suite needs **no network and no credentials**. Anything needing
either gets `live_provider`.

## Public contracts

Changes to these surfaces need contract tests and a changelog entry:

- the v2 node schema (frozen: adding/removing required fields is a breaking
  change requiring a major schema bump and migration),
- the projection surface (`akms.task_context`, `query_subgraph`,
  `generate_loadout`),
- the evidence surface (`update_graph`, `AgentMemory`/`PCD` models),
- CLI commands and their JSON output,
- the read-only global-vault invariant.

See `docs/adr/` for the reasoning behind these boundaries.

## Review standards

- Every PR runs the public-tree audit (`scripts/check_public_tree.py`); private
  plan identifiers, local absolute paths, and secrets fail CI.
- Knowledge-node contributions must state source and provenance and be
  redistributable under CC BY 4.0.
- Tests accompany behavior changes; comments explain current behavior, not
  development history.
- Versions move in lockstep across all four packages; maintainers handle
  release tagging.
