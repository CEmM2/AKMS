---
id: "cc-failure-l001"
title: "L001: exact route conformance"
domain: "consumercontract"
subdomain: "failure-memory"
tags: ["area-src","found-by-test-failure","line-hint-exact-route-conformance","module-engine-interface","package-engine","symbol-interface-commit-state"]
status: "established"
confidence: 0.99
source: "human"
confidence_floor: 0.95
edges: []
load_with: []
context_size: "small"
reading_priority: "full"
content_ref: "generated/nodes/knowledge/local-nodes/failure-lessons/cc-failure-l001.md"
akms_schema: "v2"
---
<!-- GENERATED: edit lessons.json -->
<!-- source_sha256: 30ba4b429a5e1bbab910d1e9ef403067802a2799fa1966e8bd98de82fc006247 -->

# L001: exact route conformance

## Identity

- Registry ID: L001

## Location

- Area: src
- Package: engine
- Module: engine.interface
- File: src/engine/interface.py
- Symbol: Interface.commit_state
- Line hint: exact route conformance

## Discovery

- Type: test failure
- Trigger: tests/engine/test_interface_commit.py::test_commit_is_idempotent

## Failure

### Symptom

Repeated commits advanced state that should have been idempotent.

### Root cause

Trial state was written directly into the committed record.

### Fix

Separate trial state from committed state and promote only accepted transitions.

### Prevention

tests/engine/test_interface_commit.py asserts that repeated commits do not advance state.

## Timeline

- Found: 2026-08-01 (exact)
- Fixed: 2026-08-02 (exact)

## References

- Commit:
- Issue:
- PR:
- Plan: dev/plans/consumer-integration.md

## Notes

Conformance anchor for the exact-required behaviour; prose is normative and must not be summarized.
