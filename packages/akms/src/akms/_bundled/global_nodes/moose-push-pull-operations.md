---
id: moose-push-pull-operations
title: MOOSE Push-forward and pull-back tensor operations
domain: constitutive
subdomain: algorithmic
tags:
- push-forward
- pull-back
- rank-two-tensor
- rank-four-tensor
- piola-transform
- nanson
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-objectivity-frame-operations
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-objectivity-frame-operations
- to: cm-tensor-calculus
  type: implements
  weight: 0.8
  note: Tensor push-forward/pull-back operations
---

# MOOSE Push-forward and pull-back tensor operations

MOOSE implements push-forward and pull-back operations for tensor quantities, particularly stress and elasticity tensors, within its solid mechanics module for finite deformation analysis. These operations are primarily handled by specialized material classes that manage the transformation between different stress measures (Cauchy, 1st PK, 2nd PK) and their corresponding Jacobians. The `RankTwoTensor` and `RankFourTensor` classes provide fundamental tensor operations, but explicit `pushForward()` or `pullBack()` methods are not directly exposed at that level for general use; instead, these transformations are embedded within the material constitutive models.

## Classes & Methods

*   `ComputeLagrangianStressCauchy::computeQpPK1Stress()`: Computes the 1st Piola-Kirchhoff stress from Cauchy stress and its Jacobian. 
*   `ComputeLagrangianStressPK1::computeQpCauchyStress()`: Computes the Cauchy stress from 1st Piola-Kirchhoff stress and its Jacobian. 
*   `ComputeLagrangianStressPK2::computeQpPK1Stress()`: Computes the 1st Piola-Kirchhoff stress from 2nd Piola-Kirchhoff stress and its Jacobian. 
*   `ComputeDeformGradBasedStress::computeQpStress()`: Computes Cauchy stress from 2nd PK stress using the deformation gradient. 
*   `ComputeHypoelasticStVenantKirchhoffStress::computeQpSmallStress()`: Performs push-forward of the elasticity tensor for large kinematics. 
*   `ComputeLagrangianObjectiveStress::objectiveUpdateTruesdell()`: Implements the Truesdell objective update for Cauchy stress and its Jacobian. 
*   `ComputeLagrangianObjectiveStress::polarDecomposition()`: Computes polar decomposition of the deformation gradient to get rotation and stretch tensors, and their derivatives. 
*   `CZMComputeGlobalTractionTotalLagrangian::computeEquilibriumTracionAndDerivatives()`: Computes the 1st Piola-Kirchhoff traction and its derivatives, including the area ratio. 

## Equations

### 1. Pull-back of Cauchy stress to 2nd PK
The pull-back of Cauchy stress ($\sigma$) to 2nd Piola-Kirchhoff stress ($S$) is implicitly handled by the inverse transformation of the push-forward operation. While not directly expressed as $S = J \cdot F^{-1} \cdot \sigma \cdot F^{-T}$, the MOOSE framework typically computes stresses in a specific configuration and then transforms them as needed. For instance, `ComputeLagrangianStressPK2` is designed to provide the 2nd PK stress and its tangent, and then wraps this to provide the 1st PK stress. 

### 2. Push-forward of 2nd PK to Cauchy
The push-forward of 2nd Piola-Kirchhoff stress ($S$) to Cauchy stress ($\sigma$) is computed in `ComputeDeformGradBasedStress::computeQpStress()`  and `ComputeLagrangianStressPK1::computeQpCauchyStress()` .

$$
\sigma = \frac{1}{J} \cdot F \cdot S \cdot F^T \quad (1)
$$ 

### 4. Elasticity tensor transformation
The 4th-order push-forward of the elasticity tensor from the reference to the current configuration is implemented in `ComputeHypoelasticStVenantKirchhoffStress::computeQpSmallStress()` .

$$
C_{spatial} = \frac{1}{J} \cdot F_{i\alpha} F_{j\beta} F_{k\gamma} F_{l\delta} \cdot C_{ref_{\alpha\beta\gamma\delta}} \quad (2)
$$
This is represented in code as:
` ` `cpp
  const RankTwoTensor F = _def_grad[_qp];
  const Real J = F.det();
  const RankFourTensor FF = F.times<i, k, j, l>(F);
  const RankFourTensor FtFt = F.times<k, i, l, j>(F);
  const RankFourTensor C0 = _elasticity_tensor[_qp];
  const RankFourTensor C = FF * C0 * FtFt / J;
` ` ` 

### 6. Piola transform for traction (Nanson's formula)
Nanson's formula is explicitly used in `CZMComputeGlobalTractionTotalLagrangian::computeEquilibriumTracionAndDerivatives()` to compute the area ratio for the 1st Piola-Kirchhoff traction. 
The area ratio is calculated as:
$$
\frac{da}{dA} = J \cdot ||F^T N|| \quad (3)
$$ 
This is implemented using `CohesiveZoneModelTools::computeAreaRatio` . The 1st Piola-Kirchhoff traction is then computed as $T = \frac{da}{dA} Q \hat{t}$ , where $Q$ is the total rotation and $\hat{t}$ is the interface traction. 

## Algorithm Steps

### Push-forward of 2nd PK to Cauchy Stress
` ` `pseudocode
function computeQpStress()
  iden = RankTwoTensor::Identity()
  ee = 0.5 * (_deformation_gradient.transpose() * _deformation_gradient - iden)
  pk2 = _elasticity_tensor * ee
  _stress = _deformation_gradient * pk2 * _deformation_gradient.transpose() / _deformation_gradient.det()
  _Jacobian_mult = _elasticity_tensor
end function
` ` ` 

## Relationships

` ` `mermaid
classDiagram
    class Material {
        +initQpStatefulProperties()
        +computeQpProperties()
    }
    class ComputeLagrangianStressBase {
        +computeQpStressUpdate()
        #_large_kinematics
        #_cauchy_stress
        #_cauchy_jacobian
        #_pk1_stress
        #_pk1_jacobian
    }
    class ComputeLagrangianStressCauchy {
        +computeQpCauchyStress()
        -computeQpPK1Stress()
        #_inv_df
        #_inv_def_grad
        #_F
    }
    class ComputeLagrangianStressPK1 {
        +computeQpPK1Stress()
        -computeQpCauchyStress()
        #_inv_df
        #_F
    }
    class ComputeLagrangianStressPK2 {
        +computeQpPK2Stress()
        #_E
        #_S
        #_C
    }
    class ComputeLagrangianObjectiveStress {
        +computeQpSmallStress()
        -objectiveUpdateTruesdell()
        -objectiveUpdateJaumann()
        -objectiveUpdateGreenNaghdi()
        -advectStress()
        -updateTensor()
        -stressAdvectionDerivative()
        -cauchyJacobian()
        -polarDecomposition()
        #_small_stress
        #_small_jacobian
        #_def_grad
        #_rotation
        #_stretch
    }
    class ComputeHypoelasticStVenantKirchhoffStress {
        +computeQpSmallStress()
        #_elasticity_tensor
        #_def_grad
    }
    class ComputeDeformGradBasedStress {
        +computeQpStress()
        #_deformation_gradient
        #_elasticity_tensor
        #_stress
        #_Jacobian_mult
    }
    class CZMComputeGlobalTractionTotalLagrangian {
        +computeEquilibriumTracionAndDerivatives()
        #_F
        #_J
        #_F_inv
        #_area_ratio
        #_PK1traction
        #_dPK1traction_dF
    }

    Material <|-- ComputeLagrangianStressBase
    ComputeLagrangianStressBase <|-- ComputeLagrangianStressCauchy
    ComputeLagrangianStressBase <|-- ComputeLagrangianStressPK1
    ComputeLagrangianStressPK1 <|-- ComputeLagrangianStressPK2
    ComputeLagrangianStressCauchy <|-- ComputeLagrangianObjectiveStress
    ComputeLagrangianObjectiveStress <|-- ComputeHypoelasticStVenantKirchhoffStress
    Material <|-- ComputeDeformGradBasedStress
    CZMComputeGlobalTractionBase <|-- CZMComputeGlobalTractionTotalLagrangian
` ` `

## Code Snippets

### 1. Pull-back of Cauchy stress to 2nd PK
The direct pull-back of Cauchy stress to 2nd PK is not explicitly shown as a single method. Instead, the framework often computes stresses in one form and then transforms them. For example, `ComputeLagrangianStressPK2` provides the 2nd PK stress and then derives the 1st PK stress from it. 

### 2. Push-forward of 2nd PK to Cauchy
The push-forward of 2nd PK stress to Cauchy stress is performed in `ComputeDeformGradBasedStress::computeQpStress()`:
` ` `cpp
  _stress[_qp] = _deformation_gradient[_qp] * pk2 * _deformation_gradient[_qp].transpose() /
                 _deformation_gradient[_qp].det();
` ` ` 
And in `ComputeLagrangianStressPK1::computeQpCauchyStress()`:
` ` `cpp
    _cauchy_stress[_qp] = _pk1_stress[_qp] * _F[_qp].transpose() / _F[_qp].det();
` ` ` 

### 3. `RankTwoTensor` class methods
The `RankTwoTensor` class itself does not expose methods like `rotate()`, `pushForward()`, or `pullBack()` for general tensor transformations.  These operations are typically handled at a higher level within material models, where the context of deformation gradient and Jacobian is available.

### 4. Elasticity tensor transformation
The push-forward of the 4th-order elasticity tensor is shown in `ComputeHypoelasticStVenantKirchhoffStress::computeQpSmallStress()`:
` ` `cpp
  const RankTwoTensor F = _def_grad[_qp];
  const Real J = F.det();
  const RankFourTensor FF = F.times<i, k, j, l>(F);
  const RankFourTensor FtFt = F.times<k, i, l, j>(F);
  const RankFourTensor C0 = _elasticity_tensor[_qp];
  const RankFourTensor C = FF * C0 * FtFt / J;
` ` ` 

### 5. Tangent modulus transformation for consistent linearization in total Lagrangian
MOOSE handles the tangent modulus transformation for consistent linearization in total Lagrangian formulations through the `_pk1_jacobian` property in `ComputeLagrangianStressBase`  and its derivatives in subclasses. For example, `ComputeLagrangianStressPK2::computeQpPK1Stress()` calculates `_pk1_jacobian` based on `_C[_qp]` (2nd PK tangent) and the deformation gradient.  The `TotalLagrangianStressDivergenceBase` kernel then uses this `_pk1_jacobian` for its computations. 

### 7. Material vs spatial descriptions
MOOSE converts back and forth between material (reference) and spatial (current) descriptions. The `ComputeLagrangianStressBase` class and its derivatives are designed to handle both Cauchy stress (spatial) and 1st Piola-Kirchhoff stress (material), along with their respective Jacobians.  This allows for flexibility in material model implementation while providing the necessary quantities for both total and updated Lagrangian kernels.  For instance, `ComputeLagrangianStressCauchy` computes Cauchy stress and then wraps it to get 1st PK stress,

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
