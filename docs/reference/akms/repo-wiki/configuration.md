# Configuration

`repo-wiki` reads `.repo_wiki/config.yaml` in the repository root.
`repo-wiki init` creates it with every default written out, except the
built-in exclude patterns, which apply without being listed. You only need to
keep the keys you change.

## How the file is read

- The file is merged over the built-in defaults. Mappings merge key by key,
  and a scalar or list you write replaces the default, with one exception:
  **`scanner.exclude` adds to the built-in exclude patterns** rather than
  replacing them. `scanner.include` does replace the default include list.
- The parser reads a YAML subset: nested mappings, scalars and lists of
  scalars. Write booleans as `true` or `false`. Write each list item on its
  own `- item` line; `[]` is the empty list, and a flow list such as
  `[a, b]` is read as a single string. Comments must be on their own line; a
  `#` after a value becomes part of the value.
- A missing file means all defaults. Unknown keys are ignored.
- These checks fail the command before it does any work: `scanner.max_file_size_kb`
  must be a positive number, `scanner.include` and `scanner.exclude` must be
  lists, `scanner.use_default_excludes` must be `true` or `false`,
  `generation.output_dir` must be set, and
  `summaries.provider` other than `local` requires
  `summaries.allow_source_code_upload: true`. Even then, no remote provider is
  implemented, so a non-`local` provider fails when summaries are generated.

Run `repo-wiki scan` after editing `scanner.*` or `languages.*` to see the
effect. `repo-wiki scan --json` also prints `exclude`, the complete list of
exclude patterns applied.

## `scanner`

Controls which files are read. It applies to every subcommand that scans,
including [`export-akms`](akms-export.md).

