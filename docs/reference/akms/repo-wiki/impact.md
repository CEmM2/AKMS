# impact

`repo-wiki impact SYMBOL` walks the symbol graph from one symbol and lists what
depends on it, grouped by depth, with a risk level. Run it before you edit a
function, class or method.

```bash
repo-wiki impact leaf
```

```text
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
d=3 may need testing: 2 confident, 1 possible
    python:pkg/api.py::public_entry  pkg/api.py:L6-L8  [CONFIDENT import] (public:export)
    python:pkg/service.py::persist  pkg/service.py:L11-L13  [CONFIDENT receiver]
    ? python:pkg/service.py::persist_any  pkg/service.py:L20-L22  [HEURISTIC attribute, 1 of 2 candidates]
Affected files: 3
  pkg/api.py
  pkg/core.py
  pkg/service.py
Affected test files: 1
  tests/test_core.py
Possibly affected files: 1
  other/helpers.py
Risk: HIGH (counting possible links: HIGH) - 3 direct non-test dependent(s); 2 other module(s); public entry point(s) reached: 1
Affected flows: 3 (3 through the target; not part of the risk)
  pkg.service.via_module  [root; 2 steps; depth 1]  at d=1  flow:81e076513602
  pkg.service.persist  [root; 5 steps; depth 3]  at d=3  flow:0bc38b6af8b6
  pkg.cli.main  [root; 5 steps; depth 4]  at d=4  flow:67984a14e9db
```

The last block lists the [execution flows](flows.md) with a step on the target or on
a confident dependent, ordered by the target's depth in them. It is context for the
change, not an input to the risk: flows are built from the same links the risk
already counts.

[Reading impact and risk](reading-impact.md) explains the depths, the two kinds of
link and how the risk level is chosen.

## Flags

| Flag | Default | Meaning |
|---|---|---|
| `SYMBOL` | required | Named as for [`context`](context.md#naming-a-symbol). An ambiguous name exits 4 with the candidates. |
| `--direction {upstream,downstream}` | `upstream` | `upstream`: who depends on `SYMBOL`. `downstream`: what `SYMBOL` depends on. |
| `--depth N` | `3` | How many levels to walk. Must be at least 1. |
| `--include-tests` | on | List test code among the results. Tests never raise the risk. |
| `--exclude-tests` | off | Leave test code out of the walk entirely. |
| `--json` | off | Print a `repo-wiki/impact/v1` object instead of text. |
| `--allow-stale` | off | Use the graph even when sources changed since it was built. |

For a symbol the walk follows `calls` and `inherits` edges. For a module (for
example `repo-wiki impact pkg.core`) it follows `imports` edges, so the levels list
importing modules.

A test file is one under a `tests/` or `test/` directory, or named `test_*.py`,
`*_test.py` or `conftest.py`.

## JSON

```json
{
  "schema": "repo-wiki/impact/v1",
  "target": {"id": "python:pkg/core.py::leaf", "kind": "function", "...": "..."},
  "direction": "upstream", "depth": 3, "include_tests": true,
  "levels": [
    {"depth": 1, "label": "will break",
     "confident": [{"id": "python:pkg/core.py::middle", "depth": 1,
                    "via": "python:pkg/core.py::leaf",
                    "edge": {"type": "calls", "resolution": "CONFIDENT",
                             "basis": "local", "name": "leaf",
                             "provenance": "static"}, "...": "..."}],
     "possible": []},
    {"depth": 2, "label": "likely affected", "confident": [...], "possible": [...]},
    {"depth": 3, "label": "may need testing", "confident": [...], "possible": [...]}
  ],
  "affected_files": ["pkg/api.py", "pkg/core.py", "pkg/service.py"],
  "affected_test_files": ["tests/test_core.py"],
  "possible_files": ["other/helpers.py"],
  "summary": {"confident": 8, "possible": 2, "d1_confident": 3, "modules_reached": 2,
              "public_entry_points": ["python:pkg/api.py::public_entry"],
              "risk": "HIGH", "risk_with_possible": "HIGH",
              "risk_reasons": ["3 direct non-test dependent(s)", "2 other module(s)",
                               "public entry point(s) reached: 1"]},
  "graph": {"path": "...", "built_commit": "...", "stale": false,
            "changed": [], "added": [], "removed": []},
  "flows": {"count": 3, "through_target": 3, "source": "file", "reason": null,
            "flows": [{"id": "flow:81e076513602", "name": "pkg.service.via_module",
                       "matched": [{"id": "python:pkg/core.py::leaf", "depth": 1},
                                   {"id": "python:pkg/service.py::via_module",
                                    "depth": 0}],
                       "...": "..."}]}
}
```

`via` is the node one step closer to the target, so the path back can be
reconstructed. A dependent appears once, at the shallowest depth it is reached.
Downstream walks report `risk` and `risk_with_possible` as `null`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success, whatever the risk level. |
| 2 | Usage error, such as `--depth 0`. |
| 3 | The symbol graph is missing, unreadable or stale. |
| 4 | The symbol is unknown or ambiguous. |
