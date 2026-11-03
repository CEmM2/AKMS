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
| `generated/` | `build`, `summarize` | Module pages (`modules/`), symbol pages (`symbols/`), summaries (`summaries/`), `repo_map.md` and `symbol_graph.json`. Symbol pages include the symbol's source. | No. |
| `index/repo_wiki.sqlite3` | `build`, `index` | The SQLite full-text search index. | No. |
| `ir_cache/` | `build` | Parsed-source cache that makes `build --changed-only` fast. | No. |
| `cache/llm_summaries.json` | `build`, `summarize` | Cache of the local summaries. | No. |
| `manifest.json` | `build` | File hashes and the list of generated pages. | No. |
| `build_errors.json` | `build` | Files that failed to parse in the last build; `[]` when none. | No. |

`build` runs `init` first, so it also creates `config.yaml`, `SPEC.md` and
`overlays/` if they are missing.

`repo-wiki clean` is not implemented and removes nothing. To start over, delete
`.repo_wiki/generated/`, `.repo_wiki/index/`, `.repo_wiki/ir_cache/`,
`.repo_wiki/cache/`, `manifest.json` and `build_errors.json`, then run
`repo-wiki build --force`.

## `.gitignore`

List the rebuildable paths explicitly:

```gitignore
.repo_wiki/generated/
.repo_wiki/index/
.repo_wiki/ir_cache/
.repo_wiki/cache/
.repo_wiki/manifest.json
.repo_wiki/build_errors.json
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
