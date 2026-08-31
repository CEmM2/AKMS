---
id: solver-direct
title: Direct Sparse Solvers (LU, Cholesky, LDLT)
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- direct
- lu
- cholesky
- sparse
- fill-in
- metis
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-cg-algorithm
  type: contradicts
  weight: 0.0
- to: solver-gmres-algorithm
  type: contradicts
  weight: 0.0
- to: precond-ichol-ilu
  type: feeds-into
  weight: 0.5
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Direct Sparse Solvers (LU, Cholesky, LDLT)

## Summary

Direct sparse solvers compute exact solutions x = A^-1 b for discretized linear algebraic equations in computational mechanics through matrix factorizations such as LU, Cholesky (L L^T), and L D U decomposition. Operating through a structured four-phase pipeline—preordering, symbolic factorization, numerical factorization, and triangular solve sweeps—direct solvers eliminate iteration-count uncertainty, but incur substantial memory and computational overhead due to fill-in nonzeros generated during elimination.

## 1. Core Concept

Direct sparse solvers compute exact solutions to linear systems Ax = b arising from finite element discretizations without relying on iterative convergence criteria or preconditioning operators. For symmetric positive-definite (SPD) stiffness matrices, Cholesky factorization factors A into lower triangular matrix L such that A = L L^T; for general unsymmetric or indefinite systems, LU or L D U factorizations decompose A = L U or A = L D U. A standard sparse direct solver operates in four distinct phases: (1) Preordering, where fill-reducing graph permutations (such as minimum degree or nested dissection ordering) reorder matrix rows and columns to minimize bandwidth and fill-in; (2) Symbolic Factorization, which sets up the sparsity pattern NZ(L + U) of the factored matrices without numerical floating-point operations; (3) Numerical Factorization, where actual numerical entries of L and U are computed; and (4) Triangular Solve Sweeps, where forward substitution L y = P b and backward substitution U z = y produce the final solution x = P^T z. While direct solvers excel as coarse-grid exact sub-solvers in multigrid hierarchies or for systems with multiple right-hand sides, factorization fill-in (creation of new nonzeros in L and U) generates heavy memory and arithmetic overhead for large 3D discretizations.

## 2. Mathematical Formulation

**sparse-direct-lu-factorization**
$$
A = L U \quad \text{or} \quad A = L D U
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 3.6, p. 96_

**cholesky-factorization**
$$
A = L L^T
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 3.6, p. 96_

**triangular-solve-sweeps**
$$
L y = P b, \quad U z = y, \quad x = Q z
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 3.6, p. 96_

**Notation:**
A represents global sparse stiffness matrix; L, U represent lower and upper triangular factor matrices; D represents diagonal matrix; P, Q represent fill-reducing permutation matrices; b represents load vector; x represents primal solution vector; NZ(A) represents nonzero pattern of A.


## 3. Algorithmic Implementation

**sparse-direct-solver-four-phase-pipeline**
$$
\begin{algorithmic}
\State $\text{Phase 1 (Preordering): Compute fill-reducing permutation matrix } P \text{ via minimum degree or nested dissection ordering}$
\State $\text{Phase 2 (Symbolic Factorization): Determine nonzero pattern } \text{NZ}(L + U) \text{ purely from graph connectivity without numerical values}$
\State $\text{Phase 3 (Numerical Factorization): Compute numerical entries of factors } L \text{ and } U \text{ such that } P A P^T = L U \text{ (or } L L^T\text{)}$
\State $\text{Phase 4 (Triangular Sweeps): Solve } L y = P b \text{ via forward substitution sweep, solve } U z = y \text{ via backward substitution sweep, and set } x = P^T z$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: IterMethBook_2ndEd.pdf.pdf, Section 3.6, p. 96_

**rcm-reordering-algorithm**
$$
\begin{algorithmic}
\State $\text{Identify pseudo-peripheral initial node } v \text{ with minimal degree in adjacency graph}$
\State $\text{Traverse graph level sets via Breadth-First Search (BFS), ordering adjacent nodes by increasing degree}$
\State $\text{Reverse generated node permutation list } \pi \text{ to form Reverse Cuthill-McKee (RCM) ordering}$
\State $\text{Construct reordered bandwidth-reduced system matrix } A_{\text{RCM}} = P_{\text{RCM}} A P_{\text{RCM}}^T$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: IterMethBook_2ndEd.pdf.pdf, Section 3.3.3, p. 84, Algorithm 3.1_


## 4. Known Pitfalls

- **sparse-direct-fill-in-memory-explosion**: During numerical elimination (LU or Cholesky factorization), arithmetic updates generate new nonzeros (fill-in) in matrix entries that were zero in original matrix A. For large 3D finite element discretizations, fill-in dramatically increases memory requirements and floating-point operation counts, causing out-of-memory solver failure on fine meshes. _(Source: IterMethBook_2ndEd.pdf.pdf, Section 3.6, p. 96; Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf, Section I, p. 1)_
- **triangular-solve-sequential-bottleneck**: Forward and backward triangular solves (L y = b and U x = y) require row-by-row recursive data dependencies that create severe sequential bottlenecks on parallel CPU and GPU architectures, limiting parallel speedup compared to matrix-vector multiplications in Krylov solvers. _(Source: IterMethBook_2ndEd.pdf.pdf, Section 10.3, p. 301; Section 12.1, p. 376)_

## References

- IterMethBook_2ndEd.pdf.pdf
- Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf
- Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf
