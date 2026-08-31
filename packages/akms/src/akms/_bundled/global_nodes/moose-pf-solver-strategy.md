---
id: moose-pf-solver-strategy
title: MOOSE Phase field time stepping and preconditioning strategies
domain: phase-field
subdomain: algorithmic
tags:
- time-stepping
- adaptive-dt
- preconditioning
- operator-splitting
- AMR-interface
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-phase-field-numerics
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-phase-field-numerics
- to: tgs-dom-time-integration
  type: implements
  weight: 0.5
  note: Phase field solver strategies and time adaptivity
---

# MOOSE Phase field time stepping and preconditioning strategies

The MOOSE framework provides extensive capabilities for solving phase field problems, including options for operator splitting, preconditioning, and mesh adaptivity. The `Phase Field Module`  supports both Allen-Cahn and Cahn-Hilliard equations, with different solution approaches for the latter.

## Operator Splitting and Semi-Implicit Schemes

### Allen-Cahn Equation 
The Allen-Cahn equation, which describes non-conserved order parameters, is typically solved directly. The residual equation is split into three kernels: `TimeDerivative`, `ACInterface`, and `AllenCahn` .

### Cahn-Hilliard Equation 
The Cahn-Hilliard equation, which describes conserved order parameters, can be solved in two ways:

1.  **Direct Solution**: This involves solving the fourth-order equation directly . The kernels involved are `TimeDerivative`, `CHInterface`, and `CahnHilliard` .
2.  **Split Solution**: This approach splits the fourth-order equation into two second-order equations by introducing a chemical potential variable, $\mu_i$ . This splitting can improve convergence . The kernels used for the split form are `CoupledTimeDerivative`, `SplitCHWRes`, and `SplitCHParsed` . MOOSE supports both "forward" and "reverse" split Cahn-Hilliard problems  .

## Preconditioning for Coupled $\eta + c$ Systems

MOOSE leverages PETSc for solving nonlinear systems . For coupled systems, effective preconditioning is crucial.

### Solution Methods 
*   `NEWTON`: Requires a full and accurate Jacobian.
*   `JFNK`: Jacobian-Free Newton-Krylov, does not require Jacobian terms but often needs preconditioning.
*   `PJFNK`: Preconditioned JFNK, uses the Jacobian for preconditioning but it doesn't need to be fully correct.

### Preconditioning Options 
*   **LU Decomposition**: Most accurate but expensive and does not scale well beyond tens of processors . Useful for debugging.
    ` ` `ini
    petsc_options_iname = '-pc_type'
    petsc_options_value = 'lu'
    ` ` ` 
*   **Additive Schwartz Method (ASM)**: A domain decomposition method that works well for most models, especially with the split Cahn-Hilliard equations . Increasing `-pc_asm_overlap` improves performance at higher computational cost .
    ` ` `ini
    petsc_options_iname = '-pc_type -ksp_grmres_restart -sub_ksp_type -sub_pc_type -pc_asm_overlap'
    petsc_options_value = 'asm      31                  preonly       lu           2'
    ` ` ` 
*   **ASM/ILU**: Incomplete factorization method, default and works well for elliptic problems .
*   **BoomerAMG**: Algebraic MultiGrid Method (Hypre implementation). Works well for Allen-Cahn and direct Cahn-Hilliard, but performs poorly with split Cahn-Hilliard equations .
    ` ` `ini
    petsc_options_iname = '-pc_type -pc_hypre_type -ksp_gmres_restart -pc_hypre_boomeramg_strong_threshold'
    petsc_options_value = 'hypre    boomeramg      31                 0.7'
    ` ` ` 

### Block Structure for Coupled $\eta + c$ Systems
For coupled $\eta + c$ systems, the `FieldSplitPreconditioner`  (aliased as `FSP`) is designed to handle block matrices. It allows defining coupling between variables . The `PhysicsBasedPreconditioner`  (aliased as `PBP`) also allows individual physics to have their own preconditioners and defines a `solve_order` for block rows .

## `PhaseFieldSplit` Preconditioner
MOOSE does not have a specific `PhaseFieldSplit` preconditioner class by that exact name. However, the `FieldSplitPreconditioner`  and `PhysicsBasedPreconditioner`  provide the functionality for physics-based splitting. These allow you to define how different variables (e.g., $\eta$ and $c$) are coupled and preconditioned. The `Split` base class  provides options for `splitting_type` such as additive, multiplicative, symmetric multiplicative, and Schur .

## Convergence Difficulties and Mitigation
Stiffness in phase field problems often arises from the disparate time scales of the physical phenomena or the strong non-linearities.

*   **Operator Splitting**: For Cahn-Hilliard equations, using the split formulation can improve convergence .
*   **Preconditioning**: Appropriate PETSc preconditioners are crucial. As mentioned above, `ASM` is recommended for split Cahn-Hilliard equations, while `BoomerAMG` works well for Allen-Cahn and direct Cahn-Hilliard  .
*   **Time Integration**: Implicit time integration is generally used for phase field models .

## Mesh Adaptivity for Phase Field
Refining near interfaces and coarsening in the bulk is a common strategy for phase field problems to efficiently resolve sharp interfaces. While the provided context does not explicitly detail specific "indicators" for mesh adaptivity within the phase field module, MOOSE generally supports mesh adaptivity. Typically, indicators would be based on gradients of the order parameter ($\nabla \eta$) or other field variables that define the interface. High gradients would trigger refinement.

## `InterfaceWidth` or Similar Postprocessor
The provided context does not explicitly mention an `InterfaceWidth` postprocessor. However, MOOSE's modular design allows for the creation of custom postprocessors to monitor various quantities. A postprocessor to monitor interface resolution would likely involve calculating the width of the interface based on the order parameter profile.

## Solver Configuration Examples

Here's a typical solver configuration for a multi-phase problem involving coupled Allen-Cahn and split Cahn-Hilliard equations, using `PJFNK` with `ASM` preconditioning, as suggested for split Cahn-Hilliard problems .

` ` `ini
[Executioner]
  type = Transient
  solve_type = PJFNK # Preconditioned JFNK
  petsc_options_iname = '-pc_type -ksp_grmres_restart -sub_ksp_type -sub_pc_type -pc_asm_overlap'
  petsc_options_value = 'asm      31                  preonly       lu           2'
  # Other time stepping parameters
  dt = 1e-3
  end_time = 1.0
  nl_abs_tol = 1e-6
  nl_rel_tol = 1e-8
  nl_max_its = 20
  l_max_its = 100
[]

[Problem]
  type = ReferenceResidualProblem
  # Other problem settings
[]

[Variables]
  [./eta]
    order = FIRST
    family = LAGRANGE
  [../]
  [./c]
    order = FIRST
    family = LAGRANGE
  [../]
  [./mu] # Chemical potential for split Cahn-Hilliard
    order = FIRST
    family = LAGRANGE
  [../]
[]

[Kernels]
  # Allen-Cahn kernels for 'eta'
  [./ac_time]
    type = TimeDerivative
    variable = eta
  [../]
  [./ac_interface]
    type = ACInterface
    variable = eta
    kappa = kappa_eta_prop
    L = L_eta_prop
  [../]
  [./ac_bulk]
    type = AllenCahn
    variable = eta
    L = L_eta_prop
    f_prime = f_prime_eta_prop
  [../]

  # Split Cahn-Hilliard kernels for 'c' and 'mu'
  [./ch_time]
    type = CoupledTimeDerivative
    variable = mu # Solves for mu, but time derivative of c
    coupled_variable = c
  [../]
  [./ch_mobility]
    type = SplitCHWRes
    variable = mu
    M = M_c_prop
  [../]
  [./ch_residual]
    type = SplitCHParsed
    variable = c
    kappa = kappa_c_prop
    f_prime = f_prime_c_prop
    coupled_variable = mu
  [../]
[]

[Materials]
  [./kappa_eta]
    type = GenericFunctionMaterial
    prop_name = kappa_eta_prop
    f_name = '1.0'
  [../]
  [./L_eta]
    type = GenericFunctionMaterial
    prop_name = L_eta_prop
    f_name = '1.0'
  [../]
  [./f_prime_eta]
    type = GenericFunctionMaterial
    prop_name = f_prime_eta_prop
    f_name = 'eta^3 - eta' # Example free energy derivative
  [../]
  [./kappa_c]
    type = GenericFunctionMaterial
    prop_name = kappa_c_prop
    f_name = '1.0'
  [../]
  [./M_c]
    type = GenericFunctionMaterial
    prop_name = M_c_prop
    f_name = '1.0'
  [../]
  [./f_prime_c]
    type = GenericFunctionMaterial
    prop_name = f_prime_c_prop
    f_name = 'c^3 - c' # Example free energy derivative
  [../]
[]
` ` `

## Classes & Methods

*   `FieldSplitPreconditioner::FieldSplitPreconditioner(const InputParameters & params)`: Constructor for the field split preconditioner, sets up the coupling matrix and decomposition split .
*   `PhysicsBasedPreconditioner::addSystem(unsigned int var, std::vector<unsigned int> off_diag, libMesh::PreconditionerType type)`: Adds a diagonal system and optionally off-diagonal ones, specifying the preconditioning type .
*   `Split::setup(NonlinearSystemBase & nl, const std::string & prefix)`: Sets up the split decomposition for a nonlinear system .
*   `SplitCHCRes::computeQpResidual()`: Computes the residual for the split Cahn-Hilliard concentration equation .

## Equations

### Allen-Cahn Equation (Strong Form) 
$$
\frac{\partial \eta_j}{\partial t} = -L \left( \frac{\partial f_{loc}}{\partial \eta_j}

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
