---
id: solver-jfnk
title: Jacobian-Free Newton-Krylov (JFNK)
domain: computational-mechanics
subdomain: solvers
tags:
- solvers
- JFNK
- newton-krylov
- jacobian-free
- eisenstat-walker
- knoll-keyes
status: established
confidence: 0.9
source: hybrid
edges:
- to: solver-gmres-algorithm
  type: requires
  weight: 1.0
- to: solver-matrix-free-operator
  type: refines
  weight: 0.7
- to: optim-newton-krylov
  type: refines
  weight: 0.7
context_size: large
reading_priority: full
content_ref: null
akms_schema: v2
---

# Jacobian-Free Newton-Krylov (JFNK)

## Summary

Jacobian-Free Newton-Krylov (JFNK) methods combine outer Newton-type nonlinear iterations with inner Krylov subspace linear iterative solvers (such as GMRES) to solve non-linear systems of algebraic equations F(u) = 0. The defining characteristic of JFNK is evaluating Jacobian-vector products J v directional derivatives matrix-free via finite difference residual evaluations without forming or storing the true Jacobian matrix. Preconditioning operator P is constructed separately using physics-based, lower-order, or lagged approximations to ensure rapid Krylov convergence.

## 1. Core Concept

Jacobian-Free Newton-Krylov (JFNK) is a multi-level nested iteration framework for solving systems of non-linear partial differential equations discretized as F(u) = 0. At outer Newton step k, the linearized correction equation J(u_k) du_k = -F(u_k) is solved using an inexact Newton criterion ||J(u_k) du_k + F(u_k)||_2 <= \eta_k ||F(u_k)||_2, where forcing parameter \eta_k controls linear convergence and prevents oversolving far from the root. Instead of assembling and storing full n x n Jacobian matrices J = \partial F / \partial u, Krylov solvers (e.g. GMRES) probe the Jacobian action exclusively through directional Fréchet finite-difference derivatives J v \approx (F(u + \epsilon v) - F(u)) / \epsilon. To achieve grid-independent Krylov convergence, right preconditioning J P^-1 (P v) is applied, where preconditioner P is formed from lagged Jacobians, lower-order discretizations, or physics-based operator splittings.

## 2. Mathematical Formulation

**inexact-newton-linear-system**
$$
\|J(u_k) du_k + F(u_k)\|_2 \le \eta_k \|F(u_k)\|_2
$$
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.1, p. 360; Section 2.3.2, p. 363_

**matrix-free-jacobian-vector-product**
$$
J v \approx \frac{F(u + \epsilon v) - F(u)}{\epsilon}
$$
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.2, p. 362_

**perturbation-parameter-epsilon-selection**
$$
\epsilon = \frac{\sqrt{\epsilon_{\text{mach}}}}{\|v\|_2} (1 + \|u\|_2) \quad \text{or} \quad \epsilon = \frac{1}{n \|v\|_2} \sum_{i=1}^n \sqrt{\epsilon_{\text{mach}}} (1 + |u_i|)
$$
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.2, p. 362_

**right-preconditioned-jacobian-action**
$$
J P^{-1} v \approx \frac{F(u + \epsilon y) - F(u)}{\epsilon} \quad \text{where } P y = v
$$
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 3.1, p. 367_

**Notation:**
F(u) represents non-linear residual vector; u represents solution state vector; J represents Jacobian matrix operator; du represents Newton correction vector; v represents Krylov vector; \eta_k represents inexact Newton forcing parameter; \epsilon represents finite difference step size; P represents preconditioning operator matrix; \epsilon_{\text{mach}} represents floating point machine epsilon.


## 3. Algorithmic Implementation

**jfnk-inexact-newton-outer-loop**
$$
\begin{algorithmic}
\State $\text{Initialize solution guess } u_0, \text{ non-linear tolerance } \text{tol}_{\text{res}}, \text{ and maximum Newton steps } K_{\max}$
\For{$k = 0, 1, 2, \dots, K_{\max}$}
\State $\text{Evaluate non-linear residual } F(u_k)$
\If{$\|F(u_k)\|_2 / \|F(u_0)\|_2 < \text{tol}_{\text{res}}$}
\Return $u_k \quad \text{(converged solution)}$
\EndIf
\State $\text{Select inexact Newton forcing term } \eta_k \in (0, 1)$
\State $\text{Solve linear system } J(u_k) du_k = -F(u_k) \text{ using preconditioned GMRES to tolerance } \|J du_k + F\|_2 \le \eta_k \|F\|_2$
\State $\text{Compute step size } \alpha_k \in (0, 1] \text{ via line search or trust region globalization}$
\State $u_{k+1} = u_k + \alpha_k du_k$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.1, p. 360; Section 2.3.2, p. 363_

**right-preconditioned-jvp-evaluation**
$$
\begin{algorithmic}
\State $\text{Given current solution } u, \text{ unpreconditioned residual } F(u), \text{ and Krylov vector } v$
\State $\text{Solve preconditioner subproblem } P y = v \text{ for vector } y \text{ (e.g. via incomplete LU, AMG V-cycle, or physics split)}$
\State $\text{Compute perturbation parameter } \epsilon = \frac{\sqrt{\epsilon_{\text{mach}}}}{\|y\|_2} (1 + \|u\|_2)$
\State $\text{Evaluate perturbed residual } F(u + \epsilon y)$
\State $\text{Compute matrix-vector product } w = \frac{F(u + \epsilon y) - F(u)}{\epsilon}$
\Return $w \quad \text{(action of preconditioned Jacobian } J P^{-1} v\text{)}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.2, p. 362; Section 3.1, p. 367_


## 4. Known Pitfalls

- **finite-difference-perturbation-epsilon-imbalance**: In finite difference Jacobian-vector product evaluations J v \approx (F(u + \epsilon v) - F(u)) / \epsilon, choosing \epsilon too small causes subtractive cancellation and floating-point roundoff error domination, whereas choosing \epsilon too large introduces severe truncation error from higher-order non-linear terms. Balancing \epsilon using scaling formula \epsilon = \frac{\sqrt{\epsilon_{\text{mach}}}}{\|v\|_2} (1 + \|u\|_2) is required. _(Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.2, p. 362)_
- **oversolving-inexact-newton-linear-iterations**: Solving linear Newton correction equations J(u_k) du_k = -F(u_k) to an unnecessarily tight relative tolerance (\eta_k \ll 1) when the outer iterate u_k is far from the true solution root wastes Krylov iterations and residual evaluations on an inaccurate local Taylor linearization. Utilizing adaptive forcing terms \eta_k balances inner Krylov and outer Newton convergence. _(Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.3.2, p. 364)_

## References

- Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf
- IterMethBook_2ndEd.pdf.pdf
- Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p\$-Multigrid.pdf
- Xue et al_2023_JAX-FEM.pdf
