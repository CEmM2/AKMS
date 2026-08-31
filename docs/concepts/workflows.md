# Choose a workflow

AKMS does not impose one universal lifecycle. Choose the smallest surface that
solves the project problem.

## 1. Graph-only retrieval

Use when tags and graph relations are sufficient:

```bash
akms query plasticity return-mapping --repo . --role physics_reviewer
akms loadout constitutive-review --repo . --phase 2 \
  --tags plasticity return-mapping --role physics_reviewer --mode full
```

No agent runtime is required.

## 2. Exact task-context retrieval

Use when paths, symbols, or generated code mirrors make some knowledge
mandatory:

```bash
akms resolve-task \
  --repo . \
  --task-json dev/tasks/fix-constitutive-update.json \
  --routes knowledge/task-routes.yaml \
  --base main \
  --head HEAD \
  --role code_reviewer
```

This writes both a loadout and a fingerprinted manifest.

## 3. Source-mirror refresh

Use before exact path-aware resolution when the code projection is stale:

```bash
akms mirror-status --repo . --json
akms generate-mirror --repo . --phase 2 --parent-branch main --json
```

Select `legacy` for Python-only in-process projection or configure `repo2md` for
the pinned external provider contract.

## 4. Explicit learning from task outcomes

Call `update_graph()` with a validated `AgentMemory`, `PCD`, or persistent-zone
mapping. Updates affect local nodes and the local overlay only. Nothing “learns
automatically” merely because a chat ended; a caller must supply and apply the
record.

## 5. Project-owned failure memory

Use `failure-memory` when the project needs append-only canonical lessons,
deterministic generated nodes/routes, pinned refresh, provider fingerprints, and
a CI gate. Core remains independent of the package.

## 6. Learning material

Pass a graph slice or graph path to `akms-learn` to compile a Learning Source
Packet. The graph is read-only from the learning package's perspective.

## 7. Optional staged runner

Use `akms orchestrate` only when the project wants the bundled stage/checkpoint
model. It can combine several flows above, but it is not the sole or preferred
front door for every consumer.
