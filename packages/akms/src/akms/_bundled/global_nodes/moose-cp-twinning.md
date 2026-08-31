---
id: moose-cp-twinning
title: MOOSE Crystal plasticity twinning and phase transformation
domain: constitutive
subdomain: algorithmic
tags:
- twinning
- phase-transformation
- TRIP
- volume-fraction
- reorientation
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-crystal-plasticity-advanced
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-crystal-plasticity-advanced
---

# MOOSE Crystal plasticity twinning and phase transformation

The MOOSE crystal plasticity module supports deformation twinning through the `CrystalPlasticityTwinningKalidindiUpdate` class, which implements a Kalidindi-based twinning propagation model for FCC and HCP materials   . This module tracks the volume fraction of twinned regions and can be coupled with dislocation slip models . However, it does not explicitly support stress-induced phase transformations (TRIP implementations) or reorientation of the crystal lattice due to twinning .

## Deformation Twinning

### Classes & Methods

*   `CrystalPlasticityTwinningKalidindiUpdate` : A material model that computes plastic shear increment due to twinning based on Kalidindi's model .
    *   `CrystalPlasticityTwinningKalidindiUpdate::validParams()`: Defines the input parameters for the twinning model .
    *   `CrystalPlasticityTwinningKalidindiUpdate::initQpStatefulProperties()`: Initializes stateful material properties, including twin volume fractions and slip resistance .
    *   `CrystalPlasticityTwinningKalidindiUpdate::calculateSlipRate()`: Computes the plastic shear increment due to twinning using a power law constitutive model .
    *   `CrystalPlasticityTwinningKalidindiUpdate::calculateStateVariableEvolutionRateComponent()`: Calculates the rate of twin volume fraction on each twin system .
    *   `CrystalPlasticityTwinningKalidindiUpdate::calculateTwinVolumeFraction()`: Updates the twin volume fraction for each system and the total twin volume fraction .
    *   `CrystalPlasticityTwinningKalidindiUpdate::calculateTwinResistance()`: Calculates the twin propagation resistance based on coplanar and non-coplanar hardening coefficients .

### Twin Systems: Definition

Twin systems are defined similarly to slip systems by providing a `slip_sys_file_name` parameter, which specifies the crystallographic orientations for twinning . The `CrystalPlasticityTwinningKalidindiUpdate` class uses these definitions to calculate resolved shear stresses and plastic shear increments .

### Volume Fraction Tracking for Twinned Regions

The module tracks the volume fraction of twinned regions on each twin system and the total twin volume fraction .
The total twin volume fraction is stored in the material property `_total_twin_volume_fraction` , and individual twin system volume fractions are stored in `_twin_volume_fraction` . An upper limit for the total twin volume fraction can be set using the `upper_limit_twin_volume_fraction` parameter .

### Reorientation of the Crystal Lattice Due to Twinning

The current implementation of `CrystalPlasticityTwinningKalidindiUpdate` does not explicitly support reorientation of the crystal lattice due to twinning . The model focuses on the propagation of twins and their contribution to plastic deformation and hardening .

### Transformation Plasticity (TRIP) Implementations

The MOOSE crystal plasticity module, specifically `CrystalPlasticityTwinningKalidindiUpdate`, does not include implementations for stress-induced phase transformations (TRIP) . Its scope is limited to deformation twinning and dislocation slip .

### Interaction Between Slip and Twin Systems — Latent Hardening Across Mechanisms

The interaction between slip and twin systems is handled by modifying the plastic velocity gradient calculation . When both twinning and dislocation slip models are included, the plastic velocity gradient ($L^P$) is calculated as a weighted sum of contributions from both mechanisms :

$$
L^P = \left(1 - {f_{total}}_{(n-1)} \right) \sum_{\alpha}^{slip} \dot{\gamma}^{\alpha} S^{\alpha}_o + \sum_{\beta}^{twin} \dot{f}^{\beta}\gamma_{tw}S^{\beta}_o \quad (1)
$$ 

Here, $f_{total}$ is the total twin volume fraction, $\dot{\gamma}^{\alpha}$ is the plastic shear rate due to dislocation slip, $S^{\alpha}_o$ is the Schmid tensor for slip systems, $\dot{f}^{\beta}$ is the rate of twin volume fraction, and $S^{\beta}_o$ is the Schmid tensor for twinning systems . The total twin volume fraction from the previous timestep, $f_{total(n-1)}$, is used to couple the models .

Latent hardening across mechanisms is implemented through the twin propagation resistance calculation, which considers different hardening coefficients for non-coplanar and coplanar twinning systems .

$$
\Delta g^{\beta} = \gamma_{tw} \left[ h_{nc}\left( f_{total} \right)^b \sum_{nc}^k \dot{f}^k + h_{cp}\left( f_{total} \right) \sum_{cp}^k \dot{f}^k \right] \quad (2)
$$ 

where $h_{nc}$ is the non-coplanar hardening coefficient, $b$ is the hardening exponent, and $h_{cp}$ is the coplanar hardening coefficient .

### Parameters

The `CrystalPlasticityTwinningKalidindiUpdate` class exposes several parameters for configuring the twinning model :

*   `initial_total_twin_volume_fraction = 0.0` (Real): Initial sum of twin volume fraction across all systems .
*   `twin_reference_strain_rate = 1.0e-3` (Real): Reference strain rate ($\gamma_o$) for the power law .
*   `twin_strain_rate_sensitivity_exponent = 0.05` (Real): Strain rate sensitivity exponent ($m$) .
*   `characteristic_twin_shear = 1.0 / std::sqrt(2.0)` (Real): Characteristic shear of the twin ($\gamma_{tw}$) .
*   `initial_twin_lattice_friction = 0.0` (Real): Initial lattice friction for twin propagation .
*   `non_coplanar_coefficient_twin_hardening = 8000.0` (Real): Hardening coefficient for non-coplanar twin systems ($h_{nc}$) .
*   `coplanar_coefficient_twin_hardening = 800.0` (Real): Hardening coefficient for coplanar twin systems ($h_{cp}$) .
*   `non_coplanar_twin_hardening_exponent = 0.05` (Real): Hardening exponent for non-coplanar twin systems ($b$) .
*   `upper_limit_twin_volume_fraction = 0.8` (Real): Maximum allowed total twin volume fraction ($f_{limit}$) .

### MOOSE Input Syntax

An example of how to configure the `CrystalPlasticityTwinningKalidindiUpdate` material model in a MOOSE input file is shown below :

` ` `ini
[Materials]
  [twin_only_xtalpl]
    type = CrystalPlasticityTwinningKalidindiUpdate
    number_slip_systems = 12
    slip_sys_file_name = 'fcc_input_twinning_systems.txt'
    initial_twin_lattice_friction = 1.5
    upper_limit_twin_volume_fraction = 1e-7
    stol = 0.01
    print_state_variable_convergence_error_messages = true
  []
[]
` ` ` 

To couple twinning with dislocation slip, the `total_twin_volume_fraction` property from the twinning model must be provided to the slip model :

` ` `ini
[Materials]
  [slip_xtalpl]
    type = CrystalPlasticityKalidindiUpdate
    number_slip_systems = 12
    slip_sys_file_name = input_slip_sys.txt
    total_twin_volume_fraction = 'twin_total_volume_fraction_twins'
  []
[]
` ` ` 

## Notes

The `CrystalPlasticityTwinningKalidindiUpdate` model is based on the Kalidindi (2001) constitutive model . It does not allow for de-twinning

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
