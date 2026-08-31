---
id: fem-tl-matrix-free-action
title: Matrix-Free Internal Force & Tangent Action
domain: computational-mechanics
subdomain: finite-elements
tags:
- fem
- finite-strain
- total-lagrangian
- matrix-free
- gpu
status: established
confidence: 0.9
source: hybrid
edges:
- to: fem-tl-weak-form
  type: requires
  weight: 1.0
- to: fem-tl-linearization
  type: requires
  weight: 1.0
- to: fem-tl-b-matrix
  type: requires
  weight: 0.9
context_size: medium
reading_priority: full
content_ref: null
akms_schema: v2
---

# Matrix-Free Internal Force & Tangent Action

## Summary

Matrix-free total Lagrangian finite element formulations evaluate internal force residual vectors and tangent stiffness matrix-vector actions without explicitly assembling or storing global sparse stiffness matrices. By fusing element restriction operators, basis polynomial evaluations, and quadrature-point constitutive updates into GPU-accelerated compute kernels, matrix-free methods overcome memory bandwidth limits in high-order iterative solvers.

## 1. Core Concept

In non-linear finite strain solid mechanics, traditional finite element solvers assemble and store large sparse tangent stiffness matrices at each Newton iteration. For large-scale or high-order discretizations, sparse matrix assembly and storage become bottlenecked by GPU memory capacity and memory bandwidth. Matrix-free operator evaluations eliminate global matrix assembly by directly computing the action of the residual vector and linearized tangent Jacobian on candidate displacement vectors. This is achieved via partial assembly, which composes element restriction operators, quadrature-point basis evaluations, point-wise material constitutive updates (incorporating Second Piola-Kirchhoff stresses S and material tangent moduli C^{SE}), and geometric stiffness actions in a single fused computational pass.

## 2. Mathematical Formulation

**Matrix-Free Internal Force Residual Evaluation**
$$
f^{\mathrm{int}} = \sum_{e} E_e^T \left( [B_I \quad B_{\xi}]^T W^e \Lambda \begin{bmatrix} f_0 \\ f_1 \end{bmatrix} \right)
$$
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf, Sec. II-B, Eqs. 8–10, pp. 2–3_

**Matrix-Free Action of Total Lagrangian Tangent Jacobian**
$$
J \, \mathrm{d}u = \sum_{e} E_e^T \left( [B_I \quad B_{\xi}]^T W^e \Lambda \begin{bmatrix} \hat{f}_{0,0} & \hat{f}_{0,1} \\ \hat{f}_{1,0} & \hat{f}_{1,1} \end{bmatrix} [B_I \quad B_{\xi}] E_e \, \mathrm{d}u \right)
$$
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf, Sec. II-B, Eq. 11, p. 3_

**Total Lagrangian Material and Geometric Tangent Moduli Split**
$$
K^{\mathrm{mat}}_{0IJ} = \int_{\Omega_0} B_{0I}^T C^{SE} B_{0J} \, \mathrm{d}\Omega_0, \quad K^{\mathrm{geo}}_{0IJ} = I \int_{\Omega_0} B_{0I}^T S B_{0J} \, \mathrm{d}\Omega_0
$$
_Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 6.5, p. 364; Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf, Sec. 3.4.1, Eqs. 3.99–3.102, pp. 94–96_

**Notation:**
{'f^{\\mathrm{int}}': 'Assembled global internal force vector.', 'J': 'Global Jacobian matrix operator (tangent stiffness).', 'E_e': 'Element restriction operator mapping global DOFs to local element DOFs.', 'B_I, B_{\\xi}': 'Element basis functions and parametric gradient evaluation matrices at quadrature points.', 'W^e': 'Quadrature integration weight tensor.', 'C^{SE}': 'Second Piola-Kirchhoff material tangent constitutive tensor.', 'S': 'Second Piola-Kirchhoff stress tensor.', '\\mathrm{d}u': 'Vector of incremental nodal displacements.'}


## 3. Algorithmic Implementation

**Matrix-Free Tangent Stiffness Action Algorithm**
$$
\begin{algorithmic}
\State $Given global displacement vector u, direction vector \mathrm{d}u, mesh connectivity, and material parameters$
\State $Initialize global action vector y \gets 0$
\For{$e \gets 1 \text{ to } n_e$}
\State $Gather local element displacement u_e \gets E_e u \text{ and direction } \mathrm{d}u_e \gets E_e \mathrm{d}u$
\State $Interpolate quadrature displacements u_q \gets B_I u_e \text{ and gradients } \nabla_{\xi} u_q \gets B_{\xi} u_e$
\State $Compute deformation gradient F_q = I + \nabla_X u_q \text{ and strain increment } \mathrm{d}E_q$
\State $Evaluate point-wise linearized tangent response \hat{f}_{q} \gets \Lambda(F_q, C^{SE}_q, S_q) \cdot [B_I \quad B_{\xi}] \mathrm{d}u_e$
\State $Apply quadrature weights and basis transpose w_e \gets [B_I \quad B_{\xi}]^T (W^e \cdot \hat{f}_{q})$
\State $Scatter accumulate into global action vector y \gets y + E_e^T w_e$
\EndFor
\Return $y$
\end{algorithmic}
$$
Taichi Mapping: [INSUFFICIENT SOURCE]
_Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf, Sec. II-B, Eqs. 8–11, pp. 2–3_


## 4. Known Pitfalls

- **High Memory Bandwidth Bottlenecks from Explicit Matrix Assembly**: Assembling and storing global sparse tangent stiffness matrices for high-order finite element discretizations imposes severe GPU memory bandwidth limitations and high storage overhead. Mitigation: Use matrix-free operator evaluations ("partial assembly") where basis evaluations, quadrature point stress updates, and element restrictions are fused into high-throughput parallel compute kernels. _(Source: Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf, Sec. I & Sec. II-B, Fig. 7, pp. 1, 4)_
- **Inconsistent Tangent Linearization in Matrix-Free Action**: Computing the Jacobian action J \mathrm{d}u using un-linearized stress states or omitting geometric stiffness contributions (K^{\mathrm{geo}}) destroys the quadratic convergence of Krylov-Newton solvers. Mitigation: Ensure that point-wise linearization at quadrature points accounts for both material tangent moduli C^{SE} and initial stress geometric terms S. _(Source: Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf, Box 6.5, p. 364; Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \\(p\\)-Multigrid.pdf, Sec. II-A & Sec. II-B, pp. 2–3)_

## References

- Belytschko_Nonlinear Finite Elements for Continua and Structures.pdf
- Borst_Crisfield_2012_Nonlinear finite element analysis of solids and structures.pdf
- Brown et al_2022_Performance Portable Solid Mechanics via Matrix-Free \$p-Multigrid.pdf
