---
id: moose-strain-formulations
title: MOOSE Kinematics — Strain Formulations
domain: constitutive
subdomain: algorithmic
tags:
- kinematics
- small-strain
- finite-strain
- deformation-gradient
- eigenstrain
- thermal-expansion
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: medium
reading_priority: full
akms_schema: v2
edges:
- to: moose-stress-computation-chain
  type: requires
  weight: 0.7
  note: Part of the stress computation dispatch chain
- to: cm-kinematics-tl
  type: implements
  weight: 0.9
  note: Implements finite strain kinematics and deformation gradient computation
---

# MOOSE Kinematics — Strain Formulations

Framework knowledge node covering 2 aspect(s) of Kinematics — Strain Formulations.

## Strain computation classes and formulations

This response describes how MOOSE computes strains in the Tensor Mechanics module, covering small strain, incremental small strain, finite strain, and related concepts like eigenstrain subtraction and volumetric locking. The explanation focuses on the `ComputeSmallStrain` and `ComputeFiniteStrain` classes and their associated methods and parameters.

## Classes & Methods

*   `ComputeStrainBase` : Base class for strain tensor computations.
*   `ComputeStrainBase::validParams()` : Defines common input parameters for strain computation classes, including `displacements`, `base_name`, `volumetric_locking_correction`, `eigenstrain_names`, and `global_strain`.
*   `ComputeStrainBase::_mechanical_strain` : Material property representing the mechanical strain.
*   `ComputeStrainBase::_total_strain` : Material property representing the total strain.
*   `ComputeSmallStrain` : Computes small, total strain for linear elasticity problems.
*   `ComputeSmallStrain::computeProperties()` : Calculates the small strain tensor.
*   `ComputeIncrementalStrainBase` : Base class for incremental strain formulations.
*   `ComputeIncrementalStrainBase::subtractEigenstrainIncrementFromStrain()` : Subtracts eigenstrain increments from the calculated strain.
*   `ComputeFiniteStrain` : Computes strain and rotation increments for finite strains.
*   `ComputeFiniteStrain::computeProperties()` : Calculates the incremental deformation gradient and handles volumetric locking correction.
*   `ComputeFiniteStrain::computeQpStrain()` : Computes the strain increment and updates total and mechanical strains.
*   `ComputeFiniteStrain::computeQpIncrements()` : Calculates strain and rotation increments based on the chosen decomposition method.
*   `ComputeFiniteStrain::decompositionType()` : Returns the available decomposition methods for finite strain.

## Relationships

` ` `mermaid
classDiagram
    class Material {
        +InputParameters validParams()
    }
    class ComputeStrainBase {
        +InputParameters validParams()
        +void initialSetup()
        #MaterialProperty<RankTwoTensor>& _mechanical_strain
        #MaterialProperty<RankTwoTensor>& _total_strain
        #std::vector<const MaterialProperty<RankTwoTensor>*> _eigenstrains
        #bool _volumetric_locking_correction
    }
    class ComputeSmallStrain {
        +void computeProperties()
    }
    class ComputeIncrementalStrainBase {
        +void initialSetup()
        #void subtractEigenstrainIncrementFromStrain(RankTwoTensor& strain)
        #std::vector<const VariableGradient*> _grad_disp_old
        #MaterialProperty<RankTwoTensor>& _strain_increment
        #MaterialProperty<RankTwoTensor>& _rotation_increment
        #MaterialProperty<RankTwoTensor>& _deformation_gradient
        #const MaterialProperty<RankTwoTensor>& _mechanical_strain_old
        #const MaterialProperty<RankTwoTensor>& _total_strain_old
    }
    class ComputeFiniteStrain {
        +InputParameters validParams()
        +void computeProperties()
        #void computeQpStrain()
        #void computeQpIncrements(RankTwoTensor& e, RankTwoTensor& r)
        #std::vector<RankTwoTensor> _Fhat
        #DecompMethod _decomposition_method
        #bool _use_hw
    }

    Material <|-- ComputeStrainBase
    ComputeStrainBase <|-- ComputeSmallStrain
    ComputeStrainBase <|-- ComputeIncrementalStrainBase
    ComputeIncrementalStrainBase <|-- ComputeFiniteStrain
` ` `

## 1. `ComputeSmallStrain` — linearized strain ε = ½(∇u + ∇uᵀ)

The `ComputeSmallStrain` class calculates the small, total strain for linear elasticity problems . The linearized small strain is defined as:
$$
\epsilon = \frac{1}{2} \left( \nabla u + (\nabla u)^T \right) \quad \text{when} \quad \frac{\partial u}{ \partial x} << 1
$$ 
This calculation is performed in the `ComputeSmallStrain::computeProperties()` method . The displacement gradient `grad_tensor` is obtained from the coupled displacement variables `_grad_disp` . The `_total_strain` material property is then updated with this calculated strain .

` ` `cpp
// strain = (grad_disp + grad_disp^T)/2
const auto grad_tensor = RankTwoTensor ::initializeFromRows(
    (*_grad_disp[0])[_qp], (*_grad_disp[1])[_qp], (*_grad_disp[2])[_qp]);

_total_strain[_qp] = (grad_tensor + grad_tensor.transpose()) / 2.0;
` ` ` 

## 2. `ComputeIncrementalSmallStrain` — incremental formulation, how is the strain increment Δε computed?

The prompt mentions `ComputeIncrementalSmallStrain`, but the codebase primarily uses `ComputeIncrementalStrainBase` as the base class for incremental formulations . The strain increment is computed in derived classes like `ComputeFiniteStrain`. The `_strain_increment` material property stores this value .

## 3. `ComputeFiniteStrain` — the multiplicative decomposition F = R·U, how are the deformation gradient F, rotation R, and stretch U computed? What decomposition method is used (polar, Hughes-Winget)?

In `ComputeFiniteStrain`, the deformation gradient $F$ is represented by `_deformation_gradient` . The incremental deformation gradient, $\hat{F}$, is computed in `ComputeFiniteStrain::computeProperties()` .
The decomposition of $\hat{F}$ into rotation $\hat{R}$ and stretch $\hat{U}$ (or related quantities) is handled within `ComputeFiniteStrain::computeQpIncrements()` .

MOOSE supports three decomposition methods for finite strain :
*   `TaylorExpansion` (default) 
*   `EigenSolution`
*   `HughesWinget`

The choice is made via the `decomposition_method` parameter .

### Taylor Expansion Method
This method approximates the strain increment and rotation increment using a Taylor expansion of the incremental deformation gradient . The strain increment `total_strain_increment` is calculated from `Cinv_I` . The rotation increment `rotation_increment` is computed using components `a`, `C1`, `C2`, and `C3` derived from the inverse of `_Fhat` .

### Eigen Solution Method
This method uses the polar decomposition approach. It computes the right stretch tensor $\hat{U}$ from $\hat{C} = \hat{F}^T \hat{F}$ using `MathUtils::sqrt(Chat)` . The rotation increment $\hat{R}$ is then calculated as $\hat{F} \hat{U}^{-1}$ . The strain increment is obtained by taking the logarithm of $\hat{U}$ .
$$
\hat{\boldsymbol{U}} = \sqrt{\lambda_{1}}\boldsymbol{N}_{1} + \sqrt{\lambda_{2}}\boldsymbol{N}_{2} + \sqrt{\lambda_{3}}\boldsymbol{N}_{3}
$$ 
$$
\hat{\boldsymbol{R}} = \hat{\boldsymbol{F}} \hat{\boldsymbol{U}}^{-1}
$$ 
The strain increment is given by:
$$
\boldsymbol{D} = \log{\sqrt{\lambda_{1}}}\boldsymbol{N}_{1} + \log{\sqrt{\lambda_{2}}}\boldsymbol{N}_{2} + \log{\sqrt{\lambda_{3}}}\boldsymbol{N}_{3}
$$ 

### Hughes-Winget Method
This method approximates the stretching rate tensor $\boldsymbol{D}$ and incremental rotation matrix $\hat{\boldsymbol{R}}$ based on the spatial gradient $\boldsymbol{G}$ of the displacement field evaluated at the mid-point of the time step .
The spatial gradient $\boldsymbol{G}$ is computed as:
$$
\boldsymbol{G} = 2\left( \hat{\boldsymbol{F}} - \boldsymbol{I}\right) \left( \hat{\boldsymbol{F}} + \boldsymbol{I}\right)^{-1}
$$ 
The approximate stretching rate tensor (strain increment) is:
$$
\boldsymbol{D} = \frac{1}{2 \Delta t}\left(\boldsymbol{G} + \boldsymbol{G}^{T} \right)
$$ 
The incremental rotation matrix is approximated by:
$$
\hat{\boldsymbol{R}} = \left(\boldsymbol{I} + \frac{1}{2}\omega \right) \left(\boldsymbol{I} - \frac{1}{2}\omega \right)^{-1}
$$ 
where $\omega = \frac{1}{2}\left(\boldsymbol{G} - \boldsymbol{G}^{T} \right)$ .
In the code, `total_strain_increment` is `0.5 * (G + G.transpose())`  and `rotation_increment` is `Q_1.inverse() * Q_2` .

## 4. Strain increment in finite strain: how is the incremental deformation gradient F_incr = F_new · F_old⁻¹ computed?

The incremental deformation gradient, denoted as `_Fhat` in the code, is computed in `ComputeFiniteStrain::computeProperties()` .
The calculation involves:
1.  `A = gradU` (current displacement gradient) .
2.  `Fbar = gradUold` (old displacement gradient) .
3.  `A = gradU - gradUold` .
4.  `Fbar =


## Eigenstrains and thermal expansion

MOOSE handles eigenstrains by subtracting them from the total strain to compute the mechanical strain. This is managed through a base class `ComputeEigenstrainBase`  and its derived classes, which register eigenstrains that are then collected and subtracted by strain calculator materials like `ComputeStrainBase` . Multiple eigenstrains are combined additively.

## Classes & Methods

*   `ComputeEigenstrainBaseTempl<is_ad>::computeQpEigenstrain()`: An overridden method in derived eigenstrain classes responsible for calculating and storing the eigenstrain tensor at each quadrature point .
*   `ComputeStrainBase::ComputeStrainBase()`: Constructor that retrieves a list of eigenstrain material properties based on user input .
*   `ComputeStrainBase::computeProperties()` (or derived classes like `ComputeRSphericalSmallStrain::computeProperties()` ): This method calculates the total strain and then subtracts all registered eigenstrains to determine the mechanical strain.
*   `ComputeThermalExpansionEigenstrainTempl<is_ad>::computeThermalStrain()`: Calculates the thermal strain based on the thermal expansion coefficient and temperature difference .
*   `ComputeThermalExpansionEigenstrainBaseTempl<is_ad>::computeQpEigenstrain()`: Sets the eigenstrain property based on the computed thermal strain and handles derivatives for Jacobian calculations .

## Equations

The mechanical strain ($\boldsymbol{\epsilon}_{mech}$) is computed by subtracting the sum of all eigenstrains ($\boldsymbol{\epsilon}_{eigen}$) from the total strain ($\boldsymbol{\epsilon}_{total}$) .
$$
\boldsymbol{\epsilon}_{mech} = \boldsymbol{\epsilon}_{total} - \sum_{i} \boldsymbol{\epsilon}_{eigen,i} \quad (1)
$$
For `ComputeThermalExpansionEigenstrain`, the thermal eigenstrain ($\boldsymbol{\epsilon}^{thermal}$) is calculated as:
$$
\boldsymbol{\epsilon}^{thermal} = \alpha \cdot \left( T - T_{stress\_free} \right) \boldsymbol{I} \quad (2)
$$
where $\alpha$ is the thermal expansion coefficient, $T$ is the current temperature, $T_{stress\_free}$ is the stress-free temperature, and $\boldsymbol{I}$ is the identity matrix .

## Algorithm Steps

### Eigenstrain Registration and Subtraction

1.  **Define Eigenstrain Material:** Create a material that inherits from `ComputeEigenstrainBase`  (e.g., `ComputeThermalExpansionEigenstrain` ). This material will compute a specific eigenstrain tensor.
2.  **Register Eigenstrain Name:** In the input file, assign a unique `eigenstrain_name` to each eigenstrain material .
3.  **Specify Eigenstrains in Strain Calculator:** In the `ComputeStrainBase` (or derived strain calculator) block, list the `eigenstrain_names` parameter with all the eigenstrains to be considered .
4.  **Collect Eigenstrains:** The `ComputeStrainBase` constructor collects pointers to the material properties corresponding to the specified `eigenstrain_names` into the `_eigenstrains` vector .
5.  **Compute Total Strain:** The strain calculator computes the total strain based on displacements .
6.  **Subtract Eigenstrains:** In the `computeProperties()` method of the strain calculator, each eigenstrain in the `_eigenstrains` vector is subtracted from the `_total_strain` to yield the `_mechanical_strain` .

` ` `pseudocode
function computeProperties()
  for each quadrature point qp
    compute _total_strain[qp] from displacements
    _mechanical_strain[qp] = _total_strain[qp]
    for each eigenstrain es in _eigenstrains
      _mechanical_strain[qp] -= (*es)[qp]
    end for
  end for
end function
` ` ` 

### Temperature-Dependent CTE in `ComputeThermalExpansionEigenstrain`

1.  **Define Thermal Expansion Coefficient:** The `ComputeThermalExpansionEigenstrain` class takes a `thermal_expansion_coeff` parameter .
2.  **Compute Thermal Strain:** The `computeThermalStrain()` method calculates the thermal strain using the provided `_thermal_expansion_coeff`, current `_temperature`, and `_stress_free_temperature` .
3.  **Store Eigenstrain:** The calculated thermal strain is then stored in the `_eigenstrain` material property by `computeQpEigenstrain()` .

## Parameters

*   `eigenstrain_names`: (vector of `MaterialPropertyName`) A list of material property names corresponding to the eigenstrain tensors to be subtracted from the total strain . Default is `{}`.
*   `thermal_expansion_coeff`: (`Real`) The constant thermal expansion coefficient used by `ComputeThermalExpansionEigenstrain` .
*   `stress_free_temperature`: (`Real`) The temperature at which the material is stress-free, used in thermal expansion calculations .
*   `temperature`: (`MaterialPropertyName`) The name of the material property providing the current temperature .

## Relationships

` ` `mermaid
classDiagram
    class Material
    class ComputeEigenstrainBaseTempl {
        +virtual void computeQpEigenstrain()
        #GenericMaterialProperty& _eigenstrain
    }
    class ComputeThermalExpansionEigenstrainBaseTempl {
        +virtual ValueAndDerivative computeThermalStrain()
        #const std::vector~ValueAndDerivative~& _temperature
        #const VariableValue& _stress_free_temperature
    }
    class ComputeThermalExpansionEigenstrainTempl {
        #const Real& _thermal_expansion_coeff
    }
    class ComputeStrainBase {
        #std::vector~const MaterialProperty~* _eigenstrains
        #MaterialProperty~RankTwoTensor~& _mechanical_strain
        #MaterialProperty~RankTwoTensor~& _total_strain
    }
    class ADComputeStrainBaseTempl {
        #std::vector~const ADMaterialProperty~* _eigenstrains
        #ADMaterialProperty~R2~& _mechanical_strain
        #ADMaterialProperty~R2~& _total_strain
    }

    Material <|-- ComputeEigenstrainBaseTempl
    ComputeEigenstrainBaseTempl <|-- ComputeThermalExpansionEigenstrainBaseTempl
    ComputeThermalExpansionEigenstrainBaseTempl <|-- ComputeThermalExpansionEigenstrainTempl
    Material <|-- ComputeStrainBase
    Material <|-- ADComputeStrainBaseTempl

    ComputeStrainBase "1" *-- "N" ComputeEigenstrainBaseTempl : "collects"
    ADComputeStrainBaseTempl "1" *-- "N" ComputeEigenstrainBaseTempl : "collects"
` ` `

## MOOSE Input Syntax

To define two thermal eigenstrains and apply them in a strain calculation:

` ` `ini
[Materials]
  [./elasticity_tensor]
    type = ComputeIsotropicElasticityTensor
    youngs_modulus = 2.1e5
    poissons_ratio = 0.3
  [../]
  [./small_strain]
    type = ComputeIncrementalStrain
    eigenstrain_names = 'eigenstrain1 eigenstrain2'
  [../]
  [./thermal_expansion_strain1]
    type = ComputeThermalExpansionEigenstrain
    stress_free_temperature = 298
    thermal_expansion_coeff = 1.0e-5
    temperature = temp
    eigenstrain_name = eigenstrain1
  [../]
  [./thermal_expansion_strain2]
    type = ComputeThermalExpansionEigenstrain
    stress_free_temperature = 298
    thermal_expansion_coeff = 0.3e-5
    temperature = temp
    eigenstrain_name = eigenstrain2
  [../]
[]
` ` ` 

## Notes

### Multiple Eigenstrains

MOOSE supports multiple eigenstrains, which are combined additively. The `ComputeStrainBase` class (and its Automatic Differentiation counterpart `ADComputeStrainBaseTempl`) stores a vector of pointers to `MaterialProperty<RankTwoTensor>` named `_eigenstrains`  . During the strain computation, each of these registered eigenstrains is subtracted from the total strain .

### Finite Strain Formulations

The provided context primarily focuses on small strain formulations (e.g., `ComputeRSphericalSmallStrain` , `Compute1DSmallStrain` ). While the base classes `ComputeEigenstrainBase`  and `ComputeStrainBase`  are generic, the specific interaction of eigenstrains with finite strain formulations would depend on the implementation of finite strain calculators, which are not explicitly detailed in the provided snippets. However, the general principle of subtracting eigenstrains from the total strain to get mechanical strain is expected to hold.

### Stress-Free Strains and Derivatives for Jacobian

For thermal eigenstrains, the `_stress_free_temperature` is a crucial parameter . The `ComputeThermalExpansionEigenstrainBaseTempl::computeQpEigenstrain()` method also handles the computation of derivatives of the eigenstrain with respect to temperature (`_deigenstrain_dT`) for Jacobian calculations, especially when Automatic Differentiation (AD) is not used directly (`is_ad == false`) . This ensures that the Jacobian matrix, essential for Newton-Raphson solvers, correctly accounts for the influence of eigenstrains.

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
