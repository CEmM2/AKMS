---
id: optim-lbfgs-fem
title: L-BFGS for Nonlinear FEM
domain: computational-mechanics
subdomain: optimization
tags:
- optimization
- lbfgs
- FEM
- preconditioned-lbfgs
- hybrid-newton
status: established
confidence: 0.9
source: hybrid
edges:
- to: optim-lbfgs
  type: refines
  weight: 0.7
- to: optim-as-solver
  type: refines
  weight: 0.7
- to: pf-monolithic-bfgs
  type: feeds-into
  weight: 0.5
- to: optim-newton-krylov
  type: contradicts
  weight: 0.0
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# L-BFGS for Nonlinear FEM

## Summary

Limited-memory Broyden-Fletcher-Goldfarb-Shanno (L-BFGS) for nonlinear finite element analysis replaces full Newton-Raphson iterations to solve coupled, non-convex boundary value problems without forming or factorizing dense Hessian matrices. By maintaining a memory horizon of m vector pairs (solution step s_k and residual increment y_k), L-BFGS calculates search directions via two-loop recursion. Combined with initial inverse Hessian scaling (such as block-diagonal stiffness matrices or matrix-free multigrid V-cycles), idempotent linear constraint projection matrices for hanging nodes and boundary conditions, and strong Wolfe or gradient-based line searches, L-BFGS achieves robust superlinear convergence in non-convex mechanics.

## 1. Core Concept

In finite element discretizations of non-convex mechanical problems—such as phase-field brittle fracture or large-deformation hyperelasticity—the true tangent stiffness matrix (Hessian) can become indefinite or non-symmetric, causing standard Newton-Raphson solvers to diverge during snap-back or rapid crack propagation. Classical BFGS quasi-Newton updates preserve symmetry and positive definiteness via rank-two updates, but introduce fully dense matrices that destroy finite element sparsity. L-BFGS circumvents dense matrix storage by representing the inverse Hessian implicitly using m recent vector pairs s_k = x_{k+1} - x_k and y_k = r_{k+1} - r_k. An initial scaling operator H_0^k—typically chosen as a matrix-free multigrid preconditioner or the inverse of the uncoupled block-diagonal stiffness matrix \hat{K} = \text{diag}(K_{uu}, K_{dd})—is updated using two-loop recursion. To enforce algebraic nodal constraints (such as hanging nodes from adaptive mesh refinement and Dirichlet boundary conditions x = C x + k with C^2 = C), residual vectors are pre-multiplied by C^T and search directions are post-multiplied by C, guaranteeing descent and kinematic admissibility.

## 2. Mathematical Formulation

**lbfgs-two-loop-search-direction**
$$
p_k = -H_k r_k
$$
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS method with adaptive mesh refinement.pdf, Section 3.2, p. 11_

**lbfgs-secant-and-curvature-condition**
$$
H_{k+1} = (I - \rho_k s_k y_k^T) H_k (I - \rho_k y_k s_k^T) + \rho_k s_k s_k^T, \quad \rho_k = \frac{1}{y_k^T s_k}
$$
_Source: Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2, p. 5_

**matrix-free-multigrid-initial-hessian**
$$
H_0^k = M_{\text{MG}}^{-1}
$$
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf, Section III.A, p. 3_

**constrained-lbfgs-projection**
$$
r_k = C^T \hat{r}_k, \quad p_k = C \hat{p}_k
$$
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS method with adaptive mesh refinement.pdf, Section 3.2, p. 11_

**Notation:**
x represents the global primal DOF solution vector (displacements and internal state variables); r represents the residual vector; p represents the search direction; s_k represents the solution step vector; y_k represents the residual change vector; H_k represents the inverse Hessian approximation matrix/operator; C represents the linear constraint transformation matrix; \alpha_k represents the line search step length parameter.


## 3. Algorithmic Implementation

