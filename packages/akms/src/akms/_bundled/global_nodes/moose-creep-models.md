---
id: moose-creep-models
title: MOOSE Creep model implementations in MOOSE
domain: constitutive
subdomain: algorithmic
tags:
- power-law-creep
- hyperbolic-sine-creep
- activation-energy
- temperature-coupling
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-creep-viscoplasticity
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-creep-viscoplasticity
- to: cm-viscoplastic-thermo
  type: implements
  weight: 0.9
  note: Power law and sinh creep implementations
---

# MOOSE Creep model implementations in MOOSE

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

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
