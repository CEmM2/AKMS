---
id: precond-ichol-ilu
title: Incomplete Cholesky / ILU Factorization
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- preconditioner
- IC
- ILU
- incomplete-factorization
- GPU-challenge
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-pcg-algorithm
  type: feeds-into
  weight: 0.5
- to: solver-direct
  type: refines
  weight: 0.7
- to: precond-gpu-alternatives
  type: contradicts
  weight: 0.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Incomplete Cholesky / ILU Factorization

## Summary

Incomplete Cholesky (IC) and Incomplete LU (ILU) factorizations compute sparse approximations L \tilde{U} \approx A (or \tilde{L} \tilde{L}^T \approx A for symmetric positive-definite matrices) by discarding fill-in entries outside a prescribed sparsity pattern or below a drop tolerance threshold. Used extensively as standalone preconditioners or as local block solvers in block Jacobi and domain decomposition frameworks, IC and ILU significantly reduce Krylov iteration counts compared to point-Jacobi scaling, though forward and backward triangular solves introduce sequential dependency bottlenecks on parallel computing architectures.

## 1. Core Concept

Incomplete factorizations modify Gaussian elimination to construct sparse lower and upper triangular factors \tilde{L} and \tilde{U} such that error matrix R = \tilde{L} \tilde{U} - A meets specific sparsity or threshold constraints. Zero fill-in factorizations (ILU(0) and IC(0)) restrict \tilde{L} and \tilde{U} strictly to the nonzero pattern of original matrix A, avoiding dynamic memory allocation during setup. Higher-order level-of-fill variants (ILU(p)) and threshold-based strategies (ILUT) allow fill-in based on topological graph paths or numerical magnitude, approaching exact direct LU/Cholesky factorizations as fill levels increase. For symmetric positive-definite systems arising in finite element discretizations (such as monolithic phase-field fracture or linear elasticity), IC(0) provides a positive-definite preconditioner that reduces Conjugate Gradient iteration counts by approximately 4-5x compared to point-Jacobi preconditioning. However, applying preconditioner solve M^{-1} r = \tilde{U}^{-1} \tilde{L}^{-1} r requires forward and backward substitution steps with inherently sequential, row-wise recurrences, creating fine-grained data dependencies that limit parallel scaling on vector and parallel hardware.

## 2. Mathematical Formulation

**ilu0-split-preconditioning-matrix**
$$
M = (D - E) D^{-1} (D - F)
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 10.3.2, p. 308_

**general-ikj-gaussian-elimination-ilu**
$$
a_{ij} \leftarrow a_{ij} - a_{ik} a_{kj} \quad \text{for } (i, j) \in \text{NZ}(A)
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 10.3.2, p. 307_

**incomplete-cholesky-zero-fill**
$$
M = \tilde{L} \tilde{L}^T
$$
_Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 4, p. 10; IterMethBook_2ndEd.pdf.pdf, Section 10.5, p. 332_

**Notation:**
A represents global assembled stiffness matrix; \tilde{L}, \tilde{U} represent sparse incomplete lower and upper triangular factor matrices; R represents factorization error residual matrix; D represents recursively updated diagonal matrix; -E, -F represent strict lower and upper triangular parts of A; \tau represents drop tolerance threshold parameter; p, lfil represent fill-in level parameters.


## 3. Algorithmic Implementation

**ikj-incomplete-lu-factorization-ilu0**
$$
\begin{algorithmic}
\State $\text{Given matrix } A \text{ with nonzero sparsity pattern } \text{NZ}(A)$
\For{$i = 2 \text{ to } n$}
\For{$k = 1 \text{ to } i - 1 \text{ and } (i, k) \in \text{NZ}(A)$}
\State $a_{ik} \leftarrow a_{ik} / a_{kk}$
\For{$j = k + 1 \text{ to } n \text{ and } (i, j) \in \text{NZ}(A)$}
\State $a_{ij} \leftarrow a_{ij} - a_{ik} a_{kj}$
\EndFor
\EndFor
\EndFor
\Return $\tilde{L} = \text{tril}(A, -1) + I, \quad \tilde{U} = \text{triu}(A)$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: IterMethBook_2ndEd.pdf.pdf, Section 10.3.2, p. 307, Algorithm 10.3_

**block-jacobi-ic0-preconditioner-solve**
$$
\begin{algorithmic}
\State $\text{Factorize local diagonal blocks } M_i = \tilde{L}_i \tilde{L}_i^T \text{ using zero fill-in Incomplete Cholesky IC(0)}$
\For{$i = 1 \text{ to } N_p \quad \text{(parallel subdomain loop)}$}
\State $\text{Solve } \tilde{L}_i y_i = r_i \text{ via forward substitution}$
\State $\text{Solve } \tilde{L}_i^T z_i = y_i \text{ via backward substitution}$
\EndFor
\State $z = [z_1; z_2; \dots; z_{N_p}]$
\Return $z$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 4, p. 10; Section 5.3.1, p. 21_


## 4. Known Pitfalls

- **sequential-triangular-solve-parallel-bottleneck**: Applying incomplete factorization preconditioners M^{-1} r = \tilde{U}^{-1} \tilde{L}^{-1} r requires forward and backward triangular solves with recursive, row-by-row data dependencies. These sequential dependencies limit fine-grained concurrency and vectorization on parallel hardware architectures, making point-Jacobi or polynomial smoothers more effective on massively parallel vector processors. _(Source: IterMethBook_2ndEd.pdf.pdf, Section 10.3, p. 301; Section 12.1, p. 376; Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 5.3.2, p. 23)_
- **zero-pivot-and-unstable-ilut-factorization**: Incomplete factorizations applied to non-M-matrices or non-positive-definite systems can encounter zero or near-zero pivot elements a_{kk} \approx 0 during elimination, producing unstable factors where \|\tilde{U}^{-1} \tilde{L}^{-1}\| is extremely large and causing outer Krylov iterations to diverge. Pivoting strategies (ILUTP) or diagonal shifts are required to maintain stability. _(Source: IterMethBook_2ndEd.pdf.pdf, Section 10.4.3, p. 328; Section 10.4.4, p. 327)_

## References

- IterMethBook_2ndEd.pdf.pdf
- Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf
- Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf
