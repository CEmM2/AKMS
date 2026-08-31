---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-gpu-sim/references/gotchas.md
context_size: medium
domain: gpu-simulation
edges:
- note: Understanding kernel patterns needed to debug them
  to: tgs-ref-kernel-patterns
  type: requires
  weight: 0.7
- note: Gotchas inform numerical safety policies
  to: tgs-ref-numerical-safeguards
  type: feeds-into
  weight: 0.6
- note: Known pitfalls are checked during code review
  to: tsr-ref-review-checklist
  type: feeds-into
  weight: 0.7
id: tgs-ref-gotchas
reading_priority: pitfalls-only
source: human
status: established
subdomain: taichi
tags:
- gotchas
- debugging
- performance-pitfalls
- JIT
- atomics
- race-condition
- determinism
title: Taichi GPU Pitfalls & Debugging
---

# Taichi GPU Pitfalls & Debugging

## Summary

Repository-specific pitfalls for Taichi GPU development: JIT compilation warming, kernel launch overhead from Python loops, hidden synchronizations via host reads and print statements, atomic contention, shared memory pressure, and precision losses in floating-point operations. Each gotcha lists symptom, root cause, and remediation strategy to maintain GPU performance and correctness.

**Parent skill:** `skill-taichi-gpu-sim`
**Content:** `content/taichi-gpu-sim/references/gotchas.md`
