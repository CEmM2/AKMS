---
id: solver-minres
title: MINRES for Symmetric Indefinite Systems
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- MINRES
- krylov
- symmetric-indefinite
- saddle-point
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-cg-algorithm
  type: contradicts
  weight: 0.0
- to: solver-gmres-algorithm
  type: refines
  weight: 0.7
- to: precond-field-split-block
  type: requires
  weight: 1.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# MINRES for Symmetric Indefinite Systems

## Summary

The Minimal Residual (MR) and Generalized Minimal Residual (GMRES) Krylov subspace iterative methods solve linear systems Ax = b where coefficient matrix A is symmetric indefinite or non-symmetric. Unlike standard Conjugate Gradient (CG), which requires symmetric positive-definite (SPD) operators and fails when encountering non-positive curvature, residual-minimizing Krylov solvers compute solution updates x_m = x_0 + V_m y_m that explicitly minimize the Euclidean residual norm ||b - A x_m||_2 over Krylov subspace K_m(A, r_0), providing robust convergence for saddle-point systems and indefinite block discretizations.

## 1. Core Concept

In computational mechanics and constrained optimization, discretized linear systems often exhibit saddle-point block structures \begin{bmatrix} A & B \\ B^T & 0 \end{bmatrix} with zero diagonal blocks for Lagrange multipliers or constraint variables. Because coefficient matrix A is indefinite, applying standard Conjugate Gradient (CG) can lead to division by zero or divergence when p_k^T A p_k \le 0. Residual-minimizing Krylov subspace solvers (such as Minimal Residual and GMRES) circumvent positive-definiteness requirements by constructing orthonormal Krylov basis vectors V_m via the Arnoldi process (or Lanczos process for symmetric systems) such that A V_m = V_{m+1} \bar{H}_m. Solution updates x_m = x_0 + V_m y_m are computed by finding vector y_m that minimizes least-squares residual functional ||\beta e_1 - \bar{H}_m y||_2 via Givens plane rotations. For saddle-point formulations, pairing residual-minimizing Krylov solvers with block field-split preconditioners or Schur complement solvers eliminates indefiniteness bottlenecks.

## 2. Mathematical Formulation

**krylov-residual-minimization**
$$
x_m = x_0 + V_m y_m \quad \text{where } y_m = \arg\min_{y \in \mathbb{R}^m} \|\beta e_1 - \bar{H}_m y\|_2
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 6.5.1, p. 172_

**saddle-point-indefinite-system**
$$
\begin{bmatrix} A & B \\ B^T & 0 \end{bmatrix} \begin{bmatrix} x \\ y \end{bmatrix} = \begin{bmatrix} b \\ c \end{bmatrix}
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 8.4, p. 268; Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 6.1, p. 388_

**givens-rotation-least-squares-solve**
$$
Q_m (\beta e_1 - \bar{H}_m y) = \begin{bmatrix} \bar{g}_m - R_m y \\ \gamma_{m+1} \end{bmatrix}
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 6.5.3, pp. 174-177_

**Notation:**
A represents global coefficient matrix; x_m represents solution vector at Krylov iteration m; r_0 represents initial residual vector b - A x_0; V_m represents matrix of orthonormal Krylov basis vectors; \bar{H}_m represents upper Hessenberg or tridiagonal matrix; Q_m represents sequence of Givens rotation matrices; \beta represents initial residual Euclidean norm.


## 3. Algorithmic Implementation

**minimal-residual-krylov-algorithm**
$$
\begin{algorithmic}
\State $r_0 = b - A x_0, \quad \beta = \|r_0\|_2, \quad v_1 = r_0 / \beta$
\For{$j = 1 \text{ to } m$}
\State $w_j = A v_j \quad \text{(apply linear operator)}$
\For{$i = 1 \text{ to } j$}
\State $h_{i,j} = (w_j, v_i), \quad w_j \leftarrow w_j - h_{i,j} v_i \quad \text{(orthogonalization sweep)}$
\EndFor
\State $h_{j+1,j} = \|w_j\|_2, \quad v_{j+1} = w_j / h_{j+1,j}$
\EndFor
\State $\text{Solve least-squares problem } y_m = \arg\min_y \|\beta e_1 - \bar{H}_m y\|_2 \text{ via Givens plane rotations}$
\State $x_m = x_0 + V_m y_m$
\Return $x_m$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: IterMethBook_2ndEd.pdf.pdf, Section 6.5.1, p. 172, Algorithm 6.9_


## 4. Known Pitfalls

- **cg-indefinite-breakdown-in-saddle-point-systems**: Attempting to solve symmetric indefinite saddle-point linear systems \begin{bmatrix} A & B \\ B^T & 0 \end{bmatrix} using standard Conjugate Gradient (CG) causes numerical breakdown or divergence due to non-positive curvature directions p_k^T A p_k \le 0. Using residual-minimizing Krylov solvers (such as GMRES or Minimal Residual methods) guarantees stable, monotonic convergence. _(Source: IterMethBook_2ndEd.pdf.pdf, Section 6.1, p. 214; Section 8.4, p. 268; Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 1, p. 3)_
- **unpreconditioned-indefinite-system-stagnation**: Solving symmetric indefinite or saddle-point linear systems without effective preconditioning leads to wide eigenvalue distributions spanning negative and positive real axes, causing slow Krylov convergence or iteration stagnation. Block-diagonal or Schur complement field-split preconditioners are required to cluster the preconditioned spectrum. _(Source: IterMethBook_2ndEd.pdf.pdf, Section 6.5.5, p. 179; Section 8.4, p. 268; Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 3.1, p. 367)_

## References

- IterMethBook_2ndEd.pdf.pdf
- Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf
- Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf
