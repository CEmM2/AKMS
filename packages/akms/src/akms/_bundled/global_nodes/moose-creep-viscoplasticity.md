---
id: moose-creep-viscoplasticity
title: MOOSE Creep and Viscoplasticity Models
domain: constitutive
subdomain: algorithmic
tags:
- creep
- viscoplasticity
- power-law
- hyperbolic-sine
- temperature-coupling
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: medium
reading_priority: full
akms_schema: v2
edges:
- to: moose-stress-computation-chain
  type: requires
  weight: 0.7
  note: Part of the stress computation dispatch chain
- to: moose-return-mapping-base
  type: requires
  weight: 0.9
  note: Creep models use return mapping solver
- to: cm-viscoplastic-thermo
  type: implements
  weight: 0.9
  note: Implements power law creep and viscoplastic flow rules
---

# MOOSE Creep and Viscoplasticity Models

Framework knowledge node covering 2 aspect(s) of Creep and Viscoplasticity Models.

## Creep model implementations in MOOSE

This response addresses MOOSE's creep model implementations, specifically `PowerLawCreepStressUpdate` and `HyperbolicSinCreepStressUpdate`, focusing on their constitutive equations, parameter handling, residual and derivative computations for return mapping, time integration, temperature coupling, and how multiple creep mechanisms are combined.

## 1. `PowerLawCreepStressUpdate`

### Creep Rate Equation
The `PowerLawCreepStressUpdate` class implements a power law creep model. The creep rate equation is given by:
$$
\dot{\epsilon} = \left( \sigma^{trial}_{effective} - 3 G \Delta p \right)^n \exp \left( \frac{-Q}{RT} \right) \left(t - t_o \right)^m \quad (1)
$$ 
Here, $\sigma^{trial}_{effective}$ is the scalar von Mises trial stress, $G$ is the isotropic shear modulus, $Q$ is the activation energy, $R$ is the universal gas constant, $T$ is the temperature, $t$ and $t_o$ are the current and initial times, respectively, and $n$ and $m$ are exponent values. 

### Parameter Handling
The activation energy, stress exponent, and prefactor are handled as follows:
*   **Activation Energy (`Q`)**: This is provided via the `activation_energy` parameter.  It is used in the exponential term $\exp \left( \frac{-Q}{RT} \right)$. 
*   **Stress Exponent (`n`)**: This is specified by the `n_exponent` parameter.  It is the exponent on the effective stress term $(\sigma^{trial}_{effective} - 3 G \Delta p)$. 
*   **Prefactor**: The leading coefficient in the power-law equation is given by the `coefficient` parameter.  Additionally, there is an exponent on time, `m_exponent`, which acts as part of the prefactor, $(t - t_o)^m$. 

### Parameters

` ` `ini
[./creep]
  type = ADPowerLawCreepStressUpdate
  activation_energy = 4e4
  temperature = 1200
  coefficient = 1e-18
  gas_constant = 1.987
  n_exponent = 3
  base_name = 'creep'
  outputs = all
[../]
` ` `

## 2. `HyperbolicSinCreepStressUpdate`

The provided codebase context does not contain information about `HyperbolicSinCreepStressUpdate`. Therefore, I cannot describe its sinh law formulation and parameters. 

## 3. `computeResidual()` and `computeDerivative()` for Return Mapping

These models compute `computeResidual()` and `computeDerivative()` as part of an implicit integration algorithm for radial return stress updates.  The `PowerLawCreepStressUpdate` class inherits from `RadialReturnCreepStressUpdateBaseTempl` and defines these methods. 

### `PowerLawCreepStressUpdate::computeResidual()`
This method calculates the residual for the implicit integration.  The residual equation typically involves the difference between the calculated creep strain increment and the inelastic strain multiplier (`scalar`). 

### `PowerLawCreepStressUpdate::computeDerivative()`
This method computes the derivative of the residual with respect to the inelastic strain multiplier, which is crucial for the Newton-Raphson iteration in the return mapping algorithm. 

## 4. Time Integration: How Δt enters the Residual Equation

The time step $\Delta t$ enters the residual equation by multiplying the creep rate to obtain the creep strain increment.  For instance, in the `HillCreepStressUpdate` (which is an anisotropic extension of Power Law Creep), the residual is formed as `creep_rate * _dt - delta_gamma`.  This `_dt` member variable represents the current time step. 

## 5. Temperature Coupling: How the Creep Model Gets Temperature

The creep models obtain temperature from a thermal solve by coupling a temperature variable.  The `_temperature` member in `PowerLawCreepStressUpdateTempl` is a `GenericVariableValue` that holds the temperature value.  This temperature is then used to calculate the exponential term in the creep rate equation. 

### Parameters

` ` `ini
temperature = temp
` ` `
The `temperature` parameter is used to specify the coupled temperature variable. 

## 6. Multiple Creep Mechanisms

MOOSE combines parallel creep mechanisms using classes like `ComputeMultipleInelasticStress` or `ComputeCreepPlasticityStress`. 

### `ComputeCreepPlasticityStress`
This class is designed to combine one creep model and one plasticity model.  It forms a system of residual equations for both creep and plasticity and solves them simultaneously using a combined Newton iteration. 

The residual equations for combined creep and plasticity are:
$$
f_c = \dot{p}_c \Delta t - \Delta p_c = 0 \quad (2)
$$ 
$$
f_p = \sigma^{tr}_e - 3G(\Delta p_c + \Delta p_p)-r-\sigma_y=0 \quad (3)
$$ 
These are then solved using a Jacobian matrix containing partial derivatives of $f_c$ and $f_p$ with respect to $\Delta p_c$ and $\Delta p_p$. 

### `ADMultiplePowerLawCreepStressUpdate`
For multiple power law creep expressions, the `ADMultiplePowerLawCreepStressUpdate` class allows defining different sets of power law parameters (coefficient, n_exponent, m_exponent, activation_energy) for different von Mises stress intervals.  During the return mapping, the appropriate set of parameters is selected based on the effective trial stress. 

### Parameters

` ` `cpp
  /// Leading coefficient vector
  const std::vector<Real> _coefficient;

  /// Exponent on the effective stress vector
  const std::vector<Real> _n_exponent;

  /// Exponent on time vector
  const std::vector<Real> _m_exponent;

  /// Stress thresholds vector
  const std::vector<Real> _stress_thresholds;

  /// Activation energy for exp term vector
  const std::vector<Real> _activation_energy;
` ` `

## Classes & Methods

*   `PowerLawCreepStressUpdateTempl::computeResidual(const GenericReal<is_ad> & effective_trial_stress, const GenericReal<is_ad> & scalar)`: Computes the residual for the power law creep model. 
*   `PowerLawCreepStressUpdateTempl::computeDerivative(const GenericReal<is_ad> & effective_trial_stress, const GenericReal<is_ad> & scalar)`: Computes the derivative of the residual for the power law creep model. 
*   `HillCreepStressUpdateTempl::computeResidual(...)`: Computes the residual for the anisotropic Hill creep model, which is an extension of the power law creep. 
*   `HillCreepStressUpdateTempl::computeDerivative(...)`: Computes the derivative of the residual for the anisotropic Hill creep model. 
*   `ADMultiplePowerLawCreepStressUpdate::stressIndex(const ADReal & effective_trial_stress)`: Determines which set of power law parameters to use based on the effective trial stress. 
*   `ComputeCreepPlasticityStress::initialSetup()`: Initializes the creep and plasticity models and checks for compatibility. 
*   `ComputeCreepPlasticityStress::updateQpState(...)`: Orchestrates the computation of inelastic strain increments for combined creep and plasticity. 

## Relationships

