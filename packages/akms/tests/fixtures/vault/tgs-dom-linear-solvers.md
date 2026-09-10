---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/taichi-gpu-sim/domains/linear-solvers.md
context_size: medium
domain: gpu-simulation
edges:
- note: GPU implementation of matrix-free Newton-Krylov architecture
  to: cm-solver-matrixfree
  type: implements
  weight: 0.9
- note: Solver kernels need efficient reduction patterns
  to: tgs-ref-kernel-patterns
  type: requires
  weight: 0.7
id: tgs-dom-linear-solvers
reading_priority: full
source: human
status: established
subdomain: taichi-solvers
tags:
- linear-solvers
- CG
- PCG
- matrix-free
- Jacobi
- preconditioning
- GPU-hygiene
title: GPU Linear Solvers (CG/PCG)
---

# GPU Linear Solvers (CG/PCG)

## Summary

GPU-friendly iterative solver patterns (CG/PCG for SPD systems): operator contract as matrix-free kernel, vector operations + reductions, CG iteration structure (Ap, alpha, line search, beta updates), GPU hygiene (fused kernels, 0D field reductions for dot products), Jacobi preconditioning baseline. Avoids host syncs and minimizes kernel launches within iterations.

**Parent skill:** `skill-taichi-gpu-sim`
**Content:** `content/taichi-gpu-sim/domains/linear-solvers.md`
