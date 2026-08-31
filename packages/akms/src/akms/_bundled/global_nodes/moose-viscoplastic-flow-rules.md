---
id: moose-viscoplastic-flow-rules
title: MOOSE Viscoplastic flow rules and rate-dependent plasticity
domain: constitutive
subdomain: algorithmic
tags:
- viscoplasticity
- perzyna
- norton
- overstress
- rate-dependent
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
  weight: 0.8
  note: Perzyna/Norton viscoplastic flow rules
---

# MOOSE Viscoplastic flow rules and rate-dependent plasticity

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
