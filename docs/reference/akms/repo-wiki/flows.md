# flows and flow

An execution flow is an entry point, such as a console script, a `__main__` block or
a CLI command, followed down its calls. `repo-wiki flows` lists the flows and
`repo-wiki flow` shows one as a call tree. Both read `flows.json`, which
[`build`](index.md#subcommands) writes next to the symbol graph. Neither one changes
anything.

Flows are static: they come from the symbol graph, not from running the code.

```bash
repo-wiki flows
```

```text
Flows: 3 of 3 (3 root); showing 3
  flow:67984a14e9db  pkg.cli.main  [root; 5 steps; depth 4]
      entry python:pkg/cli.py::main  pkg/cli.py:L6-L7
  flow:0bc38b6af8b6  pkg.service.persist  [root; 5 steps; depth 3]
      entry python:pkg/service.py::persist  pkg/service.py:L11-L13
  flow:81e076513602  pkg.service.via_module  [root; 2 steps; depth 1]
      entry python:pkg/service.py::via_module  pkg/service.py:L16-L17
```

```bash
repo-wiki flow pkg.cli.main
```

```text
Flow pkg.cli.main  [root; 5 steps; depth 4]  flow:67984a14e9db
  entry python:pkg/cli.py::main  pkg/cli.py:L6-L7
  main  pkg/cli.py:L6-L7
    public_entry  pkg/api.py:L6-L8  [CONFIDENT import]
      run  pkg/service.py:L7-L8  [CONFIDENT import]
        middle  pkg/core.py:L9-L10  [CONFIDENT import]
          leaf  pkg/core.py:L4-L6  [CONFIDENT local]
Terminals: 1
```

## Flags

`repo-wiki flows`:

| Flag | Default | Meaning |
|---|---|---|
| `--entry TEXT` | none | Only flows whose name, entry ID or console-script alias contains `TEXT`. With `*`, `?` or `[`, `TEXT` is a wildcard pattern matched against the whole name. |
| `--kind KIND` | none | Only flows whose entry is `console_script`, `script`, `cli`, `root` or `test`. |
| `--touching SYMBOL` | none | Only flows with a step on `SYMBOL`, named as for [`context`](context.md#naming-a-symbol). Each flow then shows the depth of that step. |
| `--limit N` | `50` | Show at most `N` flows; `0` shows all. The summary still counts every match. |
| `--json` | off | Print a `repo-wiki/flows/v1` object instead of text. |
| `--allow-stale` | off | Use the graph even when sources changed since it was built. |

`repo-wiki flow FLOW`:

| Flag | Default | Meaning |
|---|---|---|
| `FLOW` | required | A flow ID (`flow:...`), a flow name, a console-script name or alias, or the entry symbol named as for `context`. |
| `--json` | off | Print a `repo-wiki/flow/v1` object instead of text. |
| `--allow-stale` | off | As for `flows`. |

## Entry points

Each entry point gets one flow. A symbol that matches several rules takes the
first kind in this table:

| Kind | Entry point | Flow name |
|---|---|---|
| `console_script` | The target of an entry in `[project.scripts]`, `[project.gui-scripts]` or `[tool.poetry.scripts]` of any `pyproject.toml` in a directory that holds scanned sources. Two scripts with one target share a flow; the second name is an alias. | the script name |
| `script` | A module's top-level `if __name__ == "__main__":` block, or every module-level call of a `__main__.py`. The flow starts at the module. | `module:__main__` |
| `cli` | A function or method with a decorator matching [`flows.cli_decorators`](configuration.md#flows) (`@app.command()`, `@cli.group()`), or a name passed as `parser.set_defaults(func=...)` in argparse code. | dotted name |
| `root` | A public function or method (no part of its qualified name starts with `_`, not nested in a function, not in a test file) that no code outside the tests calls with a CONFIDENT link, and that has at least one link to follow. | dotted name |
| `test` | A test function: `test*` at the top level of a test file, or a `test*` method of a top-level `Test*` class. Off by default. | dotted name |

Test functions are off by default because each one is its own entry point: on a
repository with a large suite they outnumber every other kind and bury the flows a
user can run. Turn them on with `flows.entries.tests: true` to ask what a test
exercises; `--kind test` then lists only those.

Roots are a heuristic. A function that nothing calls with a CONFIDENT link may be
called through dynamic dispatch, a callback or a registry the graph cannot see, so a
root is a candidate entry point.

## How a flow is walked

From the entry, the walk goes breadth-first over `calls` links. Only CONFIDENT links
are followed unless `flows.include_heuristic` is `true`; see
[Reading impact and risk](reading-impact.md#confident-and-possible-links) for what
each kind of link means. Each step is a symbol, listed once, at the depth where it
was first reached, with `via` (the step that reached it) and the link's
`resolution`, `basis` and `provenance`.

Three caps keep a flow bounded, and a capped step says so:

| Cap | Default | When it is reached |
|---|---|---|
| `max_depth` | `6` | A step at this depth is not expanded. It is marked `cut: depth` with `omitted`, the number of its callees not yet in the flow. |
| `max_fanout` | `12` | A step with more callees follows only this many. CONFIDENT callees come first, then those that call the most themselves; the rest are `omitted` and, in JSON, listed in `omitted_ids` (up to 25). |
| `max_steps` | `60` | The flow stops growing. The step being expanded is marked `cut: steps`. |

A flow with any cut has `truncated: true` and its reasons in `truncated_reasons`.
Text output ends a capped step with `... N more not followed (fanout cap)`. A
truncated flow is a prefix of the path: what lies past the cut is unknown, not
absent.

A call back to a step on the path that led to the current one is a cycle. It is
recorded in `cycles` as a `[from, to]` pair and not followed again; a cycle alone
does not truncate a flow. Steps that call nothing the walk can follow are listed in
`terminals`.

HEURISTIC steps, when enabled, are counted in `heuristic_steps` and marked `?` in
text output. Steps reached through an inferred link (basis `receiver`) are counted in
`inferred_steps`.

## In context, impact and changes

The other code-intelligence commands read the same flows:

- [`context`](context.md) lists the flows the symbol is a step in: the count, the
  five where it sits shallowest, and the flow it is the entry of (`as_entry`).
- [`impact`](impact.md) lists the flows with a step on the target or on any
  confident dependent, and how many pass through the target itself. Flows are
  reported next to the risk and never change it: the risk table counts dependents,
  and flows are built from the same links.
- [`changes`](changes.md) lists the flows that contain a changed symbol (or the old
  ID of a moved one) and adds `flows_touched` to the summary. These are the flows
  of the stored graph, normally built before the change; `changes --refresh` builds
  first and reports the flows of both graphs.

With `flows.enabled: false` the three commands leave flows out, and `build` does not
write `flows.json` (it removes an old one). `flows` and `flow` still work: they
compute the flows in memory.

## `flows.json`

`build` rewrites `.repo_wiki/generated/flows.json` on every run, from the complete
symbol graph, right after `symbol_graph.json`. It is a pure function of the graph,
the `flows` settings and the console scripts: the same inputs give the same bytes.
Keys are sorted and each flow is one compact line, which keeps the file small and
its diffs readable.

| Key | Content |
|---|---|
| `schema` | `repo-wiki/flows-file/v1` |
| `graph_sha256` | SHA-256 of the `symbol_graph.json` bytes the flows were derived from. |
| `inputs_sha256` | SHA-256 of the flow settings and the console scripts. |
| `settings` | The settings used: `cli_decorators`, `entries`, `include_heuristic`, `max_depth`, `max_fanout`, `max_flows`, `max_steps`. |
| `summary` | `flows`, `by_kind`, `steps` (total), `truncated` (flows), `omitted_flows` (by kind). |
| `flows` | One object per flow: `id`, `name`, `kind`, `entry`, `detail`, `aliases`, `path`, `start_line`, `end_line`, `steps`, `depth`, `terminals`, `cycles`, `truncated`, `truncated_reasons`, `heuristic_steps`, `inferred_steps`. |

A flow ID is `flow:` plus the first 12 hex digits of the SHA-256 of the entry's
node ID, so it stays the same across builds while the entry keeps its ID.

`max_flows` (default `1000`) bounds the file. Past it, flows are kept in the
priority order of their entry kind (console scripts, scripts, CLI commands, roots,
tests), the longest first within a kind; the rest are counted in
`summary.omitted_flows`. On the AKMS repository itself the file holds 163 flows in
about 0.9 MB, next to an 18 MB symbol graph.

### Staleness

A reader compares `graph_sha256` with the current graph file and `inputs_sha256`
with the current settings and console scripts. If either differs, or the file is
missing or unreadable, the flows are computed in memory from the graph instead.
Nothing is written: `flows` and `flow` print a note on stderr, and every JSON
payload reports `source: computed` with the `reason`. Rebuild to refresh the file.
The symbol graph itself is checked as for `context`: a stale graph exits 3 unless
`--allow-stale` is given.

## What a flow cannot see

A flow is the set of calls the graph can see from the entry, in breadth-first
order. It is not an execution trace and says nothing about the order of calls at run
time. Besides everything the graph misses (see
[Reading impact and risk](reading-impact.md#what-the-graph-cannot-see)):

- **callbacks passed as values**: `map(f, xs)`, `register(handler)`,
  `Thread(target=run)`; only `set_defaults(func=...)` is recognized, and only as an
  entry point;
- **dynamic dispatch**: a method called on a parameter or attribute is a HEURISTIC
  link at best, so the walk stops there by default;
- **string-based imports and other entry-point groups**:
  `importlib.import_module(name)`, plugin discovery, and packaging entry points
  other than scripts.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. |
| 2 | Usage error, such as `--limit -1`. |
| 3 | The symbol graph is missing, unreadable or stale. The message gives the rebuild command. |
| 4 | Unknown or ambiguous flow (`unknown_flow`, `ambiguous_flow`) or `--touching` symbol. A symbol that is a step but not an entry is `unknown_flow`; the message suggests `flows --touching`. |

With `--json`, a failure also prints a `repo-wiki/error/v1` object on stdout.
