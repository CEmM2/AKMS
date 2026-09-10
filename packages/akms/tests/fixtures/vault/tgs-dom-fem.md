---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-gpu-sim/domains/fem.md
context_size: medium
domain: gpu-simulation
edges:
- note: Implements TL kinematics as Taichi FEM kernels
  to: cm-kinematics-tl
  type: implements
  weight: 0.9
- note: FEM kernels follow kernel pattern house style
  to: tgs-ref-kernel-patterns
  type: requires
  weight: 0.8
- note: Uses tensorial-Voigt stress conventions
  to: tgs-ref-continuum-tensors
  type: requires
  weight: 0.8
- note: Assembly calls the Stress_Update6 pipeline
  to: tgs-ref-stress-integration
  type: requires
  weight: 0.9
id: tgs-dom-fem
reading_priority: full
source: human
status: established
subdomain: taichi-fem
tags:
- FEM
- Total-Lagrangian
- corotational
- element-assembly
- quadrature
- internal-force
- GPU
title: FEM Domain Playbook (Total Lagrangian Corotational)
---

# FEM Domain Playbook (Total Lagrangian Corotational)

## Summary

FEM domain playbook for Total Lagrangian corotational formulation: mesh topology storage (x0, x, elem_conn), quadrature state layout (stress in spatial Cauchy tensorial-Voigt, peeq, T, damage scalars), four-pass kernel structure (kinematics+stress, internal force, external forces, solver). Includes PK2 conversion for TL assembly and keeps boundary logic separate from interior.

**Parent skill:** `skill-taichi-gpu-sim`
**Content:** `content/taichi-gpu-sim/domains/fem.md`
