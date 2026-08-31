# Critical invariants

## 1. Global vault is read-only

No automated graph, update, failure-memory, or runtime operation may write or
promote content into the global vault. Promotion is a separate, explicit,
human-approved process.

## 2. Schema v2 is frozen

Adding/removing required fields or changing field types is a breaking change.
Create a new schema version and migration rather than smuggling a redesign into
an “optional” field.

## 3. Deterministic graph semantics

Graph compilation, ranked query, route resolution, manifest creation, and
ordinary update logic must not require an LLM or network call.

## 4. Required knowledge fails closed

Exact route/mirror requirements cannot be dropped because a cap, confidence
threshold, or provider failure made them inconvenient.

## 5. Project data remains project-owned

Local nodes, overlays, route indexes, failure registries, generated lesson
projections, and provider results stay within the consuming repository's policy.

## 6. Single-writer artifact boundaries

Use the owning compiler/renderer for generated graph, loadout, manifest, mirror,
lesson-node, and route artifacts. Avoid hand edits that cannot be reproduced.

## 7. External tools use explicit argv contracts

Do not use shell interpolation for repo2md or similar providers. Pin and validate
versions, schemas, source identity, and fixtures where compatibility matters.

## 8. Optional runtimes stay optional

Core documentation and APIs must remain usable without the staged runner,
Claude, Codex, NotebookLM, MechDSL, or a local inference endpoint.
