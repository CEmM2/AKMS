---
id: moose-return-mapping-extension
title: MOOSE Extending radial return for new constitutive models
domain: constitutive
subdomain: procedural
tags:
- radial-return
- stress-update-base
- registration
- history-variables
- validParams
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-return-mapping-base
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-return-mapping-base
---

# MOOSE Extending radial return for new constitutive models

To implement a new inelastic material model using the radial return framework in MOOSE, you will primarily interact with the `RadialReturnStressUpdate` base class or one of its specialized derivatives. The process involves defining the material's constitutive behavior, managing history variables, and registering the model for use by `ComputeMultipleInelasticStress`.  

## Classes & Methods

### Base Class Selection

You should inherit from `RadialReturnStressUpdateTempl<is_ad>` for isotropic inelastic models.  If your model is for creep, consider `RadialReturnCreepStressUpdateBaseTempl<is_ad>` , and for isotropic plasticity, `IsotropicPlasticityStressUpdateTempl<is_ad>` . For anisotropic models, `GeneralizedRadialReturnStressUpdateTempl<is_ad>`  is the appropriate base class, with further specializations like `AnisotropicReturnCreepStressUpdateBaseTempl<is_ad>`  or `AnisotropicReturnPlasticityStressUpdateBaseTempl<is_ad>`  for specific anisotropic behaviors.

### Virtual Methods to Override

The following virtual methods from `RadialReturnStressUpdateTempl` must be overridden to define your material's behavior:

*   `computeStressInitialize(const GenericReal<is_ad> & effective_trial_stress, const GenericRankFourTensor<is_ad> & elasticity_tensor)`: Initializes stress-related quantities at the beginning of a stress update step. 
*   `computeResidual(const GenericReal<is_ad> & effective_trial_stress, const GenericReal<is_ad> & scalar)`: Computes the residual of the yield function or flow rule.  This is the function whose root is sought by the Newton solver.
*   `computeDerivative(const GenericReal<is_ad> & effective_trial_stress, const GenericReal<is_ad> & scalar)`: Computes the derivative of the residual with respect to the scalar inelastic strain increment. 
*   `computeStressFinalize(const GenericRankTwoTensor<is_ad> & plastic_strain_increment)`: Finalizes the stress state and updates history variables after the return mapping iterations converge. 

For models inheriting from `RadialReturnCreepStressUpdateBaseTempl`, you might also need to override `computeStressDerivative` for non-AD versions .

### Class Skeleton Example

Here's a skeleton for a new isotropic inelastic material model, demonstrating the required overrides:

` ` `cpp
template <bool is_ad>
class MyNewInelasticModelTempl : public RadialReturnStressUpdateTempl<is_ad>
{
public:
  static InputParameters validParams()
  {
    InputParameters params = RadialReturnStressUpdateTempl<is_ad>::validParams();
    // Add specific parameters for your model here
    return params;
  }

  MyNewInelasticModelTempl(const InputParameters & parameters)
    : RadialReturnStressUpdateTempl<is_ad>(parameters),
      _my_history_variable(this->template declareGenericProperty<Real, is_ad>(this->_base_name + "my_history_variable")),
      _my_history_variable_old(this->template getMaterialPropertyOld<Real>(this->_base_name + "my_history_variable"))
  {
    // Initialize any member variables
  }

protected:
  // Override virtual methods
  virtual void computeStressInitialize(const GenericReal<is_ad> & effective_trial_stress,
                                       const GenericRankFourTensor<is_ad> & elasticity_tensor) override
  {
    // Implement initialization logic
    RadialReturnStressUpdateTempl<is_ad>::computeStressInitialize(effective_trial_stress, elasticity_tensor);
  }

  virtual GenericReal<is_ad> computeResidual(const GenericReal<is_ad> & effective_trial_stress,
                                             const GenericReal<is_ad> & scalar) override
  {
    // Implement your yield function or flow rule residual
    // Example: return effective_trial_stress - 3 * G * scalar - yield_stress;
    return 0.0; // Placeholder
  }

  virtual GenericReal<is_ad> computeDerivative(const GenericReal<is_ad> & effective_trial_stress,
                                               const GenericReal<is_ad> & scalar) override
  {
    // Implement the derivative of the residual with respect to 'scalar'
    // Example: return -3 * G;
    return 0.0; // Placeholder
  }

  virtual void computeStressFinalize(const GenericRankTwoTensor<is_ad> & inelastic_strain_increment) override
  {
    // Update history variables and perform any final calculations
    _my_history_variable[this->_qp] = _my_history_variable_old[this->_qp] + inelastic_strain_increment.trace(); // Example update
    RadialReturnStressUpdateTempl<is_ad>::computeStressFinalize(inelastic_strain_increment);
  }

  virtual void initQpStatefulProperties() override
  {
    _my_history_variable[this->_qp] = 0.0; // Initialize to zero at the start of a new simulation
    RadialReturnStressUpdateTempl<is_ad>::initQpStatefulProperties();
  }

  virtual void propagateQpStatefulProperties() override
  {
    _my_history_variable[this->_qp] = _my_history_variable_old[this->_qp]; // Propagate old value
    RadialReturnStressUpdateTempl<is_ad>::propagateQpStatefulProperties();
  }

  // Declare stateful material properties
  GenericMaterialProperty<Real, is_ad> & _my_history_variable;
  const MaterialProperty<Real> & _my_history_variable_old;
};

typedef MyNewInelasticModelTempl<false> MyNewInelasticModel;
typedef MyNewInelasticModelTempl<true> ADMyNewInelasticModel;
` ` `

### History Variables (Stateful MaterialProperties)

History variables are managed as stateful `MaterialProperty` objects.   You declare them in your class header and initialize them in the constructor and `initQpStatefulProperties()` method.  

For example, to declare a history variable `_my_history_variable` of type `Real`:

` ` `cpp
  GenericMaterialProperty<Real, is_ad> & _my_history_variable;
  const MaterialProperty<Real> & _my_history_variable_old;
` ` ` 

In the constructor, you associate these with material properties:

` ` `cpp
  MyNewInelasticModelTempl(const InputParameters & parameters)
    : RadialReturnStressUpdateTempl<is_ad>(parameters),
      _my_history_variable(this->template declareGenericProperty<Real, is_ad>(this->_base_name + "my_history_variable")),
      _my_history_variable_old(this->template getMaterialPropertyOld<Real>(this->_base_name + "my_history_variable"))
  {
  }
` ` ` 

You must override `initQpStatefulProperties()` to set initial values (e.g., zero)  and `propagateQpStatefulProperties()` to carry over values from the previous time step. 

### Registration with `ComputeMultipleInelasticStress`

To make your new material model usable by `ComputeMultipleInelasticStress`, you need to register it using `registerMooseObject`.  This is typically done in the `.C` file of your material.

` ` `cpp
registerMooseObject("SolidMechanicsApp", MyNewInelasticModel);
` ` `

Then, in your MOOSE input file, you list your material model under the `inelastic_models` parameter of `ComputeMultipleInelasticStress`. 

` ` `ini
[Materials]
  [my_inelastic_model]
    type = MyNewInelasticModel
    # ... parameters for your model ...
  []
  [combined_inelastic_stress]
    type = ComputeMultipleInelasticStress
    inelastic_models = 'my_inelastic_model'
    # ... other parameters ...
  []
[]
` ` ` 

## Example: `IsotropicPlasticityStressUpdate`

The `IsotropicPlasticityStressUpdate` class provides a concrete example of this pattern. 

**Inheritance:** It inherits from `RadialReturnStressUpdateTempl<is_ad>`. 

**Overridden Methods:**
*   `computeStressInitialize`: Initializes the yield stress and hardening slope. 
*   `computeResidual`: Calculates the residual of the yield function. 
*   `computeDerivative`: Computes the derivative of the residual. 
*   `computeStressFinalize`: Updates the plastic strain history variable. 
*   `initQpStatefulProperties`: Initializes `_plastic_strain` and `_hardening_variable` to zero. 
*   `propagateQpStatefulProperties`: Propagates `_plastic_strain` and `_hardening_variable` from the old time step. 

**History Variables:** It declares `_plastic_strain`, `_plastic_strain_old`, `_hardening_variable`, and `_hardening_variable_old` as stateful material properties. 

## Notes

The `is_ad` template parameter indicates whether the class supports Automatic Differentiation. For new models, it's recommended to implement both `false` (for `Real` types) and `true` (for `ADReal` types) versions to leverage MOOSE's AD capabilities for Jacobian computation. 

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
