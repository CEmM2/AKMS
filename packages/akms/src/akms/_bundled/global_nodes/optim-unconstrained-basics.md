---
id: optim-unconstrained-basics
title: Unconstrained Optimization Fundamentals
domain: computational-mechanics
subdomain: optimization
tags:
- optimization
- gradient
- hessian
- descent
- wolfe
- kkt-free
status: established
confidence: 0.9
source: hybrid
edges:
- to: optim-line-search
  type: feeds-into
  weight: 0.5
- to: optim-lbfgs
  type: feeds-into
  weight: 0.5
- to: optim-newton-krylov
  type: feeds-into
  weight: 0.5
- to: optim-trust-region
  type: feeds-into
  weight: 0.5
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Unconstrained Optimization Fundamentals

## Summary

Unconstrained optimization in computational mechanics seeks the minimizer of a scalar energy functional or non-convex physical potential without explicit algebraic constraints. Fundamentals encompass first-order stationarity conditions, search direction generation via Newton or quasi-Newton operators, line search globalization satisfying Wolfe conditions, and curvature preservation in non-convex landscapes.

## 1. Core Concept

Unconstrained optimization minimizes a continuous scalar objective functional f(x) representing potential energy, compliance, or loss functions. A solution iterate x* satisfies first-order stationarity where the residual gradient r(x*) = \nabla f(x*) = 0. Iterative optimization procedures generate trial steps x_{k+1} = x_k + \alpha_k p_k by computing descent directions p_k = -H_k r_k using true or approximate inverse Hessian operators H_k. In non-convex mechanical formulations (such as phase-field fracture), the true tangent stiffness matrix can become indefinite or singular. Quasi-Newton methods approximate second-order curvature via secant updates B_{k+1} s_k = y_k, where s_k = x_{k+1} - x_k and y_k = r_{k+1} - r_k. Enforcing curvature condition s_k^T y_k > 0 through line search strategies guarantees that updated inverse Hessian approximations H_{k+1} remain positive-definite, ensuring p_k is a valid descent direction.

## 2. Mathematical Formulation

**first-order-optimality-condition**
$$
r(x) = \nabla f(x) = 0
$$
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.1, p. 10; Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2, p. 5_

**descent-direction-condition**
$$
\frac{d\phi(0)}{d\alpha} = r_k^T p_k < 0
$$
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.2, p. 12_

**quasi-newton-secant-equation**
$$
B_{k+1} s_k = y_k \quad \text{or} \quad H_{k+1} y_k = s_k
$$
_Source: Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2, p. 5; Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.1, p. 10_

**wolfe-sufficient-decrease-and-curvature**
$$
f(x_k + \alpha_k p_k) \le f(x_k) + c_1 \alpha_k r_k^T p_k, \quad r(x_k + \alpha_k p_k)^T p_k \ge c_2 r_k^T p_k
$$
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.1, p. 10_

**Notation:**
x represents solution state vector; f represents objective function; r, g represent residual gradient vectors; p represents search direction vector; \alpha represents line search step length; s_k represents solution increment x_{k+1} - x_k; y_k represents residual increment r_{k+1} - r_k; B_k represents Hessian approximation; H_k represents inverse Hessian approximation operator.


## 3. Algorithmic Implementation

**unconstrained-quasi-newton-driver**
$$
\begin{algorithmic}
\State $\text{Initialize solution vector } x_0, \text{ initial positive-definite matrix } H_0, \text{ and tolerance } \text{tol}$
\For{$k = 0, 1, 2, \dots \text{ until } \|r_k\|_2 < \text{tol}$}
\State $\text{Evaluate residual gradient } r_k = \nabla f(x_k)$
\State $\text{Compute descent search direction } p_k = -H_k r_k$
\State $\text{Determine step length } \alpha_k > 0 \text{ satisfying Wolfe conditions } f(x_k + \alpha_k p_k) \le f(x_k) + c_1 \alpha_k r_k^T p_k$
\State $x_{k+1} = x_k + \alpha_k p_k$
\State $s_k = x_{k+1} - x_k, \quad y_k = r_{k+1} - r_k$
\State $\text{Update inverse Hessian approximation } H_{k+1} \text{ using } s_k \text{ and } y_k$
\EndFor
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.1, p. 10, Algorithm 1; Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2, p. 6_


## 4. Known Pitfalls

- **non-convex-hessian-indefiniteness**: In non-convex physical problems (such as phase-field fracture or post-peak softening), the true tangent stiffness Hessian matrix \nabla^2 f(x) becomes indefinite or non-symmetric. Standard Newton updates without line search or positive-definite quasi-Newton scaling diverge or generate non-descent search directions. _(Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.1, p. 10; Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2, p. 5)_
- **curvature-condition-violation**: Updating quasi-Newton Hessian approximations when the curvature condition s_k^T y_k \le 0 is violated destroys the positive definiteness of H_{k+1}. Enforcing strong Wolfe line search conditions or skipping updates under negative curvature ensures s_k^T y_k > 0 and preserves descent directions. _(Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.1, p. 10; Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2, p. 6)_

## References

- Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf
- Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf
- Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf
- Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf
