---
id: moose-jfnk-preconditioning
title: MOOSE Solver Configuration — JFNK and Preconditioning
domain: solver
subdomain: algorithmic
tags:
- JFNK
- newton-krylov
- preconditioning
- SMP
- AMG
- PETSc
- automatic-differentiation
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: medium
reading_priority: full
akms_schema: v2
edges:
- to: moose-petsc-interface
  type: requires
  weight: 0.8
  note: JFNK solver configured through PETSc interface
- to: cm-solver-matrixfree
  type: implements
  weight: 0.8
  note: Implements matrix-free JFNK with physics-based preconditioning
---

# MOOSE Solver Configuration — JFNK and Preconditioning

Framework knowledge node covering 2 aspect(s) of Solver Configuration — JFNK and Preconditioning.

## JFNK solver architecture in MOOSE

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


## Preconditioning strategies in MOOSE

MOOSE provides several preconditioning strategies to enhance the efficiency of solving nonlinear systems, including Single Matrix Preconditioner (SMP), Finite Difference Preconditioner (FDP), and Physics-Based Preconditioner (PBP) . These strategies can be configured within the `[Preconditioning]` block in the input file or through PETSc options .

## Preconditioning Strategies

### 1. Single Matrix Preconditioner (SMP)
The `SingleMatrixPreconditioner` builds a preconditioner using user-defined off-diagonal parts of the Jacobian . By default, for `PJFNK` solves, a block-diagonal preconditioning matrix is used where each block corresponds to a single MOOSE variable, ignoring off-diagonal Jacobian terms . You can specify off-diagonal entries using `off_diag_row` and `off_diag_column` parameters, or group variables using `coupled_groups` to generate off-diagonal Jacobians for all pairs within a group .

**Classes & Methods:**
*   `SingleMatrixPreconditioner::SingleMatrixPreconditioner(const InputParameters & params)`: Constructor that sets up the coupling matrix based on input parameters .
*   `SingleMatrixPreconditioner::validParams()`: Defines valid input parameters for SMP, including `coupled_groups`, `off_diag_row`, `off_diag_column`, and `full` .

**MOOSE Input Syntax:**
` ` `ini
[Preconditioning]
  [my_smp]
    type = SMP
    # Example for coupled_groups
    coupled_groups = 'var1,var2 var3,var4'
    # Example for off_diag_row and off_diag_column
    off_diag_row = 'var1 var2'
    off_diag_column = 'var2 var1'
  []
[]
` ` `

### 2. Finite Difference Preconditioner (FDP)
The `FiniteDifferencePreconditioner` builds a numerical Jacobian for preconditioning by finite differencing . This method is generally costly and is recommended primarily for testing and verification purposes . It can use either a "standard" finite difference approach or one based on "coloring" . The "standard" finite difference method will add off-diagonal entries to the coupling matrix .

**Classes & Methods:**
*   `FiniteDifferencePreconditioner::FiniteDifferencePreconditioner(const InputParameters & params)`: Constructor that initializes the finite difference type .
*   `FiniteDifferencePreconditioner::validParams()`: Defines valid input parameters, including `implicit_geometric_coupling` and `finite_difference_type` .

**Parameters:**
*   `finite_difference_type = "standard" | "coloring"` (type: `MooseEnum`, default: `"coloring"`): Specifies the finite differencing method .

### 3. Physics-Based Preconditioner (PBP)
The `PhysicsBasedPreconditioner` allows individual physics (variables) to have their own preconditioners . It decomposes the system into smaller linear systems, each corresponding to a variable, and applies a specified preconditioner to each . The order in which these block rows are solved can be specified using `solve_order` . Off-diagonal coupling terms can also be included . PBP must be used with the `JFNK` solve type .

**Classes & Methods:**
*   `PhysicsBasedPreconditioner::PhysicsBasedPreconditioner(const InputParameters & params)`: Constructor that sets up the coupling matrix, preconditioner types, and solve order .
*   `PhysicsBasedPreconditioner::addSystem(unsigned int var, std::vector<unsigned int> off_diag, libMesh::PreconditionerType type)`: Adds a diagonal system and optionally off-diagonal systems, specifying the type of preconditioning for that system .
*   `PhysicsBasedPreconditioner::setup()`: Fills in the preconditioning matrix by computing Jacobian blocks for diagonal and specified off-diagonal terms .
*   `PhysicsBasedPreconditioner::apply(const NumericVector<Number> & x, NumericVector<Number> & y)`: Computes the preconditioned vector by solving the individual systems in the specified order, accounting for off-diagonal couplings .

