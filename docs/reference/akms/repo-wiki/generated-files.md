# Generated files

`repo-wiki` keeps its state in `.repo_wiki/` at the repository root.
`export-akms` writes to a separate output tree. Everything except your
configuration and your overlays can be rebuilt from source.

## Under `.repo_wiki/`

| Path | Written by | Contents | Commit? |
|---|---|---|---|
| `config.yaml` | `init` | The [configuration](configuration.md). | Yes, if the team shares it. |
| `SPEC.md` | `init` | A short note on how the directory is managed. | Yes, if the team shares it. |
| `overlays/` | you | Hand-written Markdown notes. `build` never touches them; `index` includes them in search. | Yes. |
| `generated/` | `build`, `summarize` | Module pages (`modules/`), symbol pages (`symbols/`), summaries (`summaries/`), `repo_map.md`, `symbol_graph.json` and `flows.json` (see [flows](flows.md#flowsjson)). Symbol pages include the symbol's source. | No. |
| `index/repo_wiki.sqlite3` | `build`, `index` | The SQLite full-text search index. | No. |
| `ir_cache/` | `build` | Parsed-source cache that makes `build --changed-only` fast. | No. |
| `cache/llm_summaries.json` | `build`, `summarize` | Cache of the local summaries. | No. |
| `manifest.json` | `build` | File hashes and the list of generated pages. | No. |
| `locks/` | `build`, `export-akms`, the git hooks | Lock files that keep two builds or exports from overlapping. | No. |
| `hooks/` | the [git hooks](hooks.md) | `build.log` of background refreshes and the `pending` marker. | No. |
| `build_errors.json` | `build` | Files that failed to parse in the last build; `[]` when none. | No. |

`build` runs `init` first, so it also creates `config.yaml`, `SPEC.md` and
`overlays/` if they are missing.

`repo-wiki clean` is not implemented and removes nothing. To start over, delete
`.repo_wiki/generated/`, `.repo_wiki/index/`, `.repo_wiki/ir_cache/`,
`.repo_wiki/cache/`, `manifest.json` and `build_errors.json`, then run
`repo-wiki build --force`.

## Symbol graph fields

`generated/symbol_graph.json` (schema `symbol_graph v1`, described in its `_comment`
field) has `nodes` keyed by ID and a sorted `edges` list. Each edge has `source`,
`target`, `type` (`defined_in`, `belongs_to`, `imports`, `calls`, `inherits`),
`resolution` (`CONFIDENT`, `HEURISTIC`, `UNRESOLVED`), `dst_id`, `dst_name` and, for
HEURISTIC edges, `dst_candidates`.

These fields are optional. Each is written only when it has a value, so a graph
without them is still valid `symbol_graph v1` and readers must not require them:

| Field | On | Meaning |
|---|---|---|
| `provenance` | edge | `static`, `observed` or `inferred`. Absent means `static`, which is every edge written today. |
| `bindings` | module node | Python: local name to dotted import target. |
| `dispatch` | module node | Python: module-level dict literals of callables, name to sorted value names. |
| `receivers` | symbol node | Python: on a function or method, locals and annotated parameters used as call receivers, name to the constructor or annotation names they are bound to; on a class, the attributes used as `self.x.m()` or `cls.x.m()`, name to the names they are bound to in the class body or `__init__`. |
| `table_refs` | symbol node | Python: module-level names the symbol indexes (`T[key]`, `T.get(key)`). |
| `cli_handlers` | symbol node | Python: names the symbol passes as argparse `set_defaults(func=...)`. |
| `decorators` | symbol node | Decorator names with their arguments dropped (`app.command`). |
| `main_calls` | module node | Python: call names run when the module executes as a script (its `__main__` block, or all module-level code of a `__main__.py`). |

`context`, `impact` and `changes` turn `receivers`, `table_refs` and `dispatch` into
`receiver` and `dispatch` links (provenance `inferred`) when they load the graph;
the edges in the file are unchanged. `cli_handlers`, `decorators` and `main_calls`
are read only to find the entry points of [flows](flows.md). See
[Reading impact and risk](reading-impact.md#confident-and-possible-links).

## `.gitignore`

List the rebuildable paths explicitly:

```gitignore
.repo_wiki/generated/
.repo_wiki/index/
.repo_wiki/ir_cache/
.repo_wiki/cache/
.repo_wiki/manifest.json
.repo_wiki/build_errors.json
.repo_wiki/locks/
.repo_wiki/hooks/
.repo2md-export-*.lock
```

Do not use a wildcard such as `.repo_wiki/*` and then re-include files with
`!`. `repo-wiki` reads the root `.gitignore` itself, does not understand `!`
lines, and would exclude `overlays/` from the search index.

## Export output

`export-akms` writes under the directory you pass as `--output`:

| Path | Contents |
|---|---|
| `<output>/.knowledge/code-mirror/` | One Markdown file per exported source file. Python mirrors sit at `code-mirror/<source path>.md` (`.py` replaced by `.md`); other languages at `code-mirror/<language>/<source path>.md` with the source extension kept, such as `code-mirror/rust/src/lib.rs.md`. |
| `<output>/knowledge/code-mirror/` | The same, when you pass `--knowledge-dir knowledge`. |
| `<parent of output>/.repo2md-export-<hash>.lock` | A single-writer lock that exists only while an export runs. It sits inside the repository only when `--output` is a subdirectory of it. See [Output lock](akms-export.md#output-lock). |

Mirrors are generated from your source and carry
`source: generated` and `auto_update: true` in their frontmatter. Whether to
commit them is a project decision; the
[mirror provider guide](../user-guide/mirror_providers.md) describes how AKMS
regenerates and refreshes them. If you commit a mirror, pin `--generated-at`
(or `SOURCE_DATE_EPOCH`) so that rebuilding unchanged source produces
identical bytes.

The lock file name still uses the `repo2md` prefix from the tool's earlier
name. Ignore it as shown above.
