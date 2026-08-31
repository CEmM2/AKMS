---
id: moose-cdm
title: MOOSE Continuum damage mechanics in MOOSE
domain: constitutive
subdomain: algorithmic
tags:
- damage
- CDM
- scalar-damage
- stress-degradation
- nonlocal-regularization
- crack-band
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-continuum-damage
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-continuum-damage
- to: cm-gtn-ductile-fracture
  type: implements
  weight: 0.7
  note: Continuum damage mechanics framework
---

# MOOSE Continuum damage mechanics in MOOSE

MOOSE implements continuum damage mechanics (CDM) through a system of material models that define and apply a scalar damage variable to degrade stress and stiffness. The core components involve a base class for damage models, concrete implementations for damage evolution, and a specialized stress calculator that integrates the damage effect. Nonlocal damage regularization is also available.

## Classes & Methods:

*   `DamageBaseTempl<is_ad>`: An abstract base class for damage models, defining the interface for updating damage, stress, and Jacobian multipliers. 
*   `DamageBaseTempl::updateDamage()`: A virtual method in `DamageBaseTempl` that derived classes override to implement their specific damage evolution laws. 
*   `DamageBaseTempl::updateStressForDamage(GenericRankTwoTensor<is_ad> & stress_new)`: A pure virtual method in `DamageBaseTempl` responsible for modifying the stress tensor based on the calculated damage. 
*   `DamageBaseTempl::updateJacobianMultForDamage(RankFourTensor & jacobian_mult)`: A pure virtual method in `DamageBaseTempl` for updating the material constitutive matrix due to damage. 
*   `ScalarDamageBaseTempl<is_ad>`: A base class for scalar damage models, inheriting from `DamageBaseTempl`.  It manages the scalar damage index and provides methods for its update.
*   `ScalarDamageBaseTempl::updateQpDamageIndex()`: A pure virtual method in `ScalarDamageBaseTempl` that concrete scalar damage models must implement to compute the damage index at each quadrature point. 
*   `ScalarMaterialDamageTempl<is_ad>`: A concrete implementation of `ScalarDamageBaseTempl` where the damage index is prescribed by another material property. 
*   `CombinedScalarDamageTempl<is_ad>`: A scalar damage model that combines multiple damage models using either a "Maximum" or "Product" rule. 
*   `NonlocalDamageTempl<is_ad>`: Implements nonlocal damage regularization by averaging a local damage property over a characteristic length. 
*   `ComputeDamageStressTempl<is_ad>`: A material model that computes stress for damaged elastic materials by interacting with a `DamageBase` derived model. 
*   `ComputeDamageStressTempl::computeQpStress()`: Overrides the base class method to apply damage to the computed stress and Jacobian. 

## Equations:

1.  **Stress Degradation**: The stress $\boldsymbol{\sigma}$ is degraded by the scalar damage variable $d$ from the undamaged stress $\boldsymbol{\sigma}_0$ (or stiffness $\mathbb{C}$ and elastic strain $\boldsymbol{\varepsilon}$). 
    $$ \boldsymbol{\sigma} = (1 - d)\ \mathbb{C} : \boldsymbol{\varepsilon} $$
    This is implemented in `DamageBaseTempl::updateStressForDamage` and `DamageBaseTempl::updateJacobianMultForDamage`. 

2.  **Combined Damage Evolution**: When multiple damage models are used, the total damage $d$ can be computed as either the maximum of individual damage variables ($d_i$) or a product combination. 
    $$ \mathrm{Maximum:} \quad d = \mathrm{max}(d_1 ... d_N) $$
    $$ \mathrm{Product:} \quad d = 1 - \prod_{i=1}^{N} (1 - d_i) $$
    This is handled by the `CombinedScalarDamage` class. 

## Algorithm Steps:

The interaction between damage models and stress computation follows these steps:

