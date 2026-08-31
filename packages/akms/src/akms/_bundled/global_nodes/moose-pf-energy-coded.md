---
id: moose-pf-energy-coded
title: MOOSE Custom free energy materials without parsing
domain: phase-field
subdomain: algorithmic
tags:
- DerivativeMaterialInterface
- CALPHAD
- sublattice
- custom-free-energy
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-derivative-parsed-material
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-derivative-parsed-material
---

# MOOSE Custom free energy materials without parsing

MOOSE handles coded (C++) free energy materials through the `DerivativeMaterialInterface` and `DerivativeFunctionMaterialBase` classes, which allow you to define a free energy function and its derivatives. Kernels like `AllenCahn` and `SplitCHParsed` then consume these registered derivatives. 

## Classes & Methods

### `DerivativeMaterialInterface`
The `DerivativeMaterialInterface` class is a veneer that provides methods for declaring and retrieving derivative material properties. 

### `DerivativeFunctionMaterialBase`
The `DerivativeFunctionMaterialBase` class is a base class for materials that compute a function and its derivatives. 

#### Methods to Implement in a Custom Material
When implementing a custom material that inherits from `DerivativeFunctionMaterialBase`, you must override the following methods to define your free energy function and its derivatives:
*   `computeF()`: Overridden to provide the free energy function. 
*   `computeDF(unsigned int arg)`: Overridden to calculate the first derivatives. 
*   `computeD2F(unsigned int arg1, unsigned int arg2)`: Overridden to calculate the second derivatives. 
*   `computeD3F(unsigned int, unsigned int, unsigned int)`: Optionally overridden to calculate the third derivatives. 

### `DerivativeMaterialPropertyNameInterface`
This interface provides helper functions to generate material property names for arbitrary derivatives. 

#### Naming Convention for Derivative Properties
The naming convention for derivative properties is handled by helper functions in `DerivativeMaterialPropertyNameInterface`. 
*   `derivativePropertyNameFirst(const MaterialPropertyName & base, const SymbolName & c1)`: Generates the name for the first derivative, e.g., `d{base}/d{c1}`. 
*   `derivativePropertyNameSecond(const MaterialPropertyName & base, const SymbolName & c1, const SymbolName & c2)`: Generates the name for the second derivative, e.g., `d2{base}/d{c1}d{c2}`. 
*   `derivativePropertyNameThird(const MaterialPropertyName & base, const SymbolName & c1, const SymbolName & c2, const SymbolName & c3)`: Generates the name for the third derivative. 

### `DerivativeMaterialInterface::getMaterialPropertyDerivative()`
This method is used to retrieve derivative material properties. It has several overloads to handle different ways of specifying the variables with respect to which the derivative is taken.  For example, you can retrieve a derivative by providing the base property name and the names of the coupled variables, or by using indices into the `_coupled_standard_moose_vars` vector. 

` ` `cpp
template <typename U, bool is_ad = false>
const GenericMaterialProperty<U, is_ad> &
DerivativeMaterialInterface<T>::getMaterialPropertyDerivative(const std::string & base,
                                                              const SymbolName & c1,
                                                              unsigned int v2,
                                                              unsigned int v3)
{
  return getMaterialPropertyDerivative<U, is_ad>(
      base,
      c1,
      this->_coupled_standard_moose_vars[v2]->name(),
      v3 == libMesh::invalid_uint ? "" : this->_coupled_standard_moose_vars[v3]->name());
}
` ` ` 
This snippet shows an overload that takes a `SymbolName` for the first variable and `unsigned int` indices for the second and third variables.  It converts the `unsigned int` indices to variable names using `this->_coupled_standard_moose_vars[vX]->name()`. 

## Example: Implementing a CALPHAD-type Gibbs energy with sublattice models in C++

To implement a custom free energy, you would create a new C++ class that inherits from `DerivativeFunctionMaterialBase`. 

