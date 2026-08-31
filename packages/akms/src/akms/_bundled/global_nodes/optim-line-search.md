---
id: optim-line-search
title: Line Search Strategies
domain: computational-mechanics
subdomain: optimization
tags:
- optimization
- line-search
- armijo
- wolfe
- backtracking
- cubic-interpolation
status: established
confidence: 0.9
source: hybrid
edges:
- to: optim-unconstrained-basics
  type: refines
  weight: 0.7
- to: optim-lbfgs
  type: feeds-into
  weight: 0.5
- to: optim-newton-krylov
  type: feeds-into
  weight: 0.5
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Line Search Strategies

## Summary

Line search strategies in computational mechanics determine the step length parameter \alpha_k along a computed search direction p_k to ensure globalization, numerical stability, and satisfaction of curvature conditions. Essential strategies range from basic Armijo backtracking to strong Wolfe conditions, Moré-Thuente cubic interpolation, interior-point upper-bounded secant updates, and gradient-based quasi-Newton line searches for non-variational mechanics.

## 1. Core Concept

Line search algorithms scale descent search directions p_k produced by Newton-Raphson, quasi-Newton (BFGS/L-BFGS), or preconditioned nonlinear conjugate gradient (PNCG) solvers to update primal solution iterates x_{k+1} = x_k + \alpha_k p_k. In unconstrained optimization, line search prevents divergence, overshooting, and snap-back instability. Simple Armijo backtracking enforces sufficient decrease of objective functionals. However, in quasi-Newton methods, line search must also satisfy the curvature condition s_k^T y_k > 0 (via Wolfe or strong Wolfe conditions) to guarantee positive definiteness of inverse Hessian updates. For non-variational or history-dependent mechanical models (such as phase-field fracture with damage irreversibility history variables or non-conservative hyperelasticity), global energy functionals do not exist or mismatch residual gradients. In these contexts, gradient-based secular line searches solve g(x_k + \alpha p_k)^T p_k = 0 via one-pass secant or quasi-Newton iterations, achieving robust convergence without evaluating energy functionals.

## 2. Mathematical Formulation

**armijo-sufficient-decrease**
$$
f(x_k + \alpha_k p_k) \le f(x_k) + c_1 \alpha_k \nabla f(x_k)^T p_k
$$
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.1, p. 10; Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf, Section 2.1, p. 242_

**strong-wolfe-conditions**
$$
f(x_k + \alpha_k p_k) \le f(x_k) + c_1 \alpha_k \nabla f(x_k)^T p_k, \quad |\nabla f(x_k + \alpha_k p_k)^T p_k| \le c_2 |\nabla f(x_k)^T p_k|
$$
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.1, p. 10; Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf, Section 2.1, p. 242_

**quasi-newton-secular-line-search**
$$
\Delta \lambda_l = -\Delta \lambda_{l-1} \frac{g_l^T p_k}{y_{l-1}^T p_k}, \quad \lambda_{l+1} = \lambda_l + \Delta \lambda_l
$$
_Source: Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2.1, p. 7_

**interior-point-quadratic-line-search**
$$
\alpha_k = \min\left( \frac{\hat{d}}{2 \|p_k\|_\infty}, -\frac{g_k^T p_k}{p_k^T H_k p_k} \right)
$$
_Source: Shen et al. - 2024 - Preconditioned Nonlinear Conjugate Gradient Method for Real-time Interior-point Hyperelasticity.pdf, Section 4.3, p. 6_

**Notation:**
x represents solution vector; f represents objective energy functional; g, r represent residual gradient vectors; p, d represent search direction vectors; \alpha, s, \lambda represent step length parameters; c_1, c_2, \delta, \sigma represent line search threshold parameters; \hat{d} represents contact barrier threshold distance.


## 3. Algorithmic Implementation

**armijo-backtracking-line-search**
$$
\begin{algorithmic}
\State $\text{Initialize step size } s = 1, \text{ decay factor } \tau \in (0, 1), \text{ and parameter } c_1 \in (0, 1)$
\While{$f(x_k + s p_k) > f(x_k) + c_1 s \nabla f(x_k)^T p_k$}
\State $s \leftarrow \tau s$
\EndWhile
\Return $\alpha_k = s$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 2.4.1, p. 364_

