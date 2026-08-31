---
id: moose-derivative-parsed-material
title: MOOSE Phase Field Energy Parsing — DerivativeParsedMaterial
domain: phase-field
subdomain: algorithmic
tags:
- free-energy
- parsed-material
- symbolic-differentiation
- fparser
- derivative-material-interface
- CALPHAD
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: medium
reading_priority: full
akms_schema: v2
edges:
- to: cm-phase-field-fracture
  type: implements
  weight: 0.6
  note: DerivativeParsedMaterial is the core free energy engine for all PF models
---

# MOOSE Phase Field Energy Parsing — DerivativeParsedMaterial

Framework knowledge node covering 2 aspect(s) of Phase Field Energy Parsing — DerivativeParsedMaterial.

## Free energy parsing system

The MOOSE framework provides a robust system for parsing free energy expressions and automatically computing their derivatives, primarily through the `DerivativeParsedMaterial` class . This system leverages the `fparser` library for symbolic differentiation and allows for flexible definition of expressions, material properties, and coupled variables .

## Classes & Methods

*   `DerivativeParsedMaterial` : A material class that evaluates a parsed function and automatically provides its derivatives.
*   `DerivativeParsedMaterialHelperTempl::functionsPostParse()` : This method sets up variables and initiates the derivative generation process after the primary function has been parsed.
*   `DerivativeParsedMaterialHelperTempl::assembleDerivatives()` : Handles the assembly of the computed derivatives.
*   `FunctionMaterialPropertyDescriptor` : Parses and describes material properties, including their dependencies and derivation state.
*   `DerivativeSumMaterial` : A meta-material class designed to combine multiple derivative materials, effectively summing up various free energy contributions.

## `DerivativeParsedMaterial` and Automatic Differentiation

The `DerivativeParsedMaterial` class automatically computes derivatives of a user-defined string expression . It achieves this by using the `fparser` library, specifically `libmesh/fparser_ad.hh` , which provides symbolic differentiation capabilities. When you define an `expression` in your input file, `DerivativeParsedMaterial` parses this expression and then, based on the `derivative_order` parameter, generates the required first, second, and potentially third-order derivatives .

For example, if you provide an expression $f(\eta, c)$, the system can compute $\frac{\partial f}{\partial \eta}$, $\frac{\partial^2 f}{\partial \eta^2}$, $\frac{\partial^2 f}{\partial \eta \partial c}$, and so on . The `functionsPostParse()` method in `DerivativeParsedMaterialHelperTempl` is responsible for setting up the symbols and then triggering the derivative generation .

## `FunctionParserBase` / `fparser` Backend

The symbolic differentiation library used is `fparser`, specifically the `libmesh/fparser_ad.hh` header . This library allows MOOSE to parse mathematical expressions provided as strings and then symbolically differentiate them to obtain the required derivatives.

## Referencing Material Property Names

Material property names are referenced within parsed expressions using the `material_property_names` parameter . The `FunctionMaterialPropertyDescriptor` class is used to parse these names and understand their dependencies .

The syntax for `material_property_names` is flexible:
*   `F`: A material property `F` with no declared variable dependencies.
*   `F(c,phi)`: A material property `F` dependent on variables `c` and `phi`.
*   `d3x:=D[x(a,b),a,a,b]`: Defines a third derivative $\frac{\partial^3x}{\partial^2a\partial b}$ of material property `x` and assigns it the name `d3x` for use in the expression.
*   `dF:=D[F,c]`: Derivative of `F` with respect to `c`.
*   `F_old:=Old[F]` or `F_older:=Older[F]`: Accesses previous time step values of `F`.



## Coupling Between Parsed Materials

One `DerivativeParsedMaterial` can reference another by listing its output property name in its `material_property_names` parameter . For example, in the `GrandPotentialMultiphase.i` test, `omegab` references `Vm`, `kb`, and `cbeq`, which could be properties provided by other materials . The system automatically pulls in the necessary derivatives of these coupled material properties when constructing the derivatives of the parsed function .

## `DerivativeSumMaterial`