` ` `cpp
// In your custom material's header file (e.g., MyCalphadMaterial.h)
#pragma once

#include "DerivativeFunctionMaterialBase.h"

class MyCalphadMaterial : public DerivativeFunctionMaterialBase
{
public:
  static InputParameters validParams();
  MyCalphadMaterial(const InputParameters & parameters);

protected:
  virtual Real computeF() override;
  virtual Real computeDF(unsigned int arg) override;
  virtual Real computeD2F(unsigned int arg1, unsigned int arg2) override;
  virtual Real computeD3F(unsigned int arg1, unsigned int arg2, unsigned int arg3) override;

private:
  // Declare coupled variables for concentrations, temperature, etc.
  const VariableValue & _c1;
  const VariableValue & _c2;
  const VariableValue & _temp;

  unsigned int _c1_var;
  unsigned int _c2_var;
  unsigned int _temp_var;
};
` ` ` 

` ` `cpp
// In your custom material's source file (e.g., MyCalphadMaterial.C)
#include "MyCalphadMaterial.h"

registerMooseObject("MyPhaseFieldApp", MyCalphadMaterial);

InputParameters
MyCalphadMaterial::validParams()
{
  InputParameters params = DerivativeFunctionMaterialBase::validParams();
  params.addClassDescription("Custom CALPHAD-type Gibbs Free Energy Material");
  params.addRequiredCoupledVar("c1", "First concentration variable");
  params.addRequiredCoupledVar("c2", "Second concentration variable");
  params.addRequiredCoupledVar("temperature", "Temperature variable");
  return params;
}

MyCalphadMaterial::MyCalphadMaterial(const InputParameters & parameters)
  : DerivativeFunctionMaterialBase(parameters),
    _c1(coupledValue("c1")),
    _c2(coupledValue("c2")),
    _temp(coupledValue("temperature")),
    _c1_var(coupled("c1")),
    _c2_var(coupled("c2")),
    _temp_var(coupled("temperature"))
{
}

Real
MyCalphadMaterial::computeF()
{
  // Implement your CALPHAD Gibbs energy function here
  // Example: G = c1*ln(c1) + c2*ln(c2) + (1-c1-c2)*ln(1-c1-c2) + ...
  const Real c1 = _c1[_qp];
  const Real c2 = _c2[_qp];
  const Real temp = _temp[_qp];
  // ... complex CALPHAD expression ...
  return c1 * std::log(c1) + c2 * std::log(c2) + (1.0 - c1 - c2) * std::log(1.0 - c1 - c2) + temp; // Placeholder
}

Real
MyCalphadMaterial::computeDF(unsigned int arg)
{
  // Implement the first derivative of computeF with respect to the variable 'arg'
  if (arg == _c1_var)
  {
    // dF/dc1
    return std::log(_c1[_qp]) + 1.0 - std::log(1.0 - _c1[_qp] - _c2[_qp]) - 1.0; // Placeholder
  }
  if (arg == _c2_var)
  {
    // dF/dc2
    return std::log(_c2[_qp]) + 1.0 - std::log(1.0 - _c1[_qp] - _c2[_qp]) - 1.0; // Placeholder
  }
  if (arg == _temp_var)
  {
    // dF/dT
    return 1.0; // Placeholder
  }
  return 0.0;
}

Real
MyCalphadMaterial::computeD2F(unsigned int arg1, unsigned int arg2)
{
  // Implement the second derivative of computeF
  if (arg1 == _c1_var && arg2 == _c1_var)
  {
    // d2F/dc1dc1
    return 1.0 / _c1[_qp] + 1.0 / (1.0 - _c1[_qp] - _c2[_qp]); // Placeholder
  }
  if (arg1 == _c1_var && arg2 == _c2_var)
  {
    // d2F/dc1dc2
    return 1.0 / (1.0 - _c1[_qp] - _c2[_qp]); // Placeholder
  }
  // ... and so on for all combinations
  return 0.0;
}

Real
MyCalphadMaterial::computeD3F(unsigned int arg1, unsigned int arg2, unsigned int arg3)
{
  // Implement the third derivative of computeF (optional)
  return 0.0;
}
` ` ` 

