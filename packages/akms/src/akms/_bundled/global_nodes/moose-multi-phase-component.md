---
id: moose-multi-phase-component
title: MOOSE Multi-Phase Multi-Component Phase Field
domain: phase-field
subdomain: algorithmic
tags:
- multi-phase
- multi-component
- switching-function
- grain-tracker
- cahn-hilliard
- split-CH
- barrier-function
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
  weight: 0.8
  note: Multi-phase uses AC for non-conserved, CH for conserved
- to: cm-phase-field-fracture
  type: implements
  weight: 0.4
  note: Multi-phase infrastructure shared with phase field fracture models
---

# MOOSE Multi-Phase Multi-Component Phase Field

Framework knowledge node covering 2 aspect(s) of Multi-Phase Multi-Component Phase Field.

## Multi-phase field models in MOOSE

MOOSE handles multi-phase field problems by employing multiple order parameters, specialized interpolation functions, and various constraint enforcement mechanisms. It supports an arbitrary number of phases and grains through a flexible material and kernel system.

## 1. Multiple Order Parameters ($\eta_1, \eta_2, ..., \eta_n$)
MOOSE uses multiple order parameters, typically one per phase or per grain, to represent different phases or grains in a multi-phase system . For grain growth models, the evolution of each grain's order parameter is defined by the Allen-Cahn equation .

## 2. Interpolation Functions $h(\eta)$ and $g(\eta_1,...,\eta_n)$
MOOSE constructs multi-phase interpolation using switching functions, denoted as $h(\eta)$, and barrier functions, denoted as $g(\eta)$.

### Switching Functions $h(\eta)$
The `SwitchingFunctionMultiPhaseMaterial` class calculates a switching function for a given phase in a multi-phase, multi-order parameter system . The formulation for phase $\alpha$ is given by:
$$ h_\alpha = \frac{\sum_i \eta_{\alpha i}^2}{\sum_\rho \sum_i \eta_{\rho i}^2} $$
where $i$ indexes grains of a phase and $\rho$ indexes phases .

For three-phase systems, the `SwitchingFunction3PhaseMaterial` provides a specific switching function to prevent the formation of a third phase at a two-phase interface . The formula is:
$$ h_i = \frac{\eta_i^2}{4} [15 (1-\eta_i) [1 + \eta_i - (\eta_k - \eta_j)^2] + \eta_i (9\eta_i^2 - 5)] $$
This can also be constrained to the range $[0,1]$ .

### Barrier Functions $g(\eta_1,...,\eta_n)$
The `MultiBarrierFunctionMaterial` provides a double-well phase transformation barrier free energy contribution . A common form is:
$$ g(\vec\eta) = \sum_i \eta_i^2(1-\eta_i)^2 $$ . This material can be configured with different polynomial orders for the barrier function .

## 3. `SwitchingFunctionMaterial` - Available Switching Functions
MOOSE provides several switching functions:
*   `SwitchingFunctionMultiPhaseMaterial`: A general switching function for multi-phase, multi-order parameter systems, based on Moelans, Acta Mat., v 59, p.1077-1086 (2011) .
*   `SwitchingFunction3PhaseMaterial`: Specifically designed for three-phase systems to suppress the formation of a third phase at two-phase interfaces .
*   `MixedSwitchingFunctionMaterial`: Supports mixed switching functions with adjustable weights .

## 4. Multi-well Potentials: Barrier Function Extension to N Phases
The barrier function is extended to N phases through classes like `MultiBarrierFunctionMaterial` . This material takes a vector of order parameters (`etas`) and computes a barrier function, typically a sum of individual well functions for each order parameter  . The `g_order` parameter allows specifying the polynomial order of the switching function .

## 5. Constraint Enforcement: $\sum_i \eta_i = 1$
MOOSE enforces the constraint $\sum_i \eta_i = 1$ primarily through a Lagrange multiplier approach .

### Lagrange Multiplier
The `SwitchingFunctionConstraintLagrange` kernel is used to constrain the sum of all switching functions in a multiphase system . It acts on a Lagrange multiplier variable (`lambda`) . The residual for this kernel is calculated as:
$$ \mathcal{R} = \psi_m \left( \sum_{i=0}^{N-1} h_i - 1 - \epsilon \lambda \right) $$
where $h_i$ are the switching functions, $\lambda$ is the Lagrange multiplier, and $\epsilon$ is a shift factor to avoid a zero pivot .

### Penalty Method
A penalty-based constraint is also available for keeping the sum of all phase order parameters equal to one .

## 6. `GrainTracker` UserObject
The `GrainTracker` UserObject identifies and tracks individual grains . The provided context does not contain details on its internal mechanism for identification and tracking.

