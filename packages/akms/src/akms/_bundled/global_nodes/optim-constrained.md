---
id: optim-constrained
title: Constrained Optimization Methods
domain: computational-mechanics
subdomain: optimization
tags:
- optimization
- constrained
- KKT
- lagrange
- penalty
- augmented-lagrangian
- SQP
status: established
confidence: 0.9
source: hybrid
edges:
- to: optim-unconstrained-basics
  type: refines
  weight: 0.7
- to: composite-delamination
  type: feeds-into
  weight: 0.5
- to: pf-at1-regularization
  type: feeds-into
  weight: 0.5
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Constrained Optimization Methods

## Summary

Constrained optimization in computational mechanics addresses minimization problems subject to equality, inequality, multipoint algebraic, and partial differential equation (PDE) constraints. The mathematical structure relies on Lagrangian formulations, Karush-Kuhn-Tucker (KKT) first-order optimality conditions, and specialized solver strategies including full-space Lagrange-Newton-Krylov (LNK), reduced sequential quadratic programming (RSQP), interior-point barrier methods, linear constraint elimination, and adjoint-based PDE-constrained optimization.

## 1. Core Concept

Constrained optimization seeks to minimize an objective functional subject to physical or geometric constraints. Equality constraints (such as finite element state equations, boundary conditions, or linear hanging-node multipoint relationships) and inequality constraints (such as contact non-penetration or damage irreversibility) modify the search space and optimality conditions. Stationarity of the Lagrangian functional leads to saddle-point linear systems (KKT systems) characterized by indefinite block coefficient matrices. In PDE-constrained optimization (PDE-CO), state constraints are coupled with design parameters, where adjoint methods enable efficient gradient evaluation for large parameter dimensions. In non-convex physical simulations, such as interior-point elastodynamics or phase-field fracture, specialized line-search procedures, barrier penalty transformations, and idempotent linear constraint projection matrices ensure robust convergence and kinematic admissibility.

## 2. Mathematical Formulation

**kkt-system**
$$
\begin{bmatrix} W_{xx} & W_{xu} & J_x^T \\ W_{ux} & W_{uu} & J_u^T \\ J_x & J_u & 0 \end{bmatrix} \begin{bmatrix} dx \\ du \\ d\lambda \end{bmatrix} = -\begin{bmatrix} g_x \\ g_u \\ h \end{bmatrix}
$$
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 6.1, p. 388_

**saddle-point-equality-constrained**
$$
\begin{bmatrix} A & B \\ B^T & 0 \end{bmatrix} \begin{bmatrix} x \\ y \end{bmatrix} = \begin{bmatrix} b \\ c \end{bmatrix}
$$
_Source: IterMethBook_2ndEd.pdf.pdf, Section 8.4, p. 268_

**interior-point-barrier-functional**
$$
E(x) = \frac{1}{2}(x - \tilde{x})^T M (x - \tilde{x}) + h^2 \Psi(x) + \kappa \sum_{k \in \mathcal{C}} b(d_k(x))
$$
_Source: Shen et al. - 2024 - Preconditioned Nonlinear Conjugate Gradient Method for Real-time Interior-point Hyperelasticity.pdf, Section 3, p. 3_

**linear-constraint-elimination-system**
$$
(C^T A C + \text{Id}_c) \hat{x} = C^T (b - A k)
$$
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.2, p. 5_

**pde-constrained-adjoint-gradient**
$$
\frac{d\hat{J}}{d\theta} = -\frac{\partial J}{\partial U} \left(\frac{\partial C}{\partial U}\right)^{-1} \frac{\partial C}{\partial \theta} + \frac{\partial J}{\partial \theta}
$$
_Source: Xue et al_2023_JAX-FEM.pdf, Section 3, p. 7_

**Notation:**
x, u, U represent state or design variables; \lambda, y represent Lagrange multipliers; W, A, H represent Hessian or stiffness matrices; J_a, B, C represent constraint Jacobians or transformation matrices; \phi, J, E represent objective functionals; d_k, \hat{d} represent contact distance and threshold; \kappa represents barrier stiffness.


## 3. Algorithmic Implementation

**lnk-full-space-kkt-solver**
$$
\begin{algorithmic}
\State $\text{Initialize state } x_0, \text{ design } u_0, \text{ and multiplier } \lambda_0$
\While{$\|[g_x^T, g_u^T, h^T]^T\| > \text{tol}$}
\State $\text{Evaluate KKT residual } r_k = \begin{bmatrix} g_x + J_x^T \lambda_k \\ g_u + J_u^T \lambda_k \\ h(x_k, u_k) \end{bmatrix}$
\State $\text{Solve KKT Newton system } \begin{bmatrix} W_{xx} & W_{xu} & J_x^T \\ W_{ux} & W_{uu} & J_u^T \\ J_x & J_u & 0 \end{bmatrix} \begin{bmatrix} dx \\ du \\ d\lambda \end{bmatrix} = -r_k \text{ via preconditioned Krylov-Schwarz}$
\State $\text{Update iterates } x_{k+1} = x_k + dx, \quad u_{k+1} = u_k + du, \quad \lambda_{k+1} = \lambda_k + d\lambda$
\EndWhile
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 6.2, p. 388_

