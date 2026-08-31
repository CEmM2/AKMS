---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-gpu-sim/domains/mpm.md
context_size: medium
domain: gpu-simulation
edges:
- note: P2G scatter uses atomics; kernel pattern critical
  to: tgs-ref-kernel-patterns
  type: requires
  weight: 0.9
- note: Particle/grid layout affects performance
  to: tgs-ref-data-layout
  type: requires
  weight: 0.7
- note: MPM uses explicit time-stepping with CFL
  to: tgs-dom-time-integration
  type: feeds-into
  weight: 0.6
id: tgs-dom-mpm
reading_priority: full
source: human
status: established
subdomain: taichi-mpm
tags:
- MPM
- P2G
- G2P
- APIC
- B-spline
- atomic-scatter
- particle-grid
title: Material Point Method (MPM) Domain Playbook
---

# Material Point Method (MPM) Domain Playbook

## Summary

MPM domain playbook: particle Lagrangian data (x, v, C affine, F, J, mass), grid Eulerian transient storage (grid_v, grid_m), canonical 4-kernel pipeline (clear → P2G scatter → grid update → G2P gather). B-spline interpolation weights/gradients, APIC affine reduction, and atomic pattern optimization. Particles persist; grid resets each timestep.

**Parent skill:** `skill-taichi-gpu-sim`
**Content:** `content/taichi-gpu-sim/domains/mpm.md`
