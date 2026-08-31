---
id: precond-geometric-mg
title: Geometric & p-Multigrid
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- GMG
- p-multigrid
- geometric-multigrid
- hierarchical
- brown-2022
status: established
confidence: 0.9
source: hybrid
edges:
- to: precond-amg-theory
  type: refines
  weight: 0.7
- to: solver-pcg-algorithm
  type: feeds-into
  weight: 0.5
- to: solver-matrix-free-operator
  type: requires
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Geometric & p-Multigrid

## Summary

Geometric and p-multigrid methods accelerate iterative linear solvers for discretized partial differential equations by constructing hierarchical coarsening spaces. While traditional geometric multigrid (GMG) relies on nested spatial mesh refinements, p-multigrid (p-MG) constructs coarse spaces by reducing the polynomial degree of high-order finite element spaces (e.g., Q_p down to linear Q_1) on a fixed mesh geometry. When combined with matrix-free partial assembly for fine-level operators, Chebyshev polynomial smoothers, and algebraic multigrid (AMG) or direct solvers on the coarsest linear level, matrix-free p-multigrid achieves optimal algorithmic scaling and high throughput on parallel CPU and GPU architectures.

## 1. Core Concept

High-order finite element discretizations (Q_p elements for p >= 2) achieve high spatial accuracy per degree of freedom, but full assembly of sparse tangent stiffness matrices causes severe memory consumption and memory bandwidth bottlenecks. Matrix-free p-multigrid (p-MG) circumvents sparse matrix storage by evaluating element operations on-the-fly via quadrature-point tensor contractions (partial assembly). In p-MG, error smoothing on high-order fine spaces (Q_p) is performed using 2nd-order Chebyshev-polynomial Jacobi iterations targeting upper eigenspectrum bounds estimated via Lanczos iterations. Coarse-grid restriction P_{c \to f}^T and prolongation P_{c \to f} map solution residuals between polynomial degree levels. Once coarsened down to the linear element level (Q_1), operator stiffness matrices are assembled into sparse CSR matrices and solved via algebraic multigrid (e.g., hypre BoomerAMG or PETSc GAMG) or direct factorization.

## 2. Mathematical Formulation

**p-mg-galerkin-operator**
$$
A_c = P_{c \to f}^T A_f P_{c \to f}
$$
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section III.A, p. 3_

**chebyshev-jacobi-smoother-operator**
$$
u^{(l+1)} = u^{(l)} + \hat{M}^{-1} (b - A_f u^{(l)})
$$
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section III.A, p. 3_

**matrix-free-operator-action**
$$
A u = \sum_e \mathcal{P}^T \mathcal{E}^T B^T D \mathcal{E} \mathcal{P} u
$$
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section II.B, p. 2, Fig. 1_

**Notation:**
A_f, A_c represent fine and coarse matrix-free operators; P_{c \to f} represents prolongation operator from coarse to fine level; u_f, u_c represent fine and coarse displacement vectors; \hat{M}^{-1} represents 2nd-order Chebyshev polynomial smoother; \lambda_{\max} represents maximum eigenvalue of preconditioned operator; Q_p represents tensor-product element space of degree p.


## 3. Algorithmic Implementation

**matrix-free-p-multigrid-v-cycle**
$$
\begin{algorithmic}
\State $\text{Given fine-grid residual } r_f = b - A_f u_f \text{ on high-order space } Q_p$
\State $u_f \leftarrow u_f + \hat{M}^{-1} (b - A_f u_f) \quad \text{(Pre-smoothing via Chebyshev/Jacobi iteration)}$
\State $r_c = P_{c \to f}^T (b - A_f u_f) \quad \text{(Restrict residual to coarse polynomial level } Q_c\text{)}$
\If{$\text{Coarse space } Q_c \text{ is linear } Q_1$}
\State $\text{Assemble } Q_1 \text{ sparse CSR matrix } A_1 \text{ and solve } A_1 e_1 = r_c \text{ via AMG (hypre BoomerAMG) or Cholesky}$
\Else
\EndIf
\State $u_f \leftarrow u_f + P_{c \to f} e_c \quad \text{(Prolong error correction to fine grid)}$
\State $u_f \leftarrow u_f + \hat{M}^{-1} (b - A_f u_f) \quad \text{(Post-smoothing via Chebyshev/Jacobi iteration)}$
\Return $u_f$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section III.A, p. 3, Fig. 2_


## 4. Known Pitfalls

- **amg-coarse-grid-setup-latency-bottleneck**: In matrix-free p-multigrid solvers, while fine-level Q_p operator evaluations and Chebyshev smoothing execute rapidly via GPU tensor contractions, assembling and setting up the Q_1 coarse-grid AMG preconditioner (e.g., BoomerAMG) accounts for more than half of total preconditioner setup time despite Q_1 having 8x fewer degrees of freedom than Q_2. _(Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section V.C, p. 6, Fig. 10)_
- **element-stretching-convergence-degradation**: High aspect-ratio element stretching degrades p-multigrid coarse-grid convergence and inflates iteration counts (e.g., condition numbers rising from ~14 to over 400 for 4:1 aspect ratios). Custom tuning of AMG coarsening thresholds and smoother relaxation for stretched element regions is required to maintain convergence robustness. _(Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf, Section V.D, p. 6, Table III)_
- **unstructured-mesh-hierarchy-generation-limitation**: Geometric multigrid (GMG) requires nested sequences of refined unstructured meshes, which are difficult and non-trivial to generate automatically for complex 3D engineering geometries. This spatial hierarchy requirement limits standard GMG applicability compared to p-multigrid or algebraic multigrid (AMG). _(Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 1, p. 3)_

## References

- Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf
- Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf
- Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf
- Trotter et al_2023_Targeting performance and user-friendliness.pdf
