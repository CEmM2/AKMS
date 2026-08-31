---
id: moose-objectivity-frame-operations
title: MOOSE Objectivity — Push-Forward, Pull-Back, and Frame Operations
domain: constitutive
subdomain: algorithmic
tags:
- objectivity
- total-lagrangian
- push-forward
- pull-back
- hughes-winget
- jaumann-rate
- truesdell-rate
- stress-measures
- 2nd-piola-kirchhoff
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: large
reading_priority: full
akms_schema: v2
edges:
- to: moose-stress-computation-chain
  type: requires
  weight: 0.7
  note: Part of the stress computation dispatch chain
- to: moose-strain-formulations
  type: requires
  weight: 0.8
  note: Frame operations depend on strain/deformation gradient
- to: cm-kinematics-tl
  type: implements
  weight: 0.9
  note: Implements total Lagrangian formulation and tensor transformations
- to: cm-objective-rates
  type: implements
  weight: 0.9
  note: Implements objective stress rate formulations (Jaumann, Truesdell)
---

# MOOSE Objectivity — Push-Forward, Pull-Back, and Frame Operations

Framework knowledge node covering 4 aspect(s) of Objectivity — Push-Forward, Pull-Back, and Frame Operations.

## Total Lagrangian formulation in MOOSE

MOOSE implements a total Lagrangian formulation in Tensor Mechanics through specific kernels and material properties, primarily using the `TotalLagrangianStressDivergence` kernel and related `ComputeLagrangianStrain` and `ComputeLagrangianStressBase` material classes  . This approach uses the initial, undeformed configuration as the reference for stress divergence calculations .

## MOOSE's Total Lagrangian Implementation

### 1. Total Lagrangian Approach and Stress Divergence
MOOSE implements the total Lagrangian approach by formulating the equilibrium equations in the initial, undeformed configuration . The stress divergence is computed using the 1st Piola-Kirchhoff stress tensor (`_pk1`) and the gradient of the test function in the reference configuration .

The weak form of the stress divergence in the reference configuration is given by:
$$
\int_{V_0} \mathbf{P} : \nabla_0 \delta \mathbf{u} \, dV_0 = \int_{V_0} \mathbf{b}_0 \cdot \delta \mathbf{u} \, dV_0 + \int_{A_0} \mathbf{t}_0 \cdot \delta \mathbf{u} \, dA_0
$$
where $\mathbf{P}$ is the 1st Piola-Kirchhoff stress tensor, $\nabla_0$ is the gradient with respect to the reference configuration, $\delta \mathbf{u}$ is the virtual displacement, $\mathbf{b}_0$ is the body force per unit reference volume, and $\mathbf{t}_0$ is the traction per unit reference area .

The `TotalLagrangianStressDivergenceBase::computeQpResidual()` method calculates the residual contribution for the weak form as:
$$
\text{gradTest}(\alpha) : \text{_pk1}[\text{_qp}]
$$
where `gradTest` is the gradient of the test function and `_pk1` is the 1st Piola-Kirchhoff stress .

### 2. `StressDivergenceTensors` with `use_displaced_mesh = false`
The `StressDivergenceTensors` kernel is part of the older kernel system . While it has a `use_displaced_mesh` parameter, setting it to `false` does not make it a total Lagrangian formulation in the context of the *new* Lagrangian kernel system . The new Lagrangian kernel system explicitly uses `TotalLagrangianStressDivergence` for the total Lagrangian path . The `TotalLagrangianStressDivergenceBase` explicitly suppresses the `use_displaced_mesh` parameter, enforcing that it is off .

### 3. Deformation Gradient Computation and Storage
The deformation gradient `F` is computed by the `ComputeLagrangianStrain` class . For large deformations, it is calculated as $F_{iJ} = \delta_{iJ} + \frac{\partial u_i}{\partial X_J}$ . This `F` is then stored as a `MaterialProperty<RankTwoTensor>` and is accessible to other material models and kernels through its name, typically `deformation_gradient` . For example, `ComputeLagrangianStressCauchy` and `ComputeLagrangianStressPK1` retrieve it using `getMaterialPropertyByName<RankTwoTensor>(_base_name + "deformation_gradient")`  .

### 4. 2nd Piola-Kirchhoff Stress (S) vs Cauchy Stress (σ)
MOOSE's new Lagrangian material system, represented by `ComputeLagrangianStressBase`, is designed to provide both Cauchy stress (`_cauchy_stress`) and 1st Piola-Kirchhoff stress (`_pk1_stress`) . The 2nd Piola-Kirchhoff stress (`_S`) is typically computed by specialized material models like `ComputeLagrangianStressPK2` or `ComputeNeoHookeanStress`  .

The conversion from 2nd Piola-Kirchhoff stress (S) to 1st Piola-Kirchhoff stress (P) and then to Cauchy stress (σ) is handled within the `ComputeLagrangianStressPK2`, `ComputeLagrangianStressPK1`, and `ComputeLagrangianStressCauchy` classes  .

The conversion from 2nd Piola-Kirchhoff stress (S) to 1st Piola-Kirchhoff stress (P) is:
$$
\mathbf{P} = \mathbf{F} \cdot \mathbf{S} \quad (1)
$$
This is implemented in `ComputeLagrangianStressPK2::computeQpPK1Stress()` .

The conversion from 1st Piola-Kirchhoff stress (P) to Cauchy stress (σ) is:
$$
\sigma = \frac{1}{J} \mathbf{P} \cdot \mathbf{F}^T \quad (2)
$$
This is implemented in `ComputeLagrangianStressPK1::computeQpCauchyStress()` .
Conversely, the conversion from Cauchy stress (σ) to 1st Piola-Kirchhoff stress (P) is:
$$
\mathbf{P} = J \sigma \cdot \mathbf{F}^{-T} \quad (3)
$$
This is implemented in `ComputeLagrangianStressCauchy::computeQpPK1Stress()` .

### 5. Updated Lagrangian Option
MOOSE supports an updated Lagrangian formulation with `use_displaced_mesh = true` for large deformation kinematics . This is handled by the `UpdatedLagrangianStressDivergence` kernel . In this formulation, the equilibrium equations are written with respect to the current (deformed) configuration . The kernel requires the Cauchy stress (`_stress`) and its derivative with respect to the spatial velocity gradient (`_material_jacobian`) .

### 6. Total Lagrangian vs. Updated Lagrangian Trade-offs
The choice between total Lagrangian and updated Lagrangian formulations in MOOSE is primarily managed by the `formulation` parameter within the `Physics/SolidMechanics/QuasiStatic` action, which can be set to `TOTAL` or `UPDATED` .

*   **Total Lagrangian:**
    *   Uses the initial configuration as the reference .
    *   Requires the 1st Piola-Kirchhoff stress and its derivative with respect to the deformation gradient .
    *   The `TotalLagrangianStressDivergence` kernel explicitly sets `use_displaced_mesh = false` .
    *   Homogenization constraints currently only support the total Lagrangian formulation .

*   **Updated Lagrangian:**
    *   Uses the current (deformed) configuration as the reference .
    *   Requires the Cauchy stress and its derivative with respect to the spatial velocity gradient .
    *   The `UpdatedLagrangianStressDivergence` kernel requires `use_displaced_mesh = true` for large kinematics .

The trade-offs involve whether the reference configuration needs to be recomputed at each step (updated Lagrangian) or remains constant (total Lagrangian). The total Lagrangian formulation simplifies some aspects by always referring to the initial geometry, while the updated Lagrangian formulation is often more natural for rate-dependent material models.

### 7. `ComputeLagrangianStrain` vs. `ComputeFiniteStrain`
*   **`ComputeLagrangianStrain`**: This class is part of the new Lagrangian kernel system . It calculates kinematic quantities for both small and large deformation theories, controlled by the `large_kinematics` flag . It computes the deformation gradient `F` and various strain measures, including incremental and total strains . It also includes stabilization options like $\bar{F}$ stabilization . It explicitly requires `use_displaced_mesh=false` .

*   **`ComputeFiniteStrain`**: This class belongs to the older kernel system . It calculates finite strain measures but is not directly integrated with the new Lagrangian kernel system's material and kernel interfaces . The new Lagrangian kernel system aims to provide exact large deformation Jacobians without requiring AD, which is a key difference .

The formulation choice propagates through the code via the `_lagrangian_kernels` and `_lk_formulation` flags within the `QuasiStaticSolidMechanicsPhysics` action . These flags determine which stress divergence kernel (`TotalLagrangianStressDivergence` or `UpdatedLagrangianStressDivergence`) and which strain calculator (`ComputeLagrangianStrain`) are instantiated .

## Classes & Methods

*   `TotalLagrangianStressDivergenceBase<G>::computeQpResidual()`: Calculates the residual contribution for the total Lagrangian weak form


## Objectivity and stress rate formulations

MOOSE handles objectivity in large-deformation solid mechanics primarily through the `ComputeLagrangianObjectiveStress` class, which provides an interface to convert small-deformation constitutive models to large-deformation formulations by integrating objective stress rates . This class supports Truesdell, Jaumann, and Green-Naghdi objective rates, with Truesdell being the default . Additionally, the `ComputeFiniteStrain` class offers different decomposition methods, including Hughes-Winget, for calculating strain and rotation increments .

## Objective Stress Rates
MOOSE provides three objective stress rates within the `ComputeLagrangianObjectiveStress` class: Truesdell, Jaumann, and Green-Naghdi . The default rate is Truesdell .

### Truesdell Rate
The Truesdell rate is defined by the kinematic tensor $Q_{ik} = l_{ik}$ . The `objectiveUpdateTruesdell` method in `ComputeLagrangianObjectiveStress` implements this update .

### Jaumann Rate
The Jaumann rate is defined by the kinematic tensor $Q_{ik} = w_{ik}$, where $w_{ik} = \frac{1}{2}(l_{ik} - l_{ki})$ is the spin tensor . This is explicitly implemented in the `objectiveUpdateJaumann` method .

### Green-Naghdi Rate
The Green-Naghdi rate is defined by $Q_{ik} = \Omega_{ik} = \dot{R}_{ij} R_{kj}$ . This rate can be selected using `objective_rate = green_naghdi`  and is implemented in `objectiveUpdateGreenNaghdi` .

## Hughes-Winget Algorithm
The Hughes-Winget method is an option within the `ComputeFiniteStrain` class for calculating strain and rotation increments . When `_use_hw` is true, the deformation gradient midpoint `_def_grad_mid` and `_f_bar` are computed . The old mechanical and total strains are rotated using the `_rotation_increment` when the Hughes-Winget method is active .

## `ComputeFiniteStrain::decomposition_method` Parameter
The `decomposition_method` parameter in `ComputeFiniteStrain` controls how strain and rotation increments are calculated . The available options are `TaylorExpansion`, `EigenSolution`, and `HughesWinget` . This parameter directly influences the objectivity treatment by determining the method for computing the incremental rotation and strain .

## Rotation Tensor in Stress Update
For the Green-Naghdi rate, polar decomposition ($F = R \cdot U$) is performed to obtain the rotation tensor $R$ . The rotation tensor `_rotation` and its derivative `_d_rotation_d_def_grad` are declared if `_polar_decomp` is true . The Green-Naghdi rate uses $\Omega_{ik} = \dot{R}_{ij} R_{kj}$ as its kinematic tensor .

## Hypoelastic Models and Strain Rate Objectification
For hypoelastic models, such as `ComputeHypoelasticStVenantKirchhoffStress`, the small stress update is given by $S_{n+1} = S_n + C : dD$ . The `ComputeLagrangianObjectiveStress` class handles the objectification of the stress rate by integrating an objective rate of the Cauchy stress . The `computeQpSmallStress` method in derived classes like `ComputeHypoelasticStVenantKirchhoffStress` calculates the small stress and Jacobian, which are then used by `ComputeLagrangianObjectiveStress` to perform the objective integration if `_large_kinematics` is true .

## Classes & Methods
*   `ComputeLagrangianObjectiveStress::validParams()`: Defines valid input parameters for the objective stress computation .
*   `ComputeLagrangianObjectiveStress::computeQpCauchyStress()`: Orchestrates the computation of Cauchy stress, performing objective integration if large kinematics are enabled .
*   `ComputeLagrangianObjectiveStress::computeQpSmallStress()`: A virtual method to be implemented by derived classes to provide the small stress update .
*   `ComputeLagrangianObjectiveStress::objectiveUpdateTruesdell(const RankTwoTensor & dS)`: Implements the objective update using the Truesdell rate .
*   `ComputeLagrangianObjectiveStress::objectiveUpdateJaumann(const RankTwoTensor & dS)`: Implements the objective update using the Jaumann rate .
*   `ComputeLagrangianObjectiveStress::objectiveUpdateGreenNaghdi(const RankTwoTensor & dS)`: Implements the objective update using the Green-Naghdi rate .
*   `ComputeFiniteStrain::validParams()`: Defines valid input parameters for finite strain computation, including `decomposition_method` .
*   `ComputeFiniteStrain::computeProperties()`: Computes strain and rotation increments based on the chosen decomposition method .
*   `ComputeFiniteStrain::computeQpIncrements(RankTwoTensor & total_strain_increment, RankTwoTensor & rotation_increment)`: Calculates the strain and rotation increments using the specified decomposition method .
*   `ComputeHypoelasticStVenantKirchhoffStress::computeQpSmallStress()`: Implements the elastic small stress update for the St. Venant-Kirchhoff model .

## Equations
### General Objective Rate Form
The general form for objective rates is given by:
$$
\hat{\sigma}_{ij} = s_{ij}=\dot{\sigma}_{ij}-Q_{ik}\sigma_{kj}-\sigma_{ik}Q_{jk}+Q_{kk}\sigma_{ij} \quad (1)
$$ 
where $Q_{ik}$ is a kinematic measure and $s_{ij}$ is the small stress.

### Truesdell Rate Kinematic Tensor
The kinematic tensor for the Truesdell rate is:
$$
Q_{ik}=l_{ik} \quad (2)
$$ 

### Jaumann Rate Kinematic Tensor
The kinematic tensor for the Jaumann rate is:
$$
Q_{ik}=w_{ik} \quad (3)
$$
with
$$
w_{ik}=\frac{1}{2}\left(l_{ik}-l_{ki}\right) \quad (4)
$$ 

### Green-Naghdi Rate Kinematic Tensor
The kinematic tensor for the Green-Naghdi rate is:
$$
Q_{ik} = \Omega_{ik} = \dot{R}_{ij} R_{kj} \quad (5)
$$ 

## Parameters
*   `objective_rate = value`: Type: `MooseEnum`, Default: `truesdell`. Specifies the objective integration rate to use. Options are `truesdell`, `jaumann`, `green_naghdi` .
*   `decomposition_method = value`: Type: `MooseEnum`, Default: `TaylorExpansion`. Specifies the method to calculate strain and rotation increments. Options are `TaylorExpansion`, `EigenSolution`, `HughesWinget` .

## Relationships
` ` `mermaid
classDiagram
    class ComputeLagrangianStressCauchy {
        +computeQpCauchyStress()
    }
    class ComputeLagrangianObjectiveStress {
        <<abstract>>
        +objectiveUpdateTruesdell()
        +objectiveUpdateJaumann()
        +objectiveUpdateGreenNaghdi()
        +computeQpSmallStress()
        -_rate
        -_polar_decomp
        -_rotation
        -_rotation_old
        -_d_rotation_d_def_grad
        -_stretch
    }
    class ComputeHypoelasticStVenantKirchhoffStress {
        +computeQpSmallStress()
    }
    class ComputeLagrangianWrappedStress {
        +computeQpSmallStress()
    }
    class ComputeIncrementalStrainBase {
        +computeProperties()
    }
    class ComputeFiniteStrain {
        +computeProperties()
        +computeQpIncrements()
        -_decomposition_method
        -_use_hw
        -_def_grad_mid
        -_f_bar
    }

    ComputeLagrangianStressCauchy <|-- ComputeLagrangianObjectiveStress : inherits
    ComputeLagrangianObjectiveStress <|-- ComputeHypoelasticStVenantKirchhoffStress : inherits
    ComputeLagrangianObjectiveStress <|-- ComputeLagrangianWrappedStress : inherits
    ComputeIncrementalStrainBase <|-- ComputeFiniteStrain : inherits

    ComputeLagrangianObjectiveStress ..> ComputeFiniteStrain : uses _rotation_increment (indirectly via _vorticity_increment)
    ComputeLagrangianObjectiveStress ..> ComputeLagrangianObjectiveStress.ObjectiveRate : uses
` ` `

## Code Snippets
### `ComputeLagrangianObjectiveStress` Constructor and Member Variables
` ` `cpp
ComputeLagrangianObjectiveStress::ComputeLagrangianObjectiveStress(
    const InputParameters & parameters)
  : ComputeLagrangianStressCauchy(parameters),
    _small_stress(declareProperty<RankTwoTensor>(_base_name + "small_stress")),
    _small_stress_old(getMaterialPropertyOld<RankTwoTensor>(_base_name + "small_stress")),
    _small_jacobian(declareProperty<RankFourTensor>(_base_name + "small_jacobian")),
    _cauchy_stress_old(getMaterialPropertyOld<RankTwoTensor>(_base_name + "cauchy_stress")),
    _mechanical_strain(getMaterialPropertyByName<RankTwoTensor>(_base_name + "mechanical_strain")),
    _strain_increment(getMaterialPropertyByName<RankTwoTensor>(_base_name + "strain_increment")),
    _vorticity_increment(
        getMaterialPropertyByName<RankTwoTensor>(_base_name + "vorticity_increment")),
    _def_grad(getMaterialPropertyByName<RankTwoTensor>(_base_name + "deformation_gradient")),
    _def_grad_old(getMaterialPropertyOldByName<RankTwoTensor>(_base_name + "deformation_gradient")),
    _rate(getParam<MooseEnum>("objective_rate").getEnum<ObjectiveRate>()),
    _polar_decomp(_rate == ObjectiveRate::GreenN


## Push-forward and pull-back tensor operations

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


## Stress measures and conversions in MOOSE

MOOSE's Solid Mechanics module computes and converts between several stress and strain measures, primarily focusing on Cauchy stress, 1st Piola-Kirchhoff (PK1) stress, and 2nd Piola-Kirchhoff (PK2) stress, along with Green-Lagrange strain. The conversions are handled within a hierarchy of material classes, specifically `ComputeLagrangianStressBase` and its derivatives, which implement the necessary transformations based on whether large or small deformation kinematics are used .

## Stress Measures and Conversions

### 1. Cauchy stress $\sigma$ (true stress)
The Cauchy stress is a primary output in MOOSE, particularly when using classes derived from `ComputeLagrangianStressCauchy` . It is stored as a `MaterialProperty<RankTwoTensor>` named `_cauchy_stress` .

#### Conversion from 1st Piola-Kirchhoff stress to Cauchy stress
When `_large_kinematics` is true, the Cauchy stress is computed from PK1 stress using the deformation gradient $F$ and its determinant $J$ (which is `_F[_qp].det()`):
$$
\sigma = \frac{1}{J} P F^T \quad (1)
$$ 
This conversion is implemented in `ComputeLagrangianStressPK1::computeQpCauchyStress()` . For small deformations, Cauchy stress is considered equivalent to PK1 stress .

### 2. 1st Piola-Kirchhoff stress $P$
The 1st Piola-Kirchhoff stress is also a primary output, especially for total Lagrangian formulations . It is stored as `_pk1_stress` .

#### Conversion from Cauchy stress to 1st Piola-Kirchhoff stress
When `_large_kinematics` is true, PK1 stress is computed from Cauchy stress using the deformation gradient $F$ and its inverse $F^{-1}$ (represented by `_inv_def_grad`) and determinant $J$:
$$
P = J \sigma F^{-T} \quad (2)
$$ 
This conversion is implemented in `ComputeLagrangianStressCauchy::computeQpPK1Stress()` . For small deformations, PK1 stress is considered equivalent to Cauchy stress .

#### Conversion from 2nd Piola-Kirchhoff stress to 1st Piola-Kirchhoff stress
When `_large_kinematics` is true, PK1 stress is computed from PK2 stress using the deformation gradient $F$:
$$
P = F S \quad (3)
$$ 
This conversion is implemented in `ComputeLagrangianStressPK2::computeQpPK1Stress()` . For small deformations, PK1 stress is considered equivalent to PK2 stress .

### 3. 2nd Piola-Kirchhoff stress $S$
The 2nd Piola-Kirchhoff stress is used for total Lagrangian formulations  and is stored as `_S` . Classes like `ComputeNeoHookeanStress`  and `ComputeStVenantKirchhoffStress`  directly compute PK2 stress.

### 4. Kirchhoff stress $\tau = J \sigma$
The Kirchhoff stress is mentioned in the context of Simo-Hughes J2 plasticity . While not explicitly stored as a `MaterialProperty`, it is computed within the `ComputeSimoHughesJ2PlasticityStress` class .

### 5. Mandel stress $M_e = C^e S^e = F^{eT} \tau F^{e-T}$
The Mandel stress is not directly computed or stored as a `MaterialProperty` in the provided context. However, `MandelConverter` is included in `ComputeLagrangianObjectiveCustomStress.h` , suggesting its potential use for conversions related to custom material models.

## Strain Measures

### 6. Green-Lagrange strain $E = \frac{1}{2}(F^T F - I)$
MOOSE computes the Green-Lagrange strain. It is explicitly calculated in `ComputeLagrangianStressPK2::computeQpPK1Stress()`  and stored as `_E` . `ADComputeGreenLagrangeStrain` is a dedicated class for defining this strain tensor . The Almansi strain is not explicitly mentioned as being computed.

### 7. Logarithmic (Hencky) strain: $\ln(U)$
Logarithmic strain is available in MOOSE. It is referred to as "mechanical_strain" and represents the integrated deformation rate . It is used as an input to stress computation classes like `ComputeLagrangianObjectiveStress` .

## Conversion Handling

Conversions between stress measures are handled through a hierarchy of material classes, primarily `ComputeLagrangianStressBase` and its derived classes (`ComputeLagrangianStressCauchy`, `ComputeLagrangianStressPK1`, `ComputeLagrangianStressPK2`). These classes define virtual methods for computing specific stress measures and then wrap these to provide other required stress forms    . The conversions are performed "ad-hoc" within these material models, often with conditional logic based on the `_large_kinematics` flag to switch between large and small deformation formulations   .

### Classes & Methods:

*   `ComputeLagrangianStressBase` : Base class for Lagrangian stress computations, defining the interface for Cauchy and 1st PK stress and their Jacobians .
    *   `computeQpStressUpdate()`: Virtual method to be implemented by derived classes for stress updates .
*   `ComputeLagrangianStressCauchy` : Implements Cauchy stress update and wraps it to provide 1st PK stress .
    *   `computeQpPK1Stress()`: Converts Cauchy stress to 1st PK stress .
*   `ComputeLagrangianStressPK1` : Implements 1st PK stress update and wraps it to provide Cauchy stress .
    *   `computeQpCauchyStress()`: Converts 1st PK stress to Cauchy stress .
*   `ComputeLagrangianStressPK2` : Implements 2nd PK stress update and wraps it to provide 1st PK stress .
    *   `computeQpPK1Stress()`: Converts 2nd PK stress to 1st PK stress and computes Green-Lagrange strain .
*   `ADComputeGreenLagrangeStrain` : Defines the Green-Lagrange strain tensor .
*   `ComputeSimoHughesJ2PlasticityStress` : Computes Kirchhoff stress as part of its algorithm .

### Relationships:

` ` `mermaid
classDiagram
    class Material
    class ComputeLagrangianStressBase
    class ComputeLagrangianStressCauchy
    class ComputeLagrangianStressPK1
    class ComputeLagrangianStressPK2
    class ComputeLagrangianObjectiveStress
    class ComputeNeoHookeanStress
    class ComputeStVenantKirchhoffStress
    class ComputeSimoHughesJ2PlasticityStress
    class ADComputeGreenLagrangeStrain

    Material <|-- ComputeLagrangianStressBase
    ComputeLagrangianStressBase <|-- ComputeLagrangianStressCauchy
    ComputeLagrangianStressBase <|-- ComputeLagrangianStressPK1
    ComputeLagrangianStressPK1 <|-- ComputeLagrangianStressPK2
    ComputeLagrangianStressCauchy <|-- ComputeLagrangianObjectiveStress
    ComputeLagrangianStressPK2 <|-- ComputeNeoHookeanStress
    ComputeLagrangianStressPK2 <|-- ComputeStVenantKirchhoffStress
    ComputeLagrangianStressPK1 <|-- ComputeSimoHughesJ2PlasticityStress

    ComputeLagrangianStressBase : +_cauchy_stress
    ComputeLagrangianStressBase : +_pk1_stress
    ComputeLagrangianStressPK2 : +_E (Green-Lagrange strain)
    ComputeLagrangianStressPK2 : +_S (2nd PK stress)
    ComputeLagrangianStressBase : +_large_kinematics
    ComputeLagrangianStressBase : +computeQpStressUpdate()
    ComputeLagrangianStressCauchy : +computeQpPK1Stress()
    ComputeLagrangianStressPK1 : +computeQpCauchyStress()
    ComputeLagrangianStressPK2 : +computeQpPK1Stress()
    ComputeLagrangianStressPK2 : +

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