## 7. Phase-Specific Material Properties
MOOSE weights phase-specific material properties by phase fraction using switching functions. For instance, in the KKS multi-phase model, the global concentration `c` is a weighted sum of phase concentrations `c_i` using switching functions `h_i` :
$$ c = h_1(\eta_1,\eta_2,\eta_3,...) c_1 + h_2(\eta_1,\eta_2,\eta_3,...) c_2 + h_3(\eta_1,\eta_2,\eta_3,..) c_3 + ... $$ .

The `DerivativeMultiPhaseMaterial` combines an arbitrary number of phase free energies into a global free energy using switching functions . The derivative of the total free energy with respect to an order parameter $\eta_i$ involves the switching function and the phase-specific free energy .

## Classes & Methods

*   `SwitchingFunctionMultiPhaseMaterialTempl<is_ad>::validParams()`: Defines valid parameters for the multi-phase switching function material .
*   `SwitchingFunctionMultiPhaseMaterialTempl<is_ad>::SwitchingFunctionMultiPhaseMaterialTempl()`: Constructor for the multi-phase switching function material, initializing properties and derivatives .
*   `SwitchingFunction3PhaseMaterial::validParams()`: Defines valid parameters for the three-phase switching function material .
*   `SwitchingFunction3PhaseMaterial::SwitchingFunction3PhaseMaterial()`: Constructor for the three-phase switching function material, parsing the switching function expression .
*   `MultiBarrierFunctionMaterial::validParams()`: Defines valid parameters for the multi-barrier function material .
*   `MultiBarrierFunctionMaterial::MultiBarrierFunctionMaterial()`: Constructor for the multi-barrier function material, initializing properties and derivatives .
*   `MultiBarrierFunctionMaterial::computeQpProperties()`: Computes the barrier function value at quadrature points .
*   `SwitchingFunctionConstraintLagrange::validParams()`: Defines valid parameters for the Lagrange multiplier constraint kernel .
*   `SwitchingFunctionConstraintLagrange::computeQpResidual()`: Computes the residual for the Lagrange multiplier constraint .
*   `KKSMultiPhaseConcentration::validParams()`: Defines valid parameters for the KKS multi-phase concentration kernel .
*   `DerivativeMultiPhaseBase::validParams()`: Defines valid parameters for the base class for multi-phase derivative materials .
*   `DerivativeMultiPhaseMaterial::computeDF()`: Computes the first derivative of the total free energy with respect to a variable .

## Equations

### Switching Function for Multi-Phase Systems
For phase $\alpha$, the switching function is:
$$ h_\alpha = \frac{\sum_i \eta_{\alpha i}^2}{\sum_\rho \sum_i \eta_{\rho i}^2} $$
where $i$ indexes grains of a phase and $\rho$ indexes phases .

### Switching Function for Three-Phase Systems
The switching function for three phases is:
$$ h_i = \frac{\eta_i^2}{4} [15 (1-\eta_i) [1 + \eta_i - (\eta_k - \eta_j)^2] + \eta_i (9\eta_i^2 - 5)] $$ .

### Multi-Well Barrier Function
A common form for the multi-well barrier function is:
$$ g(\vec\eta) = \sum_i \eta_i^2(1-\eta_i)^2 $$ .

### KKS Multi-Phase Concentration
The global concentration $c$ is related to phase concentrations $c_i$ and switching functions $h_i$ by:
$$ c = h_1(\eta_1,\eta_2,\eta_3,...) c_1 + h_2(\eta_1,\eta_2,\eta_3,...) c_2 + h_3(\eta_1,\eta_2,\eta_3,..) c_3 + ... $$ .

### Allen-Cahn Equation for Grain Growth
The evolution of each grain's order parameter $\eta_i$ is defined by the Allen-Cahn equation:
$$ \frac{\partial \eta_i}{\partial t} = - L \frac{\delta F}{\delta \eta_i} $$
where $F$ is the free energy functional and $L$ is the order parameter mobility .

## Parameters

*   `SwitchingFunctionMultiPhaseMaterial`:
    *   `h_name`: Name of the switching function material property for the given phase (MaterialPropertyName, required) .
    *   `phase_etas`: Vector of order parameters for the given phase (CoupledVar, required) .
    *   `all_etas`: Vector of all order parameters for all phases (CoupledVar, required) .
*   `SwitchingFunction3PhaseMaterial`:
    *   `eta_i`: Order parameter i (CoupledVar, required) .
    *   `eta_j`: Order parameter j (CoupledVar, required)


## Multi-component (multi-species) phase field

ERROR: Request timed out after 120.0s

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
