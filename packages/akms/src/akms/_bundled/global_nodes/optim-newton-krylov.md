---
id: optim-newton-krylov
title: Newton-Krylov Methods (Inexact Newton)
domain: computational-mechanics
subdomain: optimization
tags:
- optimization
- newton-krylov
- JFNK
- inexact-newton
- eisenstat-walker
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-jfnk
  type: refines
  weight: 0.7
- to: solver-gmres-algorithm
  type: requires
  weight: 1.0
- to: optim-line-search
  type: requires
  weight: 1.0
- to: optim-lbfgs
  type: contradicts
  weight: 0.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Newton-Krylov Methods (Inexact Newton)

## Summary

Newton-Krylov methods (inexact Newton) solve large-scale non-convex systems of nonlinear algebraic equations arising in computational mechanics by coupling outer Newton updates with inner Krylov subspace iterative solvers. By exploiting matrix-free directional derivatives (or automatic differentiation) to compute Jacobian-vector products J v without forming or factorizing dense global Jacobians, Jacobian-Free Newton-Krylov (JFNK) methods achieve superlinear convergence while reducing memory overhead.

## 1. Core Concept

Newton-Krylov methods address non-autonomous, non-convex, and coupled physical problems where assembling and factorizing full tangent stiffness matrices (Jacobians) is computationally prohibitive or analytically intractable. In an inexact Newton framework, the linearized Newton system J(u_k) du_k = -F(u_k) is solved approximately by a Krylov subspace method (such as GMRES or CG) until the linear residual satisfies an inexact termination condition ||J(u_k) du_k + F(u_k)||_2 <= \eta_k ||F(u_k)||_2, governed by a forcing term \eta_k. JFNK evaluates matrix-vector products J v via finite difference directional derivatives of the nonlinear residual functional F(u + \epsilon v) or via reverse-mode automatic differentiation. Robustness is maintained by combining inexact Newton updates with preconditioning operators (such as physics-based splitting, domain decomposition additive Schwarz, or multigrid V-cycles) and globalization strategies (such as pseudo-transient continuation or line search).

## 2. Mathematical Formulation

**inexact-newton-condition**
$$
\|J(u_k) du_k + F(u_k)\|_2 \le \eta_k \|F(u_k)\|_2
$$
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.3.2, p. 363_

**jfnk-jacobian-vector-directional-derivative**
$$
J(u) v \approx \frac{F(u + \epsilon v) - F(u)}{\epsilon}
$$
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.3, p. 362_

**jfnk-perturbation-parameter-scaling**
$$
\epsilon = \frac{\sqrt{(1 + \|u\|_2) \epsilon_{\text{mach}}}}{\|v\|_2}
$$
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.3.1, p. 363_

**preconditioned-jfnk-right-system**
$$
(J P^{-1}) (P du) = -F(u)
$$
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 3, p. 367_

**Notation:**
u represents the solution state vector; F(u) represents the nonlinear residual function; J represents the exact Jacobian operator; du represents the Newton update step; v represents a Krylov vector; \eta_k represents the forcing term parameter; \epsilon represents the finite difference perturbation parameter; P^{-1} represents the preconditioning operator.


## 3. Algorithmic Implementation

**inexact-newton-krylov-outer-inner-solver**
$$
\begin{algorithmic}
\State $\text{Initialize solution } u_0, \text{ nonlinear tolerance } \text{tol}_{\text{res}}, \text{ and forcing sequence } \{\eta_k\}$
\For{$k = 0, 1, 2, \dots \text{ until } \|F(u_k)\|_2 < \text{tol}_{\text{res}} \|F(u_0)\|_2$}
\State $\text{Evaluate residual vector } F(u_k)$
\State $\text{Solve linear system } J(u_k) du_k = -F(u_k) \text{ inexactly via GMRES to satisfy } \|J(u_k) du_k + F(u_k)\|_2 \le \eta_k \|F(u_k)\|_2$
\State $\text{Evaluate matrix-vector products } J(u_k) v \text{ matrix-free via } \frac{F(u_k + \epsilon v) - F(u_k)}{\epsilon}$
\State $\text{Determine step size } s_k \in (0, 1] \text{ via line search or pseudo-transient continuation}$
\State $u_{k+1} = u_k + s_k du_k$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.1-2.3, pp. 359-364_


## 4. Known Pitfalls

- **jfnk-oversolving-inexact-newton-step**: Solving the linear Newton correction system J(u_k) du_k = -F(u_k) to an overly tight relative linear tolerance (\eta_k \ll 1) during early outer iterations wastes Krylov iterations calculating an exact solution for an inaccurate far-from-root linearization. Setting adaptive forcing terms \eta_k avoids oversolving. _(Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.3.2, p. 364)_
- **finite-difference-perturbation-cancellation-noise**: Evaluating matrix-free directional derivatives via J v \approx (F(u + \epsilon v) - F(u)) / \epsilon requires careful scaling of \epsilon. Choosing \epsilon too large introduces severe truncation error, while choosing \epsilon too small causes floating-point roundoff cancellation, destroying Krylov subspace orthogonality. _(Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.3.1, pp. 362-363)_
- **non-monotone-discontinuity-stagnation**: In non-linear systems with sharp spatial features, shocks, or non-smooth material constitutive laws, finite difference Frechet derivative estimates J v become noisy or non-monotone, causing Newton-Krylov line searches to stagnate or fail to converge. _(Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.3, p. 362)_

## References

- Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf
- Xue et al_2023_JAX-FEM.pdf
- Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf
- IterMethBook_2ndEd.pdf.pdf
