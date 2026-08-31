---
id: moose-total-lagrangian
title: MOOSE Total Lagrangian formulation in MOOSE
domain: constitutive
subdomain: algorithmic
tags:
- total-lagrangian
- 2nd-piola-kirchhoff
- stress-divergence
- reference-configuration
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
- to: cm-kinematics-tl
  type: implements
  weight: 0.9
  note: Total Lagrangian formulation with PK2 stress
---

# MOOSE Total Lagrangian formulation in MOOSE

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

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