` ` `mermaid
classDiagram
    class RadialReturnCreepStressUpdateBaseTempl {
        +computeResidual()
        +computeDerivative()
    }
    class PowerLawCreepStressUpdateTempl {
        +PowerLawCreepStressUpdateTempl()
        +computeResidual()
        +computeDerivative()
        -_temperature
        -_coefficient
        -_n_exponent
        -_m_exponent
        -_activation_energy
        -_gas_constant
        -_start_time
    }
    class ADMultiplePowerLawCreepStressUpdate {
        +ADMultiplePowerLawCreepStressUpdate()
        +computeResidual()
        +computeDerivative()
        +stressIndex()
        -_temperature
        -_coefficient[]
        -_n_exponent[]
        -_m_exponent[]
        -_stress_thresholds[]
        -_activation_energy[]
        -_gas_constant
        -_start_time
    }
    class ComputeMultipleInelasticStress {
        +addInelasticModel()
    }
    class ComputeCreepPlasticityStress {
        +ComputeCreepPlasticityStress()
        +initialSetup()
        +updateQpState()
        -_creep_model
        -_plasticity_model
    }

    RadialReturnCreepStressUpdateBaseTempl <|-- PowerLawCreepStressUpdateTempl : inherits
    ADRadialReturnCreepStressUpdateBase <|-- ADMultiplePowerLawCreepStressUpdate : inherits
    ComputeMultipleInelasticStress <|-- ComputeCreepPlasticityStress : inherits
    ComputeCreepPlasticityStress --> PowerLawCreepStressUpdateTempl : uses
    ComputeCreepPlasticityStress --> IsotropicPlasticityStressUpdate : uses
` ` `

## Notes

The codebase does not contain any explicit implementation or documentation for `HyperbolicSinCreepStressUpdate`. The closest related class found is `PowerLawCreepStressUpdate`, and its anisotropic extension `HillCreepStressUpdate`.  The discussion on multiple creep mechanisms primarily refers to combining different types of inelastic models (creep and plasticity) or using multiple power-law expressions based on stress thresholds.


## Viscoplastic flow rules and rate-dependent plasticity

MOOSE implements rate-dependent (viscoplastic) flow rules through several material classes, primarily `ADViscoplasticityStressUpdate`  and `HyperbolicViscoplasticityStressUpdate` , which are designed to work within the `ComputeMultipleInelasticStress` framework . These classes handle the iterative solution for inelastic strain increments.

## ADViscoplasticityStressUpdate and its Formulation

The `ADViscoplasticityStressUpdate` class  is a material model that calculates stress updates for viscoplastic materials using automatic differentiation. It inherits from `ADViscoplasticityStressUpdateBase`  and `ADSingleVariableReturnMappingSolution` . The core of its formulation involves solving for the inelastic strain increment through a return mapping algorithm.

### Perzyna-type and Norton-type Flow Rules

`ADViscoplasticityStressUpdate` supports different viscoplastic models, specified by the `_model` enum . Currently, it explicitly lists `LPS` (presumably a form of power-law creep) and `GTN` (Gurson-Tvergaard-Needleman) models . The `_power` parameter  and `_coefficient`  are used to define the power-law relationship.

A Norton-type power-law creep is exemplified in the `lps_dual.i` test case , where the `power` parameter is set to `3` and `1` respectively for two different models. The `coefficient` can be a constant or a material property, as shown in the example where `coef_3` is a temperature-dependent expression .

For Perzyna-type viscoplasticity, the `NEML2` framework provides `PerzynaPlasticFlowRate` . This class takes `reference_stress` and `exponent` as parameters .

### Overstress Functions: Yield Function Integration

The `ADViscoplasticityStressUpdate` class calculates a residual in `computeResidual`  which is driven to zero during the return mapping iterations. This residual implicitly incorporates the overstress concept, where viscoplastic flow occurs when the stress state exceeds a yield-like surface. The `effective_trial_stress` is a key input to this residual calculation .

In the `NEML2` framework, the yield function is explicitly defined by classes like `YieldFunction` . The `flow` model can then be composed of `overstress`, `vonmises`, and `yield` models . The `Normality` class  then uses this `flow` model to define the plastic flow direction.

