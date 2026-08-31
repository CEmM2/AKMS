---
id: moose-elasticity-tensor
title: MOOSE Elastic stiffness tensor computation
domain: constitutive
subdomain: algorithmic
tags:
- elasticity-tensor
- rank-four-tensor
- symmetry
- rotation
- isotropic
- anisotropic
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
  weight: 0.8
  note: RankFourTensor for elasticity with symmetry classes
---

# MOOSE Elastic stiffness tensor computation

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
