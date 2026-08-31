---
id: moose-wbm-kks-model
title: MOOSE WBM — Wheeler-Boettinger-McFadden Multi-Phase Model
domain: phase-field
subdomain: algorithmic
tags:
- WBM
- KKS
- Kim-Kim-Suzuki
- equal-chemical-potential
- per-phase-composition
- CALPHAD
- multi-phase
- lagrange-multiplier
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: large
reading_priority: full
akms_schema: v2
edges:
- to: moose-derivative-parsed-material
  type: requires
  weight: 0.6
  note: Uses DerivativeParsedMaterial for free energy definitions
- to: moose-multi-phase-component
  type: requires
  weight: 0.9
  note: WBM/KKS builds on multi-phase infrastructure
- to: moose-allen-cahn-cahn-hilliard
  type: requires
  weight: 0.7
  note: WBM uses Allen-Cahn for phase evolution
- to: cm-phase-field-fracture
  type: implements
  weight: 0.3
  note: WBM/KKS shares phase field variational framework
---

# MOOSE WBM — Wheeler-Boettinger-McFadden Multi-Phase Model

Framework knowledge node covering 3 aspect(s) of WBM — Wheeler-Boettinger-McFadden Multi-Phase Model.

## WBM multi-phase field model formulation

The Wheeler-Boettinger-McFadden (WBM) multi-phase field model in MOOSE is a framework for simulating phase transformations with multiple phases and compositions. It distinguishes itself by allowing each phase to have its own composition field, unlike models with a single global composition. MOOSE implements this through specific material and kernel classes that handle the free energy functional, enforce chemical potential equality, and manage phase and composition evolution.

## 1. The WBM Free Energy Functional

The total free energy in the WBM model, as implemented in MOOSE, is expressed as a sum over the individual phase free energies, weighted by switching functions, and includes gradient energy terms. For a multi-phase KKS system, the total free energy $F$ is given by:
$$
F = \sum_i h_i F_i + W \sum_i g_i + \sum_i \frac{\kappa_i}{2} |\nabla \eta_i|^2 \quad (1)
$$ 
Here, $h_i$ are switching functions, $F_i$ are the free energies of each phase $i$, $W$ is a double-well height parameter, $g_i$ are barrier functions, and $\kappa_i$ are gradient energy coefficients associated with the phase field variables $\eta_i$. 
The `KKSMultiFreeEnergy` AuxKernel calculates this total free energy. 

## 2. Key Distinction: Per-Phase Composition Fields

In the WBM model, each phase $i$ has its own composition field $c_i^k$ for component $k$. This is a key distinction from models that use a single global composition. MOOSE handles this by using a nested Newton iteration to solve for these per-phase concentrations.  The `KKSPhaseConcentrationMultiPhaseMaterial` class is responsible for computing these phase concentrations. 

## 3. Equal Chemical Potential Constraint

The constraint of equal chemical potential $\mu_i^k = \mu_j^k$ across phases for each component is enforced through a kernel. For a two-phase system, this is expressed as $dF_a/dc_a = dF_b/dc_b$.  The `KKSPhaseChemicalPotential` kernel enforces this equality.  This kernel takes the free energy functions for two phases (`fa_name` and `fb_name`) and their corresponding concentrations (`variable` for $c_a$ and `cb` for $c_b$) as parameters.  

## 4. Phase Evolution Equation

