# Getting started

## Source-workspace installation

```bash
uv sync --project packages/akms_learn --all-extras --all-groups
uv run --project packages/akms_learn akms-learn --help
```

Python range: `>=3.11,<3.14`.

`nbformat` and Jinja2 are installed as base dependencies. The `notebook` and
`html` extras are empty backward-compatibility sentinels, not feature gates.
`llm` and `nlm` are capability sentinels; the grounded NotebookLM path probes the
external `nlm` CLI at runtime.

## First packet from the fixture graph

```python
from pathlib import Path

from akms_learn import LearningRequest, compile_learning_source, fixture_graph

request = LearningRequest(
    topic="j2 return mapping",
    goal="Understand the return-mapping algorithm",
    generation_option="deterministic_outline",
    exporters=["markdown"],
)

result = compile_learning_source(
    request=request,
    graph_slice=fixture_graph(),
    output_dir=Path("./out"),
)

print(result.packet.packet_id)
for path in result.export_paths:
    print(path)
```

CLI equivalent:

```bash
akms-learn compile \
  --graph fixture \
  --topic "j2 return mapping" \
  --goal "Understand the return-mapping algorithm" \
  --generation-option deterministic_outline \
  --export markdown \
  --output ./out
```

`compile_learning_source` accepts exactly one graph source: an in-memory
`graph_slice` or a `graph_path`.

## Determinism

Request hashing, selection, ordering, and packet identity are deterministic for
the same inputs. Packet metadata includes `created_at`, so compare the documented
canonical fields rather than pretending all wall-clock metadata is immutable.
