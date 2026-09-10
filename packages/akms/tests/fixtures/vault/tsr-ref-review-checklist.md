---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-sim-reviewer/references/review-checklist.md
context_size: medium
domain: project-meta
edges:
- note: Review requires deep knowledge of kernel patterns
  to: tgs-ref-kernel-patterns
  type: requires
  weight: 0.9
- note: Checklist includes known-pitfall checks
  to: tgs-ref-gotchas
  type: requires
  weight: 0.8
- note: Review checks tensor/stress convention correctness
  to: tgs-ref-continuum-tensors
  type: requires
  weight: 0.7
- note: Review verifies adequate test coverage
  to: tsr-ref-testing-verification
  type: requires
  weight: 0.7
id: tsr-ref-review-checklist
reading_priority: full
source: human
status: established
subdomain: code-review
tags:
- code-review
- checklist
- correctness
- performance
- style
- testing
- quality
title: Code Review Checklist for Taichi Simulation PRs
---

# Code Review Checklist for Taichi Simulation PRs

## Summary

Comprehensive code review checklist for Taichi simulation PRs covering: correctness (physical laws, sign conventions, invariants, math), performance (architecture, hot loops, data layout, atomics, block tuning), style (naming, ownership, modularity), documentation, testing, and domain specifics. Systematic baseline ensuring quality across multiple dimensions.

**Parent skill:** `skill-taichi-sim-reviewer`
**Content:** `content/taichi-sim-reviewer/references/review-checklist.md`
