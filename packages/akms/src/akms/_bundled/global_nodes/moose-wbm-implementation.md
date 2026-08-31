---
id: moose-wbm-implementation
title: MOOSE WBM implementation details and usage
domain: phase-field
subdomain: procedural
tags:
- KKSPhaseConcentration
- KKSPhaseChemicalPotential
- KKSSplitCHCRes
- KKSMulti
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-wbm-kks-model
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-wbm-kks-model
---

# MOOSE WBM implementation details and usage

This response outlines how to set up a WBM (or KKS-type) multi-phase field simulation in MOOSE, focusing on variable setup, relevant kernels, free energy specification, and practical considerations. It also provides an input file skeleton for a WBM problem.

## Variable Setup
For a multi-phase, multi-component KKS simulation, you will need the following variables:
*   **Order Parameters ($\eta_i$)**: One order parameter variable (`eta`) for each phase. For an N-phase system, you will have N order parameters. These are typically `FIRST` order, `LAGRANGE` family variables. 
*   **Global Concentration ($c$)**: One global concentration variable (`c`) for each component. This represents the overall concentration of a component in the system. These are also typically `FIRST` order, `LAGRANGE` family variables. 
*   **Phase Concentrations ($c_i$)**: One phase concentration variable (`ci`) for each component within each phase. These are not directly solved as nonlinear variables but are material properties computed by `KKSPhaseConcentrationMultiPhaseMaterial`. 
*   **Chemical Potential ($\mu$)**: A chemical potential variable (`mu` or `w`) is needed for the Cahn-Hilliard equation in a split formulation. 

For a 3-phase, 2-component problem, you would typically need:
*   3 order parameter variables ($\eta_1, \eta_2, \eta_3$). 
*   2 global concentration variables ($c_A, c_B$).
*   2 chemical potential variables ($\mu_A, \mu_B$).
This results in a total of $3 + 2 + 2 = 7$ nonlinear variables.

## Kernels for Phase and Composition Evolution

### Phase Evolution (Allen-Cahn Equation)
The evolution of the order parameters ($\eta_i$) is governed by Allen-Cahn type equations. The relevant kernels are:
*   `TimeDerivative`: For the time derivative term of the Allen-Cahn equation. 
*   `NestedKKSMultiACBulkF`: Handles the bulk free energy term for the Allen-Cahn equation. It takes into account the free energies of all phases and their derivatives with respect to the order parameters. 
*   `NestedKKSMultiACBulkC`: Accounts for the chemical potential contribution to the Allen-Cahn equation. 
*   `ACInterface`: Handles the interfacial energy term (gradient energy) for the Allen-Cahn equation. 

### Composition Evolution (Cahn-Hilliard Equation)
The evolution of the global concentration ($c$) is governed by the Cahn-Hilliard equation. In a split formulation, this involves:
*   `CoupledTimeDerivative`: For the time derivative of the chemical potential. 
*   `NestedKKSMultiSplitCHCRes`: This kernel is used in the split Cahn-Hilliard formulation. It represents the bulk free energy contribution to the Cahn-Hilliard equation, specifically the term related to the derivative of the free energy with respect to the global concentration. 
*   `SplitCHWRes`: Handles the mobility and gradient terms related to the chemical potential in the split Cahn-Hilliard equation. 

## `KKSPhaseConcentration` and `KKSPhaseChemicalPotential`

### `KKSMultiPhaseConcentration`
This kernel enforces the conservation of the global concentration, stating that the global concentration `c` is a weighted sum of the phase concentrations `c_j`, where the weights are the switching functions `h_j`. 
The equation enforced is:
$$ c = \sum_j h_j(\eta_1, \dots, \eta_N) c_j $$ 
The non-linear variable for this kernel is one of the phase concentrations ($c_n$), while other phase concentrations ($c_j \neq c_n$) and the global concentration ($c$) are supplied as coupled variables. 

### `KKSPhaseChemicalPotential`
This kernel enforces the equality of chemical potentials between two phases.  For a two-phase system, this means $\frac{dF_a}{dc_a} = \frac{dF_b}{dc_b}$.  The non-linear variable for this kernel is one of the phase concentrations ($c_a$), and the other phase concentration ($c_b$) is a coupled variable. 

## Specifying Per-Phase Free Energies
Per-phase free energies are typically specified using `DerivativeParsedMaterial` objects.  Each phase will have its own `DerivativeParsedMaterial` that defines its free energy expression as a function of its phase concentration.  These materials should have `compute = false` and `material_property_names` and `additional_derivative_symbols` set to the phase concentration variable. 

## `KKSSplitCHCRes` Kernel
The `KKSSplitCHCRes` kernel is part of the split Cahn-Hilliard formulation.  It calculates the bulk free energy contribution to the Cahn-Hilliard equation, specifically the term $\frac{\partial F}{\partial c}$.  It leverages the KKS identity $dF/dc = dF_a/dc_a (= dF_b/dc_b)$.  The non-linear variable for this kernel is the global concentration `c`. 

## Multi-Phase Extension Kernels

### `KKSMultiPhaseConcentration`
As described above, this kernel enforces the global concentration conservation equation $c = \sum_j h_j c_j$. 