1.  An elastic stress is computed by a class like `ComputeFiniteStrainElasticStressTempl`. 
2.  `ComputeDamageStressTempl` retrieves the associated damage model. 
3.  The damage model's `updateDamage()` method is called to evolve the damage variable. 
4.  The `updateStressForDamage()` method of the damage model modifies the computed stress. 
5.  The `updateJacobianMultForDamage()` method of the damage model modifies the material constitutive matrix. 

` ` `pseudocode
function computeQpStress()
  ComputeFiniteStrainElasticStress() // Compute undamaged stress
  _damage_model.setQp(_qp)
  _damage_model.updateDamage() // Evolve damage variable
  _damage_model.updateStressForDamage(this->_stress[_qp]) // Degrade stress
  _damage_model.finiteStrainRotation(this->_rotation_increment[_qp])
  _damage_model.updateJacobianMultForDamage(_Jacobian_mult[_qp]) // Degrade Jacobian
  _material_timestep_limit[_qp] = _damage_model.computeTimeStepLimit()
end function
` ` `


## Parameters:

*   `damage_model`: (Required, MaterialName) Name of the damage model to be used with `ComputeDamageStress`. 
*   `damage_index`: (Required, MaterialPropertyName) Name of the material property containing the damage index for `ScalarMaterialDamage`. 
*   `damage_models`: (Vector of MaterialName) List of damage models to combine in `CombinedScalarDamage`. 
*   `combination_type`: (Enum: Maximum, Product) Specifies how multiple damage models are combined in `CombinedScalarDamage`. Default is `Maximum`. 
*   `local_damage_model`: (MaterialName) The local damage model used by `NonlocalDamage` for averaging. 
*   `average_UO`: (UserObject) The `RadialAverage` UserObject used by `NonlocalDamage` for nonlocal regularization. 

## Relationships:

` ` `mermaid
classDiagram
    class Material {
        +InputParameters validParams()
    }
    class DamageBaseTempl {
        <<abstract>>
        +void updateDamage()
        +void updateStressForDamage(GenericRankTwoTensor& stress_new)
        +void updateJacobianMultForDamage(RankFourTensor& jacobian_mult)
        +Real computeTimeStepLimit()
    }
    class ScalarDamageBaseTempl {
        <<abstract>>
        +void updateQpDamageIndex()
        -GenericMaterialProperty<Real, is_ad>& _damage_index
    }
    class ScalarMaterialDamageTempl {
        -const GenericMaterialProperty<Real, is_ad>& _damage_property
    }
    class CombinedScalarDamageTempl {
        -CombinationType _combination_type
        -std::vector<ScalarDamageBaseTempl*> _damage_models
    }
    class NonlocalDamageTempl {
        -const RadialAverage::Result& _average
        -ScalarDamageBaseTempl* _local_damage_model
    }
    class ComputeFiniteStrainElasticStressTempl {
        +void computeQpStress()
    }
    class ComputeDamageStressTempl {
        -DamageBaseTempl* _damage_model
        +void computeQpStress()
    }

    Material <|-- DamageBaseTempl
    DamageBaseTempl <|-- ScalarDamageBaseTempl
    ScalarDamageBaseTempl <|-- ScalarMaterialDamageTempl
    ScalarDamageBaseTempl <|-- CombinedScalarDamageTempl
    ScalarDamageBaseTempl <|-- NonlocalDamageTempl
    ComputeFiniteStrainElasticStressTempl <|-- ComputeDamageStressTempl

    ComputeDamageStressTempl "1" *-- "1" DamageBaseTempl : uses >
    CombinedScalarDamageTempl "1" *-- "N" ScalarDamageBaseTempl : combines >
    NonlocalDamageTempl "1" *-- "1" ScalarDamageBaseTempl : uses local damage model >
` ` `

## Code Snippets:

