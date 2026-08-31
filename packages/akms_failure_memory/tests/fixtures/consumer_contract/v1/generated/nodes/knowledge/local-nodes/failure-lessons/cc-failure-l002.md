---
id: "cc-failure-l002"
title: "L002: coactivation source"
domain: "consumercontract"
subdomain: "failure-memory"
tags: ["area-src","found-by-review","line-hint-coactivation-source","module-engine-scheduler","package-engine","symbol-scheduler-enqueue"]
status: "established"
confidence: 0.99
source: "human"
confidence_floor: 0.95
edges: []
load_with: ["cc-failure-l003"]
context_size: "small"
reading_priority: "full"
content_ref: "generated/nodes/knowledge/local-nodes/failure-lessons/cc-failure-l002.md"
akms_schema: "v2"
---
<!-- GENERATED: edit lessons.json -->
<!-- source_sha256: 30ba4b429a5e1bbab910d1e9ef403067802a2799fa1966e8bd98de82fc006247 -->

# L002: coactivation source

## Identity

- Registry ID: L002

## Location

- Area: src
- Package: engine
- Module: engine.scheduler
- File: src/engine/scheduler.py
- Symbol: Scheduler.enqueue
- Line hint: coactivation source

## Discovery

- Type: review
- Trigger: tests/engine/test_scheduler_order.py::test_stable_order

## Failure

### Symptom

Enqueue order varied between runs on the same input.

### Root cause

The scheduler iterated an unordered mapping.

### Fix

Sort the pending set on a total key before enqueueing.

### Prevention

tests/engine/test_scheduler_order.py asserts a deterministic enqueue order.

## Timeline

- Found: 2026-08-02 (exact)
- Fixed: 2026-08-03 (exact)

## References

- Commit:
- Issue:
- PR:
- Plan: dev/plans/consumer-integration.md

## Notes

Conformance anchor for load_with coactivation; related must stay ['L003'].
