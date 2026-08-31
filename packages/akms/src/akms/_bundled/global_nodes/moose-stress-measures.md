---
id: moose-stress-measures
title: MOOSE Stress measures and conversions in MOOSE
domain: constitutive
subdomain: algorithmic
tags:
- cauchy-stress
- piola-kirchhoff
- kirchhoff-stress
- mandel-stress
- green-lagrange
- hencky-strain
- almansi
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
---

# MOOSE Stress measures and conversions in MOOSE

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
