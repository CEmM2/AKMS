# API Reference

Auto-generated reference for the public `akms_learn` surface. Every symbol below
is exported from the package root (`from akms_learn import ...`). For narrative
guidance see the [Usage guide](usage.md); for the model behind these symbols see
[Core Concepts](../../concepts/akms-learn.md).

---

## Compiler

The nine-stage pipeline entry point, its result bundle, and the stage tuple.

### `compile_learning_source`

::: akms_learn.compile_learning_source

### `CompileResult`

::: akms_learn.CompileResult

### `STAGES`

::: akms_learn.STAGES

---

## Requests

The learning-request model, its canonical normalization, and the request hash.

### `LearningRequest`

::: akms_learn.LearningRequest

### `normalize_request`

::: akms_learn.normalize_request

### `to_canonical_dict`

::: akms_learn.to_canonical_dict

### `request_hash`

::: akms_learn.request_hash

---

## Graph import

The in-memory graph slice and helpers, including the demo fixture.

### `GraphSlice`

::: akms_learn.GraphSlice

### `load_graph`

::: akms_learn.load_graph

### `compute_graph_hash`

::: akms_learn.compute_graph_hash

### `fixture_graph`

::: akms_learn.fixture_graph

---

## Models

The Learning Source Packet and its view models.

### `LearningSourcePacket`

::: akms_learn.LearningSourcePacket

### `PacketBody`

::: akms_learn.PacketBody

### `CompilerInfo`

::: akms_learn.CompilerInfo

### `SourceInfo`

::: akms_learn.SourceInfo

### `LearningRequestInfo`

::: akms_learn.LearningRequestInfo

### `LearningNodeView`

::: akms_learn.LearningNodeView

### `LearningEdgeView`

::: akms_learn.LearningEdgeView

### `PitfallView`

::: akms_learn.PitfallView

### `CodeLinkView`

::: akms_learn.CodeLinkView

### `ReferenceView`

::: akms_learn.ReferenceView

### `AssessmentView`

::: akms_learn.AssessmentView

### `LearningWarning`

::: akms_learn.LearningWarning

---

## Validation

Packet validation and its hard-error type.

### `validate_packet`

::: akms_learn.validate_packet

### `PacketValidationError`

::: akms_learn.PacketValidationError

---

## Exporters

Exporter entry points. The compiler dispatches these in Stage 9 — callers list
exporter names in `request.exporters` rather than calling these directly.

### `markdown_export`

::: akms_learn.markdown_export

### `bundle_export`

::: akms_learn.bundle_export

### `MANIFEST_VERSION`

::: akms_learn.MANIFEST_VERSION

---

## Domain packs

Metadata-only descriptors, the registry, and the capability error type.

### `DomainPackDescriptor`

::: akms_learn.DomainPackDescriptor

### `SourcePackDescriptor`

::: akms_learn.SourcePackDescriptor

### `DomainPackRegistry`

::: akms_learn.DomainPackRegistry

### `build_registry_from_paths`

::: akms_learn.build_registry_from_paths

### `LearningCapabilityError`

::: akms_learn.LearningCapabilityError
