---
id: solver-pcg-algorithm
title: Preconditioned Conjugate Gradient (PCG)
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- PCG
- preconditioning
- krylov
- flexible-PCG
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-cg-algorithm
  type: refines
  weight: 0.7
- to: precond-jacobi-block-jacobi
  type: requires
  weight: 1.0
- to: precond-amg-theory
  type: requires
  weight: 1.0
- to: precond-ichol-ilu
  type: requires
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Preconditioned Conjugate Gradient (PCG)

## Summary

The Preconditioned Conjugate Gradient (PCG) algorithm accelerates standard Conjugate Gradient iterations for symmetric positive definite (SPD) linear systems Ax = b by applying a positive definite preconditioning operator M \approx A. By transforming the original system into M^{-1} A x = M^{-1} b and evaluating inner products in the M-norm, PCG clusters operator eigenvalues and reduces condition numbers cond_2(M^{-1} A), lowering iteration counts while requiring only one matrix-vector multiplication, one preconditioner solve, two vector dot products, and three AXPY updates per iteration.

## 1. Core Concept

Preconditioned Conjugate Gradient (PCG) solves large, sparse, symmetric positive definite linear systems arising from finite element discretizations of elliptic PDEs, elasticity, and monolithic phase-field fracture models. Unpreconditioned CG convergence depends directly on matrix condition number cond_2(A); for fine finite element meshes, cond_2(A) grows as O(h^{-2}), causing slow convergence. PCG introduces a symmetric positive definite preconditioning matrix M (such as point-Jacobi, block Jacobi IC, or algebraic multigrid AMG) that approximates A. Rather than forming M^{-1} A explicitly, PCG replaces the standard Euclidean inner product with the M-inner product (x, y)_M = (M x, y), ensuring M^{-1} A remains self-adjoint. In each iteration, PCG solves auxiliary linear subproblem M z_k = r_k for preconditioned residual z_k. Direction vectors p_k are maintained M^{-1} A-conjugate, minimizing the error energy norm over preconditioned Krylov subspaces without destroying sparse matrix structure.

## 2. Mathematical Formulation

**pcg-step-length-alpha**
$$
\alpha_j = \frac{(r_j, z_j)}{(A p_j, p_j)}
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 9.2, p. 277, Algorithm 9.1_

**pcg-direction-update-beta**
$$
\beta_j = \frac{(r_{j+1}, z_{j+1})}{(r_j, z_j)}
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 9.2, p. 277, Algorithm 9.1_

**m-inner-product-self-adjointness**
$$
(M^{-1} A x, y)_M = (A x, y) = (x, A y) = (x, M^{-1} A y)_M
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 9.2, p. 276_

**Notation:**
A represents global SPD stiffness matrix; M represents SPD preconditioning matrix operator; x_j represents solution vector iterate at step j; b represents load vector; r_j represents residual vector b - A x_j; z_j represents preconditioned residual vector M^{-1} r_j; p_j represents search direction vector; \alpha_j, \beta_j represent scalar update parameters; (\cdot, \cdot) represents Euclidean inner product.


## 3. Algorithmic Implementation

**preconditioned-conjugate-gradient-algorithm**
$$
\begin{algorithmic}
\State $x_0 \leftarrow \text{Initial guess}, \quad r_0 = b - A x_0, \quad z_0 = M^{-1} r_0 \quad \text{(initial preconditioner solve)}, \quad p_0 = z_0$
\For{$j = 0, 1, 2, \dots \text{ until } \|r_j\|_2 < \text{tol}$}
\State $w_j = A p_j \quad \text{(single sparse matrix-vector product)}$
\State $\alpha_j \leftarrow \frac{(r_j, z_j)}{(w_j, p_j)}$
\State $x_{j+1} \leftarrow x_j + \alpha_j p_j \quad \text{(solution update)}$
\State $r_{j+1} \leftarrow r_j - \alpha_j w_j \quad \text{(residual update)}$
\State $z_{j+1} \leftarrow M^{-1} r_{j+1} \quad \text{(preconditioner solve sweep)}$
\State $\beta_j \leftarrow \frac{(r_{j+1}, z_{j+1})}{(r_j, z_j)}$
\State $p_{j+1} \leftarrow z_{j+1} + \beta_j p_j \quad \text{(search direction update)}$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: IterMethBook_2ndEd.pdf.pdf, Section 9.2, p. 277, Algorithm 9.1; Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 4, p. 9_


## 4. Known Pitfalls

- **non-spd-preconditioner-breakdown**: PCG strictly requires both system matrix A and preconditioner M to be symmetric positive-definite (SPD) so that M defines a valid inner product (x, y)_M = (M x, y). Applying an indefinite, non-symmetric, or non-linear variable preconditioner (which changes across iterations) destroys operator self-adjointness, leading to loss of search direction A-conjugacy, residual growth, or algorithm breakdown. _(Source: IterMethBook_2ndEd.pdf.pdf, Section 9.2, p. 276; Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 3.5, p. 375)_
- **preconditioner-setup-time-dominance**: While sophisticated preconditioners like smoothed aggregation algebraic multigrid (AMG) or incomplete factorizations with higher fill levels dramatically reduce PCG iteration counts, setting up preconditioner operator M^{-1} (t_setup) can consume up to 50% of total solution time. Balancing setup overhead against Krylov iteration reduction is critical for optimizing overall wall-clock performance. _(Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 5.3.1, p. 22, Fig. 9)_

## References

- IterMethBook_2ndEd.pdf.pdf
- Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf
- Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf
- Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf
