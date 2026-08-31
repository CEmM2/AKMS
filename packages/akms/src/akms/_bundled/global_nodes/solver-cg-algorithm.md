---
id: solver-cg-algorithm
title: 'Conjugate Gradient: Algorithm & Theory'
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- CG
- krylov
- hestenes-stiefel
- SPD
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-pcg-algorithm
  type: refines
  weight: 0.7
- to: solver-direct
  type: contradicts
  weight: 0.0
- to: solver-gmres-algorithm
  type: refines
  weight: 0.7
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Conjugate Gradient: Algorithm & Theory

## Summary

The Conjugate Gradient (CG) algorithm is a Krylov subspace iterative solver for large, sparse, symmetric positive definite (SPD) linear systems Ax = b. Developed by Hestenes and Stiefel, CG computes A-conjugate search directions through Gram-Schmidt orthogonalization of residual vectors, minimizing the A-norm of the solution error at each iteration. Operating with three vector update operations (AXPYs), two inner products, and one matrix-vector product per iteration, CG avoids dense matrix inversions while achieving superlinear convergence.

## 1. Core Concept

Conjugate Gradient solves symmetric positive-definite linear systems arising from finite element discretizations of elliptic PDEs, elastodynamics, and monolithic phase-field fracture formulations. Unlike general Krylov methods like GMRES that store full Arnoldi basis sets, CG exploits the symmetry and positive definiteness of A to construct short three-term recurrences where consecutive search directions p_k are A-conjugate (p_i^T A p_j = 0 for i != j). At each iteration k, CG minimizes the energy norm (A-norm) of the error ||x* - x_k||_A over the Krylov subspace x_0 + K_k(A, r_0). Each iteration computes one matrix-vector multiplication A p_k, two vector dot products, and three vector updates (AXPYs) for solution iterate x_{k+1}, residual r_{k+1}, and direction p_{k+1}.

## 2. Mathematical Formulation

**cg-step-length-alpha**
$$
\alpha_k = \frac{r_k^T r_k}{p_k^T A p_k}
$$
_Source: Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf, Section 2.1, p. 242; IterMethBook_2ndEd.pdf.pdf, Section 6.1, p. 214_

**cg-momentum-beta**
$$
\beta_k = \frac{r_{k+1}^T r_{k+1}}{r_k^T r_k}
$$
_Source: Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf, Section 2.1, p. 242_

**cg-error-a-norm-minimization**
$$
\|x^* - x_k\|_A = \min_{q \in \mathcal{P}_{k-1}} \|(I - A q(A)) d_0\|_A
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Lemma 6.28, p. 214_

**Notation:**
A represents global symmetric positive definite stiffness/coefficient matrix; x_k represents solution vector at iteration k; b represents load/right-hand side vector; r_k represents residual vector b - A x_k; p_k represents A-conjugate search direction vector; \alpha_k represents step size scalar; \beta_k represents orthogonalization scalar; \| \cdot \|_A represents A-norm.


## 3. Algorithmic Implementation

**linear-conjugate-gradient-algorithm**
$$
\begin{algorithmic}
\State $x_0 \leftarrow \text{Initial guess}, \quad r_0 = b - A x_0, \quad p_0 = r_0$
\For{$k = 0, 1, 2, \dots \text{ until } \|r_k\|_2 < \text{tol}$}
\State $w_k = A p_k \quad \text{(single matrix-vector product)}$
\State $\alpha_k \leftarrow \frac{r_k^T r_k}{p_k^T w_k}$
\State $x_{k+1} \leftarrow x_k + \alpha_k p_k \quad \text{(AXPY update 1)}$
\State $r_{k+1} \leftarrow r_k - \alpha_k w_k \quad \text{(AXPY update 2)}$
\State $\beta_k \leftarrow \frac{r_{k+1}^T r_{k+1}}{r_k^T r_k}$
\State $p_{k+1} \leftarrow r_{k+1} + \beta_k p_k \quad \text{(AXPY update 3)}$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf, Section 2.1, p. 242; IterMethBook_2ndEd.pdf.pdf, Section 6.1, p. 214_


## 4. Known Pitfalls

- **cg-indefinite-matrix-breakdown**: Standard Conjugate Gradient relies strictly on positive definiteness of coefficient matrix A (p_k^T A p_k > 0). If applied to indefinite, singular, or non-symmetric systems, denominator p_k^T A p_k can vanish or become negative, causing division by zero, loss of descent directions, or catastrophic divergence. _(Source: IterMethBook_2ndEd.pdf.pdf, Section 6.1, p. 214; Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 1, p. 3)_
- **floating-point-orthogonality-loss**: In finite precision arithmetic, residual vectors r_k gradually lose mutual orthogonality as iteration counts increase. This leads to residual delay and iteration inflation, requiring reorthogonalization or preconditioning to maintain superlinear convergence. _(Source: IterMethBook_2ndEd.pdf.pdf, Section 6.1, p. 214)_

## References

- IterMethBook_2ndEd.pdf.pdf
- Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf
- Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf
- Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf
