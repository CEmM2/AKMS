# AKMS Knowledge System

## Knowledge Loadout

Before starting any task, check for your knowledge loadout:

```
knowledge/loadouts/<task-id>-loadout.md
```

If the loadout exists, read it first — it contains domain knowledge, pitfalls, and
suggested reading order tailored to your task. If no loadout exists, flag this to
the orchestrator: "No loadout found for task <id>."

## Code Search

For code-level search, use the qmd scripts instead of grep:

```bash
knowledge/qmd/run_qmd.sh search_mirror "query"
knowledge/qmd/run_qmd.sh search_nodes "query"
```

These search the AKMS knowledge graph and code mirror index, which are more
semantically aware than plain text search.

## Global Vault

Domain knowledge nodes live in the global vault at:

```
~/.claude/akms/nodes/
```

Do NOT modify global nodes. All experiential state (confidence, activations,
pitfalls) lives in `knowledge/graph/local_state.yaml` per repo.

## After Task Completion

Write an AgentMemory file at `knowledge/sessions/<task_id>.md` with:

- Which knowledge nodes you used and whether they were helpful
- Any missing knowledge (concepts you needed but didn't have)
- Pitfalls discovered (hard-won lessons for future agents)
- New knowledge worth capturing

This feedback improves the graph for future tasks.

## Subagent Delegation

When spawning subagents:

1. Each subagent receives its own task JSON with `loadout_path`
2. Subagents must read their loadout before starting work
3. Subagents write their own AgentMemory on completion
4. The phase agent aggregates AgentMemories into a Phase Completion Document (PCD)
