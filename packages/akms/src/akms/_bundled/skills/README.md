# Agent assets

Drop-in skills that teach a coding agent to use AKMS. These are published with
the repository — unlike `.claude/`, `.codex/`, and `.agents/`, which are
internal harness configuration and are stripped from published copies.

They also ship **inside the wheel**, so `pip install akms` delivers them:

```python
from akms._resources import bundled_skills_path
bundled_skills_path("akms")   # -> .../site-packages/akms/_bundled/skills/akms
```

This directory is the canonical copy; `src/akms/_bundled/skills/` is mirrored
from it and a test fails the build if the two drift.

| Asset | Use it for |
|---|---|
| `skills/akms/` | The core loop: compile a graph, resolve task context, generate loadouts, feed outcomes back. **Start here.** |
| `skills/node-gen/` | Generating domain nodes from NotebookLM notebooks (papers) via the `nlm` CLI. |
| `skills/deepwiki-nodes/` | Generating domain nodes from a GitHub repo indexed by DeepWiki (code). |
| `skills/akms-spec-check/` | Auditing an AKMS implementation against the frozen v2 spec. |
| `agents/akms-spec-reviewer.md` | Reviewing AKMS changes against the frozen spec before committing. |
| `agents/digest-refiner.md` | Refining a zotero-summarizer collection digest for the AKMS bridge. |
| `commands/node-gen-invoker.md` | One-shot entry point that drives `node-gen` end to end. |
| `hooks/` | Two `PreToolUse` guards: global vault read-only, frozen-schema warning. See `hooks/README.md`. |

## Install

These mirror Claude Code's own `.claude/` layout, so installing is a copy:

```bash
# everything, project-scoped
cp -R /path/to/AKMS/{skills,agents,commands,hooks} .claude/
```

Or take just the pieces you want. Skills are plain directories; copy the ones you
want into your agent's skills directory.

**Claude Code** — project-scoped:

```bash
mkdir -p .claude/skills
cp -R path/to/AKMS/skills/akms .claude/skills/
```

…or user-scoped, to have it everywhere:

```bash
mkdir -p ~/.claude/skills
cp -R path/to/AKMS/skills/akms ~/.claude/skills/
```

Then start a new session and ask for something that matches the skill's
triggers ("what do we know about X?", "resolve task context", "generate a
loadout").

Other agent runtimes: point them at these directories however they load skills.
The `SKILL.md` files are plain markdown with YAML frontmatter (`name`,
`description`) and carry no runtime dependency on Claude Code.

## What each skill needs

**`akms/`** needs the `akms` package:

```bash
uv pip install akms
python skills/akms/scripts/check_setup.py --repo .
```

`check_setup.py` reports exactly what is wired and what is missing — package,
CLI, MCP entry point, global vault, project layout, compiled graph, and search.
Run it first when something behaves unexpectedly.

**`deepwiki-nodes/`** needs network access to `https://mcp.deepwiki.com/mcp`
(free, no auth) and a repository that DeepWiki has indexed. No MCP registration
required — the bundled engine speaks HTTP directly.

**`hooks/`** need `jq` on `PATH`. A `PreToolUse` hook that fails does not block
the write it guards, so verify it before relying on it — `hooks/README.md` gives
a one-liner that proves the vault guard actually blocks.

**`akms-spec-check/` and `agents/akms-spec-reviewer.md`** audit against
[`docs/reference/akms/conformance-invariants.md`](../docs/reference/akms/conformance-invariants.md) — a normative,
checkable subset of the frozen v2 spec with stable `INV-*` IDs to cite in
findings. It ships with published copies, so these assets work without the full
design documents (which live in `dev/`, stripped from published copies). A test
compares its vocabulary and constant tables against `akms.schema.models`, so what
you audit against is what the code enforces.

**`node-gen/`** additionally needs the `nlm` CLI:

```bash
uv tool install notebooklm-mcp-cli
nlm login
nlm notebook list      # verify auth
```

## Bundled helpers

`akms/scripts/`:

- `akms_bootstrap.sh` — create the layout and compile a first graph
- `new_node.py` — scaffold a schema-valid v2 node
- `check_setup.py` — verify a setup end to end

`akms/references/`:

- `node_authoring.md` — the v2 field and body contract
- `mcp_setup.md` — MCP registration and the tool list
- `workflows.md` — worked end-to-end examples

## Two things worth knowing up front

**A tag query returning results is not proof of coverage.** `akms query` ranks
by relevance and always returns its best effort. When specific paths or symbols
*must* be covered before they are edited, use `akms resolve-task`, which fails
closed and emits a resolution manifest you can check.

**Search degrades quietly rather than raising.** `run_qmd.sh` now ships with
the package, so the wrapper is always present; if the `qmd` binary itself is
absent it falls back to grep-style matching — poorer results, not an error. If
the wrapper were ever missing, `akms_search_*` returns an empty list rather than
raising, and an empty result would not mean the knowledge is absent.
`check_setup.py` tells you which case you are in.
