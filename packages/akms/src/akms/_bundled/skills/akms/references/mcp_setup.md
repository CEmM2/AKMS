# Serving AKMS over MCP

Use this when you want the agent to call AKMS as tools rather than shell out to
the `akms` CLI. Same surfaces either way.

## Launch

```bash
akms-mcp-stdio --repo-root /path/to/project [--global-vault /path/to/vault]
```

Module form if the console script is not on `PATH`:

```bash
python -m akms.orchestrator.mcp_stdio --repo-root /path/to/project
```

The server is bound to one repository for its lifetime.

## Register

`.mcp.json` in the project:

```json
{
  "mcpServers": {
    "akms": {
      "command": "akms-mcp-stdio",
      "args": ["--repo-root", "."]
    }
  }
}
```

Or:

```bash
claude mcp add akms -- akms-mcp-stdio --repo-root .
```

If AKMS lives in a project virtualenv, go through the runner instead:

```json
{
  "mcpServers": {
    "akms": {
      "command": "uv",
      "args": ["run", "akms-mcp-stdio", "--repo-root", "."]
    }
  }
}
```

Tools surface as `mcp__akms__akms_*`.

## Tools

**Graph lifecycle**

- `akms_build_graph()` — compile vault + local state into `graph.json`
- `akms_graph_status()` — health report
- `akms_update_graph(source_json)` — apply AgentMemory / PCD, recompile
- `akms_re_evaluate(task_id, phase, seed_tags, agent_role)` — regenerate a loadout

**Retrieval**

- `akms_query_subgraph(seed_tags, agent_role, max_depth)` — ranked subgraph
- `akms_generate_loadout(task_id, phase, seed_tags, agent_role)` — write a loadout
- `akms_resolve_task(task_json_path, routes_path, agent_role)` — exact, fail-closed
- `akms_derive_tags(task_json)` — derive tags for a task
- `akms_get_pitfalls(node_ids)` — pitfall edges from those nodes

**Search** (needs `qmd`)

- `akms_search_nodes(query, limit)`
- `akms_search_mirror(query, limit)`
- `akms_search_sessions(query, limit)`

**Code mirror**

- `akms_generate_mirror(phase, parent_branch)`

## The search caveat

The three `akms_search_*` tools shell out through `run_qmd.sh`, which ships
inside the package at `akms/_bundled/qmd/`. Two distinct degradations:

- **`qmd` binary absent** — the wrapper falls back to grep-style matching.
  Poorer results, not an error.
- **wrapper absent** (a broken install) — the call logs a warning and returns an
  **empty list**; it does not raise.

So an empty search result is never by itself evidence that no matching knowledge
exists. Run `check_setup.py` to tell the cases apart. The graph, loadout, and
resolution tools have no such dependency.

## Runtime provenance

AKMS does not declare `mcp` as a direct dependency. It comes in transitively via
`claude-agent-sdk` (`mcp>=1.23.0,<2.0.0`) and `openai-agents`, both base
dependencies. Present in any normal install; pin it explicitly if you trim deps.
