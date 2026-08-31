---
id: moose-system-taxonomy
title: MOOSE MOOSE class hierarchy and system taxonomy
domain: architecture
subdomain: procedural
tags:
- kernel
- material
- boundary-condition
- aux-kernel
- user-object
- DG-kernel
- interface-kernel
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

# MOOSE MOOSE class hierarchy and system taxonomy

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
