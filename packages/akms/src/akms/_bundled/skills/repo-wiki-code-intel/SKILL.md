---
name: repo-wiki-code-intel
description: "Check who depends on code before changing it, using the repo-wiki CLI that ships with akms. Run `repo-wiki context` to explore a symbol (definition, callers, callees, module imports), `repo-wiki impact` before editing any function, class or method (dependents grouped by depth, with a LOW/MEDIUM/HIGH/CRITICAL risk), and `repo-wiki changes` before committing (the symbols your diff touches and their direct callers). Use when exploring unfamiliar code, before editing a symbol, before a commit, or when asked what breaks if something changes. Triggers on: 'impact analysis', 'blast radius', 'who calls', 'what calls', 'callers of', 'what breaks if', 'is it safe to change', 'before committing', 'detect changes', 'symbol context'."
---

# Code intelligence with repo-wiki

`repo-wiki` builds a symbol graph of the repository (functions, classes, methods,
constants, modules and the calls, inheritance and imports between them). Three
commands read it. They are local, deterministic, make no network calls and call no
model.

| Command | Run it | It answers |
|---|---|---|
| `repo-wiki context SYMBOL` | when exploring | Where is it defined, who calls it, what does it call, what does its module import? |
| `repo-wiki impact SYMBOL` | **before editing** any function, class or method | Who depends on it, at depth 1, 2 and 3, and how risky is a change? |
| `repo-wiki changes` | **before committing** | Which symbols does my diff touch, and who calls them? |

Add `--json` to any of them for machine-readable output
(see [references/json_output.md](references/json_output.md)). Put `--repo-root PATH`
before the subcommand when you are not in the repository root.

## 0. Make sure the graph exists and is fresh

```bash
repo-wiki build --changed-only --no-summaries --no-index
```

That is the fastest refresh: it re-parses only changed files and rewrites
`.repo_wiki/generated/symbol_graph.json`. Run it at the start of a session and after
pulling or switching branches.

`context` and `impact` refuse a stale graph. If any source file differs from what the
graph was built from, they exit with code 3 and a message that names the files and
gives the rebuild command. Rebuild and rerun. `--allow-stale` exists, but its answers
can be wrong for exactly the files you changed, so use it only when you understand
which files are stale and they do not matter to the question.

`changes` is different: the files in your diff are *expected* to differ, so it
re-parses them itself and overlays them on the graph. It still fails if files
**outside** the diff are stale (for example after a `git pull` without a rebuild).

## 1. Explore: `context`

```bash
repo-wiki context build_repo
repo-wiki context pkg.core.Store.save      # dotted import path
repo-wiki context "Store.save"             # qualname
repo-wiki context python:pkg/core.py::Store.save   # exact ID
```

A symbol can be named by its exact ID, `path::qualname`, its dotted import path, its
qualname, or its bare name. If the name matches more than one symbol the command
exits with code 4 and lists every candidate ID. Pick one and rerun with that ID;
never guess.

## 2. Before editing: `impact`

Run this before you change the body, signature or behaviour of any function, class or
method:

```bash
repo-wiki impact SYMBOL                       # upstream, depth 3 (the default)
repo-wiki impact SYMBOL --exclude-tests       # leave test code out of the walk
repo-wiki impact SYMBOL --direction downstream   # what SYMBOL depends on
repo-wiki impact SYMBOL --depth 5
```

Upstream results are grouped by depth:

| Depth | Label | What to do |
|---|---|---|
| d=1 | will break | These call it directly. Each one must still work after your change: update it or confirm it is unaffected. |
| d=2 | likely affected | Callers of the callers. Check the ones whose behaviour depends on what you change. |
| d=3 | may need testing | Run their tests if the path is important. |

Then report to the user, before you edit:

1. the d=1 dependents (name and file),
2. the counts at d=2 and d=3,
3. the risk level and its reasons,
4. any possible (HEURISTIC) links worth a look.

**If the risk is HIGH or CRITICAL, say so plainly and wait for the user to confirm
before editing.** Do not soften it.

Risk is computed from confident links only and test code never counts:

| Level | When (either count reaches the minimum) |
|---|---|
| CRITICAL | 25+ direct non-test dependents, or 12+ other modules reached |
| HIGH | 10+ direct dependents, or 6+ other modules |
| MEDIUM | 3+ direct dependents, or 3+ other modules |
| LOW | below that |

Reaching a public entry point (a CLI module, or a name a package `__init__` defines or
re-exports, including the target itself) raises the level one step, but never to
CRITICAL on its own. `risk_with_possible` is the level the same rule gives if every
possible link were real; if it is higher than `risk`, mention it.

## 3. Before committing: `changes`

```bash
repo-wiki changes                 # worktree + untracked files vs HEAD (default)
repo-wiki changes --staged        # exactly what `git commit` would record
repo-wiki changes --base main     # everything since the merge base with main
```

It maps every diff hunk to the innermost symbol whose line range it overlaps and
classifies each as `added`, `modified`, `deleted` or `moved` (a symbol whose ID
changed because its file was renamed). For each one it lists the direct (d=1)
callers. Callers you edited in the same change are marked `changed` and are not
counted as affected.

Check, before you commit:

- **Only the symbols you meant to change appear.** An unexpected symbol means an
  unintended edit: look at it before committing.
- **No `deleted` or `moved` symbol has confident callers.** Those are marked with
  basis `dangling`: code that still refers to something that no longer exists. They
  force the risk to at least HIGH. Fix the callers or keep the old name.
- The summary risk follows the same table as `impact`, over the union of direct
  callers. Report HIGH or CRITICAL to the user.

