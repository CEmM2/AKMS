---
id: moose-pf-energy-parsing
title: MOOSE Free energy parsing system
domain: phase-field
subdomain: algorithmic
tags:
- DerivativeParsedMaterial
- fparser
- symbolic-differentiation
- JIT
- coupled-variables
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

# MOOSE Free energy parsing system

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

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
