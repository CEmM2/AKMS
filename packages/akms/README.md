# akms

A deterministic global-local knowledge compiler. AKMS turns typed knowledge
nodes into a directed graph, compiles task-scoped projections from that graph,
and ingests structured evidence back into it.

## What the core does

- **Typed knowledge nodes** with a frozen v2 schema, provenance, and trust metadata.
- **Global/local ownership** — a read-only global vault plus a writable project graph.
- **Deterministic selection** — tag derivation, subgraph queries, and dedup are pure
  algorithmic paths. No language model participates in graph operations.
- **Projections** — task-scoped slices of the graph, reproducible from the same inputs.
- **Evidence ingestion** — structured outcomes flow back into the graph.

The core performs **no network calls** and requires no API key.

## Installation

```bash
pip install akms
```

That is the minimal core: graph compilation, schema, projections, evidence, and
the `akms` CLI, with four dependencies and no provider SDK.

Optional capabilities are explicit extras:

| Install | Adds |
|---|---|
| `akms[agents]` | coding-agent backends |
| `akms[mcp]` | the MCP tool server |
| `akms[telemetry]` | OpenTelemetry span export |
| `akms[orchestration]` | the complete embedded first-party runtime |

## Consumption modes

AKMS is usable through any of these, and they are parallel supported paths
rather than layers you must adopt in order:

- the Python library API
- the `akms` CLI
- MCP tools
- a skill or agent-host integration
- `akms.orchestrator` — an **optional** first-party runtime that drives a coding
  agent directly
- an external consumer that requests projections and returns evidence

The embedded runtime is one consumer of the same public contracts external
systems use. AKMS does not own portfolio-wide orchestration.

## Requirements

Python 3.12. Some search paths use [qmd](https://github.com/tobi/qmd), an
external Go binary; when it is absent those paths fall back to `grep`.

## Maturity

Research software, published as a preview. See the repository root for
limitations, privacy and provider notes, and the stable-versus-experimental
capability matrix.

## License

Apache-2.0. See `LICENSE` at the repository root.
