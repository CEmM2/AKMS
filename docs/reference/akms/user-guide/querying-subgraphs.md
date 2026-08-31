# Query ranked knowledge

`query_subgraph()` performs a role-aware ranked query over the compiled graph.
Despite its historical name, it returns a ranked list of node records rather
than a NetworkX subgraph.

## Python API

```python
from akms.graph.build_graph import load_graph
from akms.graph.query_subgraph import query_subgraph

G = load_graph("knowledge/graph/graph.json")
ranked = query_subgraph(
    G,
    domain_tags=["plasticity", "return-mapping"],
    agent_role="physics_reviewer",
    config=None,
    max_depth=2,
)

for node_id, data in ranked:
    print(node_id, data["domain"], data["confidence"])
```

## Selection algorithm

The query:

1. Loads the role profile from propagation configuration.
2. Finds nodes whose tags intersect the seed tags.
3. Builds a bounded undirected ego union around those seeds.
4. Retains tentative and established nodes.
5. Traverses only edge types allowed by the role profile.
6. Applies preferred/excluded domain and confidence rules.
7. Ranks candidates according to the role profile.
8. Caps ordinary results and injects relevant pitfall nodes.

## CLI

```bash
akms query plasticity return-mapping \
  --repo . \
  --role physics_reviewer \
  --max-depth 2
```

Output is stable JSON containing `count`, `graph_path`, and `nodes`.

## When not to use a tag query

A tag match is advisory. Use [exact task resolution](task-resolution.md) when a
source path or symbol imposes a mandatory contract that must bypass ranking,
thresholds, or caps.
