---
id: "cc-failure-l004"
title: "L004: advisory only lesson"
domain: "consumercontract"
subdomain: "failure-memory"
tags: ["area-tools","found-by-manual-audit","line-hint-advisory-only-lesson","module-tools-report-render","package-report","symbol-render-summary"]
status: "established"
confidence: 0.99
source: "human"
confidence_floor: 0.95
edges: []
load_with: []
context_size: "small"
reading_priority: "full"
content_ref: "generated/nodes/knowledge/local-nodes/failure-lessons/cc-failure-l004.md"
akms_schema: "v2"
---
<!-- GENERATED: edit lessons.json -->
<!-- source_sha256: 5827bd81152da1049f56c292daa684daf7271036f1d7c3929224515f597c54c2 -->

# L004: advisory only lesson

## Identity

- Registry ID: L004

## Location

- Area: tools
- Package: report
- Module: tools.report.render
- File: tools/report/render.py
- Symbol: render_summary
- Line hint: advisory only lesson

## Discovery

- Type: manual audit
- Trigger: tools/report/test_render.py::test_summary_escapes

## Failure

### Symptom

Untrusted lesson prose reached the rendered summary unescaped.

### Root cause

The renderer interpolated raw text into markup.

### Fix

Escape every interpolated field at the render boundary.

### Prevention

tools/report/test_render.py asserts that summary rendering escapes untrusted text.

## Timeline

- Found: 2026-08-04 (exact)
- Fixed: 2026-08-05 (exact)

## References

- Commit:
- Issue:
- PR:
- Plan: dev/plans/consumer-integration.md

## Notes

Conformance anchor for advisory selection; reachable only by the akms_tags advisory path.
