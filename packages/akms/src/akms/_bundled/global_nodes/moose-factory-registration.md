---
id: moose-factory-registration
title: MOOSE Object factory and registration pattern
domain: architecture
subdomain: procedural
tags:
- factory-pattern
- registerMooseObject
- validParams
- input-parameters
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: small
reading_priority: full
akms_schema: v2
edges:
- to: moose-object-factory
  type: refines
  weight: 0.9
  note: Fine-grained aspect of moose-object-factory
---

# MOOSE Object factory and registration pattern

The MOOSE framework utilizes a robust object factory and registration system to dynamically create objects based on input file specifications. This system is centered around the `MooseObjectFactory` (referred to as `Factory` in the code)  and the `Registry` . Classes declare their input parameters using a `static InputParameters validParams()` method , which the factory uses to validate and construct objects.

## 1. How `registerMooseObject()` macro works

The `registerMooseObject()` macro  is used to register a C++ class with the MOOSE framework's `Registry` . This macro creates a static character variable whose initialization calls `Registry::add<classname>()` .

It registers the class name (as a string) along with a factory function (implicitly, through the template `classname`) that can create an instance of that class . This allows the `Factory` to later construct objects of this type using only their string name from the input file .

**Code Snippet:**
` ` `cpp
#define registerMooseObject(app, classname)                                                        \
  static char combineNames(dummyvar_for_registering_obj_##classname, __COUNTER__) =                \
      Registry::add<classname>({app, #classname, "", "", __FILE__, __LINE__, "", ""})
` ` ` 

**Example Usage:**
` ` `cpp
registerMooseObject("MooseApp", BlockWeightedPartitioner);
` ` ` 
This line registers the `BlockWeightedPartitioner` class with the "MooseApp" application label .

## 2. The `MooseObjectFactory` (referred to as `Factory`)

The `Factory` class  is responsible for creating MOOSE objects from input file type strings. When an object needs to be created, the `Factory::create()` method  is called with the object's type name (string), instance name, and `InputParameters` .

The `createTempl` method  (a template function underlying `create`) first retrieves the `RegistryEntryBase` associated with the `obj_name` from its internal map `_name_to_object` . This `RegistryEntryBase` contains the necessary information, including a factory function, to construct the actual C++ object . The `build()` or `buildShared()` method of the `registry_entry` is then invoked, passing the validated `InputParameters` to the object's constructor .

## 3. `validParams()` — how each class declares its input parameters

Every `MooseObject`  (and its derived classes) declares its input parameters by implementing a `static InputParameters validParams()` method . This method returns an `InputParameters` object  that defines all the parameters the class can accept, including their types, default values, and documentation strings .

This follows a template pattern where each class explicitly defines its own parameter interface . Derived classes typically start by calling the `validParams()` method of their parent class to inherit parameters, then add their own specific parameters .

**Code Snippet:**
` ` `cpp
InputParameters
Convection::validParams()
{
  InputParameters params = Kernel::validParams();  // Start with parent
  params.addRequiredParam<RealVectorValue>("velocity", "Velocity Vector");
  params.addParam<Real>("coefficient", "Diffusion coefficient");
  return params;
}
` ` ` 

## 4. Parameter types: `MooseEnum`, `std::vector<>`, coupled variable references

MOOSE supports various parameter types, including:
*   **`MooseEnum`**: A "smart" enum utility that handles both integer and string contexts and is self-checked for consistency . It is declared by providing a space-separated list of valid options and an optional default value .
    **Example:**
    ` ` `cpp
    MooseEnum order(
        "CONSTANT FIRST SECOND THIRD FOURTH FIFTH SIXTH SEVENTH EIGHTH NINTH TENTH ELEVENTH TWELFTH "
        "THIRTEENTH FOURTEENTH FIFTEENTH SIXTEENTH SEVENTEENTH EIGHTTEENTH NINETEENTH TWENTIETH "
        "TWENTYFIRST TWENTYSECOND TWENTYTHIRD TWENTYFOURTH TWENTYFIFTH TWENTYSIXTH TWENTYSEVENTH "
        "TWENTYEIGHTH TWENTYNINTH THIRTIETH THIRTYFIRST THIRTYSECOND THIRTYTHIRD THIRTYFOURTH "
        "THIRTYFIFTH THIRTYSIXTH THIRTYSEVENTH THIRTYEIGHTH THIRTYNINTH FORTIETH FORTYFIRST "
        "FORTYSECOND FORTYTHIRD",
        "FIRST",
        true);
    params.addParam<MooseEnum>("order",
                               order,
                               "Order of the FE shape function to use for this variable (additional "
                               "orders not listed here are allowed, depending on the family).");
    ` ` ` 

