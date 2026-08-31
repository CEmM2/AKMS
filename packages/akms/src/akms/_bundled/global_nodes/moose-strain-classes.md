---
id: moose-strain-classes
title: MOOSE Strain computation classes and formulations
domain: constitutive
subdomain: algorithmic
tags:
- small-strain
- incremental-strain
- finite-strain
- deformation-gradient
- polar-decomposition
- volumetric-locking
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-strain-formulations
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-strain-formulations
- to: cm-kinematics-tl
  type: implements
  weight: 0.9
  note: Strain computation hierarchy from small to finite
---

# MOOSE Strain computation classes and formulations

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

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
