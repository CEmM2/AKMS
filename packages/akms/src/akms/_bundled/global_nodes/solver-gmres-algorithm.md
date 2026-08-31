---
id: solver-gmres-algorithm
title: GMRES & Restarted GMRES
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- GMRES
- krylov
- arnoldi
- non-symmetric
- restart
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-cg-algorithm
  type: refines
  weight: 0.7
- to: solver-bicgstab-algorithm
  type: contradicts
  weight: 0.0
- to: precond-jacobi-block-jacobi
  type: requires
  weight: 1.0
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# GMRES & Restarted GMRES

## Summary

The Generalized Minimal Residual (GMRES) method is a Krylov subspace iterative algorithm developed by Saad and Schultz for solving general non-symmetric and indefinite linear systems Ax = b. By constructing an orthonormal Arnoldi basis V_m via Modified Gram-Schmidt or Householder transformations, GMRES computes solution updates x_m = x_0 + V_m y_m that explicitly minimize the Euclidean norm of the residual vector ||b - A x_m||_2 over the Krylov subspace. To manage memory and computational growth as iteration counts increase, restarted GMRES(m) periodically restarts Arnoldi basis generation.

## 1. Core Concept

GMRES minimizes the residual norm over the m-th Krylov subspace K_m(A, r_0) = \text{span}\{r_0, A r_0, \dots, A^{m-1} r_0\} for general non-symmetric linear systems arising in computational mechanics and Jacobian-Free Newton-Krylov (JFNK) formulations. Using the Arnoldi process, GMRES factorizes A V_m = V_{m+1} \bar{H}_m, where V_{m+1} contains orthonormal basis vectors and \bar{H}_m \in \mathbb{R}^{(m+1) \times m} is an upper Hessenberg matrix. The residual minimization problem ||b - A (x_0 + V_m y)||_2 transforms into a small (m+1) \times m least-squares problem ||\beta e_1 - \bar{H}_m y||_2, solved efficiently using Givens plane rotations without constructing intermediate solution vectors. In restarted GMRES(m), the iteration restarts every m steps using the current iterate as the new initial guess x_0, bounding memory storage at m vectors at the expense of potential convergence stagnation.

## 2. Mathematical Formulation

**gmres-least-squares-minimization**
$$
y_m = \arg\min_{y \in \mathbb{R}^m} \|\beta e_1 - \bar{H}_m y\|_2
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 6.5.1, p. 172_

**arnoldi-operator-relation**
$$
A V_m = V_{m+1} \bar{H}_m
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 6.5.1, p. 172; Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.2, p. 360_

**givens-rotation-residual-norm**
$$
\|b - A x_m\|_2 = |\gamma_{m+1}|
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 6.5.3, pp. 176-177_

**Notation:**
A represents global non-symmetric coefficient matrix; x_m represents solution vector at step m; r_0 represents initial residual vector b - A x_0; V_m represents matrix of orthonormal Arnoldi vectors; \bar{H}_m represents upper Hessenberg matrix; Q_m represents sequence of Givens rotation matrices; \beta represents initial residual Euclidean norm.


## 3. Algorithmic Implementation

**basic-gmres-algorithm**
$$
\begin{algorithmic}
\State $r_0 = b - A x_0, \quad \beta = \|r_0\|_2, \quad v_1 = r_0 / \beta$
\For{$j = 1 \text{ to } m$}
\State $w_j = A v_j \quad \text{(or matrix-free directional derivative } [F(u + \epsilon v_j) - F(u)] / \epsilon\text{)}$
\For{$i = 1 \text{ to } j$}
\State $h_{i,j} = (w_j, v_i), \quad w_j \leftarrow w_j - h_{i,j} v_i \quad \text{(Modified Gram-Schmidt)}$
\EndFor
\State $h_{j+1,j} = \|w_j\|_2$
\If{$h_{j+1,j} == 0$}
\State $m \leftarrow j \quad \text{and break}$
\EndIf
\State $v_{j+1} = w_j / h_{j+1,j}$
\EndFor
\State $\text{Form Hessenberg matrix } \bar{H}_m = \{h_{i,j}\}_{1 \le i \le m+1, 1 \le j \le m}$
\State $\text{Compute } y_m = \arg\min_y \|\beta e_1 - \bar{H}_m y\|_2 \text{ using Givens rotations}$
\State $x_m = x_0 + V_m y_m$
\Return $x_m$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: IterMethBook_2ndEd.pdf.pdf, Section 6.5.1, p. 172, Algorithm 6.9; Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.2, p. 361_

**restarted-gmres-algorithm**
$$
\begin{algorithmic}
\State $\text{Initialize solution } x_0, \text{ restart parameter } m, \text{ and tolerance } \text{tol}$
\While{$\|b - A x_0\|_2 \ge \text{tol}$}
\State $r_0 = b - A x_0, \quad \beta = \|r_0\|_2, \quad v_1 = r_0 / \beta$
\State $\text{Generate Arnoldi basis } V_{m+1} \text{ and Hessenberg matrix } \bar{H}_m \text{ for } m \text{ steps}$
\State $\text{Compute } y_m = \arg\min_y \|\beta e_1 - \bar{H}_m y\|_2 \text{ via Givens plane rotations}$
\State $x_m = x_0 + V_m y_m$
\State $x_0 \leftarrow x_m \quad \text{(restart with updated iterate)}$
\EndWhile
\Return $x_0$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: IterMethBook_2ndEd.pdf.pdf, Section 6.5.5, p. 179, Algorithm 6.11; Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.2, p. 361_


## 4. Known Pitfalls

- **gmres-restart-stagnation**: Restarted GMRES(m) can stagnate when the coefficient matrix A is indefinite or non-positive definite and restart parameter m is chosen too small to capture key eigenspectrum modes. Increasing restart size m or applying effective preconditioning eliminates stagnation. _(Source: IterMethBook_2ndEd.pdf.pdf, Section 6.5.5, p. 179; Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.2, p. 361)_
- **modified-gram-schmidt-orthogonality-loss**: Generating Arnoldi basis vectors V_m using Modified Gram-Schmidt (MGS) in finite-precision arithmetic can suffer from loss of orthogonality when solving ill-conditioned systems. Utilizing Householder transformations or reorthogonalization maintains basis orthogonality. _(Source: IterMethBook_2ndEd.pdf.pdf, Section 6.5.2, p. 173; Section 6.3.2, p. 162)_

## References

- IterMethBook_2ndEd.pdf.pdf
- Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf
- Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf
