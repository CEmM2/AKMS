---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-gpu-sim/references/testing-and-validation.md
context_size: medium
domain: gpu-simulation
edges:
- note: Tests verify adherence to tensor conventions
  to: tgs-ref-continuum-tensors
  type: requires
  weight: 0.7
- note: Tests exercise numerical safeguard assertions
  to: tgs-ref-numerical-safeguards
  type: requires
  weight: 0.6
- note: Testing strategy feeds test generation conventions
  to: skill-gen-test
  type: feeds-into
  weight: 0.8
id: tgs-ref-testing-validation
reading_priority: full
source: human
status: established
subdomain: taichi
tags:
- testing
- unit-tests
- SymPy
- verification
- regression
- Taichi-kernels
- tiers
title: Testing & Validation Strategy (Tiers A–D)
---

# Testing & Validation Strategy (Tiers A–D)

## Summary

Tiered testing strategy: Tier A (pure math/SymPy, <1s), Tier B (kernel unit tests), Tier C (integration/patch tests), Tier D (performance regression). Emphasizes tensor convention verification, mathematical identity checking via SymPy, and small-problem deterministic Taichi kernels. Primary conventions (tensorial Voigt, corotational, pressure-sign) must match both implementation and test framework.

**Parent skill:** `skill-taichi-gpu-sim`
**Content:** `content/taichi-gpu-sim/references/testing-and-validation.md`
