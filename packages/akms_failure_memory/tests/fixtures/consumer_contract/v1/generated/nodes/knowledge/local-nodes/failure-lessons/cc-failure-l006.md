---
id: "cc-failure-l006"
title: "L006: documentation only route"
domain: "consumercontract"
subdomain: "failure-memory"
tags: ["area-docs","found-by-review","line-hint-documentation-only-route","module-docs-architecture","package-docs"]
status: "established"
confidence: 0.99
source: "human"
confidence_floor: 0.95
edges: []
load_with: []
context_size: "small"
reading_priority: "full"
content_ref: "generated/nodes/knowledge/local-nodes/failure-lessons/cc-failure-l006.md"
akms_schema: "v2"
---
<!-- GENERATED: edit lessons.json -->
<!-- source_sha256: 30ba4b429a5e1bbab910d1e9ef403067802a2799fa1966e8bd98de82fc006247 -->

# L006: documentation only route

## Identity

- Registry ID: L006

## Location

- Area: docs
- Package: docs
- Module: docs.architecture
- File: docs/architecture.md
- Symbol:
- Line hint: documentation only route

## Discovery

- Type: review
- Trigger: docs/architecture.md

## Failure

### Symptom

The published architecture note kept describing a contract the engine no longer honoured.

### Root cause

The document was not part of any review checklist tied to the contract it described.

### Fix

Bind the document to the contract's own review step so the two move together.

### Prevention

docs/architecture.md is re-reviewed whenever the engine contract changes.

## Timeline

- Found: 2026-08-06 (exact)
- Fixed: 2026-08-07 (exact)

## References

- Commit:
- Issue:
- PR:
- Plan: dev/plans/consumer-integration.md

## Notes

Conformance anchor for documentation-only route suppression. location.file is a docs path, so AKMS drops it from the exact-required lane whenever EVERY declared/changed path in a task is documentation. Do not change this file path.