### `NestedKKSMultiACBulkC`
This kernel contributes to the Allen-Cahn equation for an order parameter ($\eta_i$). It accounts for the chemical potential term in the multi-phase KKS model. 

### `NestedKKSMultiACBulkF`
This kernel also contributes to the Allen-Cahn equation for an order parameter ($\eta_i$). It handles the bulk free energy contribution, which includes the free energies of all phases and their derivatives with respect to the order parameters. 

## Input File Skeleton for a WBM Problem

Here is a complete input file skeleton for a 3-phase, 1-component WBM problem, adapted from `kks_example_multiphase_nested.i`  and `kks_example_multiphase_nested_damped.i` .

` ` `ini
[Mesh]
  type = GeneratedMesh
  dim = 2
  nx = 20
  ny = 20
  xmin = 0
  xmax = 40
  ymin = 0
  ymax = 40
  elem_type = QUAD4
[]

[Variables]
  # Global concentration
  [c]
    order = FIRST
    family = LAGRANGE
  []

  # Order parameters for 3 phases
  [eta1]
    order = FIRST
    family = LAGRANGE
    initial_condition = 1.0 # Example initial condition
  []
  [eta2]
    order = FIRST
    family = LAGRANGE
    initial_condition = 0.0
  []
  [eta3]
    order = FIRST
    family = LAGRANGE
    initial_condition = 0.0
  []

  # Chemical potential for Cahn-Hilliard
  [mu]
    order = FIRST
    family = LAGRANGE
  []
[]

[AuxVariables]
  [Energy]
    order = CONSTANT
    family = MONOMIAL
  []
[]

[Materials]
  # Per-phase free energies (F1, F2, F3)
  [F1]
    type = DerivativeParsedMaterial
    property_name = F1
    expression = '20*(c1-0.2)^2' # Example free energy expression
    material_property_names = 'c1'
    additional_derivative_symbols = 'c1'
    compute = false
  []
  [F2]
    type = DerivativeParsedMaterial
    property_name = F2
    expression = '20*(c2-0.5)^2'
    material_property_names = 'c2'
    additional_derivative_symbols = 'c2'
    compute = false
  []
  [F3]
    type = DerivativeParsedMaterial
    property_name = F3
    expression = '20*(c3-0.8)^2'
    material_property_names = 'c3'
    additional_derivative_symbols = 'c3'
    compute = false
  []

  # KKS Multi-Phase Concentration Material
  # This material computes the phase concentrations (c1, c2, c3)
  [KKSPhaseConcentrationMultiPhaseMaterial]
    type = KKSPhaseConcentrationMultiPhaseMaterial
    global_cs = 'c' # Global concentration variable
    all_etas = 'eta1 eta2 eta3' # All order parameters
    hj_names = 'h1 h2 h3' # Switching functions
    ci_names = 'c1 c2 c3' # Phase concentrations (computed properties)
    ci_IC = '0.2 0.5 0.8' # Initial guess for phase concentrations
    Fj_names = 'F1 F2 F3' # Per-phase free energy materials
    min_iterations = 1
    max_iterations = 1000
    absolute_tolerance = 1e-11
    relative_tolerance = 1e-10
    # damped_Newton = true # Uncomment for damped Newton solver
    # conditions = C # Uncomment if using damped Newton with conditions
  []

  # KKS Multi-Phase Concentration Derivatives Material
  # This material computes derivatives needed by kernels
  [KKSPhaseConcentrationMultiPhaseDerivatives]
    type = KKSPhaseConcentrationMultiPhaseDerivatives
    global_cs = 'c'
    all_etas = 'eta1 eta2 eta3'
    Fj_names = 'F1 F2 F3'
    hj_names = 'h1 h2 h3'
    ci_names = 'c1 c2 c3'
  []

  # Switching functions for each phase (h1, h2, h3)
  # These define how the phases mix
  [h1]
    type = SwitchingFunction3PhaseMaterial
    eta_i = eta1
    eta_j = eta2
    eta_k = eta3
    property_name = h1
  []
  [h2]
    type = SwitchingFunction3PhaseMaterial
    eta_i = eta2
    eta_j = eta3
    eta_k = eta1
    property_name = h2
  []
  [h3]
    type = SwitchingFunction3PhaseMaterial
    eta_i = eta3
    eta_j = eta1
    eta_k = eta2
    property_name = h3
  []

  # Barrier functions for each phase (g1, g2, g3)
  # Used in Allen-Cahn bulk free energy
  [g1]
    type = BarrierFunctionMaterial
    g_order = SIMPLE
    eta = eta1
    function_name = g1
  []
  [g2]
    type = BarrierFunctionMaterial
    g_order = SIMPLE
    eta = eta2
    function_name = g2
  []
  [g3]
    type = BarrierFunctionMaterial
    g_order = SIMPLE
    eta = eta3
    function_name = g3
  []

  # Constant properties (mobility, interfacial energy coefficient)
  [constants]
    type = GenericConstantMaterial
    prop_names = 'L kappa M'
    prop_values = '0.7 1.0 0.025'

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
