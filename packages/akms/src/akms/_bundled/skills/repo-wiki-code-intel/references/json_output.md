# JSON output

Every payload carries a `schema` string. New keys may be added within a schema
version; existing keys keep their meaning and type. Read the keys you need and
ignore the rest.

## Shared shapes

A **node** (symbol or module):

```json
{
  "id": "python:pkg/core.py::leaf",
  "kind": "function",
  "name": "leaf",
  "qualname": "leaf",
  "path": "pkg/core.py",
  "start_line": 4,
  "end_line": 6,
  "module": "pkg.core",
  "is_test": false,
  "public_entry": null
}
```

`kind` is `function`, `method`, `class`, `constant` or `module`. `public_entry` is
`"cli"`, `"export"` or `null`.

A **link** is a node plus the edge that reached it:

```json
"edge": {"type": "calls", "resolution": "CONFIDENT", "basis": "import", "name": "leaf",
         "provenance": "static"}
```

`type` is `calls`, `inherits` or `imports`. `resolution` is `CONFIDENT` or
`HEURISTIC`. `name` is the name as written at the call site. A HEURISTIC edge with
more than one possible target adds `"candidates": [...]`. `provenance` says where the
link comes from: `static` (a call written in the source), `inferred` (derived from a
pattern: a local variable's constructor, a dispatch table) or `observed` (reserved for
links seen at run time; nothing produces it yet).

Links always come in two lists: `{"confident": [...], "possible": [...]}`.

## `repo-wiki/context/v1`

| Key | Value |
|---|---|
| `symbol` | node plus `signature`, `docstring` (first line), `dotted_name`, `parent` |
| `callers`, `callees` | confident / possible links |
| `bases`, `subclasses` | confident / possible links over `inherits` edges |
| `members` | IDs of nested symbols (methods of a class) |
| `unresolved_calls` | call names that match nothing in the repository |
| `external_calls` | call names into modules outside the repository |
| `module` | `id`, `path`, `imports` (repository modules), `external_imports`, `importers` |
| `resolution_counts` | `callers`: CONFIDENT/HEURISTIC; `callees`: also UNRESOLVED/EXTERNAL |
| `graph` | `path`, `built_commit`, `stale`, `changed`, `added`, `removed` |

## `repo-wiki/impact/v1`

| Key | Value |
|---|---|
| `target` | node |
| `direction`, `depth`, `include_tests` | the request |
| `levels` | one entry per depth: `depth`, `label`, `confident`, `possible` |
| `affected_files`, `affected_test_files` | files of confident dependents |
| `possible_files` | files reached only through possible links |
| `summary` | `confident`, `possible`, `risk`, `risk_with_possible`, `d1_confident`, `modules_reached`, `public_entry_points`, `risk_reasons` |
| `graph` | as for `context` |

Entries in `levels` are links plus `depth` and `via` (the node one step closer to the
target). Downstream walks set `risk` and `risk_with_possible` to `null`.

## `repo-wiki/changes/v1`

| Key | Value |
|---|---|
| `mode` | `worktree`, `staged` or `base` |
| `base`, `base_commit` | the `--base` ref and the commit compared against |
| `files` | `path`, `old_path`, `status` (`added`/`modified`/`deleted`/`renamed`), `binary`, `hunks` (`old_start`, `old_lines`, `new_start`, `new_lines`), `symbols_supported`, `parse_error` |
| `changed_symbols` | node fields plus `old_id`, `status` (`added`/`modified`/`deleted`/`moved`), `callers` |
| `module_level_changes` | `path` and `lines` (`[start, end]` ranges) outside every symbol |
| `summary` | `files`, `changed_symbols`, `by_status`, `affected_callers` (`confident`, `possible`), `dangling_references`, `modules_reached`, `public_entry_points`, `risk`, `risk_with_possible`, `risk_reasons` |
| `graph` | as for `context` |

Callers in `changed_symbols` are links plus `changed` (true when the caller is itself
part of the change). A caller of a deleted or moved symbol has basis `dangling`.

## `repo-wiki/error/v1`

```json
{"schema": "repo-wiki/error/v1",
 "error": {"code": "ambiguous_symbol", "message": "...", "candidates": [...]}}
```

`code` is one of `graph_missing`, `graph_unreadable`, `graph_stale` (with `details`:
`rebuild`, `changed`, `added`, `removed`), `unknown_symbol`, `ambiguous_symbol`
(with `candidates`: nodes), `git_error`, `usage`.
