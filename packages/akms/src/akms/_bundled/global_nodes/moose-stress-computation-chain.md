---
id: moose-stress-computation-chain
title: MOOSE Constitutive Framework — Stress Update Architecture
domain: constitutive
subdomain: algorithmic
tags:
- stress-update
- compute-stress-base
- inelastic-stress
- material-property
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: medium
reading_priority: full
akms_schema: v2
edges:
- to: cm-tensor-calculus
  type: implements
  weight: 0.7
  note: Implements stress tensor computation via MOOSE MaterialProperty system
---

# MOOSE Constitutive Framework — Stress Update Architecture

Framework knowledge node covering 2 aspect(s) of Constitutive Framework — Stress Update Architecture.

## Stress computation dispatch chain

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


## Elastic stiffness tensor computation

# Answer

You're asking about how MOOSE computes and stores elasticity tensors, specifically covering the `ComputeElasticityTensor` class hierarchy, the `RankFourTensor` data structure, tensor rotation for crystal orientations, and how tensors flow to stress computation.

## Classes & Methods



**Base Class Hierarchy:**
- `ComputeElasticityTensorBaseTempl<is_ad, T>` — abstract base for all elasticity tensor computations; declares `_elasticity_tensor` MaterialProperty and pure virtual `computeQpElasticityTensor()`
- `ComputeRotatedElasticityTensorBaseTempl<is_ad>` — intermediate class that adds Euler angle and rotation matrix support
- `ComputeElasticityTensorTempl<is_ad>` — concrete implementation for general anisotropic tensors with symmetry fill methods

**Key Methods:**
- `ComputeElasticityTensorBaseTempl::computeQpProperties()` — orchestrates tensor computation and applies optional prefactor function 
- `ComputeElasticityTensorTempl::computeQpElasticityTensor()` — assigns `_Cijkl` to `_elasticity_tensor[_qp]` 
- `RankFourTensor::rotate(RealTensorValue)` — rotates tensor using $C'_{ijkl} = R_{im} R_{jn} R_{ko} R_{lp} C_{mnop}$ 

## Symmetry Class Handling



Symmetry is handled via the `fill_method` parameter passed to `RankFourTensor` constructor:

- **Isotropic** (`symmetric_isotropic`, `symmetric_isotropic_E_nu`): Detected via `_Cijkl.isIsotropic()` and guaranteed as `ISOTROPIC` 
- **Orthotropic/Cubic** (`symmetric9`): 9 independent components; used for cubic crystals and orthotropic materials
- **General Anisotropic** (`symmetric21`): 21 independent components with full symmetries $C_{ijkl} = C_{jikl} = C_{ijlk} = C_{klij}$ 
- **Transverse Isotropic** (`axisymmetric_rz`): 5 independent components
- **No Symmetry** (`general`): All 81 components

The fill method is specified in the input file and determines how the input vector is mapped to the full 3×3×3×3 tensor.

## RankFourTensor Data Structure

The codebase context does not contain the `RankFourTensor` header or implementation details.  I cannot describe the internal storage layout (e.g., whether it uses a flat array, nested vectors, or sparse representation) or the access patterns without seeing the class definition. To answer this part fully, I would need access to `modules/solid_mechanics/include/materials/RankFourTensor.h` and its implementation.

What I can confirm is that `RankFourTensor` is instantiated with a vector of Real values and a `FillMethod` enum: 

` ` `cpp
_Cijkl(this->template getParam<std::vector<Real>>("C_ijkl"),
       (RankFourTensor::FillMethod)(int)this->template getParam<MooseEnum>("fill_method"))
` ` `

## Rotation of Elasticity Tensor



**For static rotations** (initial setup only):
- `ComputeElasticityTensor` rotates the tensor once during construction
- If `rotation_matrix` parameter is provided, it applies directly: `_Cijkl.rotate(_rotation_matrix)`
- Otherwise, it builds a `RotationTensor` from Euler angles (Bunge convention, $Z_1 X_2 Z_3$ extrinsic) and applies: `_Cijkl.rotate(R)`

**For dynamic rotations** (crystal plasticity):
- `ComputeElasticityTensorCP` overrides `computeQpElasticityTensor()` to rotate at every timestep 
- It uses active rotation (transpose of passive Bunge angles) and updates the rotation matrix from coupled Euler angle variables or a property file
- The rotation is applied as: `_elasticity_tensor[_qp].rotate(_crysrot[_qp])`

**Rotation Equation:**
$$C'_{ijkl} = R_{im} R_{jn} R_{ko} R_{lp} C_{mnop} \quad (1)$$

where $R$ is the rotation matrix (passive convention in `ComputeElasticityTensor`, active in `ComputeElasticityTensorCP`).

## MaterialProperty Data Flow



The elasticity tensor is declared as a `GenericMaterialProperty<T, is_ad>` reference:

` ` `cpp
GenericMaterialProperty<T, is_ad> & _elasticity_tensor;
` ` `

where `T` is either `RankFourTensor` or `SymmetricRankFourTensor`. The property name is stored in `_elasticity_tensor_name` (default: `"elasticity_tensor"` or `"{base_name}_elasticity_tensor"` if a base name is provided).

**Flow to stress computation:**
1. `ComputeElasticityTensorBase::computeQpProperties()` calls `computeQpElasticityTensor()` 
2. Derived classes populate `_elasticity_tensor[_qp]` with the computed tensor
3. Stress materials (e.g., `ComputeLinearElasticStress`) retrieve the property via `getMaterialProperty<RankFourTensor>("elasticity_tensor")` and use it to compute $\sigma_{ij} = C_{ijkl} \epsilon_{kl}$

## Parameters



` ` `ini
C_ijkl = <vector<Real>>          # Required: stiffness tensor components
fill_method = symmetric9         # Optional: symmetry class (default: symmetric9)
                                 # Options: symmetric21, symmetric9, orthotropic, 
                                 #          symmetric_isotropic, axisymmetric_rz, etc.
euler_angle_1 = 0.0              # Optional: first Euler angle (degrees)
euler_angle_2 = 0.0              # Optional: second Euler angle (degrees)
euler_angle_3 = 0.0              # Optional: third Euler angle (degrees)
rotation_matrix = <RealTensorValue>  # Optional: 3×3 rotation matrix (overrides Euler angles)
elasticity_tensor_prefactor = <FunctionName>  # Optional: scalar multiplier function
base_name = ""                   # Optional: prefix for material property names
` ` `

## Relationships

` ` `mermaid
graph TD
    A["ComputeElasticityTensorBase<br/>(abstract base)"]
    B["ComputeRotatedElasticityTensorBase<br/>(adds Euler angles)"]
    C["ComputeElasticityTensor<br/>(general anisotropic)"]
    D["ComputeIsotropicElasticityTensor<br/>(isotropic only)"]
    E["ComputeElasticityTensorCP<br/>(crystal plasticity)"]
    F["RankFourTensor<br/>(data structure)"]
    G["RotationTensor<br/>(rotation matrix)"]
    H["StressCompute<br/>(uses elasticity tensor)"]
    
    A -->|declares| F
    B -->|extends| A
    B -->|uses| G
    C -->|extends| B
    C -->|instantiates| F
    D -->|extends| A
    E -->|extends| C
    E -->|rotates at each step| F
    F -->|passed via MaterialProperty| H
` ` `

## Code Snippets

**Constructor with symmetry handling:**


**Tensor assignment to MaterialProperty:**


**Crystal plasticity dynamic rotation:**


## MOOSE Input Syntax

` ` `ini
[Materials]
  [elasticity_tensor]
    type = ComputeElasticityTensor
    C_ijkl = '1.0 0.5 0.5 1.0 0.5 1.0 0.25 0.25 0.25'
    fill_method = symmetric9
    euler_angle_1 = 0.0
    euler_angle_2 = 0.0
    euler_angle_3 = 0.0
    base_name = material1
  []
[]
` ` `

For isotropic materials:
` ` `ini
[Materials]
  [elasticity_tensor]
    type = ComputeIsotropicElasticityTensor
    youngs_modulus = 210e9
    poissons_ratio = 0.3
  []
[]
` ` `

For crystal plasticity with dynamic rotation:
` ` `ini
[Materials]
  [elasticity_tensor]
    type = ComputeElasticityTensorCP
    C_ijkl = '1.0 0.5 0.5 1.0 0.5 1.0 0.25 0.25 0.25'
    fill_method = symmetric9
    euler_angle_variables = 'euler_1 euler_2 euler_3'
  []
[]
` ` `

## Notes

The codebase context does not include the `RankFourTensor` class definition, so I cannot provide details on its internal storage layout or element access patterns. The documentation references engineering notation (6×6 matrix) and Einstein index notation (4-index), but the actual 3×3×3×3 storage mechanism is not visible in the provided snippets.

`ComputeElasticityTensorCP` differs from `ComputeElasticityTensor` in two key ways: (1) it uses **active** rotation (transpose of Bunge angles) rather than passive, and (2) it rotates the tensor at every material timestep, not just during initialization. This is critical for crystal plasticity simulations where the crystal frame evolves with plastic deformation.

The `_elasticity_tensor` MaterialProperty is templated on `is_ad` (automatic differentiation flag), allowing both regular and AD-enabled stress computations to use the same material class.

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
