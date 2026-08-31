---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-sim-reviewer/examples/pr-review-template.md
context_size: small
domain: project-meta
edges:
- note: Template implements the review checklist structure
  to: tsr-ref-review-checklist
  type: implements
  weight: 0.8
id: tsr-ex-pr-template
reading_priority: full
source: human
status: established
subdomain: code-review
tags:
- PR-template
- review-template
- GitHub-format
- standardized-review
- severity
title: PR Review Template (Standardized Format)
---

# PR Review Template (Standardized Format)

## Summary

Standardized GitHub PR review template: summary, review status (approve/request-changes/comment), severity counts (critical/major/minor), core checklist (correctness/performance/style/architecture/documentation/testing/domain), detailed comments per category, decision statement, and required follow-up actions.

**Parent skill:** `skill-taichi-sim-reviewer`
**Content:** `content/taichi-sim-reviewer/examples/pr-review-template.md`
