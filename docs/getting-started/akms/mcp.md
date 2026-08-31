# Serve AKMS to an agent over MCP

AKMS ships a stdio MCP server that exposes the graph, loadout, task-resolution,
and search surfaces as tools. This is the path to use when you want a coding
agent to reach AKMS directly rather than shelling out to the `akms` CLI.

The server is bound to one repository. It reads that repo's local knowledge and
the global vault, and it never writes to the global vault.

## Install

The server needs nothing beyond the base package:

```bash
uv pip install akms          # or: pip install akms
```

!!! note "Where the MCP runtime comes from"

    AKMS does not declare `mcp` directly. It arrives transitively through
    `claude-agent-sdk` (`mcp>=1.23.0,<2.0.0`) and `openai-agents`, both base
    dependencies, so it is present in any working install. If you vendor or
    trim dependencies, pin `mcp` explicitly.

## Launch

```bash
akms-mcp-stdio --repo-root /path/to/your/project
```

To point at a vault other than the default `~/.claude/akms/nodes/`:

```bash
akms-mcp-stdio --repo-root /path/to/your/project \
               --global-vault /path/to/vault
```

The equivalent module form, if you have not installed the console script:

```bash
python -m akms.orchestrator.mcp_stdio --repo-root /path/to/your/project
```

## Register with Claude Code

Add it to your project's `.mcp.json`:

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

Or register it from the command line:

```bash
claude mcp add akms -- akms-mcp-stdio --repo-root .
```

If AKMS is installed in a project-local virtualenv rather than on `PATH`, call
it through your runner so the right interpreter is used:

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

Tools then appear to the agent as `mcp__akms__akms_*`.

## Tool surface

Thirteen tools, all bound to the `--repo-root` you launched with.

### Graph lifecycle

| Tool | Arguments | Purpose |
|---|---|---|
| `akms_build_graph` | — | Compile the graph from global vault + local state into `graph.json`. |
| `akms_graph_status` | — | Health report: low-confidence, tentative, and orphaned nodes. |
| `akms_update_graph` | `source_json` | Apply AgentMemory / PCD data to local state and recompile. |
| `akms_re_evaluate` | `task_id`, `phase`, `seed_tags`, `agent_role` | Regenerate a loadout against updated graph state. |

### Retrieval

| Tool | Arguments | Purpose |
|---|---|---|
| `akms_query_subgraph` | `seed_tags`, `agent_role`, `max_depth` | Ranked subgraph for loadout construction. |
| `akms_generate_loadout` | `task_id`, `phase`, `seed_tags`, `agent_role` | Write a loadout markdown file. |
| `akms_resolve_task` | `task_json_path`, `routes_path`, `agent_role` | Exact task knowledge → loadout + resolution manifest. |
| `akms_derive_tags` | `task_json` | Derive tags for a task via hybrid scope + text matching. |
| `akms_get_pitfalls` | `node_ids` | Pitfall edges originating from the given nodes. |

### Search

| Tool | Arguments | Purpose |
|---|---|---|
| `akms_search_nodes` | `query`, `limit` | Search vault + local nodes. |
| `akms_search_mirror` | `query`, `limit` | Search `knowledge/code-mirror/`. |
| `akms_search_sessions` | `query`, `limit` | Search AgentMemory / PCD markdown. |

### Code mirror

| Tool | Arguments | Purpose |
|---|---|---|
| `akms_generate_mirror` | `phase`, `parent_branch` | Refresh code mirrors via the configured provider. |

!!! warning "How the three search tools degrade"

    They shell out through `run_qmd.sh`, which ships inside the package at
    `akms/_bundled/qmd/`. Two distinct degradations:

    - **`qmd` binary absent** — the wrapper falls back to grep-style matching.
      Poorer results, not an error.
    - **wrapper absent** (a broken install) — the call logs a warning and
      returns an **empty list**; it does not raise.

    So an empty `akms_search_*` result is never by itself evidence that no
    knowledge exists. Check with:

    ```bash
    python skills/akms/scripts/check_setup.py --repo .
    ```

    The graph, loadout, and task-resolution tools do not depend on `qmd`.

## Which surface should an agent use?

| Situation | Use |
|---|---|
| Task names exact paths or symbols that *must* be covered | `akms_resolve_task` |
| Exploratory: "what do we know about X?" | `akms_query_subgraph` or `akms_search_nodes` |
| Producing context for a downstream agent | `akms_generate_loadout` |
| Recording what an agent learned | `akms_update_graph` |

Tag matching is a ranking signal, not a guarantee. When coverage is mandatory,
use [exact task resolution](../../reference/akms/user-guide/task-resolution.md), which fails
closed rather than returning a best-effort match.

## The global vault is read-only

No AKMS process writes to `~/.claude/akms/nodes/` (or `$AKMS_GLOBAL_VAULT`).
The MCP server is no exception: `akms_update_graph` writes project-local state
only. Treat the vault as shared, immutable input.

## See also

- [Agent skills](../agent-skills.md) — a drop-in skill that teaches an agent this workflow
- [Task resolution](../../reference/akms/user-guide/task-resolution.md) — the fail-closed path
- [CLI commands](../../reference/akms/user-guide/cli-commands.md) — the same surfaces from a shell
