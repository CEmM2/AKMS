# AKMS — Adaptive Knowledge Management System

A **deterministic global-local knowledge compiler**: typed knowledge nodes
compile into a directed graph, tasks receive reproducible **projections** of
that graph, and structured **evidence** flows back in to update confidence and
grow the graph.

- **No LLM in graph operations.** Tag derivation, subgraph queries, ranking,
  and dedup are pure algorithms — same inputs, same outputs, byte for byte.
- **Global/local ownership.** A read-only global vault holds curated
  knowledge; each project keeps a writable local overlay. Automated processes
  never mutate the global vault.
- **Offline by default.** The core performs no network calls and needs no API
  key. Providers are explicit opt-ins.

## What AKMS is not

- Not a portfolio-wide orchestrator: external workflow systems consume AKMS
  projections and return evidence; AKMS does not coordinate them.
- Not a RAG vector store: knowledge is typed, versioned, and graph-structured,
  with provenance and trust metadata — not embedding soup.
- Not production infrastructure: this is research software, published as a
  preview.

## Architecture

```
sources → typed nodes → global/local graph → projection → evidence ingestion
                              │
                              ├── Python/library API
                              ├── CLI
                              ├── MCP tools
                              ├── skill / agent-host integration
                              ├── akms.orchestrator   (optional first-party runtime)
                              └── external consumer   (your workflow system)
```

The embedded runtime is one consumer of the same public contracts external
systems use. The dependency direction is one-way: the runtime depends on core
contracts; the core never depends on the runtime. See
`docs/adr/0001-projection-and-evidence-contract-surface.md`.

## Packages

| Package | What it does | Maturity |
|---|---|---|
| `akms` | Core compiler, projections, evidence, CLI, optional embedded runtime | Core stable, runtime experimental |
| `akms-learn` | Learning-packet compiler and exporters | **Experimental preview** |
| `akms-nodes-gen` | Node generation and validation tooling | Experimental |
| `akms-failure-memory` | Deterministic project-owned failure memory | Beta |

## Six ways to use it

1. **Python API** — `build_graph`, `query_subgraph`, `update_graph`.
2. **CLI** — `akms status | query | loadout | resolve-task`.
3. **MCP tools** — `pip install "akms[mcp]"`, then run `akms-mcp-stdio`.
4. **Skill / agent-host integration** — reviewed templates under `integrations/`.
5. **Embedded runtime** — `pip install "akms[orchestration]"`; `akms orchestrate`
   drives a coding agent directly. Optional; nothing else requires it.
6. **External consumer** — request projections, return evidence, never import
   the runtime. Proven by `tests/integration/external_consumer/`.

## Ten-minute quickstart (no provider, no API key)

```bash
pip install akms
```

Create a small vault and a project:

```bash
mkdir -p vault/nodes project/knowledge/{graph,local-nodes,sessions,loadouts,code-mirror,qmd}
printf 'akms_schema: v2\nnodes: {}\n' > project/knowledge/graph/local_state.yaml

cat > vault/nodes/demo-node.md <<'NODE'
---
akms_schema: v2
id: demo-node
title: Demo Node
domain: demo-domain
tags:
- demo
status: established
confidence: 0.9
source: human
edges: []
---

Demo content.
NODE
```

Compile, inspect, project:

```bash
python -c "from akms.graph.build_graph import build_graph; \
           build_graph('project', global_vault='vault/nodes')"
cd project
akms status          # health report: 1 node, 0 issues
akms query demo      # projection seeded by tag
akms loadout demo-task --phase 1 --tags demo
```

Feed evidence back:

```bash
python - <<'PY'
from akms.graph.update_graph import update_graph
summary = update_graph(
    {"task_id": "demo-task",
     "nodes_used": [{"id": "demo-node", "useful": True, "coverage": "sufficient"}],
     "nodes_missing": [], "lessons": {}, "pitfalls_discovered": [],
     "new_knowledge": []},
    ".", global_vault="../vault/nodes")
print(summary["confidence_events"])
PY
```

The node's confidence rises and the change lands in the project's local
overlay — the global vault is untouched. This exact flow runs in CI against
installed wheels (`tests/public_smoke/core/`).

## Maturity, privacy, limitations

- `docs/limitations.md` — the stable-vs-experimental capability matrix and
  known performance limits.
- `docs/privacy-and-providers.md` — the no-network guarantee, what leaves your
  machine when you opt into a provider, and untrusted-input guidance.

## Contributing and support

See `CONTRIBUTING.md`, `SUPPORT.md`, and `SECURITY.md` (private vulnerability
reporting). Conduct: `CODE_OF_CONDUCT.md`.

## License and citation

Code is licensed under **Apache-2.0** (`LICENSE`). Documentation, sample
knowledge nodes, and diagrams are **CC BY 4.0**. To cite AKMS, use
`CITATION.cff`.
