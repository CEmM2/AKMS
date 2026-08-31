---
id: moose-object-factory
title: MOOSE MOOSE Object System — Factory and Registration
domain: architecture
subdomain: procedural
tags:
- factory-pattern
- registration
- validParams
- input-parameters
- kernel
- material
- boundary-condition
- aux-kernel
status: tentative
confidence: 0.8
confidence_floor: 0.55
source: agent
context_size: medium
reading_priority: full
akms_schema: v2
edges:
- to: tgs-dom-fem
  type: implements
  weight: 0.6
  note: MOOSE object system underpins FEM kernel/material registration
- to: tgs-ref-style-architecture
  type: implements
  weight: 0.5
  note: Factory pattern defines the framework's extension architecture
---

# MOOSE MOOSE Object System — Factory and Registration

Framework knowledge node covering 2 aspect(s) of MOOSE Object System — Factory and Registration.

## Object factory and registration pattern

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


## MOOSE class hierarchy and system taxonomy

This response outlines the core systems in MOOSE as requested, detailing their base classes, essential virtual methods to override, and typical execution patterns.

## 1. Kernel — Volume Integrals (Weak Form Terms)

**Base Class:** The primary base class for Kernels is `Kernel` . For automatic differentiation (AD) enabled Kernels, the base class is `ADKernel` . Both inherit from `KernelBase` .

**Classes & Methods:**
*   `Kernel::computeQpResidual()`: Computes the Kernel's contribution to the residual at a quadrature point. This method *must* be overridden .
*   `Kernel::computeQpJacobian()`: Computes the Kernel's contribution to the diagonal Jacobian entries at a quadrature point .
*   `Kernel::computeQpOffDiagJacobian(unsigned int jvar)`: Computes the off-diagonal Jacobian entries for coupling with other variables .

**Execution Pattern:**
Kernels are responsible for computing terms in the weak form of a PDE. The `computeQpResidual()` method is called for each quadrature point within an element to calculate the residual contribution . Optionally, `computeQpJacobian()` and `computeQpOffDiagJacobian()` can be overridden to provide Jacobian contributions, which aid in solver convergence . These methods have access to various member variables like `_u` (variable value), `_grad_u` (variable gradient), `_test` (test function), and `_grad_test` (test function gradient) at the current quadrature point .

**Code Snippets:**
` ` `cpp
// From framework/include/kernels/Kernel.h
protected:
  /**
   * Compute this Kernel's contribution to the residual at the current quadrature point
   */
  virtual Real computeQpResidual() = 0;

  /**
   * Compute this Kernel's contribution to the Jacobian at the current quadrature point
   */
  virtual Real computeQpJacobian() { return 0; }

  /**
   * For coupling standard variables
   */
  virtual Real computeQpOffDiagJacobian(unsigned int /*jvar*/) { return 0; }
` ` ` 
` ` `cpp
// From test/src/kernels/DiffMKernel.C
Real
DiffMKernel::computeQpResidual()
{
  return _diff[_qp] * _grad_test[_i][_qp] * _grad_u[_qp] - _offset;
}

Real
DiffMKernel::computeQpJacobian()
{
  return _diff[_qp] * _grad_test[_i][_qp] * _grad_phi[_j][_qp];
}
` ` ` 

## 2. BoundaryCondition — DirichletBC, NeumannBC, IntegratedBC

**Base Class:** The base class for boundary conditions is `BoundaryCondition` . Integrated boundary conditions derive from `IntegratedBCBase` , while Dirichlet boundary conditions typically derive from `DirichletBCBase` .

**Classes & Methods:**
*   `IntegratedBCBase::computeQpResidual()`: (Implicitly, through `BoundaryCondition` and its derivatives) Computes the residual contribution from the boundary condition at a quadrature point.
*   `IntegratedBCBase::computeQpJacobian()`: (Implicitly) Computes the Jacobian contribution from the boundary condition at a quadrature point.

**Execution Pattern:**
Boundary conditions contribute to the residual and Jacobian on the boundaries of the domain. For `IntegratedBCBase` objects, the `computeQpResidual()` and `computeQpJacobian()` methods are called for quadrature points on the boundary faces of elements . These methods have access to boundary-specific data such as `_current_side`, `_current_side_volume`, and `_current_boundary_id` .

**Code Snippets:**
` ` `cpp
// From framework/include/bcs/IntegratedBCBase.h
class IntegratedBCBase : public BoundaryCondition,
                         public CoupleableMooseVariableDependencyIntermediateInterface,
                         public MaterialPropertyInterface
{
public:
  static InputParameters validParams();

  IntegratedBCBase(const InputParameters & parameters);

  void prepareShapes(unsigned int var_num) override final;

  virtual bool shouldApply() const override;

protected:
  /// current element
  const Elem * const & _current_elem;
  /// Volume of the current element
  const Real & _current_elem_volume;
  /// current side of the current element
  const unsigned int & _current_side;
  /// current side element
  const Elem * const & _current_side_elem;
  /// Volume of the current side
  const Real & _current_side_volume;
  /// The currenty boundary id
  const BoundaryID & _current_boundary_id;

  /// quadrature point index
  unsigned int _qp;
  /// active quadrature rule
  const QBase * const & _qrule;
  /// active quadrature points
  const MooseArray<Point> & _q_point;
  /// transformed Jacobian weights
  const MooseArray<Real> & _JxW;
  /// coordinate transformation
  const MooseArray<Real> & _coord;
  /// i-th, j-th index for enumerating test and shape functions
  unsigned int _i, _j;
` ` ` 

## 3. Material — MaterialProperty Computation

**Base Class:** The base class for materials is `MaterialBase` .

**Classes & Methods:**
*   `MaterialBase::computeProperties()`: This pure virtual method *must* be overridden to compute material properties .
*   `MaterialBase::initStatefulProperties(const unsigned int n_points)`: Initializes stateful properties .

**Execution Pattern:**
Material objects compute spatially and/or temporally varying properties, which are typically indexed at individual quadrature points . The `computeProperties()` method is invoked to calculate these properties, which can then be accessed by other MOOSE systems like Kernels and Boundary Conditions . Materials can also declare and consume properties from other materials or variables .

**Code Snippets:**
` ` `cpp
// From framework/include/materials/MaterialBase.h
class MaterialBase : public MooseObject,
                     public BlockRestrictable,
                     public BoundaryRestrictable,
                     public SetupInterface,
                     public MooseVariableDependencyInterface,
                     public ScalarCoupleable,
                     public FunctionInterface,
                     public DistributionInterface,
                     public UserObjectInterface,
                     public TransientInterface,
                     public PostprocessorInterface,
                     public VectorPostprocessorInterface,
                     public DependencyResolverInterface,
                     public Restartable,
                     public MeshChangedInterface,
                     public OutputInterface,
                     public RandomInterface,
                     public ElementIDInterface,
                     protected GeometricSearchInterface,
                     protected ADFunctorInterface
{
public:
  static InputParameters validParams();

  MaterialBase(const InputParameters & parameters);

#ifdef MOOSE_KOKKOS_ENABLED
  /**
   * Special constructor used for Kokkos functor copy during parallel dispatch
   */
  MaterialBase(const MaterialBase & object, const Moose::Kokkos::FunctorCopy & key);
#endif

  /**
   * Initialize stateful properties (if material has some)
   *
   * This is _only_ called if this material has properties that are
   * requested as stateful
   */
  virtual void initStatefulProperties(const unsigned int n_points);

  virtual bool isInterfaceMaterial() { return false; };

  /**
   * Performs the quadrature point loop, calling computeQpProperties
   */
  virtual void computeProperties() = 0;
` ` ` 

## 4. AuxKernel — Auxiliary Variable Computation

**Base Class:** The base class for auxiliary kernels is `AuxKernelTempl<ComputeValueType>` , which inherits from `AuxKernelBase` . `AuxKernel` is a typedef for `AuxKernelTempl<Real>` .

**Classes & Methods:**
*   `AuxKernelTempl::computeValue()`: This pure virtual method *must* be overridden to compute the value of the auxiliary variable .
*   `AuxKernelTempl::compute()`: Computes the value and stores it in the solution vector .

**Execution Pattern:**
AuxKernels compute and set explicitly known values of auxiliary variables . Unlike Kernels, AuxKernels do not compute residuals and do not involve test functions . The `computeValue()` method is called to determine the value of the auxiliary variable, which is then inserted into the auxiliary solution vector . AuxKernels can operate on elemental or nodal auxiliary variables .

**Code Snippets:**
` ` `cpp
// From framework/include/auxkernels/AuxKernel.h
protected:
  /**
   * Compute and return the value of the aux variable.
   */
  virtual ComputeValueType computeValue() = 0;
` ` ` 
` ` `cpp
// From framework/include/auxkernels/AuxKernel.h
  /**
   * Computes the value and stores it in the solution vector
   */
  virtual void compute() override;
` ` ` 

## 5. UserObject — General Computation Objects (Postprocessors, VectorPostprocessors)

**Base Class:** The base class for UserObjects is `UserObject` .

**Classes & Methods:**
*   `UserObject::execute()`: Performs the main computation of the UserObject.
*   `UserObject::getValue()`: Returns the computed value of the UserObject.

**Execution Pattern:**
UserObjects are general computation objects that can perform various tasks. They are often used for post-processing, data analysis, or to provide values to other MOOSE objects . The `execute()` method is called at different times depending on the type of UserObject (e.g., `GeneralPostprocessor`, `NodalPostprocessor`, `ElementalPostprocessor`) and the configured execution flags . The `getValue()` method is responsible for returning the result of the computation .

## 6. Constraint — Nodal/Mortar Constraints

**Base Class:** The base class for constraints is `Constraint` . Specific types include `NodalConstraint`  and `MortarConstraint` .

**Classes & Methods:**
*   `Constraint::constrain()`: Applies the constraint to the system.

**Execution Pattern:**
Constraints are used to enforce relationships between degrees of freedom, such as nodal constraints or mortar constraints for non-conforming meshes. They modify the system's residual and Jacobian to impose these conditions. The `constrain()` method is typically called during the assembly process to apply the constraint equations.

## 7. DGKernel — Discontinuous Galerkin

**Base Class:** The base class for Discontinuous Galerkin (DG) Kernels is `DGKernelBase` .

**Classes & Methods:**
*   `DGKernelBase::computeQpResidual()`: Computes the residual contribution for DG terms at a quadrature point.
*   `DGKernelBase::computeQpJacobian()`: Computes the Jacobian contribution for DG terms at a quadrature point.

Wiki pages you might want to explore:
- [Problem Solving Architecture (idaholab/moose)](https://deepwiki.com/idaholab/moose#3)

Source: this node summarizes the MOOSE framework (https://github.com/idaholab/moose), indexed at https://deepwiki.com/idaholab/moose. See THIRD_PARTY_NOTICES.md for attribution and licensing.
