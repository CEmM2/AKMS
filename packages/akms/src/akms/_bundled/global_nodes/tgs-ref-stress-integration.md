---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-gpu-sim/references/stress-integration.md
context_size: large
domain: gpu-simulation
edges:
- note: Uses Voigt/Mandel conventions from continuum-tensors
  to: tgs-ref-continuum-tensors
  type: requires
  weight: 0.9
- note: Quick-ref provides sign conventions
  to: tgs-ref-conventions-quickref
  type: requires
  weight: 0.7
- note: GPU implementation of corotational objective rate theory
  to: cm-objective-rates
  type: implements
  weight: 0.9
- note: Implements Perzyna viscoplastic integration on GPU
  to: cm-viscoplastic-thermo
  type: implements
  weight: 0.9
- note: Stress pipeline uses NaN/clamping safeguards
  to: tgs-ref-numerical-safeguards
  type: feeds-into
  weight: 0.7
id: tgs-ref-stress-integration
reading_priority: full
source: human
status: established
subdomain: taichi
tags:
- stress-integration
- stress-update
- corotational
- J2-plasticity
- phase-field
- EOS-coupling
title: Stress Update Pipeline (Stress_Update6)
---

# Stress Update Pipeline (Stress_Update6)

## Summary

Exact stress update pipeline (Stress_Update6) for this codebase: objective corotational J2-closest-point-projection in midpoint frame, phase-field degradation (ω_s, ω_t), optional EOS hydrostatic coupling, work/temperature tracking. Unified 6-output interface with hat notation for the corotational frame. Implementation matches TLCorotated kinematics and Hughes–Winget rotation. Central to all constitutive integration in the codebase.

**Parent skill:** `skill-taichi-gpu-sim`
**Content:** `content/taichi-gpu-sim/references/stress-integration.md`
