# Resolve exact task context

`akms resolve-task` is the preferred front door when task paths, changed files,
symbols, or route rules identify mandatory knowledge.

The CLI and optional MCP tool share one offline service:
`akms.task_context.resolve_task_service.resolve_task`.

## Inputs

### Task JSON

A task requires `task_id` (or `id`). Retrieval-relevant optional fields are:

```json
{
  "task_id": "fix-constitutive-update",
  "phase": 2,
  "title": "Repair the constitutive update",
  "objective": "Preserve the consistent tangent contract",
  "scope": ["src/constitutive/"],
  "deliverables": ["src/constitutive/update.py"],
  "changed_files": [],
  "symbols": ["Material.update"],
  "akms_tags": ["plasticity", "consistent-tangent"],
  "implementation_steps": ["update stress", "assemble tangent"]
}
```

### Route index

```yaml
schema_version: v1
source_hash: "sha256:replace-with-source-digest"
by_path:
  src/constitutive/update.py:
    - node_id: consistent-tangent-contract
      reason: Required invariant for this update path
      provenance: knowledge/task-routes.yaml
by_symbol:
  Material.update:
    - node_id: return-mapping-contract
      reason: Symbol-specific constitutive algorithm
      provenance: knowledge/task-routes.yaml
```

### Changed paths

Choose one:

- `--changed-paths changed.json`, where JSON is a list or an object containing
  `changed_paths`, `changed_files`, or `paths`
- `--base <rev> [--head <rev>]`, which runs `git diff --name-only base...head`

A bare single path string is rejected. Do not provide both mechanisms.

## CLI

```bash
akms resolve-task \
  --repo . \
  --task-json dev/tasks/fix-constitutive-update.json \
  --routes knowledge/task-routes.yaml \
  --base main \
  --head HEAD \
  --role code_reviewer \
  --mode routing \
  --max-depth 2
```

The command prints pure JSON on stdout and exits nonzero for a structured error.

Default artifacts:

```text
knowledge/loadouts/<phase>-<task>-<role>-loadout.md
knowledge/resolution-manifests/<phase>-<task>-<role>-manifest.json
```

## Result contract

Successful JSON includes paths, fingerprint, graph version, route-index hash,
counts for required/coactivated/advisory selections, role, phase, task ID, mode,
and canonical changed paths.

Failures include `status: error`, `error`, and a stable `error_code` when the
failure is classified.

## Python API

```python
from akms.task_context.resolve_task_service import resolve_task

result = resolve_task(
    repo_root=".",
    task="dev/tasks/fix-constitutive-update.json",
    route_index="knowledge/task-routes.yaml",
    agent_role="code_reviewer",
    base="main",
    head="HEAD",
    mode="routing",
)

if result.status != "ok":
    raise RuntimeError(f"{result.error_code}: {result.error}")
print(result.fingerprint)
```

## Fail-closed behavior

An unavailable required node is not demoted to advisory context. The resolver
returns `required_node_unavailable`, preserving the distinction between “not
found” and “probably enough context.”
