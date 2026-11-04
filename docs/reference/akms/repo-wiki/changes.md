# changes

`repo-wiki changes` maps a git diff to the symbols whose line ranges it touches
and lists each symbol's direct callers. Run it before you commit, to confirm the
change touches only what you meant and that nothing still calls a symbol you
removed.

```bash
repo-wiki changes
```

```text
Changes (worktree vs HEAD, a0fa1a8b16f4): 1 file(s), 2 changed symbol(s)
  modified python:pkg/core.py::leaf  pkg/core.py:L4-L6
      d=1 callers: 3 confident, 0 possible
        python:pkg/core.py::Store._write  pkg/core.py:L19-L20  [CONFIDENT local]
        python:pkg/service.py::via_module  pkg/service.py:L16-L17  [CONFIDENT import]
        python:tests/test_core.py::test_leaf  tests/test_core.py:L4-L5  [CONFIDENT import] (test)
  deleted  python:pkg/core.py::middle  pkg/core.py:L9-L10
      d=1 callers: 1 confident, 1 possible
        python:pkg/service.py::run  pkg/service.py:L7-L8  [CONFIDENT dangling]
        ? python:other/helpers.py::stray  other/helpers.py:L13-L14  [HEURISTIC dangling]
Summary: 2 changed symbol(s) (1 deleted, 1 modified); affected callers: 4 confident, 1 possible; risk HIGH (counting possible links: HIGH)
  3 direct non-test dependent(s); 1 other module(s); 1 caller(s) still reference a deleted or moved symbol
```

## Flags

| Flag | Meaning |
|---|---|
| `--worktree` | The default. The worktree, staged and unstaged, plus untracked files that git does not ignore, against `HEAD`. |
| `--staged` | The index against `HEAD`: what `git commit` would record. The new side of each file is read from the index, not the worktree. |
| `--base REF` | The worktree, plus untracked files, against the merge base of `REF` and `HEAD`: everything your branch changed. |
| `--json` | Print a `repo-wiki/changes/v1` object instead of text. |
| `--allow-stale` | Use the graph even when files outside the diff changed since it was built. |

The three modes are mutually exclusive. In a repository without commits the base
is the empty tree.

## How changes become symbols

1. git lists the changed files (renames detected) and the `-U0` hunks with their
   old and new line ranges. Paths under `.repo_wiki/` are ignored.
2. Each changed file is parsed with the extractor `build` uses: the new side from
   the worktree (or the index for `--staged`), the old side from the base
   revision. A Python symbol's range is extended upward over its decorators.
3. Every changed line is assigned to the innermost symbol that contains it. Lines
   on the new side give `added` and `modified` symbols; lines on the old side give
   `modified` and `deleted` ones, with the base revision's line numbers. Symbols are
   matched across the two sides by qualname.
4. In a renamed file every symbol gets a new ID. Symbols the hunks did not touch
   are reported as `moved`, with `old_id`.
5. Non-blank, non-comment lines outside every symbol (imports, module-level
   statements) are listed under `module_level_changes`.

Callers come from the symbol graph with the new side of every changed file swapped
in, so a call added in this change is seen without a rebuild, and callers reflect
the tree being committed whether the graph was built before or after the edits.

For a `deleted` or `moved` symbol, the callers are the code that still names it.
They carry the basis `dangling`: confident when the caller imports the old path or
calls the name in the same file, possible when only the name matches. Any
confident dangling caller raises the risk to at least HIGH.

A caller that is itself part of the change is marked `changed` and is not counted
among the affected callers. The summary risk applies the
[impact risk rule](reading-impact.md#risk) to the union of the remaining direct
callers.

### What is not mapped

| File | Reported as |
|---|---|
| No extractor (Markdown, YAML, ...) or a language that is not enabled | `symbols_supported: false` |
| Does not parse, on either side | `parse_error` with the first error; no symbols |
| Binary | `binary: true` |

## Staleness

The files in the diff, and any file with uncommitted changes, are expected to
differ from the graph and are not checked. Any other source that differs from
what the graph was built from, for example after a `git pull` without a rebuild,
makes the command exit 3. Rebuild with
`repo-wiki build --changed-only --no-summaries --no-index`.

## JSON

```json
{
  "schema": "repo-wiki/changes/v1",
  "mode": "worktree", "base": null, "base_commit": "a0fa1a8b...",
  "files": [{"path": "pkg/core.py", "old_path": null, "status": "modified",
             "binary": false, "symbols_supported": true, "parse_error": null,
             "hunks": [{"old_start": 6, "old_lines": 1, "new_start": 6, "new_lines": 1}]}],
  "changed_symbols": [
    {"id": "python:pkg/core.py::middle", "old_id": null, "status": "deleted",
     "kind": "function", "name": "middle", "qualname": "middle",
     "path": "pkg/core.py", "start_line": 9, "end_line": 10,
     "is_test": false, "public_entry": null,
     "callers": {"confident": [{"id": "python:pkg/service.py::run", "changed": false,
                                "edge": {"type": "calls", "resolution": "CONFIDENT",
                                         "basis": "dangling", "name": "middle"},
                                "...": "..."}],
                 "possible": [...]}}
  ],
  "module_level_changes": [],
  "summary": {"files": 1, "changed_symbols": 2,
              "by_status": {"deleted": 1, "modified": 1},
              "affected_callers": {"confident": 4, "possible": 1},
              "dangling_references": 1, "modules_reached": 1,
              "public_entry_points": [], "risk": "HIGH", "risk_with_possible": "HIGH",
              "risk_reasons": ["..."]},
  "graph": {"path": "...", "built_commit": "...", "stale": false,
            "changed": [], "added": [], "removed": []}
}
```

File `status` is `added`, `modified`, `deleted` or `renamed`. Symbol `status` is
`added`, `modified`, `deleted` or `moved`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success, whatever the risk level. |
| 1 | git failed: not a work tree, or an unknown `--base` ref. |
| 3 | The symbol graph is missing, unreadable, or stale outside the diff. |
