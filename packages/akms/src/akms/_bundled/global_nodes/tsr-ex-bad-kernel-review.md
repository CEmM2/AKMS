---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-sim-reviewer/examples/bad-kernel-review.md
context_size: medium
domain: project-meta
edges:
- note: This example applies the review checklist
  to: tsr-ref-review-checklist
  type: implements
  weight: 0.9
- note: Bad review populates the PR template format
  to: tsr-ex-pr-template
  type: feeds-into
  weight: 0.5
id: tsr-ex-bad-kernel-review
reading_priority: full
source: human
status: established
subdomain: code-review
tags:
- code-review
- example
- critical-issues
- heat-equation
- data-races
- annotated
title: 'Example: Bad Kernel Review (Annotated)'
---

# Example: Bad Kernel Review (Annotated)

## Summary

Detailed code review example of a flawed 2D heat solver: identifies critical issues (no explicit arch, CFL violation, data race from single buffer), major issues (branch divergence, boundaries mixed with interior), and minor issues (magic numbers, missing docstrings). Annotated code with severity levels showing the reviewer workflow and required fixes before merge.

**Parent skill:** `skill-taichi-sim-reviewer`
**Content:** `content/taichi-sim-reviewer/examples/bad-kernel-review.md`