**more-thuente-strong-wolfe-line-search**
$$
\begin{algorithmic}
\State $\text{Set initial step } \alpha_0 = 1, \text{ tolerances } c_1 = 10^{-4}, c_2 = 0.9$
\State $\text{Define scalar function } \phi(\alpha) = f(x_k + \alpha p_k) \text{ with derivative } \phi'(\alpha) = \nabla f(x_k + \alpha p_k)^T p_k$
\While{$\phi(\alpha_l) > \phi(0) + c_1 \alpha_l \phi'(0) \text{ or } |\phi'(\alpha_l)| > c_2 |\phi'(0)|$}
\State $\text{Update trial step } \alpha_{l+1} \text{ via cubic/quadratic interpolation in interval } I_l \text{ satisfying Wolfe conditions}$
\State $l \leftarrow l + 1$
\EndWhile
\Return $\alpha_k = \alpha_l$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.2, p. 11_

**quasi-newton-gradient-line-search**
$$
\begin{algorithmic}
\State $x_k, p_k, g_k \leftarrow \text{Iterate, search direction, gradient}$
\State $\lambda_0 = 1, \quad g_1 = g(x_k + \lambda_0 p_k), \quad y_0 = g_1 - g_k$
\If{$p_k^T y_0 > \text{TOL}_{\text{act}}^{\text{LS}}$}
\For{$l = 1 \text{ to } l_{\text{max}}$}
\State $\Delta \lambda_l \leftarrow -\Delta \lambda_{l-1} \frac{g_l^T p_k}{y_{l-1}^T p_k}$
\State $\lambda_{l+1} \leftarrow \lambda_l + \Delta \lambda_l$
\If{$|\Delta \lambda_l| \le \text{TOL}_{\text{LS}}$}
\State $\text{Break}$
\EndIf
\State $g_{l+1} \leftarrow g(x_k + \lambda_{l+1} p_k), \quad y_l \leftarrow g_{l+1} - g_l$
\EndFor
\Else
\State $\lambda_k \leftarrow 1$
\EndIf
\Return $\alpha_k = \lambda_k$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2.1, p. 8, Algorithm 3_


## 4. Known Pitfalls

- **non-variational-energy-line-search-failure**: In non-variational mechanical formulations (such as phase-field fracture incorporating history variables for damage irreversibility), the energy functional becomes a pseudo-energy whose value does not monotonically decrease with residual gradients. Line search methods based strictly on objective energy decrease (e.g. Armijo or energy-minimized interpolation) can select incorrect step lengths, cause line search stalling, or lead to algorithm divergence. Gradient-based secular line search solving g(x_k + \lambda p_k)^T p_k = 0 resolves this issue without evaluating energy functionals. _(Source: Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2.1, pp. 6-7)_
- **armijo-backtracking-violates-curvature-condition**: Simple Armijo backtracking line search only enforces sufficient decrease of the objective function and does not satisfy the curvature condition s_k^T y_k > 0. In quasi-Newton methods (such as BFGS or L-BFGS), updating inverse Hessian approximations under steps that violate curvature condition s_k^T y_k > 0 produces indefinite matrices and non-descent directions, causing solver breakdown. Strong Wolfe or modified curvature-skipped updates must be enforced. _(Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.1, p. 10; Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2, p. 6)_
- **line-search-computational-overhead-in-fft-mechanics**: In FFT-based computational micromechanics, line search procedures require multiple expensive material law evaluations and stress updates per iteration. Because condensed energy functionals are typically not computed explicitly in FFT solvers (only stress gradients are available), naive line search doubled the execution time compared to fixed-step fast gradient methods. _(Source: Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf, Section 2, pp. 241-242)_

## References

- Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf
- Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf
- Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf
- Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf
- Shen et al. - 2024 - Preconditioned Nonlinear Conjugate Gradient Method for Real-time Interior-point Hyperelasticity.pdf
