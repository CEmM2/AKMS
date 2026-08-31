---
id: moose-preconditioning
title: MOOSE Preconditioning strategies in MOOSE
domain: solver
subdomain: algorithmic
tags:
- SMP
- FDP
- PBP
- AMG
- HYPRE
- block-diagonal
- automatic-differentiation
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
---

# MOOSE Preconditioning strategies in MOOSE

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
