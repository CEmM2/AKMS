# Usage

A practical guide to driving akms-learn from Python and from the CLI. For the
model behind these calls, see [Core Concepts](../../concepts/akms-learn.md).

---

## Python API

### Building a request

A [`LearningRequest`](api-reference.md#requests) needs at minimum `topic`,
`goal`, and `generation_option`; everything else has a default:

```python
from akms_learn import LearningRequest

request = LearningRequest(
    topic="j² return mapping",
    goal="Understand the j² return-mapping algorithm",
    audience="engineer",              # default "engineer"
    depth="implementation",           # default "implementation"
    generation_option="deterministic_outline",
    seed_tags=["j2_plasticity"],      # default []
    include_pitfalls=True,            # default True
    include_code_links=True,          # default True
    exporters=["markdown", "bundle"], # default []
)
```

You can also pass a **plain dict** anywhere a `LearningRequest` is accepted — the
compiler normalizes it identically. Extra keys are dropped:

```python
request = {
    "topic": "j² return mapping",
    "goal": "Understand it",
    "generation_option": "deterministic_outline",
    "session_id": "abc123",   # UI state — silently dropped
}
```

### Calling the compiler

[`compile_learning_source`](api-reference.md#compiler) is the single entry
point. Supply **exactly one** of `graph_slice` or `graph_path`:

```python
from pathlib import Path
from akms_learn import compile_learning_source, fixture_graph

result = compile_learning_source(
    request=request,
    graph_slice=fixture_graph(),       # XOR graph_path=Path("graph.json")
    output_dir=Path("./out"),          # optional; enables disk writes
    domain_pack_paths=None,            # optional list of YAML paths/dirs
    source_pack_paths=None,            # optional list of YAML paths
)
```

| Parameter | Meaning |
|---|---|
| `request` | A `LearningRequest` or a raw dict. |
| `graph_path` | Path to a graph JSON. Mutually exclusive with `graph_slice`. |
| `graph_slice` | A `GraphSlice` or raw dict payload. Mutually exclusive with `graph_path`. |
| `output_dir` | When set, the canonical packet JSON is written to `<output_dir>/<request_hash>.json` and exporters write here. |
| `domain_pack_paths` | Paths to `domain_pack.yaml` files (or directories containing one). |
| `source_pack_paths` | Paths to source-pack YAMLs. |

!!! warning "Supply exactly one graph source"
    Passing neither or both of `graph_path` and `graph_slice` raises
    `ValueError`. The compiler never invents a graph.

### Reading the result

The call returns a [`CompileResult`](api-reference.md#compiler) dataclass:

```python
result.packet                    # LearningSourcePacket (validated)
result.packet_path               # Path | None — written canonical JSON
result.export_paths              # list[Path] — every Stage 9 artifact
result.warnings                  # list[LearningWarning] — soft issues
result.unavailable_capabilities  # list[str]
result.stage_log                 # list[str] — equals STAGES on success
```

Inspecting the packet body:

```python
packet = result.packet
print(packet.packet_id)                     # lsp-<hash>-<hash>
print(packet.source.graph_hash)
print(packet.request.request_hash)
print(packet.body.reading_order)            # ordered node ids
for node in packet.body.nodes:
    print(node.node_id, node.title, node.source_path, node.line_range)
for w in packet.warnings:
    print(w.severity, w.code, w.message)
```

!!! tip "Exporters run inside the compiler"
    Do not import `akms_learn.exporters.markdown` or `.bundle` and call them
    yourself. List the exporter in `request.exporters` and read the produced
    paths from `result.export_paths`. The compiler owns Stage 9 dispatch.

---

## CLI reference

The console script `akms-learn` is a thin wrapper over
`compile_learning_source`. It exposes two subcommands: `compile` and `validate`.

### `akms-learn compile`

Compile a graph slice into a packet and (optionally) exporter artifacts.

```bash
akms-learn compile --graph fixture --topic "j² return mapping" \
  --goal "Understand it" --export markdown --output ./out
```

| Flag | Default | Meaning |
|---|---|---|
| `--graph` | *(required)* | Path to a graph JSON, or the literal `fixture` to use `fixture_graph()`. |
| `--topic` | *(required)* | Learning topic. |
| `--goal` | `--topic` value | Learning goal (defaults to `--topic` when omitted). |
| `--audience` | `engineer` | Audience. |
| `--depth` | `implementation` | Depth. |
| `--generation-option` | `deterministic_outline` | Generation mode. |
| `--seed-tags` | `[]` | Seed tag (repeatable). |
| `--max-nodes` | `None` | Maximum nodes to retain. |
| `--max-depth` | `None` | Maximum traversal depth. |
| `--include-pitfalls` / `--no-include-pitfalls` | enabled | Toggle pitfall sections. |
| `--include-code-links` / `--no-include-code-links` | enabled | Toggle code-link sections. |
| `--export` | `[]` | Exporter name (repeatable). One of `markdown`, `bundle`, `notebook`, `assessment`, `html`. |
| `--output` | *(required)* | Output directory (created if missing). |
| `--domain-pack` | `[]` | Path to a `domain_pack.yaml` (repeatable). |
| `--source-pack` | `[]` | Path to a `source_pack.yaml` (repeatable). |
| `--quiet` | off | Suppress non-key output. |
| `--json` | off | Emit a single JSON object instead of `key: value` lines. |

**LLM-expansion flags** (off by default):

| Flag | Meaning |
|---|---|
| `--llm-enable` / `--no-llm-enable` | Enable LLM expansion (default disabled). |
| `--llm-provider` | Provider registry name: `akms`, `nlm`, or `no_provider_stub`. |
| `--llm-policy` | `source_locked`, `explanatory_only`, or `no_new_claims`. |
| `--llm-notebook-id` | NotebookLM notebook id used as a grounded source. |
| `--llm-pdf` | PDF path added as a grounded source (repeatable). |
| `--llm-profile` | NotebookLM profile name for the grounded provider. |

**Learner-profile flags** (only effective with `--generation-option adaptive_path`):

| Flag | Meaning |
|---|---|
| `--knows` | Concept/tag/node-id the learner already knows (repeatable). |
| `--weak` | Weak-area topic (repeatable); surfaced in the summary, does not affect selection. |
| `--learner-goal` | Adaptive-path goal (repeatable); not the same as `--goal`. |
| `--conservative` / `--no-conservative` | Conservative prerequisite mode. Conservative (the default) never skips a prerequisite. |

The `compile` command prints `packet_path`, one `export_paths` line per
artifact, a `warnings` count (with per-warning lines unless `--quiet`),
`unavailable_capabilities`, and `manifest_path`.

### `akms-learn validate`

Load a packet from disk (YAML if the path ends in `.yaml`/`.yml`, JSON
otherwise) and run `validate_packet`:

```bash
akms-learn validate --packet ./out/learning_source_packet.yaml
```

| Flag | Meaning |
|---|---|
| `--packet` | *(required)* Path to an LSP YAML or JSON file. |
| `--quiet` | Suppress per-warning lines. |
| `--json` | Emit a single JSON object. |

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. |
| `2` | `PacketValidationError`. |
| `3` | `LearningCapabilityError`. |
| `1` | Any other unhandled error (message printed to stderr). |

!!! note
    `--help` and argparse parse errors use argparse's own conventional exit
    codes, surfaced unchanged.

---

## Choosing a generation mode

Set `generation_option` (or `--generation-option`):

| You want… | Use |
|---|---|
| A reproducible structured outline | `deterministic_outline` |
| A readable lesson from rich node bodies | `anthology` |
| A failure-mode / debugging walk | `pitfall` |
| Overview / standard / deep-dive variants | `multi_granularity` (set `granularity`) |
| Optional LLM prose on top of the packet | `llm_expanded` (set `--llm-enable`) |
| Learner-personalised prerequisite filtering | `adaptive_path` (needs the `llm` extra) |

An unrecognised `generation_option` falls back to the default ordering strategy,
so output is still well-formed. See [Generation modes](../../concepts/akms-learn.md#generation-modes).

---

## Choosing exporters

List exporter names in `request.exporters` (or repeat `--export`). Valid names
are the members of `KNOWN_EXPORTERS`: `markdown`, `bundle`, `notebook`,
`assessment`, `html`.

```python
request = LearningRequest(
    topic="...", goal="...",
    generation_option="deterministic_outline",
    exporters=["markdown", "bundle"],
)
```

- `markdown` produces `lesson.md`.
- `bundle` produces the full seven-artifact review bundle and a `manifest.json`.
- `notebook` and `html` require their respective extras.

An unknown or stub exporter emits an `exporter_unavailable` warning rather than
failing the compile.

---

## Working with domain packs

Pass YAML descriptor paths (or a directory containing `domain_pack.yaml`):

=== "Python API"

    ```python
    result = compile_learning_source(
        request=request,
        graph_slice=fixture_graph(),
        domain_pack_paths=["./packs/compmech_reference"],   # dir auto-resolves
        source_pack_paths=["./packs/sources/papers.yaml"],
    )
    provenance = result.packet.body.domain_pack_provenance   # list of descriptors
    ```

=== "CLI"

    ```bash
    akms-learn compile --graph fixture --topic "..." --goal "..." \
      --domain-pack ./packs/compmech_reference \
      --source-pack ./packs/sources/papers.yaml \
      --output ./out
    ```

Loaded descriptors are attached (in deterministic order) to
`body.domain_pack_provenance` and `body.source_pack_provenance`. A missing path
raises `LearningCapabilityError`. See
[Domain packs](../../concepts/akms-learn.md#domain-packs-and-source-packs).

---

## Next steps

- Work through end-to-end [Examples](examples.md).
- Look up exact signatures in the [API Reference](api-reference.md).