## Registering Derivatives for Kernels

Kernels like `AllenCahn` and `SplitCHParsed` consume derivatives by requesting them from the material system using `getMaterialPropertyDerivative()`. 

For example, in `AllenCahn`, the first and second derivatives of the free energy `f_name` with respect to the order parameter `_var.name()` are retrieved:
` ` `cpp
AllenCahn::AllenCahn(const InputParameters & parameters)
  : ACBulk<Real>(parameters),
    _dFdEta(getMaterialPropertyDerivative<Real>("f_name", _var.name())),
    _d2FdEta2(getMaterialPropertyDerivative<Real>("f_name", _var.name(), _var.name())),
    _d2FdEtadarg(_n_args)
{
  // Iterate over all coupled variables
  for (unsigned int i = 0; i < _n_args; ++i)
    _d2FdEtadarg[i] = &getMaterialPropertyDerivative<Real>("f_name", _var.name(), i);
}
` ` ` 
Here, `_dFdEta` stores $\frac{\partial F}{\partial \eta}$ and `_d2FdEta2` stores $\frac{\partial^2 F}{\partial \eta^2}$.  The loop then retrieves mixed second derivatives $\frac{\partial^2 F}{\partial \eta \partial arg_i}$ for all other coupled variables. 

The `DerivativeFunctionMaterialBase` class automatically declares and registers these derivative properties based on the `computeF`, `computeDF`, `computeD2F`, and `computeD3F` methods you implement.  When a kernel requests a derivative using `getMaterialPropertyDerivative()`, the material system looks up the corresponding property that was computed by your custom material. 

## Relationships

` ` `mermaid
classDiagram
    class Material {
        +computeQpProperties()
    }
    class DerivativeMaterialPropertyNameInterface {
        +derivativePropertyNameFirst()
        +derivativePropertyNameSecond()
        +derivativePropertyNameThird()
    }
    class DerivativeMaterialInterface {
        +getMaterialPropertyDerivative()
        +declarePropertyDerivative()
    }
    class FunctionMaterialBase {
        +computeProperties()
    }
    class DerivativeFunctionMaterialBase {
        +computeF()
        +computeDF(arg)
        +computeD2F(arg1, arg2)
        +computeD3F(arg1, arg2, arg3)
    }
    class AllenCahn {
        -_dFdEta
        -_d2FdEta2
        -_d2FdEtadarg
    }
    class SplitCHParsed {
        -_dFdc
        -_d2Fdc2
        -_d2Fdcdarg
    }
    class MyCalphadMaterial {
        +computeF()
        +computeDF(arg)
        +computeD2F(arg1, arg2)
        +computeD3F(arg1, arg2, arg3)
    }

    DerivativeMaterialInterface <|-- DerivativeFunctionMaterialBase : public
    DerivativeMaterialPropertyNameInterface <|-- DerivativeMaterialInterface : public
    FunctionMaterialBase <|-- DerivativeFunctionMaterialBase : public
    DerivativeMaterialInterface <|-- AllenCahn : public
    DerivativeMaterialInterface <|-- SplitCHParsed : public
    DerivativeFunctionMaterialBase <|-- MyCalphadMaterial : public

    AllenCahn ..> DerivativeMaterialInterface : uses getMaterialPropertyDerivative()
    SplitCHParsed ..> DerivativeMaterialInterface : uses getMaterialPropertyDerivative()
    MyCalphadMaterial ..> Material : provides properties
` ` `

## Notes
The `DerivativeParsedMaterial` is a related class that automatically performs symbolic differentiation for free energy functions defined by string expressions in the input file.  However, the user's query specifically asks about cases "too complex for string parsing," which points to implementing a custom C++ material inheriting from `DerivativeFunctionMaterialBase`.  The `MathFree

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
