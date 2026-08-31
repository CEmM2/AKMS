---
id: moose-stress-dispatch-chain
title: MOOSE Stress computation dispatch chain
domain: constitutive
subdomain: algorithmic
tags:
- stress-update
- compute-stress-base
- compute-multiple-inelastic-stress
- material-property
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-stress-computation-chain
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-stress-computation-chain
- to: cm-tensor-calculus
  type: implements
  weight: 0.7
  note: Stress computation chain for tensor mechanics
---

# MOOSE Stress computation dispatch chain

The stress computation in MOOSE's Tensor Mechanics module, particularly for inelastic models, follows a hierarchical structure starting from `ComputeStressBase` and extending to specialized inelastic stress computation classes like `ComputeMultipleInelasticStress` and `ComputeCreepPlasticityStress`. Strain input is processed through a series of material properties, and stress output is produced iteratively, especially when multiple inelastic models are involved.

## 1. How `ComputeStressBase` receives strain input and produces stress output

`ComputeStressBase` is the foundational class for stress calculations in MOOSE's Solid Mechanics module . It inherits from `ComputeGeneralStressBase` , which defines the core material properties for stress computation.

**Input:**
`ComputeStressBase` (via `ComputeGeneralStressBase`) receives strain input through the `_mechanical_strain` material property . This property is obtained using `getMaterialPropertyByName<RankTwoTensor>(_base_name + "mechanical_strain")` in the constructor of `ComputeGeneralStressBase` .

**Output:**
The computed stress is stored in the `_stress` material property , which is declared as an output property using `declareProperty<RankTwoTensor>(_base_name + "stress")` . Additionally, `_elastic_strain`  and `_Jacobian_mult`  are also declared and computed. The actual stress computation is performed by the pure virtual function `computeQpStress()` , which must be implemented by derived classes.

## 2. Role of `ComputeFiniteStrainElasticStress` vs `ComputeMultipleInelasticStress`

These two classes represent different levels of complexity in stress calculation:

*   **`ComputeFiniteStrainElasticStress`**: This class computes stress based on elasticity theory for finite strains . It directly calculates stress from the elasticity tensor and strain increment, considering finite strain rotations . It does not handle inelastic material behavior directly.

*   **`ComputeMultipleInelasticStress`**: This class, which inherits from `ComputeMultipleInelasticStressBase` , is designed to handle multiple inelastic models (e.g., plasticity, creep) . It orchestrates an iterative process to determine the stress and decompose the strain into elastic and inelastic parts . It uses `StressUpdateBase` derived classes for individual inelastic models .

In essence, `ComputeFiniteStrainElasticStress` provides a basic elastic stress calculation, while `ComputeMultipleInelasticStress` builds upon this by incorporating and managing complex inelastic material responses through an iterative scheme.

## 3. How `ComputeMultipleInelasticStress` orchestrates multiple inelastic models

`ComputeMultipleInelasticStress` (and its base class `ComputeMultipleInelasticStressBase`) orchestrates multiple inelastic models using an iterative Picard scheme .

**Iteration/Composition Strategy:**

1.  **Initialization**: The `updateQpState` method is called, which initializes `inelastic_strain_increment` for each model to zero .
2.  **Iterative Loop**: The class enters a `do-while` loop that continues until the change in stress (`l2norm_delta_stress`) is within user-defined `_absolute_tolerance` and `_relative_tolerance`, or `_max_iterations` is reached .
3.  **Model-wise Stress Update**: Inside the loop, it iterates through each registered inelastic model (`_models`) .
    *   For each model, it sets the current quadrature point (`_qp`) .
    *   It assumes the strain is initially elastic and subtracts all previously calculated inelastic strain increments from other models .
    *   A trial stress is formed using the current elasticity tensor and the elastic strain increment .
    *   The `computeAdmissibleState` method is called for the current inelastic model. This method allows the individual model to produce an admissible stress, and decompose the strain increment into elastic and inelastic parts .
4.  **Convergence Check**: After all models have been processed in an iteration, the L2 norm of the change in stress (`l2norm_delta_stress`) is calculated and checked against the tolerances .
5.  **Combined Inelastic Strain**: Once convergence is achieved, the `combined_inelastic_strain_increment` is calculated as a weighted sum of the inelastic strain increments from all models .

A specialized class, `ComputeCreepPlasticityStress`, is designed to combine creep and plasticity models, solving for both simultaneously rather than in a staggered approach . It overrides `updateQpState` to implement its specific coupled iteration strategy .

## 4. Key MaterialProperty names exchanged

The following `MaterialProperty` names are crucial for stress computation:

*   `_mechanical_strain`: Represents the total mechanical strain applied to the material . It is an input to the stress calculation.
*   `_stress`: The computed stress tensor output by the material model .
*   `_elastic_strain`: The elastic portion of the total strain . In inelastic models, this is derived by subtracting inelastic strains from the mechanical strain.
*   `_elasticity_tensor`: Represents the material's elasticity tensor, which relates elastic strain to stress .
*   `_Jacobian_mult`: Represents the consistent tangent operator, which is the derivative of stress with respect to strain (`dstress_dstrain`) . This is critical for Jacobian computations in the finite element solver.

## 5. `computeQpStress()` call sequence

The `computeQpStress()` call sequence starts from the base class and proceeds through the inheritance hierarchy to a specific material model.

` ` `mermaid
graph TD
    A["ComputeGeneralStressBase::computeQpProperties()"] --> B["ComputeGeneralStressBase::computeQpStress() (virtual)"];
    B --> C["ComputeMultipleInelasticStressBase::computeQpStress()"];
    C --> D["ComputeMultipleInelasticStressBase::computeQpStressIntermediateConfiguration()"];
    D --> E["ComputeMultipleInelasticStressBase::updateQpState() (virtual)"];
    E --> F["ComputeMultipleInelasticStress::updateQpState()"];
    F --> G["ComputeMultipleInelasticStressBase::computeAdmissibleState()"];
    G --> H["StressUpdateBase::computeStressTensor() (virtual)"];
` ` `

1.  **`ComputeGeneralStressBase::computeQpProperties()`**: This is the entry point for computing material properties at a quadrature point. It calls the virtual `computeQpStress()` method .
2.  **`ComputeMultipleInelasticStressBase::computeQpStress()`**: This overridden method handles damage models and finite strain rotations . It calls `computeQpStressIntermediateConfiguration()` .
3.  **`ComputeMultipleInelasticStressBase::computeQpStressIntermediateConfiguration()`**: This method prepares for the stress update by initializing `elastic_strain_increment` and `combined_inelastic_strain_increment` . If there are no inelastic models, it performs a simple elastic stress calculation . Otherwise, it calls the virtual `updateQpState()` .
4.  **`ComputeMultipleInelasticStress::updateQpState()`**: This is where the iterative process for multiple inelastic models takes place . Within its loop, it calls `computeAdmissibleState()` for each inelastic model .
5.  **`ComputeMultipleInelasticStressBase::computeAdmissibleState()`**: This method, implemented in the base class, is responsible for calling the specific `StressUpdateBase` derived model's `computeStressTensor()` method .
6.  **`StressUpdateBase::computeStressTensor()`**: This is a virtual method in `StressUpdateBase` that each concrete inelastic model (e.g., `PowerLawCreepStressUpdate`, `IsotropicPlasticityStressUpdate`) must implement to perform its specific stress and inelastic strain calculations.

For example, in `ComputeCreepPlasticityStress`, the `updateQpState` method is overridden to handle the coupled creep and plasticity calculation . It calls its own `computeStress` method  and then iteratively computes inelastic strain increments and updates stress.

## Classes & Methods

*   `ComputeGeneralStressBase::computeQpProperties()`: The main method called by MOOSE to compute all material properties at a quadrature point. 
*   `ComputeGeneralStressBase::computeQpStress()`: A pure virtual method that derived classes must implement to calculate the stress tensor. 
*   `ComputeFiniteStrainElasticStress::computeQpStress()`: Computes stress based on elasticity theory for finite strains. 
*   `ComputeMultipleInelasticStressBase::computeQpStress()`: Overrides the base `computeQpStress` to handle damage and finite strain rotations, then calls `computeQpStressIntermediateConfiguration`. 
*   `ComputeMultipleInelasticStressBase::computeQpStressIntermediateConfiguration()`: Computes stress in an intermediate configuration, handling the case of zero inelastic models or calling `updateQpState` for inelastic models. 
*   `ComputeMultipleInelasticStressBase::updateQpState()`: A pure virtual method for iteratively finding an admissible stress and inelastic strains when multiple inelastic models are present. 
*   `ComputeMultipleInelasticStress::updateQpState()`: Implements the iterative Picard scheme for combining multiple inelastic models.

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
