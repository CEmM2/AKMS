---
id: moose-jfnk-architecture
title: MOOSE JFNK solver architecture in MOOSE
domain: solver
subdomain: algorithmic
tags:
- JFNK
- matrix-free
- GMRES
- PETSc-SNES
- jacobian-vector-product
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-jfnk-preconditioning
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-jfnk-preconditioning
- to: cm-solver-matrixfree
  type: implements
  weight: 0.9
  note: JFNK matrix-free Newton-Krylov architecture
---

# MOOSE JFNK solver architecture in MOOSE

MOOSE leverages PETSc's SNES (Scalable Nonlinear Equation Solvers) component to configure Newton-based nonlinear iterations, including Jacobian-Free Newton-Krylov (JFNK) methods . The core of JFNK in MOOSE involves approximating the Jacobian-vector product using a finite-difference approach, which is then utilized by Krylov subspace methods like GMRES for the linear solve . For preconditioning, MOOSE assembles an approximate Jacobian matrix, even when the full Jacobian is not explicitly formed .

## Newton Nonlinear Iteration Setup with PETSc SNES

MOOSE sets up the Newton nonlinear iteration by interfacing with PETSc's SNES component through the `NonlinearSystem` class . The `NonlinearSystem::getSNES()` method retrieves the PETSc SNES object, allowing MOOSE to configure its behavior . The overall nonlinear problem is represented as $\mathbf{R}(\mathbf{u}) = \mathbf{0}$ , and Newton's method iteratively solves the linear system $\mathbf{J}(\mathbf{u}^{i-1}) \delta \mathbf{u}^{i} = -\mathbf{R}(\mathbf{u}^{i-1})$ at each step .

## Matrix-Free Jacobian-Vector Product Approximation

For JFNK, MOOSE approximates the Jacobian-vector product $\mathbf{J}(\mathbf{u}^{i-1}) \mathbf{y}$ using a finite-difference like approximation :

$$
\mathbf{J}(\mathbf{u}^{i-1}) \mathbf{y} \approx \frac{\mathbf{R}(\mathbf{u}^{i-1} + \epsilon \mathbf{y}) - \mathbf{R}(\mathbf{u}^{i-1})}{\epsilon} \quad (1)
$$ 

Here, $\mathbf{R}(\mathbf{u})$ is the residual vector, $\mathbf{u}$ is the current solution vector, $\mathbf{y}$ is a perturbation vector, and $\epsilon$ is a scalar chosen by PETSc to ensure accuracy . This approximation avoids the explicit formation of the Jacobian matrix . The `mffd_type` parameter in the `[Executioner]` block can specify the finite differencing type, with "wp" (Walker and Pernice) being the default .

## Krylov Method (GMRES) and Jv Product

Krylov methods, such as GMRES (Generalized Minimal Residual method), are used to solve the linear system arising from each Newton iteration . GMRES is the default linear solution algorithm in PETSc and MOOSE due to its flexibility, as it does not assume properties like symmetry for the Jacobian . The Krylov method uses the matrix-free Jacobian-vector product (Equation 1) to construct the Krylov subspace without explicitly forming the Jacobian matrix . During each linear step of JFNK, the `computeQpResidual` method is called to approximate the action of the Jacobian on the Krylov vector .

## Preconditioning Matrix in JFNK

Even with JFNK, preconditioning is crucial for efficient convergence . In MOOSE, when using Preconditioned JFNK (`PJFNK`), an approximate Jacobian matrix $\mathbf{M}$ is assembled for preconditioning . This preconditioning matrix is typically easier to compute than the exact Jacobian and is used to improve the convergence of the Krylov solver . By default, MOOSE uses block-diagonal preconditioning, where each block corresponds to a single MOOSE variable . The `computeQpJacobian` and `computeQpOffDiagJacobian` methods are used to compute values for this preconditioning matrix .

## `solve_type = JFNK` vs `solve_type = NEWTON`

MOOSE provides different `solve_type` options in the `[Executioner]` block :

*   **`JFNK`**: Jacobian-Free Newton-Krylov . This option activates matrix-free Jacobian-vector products and does not assemble a preconditioning matrix . It is generally used when forming the full Jacobian is too expensive or complex, but it often performs poorly without preconditioning .
*   **`PJFNK`**: Preconditioned Jacobian-Free Newton-Krylov . This is the default solve type . It uses matrix-free Jacobian-vector products but includes a preconditioner built from an approximate Jacobian matrix . This is generally preferred over `JFNK` for better convergence.
*   **`NEWTON`**: Full Newton Solve . This option uses the Jacobian provided by kernels (which may not be exact) for the Krylov solve . It requires an accurate Jacobian for effective convergence .