*   **`std::vector<>`**: Standard C++ vectors are supported for lists of values .
    **Example:**
    ` ` `cpp
    params.addRequiredParam<std::vector<SubdomainName>>(
        "block", "The list of block ids (SubdomainID) that this object will be applied");
    ` ` ` 

*   **Coupled Variable References**: These are declared using `addCoupledVar()` . This method takes the variable name and an optional documentation string .
    **Example:**
    ` ` `cpp
    params.addCoupledVar("temperature", 0.0, "Coupled temperature");
    params.addCoupledVar("external_fields",
                         "The external fields that can be used in the UMAT subroutine");
    ` ` ` 

## 5. Required vs optional parameters, default values, documentation strings

The `InputParameters` class provides methods to define the characteristics of each parameter:
*   **Required Parameters**: Declared using `addRequiredParam<Type>("name", "documentation string")` . These parameters *must* be supplied in the input file .
    **Example:**
    ` ` `cpp
    params.addRequiredParam<int>("month", "Provide the month you were born.");
    ` ` ` 

*   **Optional Parameters with Default Values**: Declared using `addParam<Type>("name", default_value, "documentation string")` . If the parameter is not provided in the input file, the specified `default_value` is used .
    **Example:**
    ` ` `cpp
    params.addParam<int>("year", 1980, "Provide the year you were born.");
    ` ` ` 

*   **Documentation Strings**: A string provided as the last argument to `addParam` or `addRequiredParam` . This string is used for generating documentation for the parameter .

## 6. How the factory enforces parameter validation before object construction

The `Factory` ensures parameter validation happens before object construction through a two-step process:
1.  **`getValidParams()`**: When an object is requested, the `Factory` first calls `getValidParams()`  on the registered class type to obtain a pristine `InputParameters` object containing all declared parameters and their default values .
2.  **`initialize()`**: The `Factory::initialize()` method  then takes the `InputParameters` provided by the user (from the input file) and merges them with the valid parameters obtained from `getValidParams()` . During this process, it performs validation, checking for required parameters, type correctness, and range constraints .
3.  **Construction**: Only after successful validation and initialization of the `InputParameters` object is the actual object constructed by calling its constructor with the validated `InputParameters` . The `MooseObject` constructor itself contains an assertion to ensure it was constructed via the factory with validated parameters .

## 7. The `InputParameters` class — key methods

The `InputParameters` class  is central to MOOSE's parameter system. Key methods include:
*   `addRequiredParam<Type>("name", "doc_string")`: Adds a parameter that *must* be specified by the user .
*   `addParam<Type>("name", default_value, "doc_string")`: Adds an optional parameter with a default value .
*   `addCoupledVar("name", "doc_string")`: Adds a parameter that represents a coupled variable, allowing objects to depend on other variables in the simulation .

## Complete pattern from `validParams()` declaration through factory construction

### Classes & Methods:
*   `MooseObject::validParams()`: Static method in `MooseObject` and its derivatives to declare input parameters .
*   `InputParameters::addRequiredParam()`: Adds a mandatory parameter .
*   `InputParameters::addParam()`: Adds an optional parameter, potentially with a default value .

Wiki pages you might want to explore:
- [Core Application Architecture (idaholab/moose)](https://deepwiki.com/idaholab/moose#2)

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