**interior-point-pncg-solver**
$$
\begin{algorithmic}
\State $x_0 \leftarrow x_t, \quad \tilde{x} = x_t + h v_t + h^2 M^{-1} f_{\text{ext}}$
\For{$k = 0 \text{ to } \text{IterMax}$}
\State $\mathcal{C} \leftarrow \text{ComputeConstraintSet}(x_k, \hat{d})$
\State $g_{k+1}, P_{k+1} \leftarrow \text{ComputeGradientAndPreconditioning}(x_k, \tilde{x}, \mathcal{C})$
\If{$k == 0$}
\State $\beta_k \leftarrow 0$
\Else
\EndIf
\State $p_{k+1} \leftarrow -P_{k+1} g_{k+1} + \beta_k p_k$
\State $\alpha \leftarrow \min\left( \frac{\hat{d}}{2 \|p_{k+1}\|_\infty}, -\frac{g_{k+1}^T p_{k+1}}{p_{k+1}^T H_{k+1} p_{k+1}} \right)$
\State $x_{k+1} \leftarrow x_k + \alpha p_{k+1}$
\State $\Delta E \leftarrow -\alpha g_{k+1}^T p_{k+1} - \frac{\alpha^2}{2} p_{k+1}^T H_{k+1} p_{k+1}$
\If{$\Delta E < \epsilon \Delta E_0$}
\State $\text{Break}$
\EndIf
\EndFor
\end{algorithmic}
$$
Taichi Mapping: Implemented natively in Taichi using MeshTaichi for GPU parallel element assembly, diagonal preconditioning P_{k+1}, directional Hessian-vector products p_{k+1}^T H_{k+1} p_{k+1}, and spatial hashing for broad-phase culling.
_Source: Shen et al. - 2024 - Preconditioned Nonlinear Conjugate Gradient Method for Real-time Interior-point Hyperelasticity.pdf, Section 4, p. 5_

**linear-constraint-lbfgs-step**
$$
\begin{algorithmic}
\State $\text{Assemble unconstrained residual } \hat{r}_k = [r_u(x_k); r_d(x_k)]$
\State $\text{Incorporate nodal constraints into residual } r_k = C^T \hat{r}_k$
\State $\text{Compute unconstrained search direction } \hat{p}_k = -H_k^0 r_k \text{ via L-BFGS two-loop recursion}$
\State $\text{Enforce constraint kinematics on search direction } p_k = C \hat{p}_k$
\State $\text{Find step length } \alpha_k > 0 \text{ satisfying strong Wolfe conditions}$
\State $\text{Update solution } x_{k+1} = x_k + \alpha_k p_k$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf, Section 3.2, p. 6_


## 4. Known Pitfalls

- **rsqp-reduced-hessian-scaling-bottleneck**: Reduced Sequential Quadratic Programming (RSQP) requires solving m linear systems with the state Jacobian J_x to form the reduced Hessian H at each design iteration. For large-scale problems where design dimension m scales with state dimension n, exact RSQP becomes computationally prohibitive, while quasi-Newton RSQP suffers from slow convergence O(m^p) and loss of scalability. _(Source: Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 6.2, pp. 388-389)_
- **barrier-step-overshoot-intersection**: In interior-point collision and contact simulations, unconstrained Newton or conjugate gradient step lengths can cause vertex displacements exceeding the barrier threshold d_hat, leading to undetected primitive interpenetration before contact repulsion is activated. Capping step size by alpha_upper = d_hat / (2 ||p||_inf) prevents mesh interpenetration. _(Source: Shen et al. - 2024 - Preconditioned Nonlinear Conjugate Gradient Method for Real-time Interior-point Hyperelasticity.pdf, Section 4.2, p. 6)_
- **non-convex-lagrangian-indefiniteness**: The KKT matrix arising from constrained optimization is inherently indefinite due to zero diagonal blocks for Lagrange multipliers, preventing direct application of standard positive-definite linear CG solvers without preconditioning or Schur complement transformations. _(Source: IterMethBook_2ndEd.pdf.pdf, Section 8.4, p. 268; Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf, Section 6.1, p. 388)_

## References

- Knoll_Keyes_2004_Jacobian-free Newton–Krylov methods.pdf
- Shen et al. - 2024 - Preconditioned Nonlinear Conjugate Gradient Method for Real-time Interior-point Hyperelasticity.pdf
- Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS.pdf
- IterMethBook_2ndEd.pdf.pdf
- Xue et al_2023_JAX-FEM.pdf