The phase evolution equation for $\phi_i$ (or $\eta_i$ in MOOSE's implementation) is generally given by:
$$
\frac{\partial \phi_i}{\partial t} = -L \left( \frac{\partial f}{\partial \phi_i} - \kappa \nabla^2 \phi_i + \lambda \right) \quad (2)
$$
where $\lambda$ is a Lagrange multiplier to enforce the constraint $\sum \phi_i = 1$.  MOOSE uses a Lagrange multiplier based constraint for keeping the sum of all phase order parameters equal to one.  This is demonstrated in input files like `lagrange_multiplier.i` where `eta1 + eta2 = 1` is enforced. 

## 5. Diffusion Equations

The evolution of each phase's composition and interdiffusion is handled by ensuring concentration conservation. The `KKSMultiPhaseConcentration` kernel enforces the concentration conservation equation $c = \sum_j h_j c_j$, where $c$ is the physical concentration and $c_j$ are the phase concentrations.  This kernel takes an array of phase concentrations (`cj`), the physical concentration (`c`), and switching functions (`hj_names`) as input. 

## 6. Implementation Classes

The primary MOOSE classes implementing the WBM model, particularly for multi-phase KKS, include:

*   `KKSPhaseChemicalPotential`: A kernel that enforces the equality of chemical potentials between phases. 
*   `KKSMultiPhaseConcentration`: A kernel that enforces the concentration conservation equation for multiple phases. 
*   `KKSPhaseConcentrationMultiPhaseMaterial`: A material class that computes the KKS phase concentrations using a nested Newton iteration to solve the equal chemical potential and concentration conservation equations for multiphase systems. 
*   `KKSMultiFreeEnergy`: An AuxKernel that computes the total free energy in a multi-phase KKS system, including chemical, barrier, and gradient terms. 

## 7. WBM vs. KKS in MOOSE

In MOOSE, the WBM and KKS models are closely related and often discussed within the same framework, particularly for multi-phase systems. The KKS model is a specific type of phase-field model for binary alloys.  The `KKSPhaseChemicalPotential` and `KKSMultiPhaseConcentration` classes are explicitly named with "KKS", indicating their role in implementing the KKS framework.   The documentation refers to "KKS" as a model with "per-phase concentrations, two phases" or "per-phase concentrations, per-sublattice concentrations, multiple phases" . The WBM model is described as handling "$N$ phases, $N$ phase order parameters" . Essentially, the KKS model, as implemented in MOOSE, leverages the WBM framework's ability to handle per-phase compositions and multiple order parameters to describe multi-component, multi-phase systems. The `KKSMultiFreeEnergy` AuxKernel, for instance, computes the total free energy in a "multi-phase KKS system". 

## Classes & Methods

*   `KKSPhaseChemicalPotential::validParams()`: Defines the valid input parameters for the `KKSPhaseChemicalPotential` kernel. 
*   `KKSPhaseChemicalPotential::KKSPhaseChemicalPotential()`: Constructor for the `KKSPhaseChemicalPotential` kernel, initializing member variables. 
*   `KKSMultiPhaseConcentration::validParams()`: Defines the valid input parameters for the `KKSMultiPhaseConcentration` kernel. 
*   `KKSMultiPhaseConcentration::KKSMultiPhaseConcentration()`: Constructor for the `KKSMultiPhaseConcentration` kernel. 
*   `KKSPhaseConcentrationMultiPhaseMaterial::validParams()`: Defines the valid input parameters for the `KKSPhaseConcentrationMultiPhaseMaterial`. 
*   `KKSPhaseConcentrationMultiPhaseMaterial::KKSPhaseConcentrationMultiPhaseMaterial()`: Constructor for the `KKSPhaseConcentrationMultiPhaseMaterial`. 
*   `KKSMultiFreeEnergy::validParams()`: Defines the valid input parameters for the `KKSMultiFreeEnergy` AuxKernel. 
*   `KKSMultiFreeEnergy::KKSMultiFreeEnergy()`: Constructor for the `KKSMultiFreeEnergy` AuxKernel. 

## Equations

### Total Free Energy Functional
$$
F = \sum_i h_i F_i + W \sum_i g_i + \sum_i \frac{\kappa_i}{2} |\nabla \eta_i|^2 \quad (1)
$$ 

### Equal Chemical Potential Constraint
$$
\frac{dF_a}{dc_a} = \frac{dF_b}{dc_b} \quad (2)
$$ 

### Phase Evolution Equation
$$
\frac{\partial \phi_i}{\partial t} = -L \left( \frac{\partial f}{\partial \phi_i} - \kappa \nabla^2 \phi_i + \lambda \right) \quad (3)
$$

### Concentration Conservation
$$
c = \sum_j h_j c_j \quad (4)
$$ 

## Parameters

*   `KKSPhaseChemicalPotential` parameters:
    *   `cb`: Coupled variable for phase b concentration. 
    *   `fa_name`: Base name of the free energy function for phase a. 
    *   `fb_name`: Base name of the free energy function for phase b. 
    *   `ka`: Site fraction for the $c_a$ variable (default: 1.0). 
    *   `kb`: Site fraction for the $c_b$ variable (default: 1.0). 
    *   `args_a`: Vector of further parameters to $F_a$. 
    *   `args_b`: Vector of further parameters to $F_b$. 
*   `KKSMultiPhaseConcentration` parameters:
    *   `cj`: Array of phase concentrations. 
    *   `c`: Physical concentration. 
    *   `etas`: Order parameters for all phases. 
    *   `hj_names`: Switching Function Materials that provide $h(\eta_1, \eta_2, \dots)$. 
*   `KKSPhaseConcentrationMultiPhaseMaterial` parameters:
    *   `global_cs`: The interpolated concentrations. 
    *   `all_etas`: Order parameters. 
    *   `hj_names`: Switching functions in the same order as `all_etas`. 
    *   `Fj_names`: Free energy material objects in the same order as `all_etas


## WBM implementation details and usage

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



## WBM thermodynamic coupling and CALPHAD integration

The WBM/KKS models in MOOSE connect to thermodynamic databases primarily through the `python/calphad/free_energy.py` script, which extracts free energy expressions from CALPHAD `.tdb` files and formats them for use with MOOSE's `DerivativeParsedMaterial` . This allows per-phase free energies to be directly incorporated into phase-field simulations. Temperature dependence and multi-component extensions like Redlich-Kister and sublattice models are handled by the CALPHAD data itself and then parsed into MOOSE's symbolic expression system .

## Connecting CALPHAD Data to MOOSE

### 1. Per-phase free energies from CALPHAD data and TDB file interface

MOOSE can utilize per-phase free energies derived from CALPHAD data . The primary interface for this is the `python/calphad/free_energy.py` script . This script uses the `pycalphad` Python module to parse `.tdb` thermodynamic database files . It then exports these free energy expressions as MOOSE `Material` blocks, specifically using the `DerivativeParsedMaterial` class .

**Algorithm Steps:**
` ` `pseudocode
1. User runs `free_energy.py` with a .tdb file and optional phase list.
2. `free_energy.py` opens the .tdb file using `pycalphad.Database`.
3. For each specified phase, a thermodynamic model is created using `pycalphad.Model`.
4. The free energy expression from the model is exported as a string using `fparser`.
5. MOOSE input file blocks are generated, defining a `DerivativeParsedMaterial` for each phase with the extracted function and its arguments.
` ` `


**MOOSE Input Syntax:**
The `free_energy.py` script generates output similar to this for each phase:
` ` `ini
  [./F_phase_name]
    type = DerivativeParsedMaterial
    function = 'CALPHAD_free_energy_expression'
    args = 'variable1 variable2 ...'
  [../]
` ` `


### 2. Parabolic approximation of CALPHAD data

The MOOSE documentation indicates that the `free_energy.py` tool directly exports CALPHAD functional expressions . This implies that MOOSE uses the full CALPHAD expressions rather than relying on parabolic approximations. The `DerivativeParsedMaterial` is designed to handle these complex functional forms and their derivatives symbolically .

### 3. `TabulatedFluidProperties` for tabulated thermodynamic data

While `TabulatedFluidProperties` exists in MOOSE for fluid simulations , it is part of the `fluid_properties` module and is designed for single-phase fluid properties based on pressure and temperature tables . It is not directly applicable to phase-field models for solid-state transformations where free energies are typically functions of order parameters and concentrations, and often derived from CALPHAD. The phase-field module uses `DerivativeParsedMaterial` for free energy expressions .

### 4. Temperature dependence in per-phase free energies

Temperature dependence is inherently included in the CALPHAD free energy expressions extracted by `free_energy.py` . When these expressions are parsed into `DerivativeParsedMaterial`, temperature can be included as one of the `args` (arguments) to the function .

### 5. Multi-component extensions (Redlich-Kister, sublattice models)

CALPHAD databases often incorporate multi-component extensions like Redlich-Kister and sublattice models . Since the `free_energy.py` script uses `pycalphad` to interpret the `.tdb` files , these complex models are handled by `pycalphad` during the extraction process. The resulting free energy expressions, which can be quite complex, are then passed to `DerivativeParsedMaterial` . `DerivativeParsedMaterial` is capable of handling arbitrary symbolic functions and their derivatives, making it suitable for these extensions .

### 6. Higher-order derivatives from CALPHAD and numerical stability

The `DerivativeParsedMaterial` class in MOOSE is designed to automatically compute derivatives of the free energy expressions . This symbolic differentiation capability helps in maintaining numerical stability by providing exact derivatives, rather than relying on numerical approximations that can introduce errors. The `KKSPhaseConcentrationMultiPhaseMaterial` uses nested Newton iterations to solve for phase concentrations, which requires derivatives of the free energies . The accuracy of these derivatives is crucial for the stability and convergence of the solver.

## Practical Approaches for Connecting Phase Field with Thermodynamic Data

### Classes & Methods:
*   `python/calphad/free_energy.py`: A Python script that extracts free energy expressions from `.tdb` files and generates MOOSE input blocks .
*   `DerivativeParsedMaterial`: A MOOSE material class that takes a symbolic function string and its arguments, and automatically computes its derivatives .
*   `KKSMultiFreeEnergy::validParams()`: Defines the input parameters for the `KKSMultiFreeEnergy` AuxKernel, including lists of free energy functions, switching functions, and barrier functions for each phase .
*   `KKSPhaseConcentrationMultiPhaseMaterial::validParams()`: Defines input parameters for the `KKSPhaseConcentrationMultiPhaseMaterial`, which computes KKS phase concentrations using a nested Newton iteration . It requires free energy material objects (`Fj_names`) and their derivatives .

### Relationships:
` ` `mermaid
classDiagram
    direction LR
    class "python/calphad/free_energy.py" as FreeEnergyScript
    class "pycalphad" as Pycalphad
    class "Database" as TDBDatabase
    class "Model" as PycalphadModel
    class "DerivativeParsedMaterial" as DerivativeParsedMaterial
    class "KKSMultiFreeEnergy" as KKSMultiFreeEnergy
    class "KKSPhaseConcentrationMultiPhaseMaterial" as KKSPhaseConcentrationMultiPhaseMaterial
    class "TotalFreeEnergyBase" as TotalFreeEnergyBase
    class "Material" as Material

    FreeEnergyScript --> Pycalphad : uses
    Pycalphad --> TDBDatabase : parses
    Pycalphad --> PycalphadModel : creates
    FreeEnergyScript --> DerivativeParsedMaterial : generates_input_for
    DerivativeParsedMaterial --|> Material : inherits
    KKSMultiFreeEnergy --|> TotalFreeEnergyBase : inherits
    KKSPhaseConcentrationMultiPhaseMaterial --|> Material : inherits
    KKSMultiFreeEnergy ..> DerivativeParsedMaterial : uses_Fj_names
    KKSPhaseConcentrationMultiPhaseMaterial ..> DerivativeParsedMaterial : uses_Fj_names
` ` `


## Notes
The `CALPHAD.md` documentation explicitly states that the `free_energy.py` script is a "work in progress" . This suggests that while the functionality exists, it may still be under active development or refinement. The `PFParamsPolyFreeEnergy` material  is mentioned as calculating properties for a single-component phase field model using polynomial free energies, which is a simpler approach compared to direct CALPHAD coupling and might be used for quantitative models as indicated in `modules/phase_field/doc/content/modules/phase_field/index.md` .

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
