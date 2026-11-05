# context

`repo-wiki context SYMBOL` shows one symbol from every side: where it is defined,
who calls it, what it calls, what its module imports and who imports that module.
It reads the symbol graph that [`build`](index.md#subcommands) writes and changes
nothing.

```bash
repo-wiki context Store.save
```

```text
python:pkg/core.py::Store.save  (method)
  pkg/core.py:L20-L21
  def save(self, item)
Callers: 0 confident, 1 possible
  ? python:pkg/service.py::persist  pkg/service.py:L11-L13  [HEURISTIC attribute, 1 of 2 candidates]
Callees: 1 confident, 0 possible
  python:pkg/core.py::Store._write  pkg/core.py:L23-L24  [CONFIDENT self]
Module pkg.core: imports 0 repository module(s) and 0 external name(s); imported by 2
  imported by pkg.service
  imported by tests.test_core
```

Lines marked `?` are possible links, not facts. See
[Reading impact and risk](reading-impact.md#confident-and-possible-links).

## Flags

| Flag | Default | Meaning |
|---|---|---|
| `SYMBOL` | required | The symbol or module to show. See [Naming a symbol](#naming-a-symbol). |
| `--json` | off | Print a `repo-wiki/context/v1` object instead of text. |
| `--allow-stale` | off | Use the graph even when sources changed since it was built. |

## Naming a symbol

`SYMBOL` is matched in this order, and the first step with any match wins:

1. the exact node ID, such as `python:pkg/core.py::Store.save`;
2. `path::qualname` without the language prefix, such as `pkg/core.py::Store.save`;
3. a dotted import path, such as `pkg.core.Store.save` or a module, `pkg.core`;
4. a qualname, such as `Store.save`;
5. a bare name, such as `save`;
6. a dotted suffix of `<module>.<qualname>`, such as `core.Store.save`.

When a step matches more than one symbol, the command does not guess. It exits
with code 4 and lists the candidates:

```text
$ repo-wiki context parse
repo-wiki context: 'parse' matches 2 symbols; pass one of the IDs listed
  other/helpers.py:L4-L5  python:other/helpers.py::parse
  pkg/core.py:L13-L14  python:pkg/core.py::parse
```

## What it reports

| Section | Content |
|---|---|
| Definition | Kind, file and lines, the signature and the first docstring line (parsed from the file now), the dotted import name and the parent symbol. |
| Callers, callees | Direct calls in each direction, split into confident and possible links. A call of a class also reaches its `__init__`. |
| Bases, subclasses | `inherits` edges, for classes. |
| Members | Methods and nested symbols. |
| Unresolved and external calls | Call names that match nothing in the repository, and calls into modules outside it (`json.dumps`). |
| Module | The repository modules its module imports, the external imports, and the modules that import it. |
| Resolution counts | How many links of each kind were found. |

## JSON

```json
{
  "schema": "repo-wiki/context/v1",
  "symbol": {"id": "...", "kind": "method", "path": "pkg/core.py", "start_line": 20,
             "end_line": 21, "signature": "def save(self, item)", "docstring": null,
             "dotted_name": "pkg.core.Store.save", "parent": "python:pkg/core.py::Store",
             "...": "..."},
  "callers": {"confident": [], "possible": [{"id": "...", "edge": {...}}]},
  "callees": {"confident": [...], "possible": []},
  "bases": {...}, "subclasses": {...}, "members": [],
  "unresolved_calls": [], "external_calls": [],
  "module": {"id": "pkg.core", "path": "pkg/core.py", "imports": [],
             "external_imports": [], "importers": ["pkg.service", "tests.test_core"]},
  "resolution_counts": {"callers": {"CONFIDENT": 0, "HEURISTIC": 1},
                        "callees": {"CONFIDENT": 1, "HEURISTIC": 0,
                                    "UNRESOLVED": 0, "EXTERNAL": 0}},
  "graph": {"path": ".repo_wiki/generated/symbol_graph.json", "built_commit": "...",
            "stale": false, "changed": [], "added": [], "removed": []}
}
```

Each link carries the node fields (`id`, `kind`, `name`, `qualname`, `path`,
`start_line`, `end_line`, `module`, `is_test`, `public_entry`) and an `edge`:
`type`, `resolution`, `basis`, `name`, and `candidates` when a possible link has
several targets. New keys may be added within `v1`; existing ones keep their
meaning.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. |
| 3 | The symbol graph is missing, unreadable or stale. The message gives the rebuild command. |
| 4 | The symbol is unknown or ambiguous. |

With `--json`, a failure also prints a `repo-wiki/error/v1` object on stdout:
`{"schema": "repo-wiki/error/v1", "error": {"code": ..., "message": ...}}`, with
`candidates` for an ambiguous name and `details` for a stale graph.
