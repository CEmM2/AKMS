---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-gpu-sim/references/continuum-tensors.md
context_size: medium
domain: gpu-simulation
edges:
- note: Implements the theoretical notation as concrete conventions
  to: cm-notation-cheatsheet
  type: implements
  weight: 0.9
- note: Quick-reference distills this into a lookup table
  to: tgs-ref-conventions-quickref
  type: feeds-into
  weight: 0.9
- note: Stress update pipeline uses these exact conventions
  to: tgs-ref-stress-integration
  type: feeds-into
  weight: 0.9
id: tgs-ref-continuum-tensors
reading_priority: full
source: human
status: established
subdomain: taichi
tags:
- Voigt-convention
- Mandel-basis
- corotational-stress
- tensorial-Voigt
- implementation-truth
- PK2
title: Continuum Tensor Conventions (Implementation Truth)
---

# Continuum Tensor Conventions (Implementation Truth)

## Summary

Implementation-truth document specifying exact tensor conventions used in the codebase for FEM/MPM constitutive updates: Cauchy stress updated in corotational frame, tensorial Voigt packing [xx,yy,zz,xy,xz,yz] (unscaled shear), Mandel similarity transforms for 6×6 tangents. Reconciles material measures (PK2) for Total Lagrangian with spatial Cauchy updates. This is the authoritative convention document — code must match it.

**Parent skill:** `skill-taichi-gpu-sim`
**Content:** `content/taichi-gpu-sim/references/continuum-tensors.md`
