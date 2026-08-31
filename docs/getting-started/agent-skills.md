# Agent assets

AKMS ships drop-in skills that teach a coding agent to use it. They live in
the `skills/` directory at the repository root.

They are deliberately **not** under `.claude/` — that directory holds internal
harness configuration and is stripped from published copies, so anything placed
there never reaches a consumer.

| Asset | Use it for |
|---|---|
| `skills/akms/` | The core loop: compile a graph, resolve task context, generate loadouts, feed outcomes back. **Start here.** |
| `skills/node-gen/` | Generating domain nodes from NotebookLM notebooks (papers) via the `nlm` CLI. |
| `skills/deepwiki-nodes/` | Generating domain nodes from a GitHub repo indexed by DeepWiki (code). |
| `skills/akms-spec-check/` | Auditing an implementation against the frozen v2 conformance invariants. |
| `agents/akms-spec-reviewer.md` | Reviewing AKMS changes against those invariants before committing. |
| `agents/digest-refiner.md` | Refining a zotero-summarizer collection digest for the AKMS bridge. |
| `commands/node-gen-invoker.md` | One-shot entry point that drives `node-gen` end to end. |
| `hooks/` | Two `PreToolUse` guards: global vault read-only, frozen-schema warning. |

## Install

Skills are plain directories — copy the ones you want into your agent's skills
directory.

These mirror Claude Code's own `.claude/` layout, so installing is a copy:

```bash
# everything, project-scoped
cp -R /path/to/AKMS/{skills,agents,commands,hooks} .claude/

# or just one skill, user-scoped
mkdir -p ~/.claude/skills && cp -R /path/to/AKMS/skills/akms ~/.claude/skills/
```

Other runtimes: each `SKILL.md` is plain markdown with YAML frontmatter
(`name`, `description`) and has no runtime dependency on Claude Code.

!!! tip "`pip install akms` delivers these too"

    The skills are mirrored into the package as `akms/_bundled/skills/`, so a
    wheel install carries them. Locate them without a clone:

    ```python
    from akms._resources import bundled_skills_path
    bundled_skills_path("akms")   # a real directory inside site-packages
    ```

    The repo-root `skills/` tree remains the canonical copy; a test fails the
    build if the two drift. The qmd wrapper is bundled the same way, which is
    what makes `akms_search_*` work in a wheel-only install.

## Verify a setup

```bash
python skills/akms/scripts/check_setup.py --repo .
```

Reports what is actually wired — package, CLI, MCP entry point, global vault,
project layout, compiled graph, and search — and distinguishes "absent" from
"broken" from "present but empty".

## Bundled helpers

`skills/akms/scripts/`

- `akms_bootstrap.sh` — create the layout and compile a first graph
- `new_node.py` — scaffold a schema-valid v2 node
- `check_setup.py` — verify a setup end to end

`skills/akms/references/`

- `node_authoring.md` — the v2 field and body contract
- `mcp_setup.md` — MCP registration and the tool list
- `workflows.md` — worked end-to-end examples

## Two things worth knowing

**A tag query returning results is not proof of coverage.** `akms query` ranks
by relevance and always returns a best effort. When specific paths or symbols
must be covered before being edited, use
[`akms resolve-task`](../reference/akms/user-guide/task-resolution.md), which fails closed
and emits a resolution manifest.

**Search degrades quietly rather than raising.** The `run_qmd.sh` wrapper ships
with the package; if the `qmd` binary is absent it falls back to grep-style
matching — poorer results, not an error. Were the wrapper ever missing,
`akms_search_*` returns an empty list rather than raising, and that would not
mean the knowledge is absent.

## Auditing an implementation

`skills/akms-spec-check/` and `agents/akms-spec-reviewer.md` audit against
[Conformance Invariants](../reference/akms/conformance-invariants.md) — the normative, checkable
subset of the frozen v2 spec, with stable `INV-*` IDs to cite in findings.

That page exists so an audit does not depend on the full design documents, which
live in `dev/` and are stripped from every published copy. Its vocabulary and
constant tables are compared against `akms.schema.models` by a test, so they
cannot drift from what the code enforces.

## See also

- [Serve AKMS over MCP](akms/mcp.md)
- [Quickstart](akms/quickstart.md)
- [Task resolution](../reference/akms/user-guide/task-resolution.md)
