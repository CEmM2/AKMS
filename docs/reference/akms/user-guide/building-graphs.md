# Build and load graphs

## Inputs

`build_graph()` reads, in order:

1. Global Markdown nodes from the resolved vault
2. Local Markdown nodes from `knowledge/local-nodes/`
3. Code-mirror Markdown nodes from `knowledge/code-mirror/`
4. The optional overlay `knowledge/graph/local_state.yaml`

It validates each artifact against the frozen v2 schemas and writes
`knowledge/graph/graph.json` unless another output path is supplied.

## Python API

```python
from pathlib import Path
from akms.graph.build_graph import build_graph, load_graph

root = Path(".")
graph = build_graph(
    repo_root=root,
    global_vault=None,      # use documented precedence
    output_path=None,       # knowledge/graph/graph.json
    config=None,
    strict=True,
)

same_graph = load_graph(root / "knowledge/graph/graph.json")
```

`strict=True` propagates frontmatter parse failures instead of collecting them
as skipped-file warnings.

## CLI behavior

There is no separate `akms build` command. `akms query`, `akms loadout`, and
`akms resolve-task` build the default graph when it does not exist. An explicitly
provided missing `--graph` path fails rather than silently building elsewhere.

## Merge rules

- Global nodes are loaded first.
- A local node whose ID collides with a global node is skipped and reported.
- Code-mirror nodes validate against their dedicated tagless schema.
- Overlay entries for missing nodes are reported as orphans.
- Local edges and generated session nodes are applied after source nodes.

## Reproducibility

The semantic graph and serialized ordering are deterministic for identical
inputs. The ordinary graph serializer includes a current `generated_at`
timestamp; use a canonical semantic comparison or the failure-memory pinned
refresh path when byte identity matters.

## Health report

```bash
akms status --repo .
```

Use the status report to find missing graphs, skipped inputs, orphaned overlay
entries, and other health conditions. Do not copy a sample count from these docs
and expect the repository to politely stop changing.
