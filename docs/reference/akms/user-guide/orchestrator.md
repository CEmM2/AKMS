# Optional pipeline runner

`akms orchestrate` runs the repository's staged coding pipeline. Use it when its
stage model, checkpoint handlers, and runtime adapters match the project. It is
not required for AKMS core.

## CLI example

```bash
akms orchestrate \
  --repo . \
  --plan consistent-tangent \
  --goal "Implement and review the consistent tangent" \
  --backend codex-cli \
  --model <model-name> \
  --terminal
```

Use `--resume` to continue saved state. File-based checkpoints are the default;
`--terminal` selects interactive terminal approval.

## Backend selection

| Value | Behavior |
|---|---|
| `claude-sdk` | Built-in Claude Agent SDK adapter |
| `claude-cli` | Drives the `claude` executable headlessly |
| `codex-sdk` | Built-in OpenAI Agents SDK adapter |
| `codex-cli` | Drives `codex exec` |
| `local` | Uses a local OpenAI-compatible endpoint |

For project-specific behavior, pass a dotted `AKMSAgent` subclass with
`--agent`; it overrides `--backend`.

## Python entry point

```python
import asyncio
from pathlib import Path

from akms.orchestrator.orchestrator import run_pipeline

asyncio.run(
    run_pipeline(
        repo_root=Path("."),
        spec_path="spec.md",
        goal="Implement the constitutive update",
        plan_name="constitutive-update",
        resume=False,
        config=None,
        model=None,
    )
)
```

Consult API autodoc for the exact signature at the installed revision.

## Checkpoints

- `TerminalCheckpointHandler`: interactive local approval
- `FileCheckpointHandler`: file-based external/headless approval

## MCP tools

The optional MCP surface exposes graph, status, loadout, update, mirror, search,
pitfall, and exact task-resolution operations bound to a repository. CLI and MCP
must remain thin adapters over the same deterministic service functions.

## Boundary warning

Do not write package or ecosystem documentation as though every AKMS user must
subclass an agent or accept this stage sequence. The core's value is the
knowledge contract; orchestration remains replaceable.