**MOOSE Input Syntax:**
` ` `ini
[Preconditioning]
  [my_pbp]
    type = PBP
    solve_order = 'temp pressure' # Example: solve temperature then pressure
    preconditioner = 'hypre hypre' # Example: use hypre for both
    off_diag_row = 'temp'
    off_diag_column = 'pressure'
  []
[]
` ` `

### 4. Block Diagonal vs. Block Off-Diagonal Coupling
MOOSE determines coupling between variables through a `CouplingMatrix` .
*   **Block Diagonal:** By default, for `PJFNK` solves, the preconditioning matrix is block-diagonal, meaning off-diagonal Jacobian terms are ignored . This is represented by setting 1s on the diagonal of the `CouplingMatrix` and 0s elsewhere .
*   **Block Off-Diagonal:** You can explicitly include off-diagonal coupling terms using parameters like `off_diag_row` and `off_diag_column` . These parameters specify which variable pairs should have their Jacobian blocks included in the preconditioning matrix . The `full = true` parameter can be used to include all possible couplings between variables for convenience .

### 5. Algebraic Multigrid (AMG) with HYPRE BoomerAMG
MOOSE leverages PETSc for solvers and preconditioners, including HYPRE's BoomerAMG . BoomerAMG is an algebraic multigrid method suitable for elliptic PDEs .

**Configuration through MOOSE:**
You configure HYPRE BoomerAMG using PETSc options, which can be set in the `Executioner` or `Preconditioning` blocks using `petsc_options_iname` and `petsc_options_value` .

**Parameters:**
*   `petsc_options_iname = '-pc_type -pc_hypre_type'` 
*   `petsc_options_value = 'hypre boomeramg'` 

Key BoomerAMG options include:
*   `-pc_hypre_boomeramg_strong_threshold`: Controls the coarsening mechanism by setting a threshold for matrix entries to be kept . Default is 0.25, but 0.7 is automatically set for 3D problems .
*   `-pc_hypre_boomeramg_max_levels`: Number of multigrid levels .
*   `-pc_hypre_boomeramg_coarsen_type`: Coarsening algorithm, e.g., `Falgout` (default), `HMIS`, or `PMIS` .
*   `-pc_hypre_boomeramg_agg_nl`: Number of levels for aggressive coarsening .
*   `-pc_hypre_boomeramg_agg_num_paths`: Number of pathways to consider for aggressive coarsening .
*   `-pc_hypre_boomeramg_truncfactor`: Truncation factor for interpolation .
*   `-pc_hypre_boomeramg_interp_type`: Type of interpolation, e.g., `classic` (default) or `ext+i` .

**MOOSE Input Syntax:**
` ` `ini
[Executioner]
  type = Steady
  petsc_options_iname = '-pc_type -pc_hypre_type -pc_hypre_boomeramg_strong_threshold'
  petsc_options_value = 'hypre    boomeramg    0.7'
[]
` ` `

### 6. Automatic Differentiation (AD) and Preconditioning
MOOSE uses forward mode automatic differentiation from the MetaPhysicL package to compute Jacobians . When `ADKernel` is used, the Jacobian is automatically calculated . While AD Jacobians can be slower to compute than hand-coded ones, they parallelize well and can benefit from a `NEWTON` solve type, potentially leading to decreased overall solve time .

The preconditioner is seldom the exact Jacobian because computing it is computationally expensive and memory-intensive . Even with AD, the preconditioner is an approximation of the Jacobian, not necessarily exact . The `PJFNK` solve type uses a preconditioning matrix that approximates the Jacobian . If the Jacobian is not exact, the Newton update might not effectively reduce the residual, potentially leading to unconverged iterations .

## Notes
The `FieldSplitPreconditioner` (FSP) is another preconditioner that allows custom preconditioning for each nonlinear variable . It can be used for block-diagonal preconditioning and is the default for `PJFNK` solves . While similar in concept to PBP, FSP is a separate implementation.

Other preconditioners mentioned in the codebase include `MooseStaticCondensationPreconditioner`  and `VariableCondensationPreconditioner` . These are specialized preconditioners for static and variable condensation, respectively.

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
