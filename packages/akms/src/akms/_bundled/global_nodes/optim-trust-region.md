---
id: optim-trust-region
title: Trust Region Methods
domain: computational-mechanics
subdomain: optimization
tags:
- optimization
- trust-region
- dogleg
- steihaug
- cauchy-point
status: established
confidence: 0.9
source: hybrid
edges:
- to: optim-unconstrained-basics
  type: refines
  weight: 0.7
- to: optim-line-search
  type: contradicts
  weight: 0.0
- to: optim-newton-krylov
  type: feeds-into
  weight: 0.5
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Trust Region Methods

## Summary

Trust region methods provide a robust globalization framework for Newton and Newton-Krylov solvers in computational mechanics by defining a neighborhood around the current iterate where a local Taylor linearization or model approximation is trusted to accurately represent the nonlinear residual. Rather than restricting search steps to a single search direction as in line search methods, trust region approaches search for candidate steps—often formed as linear combinations of candidate directions, including approximate Newton corrections—within a bounded trust radius. In non-convex physical problems, such as fully monolithic phase-field models of fracture, trust region methods prevent divergence during post-peak softening and brutal crack propagation regimes.

## 1. Core Concept

Globalization of Newton-Raphson and Jacobian-Free Newton-Krylov (JFNK) methods is essential when initial solution iterates lie far from the root, where full Newton steps cause divergence or stagnation. Trust region globalization replaces line search step-length scaling along a single search direction by searching within a ball or region in which the linear residual model approximation F(u_k) + J(u_k) du \approx F(u_k + du) remains valid. Candidate steps are chosen to ensure residual reduction and robust convergence. In non-convex solid mechanics and phase-field fracture, where energy functionals lack convexity and tangent stiffness matrices become indefinite or ill-conditioned, trust region strategies maintain numerical stability through brutal crack propagation and post-peak softening regimes where standard line search methods frequently fail.

## 2. Mathematical Formulation

**trust-region-linear-model-approximation**
$$
F(u_k) + J(u_k) du \approx F(u_k + du) \quad \text{for } \|du\| \le \Delta_k
$$
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.4.1, p. 364_

**trust-region-candidate-step-combination**
$$
du_k = \sum_{j=1}^p \alpha_j s_j \quad \text{such that } \|du_k\| \le \Delta_k
$$
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.4.1, p. 364_

**inexact-newton-trust-region-subproblem**
$$
\|J(u_k) du_k + F(u_k)\|_2 \le \eta_k \|F(u_k)\|_2 \quad \text{subject to } \|du_k\| \le \Delta_k
$$
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.3.2, p. 363; Section 2.4.1, p. 364_

**Notation:**
u represents the solution state vector; F(u) represents the nonlinear residual vector; J(u) represents the Jacobian matrix or matrix-free operator; du represents the solution update step; \Delta_k represents the trust region radius; \eta_k represents the inexact Newton forcing parameter.


## 3. Algorithmic Implementation

**newton-krylov-trust-region-globalization**
$$
\begin{algorithmic}
\State $\text{Initialize solution } u_0, \text{ initial trust radius } \Delta_0, \text{ and tolerance } \text{tol}$
\For{$k = 0, 1, 2, \dots \text{ until } \|F(u_k)\|_2 < \text{tol}$}
\State $\text{Evaluate nonlinear residual } F(u_k)$
\State $\text{Form local linear model } M_k(du) = F(u_k) + J(u_k) du$
\State $\text{Compute candidate step } du_k \text{ satisfying } \|J(u_k) du_k + F(u_k)\|_2 \le \eta_k \|F(u_k)\|_2 \text{ within trust bound } \|du_k\| \le \Delta_k$
\If{$\|F(u_k + du_k)\|_2 < \|F(u_k)\|_2$}
\State $u_{k+1} = u_k + du_k \quad \text{(accept step and expand/maintain } \Delta_{k+1} \ge \Delta_k\text{)}$
\Else
\EndIf
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.4.1, p. 364_


## 4. Known Pitfalls

- **line-search-stagnation-near-post-peak-softening**: Standard line search Newton-Raphson solvers often stagnate or diverge during post-peak softening or brutal crack propagation in phase-field fracture mechanics due to non-convex energy landscapes and negative directional derivatives. Trust region globalization and recursive multilevel trust region methods preserve convergence where line search fails. _(Source: Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf, Section 2, p. 4; Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.4.1, p. 364)_
- **trust-region-model-mismatch-stagnation**: If the trust region radius Delta_k is shrunk too aggressively due to local non-convexity or function evaluation noise, Newton-Krylov solvers take infinitesimally small steps, leading to iteration stagnation without making progress toward the root. _(Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.4.1, p. 364)_

## References

- Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf
- Badri et al_2021_Preconditioning strategies for vectorial finite element linear systems arising.pdf
- Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf
- Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf
