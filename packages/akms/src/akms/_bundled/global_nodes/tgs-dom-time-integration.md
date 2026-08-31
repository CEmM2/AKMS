---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-gpu-sim/domains/time-integration.md
context_size: small
domain: gpu-simulation
edges:
- note: Implicit stepping uses FEM assembly
  to: tgs-dom-fem
  type: requires
  weight: 0.6
- note: Implicit Newton needs CG/PCG solver
  to: tgs-dom-linear-solvers
  type: requires
  weight: 0.7
- note: Time integrators call stress update at each step
  to: tgs-ref-stress-integration
  type: requires
  weight: 0.7
id: tgs-dom-time-integration
reading_priority: full
source: human
status: established
subdomain: taichi-timeint
tags:
- time-integration
- explicit
- implicit
- Newton-Krylov
- substepping
- stability
- midpoint
title: 'Time Integration: Explicit & Implicit Stepping'
---

# Time Integration: Explicit & Implicit Stepping

## Summary

Time stepping structure: explicit (MPM, sometimes FEM) — compute forces → update velocities → update positions → apply BCs. Implicit — Newton loop with residual assembly, tangent operator apply, CG solve. Substepping policy when plasticity/damage stiffness or EOS requires finer dt. Midpoint kinematics coupling for objective stress integration.

**Parent skill:** `skill-taichi-gpu-sim`
**Content:** `content/taichi-gpu-sim/domains/time-integration.md`
