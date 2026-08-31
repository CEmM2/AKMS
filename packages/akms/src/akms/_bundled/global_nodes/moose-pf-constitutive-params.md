---
id: moose-pf-constitutive-params
title: MOOSE Phase field parameters in constitutive models
domain: phase-field
subdomain: algorithmic
tags:
- composite-elasticity
- phase-dependent-moduli
- swelling-eigenstrain
- CTE-per-phase
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-phase-field-mechanics-coupling
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-phase-field-mechanics-coupling
---

# MOOSE Phase field parameters in constitutive models

MOOSE integrates phase field variables into solid mechanics constitutive models primarily through material classes that allow for phase-dependent material properties and stress calculations.

## Phase-dependent elastic moduli: $C(\eta) = h(\eta) \cdot C_{phase1} + (1-h(\eta)) \cdot C_{phase2}$

The `ComputeConcentrationDependentElasticityTensor` class is used to define an elasticity tensor that depends on a concentration field, which can represent a phase field variable . This class interpolates between two elasticity tensors, `_Cijkl0` and `_Cijkl1`, based on the value of a coupled concentration variable `_c` .

### Classes & Methods:
*   `ComputeConcentrationDependentElasticityTensor::validParams()`: Defines the input parameters for the concentration-dependent elasticity tensor, including two stiffness tensors (`C0_ijkl`, `C1_ijkl`) and a coupled concentration variable (`c`) .
*   `ComputeConcentrationDependentElasticityTensor::computeQpElasticityTensor()`: Computes the elasticity tensor at a given quadrature point using a linear interpolation formula .

### Equations:
The elasticity tensor $C$ is computed as:
$$
C = C_{ijkl0} + (C_{ijkl1} - C_{ijkl0}) \cdot c \quad (1)
$$ 
where $C_{ijkl0}$ is the stiffness tensor for zero concentration, $C_{ijkl1}$ is the stiffness tensor for concentration 1.0, and $c$ is the concentration variable .

## `CompositeElasticityTensor` — how does it interpolate tensors between phases?

The `CompositeElasticityTensor` class is used to combine multiple elasticity tensors with corresponding weights . While the provided snippets do not show its C++ implementation, an example input file demonstrates its usage where `tensors` are combined with `weights` . This allows for interpolation of elasticity tensors based on material properties that can be derived from phase field variables.

## Creep/plasticity parameters that depend on phase

MOOSE supports phase-dependent creep and plasticity parameters. The test suite for `CompositePowerLawCreepStressUpdate` indicates that the system provides phase-dependent power law creep that can handle different material properties for different phases . This includes scenarios with multiple plasticity rules for different phases . The input parameters for such creep models, like activation energy, coefficient, and n-exponent, are expected to have lengths equal to the number of switching functions (phases) .

## Swelling eigenstrains: coupling species concentration c to volumetric strain

The `ElasticEnergyMaterial` class is designed to handle elastic energy contributions and can fetch stress and elasticity tensor derivatives with respect to coupled variables . This framework allows for coupling species concentration `c` to volumetric strain by defining the elastic strain and elasticity tensor as functions of `c` and their derivatives.

## Thermal expansion differences between phases: phase-dependent CTE

While not explicitly shown in the provided snippets, the general approach for phase-dependent material properties in MOOSE, as demonstrated with elasticity tensors and creep parameters, would extend to thermal expansion coefficients. A material class similar to `ComputeConcentrationDependentElasticityTensor` could be implemented to interpolate CTE values based on a phase field variable.

## How to ensure thermodynamic consistency when mixing phase field and mechanics?

Thermodynamic consistency in coupled phase field and mechanics problems is ensured by defining a global free energy functional that includes contributions from both the local free energy density ($f_{loc}$), gradient energy density ($f_{gr}$), and additional energy sources like deformation energy ($E_d$) . The evolution equations for phase field variables (conserved and non-conserved) are derived from the functional derivatives of this global free energy .

For two-phase models, the `DerivativeTwoPhaseMaterial` combines phase free energies into a global free energy using a switching function $h(\eta)$ .
$$
F = (1-h(\eta)) F_a + h(\eta)F_b + Wg(\eta) \quad (2)
$$ 
where $F_a$ and $F_b$ are the free energies of phase A and B, respectively, and $\eta$ is the order parameter. The `TwoPhaseStressMaterial` and `MultiPhaseStressMaterial` classes calculate global stress and its derivative with respect to strain by interpolating between phase-specific stresses and stiffnesses using a switching function `_h_eta` . This approach ensures that the mechanical response is consistent with the phase distribution.

### Classes & Methods:
*   `TwoPhaseStressMaterial::computeQpProperties()`: Computes the global stress and its Jacobian by linearly interpolating between the stresses and Jacobians of two phases using a switching function `_h_eta` .
*   `ElasticEnergyMaterial`: A free energy material for elastic energy contributions, which can be coupled with other variables like concentration .

### MOOSE Input Syntax:
For phase-dependent elastic moduli using `ComputeConcentrationDependentElasticityTensor`:
` ` `ini
[Materials]
  [./elasticity_tensor]
    type = ComputeConcentrationDependentElasticityTensor
    block = '1'
    C0_ijkl = '...' # Stiffness tensor for zero concentration phase
    C1_ijkl = '...' # Stiffness tensor for concentration 1.0 phase
    c = concentration_variable # Coupled concentration variable
  [../]
[]
` ` ` 

For combining stresses from multiple phases using `TwoPhaseStressMaterial`:
` ` `ini
[Materials]
  [./phase_A_stress]
    type = SomeElasticStressMaterial
    block = '1'
    # ... parameters for phase A stress
  [../]
  [./phase_B_stress]
    type = SomeElasticStressMaterial
    block = '1'
    # ... parameters for phase B stress
  [../]
  [./switching_function]
    type = SwitchingFunctionMaterial
    block = '1'
    # ... parameters for h(eta)
  [../]
  [./global_stress]
    type = TwoPhaseStressMaterial
    block = '1'
    h = switching_function # Material property providing h(eta)
    base_A = phase_A_stress # Base name for Phase A strain/stress
    base_B = phase_B_stress # Base name for Phase B strain/stress
  [../]
[]
` ` ` 

## Notes
The provided context primarily focuses on elastic properties and general free energy formulations. Specific implementations for phase-dependent thermal expansion coefficients (CTE) were not directly found, but the framework suggests that similar material classes could be developed. The `ComputePolycrystalElasticityTensor` class also deals with evolving elasticity tensors coupled to grain growth phase field models, which is a related concept but not directly addressing the user's specific question about $C(\eta) = h(\eta) \cdot C_{phase1} + (1-h(\eta)) \cdot C_{phase2}$ .

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
