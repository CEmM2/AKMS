---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-gpu-sim/references/numerical-safeguards.md
context_size: medium
domain: gpu-simulation
edges:
- note: Safeguards apply to Voigt-packed stress fields
  to: tgs-ref-continuum-tensors
  type: requires
  weight: 0.6
- note: Safeguards protect the stress update pipeline
  to: tgs-ref-stress-integration
  type: requires
  weight: 0.7
- note: Safeguard assertions feed into testing strategy
  to: tgs-ref-testing-validation
  type: feeds-into
  weight: 0.7
id: tgs-ref-numerical-safeguards
reading_priority: full
source: human
status: established
subdomain: taichi
tags:
- numerical-safety
- NaN-detection
- clamping
- physical-invariants
- safeguards
- diagnostics
title: Numerical Safeguards & Diagnostic Policies
---

# Numerical Safeguards & Diagnostic Policies

## Summary

Repository-wide numerical safety policies: NaN/Inf scanning kernels, range clamping for deformation gradient (J_min/J_max), yield surface intersection checks, divergence-free enforcement, and diagnostic counters. Balances physics correctness (fail loudly when physically impossible) with graceful numerical degradation for edge cases.

**Parent skill:** `skill-taichi-gpu-sim`
**Content:** `content/taichi-gpu-sim/references/numerical-safeguards.md`
