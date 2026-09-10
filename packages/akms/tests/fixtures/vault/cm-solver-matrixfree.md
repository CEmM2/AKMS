---
akms_schema: v2
confidence: 0.9
confidence_floor: 0.65
content_ref: content/computational-mechanics/reference/solver-architecture-matrixfree.md
context_size: large
domain: computational-mechanics
edges:
- note: Solver operates on tensor-valued residuals
  to: cm-tensor-calculus
  type: requires
  weight: 0.5
- note: FFT solver architecture builds on Lippmann-Schwinger
  to: cm-fft-galerkin
  type: requires
  weight: 0.7
- note: Architecture implemented as Taichi GPU solver kernels
  to: tgs-dom-linear-solvers
  type: feeds-into
  weight: 0.9
id: cm-solver-matrixfree
reading_priority: full
source: human
status: established
subdomain: solvers
tags:
- matrix-free
- Newton-Krylov
- CG
- GMRES
- JVP
- preconditioning
- solver-architecture
title: Matrix-Free Newton-Krylov Solver Architecture
---

# Matrix-Free Newton-Krylov Solver Architecture

## Summary

Defines the matrix-free Newton-Krylov solver architecture for both FEM and FFT. Specifies residual evaluation, Jacobian-vector-product (JVP) computation, Krylov iterators (CG for SPD, GMRES for nonsymmetric), preconditioning strategies (Jacobi, p-multigrid), and convergence criteria. Addresses element-loop-based assembly for FEM and Lippmann-Schwinger projections for FFT without explicit global matrices.

## Related templates

- `content/computational-mechanics/templates/newton_krylov_matrixfree.py`

**Parent skill:** `skill-computational-mechanics`
**Content:** `content/computational-mechanics/reference/solver-architecture-matrixfree.md`
