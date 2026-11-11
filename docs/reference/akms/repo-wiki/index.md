# repo-wiki

`repo-wiki` reads a repository's source and writes a local, searchable wiki
of its modules and symbols (functions, classes and methods). It also projects
that source into AKMS code mirrors, which is what the default `builtin`
[code-mirror provider](../user-guide/mirror_providers.md) runs.

It is part of the `akms` package, as the module `akms.repo_wiki`, and runs on
your machine: the command makes no network calls and calls no language model.
The one exception is in your browser: the `graph` viewer page loads its
drawing library from a CDN. See [Privacy and security](privacy-security.md).

## Ways to run it

All three run the same command with the same subcommands and flags.

| Invocation | Notes |
|---|---|
| `repo-wiki <subcommand>` | Console script installed with `akms`. |
| `akms wiki <subcommand>` | Passes everything after `wiki` through. The root `--repo` becomes `--repo-root`; a `--repo-root` given after `wiki` takes precedence. |
| `python -m akms.repo_wiki <subcommand>` | The form the `builtin` provider uses. |

`--repo-root` (default `.`) selects the repository to operate on. It goes
before the subcommand:

```bash
repo-wiki --repo-root path/to/repo scan
akms --repo path/to/repo wiki scan
```

## Install

`repo-wiki` needs nothing beyond `akms` itself, which requires Python 3.12:

```bash
pip install akms
repo-wiki --help
```

Python sources are always supported. Other languages are opt-in in
[the configuration](configuration.md#languages) and need extra packages:

| Language | Needs | Install |
|---|---|---|
| Python | nothing extra | — |
| Rust | tree-sitter grammar | `pip install "akms[rust]"` |
| C++ | tree-sitter grammar, or the `doxygen` program on `PATH` | `pip install "akms[cpp]"` |
| Julia | tree-sitter grammar | `pip install "akms[julia]"` |
| all three tree-sitter languages | | `pip install "akms[multilang]"` |

Quote the argument: zsh otherwise treats the brackets as a glob. See
[Installation](../../../getting-started/akms/installation.md) for the other
extras.

## Subcommands

| Subcommand | What it does |
|---|---|
| `init` | Creates `.repo_wiki/` with `config.yaml`, `SPEC.md` and `overlays/`. |
| `scan` | Lists the files that would be processed and counts the skipped ones. |
| `parse <path>` | Parses one Python file and prints its symbols. |
| `build` | Scans, parses and writes the wiki pages, local summaries and the search index. Also accepts `--changed-only`, `--force`, `--no-summaries`, `--no-index` and `--json`. |
| `index` | Updates the search index from the generated pages and your overlays. `--query` prints matching entries as JSON. |
| `query <question>` | Searches the index and prints ranked results with source citations. |
| `summarize` | Generates local summary pages. `--changed-only`, `--force` and `--symbol` narrow or force the run. |
| `export-akms` | Writes AKMS code mirrors. See [AKMS export](akms-export.md). |
| `stats` | Prints the number of tracked files and generated pages. |
| `context <symbol>` | Shows a symbol's definition, callers, callees and module imports. See [context](context.md). |
| `impact <symbol>` | Lists what depends on a symbol, by depth, with a risk level. See [impact](impact.md). |
| `changes` | Maps a git diff to the symbols it touches and their direct callers. See [changes](changes.md). |
| `flows` | Lists execution flows: entry points followed down their confident calls. See [flows and flow](flows.md). |
| `flow <flow>` | Shows one execution flow as a call tree. See [flows and flow](flows.md). |
| `hooks <action>` | `install`, `uninstall` or `status` of the opt-in git hooks that refresh the graph in the background after git changes the tree. See [hooks](hooks.md). |
| `graph [input]` | Serves an interactive viewer for the symbol graph on `127.0.0.1:8765`. |
| `clean` | Not implemented: prints a message and removes nothing. |

Run `repo-wiki <subcommand> --help` for the flags of each.

## In this section

- [Quickstart](quickstart.md): initialize, build, query, and export a mirror.
- [Configuration](configuration.md): every key in `.repo_wiki/config.yaml`.
- [Generated files](generated-files.md): what is written where, and what to
  commit.
- [Privacy and security](privacy-security.md): what is scanned and what is
  excluded.
- [AKMS export](akms-export.md): `export-akms` flags, output and locking.
- [context](context.md), [impact](impact.md) and [changes](changes.md): code
  intelligence over the symbol graph, for exploring a symbol, checking who depends
  on it before an edit, and checking a diff before a commit.
- [flows and flow](flows.md): static execution flows from console scripts,
  `__main__` blocks, CLI commands and uncalled public functions, and the
  `flows.json` format.
- [hooks](hooks.md): opt-in git hooks that keep the graph and flows fresh.
- [Reading impact and risk](reading-impact.md): depths, confident and possible
  links, the risk rule, and what the graph cannot see.
