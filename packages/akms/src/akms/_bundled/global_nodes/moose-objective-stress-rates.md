---
id: moose-objective-stress-rates
title: MOOSE Objectivity and stress rate formulations
domain: constitutive
subdomain: algorithmic
tags:
- jaumann-rate
- truesdell-rate
- green-naghdi
- hughes-winget
- spin-tensor
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
- to: cm-objective-rates
  type: implements
  weight: 0.9
  note: Objective stress rate implementations
---

# MOOSE Objectivity and stress rate formulations

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

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
