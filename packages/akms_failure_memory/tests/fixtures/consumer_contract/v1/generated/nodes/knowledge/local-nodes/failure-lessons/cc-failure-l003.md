---
id: "cc-failure-l003"
title: "L003: coactivation target"
domain: "consumercontract"
subdomain: "failure-memory"
tags: ["area-src","found-by-test-failure","line-hint-coactivation-target","module-engine-queue","package-engine","symbol-queue-drain"]
status: "established"
confidence: 0.99
source: "human"
confidence_floor: 0.95
edges: []
load_with: []
context_size: "small"
reading_priority: "full"
content_ref: "generated/nodes/knowledge/local-nodes/failure-lessons/cc-failure-l003.md"
akms_schema: "v2"
---
<!-- GENERATED: edit lessons.json -->
<!-- source_sha256: 30ba4b429a5e1bbab910d1e9ef403067802a2799fa1966e8bd98de82fc006247 -->

# L003: coactivation target

## Identity

- Registry ID: L003

## Location

- Area: src
- Package: engine
- Module: engine.queue
- File: src/engine/queue.py
- Symbol: Queue.drain
- Line hint: coactivation target

## Discovery

- Type: test failure
- Trigger: tests/engine/test_queue_drain.py::test_drain_is_total

## Failure

### Symptom

Draining the queue left items behind when a consumer raised.

### Root cause

The drain loop mutated the queue while iterating it.

### Fix

Drain from a snapshot and re-queue only unconsumed items.

### Prevention

tests/engine/test_queue_drain.py asserts that drain consumes every queued item.

## Timeline

- Found: 2026-08-03 (exact)
- Fixed: 2026-08-04 (exact)

## References

- Commit:
- Issue:
- PR:
- Plan: dev/plans/consumer-integration.md

## Notes

Reached only through L002.related; never routed directly by the conformance requests.