For `HyperbolicViscoplasticityStressUpdate` , the constitutive equation for scalar plastic strain rate is given by:
$$\dot{p} = \phi (\sigma_e , r) = \alpha \sinh \beta (\sigma_e -r - \sigma_y)$$ 
Here, $\sigma_e$ is the effective stress, $r$ is a hardening variable, and $\sigma_y$ is the yield stress. The parameters `_c_alpha` and `_c_beta`  correspond to $\alpha$ and $\beta$ respectively. The `computeResidual` method  in this class is responsible for solving this equation.

## Interaction with ComputeMultipleInelasticStress Framework

The `ComputeMultipleInelasticStress` class  is designed to combine multiple inelastic stress calculations, such as creep and plasticity . It iterates over individual inelastic models, which are typically derived from `StressUpdateBase` , until the change in stress converges .

The `ADViscoplasticityStressUpdate`  and `HyperbolicViscoplasticityStressUpdate`  classes are examples of such inelastic models. They are configured as sub-materials within `ComputeMultipleInelasticStress` . The `updateQpState` method in `ComputeMultipleInelasticStress`  orchestrates the iterative solution, calling the `updateState` method of each inelastic model .

## Classes & Methods

*   `ADViscoplasticityStressUpdate::updateState()` : Updates the stress and inelastic strain increment for viscoplastic materials.
*   `ADViscoplasticityStressUpdate::computeResidual()` : Computes the residual for the return mapping iteration.
*   `HyperbolicViscoplasticityStressUpdate::computeResidual()` : Computes the residual for the hyperbolic sine viscoplasticity model.
*   `ComputeMultipleInelasticStress::updateQpState()` : Manages the iterative update of stress and inelastic strains for multiple inelastic models.
*   `HEVPFlowRatePowerLawJ2::computeValue()` : Calculates the flow rate based on a power-law relationship for hyperelastic viscoplasticity.

## Equations

### Hyperbolic Viscoplasticity Strain Rate
The constitutive equation for scalar plastic strain rate in `HyperbolicViscoplasticityStressUpdate` is: 
$$ \dot{p} = \alpha \sinh \beta (\sigma_e -r - \sigma_y) $$
where:
*   $\dot{p}$ is the scalar plastic strain rate.
*   $\alpha$ is the viscoplasticity coefficient (`_c_alpha`).
*   $\beta$ is the viscoplasticity coefficient inside the hyperbolic sine function (`_c_beta`).
*   $\sigma_e$ is the effective stress.
*   $r$ is the hardening variable.
*   $\sigma_y$ is the yield stress (`_yield_stress`).

### Power Law Flow Rate (HEVP)
The flow rate in `HEVPFlowRatePowerLawJ2` is calculated as: 
$$ \text{val} = \left(\frac{\text{eqv\_stress}}{\text{_strength[qp]}}\right)^{\text{_flow\_rate\_exponent}} \times \text{_ref\_flow\_rate} $$
where:
*   `eqv_stress` is the equivalent stress.
*   `_strength[qp]` is the material strength at the quadrature point.
*   `_flow_rate_exponent` is the power law exponent.
*   `_ref_flow_rate` is the reference flow rate.

## Parameters

*   `ADViscoplasticityStressUpdate` :
    *   `coefficient`: `ADMaterialProperty<Real>` (e.g., `coef_3 = '0.5e-18 * exp(-4e4 / 1.987 / temp)'`) 
    *   `power`: `Real` (e.g., `3`, `1`) 
    *   `base_name`: `String` (e.g., `'lps_1'`) 
*   `HyperbolicViscoplasticityStressUpdate` :
    *   `yield_stress`: `Real` (required) 
    *   `hardening_constant`: `Real` (required) 
    *   `c_alpha`: `Real` (required, viscoplasticity coefficient) 
    *   `c_beta`: `Real` (required, viscoplasticity coefficient) 
*   `PerzynaPlasticFlowRate` (NEML2) :
    *   `reference_stress`: `Real` (e.g., `100`) 
    *   `exponent`: `Real` (e.g., `2`) 
*   `HEVPFlowRatePowerLawJ2` :
    *   `reference_flow_rate`: `Real` (default `0.001`)

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