| Key | Default | Effect |
|---|---|---|
| `scanner.include` | `**/*.py`, `**/*.md`, `**/*.yaml`, `**/*.yml`, `**/*.toml` | Glob patterns a file must match to be eligible. A list you write replaces the default list. The globs of each enabled non-Python language (see [`languages`](#languages)) are added to a non-empty list. An empty list accepts every file. |
| `scanner.exclude` | none | Patterns that remove a file or prune a directory, added to the [built-in exclude patterns](privacy-security.md#built-in-exclude-patterns). Checked before the file is read. Duplicates of a built-in pattern are ignored. |
| `scanner.use_default_excludes` | `true` | With `false`, the ordinary built-in excludes (environments, caches, build and data output) are not applied. The tool-state patterns (`.git`, `.repo_wiki/`, the generated-page directory) and the secret and credential patterns always are; no setting removes them. |
| `scanner.max_file_size_kb` | `512` | Larger files are skipped as `too_large`. |
| `scanner.respect_gitignore` | `true` | Also skip anything matched by the repository's root `.gitignore`. See [the limits of this](privacy-security.md#gitignore). |

A file is eligible only if it passes the exclude patterns, matches an include
pattern, is within the size limit, and is not binary (a NUL byte or invalid
UTF-8 in the first 8 KiB marks a file as binary). Symbolic links are never
followed.

## `languages`

Python is always on and parsed with the standard-library `ast` module. Other
languages are opt-in, each by its own key.

| Key | Default | Effect |
|---|---|---|
| `languages.rust.enabled` | not set (off) | Adds `**/*.rs` and parses with tree-sitter. Needs `akms[rust]`. |
| `languages.cpp.enabled` | not set (off) | Adds `**/*.cpp`, `*.cc`, `*.cxx`, `*.hpp`, `*.hh`, `*.h` and `*.hxx`. |
| `languages.julia.enabled` | not set (off) | Adds `**/*.jl` and parses with tree-sitter. Needs `akms[julia]`. |
| `languages.cpp.backend` | `treesitter` | `treesitter` (needs `akms[cpp]`) or `doxygen`. |

With `backend: doxygen`, the installed `doxygen` program runs once over the
C++ files. If `doxygen` is not on `PATH`, `repo-wiki` falls back to
tree-sitter and records a backend note, shown by `build`. If the tree-sitter
grammar is also missing, those files are skipped with a note rather than
failing the build. `build --changed-only` reruns Doxygen only when the C++
file set or the Doxygen version changed.

A minimal multi-language configuration:

```yaml
languages:
  rust:
    enabled: true
  cpp:
    enabled: true
    backend: doxygen
  julia:
    enabled: true
```

## `generation`

Controls what `build` writes.

| Key | Default | Effect |
|---|---|---|
| `generation.output_dir` | `.repo_wiki/generated` | Directory for generated pages, relative to the repository root. The index reads from it, and the scanner always skips it. |
| `generation.generate_module_docs` | `true` | Write one page per module under `modules/`. |
| `generation.generate_symbol_docs` | `true` | Write one page per symbol under `symbols/`. |
| `generation.generate_repo_map` | `true` | Write `repo_map.md`. |

## `summaries`

Summaries are generated locally from each symbol's kind, location, docstring
and detected calls. No model is involved.

| Key | Default | Effect |
|---|---|---|
| `summaries.enabled` | `true` | Write summary pages and add summaries to symbol pages. `build --no-summaries` turns them off for one run. |
| `summaries.provider` | `local` | Only `local` works. See above for other values. |
| `summaries.allow_source_code_upload` | `false` | Acknowledgement required before a non-`local` provider is accepted. |

## `retrieval`

Controls `query`. The index returns `top_k_initial` candidates; the best
`top_k_reranked` are kept, and each is expanded with related context.

| Key | Default | Effect |
|---|---|---|
| `retrieval.top_k_initial` | `30` | Candidates taken from the index. |
| `retrieval.top_k_reranked` | `8` | Results kept. `query --top-k N` overrides it for one run. The context list is capped at three times this value. |
| `retrieval.expand_parent` | `true` | Add the enclosing class or module of each result. |
| `retrieval.expand_children` | `true` | Add the members of each result. |
| `retrieval.expand_callees` | `true` | Add the symbols each result calls. |
| `retrieval.expand_callers` | `true` | Add the symbols that call each result. |
| `retrieval.expand_heuristic_edges` | `true` | Follow call edges that matched several candidates by name. With `false`, only edges that resolved to exactly one target are followed. |
| `retrieval.include_tests` | `true` | Add test modules (paths containing `test`) that mention a result. |

## `flows`

Settings for the [execution flows](flows.md) that `build` writes to `flows.json`.
Unknown keys and values of the wrong type are rejected when the file is loaded.

| Key | Default | Effect |
|---|---|---|
| `flows.enabled` | `true` | Write `flows.json` on `build`, and show flows in `context`, `impact` and `changes`. With `false`, `build` removes an old `flows.json`; `flows` and `flow` still compute flows on demand. |
| `flows.entries.console_scripts` | `true` | Console scripts declared in `pyproject.toml` files are entry points. |
| `flows.entries.scripts` | `true` | `if __name__ == "__main__":` blocks and `__main__.py` modules are entry points. |
| `flows.entries.cli` | `true` | Functions with a decorator matching `cli_decorators`, and argparse `set_defaults(func=...)` handlers, are entry points. |
| `flows.entries.tests` | `false` | Test functions are entry points. |
| `flows.entries.roots` | `true` | Public functions and methods that nothing outside the tests calls confidently are entry points. |
| `flows.cli_decorators` | `["*.command", "*.group"]` | Wildcard patterns matched against a decorator's dotted name, without its arguments (`@app.command("x")` is `app.command`). |
| `flows.include_heuristic` | `false` | Also follow HEURISTIC links. They are counted and flagged in each flow. |
| `flows.max_depth` | `6` | Levels below the entry. |
| `flows.max_fanout` | `12` | Callees followed from one step. |
| `flows.max_steps` | `60` | Steps in one flow. |
| `flows.max_flows` | `1000` | Flows kept in `flows.json`; tests, then roots, are dropped first, the shortest first. |

A change to any of these, except `enabled`, makes an existing `flows.json` stale:
readers recompute until the next build.

## Keys that are written but not read

`init` writes these keys, and they are accepted, but the current code does not
read them. Changing them has no effect.

| Key | Written default |
|---|---|
| `repo.name`, `repo.root`, `repo.default_branch` | directory name, `.`, `main` |
| `languages.python.enabled` | `true` |
| `generation.include_full_code`, `include_signatures`, `include_docstrings`, `include_imports`, `include_line_numbers` | `true` |
| `index.backend` | `qmd` |
| `index.bm25`, `index.vectors`, `index.hybrid_search`, `index.rerank` | `true` |
| `index.chunking.mode`, `max_chunk_chars`, `overlap_chars` | `symbol`, `8000`, `500` |
| `retrieval.expand_siblings` | `false` |
| `summaries.model`, `cache`, `regenerate_on_code_change`, `max_symbol_chars` | `null`, `true`, `true`, `12000` |

The search index is a local SQLite full-text index (`.repo_wiki/index/repo_wiki.sqlite3`),
ranked with BM25 and a score-fusion step. It does not use vectors or an
external search service, whatever `index.*` says.

## Export and configuration

`export-akms` reads `scanner.*` and `languages.*` only. It ignores
`generation`, `summaries`, `index` and `retrieval`, and it never writes
summaries or the index.