**lbfgs-two-loop-recursion-algorithm**
$$
\begin{algorithmic}
\State $q \leftarrow r_k, \quad \hat{m} \leftarrow \min(m, k)$
\For{$i = k - 1 \text{ down to } k - \hat{m}$}
\State $\rho_i \leftarrow \frac{1}{y_i^T s_i}$
\State $\alpha_i \leftarrow \rho_i s_i^T q$
\State $q \leftarrow q - \alpha_i y_i$
\EndFor
\State $p_k \leftarrow H_0^k q \quad \text{where } H_0^k = \hat{K}^{-1} = \begin{bmatrix} K_{uu}^{-1} & 0 \\ 0 & K_{dd}^{-1} \end{bmatrix}$
\For{$i = k - \hat{m} \text{ to } k - 1$}
\State $\beta \leftarrow \rho_i y_i^T p_k$
\State $p_k \leftarrow p_k + s_i (\alpha_i - \beta)$
\EndFor
\State $p_k \leftarrow -p_k$
\Return $p_k$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS method with adaptive mesh refinement.pdf, Section 3.2, p. 11, Algorithm 1_

**constrained-lbfgs-monolithic-step**
$$
\begin{algorithmic}
\State $\text{Assemble global FE residual } \hat{r}_k = [r_u(x_k); r_d(x_k)]$
\State $r_k = C^T \hat{r}_k \quad \text{(filter residual at constrained nodes)}$
\State $\text{Compute search direction } \hat{p}_k = -H_k r_k \text{ via L-BFGS two-loop recursion}$
\State $p_k = C \hat{p}_k \quad \text{(enforce constraint kinematics)}$
\State $\text{Determine step size } \alpha_k > 0 \text{ satisfying strong Wolfe conditions } \Pi(x_k + \alpha_k p_k) \le \Pi(x_k) + c_1 \alpha_k r_k^T p_k$
\State $x_{k+1} = x_k + \alpha_k p_k$
\State $s_k = x_{k+1} - x_k, \quad y_k = r_{k+1} - r_k$
\State $\text{Update L-BFGS memory buffer with vector-pair } \{s_k, y_k\} \text{ (evicting oldest pair if } k > m\text{)}$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS method with adaptive mesh refinement.pdf, Section 3.2, p. 12, Algorithm 2_


## 4. Known Pitfalls

- **lbfgs-dense-matrix-storage-exhaustion**: Classical BFGS updates add rank-two outer product modifications y_k y_k^T and B_k s_k (B_k s_k)^T to sparse FE stiffness matrices. This destroys finite element matrix sparsity and converts sparse systems into fully dense n \times n matrices, causing severe memory allocation failure on large 2D/3D meshes. L-BFGS circumvents this by storing only m vector pairs \{s_i, y_i\} (typically m = 5 to 10). _(Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS method with adaptive mesh refinement.pdf, Section 3.1, pp. 10-11)_
- **non-convex-curvature-breakdown**: For non-convex mechanical energy functionals (such as phase-field damage formulations during snap-back or crack initiation), the curvature condition s_k^T y_k > 0 can be violated. Performing standard BFGS matrix updates when s_k^T y_k \le 0 destroys the positive definiteness of H_{k+1}, causing search direction breakdown unless guarded by strong Wolfe line search or curvature-filtered modified updates. _(Source: Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf, Section 3.2, pp. 5-6)_
- **premature-energy-plateau-termination**: In brutal crack propagation simulations, total energy functional \Pi(x) can reach a flat numerical plateau after several hundred L-BFGS iterations while absolute residual norms ||r_u||_2 and ||r_d||_2 remain unacceptably large (>10^{-3}). Terminating L-BFGS based solely on energy flattening or loose increment thresholds under-predicts crack growth; strict residual-based convergence criteria are required. _(Source: Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS method with adaptive mesh refinement.pdf, Section 4.1, pp. 13-14)_

## References

- Jin et al. - A novel phase-field monolithic scheme for brittle crack propagation based on the limited-memory BFGS method with adaptive mesh refinement.pdf
- Ramos et al. - 2025 - Phase-field fracture analysis A gradient-based line search strategy for the L-BFGS algorithm.pdf
- Wu et al. - 2020 - On the BFGS monolithic algorithm for the unified phase field damage theory.pdf
- Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p-Multigrid.pdf
- Schneider_2020_A dynamical view of nonlinear conjugate gradient methods with applications to.pdf
