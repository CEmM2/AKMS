---
id: solver-bicgstab-algorithm
title: BiCGSTAB for Non-Symmetric Systems
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- BiCGSTAB
- krylov
- non-symmetric
- IDR
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-cg-algorithm
  type: refines
  weight: 0.7
- to: solver-gmres-algorithm
  type: contradicts
  weight: 0.0
- to: solver-pcg-algorithm
  type: refines
  weight: 0.7
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# BiCGSTAB for Non-Symmetric Systems

## Summary

The Biconjugate Gradient Stabilized (BiCGSTAB) method is a transpose-free Krylov subspace iterative algorithm for solving large, sparse, non-symmetric linear systems Ax = b. Developed by van der Vorst to overcome the irregular convergence and transpose matrix-vector multiplication overhead of standard Biconjugate Gradient (BiCG) and Conjugate Gradient Squared (CGS), BiCGSTAB combines BiCG polynomial updates with local steepest-descent residual minimization steps, requiring two matrix-vector products per iteration.

## 1. Core Concept

BiCGSTAB solves non-symmetric linear systems arising in fluid-structure interaction, advection-diffusion PDEs, and linearized PDE-constrained optimization without evaluating transpose matrix-vector operations A^T v. At each iteration, BiCGSTAB updates solution vector x_{j+1} in two distinct phases: first, a standard BiCG step using step length \alpha_j along direction p_j yields an intermediate residual s_j = r_j - \alpha_j A p_j; second, a GMRES-like local residual minimization step scales s_j by parameter \omega_j = (A s_j, s_j) / (A s_j, A s_j), producing a smooth, stabilized residual trajectory r_{j+1} = s_j - \omega_j A s_j. By avoiding explicit transpose operations, BiCGSTAB reduces computational cost per step compared to BiCG while providing smoother convergence profiles than CGS.

## 2. Mathematical Formulation

**bicgstab-step-length-alpha**
$$
\alpha_j = \frac{(r_j, r_0^*)}{(A p_j, r_0^*)}
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 7.4.2, p. 247_

**bicgstab-residual-vector-update**
$$
s_j = r_j - \alpha_j A p_j, \quad r_{j+1} = s_j - \omega_j A s_j
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 7.4.2, p. 247_

**bicgstab-omega-parameter**
$$
\omega_j = \frac{(A s_j, s_j)}{(A s_j, A s_j)}
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 7.4.2, p. 246_

**bicgstab-solution-update**
$$
x_{j+1} = x_j + \alpha_j p_j + \omega_j s_j
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 7.4.2, p. 247_

**Notation:**
A represents global non-symmetric coefficient matrix; x represents solution vector; b represents right-hand side vector; r_j represents residual vector at step j; r_0^* represents shadow test vector; p_j represents search direction vector; s_j represents intermediate residual vector; \alpha_j represents BiCG step parameter; \omega_j represents residual minimization parameter; \beta_j represents momentum weighting parameter.


## 3. Algorithmic Implementation

**bicgstab-algorithm**
$$
\begin{algorithmic}
\State $x_0 \leftarrow \text{Initial guess}, \quad r_0 = b - A x_0, \quad r_0^* \leftarrow \text{Arbitrary shadow vector (e.g., } r_0\text{)}, \quad p_0 = r_0$
\For{$j = 0, 1, 2, \dots \text{ until } \|r_j\|_2 < \text{tol}$}
\State $\alpha_j \leftarrow \frac{(r_j, r_0^*)}{(A p_j, r_0^*)}$
\State $s_j \leftarrow r_j - \alpha_j A p_j$
\State $\omega_j \leftarrow \frac{(A s_j, s_j)}{(A s_j, A s_j)}$
\State $x_{j+1} \leftarrow x_j + \alpha_j p_j + \omega_j s_j$
\State $r_{j+1} \leftarrow s_j - \omega_j A s_j$
\State $\beta_j \leftarrow \frac{(r_{j+1}, r_0^*)}{(r_j, r_0^*)} \frac{\alpha_j}{\omega_j}$
\State $p_{j+1} \leftarrow r_{j+1} + \beta_j (p_j - \omega_j A p_j)$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: IterMethBook_2ndEd.pdf.pdf, Section 7.4.2, p. 247, Algorithm 7.7; Xue et al_2023_JAX-FEM.pdf, Section 5, p. 11_


## 4. Known Pitfalls

- **bicgstab-breakdown-zero-scalar-products**: BiCGSTAB experiences breakdown or severe numerical instability when inner product (r_j, r_0*) = 0 or denominator (A p_j, r_0*) = 0 occurs before convergence. This breakdown stems from the underlying Lanczos or BiCG biorthogonalization process failing. _(Source: IterMethBook_2ndEd.pdf.pdf, Section 7.4.2, p. 247; Section 7.5, p. 254)_
- **bicgstab-stagnation-omega-zero**: The local residual minimization parameter omega_j = (A s_j, s_j) / (A s_j, A s_j) becomes zero when intermediate vector A s_j is orthogonal to s_j. When omega_j = 0, solution iterates x_{j+1} stop making progress, causing algorithm stagnation. _(Source: IterMethBook_2ndEd.pdf.pdf, Section 7.4.2, p. 246; Section 7.5, p. 254)_

## References

- IterMethBook_2ndEd.pdf.pdf
- Xue et al_2023_JAX-FEM.pdf
- Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf
