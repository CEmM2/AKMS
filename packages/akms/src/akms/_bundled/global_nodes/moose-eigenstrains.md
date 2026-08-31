---
id: moose-eigenstrains
title: MOOSE Eigenstrains and thermal expansion
domain: constitutive
subdomain: algorithmic
tags:
- eigenstrain
- thermal-expansion
- CTE
- stress-free-strain
- additive-decomposition
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
---

# MOOSE Eigenstrains and thermal expansion

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