The `DerivativeSumMaterial` class is designed to combine multiple free energy contributions . It takes a list of material names via the `sum_materials` parameter and sums their contributions, potentially with prefactors and a constant term .

### Parameters
*   `sum_materials` (vector of strings): Base names of the parsed sum material properties .
*   `coupled_variables` (vector of strings): Names of variables being summed .
*   `prefactor` (vector of Reals, default: `{}`): Prefactor to multiply each sum term with .
*   `constant` (Real, default: `0.0`): Constant to be added to the prefactor multiplied sum .

## Performance: JIT-compilation and Caching

The parsed expressions can be JIT-compiled for performance . The `enable_jit` parameter controls this behavior . Derivatives are also cached internally to avoid redundant computations.

## Derivative Depth

The `DerivativeParsedMaterial` can automatically compute derivatives up to the third order . The maximum order is controlled by the `derivative_order` parameter . Only required derivatives are evaluated .

### Parameters
*   `derivative_order` (unsigned int, default: `3`): Maximum order of derivatives to be taken .

## `coupled_variables` Parameter

The `coupled_variables` parameter maps variable names to symbols in the expression . These are the primary variables with respect to which derivatives are always taken .

### Parameters
*   `coupled_variables` (vector of strings): Vector of names of variables used in the parsed function .

## Example Usage Pattern

Here's an example of a free energy expression using `DerivativeParsedMaterial` from a MOOSE input file :

` ` `ini
[Materials]
  [local_energy]
    type = DerivativeParsedMaterial
    block = 0
    f_name = f_loc
    args = c
    constant_names = 'A   B   C   D   E   F   G  eV_J  d'
    constant_expressions = '-2.446831e+04 -2.827533e+04 4.167994e+03 7.052907e+03
                            1.208993e+04 2.568625e+03 -2.354293e+03
                            6.24150934e+18 1e-27'
    function = 'eV_J*d*(A*c+B*(1-c)+C*c*log(c)+D*(1-c)*log(1-c)+
                E*c*(1-c)+F*c*(1-c)*(2*c-1)+G*c*(1-c)*(2*c-1)^2)'
  []
[]
` ` `


In this example:
*   `type = DerivativeParsedMaterial` specifies the material class .
*   `f_name = f_loc` gives a name to the free energy function .
*   `args = c` defines `c` as a coupled variable (though `coupled_variables` is the more explicit parameter) .
*   `constant_names` and `constant_expressions` define constants used in the expression .
*   `function` (or `expression`) contains the free energy formula .

## Relationships

` ` `mermaid
classDiagram
    class MooseObject
    class Material
    class ParsedMaterialBase
    class ParsedMaterialHelper
    class DerivativeParsedMaterialHelper
    class DerivativeParsedMaterial
    class DerivativeSumMaterial
    class FunctionMaterialPropertyDescriptor
    class DerivativeMaterialPropertyNameInterface

    MooseObject <|-- Material
    Material <|-- ParsedMaterialBase
    ParsedMaterialBase <|-- ParsedMaterialHelper
    ParsedMaterialHelper <|-- DerivativeParsedMaterialHelper
    DerivativeParsedMaterialHelper <|-- DerivativeParsedMaterial
    Material <|-- DerivativeSumMaterial

    DerivativeMaterialPropertyNameInterface <|-- FunctionMaterialPropertyDescriptor

    DerivativeParsedMaterialHelper "1" *-- "1" FunctionMaterialPropertyDescriptor : uses
    DerivativeParsedMaterialHelper "1" *-- "1" libmesh::fparser_ad : uses
` ` `

## Notes

The `ParsedMaterialBase` class provides the fundamental parsing capabilities for expressions, constants, and material properties . `DerivativeParsedMaterial` extends this by adding automatic differentiation . The `additional_derivative_symbols` parameter allows specifying extra symbols (beyond coupled variables) for which derivatives should be computed . The `DerivativeFunctionMaterialBase` is a more general base class for materials that compute functions and their derivatives, which `DerivativeParsedMaterial` ultimately builds upon .


## Custom free energy materials without parsing

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
