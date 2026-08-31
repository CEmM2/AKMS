---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-sim-reviewer/references/testing-verification.md
context_size: small
domain: project-meta
edges:
- note: Review testing references verification benchmarks
  to: cm-verification
  type: requires
  weight: 0.7
- note: Testing tier conventions feed test generation skill
  to: skill-gen-test
  type: feeds-into
  weight: 0.8
id: tsr-ref-testing-verification
reading_priority: full
source: human
status: established
subdomain: code-review
tags:
- testing
- verification
- tiers
- regression
- tolerance-guidelines
- SymPy
- determinism
title: Testing & Verification Review Practices
---

# Testing & Verification Review Practices

## Summary

Tiered testing verification strategy for review: Tier A (pure math unit tests <1s), Tier B (Taichi kernel units), Tier C (integration/patch tests), Tier D (performance). Coverage expectations per code type, regression testing protocols, determinism requirements (fixed seeds, no flakiness), tolerance guidelines (f32: rtol=1e-5, f64: rtol=1e-10), and SymPy verification for complex math.

**Parent skill:** `skill-taichi-sim-reviewer`
**Content:** `content/taichi-sim-reviewer/references/testing-verification.md`
