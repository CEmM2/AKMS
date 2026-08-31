---
id: "cc-failure-l005"
title: "L005: diff only discovery"
domain: "consumercontract"
subdomain: "failure-memory"
tags: ["area-src","found-by-test-failure","line-hint-diff-only-discovery","module-storage-writer","package-storage","symbol-writer-flush"]
status: "established"
confidence: 0.99
source: "human"
confidence_floor: 0.95
edges: []
load_with: []
context_size: "small"
reading_priority: "full"
content_ref: "generated/nodes/knowledge/local-nodes/failure-lessons/cc-failure-l005.md"
akms_schema: "v2"
---
<!-- GENERATED: edit lessons.json -->
<!-- source_sha256: 30ba4b429a5e1bbab910d1e9ef403067802a2799fa1966e8bd98de82fc006247 -->

# L005: diff only discovery

## Identity

- Registry ID: L005

## Location

- Area: src
- Package: storage
- Module: storage.writer
- File: src/storage/writer.py
- Symbol: Writer.flush
- Line hint: diff only discovery

## Discovery

- Type: test failure
- Trigger: tests/storage/test_writer_flush.py::test_flush_is_atomic

## Failure

### Symptom

A failed flush left a truncated file on disk.

### Root cause

The writer opened the destination for truncation before the payload was complete.

### Fix

Write a sibling temporary file and atomically replace the destination.

### Prevention

tests/storage/test_writer_flush.py asserts that a failed flush leaves the prior file intact.

## Timeline

- Found: 2026-08-05 (exact)
- Fixed: 2026-08-06 (exact)

## References

- Commit:
- Issue:
- PR:
- Plan: dev/plans/consumer-integration.md

## Notes

Conformance anchor for post-diff-only discovery; never declared in pre-task scope.