The choice between `JFNK`, `PJFNK`, and `NEWTON` depends on the problem's nonlinearity, the cost of forming the Jacobian, and the desired convergence properties. `PJFNK` is often a good balance, providing robustness without the full cost of assembling an exact Jacobian.

## Key PETSc Options and MOOSE Equivalents

MOOSE allows users to configure PETSc options through parameters in the `[Executioner]` block .

*   **`-snes_type`**: Controls the type of nonlinear solver.
    *   MOOSE's `solve_type` parameter maps to this. For example, `solve_type = JFNK` or `solve_type = PJFNK` internally configures the SNES type for matrix-free operation .
*   **`-ksp_type`**: Controls the type of Krylov subspace method for the linear solve.
    *   GMRES is the default in MOOSE . You can set this directly using `petsc_options_iname = '-ksp_type'` and `petsc_options_value = 'gmres'` .
*   **`-pc_type`**: Controls the type of preconditioner.
    *   MOOSE's default preconditioning is block-diagonal . Common options include `ilu` (incomplete LU), `bjacobi` (block Jacobi), `asm` (Additive Schwartz Method), `lu` (full LU), `gamg` (Geometric AMG), and `hypre` (Hypre preconditioners like BoomerAMG) . These can be set via `petsc_options_iname = '-pc_type'` and `petsc_options_value = 'ilu'` (or other types) .

### MOOSE `[Executioner]` Block Parameters

` ` `ini
[Executioner]
  type = Steady
  solve_type = PJFNK # or JFNK, NEWTON, FD, LINEAR
  petsc_options_iname = '-snes_type -ksp_type -pc_type -ksp_gmres_restart -pc_asm_overlap'
  petsc_options_value = 'newtonls   gmres    bjacobi  30                2'
[]
` ` `  

## Convergence Monitors

MOOSE provides several convergence monitors for both nonlinear and linear solves:

*   **Nonlinear Residual Norm**: MOOSE prints the norm of the nonlinear residual, $\|\vec{R}(\vec{u}_n)\|$, at each Newton iteration . Convergence is typically checked against absolute (`nl_abs_tol`) and relative (`nl_rel_tol`) tolerances .
*   **Linear Residual Norm**: For the linear solve within each Newton iteration, MOOSE can print the norm of the linear residual, $\|\vec{\rho}_k\|$, if `print_linear_residuals = true` is set in the `[Outputs]` block .
*   **SNES Line Search**: PETSc's SNES line search monitors the step size $\alpha$ in the update $\mathbf{u}^{i} = \mathbf{u}^{i-1} + \alpha \delta \mathbf{u}^{i}$ . The line search type can be controlled by PETSc options like `-snes_linesearch_type` .

## Classes & Methods

*   `NonlinearSystem::getSNES()`: Retrieves the PETSc SNES object for the nonlinear system .
*   `FEProblemBase::computeResidualSys()`: Computes the residual vector for a given system .
*   `FEProblemBase::computeJacobianSys()`: Computes the Jacobian matrix for a given system .
*   `Moose::ST_JFNK`, `Moose::ST_PJFNK`, `Moose::ST_NEWTON`: Enumerations defining the solve types .

## Equations

1.  **Newton's Method Linear System**:
    $$
    \mathbf{J}(\mathbf{u}^{i-1}) \delta \mathbf{u}^{i} = -\mathbf{R}(\mathbf{u}^{i-1})
    $$ 
2.  **Matrix-Free Jacobian-Vector Product Approximation**:
    $$
    \mathbf{J}(\mathbf{u}^{i-1}) \mathbf{y} \approx \frac{\mathbf{R}(\mathbf{u}^{i-1} + \epsilon \mathbf{y}) - \mathbf{R}(\mathbf{u}^{i-1})}{\epsilon}
    $$ 
3.  **Nonlinear Solution Update**:
    $$
    \mathbf{u}^{i} = \mathbf{u}^{i-1} + \alpha \delta \mathbf{u}^{i}
    $$ 

## Parameters

*   `solve_type`: `MooseEnum` (`PJFNK`, `JFNK`, `NEWTON`, `FD`, `LINEAR`). Default is `PJFNK`. Controls the general method for

Wiki pages you might want to explore:
- [Problem Solving Architecture (idaholab/moose)](https://deepwiki.com/idaholab/moose#3)

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
