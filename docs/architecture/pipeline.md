# Optional staged pipeline runner

The core package includes a staged runner for projects that want AKMS to
coordinate task planning, execution, review, checkpoints, and graph updates.
This is an optional integration layer.

## Stage model

```text
INIT → PLAN → TASK_BREAKDOWN → SCAFFOLD → EXECUTE → REVIEW → FINALIZE → COMPLETE
```

The runner can:

- Build or load the graph
- Prepare role-specific context
- Dispatch an `AKMSAgent` implementation
- Persist checkpoints and resume state
- Collect task/phase records
- Invoke explicit local graph updates
- Run code and physics reviewer roles

## Runtime backends

The CLI currently maps friendly backend names to built-in adapters:

| Backend | Adapter model |
|---|---|
| `claude-sdk` | Claude Agent SDK |
| `claude-cli` | Headless `claude` command |
| `codex-sdk` | OpenAI Agents SDK |
| `codex-cli` | `codex exec` command |
| `local` | OpenAI-compatible local endpoint |

An explicit dotted `--agent module.ClassName` overrides the backend mapping.

## Architectural rule

Do not make graph, route, loadout, failure-memory, or learning documentation
assume this runner is present. Those services must remain independently usable
from CLI, Python, MCP, or another harness.
