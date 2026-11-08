# Reading impact and risk

[`context`](context.md), [`impact`](impact.md) and [`changes`](changes.md) all report
dependencies found in the symbol graph. This page explains what a reported link
means, how depth and risk are computed, and what the graph cannot see.

## Depth

`impact` walks outward from the target, one edge at a time. Upstream, each depth
has a label that says what to do with it:

| Depth | Label | Meaning |
|---|---|---|
| d=1 | will break | Calls or subclasses the target directly. If the target's contract changes, these change too. |
| d=2 | likely affected | Depends on a d=1 dependent. Affected when the change is visible through it. |
| d=3 | may need testing | Further out. Worth running their tests on important paths. |

Downstream, the labels are `direct dependency`, `indirect dependency` and
`transitive dependency`. Depths beyond 3 reuse the depth-3 label.

A dependent appears once, at the shallowest depth any path reaches it.

## Confident and possible links

The build records each call by name. The commands resolve every name the way
Python looks it up, using only what the graph records, and label the result:

| Resolution | Basis | Evidence |
|---|---|---|
| CONFIDENT | `local` | A definition in the caller's own module. |
| CONFIDENT | `import` | The caller's module imports the name: at module or function level, under an `as` alias, or through a package `__init__` that re-exports it. |
| CONFIDENT | `scope` | A function nested in an enclosing function of the caller. |
| CONFIDENT | `self` | `self.m()` or `cls.m()`, found on the enclosing class or a confidently resolved base class. |
| CONFIDENT | `constructor` | A call of class `C`, which also reaches `C.__init__`. |
| CONFIDENT | `receiver` | `x.m()` where the caller (or an enclosing function) binds `x = C(...)`, annotates `x: C`, or takes a parameter `x: C` (also `Optional[C]`, `C \| None`, `"C"`); or `self.x.m()` / `cls.x.m()` where the class or a base binds `x` with a class-level `x: C` or `x = C(...)`, or in `__init__` with `self.x = C(...)`, `self.x: C = ...` or `self.x = param` for a parameter `param: C`. Every bound name must be a repository class and exactly one method `m` must be found on them or their bases. Provenance `inferred`. |
| CONFIDENT | `name` | Rust, C++ and Julia: exactly one symbol in the repository has the name. |
| HEURISTIC | `name` | The name matches a top-level definition, but nothing imports or defines it where it is called. |
| HEURISTIC | `attribute` | `obj.m()` on a receiver whose type is unknown, linked to the methods named `m`. Only when there are at most four such methods, and never for method names of built-in types or `pathlib.Path` (`append`, `get`, `exists`, ...). |
| HEURISTIC | `receiver` | As above, but `x` is bound to several classes, or also to something that is not a repository class: one link per method found. Provenance `inferred`. |
| HEURISTIC | `dispatch` | The caller indexes (`T[key]`, `T.get(key)`) a module-level dict literal with literal keys whose values are all functions or classes defined or imported in that module (at least two entries). One link per value; never CONFIDENT. Provenance `inferred`. |
| CONFIDENT or HEURISTIC | `dangling` | `changes` only: code that still names a deleted or moved symbol. |

CONFIDENT links are counted. HEURISTIC links are reported apart, as *possible*:
in the `possible` lists of the JSON output and with a leading `?` in text. They
never feed the risk level. When a possible link has several targets, `candidates`
lists all of them, and the call usually reaches only one.

Calls into modules outside the repository (`json.dumps`, `Path.read_text` on a
`pathlib` import) produce no link. `context` lists them as external calls. So does a
method call on a local bound only to outside classes
(`parser = argparse.ArgumentParser()`, then `parser.add_argument(...)`).

Every link also carries a `provenance` in the JSON output: `static` for a call
written in the source, `inferred` for `receiver` and `dispatch` links, and `observed`,
reserved for links seen at run time (nothing produces it yet). The graph file writes
the field only when it is not `static`; see
[Generated files](generated-files.md#symbol-graph-fields).

Python resolution is finer than the graph file's own `resolution` field, which
matches names across the whole repository. A bare call of a name the module never
imports is CONFIDENT in the graph file when only one symbol has that name, but
HEURISTIC here.

## Risk

Risk is computed from confident links only, and test code never counts:

- **d1**: the number of non-test dependents at depth 1;
- **modules**: the number of distinct modules, other than the target's own, among
  all non-test confident dependents up to the requested depth;
- **public entry points**: whether the target or a dependent is in a CLI module
  (`cli.py`, `__main__.py`, a `cli/` package) or is a public name that a package
  `__init__.py` defines or re-exports from its own subpackages.

The level is the first row where *either* count reaches its minimum:

| Level | Minimum d1 | Minimum modules |
|---|---|---|
| CRITICAL | 25 | 12 |
| HIGH | 10 | 6 |
| MEDIUM | 3 | 3 |
| LOW | below that | below that |

Reaching a public entry point raises the level one step, but never above HIGH: only
the counts make a change CRITICAL. The table lives in one constant,
`akms.repo_wiki.impact.RISK_THRESHOLDS`, with the cap in `PUBLIC_ENTRY_CAP`.

`risk_with_possible` applies the same rule as if every possible link were real.
When it is higher than `risk`, the possible links deserve a look.

`changes` applies the rule to the union of the direct callers of every changed
symbol, leaving out callers that are part of the change, and raises the level to at
least HIGH when a confident caller still names a deleted or moved symbol.

As a calibration point: on the AKMS repository itself, at the default depth, about
62% of non-test symbols come out LOW, 21% MEDIUM, 16% HIGH and 1% CRITICAL.

## Freshness

The graph records a content hash for every source it was built from. Before
answering, `context` and `impact` compare those hashes with the tree, hashing only
files modified after the graph was written, and look for new or deleted sources.
Any difference is an error (exit 3) that names the files and gives the rebuild
command:

```bash
repo-wiki build --changed-only --no-summaries --no-index
```

`--allow-stale` skips the check and reports `"stale": true` in the JSON `graph`
block. `changes` skips the files in its diff, which it parses itself.

## What the graph cannot see

The graph comes from parsing source, without running it. Its only type inference
is the `receiver` rule above. These are missed, or found only as possible links:

- calls through dynamic dispatch: a method called on an unannotated parameter, an
  attribute bound anywhere but the class body or `__init__`, a chain such as
  `self.a.b.m()` or `make().m()`, and overrides in subclasses;
- reflection and indirection: `getattr`, registries filled at run time, callbacks
  passed as values, decorators that replace a function (a literal dict of callables
  gives only possible `dispatch` links);
- string-based imports: `importlib.import_module`, packaging entry points, plugin
  discovery;
- references that are not calls: reading a constant, passing a function without
  calling it, `isinstance` checks, annotations;
- `super().method()` and calls on the result of another call;
- module-level code, such as calls made at import time;
- files the scanner skips, and languages not enabled in the
  [configuration](configuration.md).

A LOW risk or an empty level means no dependents the graph can see. For public
API, plugin hooks and anything called by name from configuration, search for the
name as well.
