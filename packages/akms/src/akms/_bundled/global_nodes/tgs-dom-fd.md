---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-gpu-sim/domains/fd.md
context_size: small
domain: gpu-simulation
edges:
- note: Stencil kernels use block-dim and tiling patterns
  to: tgs-ref-kernel-patterns
  type: requires
  weight: 0.7
- note: FD time-stepping needs stable integration schemes
  to: tgs-dom-time-integration
  type: feeds-into
  weight: 0.6
id: tgs-dom-fd
reading_priority: full
source: human
status: established
subdomain: taichi-fd
tags:
- finite-difference
- stencils
- double-buffering
- CFL
- PDE-discretization
- heat-equation
title: Finite Differences Domain Playbook
---

# Finite Differences Domain Playbook

## Summary

Finite difference domain playbook: stencil-based discretization for PDEs (heat, wave, diffusion). Covers double-buffering strategy (u_old/u_new to prevent races), grid field layout, domain parameters (dx, dt), GPU-friendly kernel structure (interior separate from boundaries), CFL stability constraints, and explicit/semi-implicit time-stepping patterns.

**Parent skill:** `skill-taichi-gpu-sim`
**Content:** `content/taichi-gpu-sim/domains/fd.md`
