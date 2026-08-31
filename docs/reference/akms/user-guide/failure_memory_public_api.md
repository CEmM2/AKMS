# Public AKMS API pin for failure memory

The optional `akms-failure-memory` package may depend only on documented public
AKMS contracts. The machine-readable pin lives at:

```text
Packages/AKMS/release/failure_memory_public_api_pin.json
```

## Permitted surface

| Capability | Public boundary |
|---|---|
| Full task resolution | `akms.task_context.resolve_task_service.resolve_task` |
| CLI adapter | `akms resolve-task` |
| Reviewer context | `akms.task_context.review.resolve_reviewer_context` |
| Loadout rendering | `akms.graph.generate_loadout.generate_loadout` with optional task-knowledge/manifest inputs |
| Mirror refresh | `akms.graph.generate_mirror.generate_mirror` |
| Provider protocol | Documented symbols in `akms.graph.mirror_provider` |
| Task-context models/routes/query/manifest | Exact symbols enumerated by the pin |
| Schema | Frozen AKMS v2 public models and version constant |

The pin hashes the listed public source files. A change to a pinned source is an
intentional compatibility event, not an opportunity to update a digest until a
test stops complaining.

## Forbidden dependencies

- Importing `repo2md` as a Python package
- Importing private orchestrator handlers or context builders
- Depending on private MCP closures
- Treating private provider validators as stable API
- Rewriting frozen v2 node frontmatter
- Shell interpolation for external tools

## Stability test

```bash
uv run pytest Packages/AKMS/tests/akms/test_failure_memory_public_api_pin.py -q
```