**`DamageBase.h` - Abstract Base Class for Damage Models**
` ` `cpp
template <bool is_ad>
class DamageBaseTempl : public Material
{
public:
  static InputParameters validParams();

  DamageBaseTempl(const InputParameters & parameters);

  /**
   * Update the internal variable(s) that evolve the damage
   */
  virtual void updateDamage();

  /**
   * Update the current stress tensor for effects of damage.
   * @param stress_new Undamaged stress to be modified by the damage model
   */
  virtual void updateStressForDamage(GenericRankTwoTensor<is_ad> & stress_new) = 0;

  /**
   * Update the material constitutive matrix
   * @param jacobian_mult Material constitutive matrix to be modified for
   * effects of damage
   */
  virtual void updateJacobianMultForDamage(RankFourTensor & jacobian_mult) = 0;
` ` `


**`ScalarDamageBase.h` - Base Class for Scalar Damage Models**
` ` `cpp
template <bool is_ad>
class ScalarDamageBaseTempl : public DamageBaseTempl<is_ad>
{
public:
  static InputParameters validParams();

  ScalarDamageBaseTempl(const InputParameters & parameters);

  virtual void initQpStatefulProperties() override;

  virtual void updateDamage() override;

  virtual void updateStressForDamage(GenericRankTwoTensor<is_ad> & stress_new) override;

  virtual void updateJacobianMultForDamage(RankFourTensor & jacobian_mult) override;

  virtual void computeUndamagedOldStress(RankTwoTensor & stress_old) override;

  virtual Real computeTimeStepLimit() override;

  /**
   * Get the value of the damage index for the current quadrature point.
   */
  const GenericReal<is_ad> & getQpDamageIndex(unsigned int qp);

  /**
   * Get the name of the material property containing the damage index
   */
  const std::string getDamageIndexName() const { return _damage_index_name; }

protected:
  /// Name of the material property where the damage index is stored
  const MaterialPropertyName _damage_index_name;

  /// Update the damage index at the current qpoint
  virtual void updateQpDamageIndex() = 0;
` ` `


**`ComputeDamageStress.C` - Stress Computation with Damage**
` ` `cpp
template <>
void
ComputeDamageStressTempl<false>::computeQpStress()
{
  ComputeFiniteStrainElasticStressTempl<false>::computeQpStress();

  _damage_model->setQp(_qp);
  _damage_model->updateDamage();
  _damage_model->updateStressForDamage(this->_stress[_qp]);
  _damage_model->finiteStrainRotation(this->_rotation_increment[_qp]);
  _damage_model->updateJacobianMultForDamage(_Jacobian_mult[_qp]);

  _material_timestep_limit[_qp] = _damage_model->computeTimeStepLimit();
}
` ` `


## MOOSE Input Syntax:

**Basic Scalar Damage Model**
` ` `ini
[Materials]
  [damage_index]
    type = GenericFunctionMaterial
    prop_names = damage_index_prop
    prop_values = damage_evolution
  []
  [damage]
    type = ScalarMaterialDamage
    damage_index = damage_index_prop
  []
  [stress]
    type = ComputeDamageStress
    damage_model = damage
  []
  [elasticity]
    type = ComputeIsotropicElasticityTensor
    poissons_ratio = 0.2
    youngs_modulus = 10e9
  []
[]
` ` `


**Combined Scalar Damage Model**
` ` `ini
[Materials]
  [damage_index_a]
    type = GenericFunctionMaterial
    prop_names = damage_index_prop_a
    prop_values = damage_evolution_a
  []
  [damage_index_b]
    type = GenericFunctionMaterial
    prop_names = damage_index_prop_b
    prop_values = damage_evolution_b
  []
  [damage_a]
    type = ScalarMaterialDamage
    damage_index = damage_index_prop_a
    damage_index_name = damage_index_a
  []
  [damage_b]
    type = ScalarMaterialDamage
    damage_index = damage_index_prop_b
    damage_index_name = damage_index_b
  []
  [damage]
    type = CombinedScalarDamage
    damage_models = 'damage_a damage_b'
  []
  [stress]
    type = ComputeDamageStress
    damage_model = damage
  []
  [elasticity]
    type = ComputeIsotropicElasticityTensor
    poissons_ratio = 0.2
    youngs_modulus = 10e9
  []
[]
` ` `
<

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