Changes outside any symbol (imports, module-level statements) are listed under
`module_level_changes`; files with no extractor (Markdown, YAML, ...) are listed with
`symbols_supported: false`; a file that does not parse is listed with its
`parse_error` and contributes no symbols, so fix the syntax and rerun.

## Reading the links: CONFIDENT and HEURISTIC

Every caller, callee and dependent carries the edge that produced it:
`resolution` and `basis`.

| Resolution | Basis | Meaning |
|---|---|---|
| CONFIDENT | `local` | a definition in the caller's own module |
| CONFIDENT | `import` | the caller's module imports the name (module- or function-level, aliases, re-exports through a package `__init__`) |
| CONFIDENT | `scope` | a function nested in an enclosing function |
| CONFIDENT | `self` | `self.m()` / `cls.m()` found on the enclosing class or a resolved base class |
| CONFIDENT | `constructor` | a call of class `C` also reaches `C.__init__` |
| CONFIDENT | `name` | Rust, C++ and Julia only: exactly one symbol in the repository has that name |
| HEURISTIC | `name` | the name matches, but nothing imports or defines it where it is called (a star import, a parameter holding a callable, a builtin with the same name) |
| HEURISTIC | `attribute` | `obj.m()` on a receiver of unknown type, linked to the methods named `m` (at most 4 candidates; `candidates` lists them) |

Count CONFIDENT links as fact. Treat HEURISTIC links as *possible*: they are listed
separately (`possible`, marked `?` in text output), never feed the risk level, and
must not be reported as certain. Open the caller and check when it matters. A
HEURISTIC `attribute` link with several candidates usually reaches only one of them.

## What the graph cannot know

The graph is built from source text, without running anything and without type
inference. It misses, or gets only as a possible link:

- **dynamic dispatch**: a method called on an object whose type is not visible at the
  call site (`repo.save()` when `repo` is a parameter) is at best a HEURISTIC
  `attribute` link; overrides in subclasses are not callers of the base method;
- **reflection and indirection**: `getattr(obj, name)()`, registries and dispatch
  tables, callbacks passed as values, decorators that replace a function;
- **string-based imports**: `importlib.import_module("pkg.mod")`, entry points declared
  in packaging metadata, plugin discovery;
- **a function-level import under another name**: `from pkg.cli import main as run_cli`
  inside a function; the `as` name is not recorded, so `run_cli()` is not linked
  (module-level aliases are);
- **references that are not calls**: reading a constant, passing a function without
  calling it, `isinstance` checks, type annotations;
- **`super().method()`** and calls on the result of another call (`make().run()`);
- **module-level code**: calls made at import time or under `if __name__ == "__main__":`
  are not attributed to any symbol;
- **files the scanner skips**: excluded or ignored paths, files over the size limit,
  and languages not enabled in `.repo_wiki/config.yaml`.

So an empty or LOW result means "no dependents the graph can see", not "safe". For
public API, plugin hooks, or anything called by name from configuration, search the
repository for the name as well.

## Worked example

From a small repository where `pkg/core.py` defines `leaf` and `middle`, `pkg/service.py`
imports them, `pkg/api.py` exports `public_entry`, and `other/helpers.py` calls
`middle` without importing it:

```text
$ repo-wiki impact leaf
Impact of python:pkg/core.py::leaf (function) pkg/core.py:L4-L6 - upstream, depth 3
d=1 will break: 4 confident, 0 possible
    python:pkg/core.py::Store._write  pkg/core.py:L23-L24  [CONFIDENT local]
    python:pkg/core.py::middle  pkg/core.py:L9-L10  [CONFIDENT local]
    python:pkg/service.py::via_module  pkg/service.py:L16-L17  [CONFIDENT import]
    python:tests/test_core.py::test_leaf  tests/test_core.py:L4-L5  [CONFIDENT import] (test)
d=2 likely affected: 2 confident, 1 possible
    python:pkg/core.py::Store.save  pkg/core.py:L20-L21  [CONFIDENT self]
    python:pkg/service.py::run  pkg/service.py:L7-L8  [CONFIDENT import]
    ? python:other/helpers.py::stray  other/helpers.py:L13-L14  [HEURISTIC name]
d=3 may need testing: 1 confident, 1 possible
    python:pkg/api.py::public_entry  pkg/api.py:L6-L8  [CONFIDENT import] (public:export)
    ? python:pkg/service.py::persist  pkg/service.py:L11-L13  [HEURISTIC attribute, 1 of 2 candidates]
Affected files: 3
  pkg/api.py
  pkg/core.py
  pkg/service.py
Affected test files: 1
  tests/test_core.py
Possibly affected files: 1
  other/helpers.py
Risk: HIGH (counting possible links: HIGH) - 3 direct non-test dependent(s); 2 other module(s); public entry point(s) reached: 1
```

What to tell the user before editing `leaf`: three production callers break if its
contract changes (`Store._write`, `middle`, `via_module`), plus `test_leaf`; two more
at d=2 and the exported `public_entry` at d=3; risk HIGH because a public entry point
is reached, so wait for confirmation. `stray` and `persist` are only possible links:
`stray` calls a name it never imports, and `persist` calls `.save()` on a value whose
type the graph cannot see.

After changing `leaf`'s body and deleting `middle`:

```text
$ repo-wiki changes
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

`run` still imports the deleted `middle`, so this commit would break it: fix `run`
before committing.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success (a HIGH risk is still exit 0: read the summary) |
| 1 | git failure (not a work tree, unknown `--base` ref) |
| 2 | usage error |
| 3 | symbol graph missing, unreadable or stale: run the rebuild command it prints |
| 4 | symbol unknown or ambiguous: the candidates are listed |

With `--json`, a failure also prints a `repo-wiki/error/v1` object on stdout.
