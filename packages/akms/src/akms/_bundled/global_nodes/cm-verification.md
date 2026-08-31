---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/computational-mechanics/reference/verification-benchmarks.md
context_size: medium
domain: computational-mechanics
edges:
- note: Benchmark definitions feed test generation conventions
  to: skill-gen-test
  type: feeds-into
  weight: 0.7
- note: Verification benchmarks inform review testing criteria
  to: tsr-ref-testing-verification
  type: feeds-into
  weight: 0.6
id: cm-verification
reading_priority: full
source: human
status: established
subdomain: verification
tags:
- verification
- benchmarks
- Taylor-anvil
- Sneddon
- RVE-inclusion
- patch-test
- energy-balance
title: Verification & Validation Benchmark Suite
---

# Verification & Validation Benchmark Suite

## Summary

Benchmark suite for validating mechanics implementations: Taylor anvil impact (high-rate plasticity + thermo), Sneddon Mode-I crack (phase-field), periodic RVE with inclusion (FFT/contrast), biaxial sheet tension (anisotropy + necking). Specifies metrics (energy balance, crack bandwidth, convergence iterations), verification checks, and required docstring headers for test functions. Cross-cutting node used by all constitutive and solver implementations.

## Related templates

- `content/computational-mechanics/templates/validation_benchmarks.py`
- `content/computational-mechanics/templates/pytest_benchmarks_template.py`

**Parent skill:** `skill-computational-mechanics`
**Content:** `content/computational-mechanics/reference/verification-benchmarks.md`
