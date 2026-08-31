---
id: moose-phase-field-numerics
title: MOOSE Phase Field Constraints and Numerical Techniques
domain: phase-field
subdomain: algorithmic
tags:
- constraints
- mass-conservation
- time-stepping
- nucleation
- adaptive-dt
- stabilization
- interface-width
- BDF2
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: medium
reading_priority: full
akms_schema: v2
edges:
- to: moose-derivative-parsed-material
  type: requires
  weight: 0.6
  note: Uses DerivativeParsedMaterial for free energy definitions
- to: moose-allen-cahn-cahn-hilliard
  type: requires
  weight: 0.7
  note: Numerical techniques applied to AC/CH solves
- to: moose-jfnk-preconditioning
  type: requires
  weight: 0.5
  note: Phase field preconditioning uses JFNK infrastructure
- to: tgs-dom-time-integration
  type: implements
  weight: 0.5
  note: Phase field time integration strategies
---

# MOOSE Phase Field Constraints and Numerical Techniques

Framework knowledge node covering 2 aspect(s) of Phase Field Constraints and Numerical Techniques.

## Constraint enforcement and numerical stabilization

MOOSE employs various numerical techniques for phase field simulations, including specific approaches for nucleation events and time step adaptivity. The framework provides kernels for solving both Allen-Cahn and Cahn-Hilliard equations, allowing for different solution strategies.

## Phase Field Nucleation
MOOSE handles nucleation events through a `DiscreteNucleation` system . This system artificially triggers and stabilizes nuclei formation by locally modifying the free energy density or directly changing an order parameter .

### Classes & Methods
*   `DiscreteNucleationInserter`: A user object that manages a global list of active nucleus positions .
*   `DiscreteNucleationMap`: A user object that maintains a smooth density map for nuclei locations, obtained from a `DiscreteNucleationInserter` .
*   `DiscreteNucleation`: A material that calculates a local free energy penalty based on the difference between concentration variables and their target concentrations .
*   `DiscreteNucleationTimeStep`: A postprocessor that provides a time step limit for new nuclei, used with `IterationAdaptiveDT` .

### Parameters
*   `DiscreteNucleation::penalty`: `Real`, default `20.0`. Penalty factor for enforcing target concentrations .
*   `DiscreteNucleation::penalty_mode`: `MooseEnum`, default `MATCH`. Determines if the target concentration is matched, or taken as a minimum or maximum .
*   `DiscreteNucleationTimeStep::dt_max`: `Real`. Time step to cut back to at the start of a nucleation event .
*   `DiscreteNucleationTimeStep::p2nucleus`: `Real`, range `(0, 1)`. Maximum probability for more than one nucleus to appear during a time step .

### Free Energy Penalty Based Nucleation
The `DiscreteNucleation` material implements a harmonic form of a free energy penalty to bias the system's thermodynamics, driving the formation of nuclei .

### Direct Order Parameter Modification
For non-conserved order parameters, direct modification can be achieved by applying a `DiscreteNucleationForce` and a `Reaction` kernel to a reserved order parameter .

## Time Integration Schemes
MOOSE's `Transient` executioner allows for time-dependent simulations . The `scheme` parameter in the `Executioner` block determines the `TimeIntegrator` to use . While the documentation mentions Backward Euler as a default , it also supports other schemes like BDF2 .

## Time Step Adaptivity
Time step adaptivity is supported through objects like `DiscreteNucleationTimeStep` and `IterationAdaptiveDT` . The `DiscreteNucleationTimeStep` postprocessor limits the time step based on two criteria: a user-defined `dt_max` at nucleus insertion and a nucleation rate-based limit to control the probability of multiple nucleation events within a single time step  .

### Equations
The probability of more than two nucleation events ($p_{2nuc}$) is calculated as:
$$
p_{2nuc} = 1-(1+\lambda_{2nuc})e^{-\lambda_{2nuc}} \label{eq:p2nuc} \tag{1}
$$
where $\lambda_{2nuc}$ is the total nucleation rate over the simulation cell . This equation is numerically inverted to obtain $\lambda_{2nuc}$ for a given $p_{2nuc}$ .

## Mass Conservation for Cahn-Hilliard
The Cahn-Hilliard equation, which describes mass conservation, can be solved in two ways within MOOSE .
1.  **Direct solution of the fourth-order equation**: This involves solving the equation directly .
2.  **Split into two second-order equations**: This approach solves for concentration ($c_i$) and chemical potential ($\mu_i$) separately . This method is noted to improve solve convergence .

### Equations
The residual for the direct solution of the Cahn-Hilliard equation is:
$$
\boldsymbol{\mathcal{R}}_{c_i} = \left( \frac{\partial c_i}{\partial t}, \psi_m \right) + \left( \kappa_i \nabla^2 c_i, \nabla \cdot (M_i \nabla \psi_m ) \right) + \left( M_i \left( \nabla \frac{\partial f_{loc} }{\partial c_i} + \nabla  \frac{\partial E_d}{\partial c_i} \right), \nabla \psi_m \right) \label{eq:ch_direct_residual} \tag{2}
$$ 
For the split form, the two residual equations are:
$$
\begin{aligned}
	\boldsymbol{\mathcal{R}}_{\mu_i} &=& \left(  \frac{\partial c_i}{\partial t}, \psi_m \right) + \left( M_i  \nabla \mu_i, \nabla \psi_m \right) \\
  \boldsymbol{\mathcal{R}}_{c_i} &=& \left( \left( -\kappa_i \nabla^2 c_i +  \frac{\partial f_{loc}}{\partial c_i} + \frac{\partial E_d}{\partial c_i} - \mu_i \right), \psi_m \right)
\end{aligned} \label{eq:ch_split_residual} \tag{3}
$$ 

## Order Parameter Constraint $\Sigma\eta_i = 1$
The provided context does not explicitly detail the numerical techniques used for enforcing the order parameter constraint $\Sigma\eta_i = 1$, such as penalty methods, Lagrange multipliers, or variable elimination.

## Numerical Stabilization
The provided context does not explicitly mention numerical stabilization techniques like anti-trapping currents for sharp-interface limits.

## Interface Width Control
The provided context does not explicitly detail the relationship between $\kappa$, interface width ($W$), and mesh size requirements. However, the `DiscreteNucleationMap` user object has an `int_width` parameter for the nucleus interface width .

## Notes
The MOOSE phase field module is designed to simplify the implementation of phase field models by leveraging common structures like the Cahn-Hilliard and Allen-Cahn equations and free energy functionals . The framework uses PETSc for solving nonlinear equations  and offers different solution methods like `NEWTON`, `JFNK`, and `PJFNK` . Preconditioning options such as LU decomposition and Additive Schwartz Method (ASM) are available to improve performance .


## Phase field time stepping and preconditioning strategies

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
