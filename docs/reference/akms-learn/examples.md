# Examples

Worked examples derived from the package's own integration tests and fixtures.
Each uses the built-in [`fixture_graph()`](api-reference.md#graph-import) — a
six-node "j² return mapping" learning path — so every snippet runs without a real
graph build.

!!! note "The fixture graph"
    `fixture_graph()` ships six nodes (two prerequisites, a core concept, a
    derivation, an implementation, a pitfall, an exercise) wired by `requires`,
    `derives`, `implements`, `pitfall_of`, and `exercise_for` edges. The
    examples below reference those nodes directly.

---

## 1. Minimal deterministic outline

The smallest useful compile: a deterministic outline, no exporters, no disk
writes. Mirrors `test_compile_fixture_graph_produces_valid_lsp`.

```python
from akms_learn import (
    LearningRequest,
    LearningSourcePacket,
    compile_learning_source,
    fixture_graph,
    validate_packet,
)

request = LearningRequest(
    topic="j² return mapping",
    goal="Understand the j² return-mapping algorithm",
    generation_option="deterministic_outline",
)

result = compile_learning_source(request=request, graph_slice=fixture_graph())

assert isinstance(result.packet, LearningSourcePacket)
assert len(result.packet.body.nodes) == 6      # every fixture node retained
assert result.packet.body.reading_order        # populated
assert validate_packet(result.packet) == []    # no soft warnings
```

**Expected output:** a valid packet with six node views, six edge views, a
populated `reading_order`, and a deterministic `packet_id` of the form
`lsp-<request_hash[:16]>-<graph_hash[:8]>`. `result.stage_log` equals the nine
`STAGES`.

---

## 2. Verifying determinism

Two identical compiles produce byte-equal packets except for `created_at`.
Mirrors `test_compile_byte_stable_except_timestamp`.

```python
import re
from akms_learn import compile_learning_source, fixture_graph, LearningRequest

request = LearningRequest(
    topic="j² return mapping",
    goal="Understand it",
    generation_option="deterministic_outline",
)
slice_ = fixture_graph()

a = compile_learning_source(request=request, graph_slice=slice_)
b = compile_learning_source(request=request, graph_slice=slice_)

assert a.packet.packet_id == b.packet.packet_id   # deterministic id

ts = re.compile(r'"created_at":\s*"[^"]*"')
json_a = ts.sub('"created_at":"X"', a.packet.model_dump_json(by_alias=True))
json_b = ts.sub('"created_at":"X"', b.packet.model_dump_json(by_alias=True))
assert json_a == json_b   # byte-identical once the timestamp is masked
```

**Expected output:** identical `packet_id`s, and identical serialised JSON once
the `created_at` field is masked.

---

## 3. A dict-shaped request

`compile_learning_source` accepts a plain dict anywhere a `LearningRequest` is
accepted; extra keys are dropped before hashing. Mirrors `TestCompileDictRequest`.

```python
from akms_learn import compile_learning_source, fixture_graph, STAGES

request = {
    "topic": "j² return mapping",
    "goal": "Understand the j² return-mapping algorithm",
    "audience": "engineer",
    "depth": "implementation",
    "generation_option": "deterministic_outline",
    "seed_tags": [],
    "exporters": [],
    "session_id": "abc123",   # UI state — silently dropped, never hashed
}

result = compile_learning_source(request=request, graph_slice=fixture_graph())
assert tuple(result.stage_log) == STAGES
```

**Expected output:** an identical packet to the `LearningRequest` form — the
`session_id` key never reaches the request hash.

---

## 4. Exporting Markdown and a review bundle

Add exporters and an `output_dir` to write artifacts to disk. Selecting
`bundle` produces the full seven-artifact review bundle plus a `manifest.json`.

=== "Python API"

    ```python
    from pathlib import Path
    from akms_learn import LearningRequest, compile_learning_source, fixture_graph

    request = LearningRequest(
        topic="j² return mapping",
        goal="Understand the j² return-mapping algorithm",
        generation_option="deterministic_outline",
        exporters=["markdown", "bundle"],
    )

    result = compile_learning_source(
        request=request,
        graph_slice=fixture_graph(),
        output_dir=Path("./out"),
    )

    for path in result.export_paths:
        print(path)
    ```

=== "CLI"

    ```bash
    akms-learn compile \
      --graph fixture \
      --topic "j² return mapping" \
      --goal "Understand the j² return-mapping algorithm" \
      --export markdown \
      --export bundle \
      --output ./out
    ```

**Expected output** under `./out`:

```text
out/<request_hash>.json            # canonical packet JSON
out/lesson.md                      # markdown exporter
out/learning_source_packet.yaml    # bundle: full LSP as YAML
out/manifest.json                  # bundle: index
out/concept_map.json               # bundle: nodes + edges subset
out/provenance.json                # bundle: graph/request hashes + per-node provenance
out/warnings.json                  # bundle: serialised warnings
out/exports/.gitkeep               # bundle: kept directory
out/assets/.gitkeep                # bundle: kept directory
```

All bundle artifacts are byte-stable across reruns (the LSP YAML's `created_at`
is the only exception).

---

## 5. Attaching domain-pack provenance

Pass a domain-pack directory; its descriptors are attached to the packet body.
Mirrors `test_compile_with_domain_pack_paths_populates_metadata`.

```python
from akms_learn import LearningRequest, compile_learning_source, fixture_graph

request = LearningRequest(
    topic="j² return mapping",
    goal="Understand it",
    generation_option="deterministic_outline",
)

result = compile_learning_source(
    request=request,
    graph_slice=fixture_graph(),
    domain_pack_paths=["./fixtures/domain_packs/compmech_reference"],
)

provenance = result.packet.body.domain_pack_provenance
assert isinstance(provenance, list) and provenance
ids = {d.get("id") for d in provenance}
assert any("compmech" in (i or "") for i in ids)
```

**Expected output:** `body.domain_pack_provenance` is a list of descriptor dicts
in deterministic (alphabetic-by-id) order. A missing or invalid pack path raises
`LearningCapabilityError` instead.

---

## 6. Handling a required-but-unavailable capability

A request can demand capabilities; if one is missing the compile raises at Stage
1. Mirrors `test_compile_required_unavailable_raises_capability_error`.

```python
import pytest
from akms_learn import (
    LearningRequest,
    LearningCapabilityError,
    compile_learning_source,
    fixture_graph,
)

request = LearningRequest(
    topic="j² return mapping",
    goal="Understand it",
    generation_option="deterministic_outline",
    required_capabilities=["nonexistent_capability"],
)

with pytest.raises(LearningCapabilityError, match="nonexistent_capability"):
    compile_learning_source(request=request, graph_slice=fixture_graph())
```

**Expected output:** a `LearningCapabilityError` naming the missing capability —
no packet is produced. Note that `required_capabilities` is excluded from the
request hash, so it gates availability without changing request identity.

---

## Next steps

- Review the model and pipeline in [Core Concepts](../../concepts/akms-learn.md).
- Look up every signature in the [API Reference](api-reference.md).
