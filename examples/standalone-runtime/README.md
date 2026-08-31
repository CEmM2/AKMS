# Standalone runtime example

Runs the embedded AKMS orchestration runtime **end to end, offline and
deterministically** — no network, no credentials, no LLM.

```bash
pip install "akms[orchestration]"   # or use the workspace checkout
python run_demo.py                  # workspace defaults to ./demo-workspace
```

Expected output (paths aside):

```text
workspace: .../demo-workspace
  [gate] stage=PLAN -> APPROVE (0 warnings)
  [gate] stage=TASK_BREAKDOWN -> APPROVE (0 warnings)
  [gate] stage=SCAFFOLD -> APPROVE (0 warnings)
  [gate] stage=EXECUTE -> APPROVE (0 warnings)
  [gate] stage=REVIEW -> APPROVE (2 warnings)
  [gate] stage=FINALIZE -> APPROVE (0 warnings)
pipeline COMPLETED (stage=COMPLETE, aborted=False)
agent memories written: ['handoff_phase_1.md', ...]
```

(A couple of benign notices appear when the workspace is not a git repository
and has no seed nodes — the pipeline proceeds regardless.)

## What it demonstrates

- **The backend seam** (`demo_backend.py`): a custom backend subclasses
  `akms.agents.base.AKMSAgent` and implements exactly two things —
  `preflight()` (cheap availability probe, run before any file is written)
  and `execute()` (do one task, write a schema-valid `AgentMemory` to
  `knowledge/sessions/{task_id}.md`). The sealed `run()` wrapper owns the
  protocol lifecycle, including converting failures into
  `status: failed` memories.
- **The checkpoint seam** (`run_demo.py`): a `CheckpointHandler` subclass
  decides how gates are presented. The demo auto-approves; real runs should
  keep the default `FileCheckpointHandler`, which announces a response-file
  path and — as of 0.3.0 — aborts instead of polling when unattended
  (60 s headless, 1 h at a TTY).
- **Determinism policy**: this mirrors `tests/public_smoke/runtime/`, which
  CI runs against installed wheels. Live-provider trials are deliberately
  separate; nothing here reaches a backend service.

## Switching to a real backend

In a real repository, drop the demo classes and run:

```bash
akms orchestrate --goal "..." --backend claude    # or codex, claude-cli, codex-cli
```

`preflight()` will fail fast with an actionable message if the chosen
backend's SDK or binary is missing (`pip install "akms[agents]"` covers the
SDK backends).
